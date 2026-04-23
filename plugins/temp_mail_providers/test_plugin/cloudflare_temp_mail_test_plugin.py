from __future__ import annotations

import email as _email_lib
import email.policy
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


def _status_error_code(status_code: int) -> str:
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


def _normalize_timestamp(raw_value: Any) -> int:
    if raw_value is None:
        return 0

    if isinstance(raw_value, (int, float)):
        ts = int(raw_value)
        return ts // 1000 if ts > 1_000_000_000_000 else ts

    text = str(raw_value or "").strip()
    if not text:
        return 0

    try:
        as_int = int(float(text))
        return as_int // 1000 if as_int > 1_000_000_000_000 else as_int
    except ValueError:
        pass

    try:
        clean = text.replace("Z", "+00:00")
        if "." in clean and "+" in clean:
            clean = clean[: clean.index(".")] + clean[clean.index("+") :]
        return int(datetime.fromisoformat(clean).timestamp())
    except (ValueError, TypeError):
        return 0


def _parse_mime_raw(raw_mime: str) -> dict[str, Any]:
    try:
        msg = _email_lib.message_from_string(raw_mime, policy=_email_lib.policy.compat32)
    except Exception:
        return {
            "subject": "",
            "from_address": "",
            "content": raw_mime,
            "html_content": "",
            "has_html": False,
        }

    subject = str(msg.get("Subject", "") or "")
    from_address = str(msg.get("From", "") or "").strip()

    plain_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            cdisp = str(part.get("Content-Disposition") or "")
            if "attachment" in cdisp:
                continue
            content_type = part.get_content_type()
            charset = part.get_content_charset() or "utf-8"
            try:
                payload = part.get_payload(decode=True)
                text = payload.decode(charset, errors="replace") if payload else ""
            except Exception:
                text = ""
            if content_type == "text/plain":
                plain_parts.append(text)
            elif content_type == "text/html":
                html_parts.append(text)
    else:
        content_type = msg.get_content_type()
        charset = msg.get_content_charset() or "utf-8"
        try:
            payload = msg.get_payload(decode=True)
            text = payload.decode(charset, errors="replace") if payload else ""
        except Exception:
            text = str(msg.get_payload() or "")
        if content_type == "text/html":
            html_parts.append(text)
        else:
            plain_parts.append(text)

    content = "\n".join(part for part in plain_parts if part).strip()
    html_content = "\n".join(part for part in html_parts if part).strip()
    return {
        "subject": subject,
        "from_address": from_address,
        "content": content,
        "html_content": html_content,
        "has_html": bool(html_content),
    }


def _parse_domains_text(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
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


@register_provider
class CloudflareTempMailTestPluginProvider(TempMailProviderBase):
    provider_name = "cloudflare_temp_mail_test_plugin"
    provider_label = "Cloudflare Temp Email (Test Plugin)"
    provider_version = "1.0.0"
    provider_author = "OutlookMail Plus"
    config_schema = {
        "fields": [
            {
                "key": "base_url",
                "label": "CF Temp Mail Base URL",
                "type": "url",
                "required": True,
                "placeholder": "https://mail.example.workers.dev",
                "default": "",
            },
            {
                "key": "admin_key",
                "label": "Admin Key",
                "type": "password",
                "required": True,
                "placeholder": "x-admin-auth 值",
                "default": "",
            },
            {
                "key": "custom_auth",
                "label": "x-custom-auth（可选）",
                "type": "password",
                "required": False,
                "placeholder": "站点访问密码（如果启用）",
                "default": "",
            },
            {
                "key": "domains",
                "label": "域名白名单",
                "type": "textarea",
                "required": False,
                "placeholder": "example.com\nmail.example.com",
                "default": "",
                "description": "可选；留空时从 /open_api/settings 自动拉取",
            },
            {
                "key": "default_domain",
                "label": "默认域名",
                "type": "text",
                "required": False,
                "default": "",
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
        self.provider_name = provider_name or self.provider_name
        prefix = f"plugin.{self.provider_name}"
        self._base_url = settings_repo.get_setting(f"{prefix}.base_url", "").strip().rstrip("/")
        self._admin_key = settings_repo.get_setting(f"{prefix}.admin_key", "").strip()
        self._custom_auth = settings_repo.get_setting(f"{prefix}.custom_auth", "").strip()
        self._domains_text = settings_repo.get_setting(f"{prefix}.domains", "")
        self._default_domain = settings_repo.get_setting(f"{prefix}.default_domain", "").strip()
        self._request_timeout = max(3, _safe_int(settings_repo.get_setting(f"{prefix}.request_timeout", "30"), 30))

    def _headers(self, *, admin: bool = False, jwt: str = "") -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._custom_auth:
            headers["x-custom-auth"] = self._custom_auth
        if admin and self._admin_key:
            headers["x-admin-auth"] = self._admin_key
        if jwt:
            headers["Authorization"] = f"Bearer {jwt}"
        return headers

    def _extract_error(self, resp: requests.Response) -> str:
        try:
            payload = resp.json()
            if isinstance(payload, dict):
                message = str(payload.get("error") or payload.get("message") or "").strip()
                if message:
                    return message
        except Exception:
            pass
        return str(resp.text or "").strip() or f"HTTP {resp.status_code}"

    def _extract_jwt(self, mailbox: dict[str, Any] | str) -> str:
        if isinstance(mailbox, dict):
            meta = mailbox.get("meta") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            return str((meta or {}).get("provider_jwt") or mailbox.get("provider_jwt") or "").strip()
        return ""

    def _extract_address_id(self, mailbox: dict[str, Any] | str) -> str:
        if isinstance(mailbox, dict):
            meta = mailbox.get("meta") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            for key in ("provider_mailbox_id", "address_id", "id"):
                value = str((meta or {}).get(key) or mailbox.get(key) or "").strip()
                if value:
                    return value
        return ""

    def _to_raw_message_id(self, message_id: str) -> str:
        text = str(message_id or "").strip()
        if text.startswith("cf_test_"):
            return text[8:]
        return text

    def _normalize_message(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        raw_id = str(payload.get("id") or payload.get("message_id") or "").strip()
        if not raw_id:
            return None

        content = str(payload.get("content") or payload.get("body") or payload.get("text") or "")
        html_content = str(payload.get("html") or payload.get("html_content") or payload.get("body_html") or "")
        from_address = str(
            payload.get("from_address") or payload.get("from") or payload.get("sender") or payload.get("source") or ""
        ).strip()
        subject = str(payload.get("subject") or "")

        raw_mime = str(payload.get("raw") or "")
        if raw_mime and (not subject or not from_address or (not content and not html_content)):
            parsed = _parse_mime_raw(raw_mime)
            subject = subject or parsed.get("subject", "")
            from_address = from_address or parsed.get("from_address", "")
            content = content or parsed.get("content", "")
            html_content = html_content or parsed.get("html_content", "")

        return {
            "id": f"cf_test_{raw_id}",
            "message_id": f"cf_test_{raw_id}",
            "from_address": from_address,
            "subject": subject,
            "content": content,
            "html_content": html_content,
            "has_html": bool(html_content),
            "timestamp": _normalize_timestamp(
                payload.get("timestamp") or payload.get("created_at") or payload.get("received_at")
            ),
        }

    def _fetch_domains_from_remote(self) -> tuple[list[str], str]:
        if not self._base_url:
            raise RuntimeError("CF Temp Mail base_url 未配置")
        try:
            resp = requests.get(
                f"{self._base_url}/open_api/settings",
                headers=self._headers(),
                timeout=self._request_timeout,
            )
        except requests.Timeout as exc:
            raise RuntimeError("CF Temp Mail 拉取域名超时") from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"CF Temp Mail 拉取域名失败: {exc}") from exc

        if not resp.ok:
            raise RuntimeError(f"CF Temp Mail 拉取域名失败: {self._extract_error(resp)}")

        try:
            data = resp.json()
        except Exception as exc:
            raise RuntimeError("CF Temp Mail /open_api/settings 返回非 JSON") from exc

        if not isinstance(data, dict):
            raise RuntimeError("CF Temp Mail /open_api/settings 返回结构异常")

        domains_raw = data.get("domains") or []
        domains = [str(item).strip() for item in domains_raw if str(item).strip()]
        default_domains = data.get("defaultDomains") or []
        default_domain = str(default_domains[0]).strip() if isinstance(default_domains, list) and default_domains else ""
        if not default_domain and domains:
            default_domain = domains[0]
        return domains, default_domain

    def get_options(self) -> dict[str, Any]:
        domains = _parse_domains_text(self._domains_text)
        default_domain = self._default_domain
        if not domains:
            domains, remote_default = self._fetch_domains_from_remote()
            default_domain = default_domain or remote_default

        if not domains:
            raise RuntimeError("CF Temp Mail 未返回可用域名")

        if not default_domain or default_domain not in domains:
            default_domain = domains[0]

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
                "max_length": 32,
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
                "error": "CF Temp Mail base_url 未配置",
                "error_code": "TEMP_MAIL_PROVIDER_NOT_CONFIGURED",
            }
        if not self._admin_key:
            return {
                "success": False,
                "error": "CF Temp Mail admin_key 未配置",
                "error_code": "TEMP_MAIL_PROVIDER_NOT_CONFIGURED",
            }

        options = self.get_options()
        domains = options.get("domains") or []
        target_domain = str(domain or "").strip()
        if not target_domain:
            for item in domains:
                if item.get("enabled") and item.get("is_default"):
                    target_domain = str(item.get("name") or "").strip()
                    break
        if not target_domain and domains:
            target_domain = str(domains[0].get("name") or "").strip()
        if not target_domain:
            return {
                "success": False,
                "error": "CF Temp Mail 无可用域名",
                "error_code": "TEMP_MAIL_PROVIDER_NOT_CONFIGURED",
            }

        local_name = str(prefix or "").strip()
        if not local_name:
            alphabet = string.ascii_lowercase + string.digits
            local_name = "".join(secrets.choice(alphabet) for _ in range(8))

        payload = {
            "name": local_name,
            "domain": target_domain,
            "enablePrefix": False,
        }

        try:
            resp = requests.post(
                f"{self._base_url}/admin/new_address",
                headers=self._headers(admin=True),
                json=payload,
                timeout=self._request_timeout,
            )
        except requests.Timeout:
            return {
                "success": False,
                "error": "CF Temp Mail 创建邮箱超时",
                "error_code": "UPSTREAM_TIMEOUT",
            }
        except requests.RequestException as exc:
            return {
                "success": False,
                "error": f"CF Temp Mail 创建邮箱失败: {exc}",
                "error_code": "UPSTREAM_SERVER_ERROR",
            }

        if not resp.ok:
            return {
                "success": False,
                "error": self._extract_error(resp),
                "error_code": _status_error_code(resp.status_code),
            }

        try:
            data = resp.json()
        except Exception:
            return {
                "success": False,
                "error": "CF Temp Mail 返回非 JSON",
                "error_code": "UPSTREAM_BAD_PAYLOAD",
            }

        if not isinstance(data, dict):
            return {
                "success": False,
                "error": "CF Temp Mail 返回结构异常",
                "error_code": "UPSTREAM_BAD_PAYLOAD",
            }

        email_addr = str(data.get("address") or data.get("email") or "").strip()
        jwt = str(data.get("jwt") or "").strip()
        address_id = str(data.get("address_id") or data.get("id") or "").strip()
        if not email_addr:
            return {
                "success": False,
                "error": "CF Temp Mail 未返回邮箱地址",
                "error_code": "UPSTREAM_BAD_PAYLOAD",
            }

        return {
            "success": True,
            "email": email_addr,
            "meta": {
                "provider_name": self.provider_name,
                "provider_mailbox_id": address_id,
                "provider_jwt": jwt,
                "provider_capabilities": {
                    "delete_mailbox": True,
                    "delete_message": True,
                    "clear_messages": True,
                },
            },
        }

    def delete_mailbox(self, mailbox: dict[str, Any]) -> bool:
        if not self._base_url:
            return False

        address_id = self._extract_address_id(mailbox)
        if address_id and self._admin_key:
            try:
                resp = requests.delete(
                    f"{self._base_url}/admin/delete_address/{address_id}",
                    headers=self._headers(admin=True),
                    timeout=self._request_timeout,
                )
                if resp.ok:
                    return True
            except requests.RequestException:
                pass

        jwt = self._extract_jwt(mailbox)
        if not jwt:
            return False
        try:
            resp = requests.delete(
                f"{self._base_url}/api/delete_address",
                headers=self._headers(jwt=jwt),
                timeout=self._request_timeout,
            )
            return bool(resp.ok)
        except requests.RequestException:
            return False

    def list_messages(self, mailbox: dict[str, Any]) -> list[dict[str, Any]] | None:
        if not self._base_url:
            raise RuntimeError("CF Temp Mail base_url 未配置")

        jwt = self._extract_jwt(mailbox)
        if not jwt:
            raise RuntimeError("邮箱缺少 provider_jwt")

        try:
            resp = requests.get(
                f"{self._base_url}/api/mails",
                headers=self._headers(jwt=jwt),
                params={"limit": 100, "offset": 0},
                timeout=self._request_timeout,
            )
        except requests.Timeout as exc:
            raise RuntimeError("CF Temp Mail 拉取邮件超时") from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"CF Temp Mail 拉取邮件失败: {exc}") from exc

        if not resp.ok:
            raise RuntimeError(f"CF Temp Mail 拉取邮件失败: {self._extract_error(resp)}")

        try:
            data = resp.json()
        except Exception as exc:
            raise RuntimeError("CF Temp Mail 邮件列表返回非 JSON") from exc

        rows = []
        if isinstance(data, dict):
            rows = data.get("results") or data.get("mails") or []
        if not isinstance(rows, list):
            raise RuntimeError("CF Temp Mail 邮件列表返回结构异常")

        messages: list[dict[str, Any]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            normalized = self._normalize_message(item)
            if normalized is not None:
                messages.append(normalized)
        return messages

    def get_message_detail(self, mailbox: dict[str, Any], message_id: str) -> dict[str, Any] | None:
        if not self._base_url:
            return None

        jwt = self._extract_jwt(mailbox)
        raw_id = self._to_raw_message_id(message_id)
        if not jwt or not raw_id:
            return None

        try:
            resp = requests.get(
                f"{self._base_url}/api/mail/{raw_id}",
                headers=self._headers(jwt=jwt),
                timeout=self._request_timeout,
            )
            if resp.ok:
                payload = resp.json()
                if isinstance(payload, dict):
                    normalized = self._normalize_message(payload)
                    if normalized is not None:
                        return normalized
            elif resp.status_code not in (404, 405):
                return None
        except Exception:
            pass

        messages = self.list_messages(mailbox) or []
        for item in messages:
            if item.get("id") == message_id or item.get("message_id") == message_id:
                return item
        return None

    def delete_message(self, mailbox: dict[str, Any], message_id: str) -> bool:
        if not self._base_url:
            return False

        jwt = self._extract_jwt(mailbox)
        raw_id = self._to_raw_message_id(message_id)
        if not jwt or not raw_id:
            return False

        try:
            resp = requests.delete(
                f"{self._base_url}/api/mails/{raw_id}",
                headers=self._headers(jwt=jwt),
                timeout=self._request_timeout,
            )
            return bool(resp.ok)
        except requests.RequestException:
            return False

    def clear_messages(self, mailbox: dict[str, Any]) -> bool:
        if not self._base_url:
            return False

        jwt = self._extract_jwt(mailbox)
        if not jwt:
            return False

        try:
            resp = requests.delete(
                f"{self._base_url}/api/clear_inbox",
                headers=self._headers(jwt=jwt),
                timeout=self._request_timeout,
            )
            return bool(resp.ok)
        except requests.RequestException:
            return False
