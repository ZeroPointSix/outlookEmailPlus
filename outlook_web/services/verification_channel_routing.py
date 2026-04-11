from __future__ import annotations

from typing import Any, Dict, List, Optional

from outlook_web.services import channel_capability_cache
from outlook_web.services import graph as graph_service
from outlook_web.services import imap as imap_service

CHANNEL_GRAPH_INBOX = "graph_inbox"
CHANNEL_GRAPH_JUNK = "graph_junk"
CHANNEL_IMAP_NEW = "imap_new"
CHANNEL_IMAP_OLD = "imap_old"

DEFAULT_VERIFICATION_CHANNEL_CHAIN = (
    CHANNEL_GRAPH_INBOX,
    CHANNEL_GRAPH_JUNK,
    CHANNEL_IMAP_NEW,
    CHANNEL_IMAP_OLD,
)
VALID_VERIFICATION_CHANNELS = set(DEFAULT_VERIFICATION_CHANNEL_CHAIN)

IMAP_SERVER_NEW = "outlook.live.com"
IMAP_SERVER_OLD = "outlook.office365.com"


def normalize_verification_channel(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    if text in VALID_VERIFICATION_CHANNELS:
        return text
    return None


def build_verification_channel_plan(preferred_channel: Any) -> List[str]:
    preferred = normalize_verification_channel(preferred_channel)
    if not preferred:
        return list(DEFAULT_VERIFICATION_CHANNEL_CHAIN)
    return [preferred] + [
        channel
        for channel in DEFAULT_VERIFICATION_CHANNEL_CHAIN
        if channel != preferred
    ]


def map_method_to_verification_channel(
    method: str, *, folder: str = "inbox"
) -> Optional[str]:
    method_text = str(method or "").strip().lower()
    folder_text = str(folder or "inbox").strip().lower()
    if method_text == "graph api":
        return CHANNEL_GRAPH_JUNK if folder_text == "junkemail" else CHANNEL_GRAPH_INBOX
    if method_text == "imap (new)":
        return CHANNEL_IMAP_NEW
    if method_text == "imap (old)":
        return CHANNEL_IMAP_OLD
    return None


def channel_method_label(channel: str) -> str:
    normalized = normalize_verification_channel(channel)
    if normalized == CHANNEL_GRAPH_INBOX:
        return "Graph API (Inbox)"
    if normalized == CHANNEL_GRAPH_JUNK:
        return "Graph API (Junk)"
    if normalized == CHANNEL_IMAP_NEW:
        return "IMAP (New)"
    if normalized == CHANNEL_IMAP_OLD:
        return "IMAP (Old)"
    return ""


def is_outlook_oauth_account(account: Dict[str, Any]) -> bool:
    account_type = str(account.get("account_type") or "outlook").strip().lower()
    if account_type != "outlook":
        return False
    return bool(str(account.get("client_id") or "").strip()) and bool(
        str(account.get("refresh_token") or "").strip()
    )


def fetch_emails_for_channel(
    *,
    account: Dict[str, Any],
    channel: str,
    proxy_url: str = "",
    skip: int = 0,
    top: int = 20,
) -> Dict[str, Any]:
    normalized = normalize_verification_channel(channel)
    if not normalized:
        return {
            "success": False,
            "error": {
                "code": "INVALID_CHANNEL",
                "message": "invalid verification channel",
            },
        }

    if normalized in (CHANNEL_GRAPH_INBOX, CHANNEL_GRAPH_JUNK):
        folder = "junkemail" if normalized == CHANNEL_GRAPH_JUNK else "inbox"
        graph_result = graph_service.get_emails_graph(
            str(account.get("client_id") or ""),
            str(account.get("refresh_token") or ""),
            folder=folder,
            skip=int(skip or 0),
            top=int(top or 20),
            proxy_url=proxy_url,
        )
        if not graph_result.get("success"):
            return {
                "success": False,
                "auth_expired": bool(graph_result.get("auth_expired")),
                "error": graph_result.get("error"),
                "channel": normalized,
            }

        emails = []
        for item in graph_result.get("emails", []) or []:
            enriched = dict(item)
            enriched["folder"] = folder
            enriched["_verification_channel"] = normalized
            emails.append(enriched)
        return {
            "success": True,
            "emails": emails,
            "new_refresh_token": graph_result.get("new_refresh_token"),
            "channel": normalized,
        }

    imap_server = IMAP_SERVER_NEW if normalized == CHANNEL_IMAP_NEW else IMAP_SERVER_OLD
    imap_result = imap_service.get_emails_imap_with_server(
        str(account.get("email") or ""),
        str(account.get("client_id") or ""),
        str(account.get("refresh_token") or ""),
        folder="inbox",
        skip=int(skip or 0),
        top=int(top or 20),
        server=imap_server,
    )
    if not imap_result.get("success"):
        return {
            "success": False,
            "error": imap_result.get("error"),
            "channel": normalized,
        }

    emails = []
    for item in imap_result.get("emails", []) or []:
        enriched = dict(item)
        enriched["folder"] = "inbox"
        enriched["_verification_channel"] = normalized
        emails.append(enriched)
    return {"success": True, "emails": emails, "channel": normalized}


def fetch_email_detail_for_channel(
    *,
    account: Dict[str, Any],
    channel: str,
    message_id: str,
    proxy_url: str = "",
) -> Optional[Dict[str, Any]]:
    normalized = normalize_verification_channel(channel)
    if not normalized or not message_id:
        return None

    if normalized in (CHANNEL_GRAPH_INBOX, CHANNEL_GRAPH_JUNK):
        return graph_service.get_email_detail_graph(
            str(account.get("client_id") or ""),
            str(account.get("refresh_token") or ""),
            str(message_id),
            proxy_url,
        )

    if normalized == CHANNEL_IMAP_NEW:
        return imap_service.get_email_detail_imap_with_server(
            str(account.get("email") or ""),
            str(account.get("client_id") or ""),
            str(account.get("refresh_token") or ""),
            str(message_id),
            "inbox",
            IMAP_SERVER_NEW,
        )

    return imap_service.get_email_detail_imap_with_server(
        str(account.get("email") or ""),
        str(account.get("client_id") or ""),
        str(account.get("refresh_token") or ""),
        str(message_id),
        "inbox",
        IMAP_SERVER_OLD,
    )


def fetch_emails_and_detail_for_channel(
    *,
    account: Dict[str, Any],
    channel: str,
    proxy_url: str = "",
    skip: int = 0,
    top: int = 20,
) -> Dict[str, Any]:
    """IMAP 渠道返回 emails+detail（连接复用），Graph 只返回 emails。"""
    normalized = normalize_verification_channel(channel)
    if not normalized:
        return {
            "success": False,
            "error": {
                "code": "INVALID_CHANNEL",
                "message": "invalid verification channel",
            },
            "channel": "",
        }

    if normalized in (CHANNEL_GRAPH_INBOX, CHANNEL_GRAPH_JUNK):
        return fetch_emails_for_channel(
            account=account,
            channel=normalized,
            proxy_url=proxy_url,
            skip=skip,
            top=top,
        )

    server = IMAP_SERVER_NEW if normalized == CHANNEL_IMAP_NEW else IMAP_SERVER_OLD
    result = imap_service.fetch_and_detail_imap_with_server(
        str(account.get("email") or ""),
        str(account.get("client_id") or ""),
        str(account.get("refresh_token") or ""),
        folder="inbox",
        skip=int(skip or 0),
        top=int(top or 20),
        server=server,
    )

    # 兼容回退：当连接复用路径失败时，降级到原 list + detail 两次调用。
    if not result.get("success"):
        legacy_list = imap_service.get_emails_imap_with_server(
            str(account.get("email") or ""),
            str(account.get("client_id") or ""),
            str(account.get("refresh_token") or ""),
            folder="inbox",
            skip=int(skip or 0),
            top=int(top or 20),
            server=server,
        )
        if not legacy_list.get("success"):
            return {
                "success": False,
                "error": result.get("error") or legacy_list.get("error"),
                "channel": normalized,
            }

        legacy_emails = [
            dict(item, folder="inbox", _verification_channel=normalized)
            for item in (legacy_list.get("emails") or [])
        ]

        legacy_detail = None
        if legacy_emails:
            latest_id = str((legacy_emails[0] or {}).get("id") or "")
            if latest_id:
                legacy_detail = imap_service.get_email_detail_imap_with_server(
                    str(account.get("email") or ""),
                    str(account.get("client_id") or ""),
                    str(account.get("refresh_token") or ""),
                    latest_id,
                    "inbox",
                    server,
                )

        return {
            "success": True,
            "emails": legacy_emails,
            "detail": legacy_detail,
            "channel": normalized,
        }

    emails = [
        dict(item, folder="inbox", _verification_channel=normalized)
        for item in (result.get("emails") or [])
    ]
    return {
        "success": True,
        "emails": emails,
        "detail": result.get("detail"),
        "channel": normalized,
    }


def _get_channel_display_name(channel: str) -> str:
    return {
        "graph_inbox": "Graph (Inbox)",
        "graph_junk": "Graph (Junk)",
        "imap_new": "IMAP (New)",
        "imap_old": "IMAP (Old)",
    }.get(channel, channel)


def _is_extraction_success(extracted: Dict[str, Any], expected_field: Any) -> bool:
    if expected_field:
        return bool(extracted.get(expected_field))
    return bool(
        extracted.get("verification_code") or extracted.get("verification_link")
    )


def _build_email_obj_from_channel_detail(
    *, detail: Dict[str, Any], latest: Dict[str, Any]
) -> Dict[str, Any]:
    # Graph 详情
    if "body" in detail and isinstance(detail.get("body"), dict):
        body_content = detail.get("body") or {}
        content_type = str(body_content.get("contentType") or "text").lower()
        body_content_text = str(body_content.get("content") or "")

        from_obj = detail.get("from") or {}
        if isinstance(from_obj, dict):
            from_addr = (
                (from_obj.get("emailAddress") or {}).get("address")
                or from_obj.get("address")
                or ""
            )
        else:
            from_addr = str(from_obj or "")

        return {
            "subject": str(detail.get("subject") or latest.get("subject") or ""),
            "body": body_content_text if content_type == "text" else "",
            "body_html": body_content_text if content_type == "html" else "",
            "raw_content": str(detail.get("raw_content") or ""),
            "from": str(from_addr or latest.get("from") or ""),
            "date": str(detail.get("receivedDateTime") or latest.get("date") or ""),
        }

    return {
        "subject": str(detail.get("subject") or latest.get("subject") or ""),
        "body": str(detail.get("body") or ""),
        "body_html": str(detail.get("body_html") or ""),
        "raw_content": str(detail.get("raw_content") or ""),
        "from": str(detail.get("from") or latest.get("from") or ""),
        "date": str(detail.get("date") or latest.get("date") or ""),
    }


def extract_verification_for_outlook(
    *,
    account: Dict[str, Any],
    proxy_url: str = "",
    resolved_policy: Dict[str, Any],
    code_source: str = "all",
    expected_field: Any = None,
    from_contains: str = "",
    subject_contains: str = "",
    since_minutes: Any = None,
    baseline_timestamp: Any = None,
) -> Dict[str, Any]:
    """Outlook OAuth 账号验证码提取统一入口（Web 端和 External API 均调用此函数）。"""
    preferred = normalize_verification_channel(
        account.get("preferred_verification_channel")
    )
    channel_plan = build_verification_channel_plan(preferred)
    channel_plan = channel_capability_cache.filter_channel_plan(
        str(account.get("email") or ""), channel_plan
    )

    # Graph 权限预检：无 Mail.Read 权限时直接跳过 Graph 渠道。
    try:
        from outlook_web.services.graph import (
            get_access_token_graph_result,
            has_mail_read_permission,
        )

        precheck = get_access_token_graph_result(
            str(account.get("client_id") or ""),
            str(account.get("refresh_token") or ""),
            proxy_url or None,
        )
        if precheck.get("success") and not has_mail_read_permission(
            precheck.get("scope", "")
        ):
            channel_plan = [ch for ch in channel_plan if not ch.startswith("graph_")]
    except Exception:
        pass

    any_channel_read_success = False
    graph_auth_expired = False
    upstream_errors: Dict[str, Any] = {}
    last_extracted = None
    new_refresh_token = None

    for channel in channel_plan:
        channel_result = fetch_emails_and_detail_for_channel(
            account=account,
            channel=channel,
            proxy_url=proxy_url,
            top=20,
        )

        if not channel_result.get("success"):
            upstream_errors[channel] = channel_result.get("error")
            if channel.startswith("graph_") and channel_result.get("auth_expired"):
                graph_auth_expired = True
            channel_capability_cache.set_status(
                str(account.get("email") or ""), channel, available=False
            )
            continue

        any_channel_read_success = True
        channel_capability_cache.set_status(
            str(account.get("email") or ""), channel, available=True
        )

        if channel_result.get("new_refresh_token"):
            new_refresh_token = channel_result.get("new_refresh_token")

        emails = channel_result.get("emails", [])
        if from_contains or subject_contains or since_minutes or baseline_timestamp:
            from outlook_web.services.external_api import filter_messages

            emails = filter_messages(
                emails,
                from_contains=from_contains,
                subject_contains=subject_contains,
                since_minutes=since_minutes,
                baseline_timestamp=baseline_timestamp,
            )
        if not emails:
            continue

        latest = sorted(
            emails,
            key=lambda x: x.get("date", "") or x.get("receivedDateTime", ""),
            reverse=True,
        )[0]

        if channel.startswith("imap_"):
            detail = channel_result.get("detail")
        else:
            detail = fetch_email_detail_for_channel(
                account=account,
                channel=channel,
                message_id=latest.get("id", ""),
                proxy_url=proxy_url,
            )

        if not detail:
            continue

        email_obj = _build_email_obj_from_channel_detail(detail=detail, latest=latest)

        from outlook_web.services.verification_extractor import (
            apply_confidence_gate,
            enhance_verification_with_ai_fallback,
            extract_verification_info_with_options,
        )

        extracted = extract_verification_info_with_options(
            email_obj,
            code_regex=resolved_policy.get("code_regex"),
            code_length=resolved_policy.get("code_length"),
            code_source=code_source,
            enforce_mutual_exclusion=False,
        )
        extracted = enhance_verification_with_ai_fallback(
            email=email_obj,
            extracted=extracted,
            code_regex=resolved_policy.get("code_regex"),
            code_length=resolved_policy.get("code_length"),
            code_source=code_source,
            enforce_mutual_exclusion=False,
        )
        extracted = apply_confidence_gate(extracted, enforce_mutual_exclusion=False)

        extracted.update(
            {
                "email": account.get("email", ""),
                "matched_email_id": latest.get("id", ""),
                "from": email_obj["from"],
                "subject": email_obj["subject"],
                "received_at": email_obj["date"],
                "folder": latest.get("folder", "inbox"),
                "method": _get_channel_display_name(channel),
            }
        )
        last_extracted = extracted

        if _is_extraction_success(extracted, expected_field):
            try:
                from outlook_web.repositories import accounts as accounts_repo

                accounts_repo.update_preferred_verification_channel(
                    int(account["id"]), channel
                )
            except Exception:
                pass

            return {
                "success": True,
                "data": extracted,
                "channel_used": channel,
                "new_refresh_token": new_refresh_token,
            }

    if last_extracted:
        return {
            "success": True,
            "data": last_extracted,
            "channel_used": "",
            "new_refresh_token": new_refresh_token,
        }

    if not any_channel_read_success:
        return {
            "success": False,
            "error_code": "ACCOUNT_AUTH_EXPIRED",
            "error_message": "所有渠道认证失败",
            "error_status": 401,
            "upstream_errors": upstream_errors,
            "graph_auth_expired": graph_auth_expired,
        }

    return {
        "success": False,
        "error_code": "EMAIL_NOT_FOUND",
        "error_message": "未找到匹配邮件",
        "error_status": 404,
        "upstream_errors": upstream_errors,
    }
