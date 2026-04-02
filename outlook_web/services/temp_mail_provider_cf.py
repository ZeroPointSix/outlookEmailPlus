"""
CloudflareTempMailProvider
~~~~~~~~~~~~~~~~~~~~~~~~~~

对接 dreamhunter2333/cloudflare_temp_email 的 TempMailProviderBase 实现。

认证模型
--------
- 管理操作（创建/删除邮箱）：HTTP 头 ``x-admin-auth: <ADMIN_PASSWORD>``
- 用户操作（读取/删除邮件）：HTTP 头 ``Authorization: Bearer <jwt>``
  JWT 在创建邮箱时由 CF Worker 颁发，存储在 mailbox.meta["provider_jwt"]。

字段映射
--------
CF Worker 使用以下非标准字段名，本模块统一转换为平台标准字段名：
- ``source``      -> ``from_address``
- ``created_at``  -> ``timestamp`` (ISO 8601 -> int unix timestamp)
- ``id``          -> ``message_id`` (加 "cf_" 前缀，避免与其他 provider 冲突)
- ``raw``         -> 解析 MIME 后提取 subject/content/html_content/has_html
"""

from __future__ import annotations

import email as _email_lib
import email.policy
import json
import logging
import secrets
import string
from datetime import datetime, timezone
from typing import Any

import requests

from outlook_web.repositories import settings as settings_repo
from outlook_web.services.temp_mail_provider_base import TempMailProviderBase

logger = logging.getLogger(__name__)

_CF_REQUEST_TIMEOUT = 30  # seconds

DEFAULT_PREFIX_RULES = {
    "min_length": 1,
    "max_length": 32,
    "pattern": r"^[a-z0-9][a-z0-9._-]*$",
}


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class CloudflareTempMailProviderError(Exception):
    def __init__(self, code: str, message: str, *, data: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _map_cf_http_error(status_code: int, text: str = "") -> str:
    if status_code in (401, 403):
        return "UNAUTHORIZED"
    if status_code == 404:
        return "TEMP_EMAIL_NOT_FOUND"
    if status_code == 429:
        return "UPSTREAM_RATE_LIMITED"
    if status_code >= 500:
        return "UPSTREAM_SERVER_ERROR"
    return "UPSTREAM_BAD_PAYLOAD"


def _iso_to_timestamp(iso_str: str) -> int:
    """将 CF Worker 返回的 ISO 8601 字符串转换为 Unix timestamp（整数）。"""
    try:
        clean = iso_str.replace("Z", "+00:00")
        # 兼容毫秒格式：2025-12-07T10:30:00.000+00:00
        if "." in clean:
            clean = clean[: clean.index(".")] + clean[clean.index("+") :]
        return int(datetime.fromisoformat(clean).timestamp())
    except (ValueError, AttributeError):
        return 0


def _parse_mime_raw(raw_mime: str) -> dict[str, Any]:
    """
    使用 Python 标准库解析 CF Worker 返回的原始 MIME 字符串。

    返回包含以下键的字典：
    - subject       : str
    - from_address  : str
    - content       : str  （纯文本正文）
    - html_content  : str  （HTML 正文，可能为空）
    - has_html      : bool
    """
    try:
        msg = _email_lib.message_from_string(
            raw_mime, policy=_email_lib.policy.compat32
        )
    except Exception:
        return {
            "subject": "",
            "from_address": "",
            "content": raw_mime,
            "html_content": "",
            "has_html": False,
        }

    # subject
    raw_subject = msg.get("Subject", "") or ""
    try:
        from email.header import decode_header as _decode_header

        decoded_parts = _decode_header(raw_subject)
        subject_parts = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                subject_parts.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                subject_parts.append(str(part))
        subject = "".join(subject_parts)
    except Exception:
        subject = raw_subject

    # from_address
    from_address = str(msg.get("From", "") or "").strip()

    # body parts
    plain_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cdisp = str(part.get("Content-Disposition") or "")
            if "attachment" in cdisp:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                text = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if ct == "text/plain":
                plain_parts.append(text)
            elif ct == "text/html":
                html_parts.append(text)
    else:
        ct = msg.get_content_type()
        charset = msg.get_content_charset() or "utf-8"
        try:
            payload = msg.get_payload(decode=True)
            text = payload.decode(charset, errors="replace") if payload else ""
        except Exception:
            text = str(msg.get_payload() or "")
        if ct == "text/html":
            html_parts.append(text)
        else:
            plain_parts.append(text)

    content = "\n".join(plain_parts).strip()
    html_content = "\n".join(html_parts).strip()
    has_html = bool(html_content)

    return {
        "subject": subject,
        "from_address": from_address,
        "content": content,
        "html_content": html_content,
        "has_html": has_html,
    }


def _normalize_domain_entries(
    raw_domains: Any, default_domain: str
) -> list[dict[str, Any]]:
    domains: list[dict[str, Any]] = []
    seen: set[str] = set()
    values: list[Any] = raw_domains if isinstance(raw_domains, list) else []
    for item in values:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            enabled = bool(item.get("enabled", True))
        else:
            name = str(item or "").strip()
            enabled = True
        if not name or name in seen:
            continue
        seen.add(name)
        domains.append(
            {
                "name": name,
                "enabled": enabled,
                "is_default": bool(default_domain and name == default_domain),
            }
        )
    if default_domain and default_domain not in seen:
        domains.append({"name": default_domain, "enabled": True, "is_default": True})
    return domains


# ---------------------------------------------------------------------------
# Provider 实现
# ---------------------------------------------------------------------------


class CloudflareTempMailProvider(TempMailProviderBase):
    """
    对接 Cloudflare Workers Temp Email 的 Provider 实现。

    配置读取（来自 settings 表）：
    - ``temp_mail_api_base_url`` : CF Worker 部署地址（如 https://mail.example.workers.dev）
    - ``temp_mail_api_key``      : CF Worker ADMIN_PASSWORDS 中的一个值
    - ``temp_mail_domains``      : CF Worker 配置的域名列表（JSON 数组）
    - ``temp_mail_default_domain``: 默认域名
    """

    def __init__(self, *, provider_name: str | None = None):
        self.provider_name = provider_name or "cloudflare_temp_mail"

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _base_url(self) -> str:
        """读取 CF Worker 独立部署地址（cf_worker_base_url），与 GPTMail 设置完全隔离。"""
        url = settings_repo.get_cf_worker_base_url().rstrip("/")
        return url

    def _admin_key(self) -> str:
        """读取 CF Worker 独立 Admin 密码（cf_worker_admin_key）。"""
        return settings_repo.get_cf_worker_admin_key()

    def _admin_headers(self) -> dict[str, str]:
        return {"x-admin-auth": self._admin_key(), "Content-Type": "application/json"}

    def _user_headers(self, jwt: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}

    def _coerce_email(self, mailbox: dict[str, Any] | str) -> str:
        if isinstance(mailbox, dict):
            return str(mailbox.get("email") or "").strip()
        return str(mailbox or "").strip()

    def _get_jwt(self, mailbox: dict[str, Any] | str) -> str:
        """从 mailbox.meta 中取出 provider_jwt；无则返回空串。"""
        if isinstance(mailbox, dict):
            meta = mailbox.get("meta") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            return str(meta.get("provider_jwt") or "").strip()
        return ""

    def _build_meta(self, *, jwt: str = "", address_id: str = "") -> dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "provider_mailbox_id": address_id,
            "provider_jwt": jwt,
            "provider_cursor": "",
            "provider_labels": [],
            "provider_capabilities": {
                "delete_mailbox": True,
                "delete_message": True,
                "clear_messages": True,
            },
            "provider_debug": {"bridge": "cloudflare_worker"},
        }

    def _raise_http_error(self, resp: requests.Response, *, operation: str) -> None:
        code = _map_cf_http_error(resp.status_code, resp.text)
        raise CloudflareTempMailProviderError(
            code,
            f"CF Worker {operation} 失败 HTTP {resp.status_code}",
            data={"status_code": resp.status_code, "body": resp.text[:500]},
        )

    # ------------------------------------------------------------------
    # TempMailProviderBase 接口实现
    # ------------------------------------------------------------------

    def get_options(self) -> dict[str, Any]:
        raw_domains_str = settings_repo.get_setting("temp_mail_domains", "[]")
        default_domain = settings_repo.get_setting(
            "temp_mail_default_domain", ""
        ).strip()
        raw_prefix_rules_str = (
            settings_repo.get_setting("temp_mail_prefix_rules", "") or ""
        )

        try:
            domains_payload = json.loads(raw_domains_str)
        except (json.JSONDecodeError, TypeError):
            domains_payload = []

        try:
            prefix_rules = (
                json.loads(raw_prefix_rules_str) if raw_prefix_rules_str else {}
            )
        except (json.JSONDecodeError, TypeError):
            prefix_rules = {}

        normalized_prefix_rules = {
            "min_length": int(
                prefix_rules.get("min_length", DEFAULT_PREFIX_RULES["min_length"])
            ),
            "max_length": int(
                prefix_rules.get("max_length", DEFAULT_PREFIX_RULES["max_length"])
            ),
            "pattern": str(
                prefix_rules.get("pattern") or DEFAULT_PREFIX_RULES["pattern"]
            ),
        }

        return {
            "domain_strategy": "auto_or_manual",
            "default_mode": "auto",
            "domains": _normalize_domain_entries(domains_payload, default_domain),
            "prefix_rules": normalized_prefix_rules,
            "provider": self.provider_name,
            "provider_name": self.provider_name,
            "provider_label": "cloudflare_temp_mail",
            "api_base_url": self._base_url(),
        }

    def create_mailbox(
        self, *, prefix: str | None = None, domain: str | None = None
    ) -> dict[str, Any]:
        """
        调用 POST /admin/new_address 创建邮箱。

        返回格式：
        - 成功：{"success": True, "email": "...", "meta": {...}}
        - 失败：{"success": False, "error": "...", "error_code": "..."}
        """
        base_url = self._base_url()
        if not base_url:
            return {
                "success": False,
                "error": "CF Worker base_url 未配置",
                "error_code": "TEMP_MAIL_PROVIDER_NOT_CONFIGURED",
            }
        if not self._admin_key():
            return {
                "success": False,
                "error": "CF Worker admin key 未配置",
                "error_code": "TEMP_MAIL_PROVIDER_NOT_CONFIGURED",
            }

        # 确定目标域名
        options = self.get_options()
        domains_list: list[dict[str, Any]] = options.get("domains") or []
        enabled_domains = [d["name"] for d in domains_list if d.get("enabled")]
        target_domain = (domain or "").strip()
        if not target_domain:
            # 优先使用 is_default，其次第一个 enabled
            for d in domains_list:
                if d.get("is_default") and d.get("enabled"):
                    target_domain = d["name"]
                    break
            if not target_domain and enabled_domains:
                target_domain = enabled_domains[0]

        if not target_domain:
            return {
                "success": False,
                "error": "未配置可用域名",
                "error_code": "TEMP_MAIL_PROVIDER_NOT_CONFIGURED",
            }

        # 注意：部分 CF Worker 部署版本（如 zerodotsix.top）不支持显式 domain 字段，
        # 传入 domain 字段会导致 400 "Required field is missing"。
        # 解决方案：始终省略 domain 字段，让 CF Worker 使用其内置默认域名。
        # 当配置的 target_domain 与 CF Worker 实际默认域名一致时，结果相同。

        # CF Worker 要求 name 不能为空字符串（空串会返回 400 "Required field is missing"）。
        # 当调用方未指定 prefix 时，在 Python 侧生成随机 8 字符前缀。
        effective_name = (prefix or "").strip()
        if not effective_name:
            alphabet = string.ascii_lowercase + string.digits
            effective_name = "".join(secrets.choice(alphabet) for _ in range(8))

        payload: dict[str, Any] = {
            "name": effective_name,
            "enablePrefix": False,  # BUG-CF-06：禁止 CF 自动加前缀
        }

        try:
            resp = requests.post(
                f"{base_url}/admin/new_address",
                headers=self._admin_headers(),
                json=payload,
                timeout=_CF_REQUEST_TIMEOUT,
            )
        except requests.Timeout:
            return {
                "success": False,
                "error": "CF Worker 请求超时",
                "error_code": "UPSTREAM_TIMEOUT",
            }
        except requests.RequestException as exc:
            return {
                "success": False,
                "error": f"CF Worker 网络错误: {exc}",
                "error_code": "UPSTREAM_SERVER_ERROR",
            }

        if not resp.ok:
            code = _map_cf_http_error(resp.status_code, resp.text)
            return {
                "success": False,
                "error": f"CF Worker 创建邮箱失败 HTTP {resp.status_code}",
                "error_code": code,
            }

        try:
            data = resp.json()
        except Exception:
            return {
                "success": False,
                "error": "CF Worker 返回非 JSON 响应",
                "error_code": "UPSTREAM_BAD_PAYLOAD",
            }

        address = str(data.get("address") or "").strip()
        jwt = str(data.get("jwt") or "").strip()
        address_id = str(data.get("address_id") or data.get("id") or "").strip()

        if not address:
            return {
                "success": False,
                "error": "CF Worker 未返回邮箱地址",
                "error_code": "UPSTREAM_BAD_PAYLOAD",
            }

        return {
            "success": True,
            "email": address,
            "meta": self._build_meta(jwt=jwt, address_id=address_id),
        }

    def delete_mailbox(self, mailbox: dict[str, Any]) -> bool:
        """调用 DELETE /admin/delete_address/:id 删除邮箱（按数字 address_id）。

        CF Worker 正确路由为 DELETE /admin/delete_address/{id}，
        id 是创建邮箱时返回的数字 address_id，存储在 meta["provider_mailbox_id"] 中。
        """
        address_id = ""
        if isinstance(mailbox, dict):
            meta_raw = mailbox.get("meta") or {}
            if isinstance(meta_raw, str):
                try:
                    meta_raw = json.loads(meta_raw)
                except Exception:
                    meta_raw = {}
            address_id = str(meta_raw.get("provider_mailbox_id") or "").strip()

        if not address_id:
            email_addr = self._coerce_email(mailbox)
            logger.warning(
                "[cf_provider] delete_mailbox: no address_id in meta for %s, cannot delete",
                email_addr,
            )
            return False

        base_url = self._base_url()
        try:
            resp = requests.delete(
                f"{base_url}/admin/delete_address/{address_id}",
                headers=self._admin_headers(),
                timeout=_CF_REQUEST_TIMEOUT,
            )
            return resp.ok
        except requests.RequestException as exc:
            logger.warning(
                "[cf_provider] delete_mailbox failed id=%s err=%s", address_id, exc
            )
            return False

    def list_messages(self, mailbox: dict[str, Any] | str) -> list[dict[str, Any]]:
        """
        调用 GET /api/mails?limit=100&offset=0 获取邮件列表，解析每封邮件的 raw MIME。

        注意：正确路由为 /api/mails（不是 /mails，后者返回 HTML 前端页面）。

        返回列表中每项的字段符合平台标准（供 save_temp_email_messages 使用）：
        - id, message_id, from_address, subject, content, html_content, has_html, timestamp
        """
        email_addr = self._coerce_email(mailbox)
        jwt = self._get_jwt(mailbox) if isinstance(mailbox, dict) else ""

        if not jwt:
            raise CloudflareTempMailProviderError(
                "UNAUTHORIZED",
                f"邮箱 {email_addr} 缺少 provider_jwt，无法读取邮件",
                data={"email": email_addr},
            )

        base_url = self._base_url()
        try:
            resp = requests.get(
                f"{base_url}/api/mails",
                params={"limit": 100, "offset": 0},
                headers=self._user_headers(jwt),
                timeout=_CF_REQUEST_TIMEOUT,
            )
        except requests.Timeout:
            raise CloudflareTempMailProviderError(
                "UPSTREAM_TIMEOUT",
                "CF Worker 读取邮件超时",
                data={"email": email_addr},
            )
        except requests.RequestException as exc:
            raise CloudflareTempMailProviderError(
                "UPSTREAM_SERVER_ERROR",
                f"CF Worker 网络错误: {exc}",
                data={"email": email_addr},
            )

        if not resp.ok:
            code = _map_cf_http_error(resp.status_code, resp.text)
            raise CloudflareTempMailProviderError(
                code,
                f"CF Worker 读取邮件失败 HTTP {resp.status_code}",
                data={"email": email_addr, "status_code": resp.status_code},
            )

        try:
            data = resp.json()
        except Exception:
            raise CloudflareTempMailProviderError(
                "UPSTREAM_BAD_PAYLOAD",
                "CF Worker 邮件列表返回非 JSON 响应",
                data={"email": email_addr},
            )

        cf_mails = data.get("mails") or data.get("results") or []
        if not isinstance(cf_mails, list):
            raise CloudflareTempMailProviderError(
                "UPSTREAM_BAD_PAYLOAD",
                "CF Worker 邮件列表字段格式错误",
                data={"email": email_addr},
            )

        results: list[dict[str, Any]] = []
        for cf_msg in cf_mails:
            try:
                results.append(self._normalize_cf_message(cf_msg))
            except Exception as exc:
                logger.warning(
                    "[cf_provider] failed to parse cf_msg id=%s err=%s",
                    cf_msg.get("id"),
                    exc,
                )
        return results

    def _normalize_cf_message(self, cf_msg: dict[str, Any]) -> dict[str, Any]:
        """将 CF Worker 原始邮件结构转换为平台标准结构。"""
        cf_id = cf_msg.get("id")
        # BUG-CF-05：加 cf_ 前缀避免与其他 provider 的 ID 冲突
        message_id = f"cf_{cf_id}" if cf_id is not None else ""

        created_at_str = str(cf_msg.get("created_at") or "")
        # BUG-CF-07：ISO 字符串 -> int timestamp
        timestamp = _iso_to_timestamp(created_at_str) if created_at_str else 0

        raw_mime = str(cf_msg.get("raw") or "")
        if raw_mime:
            parsed = _parse_mime_raw(raw_mime)
        else:
            parsed = {
                "subject": "",
                "from_address": "",
                "content": "",
                "html_content": "",
                "has_html": False,
            }

        # BUG-CF-01：from_address 优先从解析后的 MIME 中取，其次使用 CF 的 source 字段
        from_address = (
            parsed.get("from_address") or str(cf_msg.get("source") or "")
        ).strip()

        # subject 优先从 MIME 中取，其次从顶层字段取（部分 CF 版本可能有）
        subject = (parsed.get("subject") or str(cf_msg.get("subject") or "")).strip()

        # message_id 字段（RFC 822 Message-ID），用于去重
        cf_message_id_header = str(cf_msg.get("message_id") or "")

        return {
            "id": message_id,  # 供 save_temp_email_messages 的 msg.get("id") 使用
            "message_id": message_id,  # 冗余，方便直接读取
            "from_address": from_address,
            "source": from_address,  # 保留原始字段（兼容 save_temp_email_messages 的 source fallback）
            "subject": subject,
            "content": parsed.get("content", ""),
            "html_content": parsed.get("html_content", ""),
            "has_html": parsed.get("has_html", False),
            "timestamp": timestamp,
            "created_at": created_at_str,
            "raw_message_id": cf_message_id_header,
        }

    def get_message_detail(
        self, mailbox: dict[str, Any] | str, message_id: str
    ) -> dict[str, Any] | None:
        """
        CF Worker 无独立「获取单封邮件」接口，
        通过 list_messages 获取全部邮件后按 message_id 过滤。
        """
        messages = self.list_messages(mailbox)
        for msg in messages:
            if msg.get("id") == message_id or msg.get("message_id") == message_id:
                return msg
        return None

    def delete_message(self, mailbox: dict[str, Any] | str, message_id: str) -> bool:
        """
        调用 DELETE /api/mails/{id} 删除单封邮件。

        注意：正确路由为 /api/mails/{id}（不是 /mails/{id}，后者返回 405）。
        message_id 为平台格式 ``cf_<int>``，需还原为 CF 整数 ID。
        """
        jwt = self._get_jwt(mailbox) if isinstance(mailbox, dict) else ""
        if not jwt:
            logger.warning(
                "[cf_provider] delete_message: no jwt for %s",
                self._coerce_email(mailbox),
            )
            return False

        # 还原 CF 整数 ID
        cf_id: str = message_id
        if message_id.startswith("cf_"):
            cf_id = message_id[3:]

        base_url = self._base_url()
        try:
            resp = requests.delete(
                f"{base_url}/api/mails/{cf_id}",
                headers=self._user_headers(jwt),
                timeout=_CF_REQUEST_TIMEOUT,
            )
            return resp.ok
        except requests.RequestException as exc:
            logger.warning(
                "[cf_provider] delete_message failed id=%s err=%s", message_id, exc
            )
            return False

    def clear_messages(self, mailbox: dict[str, Any] | str) -> bool:
        """调用 DELETE /admin/clear_inbox/{addr_id} 清空邮箱所有邮件（Admin 接口）。

        注意：用户侧没有 clear_messages 路由，需用 Admin 接口 /admin/clear_inbox/{id}，
        id 为 meta["provider_mailbox_id"]（数字 address_id）。
        """
        address_id = ""
        if isinstance(mailbox, dict):
            meta_raw = mailbox.get("meta") or {}
            if isinstance(meta_raw, str):
                try:
                    meta_raw = json.loads(meta_raw)
                except Exception:
                    meta_raw = {}
            address_id = str(meta_raw.get("provider_mailbox_id") or "").strip()

        if not address_id:
            logger.warning(
                "[cf_provider] clear_messages: no address_id for %s",
                self._coerce_email(mailbox),
            )
            return False

        base_url = self._base_url()
        try:
            resp = requests.delete(
                f"{base_url}/admin/clear_inbox/{address_id}",
                headers=self._admin_headers(),
                timeout=_CF_REQUEST_TIMEOUT,
            )
            return resp.ok
        except requests.RequestException as exc:
            logger.warning("[cf_provider] clear_messages failed err=%s", exc)
            return False
