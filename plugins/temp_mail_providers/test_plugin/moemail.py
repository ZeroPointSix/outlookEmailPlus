from __future__ import annotations

import json
import secrets
import string
from datetime import datetime
from typing import Any

import requests

from outlook_web.repositories import settings as settings_repo
from outlook_web.services.temp_mail_provider_base import TempMailProviderBase, register_provider


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _error_code_by_status(status_code: int) -> str:
    if status_code in (401, 403):
        return "UNAUTHORIZED"
    if status_code == 404:
        return "TEMP_EMAIL_NOT_FOUND"
    if status_code == 409:
        return "TEMP_EMAIL_ALREADY_EXISTS"
    if status_code == 429:
        return "UPSTREAM_RATE_LIMITED"
    if status_code >= 500:
        return "UPSTREAM_SERVER_ERROR"
    return "UPSTREAM_BAD_PAYLOAD"


def _parse_domains_text(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    # 兼容逗号/换行输入
    normalized = text.replace("\r", "").replace(",", "\n")
    seen: set[str] = set()
    domains: list[str] = []
    for item in normalized.split("\n"):
        domain = item.strip()
        if not domain or domain in seen:
            continue
        seen.add(domain)
        domains.append(domain)
    return domains


def _normalize_timestamp(raw_value: Any) -> int:
    if raw_value is None:
        return 0

    if isinstance(raw_value, (int, float)):
        ts = int(raw_value)
        # 兼容毫秒时间戳
        return ts // 1000 if ts > 1_000_000_000_000 else ts

    text = str(raw_value).strip()
    if not text:
        return 0

    # 先尝试数字字符串
    try:
        as_int = int(float(text))
        return as_int // 1000 if as_int > 1_000_000_000_000 else as_int
    except ValueError:
        pass

    # 再尝试 ISO 时间
    try:
        clean = text.replace("Z", "+00:00")
        if "." in clean and "+" in clean:
            clean = clean[: clean.index(".")] + clean[clean.index("+") :]
        return int(datetime.fromisoformat(clean).timestamp())
    except (ValueError, TypeError):
        return 0


@register_provider
class MoemailTempMailProvider(TempMailProviderBase):
    provider_name = "moemail"
    provider_label = "Moemail"
    provider_version = "1.0.0"
    provider_author = "OutlookMail Plus"
    config_schema = {
        "fields": [
            {
                "key": "base_url",
                "label": "Moemail Base URL",
                "type": "url",
                "required": True,
                "placeholder": "https://moemail.example.com",
                "default": "",
                "description": "Moemail 服务地址（不含末尾斜杠）",
            },
            {
                "key": "api_key",
                "label": "Moemail API Key",
                "type": "password",
                "required": True,
                "placeholder": "请输入 API Key",
                "default": "",
            },
            {
                "key": "domains",
                "label": "域名白名单",
                "type": "textarea",
                "required": False,
                "placeholder": "moemail.app\nexample.com",
                "default": "",
                "description": "可选：每行一个域名；留空时自动从 /api/config 拉取",
            },
            {
                "key": "default_domain",
                "label": "默认域名",
                "type": "text",
                "required": False,
                "placeholder": "moemail.app",
                "default": "",
            },
            {
                "key": "default_expiry_ms",
                "label": "默认有效期(ms)",
                "type": "number",
                "required": False,
                "default": 3600000,
                "description": "创建邮箱时默认传给 Moemail 的 expiryTime，默认 1 小时",
            },
            {
                "key": "request_timeout",
                "label": "请求超时(秒)",
                "type": "number",
                "required": False,
                "default": 30,
            },
        ]
    }

    def __init__(self, *, provider_name: str | None = None):
        self.provider_name = provider_name or "moemail"
        prefix = f"plugin.{self.provider_name}"
        self._base_url = settings_repo.get_setting(f"{prefix}.base_url", "").strip().rstrip("/")
        self._api_key = settings_repo.get_setting(f"{prefix}.api_key", "").strip()
        self._domains_text = settings_repo.get_setting(f"{prefix}.domains", "")
        self._default_domain = settings_repo.get_setting(f"{prefix}.default_domain", "").strip()
        self._default_expiry_ms = _safe_int(settings_repo.get_setting(f"{prefix}.default_expiry_ms", "3600000"), 3600000)
        self._request_timeout = max(3, _safe_int(settings_repo.get_setting(f"{prefix}.request_timeout", "30"), 30))

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        return headers

    def _extract_error_message(self, resp: requests.Response) -> str:
        try:
            payload = resp.json()
            if isinstance(payload, dict):
                message = str(payload.get("error") or payload.get("message") or "").strip()
                if message:
                    return message
        except Exception:
            pass
        return str(resp.text or "").strip() or f"HTTP {resp.status_code}"

    def _fetch_domains_from_remote(self) -> list[str]:
        if not self._base_url:
            raise RuntimeError("Moemail base_url 未配置")

        try:
            resp = requests.get(
                f"{self._base_url}/api/config",
                headers=self._headers(),
                timeout=self._request_timeout,
            )
        except requests.Timeout as exc:
            raise RuntimeError("Moemail 获取域名超时") from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Moemail 获取域名失败: {exc}") from exc

        if not resp.ok:
            raise RuntimeError(f"Moemail 获取域名失败: {self._extract_error_message(resp)}")

        try:
            data = resp.json()
        except Exception as exc:
            raise RuntimeError("Moemail /api/config 返回非 JSON") from exc

        domain_value = None
        if isinstance(data, dict):
            domain_value = data.get("emailDomains") or data.get("email_domains") or data.get("domains")

        if isinstance(domain_value, list):
            return [str(item).strip() for item in domain_value if str(item).strip()]

        return _parse_domains_text(str(domain_value or ""))

    def _resolve_domain(self, requested_domain: str | None = None) -> str:
        given = str(requested_domain or "").strip()
        if given:
            return given
        if self._default_domain:
            return self._default_domain

        options = self.get_options()
        domains = options.get("domains") or []
        for item in domains:
            if item.get("is_default") and item.get("enabled"):
                return str(item.get("name") or "").strip()
        for item in domains:
            if item.get("enabled"):
                return str(item.get("name") or "").strip()
        return ""

    def _extract_mailbox_id(self, mailbox: dict[str, Any] | str) -> str:
        if isinstance(mailbox, dict):
            meta = mailbox.get("meta") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            for key in ("provider_mailbox_id", "mailbox_id", "email_id", "id"):
                value = str((meta or {}).get(key) or mailbox.get(key) or "").strip()
                if value:
                    return value
        return ""

    def _to_raw_message_id(self, message_id: str) -> str:
        text = str(message_id or "").strip()
        if text.startswith("moemail_"):
            return text[8:]
        return text

    def _normalize_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        raw_id = str(message.get("id") or message.get("message_id") or "").strip()
        if not raw_id:
            return None

        normalized_id = f"moemail_{raw_id}"
        content = str(message.get("content") or message.get("text") or message.get("body") or "")
        html_content = str(message.get("html") or message.get("html_content") or message.get("body_html") or "")
        from_address = str(message.get("from_address") or message.get("from") or message.get("sender") or "").strip()

        timestamp = _normalize_timestamp(message.get("received_at") or message.get("sent_at") or message.get("timestamp"))

        return {
            "id": normalized_id,
            "message_id": normalized_id,
            "from_address": from_address,
            "subject": str(message.get("subject") or ""),
            "content": content,
            "html_content": html_content,
            "has_html": bool(html_content),
            "timestamp": timestamp,
        }

    def get_options(self) -> dict[str, Any]:
        domains = _parse_domains_text(self._domains_text)
        if not domains:
            domains = self._fetch_domains_from_remote()
        if not domains:
            raise RuntimeError("Moemail 未返回可用域名")

        default_domain = self._default_domain if self._default_domain in domains else domains[0]
        return {
            "domain_strategy": "auto_or_manual",
            "default_mode": "auto",
            "domains": [
                {
                    "name": domain,
                    "enabled": True,
                    "is_default": domain == default_domain,
                }
                for domain in domains
            ],
            "prefix_rules": {
                "min_length": 1,
                "max_length": 64,
                "pattern": r"^[a-z0-9][a-z0-9._-]*$",
            },
            "provider": self.provider_name,
            "provider_name": self.provider_name,
            "provider_label": self.provider_label,
        }

    def create_mailbox(self, *, prefix: str | None = None, domain: str | None = None) -> dict[str, Any]:
        if not self._base_url:
            return {
                "success": False,
                "error": "Moemail base_url 未配置",
                "error_code": "TEMP_MAIL_PROVIDER_NOT_CONFIGURED",
            }
        if not self._api_key:
            return {
                "success": False,
                "error": "Moemail api_key 未配置",
                "error_code": "TEMP_MAIL_PROVIDER_NOT_CONFIGURED",
            }

        target_domain = self._resolve_domain(domain)
        if not target_domain:
            return {
                "success": False,
                "error": "Moemail 无可用域名",
                "error_code": "TEMP_MAIL_PROVIDER_NOT_CONFIGURED",
            }

        local_name = str(prefix or "").strip()
        if not local_name:
            alphabet = string.ascii_lowercase + string.digits
            local_name = "".join(secrets.choice(alphabet) for _ in range(8))

        payload = {
            "name": local_name,
            "domain": target_domain,
            "expiryTime": self._default_expiry_ms,
        }

        try:
            resp = requests.post(
                f"{self._base_url}/api/emails/generate",
                headers=self._headers(),
                json=payload,
                timeout=self._request_timeout,
            )
        except requests.Timeout:
            return {
                "success": False,
                "error": "Moemail 创建邮箱超时",
                "error_code": "UPSTREAM_TIMEOUT",
            }
        except requests.RequestException as exc:
            return {
                "success": False,
                "error": f"Moemail 创建邮箱失败: {exc}",
                "error_code": "UPSTREAM_SERVER_ERROR",
            }

        if not resp.ok:
            return {
                "success": False,
                "error": self._extract_error_message(resp),
                "error_code": _error_code_by_status(resp.status_code),
            }

        try:
            data = resp.json()
        except Exception:
            return {
                "success": False,
                "error": "Moemail 返回非 JSON",
                "error_code": "UPSTREAM_BAD_PAYLOAD",
            }

        if not isinstance(data, dict):
            return {
                "success": False,
                "error": "Moemail 返回结构异常",
                "error_code": "UPSTREAM_BAD_PAYLOAD",
            }

        email_addr = str(data.get("email") or data.get("address") or "").strip()
        mailbox_id = str(data.get("id") or data.get("email_id") or "").strip()
        if not email_addr:
            return {
                "success": False,
                "error": "Moemail 未返回 email",
                "error_code": "UPSTREAM_BAD_PAYLOAD",
            }

        return {
            "success": True,
            "email": email_addr,
            "meta": {
                "provider_name": self.provider_name,
                "provider_mailbox_id": mailbox_id,
                "provider_capabilities": {
                    "delete_mailbox": True,
                    "delete_message": True,
                    "clear_messages": True,
                },
            },
        }

    def delete_mailbox(self, mailbox: dict[str, Any]) -> bool:
        mailbox_id = self._extract_mailbox_id(mailbox)
        if not mailbox_id or not self._base_url:
            return False

        try:
            resp = requests.delete(
                f"{self._base_url}/api/emails/{mailbox_id}",
                headers=self._headers(),
                timeout=self._request_timeout,
            )
            return bool(resp.ok)
        except requests.RequestException:
            return False

    def list_messages(self, mailbox: dict[str, Any]) -> list[dict[str, Any]] | None:
        mailbox_id = self._extract_mailbox_id(mailbox)
        if not mailbox_id:
            return []

        try:
            resp = requests.get(
                f"{self._base_url}/api/emails/{mailbox_id}",
                headers=self._headers(),
                timeout=self._request_timeout,
            )
        except requests.Timeout as exc:
            raise RuntimeError("Moemail 拉取邮件列表超时") from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Moemail 拉取邮件列表失败: {exc}") from exc

        if not resp.ok:
            raise RuntimeError(f"Moemail 拉取邮件列表失败: {self._extract_error_message(resp)}")

        try:
            data = resp.json()
        except Exception as exc:
            raise RuntimeError("Moemail 邮件列表返回非 JSON") from exc

        raw_messages = []
        if isinstance(data, dict):
            raw_messages = data.get("messages") or []
        if not isinstance(raw_messages, list):
            raise RuntimeError("Moemail 邮件列表返回结构异常")

        normalized: list[dict[str, Any]] = []
        for item in raw_messages:
            if not isinstance(item, dict):
                continue
            row = self._normalize_message(item)
            if row is not None:
                normalized.append(row)
        return normalized

    def get_message_detail(self, mailbox: dict[str, Any], message_id: str) -> dict[str, Any] | None:
        mailbox_id = self._extract_mailbox_id(mailbox)
        if not mailbox_id:
            return None

        raw_message_id = self._to_raw_message_id(message_id)
        if not raw_message_id:
            return None

        try:
            resp = requests.get(
                f"{self._base_url}/api/emails/{mailbox_id}/{raw_message_id}",
                headers=self._headers(),
                timeout=self._request_timeout,
            )

            if resp.ok:
                payload = resp.json()
                if isinstance(payload, dict):
                    message = payload.get("message") or payload.get("data") or payload
                    if isinstance(message, dict):
                        normalized = self._normalize_message(message)
                        if normalized is not None:
                            return normalized
            elif resp.status_code not in (404, 405):
                # 404/405 走 fallback，其它错误直接返回空
                return None
        except requests.RequestException:
            # 网络异常走 fallback
            pass
        except Exception:
            # 非 JSON 走 fallback
            pass

        # detail 接口不可用时 fallback 到 list_messages 过滤
        messages = self.list_messages(mailbox) or []
        for item in messages:
            if item.get("id") == message_id or item.get("message_id") == message_id:
                return item
        return None

    def delete_message(self, mailbox: dict[str, Any], message_id: str) -> bool:
        mailbox_id = self._extract_mailbox_id(mailbox)
        raw_message_id = self._to_raw_message_id(message_id)
        if not mailbox_id or not raw_message_id:
            return False

        try:
            resp = requests.delete(
                f"{self._base_url}/api/emails/{mailbox_id}/{raw_message_id}",
                headers=self._headers(),
                timeout=self._request_timeout,
            )
            return bool(resp.ok)
        except requests.RequestException:
            return False

    def clear_messages(self, mailbox: dict[str, Any]) -> bool:
        try:
            messages = self.list_messages(mailbox) or []
        except Exception:
            return False

        for item in messages:
            msg_id = str(item.get("id") or item.get("message_id") or "").strip()
            if not msg_id:
                continue
            if not self.delete_message(mailbox, msg_id):
                return False
        return True
