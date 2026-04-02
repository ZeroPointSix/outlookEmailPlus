from __future__ import annotations

from typing import Any, Dict, List, Optional

# 对齐：PRD-00005 / FD-00005 / TDD-00005 / PRD-00006 / FD-00006
# 职责：集中维护邮箱提供商元数据、邮箱域名归一化规则，以及 provider/domain 一致性校验。

MAIL_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "outlook": {
        "label": "Outlook",
        "imap_host": "outlook.live.com",
        "imap_port": 993,
        "account_type": "outlook",
        "note": "使用 OAuth2 认证（client_id + refresh_token）",
    },
    "gmail": {
        "label": "Gmail",
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "account_type": "imap",
        "note": "需开启 IMAP，并使用应用专用密码（非登录密码）",
    },
    "qq": {
        "label": "QQ 邮箱",
        "imap_host": "imap.qq.com",
        "imap_port": 993,
        "account_type": "imap",
        "note": "需开启 IMAP 服务，使用授权码（非 QQ 密码）",
    },
    "163": {
        "label": "163 邮箱",
        "imap_host": "imap.163.com",
        "imap_port": 993,
        "account_type": "imap",
        "note": "需开启 IMAP 服务，使用授权码",
    },
    "126": {
        "label": "126 邮箱",
        "imap_host": "imap.126.com",
        "imap_port": 993,
        "account_type": "imap",
        "note": "需开启 IMAP 服务，使用授权码",
    },
    "yahoo": {
        "label": "Yahoo 邮箱",
        "imap_host": "imap.mail.yahoo.com",
        "imap_port": 993,
        "account_type": "imap",
        "note": "需在账号安全设置中生成应用密码",
    },
    "aliyun": {
        "label": "阿里邮箱",
        "imap_host": "imap.aliyun.com",
        "imap_port": 993,
        "account_type": "imap",
        "note": "使用阿里邮箱登录密码",
    },
    "custom": {
        "label": "自定义 IMAP",
        "imap_host": "",
        "imap_port": 993,
        "account_type": "imap",
        "note": "请手动填写 IMAP 服务器地址和端口",
    },
}

DOMAIN_PROVIDER_MAP: Dict[str, str] = {
    "gmail.com": "gmail",
    "googlemail.com": "gmail",
    "qq.com": "qq",
    "foxmail.com": "qq",
    "163.com": "163",
    "126.com": "126",
    "yahoo.com": "yahoo",
    "yahoo.co.jp": "yahoo",
    "yahoo.co.uk": "yahoo",
    "aliyun.com": "aliyun",
    "alimail.com": "aliyun",
    "outlook.com": "outlook",
    "hotmail.com": "outlook",
    "live.com": "outlook",
    "live.cn": "outlook",
}

PROVIDER_GROUP_NAME: Dict[str, str] = {
    "outlook": "Outlook",
    "gmail": "Gmail",
    "qq": "QQ邮箱",
    "163": "163邮箱",
    "126": "126邮箱",
    "yahoo": "Yahoo",
    "aliyun": "阿里云邮箱",
    "custom": "自定义IMAP",
    "gptmail": "临时邮箱",
}

KNOWN_PROVIDER_KEYS: set[str] = set(MAIL_PROVIDERS.keys())

PROVIDER_FAMILY_DOMAINS: Dict[str, set[str]] = {}
for domain_name, provider_key in DOMAIN_PROVIDER_MAP.items():
    PROVIDER_FAMILY_DOMAINS.setdefault(provider_key, set()).add(domain_name)


def normalize_email_domain(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "@" in text:
        text = text.rsplit("@", 1)[-1]
    return text.strip().strip(".")


def extract_email_domain(email: str | None) -> str:
    text = str(email or "").strip().lower()
    if "@" not in text:
        return ""
    return normalize_email_domain(text.rsplit("@", 1)[-1])


def infer_provider_from_email(email: str | None) -> Optional[str]:
    domain = extract_email_domain(email)
    if not domain:
        return None
    return DOMAIN_PROVIDER_MAP.get(domain)


def infer_provider_from_domain(domain: str | None) -> Optional[str]:
    normalized = normalize_email_domain(domain)
    if not normalized:
        return None
    return DOMAIN_PROVIDER_MAP.get(normalized)


def provider_supports_email_domain(provider: str | None, email_domain: str | None) -> bool:
    provider_key = str(provider or "").strip().lower()
    normalized_domain = normalize_email_domain(email_domain)
    if not provider_key or not normalized_domain:
        return False
    inferred_provider = infer_provider_from_domain(normalized_domain)
    if inferred_provider is not None:
        return inferred_provider == provider_key
    return provider_key == "custom"


def get_provider_domains(provider: str | None) -> set[str]:
    provider_key = str(provider or "").strip().lower()
    return set(PROVIDER_FAMILY_DOMAINS.get(provider_key, set()))


PROVIDER_FOLDER_MAP: Dict[str, Dict[str, List[str]]] = {
    "gmail": {
        "inbox": ["INBOX"],
        "junkemail": ["[Gmail]/Spam", "[Gmail]/垃圾邮件"],
        "deleteditems": ["[Gmail]/Trash", "[Gmail]/已删除邮件"],
    },
    "qq": {
        "inbox": ["INBOX"],
        "junkemail": ["Junk", "&V4NXPpCuTvY-"],
        "deleteditems": ["Deleted Messages", "&XfJT0ZABkK5O9g-"],
    },
    "163": {
        "inbox": ["INBOX"],
        "junkemail": ["&V4NXPpCuTvY-"],
        "deleteditems": ["&XfJT0ZABkK5O9g-"],
    },
    "yahoo": {
        "inbox": ["INBOX"],
        "junkemail": ["Bulk Mail"],
        "deleteditems": ["Trash"],
    },
    "_default": {
        "inbox": ["INBOX"],
        "junkemail": ["Junk", "Junk Email", "Spam", "SPAM", "Bulk Mail"],
        "deleteditems": ["Trash", "Deleted", "Deleted Messages"],
    },
}


def get_imap_folder_candidates(provider: str, folder: str) -> List[str]:
    provider_key = (provider or "").strip() or "_default"
    folder_key = (folder or "").strip().lower() or "inbox"
    folder_map = PROVIDER_FOLDER_MAP.get(provider_key, PROVIDER_FOLDER_MAP["_default"])
    return folder_map.get(folder_key, PROVIDER_FOLDER_MAP["_default"].get(folder_key, ["INBOX"]))


def get_provider_list() -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = [
        {
            "key": "auto",
            "label": "🔍 智能识别（混合导入）",
            "account_type": "mixed",
            "note": "自动识别每行的账号类型，支持混合文件一键导入",
        }
    ]
    order = ["outlook", "gmail", "qq", "163", "126", "yahoo", "aliyun", "custom"]
    for key in order:
        if key not in MAIL_PROVIDERS:
            continue
        provider = MAIL_PROVIDERS[key]
        result.append(
            {
                "key": key,
                "label": provider.get("label", key),
                "account_type": provider.get("account_type", "imap" if key != "outlook" else "outlook"),
                "note": provider.get("note", ""),
            }
        )
    return result
