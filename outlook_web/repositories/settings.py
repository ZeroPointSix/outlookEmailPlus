from __future__ import annotations

import json
from typing import Any, Dict

from outlook_web import config
from outlook_web.db import get_db
from outlook_web.security.crypto import decrypt_data

DEFAULT_TEMP_MAIL_PROVIDER = "custom_domain_temp_mail"
LEGACY_TEMP_MAIL_PROVIDER = "legacy_bridge"
CLOUDFLARE_TEMP_MAIL_PROVIDER = "cloudflare_temp_mail"
LEGACY_TEMP_MAIL_PROVIDER_NAMES = {"legacy_bridge", "legacy_gptmail", "gptmail"}
SUPPORTED_TEMP_MAIL_PROVIDERS = {
    DEFAULT_TEMP_MAIL_PROVIDER,
    LEGACY_TEMP_MAIL_PROVIDER,
    CLOUDFLARE_TEMP_MAIL_PROVIDER,
}


def get_setting(key: str, default: str = "") -> str:
    """获取设置值"""
    db = get_db()
    cursor = db.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str, *, commit: bool = True) -> bool:
    """设置值"""
    db = get_db()
    try:
        db.execute(
            """
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (key, value),
        )
        if commit:
            db.commit()
        return True
    except Exception:
        return False


def get_all_settings() -> Dict[str, str]:
    """获取所有设置"""
    db = get_db()
    cursor = db.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    return {row["key"]: row["value"] for row in rows}


def get_login_password() -> str:
    """获取登录密码（优先从数据库读取）"""
    password = get_setting("login_password")
    return password if password else config.get_login_password_default()


def get_legacy_gptmail_api_key() -> str:
    """兼容读取 legacy gptmail_api_key。"""
    return get_setting("gptmail_api_key")


def get_temp_mail_api_key() -> str:
    """获取正式临时邮箱 API Key，并兼容 legacy gptmail_api_key 回退。"""
    api_key = get_setting("temp_mail_api_key")
    if api_key:
        return api_key
    legacy_api_key = get_legacy_gptmail_api_key()
    if legacy_api_key:
        return legacy_api_key
    return config.get_temp_mail_api_key_default()


def get_gptmail_api_key() -> str:
    """legacy bridge 兼容入口。"""
    return get_temp_mail_api_key()


def normalize_temp_mail_provider_name(value: str | None) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return DEFAULT_TEMP_MAIL_PROVIDER
    if normalized.lower() in LEGACY_TEMP_MAIL_PROVIDER_NAMES:
        return LEGACY_TEMP_MAIL_PROVIDER
    return normalized


def get_supported_temp_mail_provider_names() -> set[str]:
    return set(SUPPORTED_TEMP_MAIL_PROVIDERS)


def is_supported_temp_mail_provider_name(value: str | None) -> bool:
    return normalize_temp_mail_provider_name(value) in SUPPORTED_TEMP_MAIL_PROVIDERS


def validate_temp_mail_provider_name(value: str | None) -> str:
    normalized = normalize_temp_mail_provider_name(value)
    if normalized not in SUPPORTED_TEMP_MAIL_PROVIDERS:
        raise ValueError("临时邮箱 Provider 配置无效")
    return normalized


def get_temp_mail_provider() -> str:
    return normalize_temp_mail_provider_name(get_setting("temp_mail_provider", DEFAULT_TEMP_MAIL_PROVIDER))


def get_temp_mail_runtime_provider_name(provider_name: str | None = None) -> str:
    if provider_name is not None:
        return normalize_temp_mail_provider_name(provider_name)
    return get_temp_mail_provider()


def get_temp_mail_api_base_url() -> str:
    base_url = get_setting("temp_mail_api_base_url")
    return base_url if base_url else config.get_temp_mail_base_url()


def get_cf_worker_base_url() -> str:
    """获取 Cloudflare Temp Email Worker 独立部署地址（与 GPTMail 设置完全隔离）。"""
    return get_setting("cf_worker_base_url", "").strip()


def get_cf_worker_admin_key() -> str:
    """获取 Cloudflare Worker ADMIN_PASSWORDS 中的密码值（自动解密 enc: 格式）。"""
    value = get_setting("cf_worker_admin_key", "").strip()
    if not value:
        return ""
    try:
        return decrypt_data(value)
    except Exception:
        # 兼容历史明文值：解密失败时直接返回明文
        return value


def get_temp_mail_domains() -> list[dict[str, Any]]:
    raw = get_setting("temp_mail_domains", "[]")
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return value if isinstance(value, list) else []


def get_temp_mail_default_domain() -> str:
    return get_setting("temp_mail_default_domain", "").strip()


def get_temp_mail_prefix_rules() -> dict[str, Any]:
    raw = get_setting("temp_mail_prefix_rules", "{}")
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def get_cf_worker_domains() -> list[dict[str, Any]]:
    """获取 CF Worker 独立域名列表（v0.3 Tab 重构）。"""
    raw = get_setting("cf_worker_domains", "[]")
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return value if isinstance(value, list) else []


def get_cf_worker_default_domain() -> str:
    """获取 CF Worker 默认域名（v0.3 Tab 重构）。"""
    return get_setting("cf_worker_default_domain", "").strip()


def get_cf_worker_prefix_rules() -> dict[str, Any]:
    """获取 CF Worker 前缀规则（v0.3 Tab 重构）。"""
    _default_rules: dict[str, Any] = {
        "min_length": 1,
        "max_length": 32,
        "pattern": "^[a-z0-9][a-z0-9._-]*$",
    }
    raw = get_setting("cf_worker_prefix_rules", "{}")
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return _default_rules
    if not isinstance(value, dict) or not value:
        return _default_rules
    return value


def get_external_api_key() -> str:
    """
    获取对外开放 API Key。

    - 若数据库为空，返回空字符串
    - 若为 enc: 加密格式，自动解密
    - 若为历史明文（兼容），直接返回明文
    - 解密失败时返回空字符串（避免影响外部接口鉴权逻辑）
    """
    value = get_setting("external_api_key") or ""
    if not value:
        return ""
    try:
        return decrypt_data(value)
    except Exception:
        return ""


def get_external_api_key_masked(head: int = 4, tail: int = 4) -> str:
    """对外 API Key 脱敏展示：前 N 位 + 若干 * + 后 N 位。"""
    key = get_external_api_key()
    if not key:
        return ""
    safe_value = str(key)
    if len(safe_value) <= head + tail:
        return "*" * len(safe_value)
    return safe_value[:head] + ("*" * (len(safe_value) - head - tail)) + safe_value[-tail:]


# ── P1：公网模式安全配置 ──────────────────────────────


def get_external_api_public_mode() -> bool:
    """公网模式是否开启（默认关闭，保持 P0 受控私有行为）。"""
    return get_setting("external_api_public_mode", "false").lower() == "true"


def get_external_api_ip_whitelist() -> list:
    """IP 白名单列表（JSON 数组，支持 CIDR 如 '192.168.1.0/24'）。"""
    import json

    raw = get_setting("external_api_ip_whitelist", "[]")
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def get_external_api_rate_limit() -> int:
    """每分钟每 IP 最大请求数（默认 60）。"""
    try:
        val = int(get_setting("external_api_rate_limit_per_minute", "60"))
        return max(1, val)
    except (ValueError, TypeError):
        return 60


def get_external_api_disable_wait_message() -> bool:
    """是否禁用 wait-message 端点（默认不禁用）。"""
    return get_setting("external_api_disable_wait_message", "false").lower() == "true"


def get_external_api_disable_raw_content() -> bool:
    """是否禁用 raw 端点（默认不禁用）。"""
    return get_setting("external_api_disable_raw_content", "false").lower() == "true"


def get_pool_external_enabled() -> bool:
    return get_setting("pool_external_enabled", "false").lower() == "true"


def get_external_api_disable_pool_claim_random() -> bool:
    return get_setting("external_api_disable_pool_claim_random", "false").lower() == "true"


def get_external_api_disable_pool_claim_release() -> bool:
    return get_setting("external_api_disable_pool_claim_release", "false").lower() == "true"


def get_external_api_disable_pool_claim_complete() -> bool:
    return get_setting("external_api_disable_pool_claim_complete", "false").lower() == "true"


def get_external_api_disable_pool_stats() -> bool:
    return get_setting("external_api_disable_pool_stats", "false").lower() == "true"


def get_ui_layout_v2() -> dict:
    """读取前端布局状态"""
    import json

    raw = get_setting("ui_layout_v2", "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def set_ui_layout_v2(layout: dict) -> None:
    """写入前端布局状态"""
    import json

    set_setting("ui_layout_v2", json.dumps(layout, ensure_ascii=False))


# ── Telegram 代理配置 ──────────────────────────────


def get_telegram_proxy_url() -> str:
    """获取 Telegram 推送使用的系统级代理 URL（明文存储，如 socks5://host:port）。"""
    return get_setting("telegram_proxy_url", "").strip()


def set_telegram_proxy_url(url: str) -> bool:
    """保存 Telegram 代理 URL。"""
    return set_setting("telegram_proxy_url", url.strip())


def get_telegram_bot_token() -> str:
    """获取 Telegram Bot Token（支持 enc: 加密格式）。"""
    from outlook_web.security.crypto import decrypt_data, is_encrypted

    value = get_setting("telegram_bot_token", "").strip()
    if not value:
        return ""
    if is_encrypted(value):
        try:
            return decrypt_data(value)
        except Exception:
            return ""
    return value
