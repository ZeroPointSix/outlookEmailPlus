from __future__ import annotations

import os


def _getenv(key: str, default: str | None = None) -> str | None:
    value = os.getenv(key)
    if value is None:
        return default
    value = value.strip()
    return value if value != "" else default


def require_secret_key() -> str:
    secret_key = _getenv("SECRET_KEY")
    if not secret_key:
        raise RuntimeError(
            "SECRET_KEY environment variable is required. "
            "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )
    return secret_key


def get_database_path() -> str:
    return _getenv("DATABASE_PATH", "data/outlook_accounts.db") or "data/outlook_accounts.db"


def get_login_password_default() -> str:
    return _getenv("LOGIN_PASSWORD", "admin123") or "admin123"


def get_gptmail_base_url() -> str:
    return _getenv("GPTMAIL_BASE_URL", "https://mail.chatgpt.org.uk") or "https://mail.chatgpt.org.uk"


def get_gptmail_api_key_default() -> str:
    return _getenv("GPTMAIL_API_KEY", "gpt-test") or "gpt-test"


def get_temp_mail_base_url() -> str:
    """正式临时邮箱上游地址；环境变量保持兼容旧 GPTMAIL_* 命名。"""
    return get_gptmail_base_url()


def get_temp_mail_api_key_default() -> str:
    """正式临时邮箱 API Key 默认值；环境变量保持兼容旧 GPTMAIL_* 命名。"""
    return get_gptmail_api_key_default()


def get_oauth_client_id() -> str:
    return _getenv("OAUTH_CLIENT_ID", "24d9a0ed-8787-4584-883c-2fd79308940a") or "24d9a0ed-8787-4584-883c-2fd79308940a"


def get_oauth_redirect_uri(default: str | None = None) -> str:
    fallback = default or "http://localhost:8080"
    return _getenv("OAUTH_REDIRECT_URI", fallback) or fallback


def env_true(key: str, default: bool) -> bool:
    """
    与旧实现保持一致：只有值为 'true'（忽略大小写）才视为 True；其它值均为 False。
    """
    value = _getenv(key, "true" if default else "false") or ("true" if default else "false")
    return value.lower() == "true"


def get_allow_login_password_change() -> bool:
    return env_true("ALLOW_LOGIN_PASSWORD_CHANGE", True)


def get_scheduler_autostart_default() -> bool:
    return env_true("SCHEDULER_AUTOSTART", True)


def get_trusted_proxies() -> list[str]:
    """
    获取受信任的代理 IP 列表。
    用于验证 X-Forwarded-For 头的来源是否可信。

    环境变量 TRUSTED_PROXIES 格式：逗号分隔的 CIDR 或 IP，如：
    - "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16" (内网代理)
    - "127.0.0.1" (本地代理)
    - "" (空表示不信任任何代理，直接使用 remote_addr)

    默认值：空字符串（安全默认 - 不信任任何代理）
    """
    proxies_str = _getenv("TRUSTED_PROXIES", "")
    if not proxies_str:
        return []
    return [p.strip() for p in proxies_str.split(",") if p.strip()]


def get_proxy_fix_enabled() -> bool:
    """
    是否启用 ProxyFix 中间件。

    只有在应用部署在反向代理后面，并且配置了 TRUSTED_PROXIES 时才应启用。
    默认：False（安全默认）
    """
    return env_true("PROXY_FIX_ENABLED", False)
