from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple

from outlook_web.audit import log_audit
from outlook_web.repositories import accounts as accounts_repo
from outlook_web.repositories import external_api_keys as external_api_keys_repo
from outlook_web.repositories import groups as groups_repo
from outlook_web.security.auth import get_external_api_consumer
from outlook_web.services import graph as graph_service
from outlook_web.services import imap as imap_service
from outlook_web.services.imap_generic import get_email_detail_imap_generic_result, get_emails_imap_generic
from outlook_web.services import pool as pool_service
from outlook_web.services.verification_extractor import extract_email_text, extract_verification_info_with_options

# Outlook IMAP 回退服务器（保持与内部接口一致）
IMAP_SERVER_NEW = "outlook.live.com"
IMAP_SERVER_OLD = "outlook.office365.com"

# wait-message 约束
MAX_TIMEOUT_SECONDS = 120


class ExternalApiError(Exception):
    code = "INTERNAL_ERROR"
    status = 500

    def __init__(self, message: str, *, data: Any = None):
        super().__init__(message)
        self.message = message
        self.data = data


class InvalidParamError(ExternalApiError):
    code = "INVALID_PARAM"
    status = 400


class AccountNotFoundError(ExternalApiError):
    code = "ACCOUNT_NOT_FOUND"
    status = 404


class MailNotFoundError(ExternalApiError):
    code = "MAIL_NOT_FOUND"
    status = 404


class VerificationCodeNotFoundError(ExternalApiError):
    code = "VERIFICATION_CODE_NOT_FOUND"
    status = 404


class VerificationLinkNotFoundError(ExternalApiError):
    code = "VERIFICATION_LINK_NOT_FOUND"
    status = 404


class ProxyError(ExternalApiError):
    code = "PROXY_ERROR"
    status = 502


class UpstreamReadFailedError(ExternalApiError):
    code = "UPSTREAM_READ_FAILED"
    status = 502


class EmailScopeForbiddenError(ExternalApiError):
    code = "EMAIL_SCOPE_FORBIDDEN"
    status = 403


class AccountAccessForbiddenError(ExternalApiError):
    code = "ACCOUNT_ACCESS_FORBIDDEN"
    status = 403


class ClaimContextMismatchError(ExternalApiError):
    code = "CLAIM_CONTEXT_MISMATCH"
    status = 400


class ClaimTokenNotFoundError(ExternalApiError):
    code = "CLAIM_TOKEN_NOT_FOUND"
    status = 404


def ok(data: Any = None, *, message: str = "success") -> Dict[str, Any]:
    return {"success": True, "code": "OK", "message": message, "data": data}


def fail(code: str, message: str, *, data: Any = None) -> Dict[str, Any]:
    return {"success": False, "code": code, "message": message, "data": data}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None

    # 1) ISO 8601（Graph 常见：2026-03-08T12:00:00Z）
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # 2) RFC2822（IMAP Date header 常见）
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _format_datetime(dt: Optional[datetime], fallback: str = "") -> tuple[str, int]:
    if not dt:
        return (fallback or "", 0)
    try:
        dt = dt.astimezone(timezone.utc).replace(microsecond=0)
        return (dt.isoformat().replace("+00:00", "Z"), int(dt.timestamp()))
    except Exception:
        return (fallback or "", 0)


def _extract_email_address(value: str) -> str:
    """从 `Name <addr>` 中提取 addr；解析失败则原样返回。"""
    try:
        _name, addr = parseaddr(str(value or ""))
        return addr or str(value or "")
    except Exception:
        return str(value or "")


def get_current_external_api_consumer() -> Dict[str, Any]:
    return get_external_api_consumer() or {}


def ensure_external_email_access(email_addr: str) -> None:
    consumer = get_current_external_api_consumer()
    allowed_emails = [str(item or "").strip().lower() for item in (consumer.get("allowed_emails") or [])]
    target_email = str(email_addr or "").strip().lower()
    if allowed_emails and target_email not in allowed_emails:
        raise EmailScopeForbiddenError(
            "当前 API Key 无权访问该邮箱",
            data={
                "email": email_addr,
                "consumer_id": consumer.get("id"),
                "consumer_name": consumer.get("name"),
            },
        )


def _normalize_email_addr(email_addr: str | None) -> str:
    return str(email_addr or "").strip().lower()


def resolve_claim_context(*, claim_token: str, email_addr: str | None = None) -> Dict[str, Any]:
    try:
        claim_context = pool_service.get_claim_context(claim_token=claim_token)
    except pool_service.PoolServiceError as exc:
        error_code = str(exc.error_code or "").strip().lower()
        if error_code == "claim_token_not_found":
            raise ClaimTokenNotFoundError(str(exc)) from exc
        raise InvalidParamError(str(exc)) from exc

    claim_email = _normalize_email_addr(claim_context.get("email"))
    if not claim_email:
        raise ClaimTokenNotFoundError("claim_token 对应的邮箱上下文不存在")
    ensure_external_email_access(claim_email)

    requested_email = _normalize_email_addr(email_addr)
    if requested_email and requested_email != claim_email:
        raise ClaimContextMismatchError(
            "claim_token 与 email 不匹配",
            data={"email": requested_email, "claim_email": claim_email},
        )

    return {
        "account_id": claim_context.get("account_id"),
        "claim_token": claim_context.get("claim_token") or str(claim_token or "").strip(),
        "email": claim_email,
        "email_domain": claim_context.get("email_domain") or "",
        "provider": claim_context.get("provider") or "",
        "consumer_key": claim_context.get("consumer_key") or "",
        "project_key": claim_context.get("project_key") or "",
        "caller_id": claim_context.get("caller_id") or "",
        "task_id": claim_context.get("task_id") or "",
        "claimed_at": claim_context.get("claimed_at") or "",
        "pool_status": claim_context.get("pool_status") or "",
    }


def resolve_external_mail_scope(*, email_addr: str | None = None, claim_token: str | None = None) -> Dict[str, Any]:
    normalized_claim_token = str(claim_token or "").strip()
    normalized_email = _normalize_email_addr(email_addr)

    if normalized_claim_token:
        claim_context = resolve_claim_context(claim_token=normalized_claim_token, email_addr=normalized_email or None)
        return {
            "email": claim_context["email"],
            "claim_context": claim_context,
            "claimed_at": claim_context.get("claimed_at") or "",
        }

    if not normalized_email:
        raise InvalidParamError("email 参数无效")
    ensure_external_email_access(normalized_email)
    return {"email": normalized_email, "claim_context": None, "claimed_at": ""}


def claimed_at_to_timestamp(claimed_at: str | None) -> Optional[int]:
    dt = _parse_datetime(str(claimed_at or ""))
    if not dt:
        return None
    try:
        return int(dt.timestamp())
    except Exception:
        return None


def record_claim_read_context(*, claim_token: str | None, action: str, payload: Dict[str, Any]) -> None:
    normalized_token = str(claim_token or "").strip()
    if not normalized_token:
        return
    try:
        pool_service.append_claim_read_context(
            claim_token=normalized_token,
            action=action,
            payload=payload,
        )
    except Exception:
        pass


def _build_message_summary(email_addr: str, item: Dict[str, Any], *, method: str) -> Dict[str, Any]:
    raw_from = item.get("from")
    if isinstance(raw_from, dict):
        from_address = (raw_from.get("emailAddress") or {}).get("address") or ""
    else:
        from_address = str(raw_from or item.get("from_address") or "")
    from_address = _extract_email_address(from_address)

    subject = str(item.get("subject") or "无主题")

    created_at_raw = (
        item.get("receivedDateTime") or item.get("date") or item.get("created_at") or item.get("received_at") or ""
    )
    created_dt = _parse_datetime(str(created_at_raw))
    created_at, timestamp = _format_datetime(created_dt, str(created_at_raw))

    content_preview = str(
        item.get("bodyPreview") or item.get("body_preview") or item.get("content_preview") or item.get("bodyPreview") or ""
    )

    is_read = bool(item.get("isRead") if "isRead" in item else item.get("is_read") or item.get("isRead") or False)

    return {
        "id": str(item.get("id") or ""),
        "email_address": email_addr,
        "from_address": from_address,
        "subject": subject,
        "content_preview": content_preview,
        "has_html": bool(item.get("has_html") or False),
        "timestamp": timestamp,
        "created_at": created_at,
        "is_read": is_read,
        "method": method,
    }


def _get_proxy_url(account: Dict[str, Any]) -> str:
    proxy_url = ""
    group_id = account.get("group_id")
    if not group_id:
        return ""
    group = groups_repo.get_group_by_id(group_id)
    if group:
        proxy_url = group.get("proxy_url", "") or ""
    return proxy_url


def require_account(email_addr: str) -> Dict[str, Any]:
    email_addr = (email_addr or "").strip()
    if not email_addr:
        raise InvalidParamError("email 参数不能为空")
    if "@" not in email_addr:
        raise InvalidParamError("email 参数无效")
    account = accounts_repo.get_account_by_email(email_addr)
    if not account:
        raise AccountNotFoundError("账号不存在", data={"email": email_addr})
    return account


def _preferred_probe_method(account: Dict[str, Any]) -> str:
    account_type = (account.get("account_type") or "outlook").strip().lower()
    return "imap_generic" if account_type == "imap" else "graph"


def _account_can_read(account: Dict[str, Any]) -> bool:
    status = (account.get("status") or "active").strip().lower()
    if status != "active":
        return False
    account_type = (account.get("account_type") or "outlook").strip().lower()
    if account_type == "imap":
        return bool((account.get("imap_host") or "").strip()) and bool((account.get("imap_password") or "").strip())
    return bool((account.get("client_id") or "").strip()) and bool((account.get("refresh_token") or "").strip())


def can_account_read(account: Dict[str, Any]) -> bool:
    return _account_can_read(account)


def ensure_account_can_read(account: Dict[str, Any]) -> Dict[str, Any]:
    if _account_can_read(account):
        return account
    raise AccountAccessForbiddenError(
        "当前账号不可读取",
        data={
            "email": account.get("email") or "",
            "status": account.get("status") or "",
            "account_type": account.get("account_type") or "",
        },
    )


def _probe_now_iso() -> str:
    return _utcnow().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _probe_summary_from_row(row: Any) -> Dict[str, Any]:
    if not row:
        return {
            "upstream_probe_ok": None,
            "probe_method": "",
            "last_probe_at": "",
            "last_probe_error": "",
        }
    return {
        "upstream_probe_ok": None if row["probe_ok"] is None else bool(row["probe_ok"]),
        "probe_method": row["probe_method"] or "",
        "last_probe_at": row["last_probe_at"] or "",
        "last_probe_error": row["last_probe_error"] or "",
    }


def get_upstream_probe_summary(scope_type: str, scope_key: str) -> Dict[str, Any]:
    from outlook_web.db import get_db

    db = get_db()
    row = db.execute(
        """
        SELECT scope_type, scope_key, email_addr, probe_method, probe_ok, last_probe_at, last_probe_error
        FROM external_upstream_probes
        WHERE scope_type = ? AND scope_key = ?
        """,
        (scope_type, scope_key),
    ).fetchone()
    return _probe_summary_from_row(row)


def _is_probe_summary_fresh(summary: Dict[str, Any], cache_ttl_seconds: int) -> bool:
    last_probe_at = summary.get("last_probe_at") or ""
    if not last_probe_at:
        return False
    probed_at = _parse_datetime(last_probe_at)
    if not probed_at:
        return False
    age_seconds = (_utcnow() - probed_at).total_seconds()
    return age_seconds <= max(0, int(cache_ttl_seconds))


def record_upstream_probe_summary(
    *,
    scope_type: str,
    scope_key: str,
    email_addr: str,
    probe_ok: Optional[bool],
    probe_method: str = "",
    last_probe_error: str = "",
    last_probe_at: Optional[str] = None,
) -> Dict[str, Any]:
    from outlook_web.db import get_db

    db = get_db()
    probe_at = last_probe_at or _probe_now_iso()
    db.execute(
        """
        INSERT INTO external_upstream_probes
            (scope_type, scope_key, email_addr, probe_method, probe_ok, last_probe_at, last_probe_error, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(scope_type, scope_key)
        DO UPDATE SET
            email_addr = excluded.email_addr,
            probe_method = excluded.probe_method,
            probe_ok = excluded.probe_ok,
            last_probe_at = excluded.last_probe_at,
            last_probe_error = excluded.last_probe_error,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            scope_type,
            scope_key,
            email_addr or "",
            probe_method or "",
            None if probe_ok is None else int(bool(probe_ok)),
            probe_at,
            str(last_probe_error or "")[:500],
        ),
    )
    db.commit()
    return {
        "upstream_probe_ok": probe_ok,
        "probe_method": probe_method or "",
        "last_probe_at": probe_at,
        "last_probe_error": str(last_probe_error or "")[:500],
    }


def _probe_error_message(exc: Exception) -> str:
    if isinstance(exc, ExternalApiError):
        return str(exc.message or exc.code or "探测失败")
    return str(exc)[:500] or type(exc).__name__


def probe_account_upstream(
    account: Dict[str, Any],
    *,
    folder: str = "inbox",
    cache_ttl_seconds: int = 60,
    force: bool = False,
) -> Dict[str, Any]:
    email_addr = str(account.get("email") or "").strip()
    preferred_method = _preferred_probe_method(account)
    cached = get_upstream_probe_summary("account", email_addr) if email_addr else {}
    if email_addr and (not force) and _is_probe_summary_fresh(cached, cache_ttl_seconds):
        return cached

    last_probe_at = _probe_now_iso()
    try:
        _emails, method = list_messages_for_external(email_addr=email_addr, folder=folder, top=1, skip=0)
        summary = record_upstream_probe_summary(
            scope_type="account",
            scope_key=email_addr,
            email_addr=email_addr,
            probe_ok=True,
            probe_method=str(method or preferred_method),
            last_probe_error="",
            last_probe_at=last_probe_at,
        )
    except Exception as exc:
        summary = record_upstream_probe_summary(
            scope_type="account",
            scope_key=email_addr,
            email_addr=email_addr,
            probe_ok=False,
            probe_method=preferred_method,
            last_probe_error=_probe_error_message(exc),
            last_probe_at=last_probe_at,
        )
    record_upstream_probe_summary(
        scope_type="instance",
        scope_key="__instance__",
        email_addr=email_addr,
        probe_ok=summary.get("upstream_probe_ok"),
        probe_method=summary.get("probe_method") or preferred_method,
        last_probe_error=summary.get("last_probe_error") or "",
        last_probe_at=summary.get("last_probe_at") or last_probe_at,
    )
    return summary


def _pick_instance_probe_account() -> Optional[Dict[str, Any]]:
    candidates = accounts_repo.load_accounts()
    for account in candidates:
        if _account_can_read(account):
            return account
    return None


def probe_instance_upstream(*, cache_ttl_seconds: int = 60, force: bool = False) -> Dict[str, Any]:
    cached = get_upstream_probe_summary("instance", "__instance__")
    if (not force) and _is_probe_summary_fresh(cached, cache_ttl_seconds):
        return cached

    account = _pick_instance_probe_account()
    if not account:
        return cached

    return probe_account_upstream(account, cache_ttl_seconds=cache_ttl_seconds, force=force)


def list_messages_for_external(
    *,
    email_addr: str,
    folder: str = "inbox",
    skip: int = 0,
    top: int = 20,
) -> Tuple[List[Dict[str, Any]], str]:
    account = ensure_account_can_read(require_account(email_addr))
    folder = (folder or "inbox").strip().lower() or "inbox"
    skip = max(0, int(skip or 0))
    top = max(1, min(int(top or 20), 50))

    account_type = (account.get("account_type") or "outlook").strip().lower()
    if account_type == "imap":
        result = get_emails_imap_generic(
            email_addr=email_addr,
            imap_password=account.get("imap_password", "") or "",
            imap_host=account.get("imap_host", "") or "",
            imap_port=account.get("imap_port", 993) or 993,
            folder=folder,
            provider=account.get("provider", "_default") or "_default",
            skip=skip,
            top=top,
        )
        if not result.get("success"):
            raise UpstreamReadFailedError("IMAP 读取失败", data=result.get("error"))
        method_label = str(result.get("method") or "IMAP (Generic)")
        emails = [_build_message_summary(email_addr, e, method=method_label) for e in (result.get("emails") or [])]
        return emails, method_label

    proxy_url = _get_proxy_url(account)

    graph_result = graph_service.get_emails_graph(
        account.get("client_id") or "",
        account.get("refresh_token") or "",
        folder=folder,
        skip=skip,
        top=top,
        proxy_url=proxy_url,
    )
    if graph_result.get("success"):
        method_label = "Graph API"
        emails = [_build_message_summary(email_addr, e, method=method_label) for e in (graph_result.get("emails") or [])]
        return emails, method_label

    graph_error = graph_result.get("error")
    if isinstance(graph_error, dict) and graph_error.get("type") in ("ProxyError", "ConnectionError"):
        raise ProxyError("代理连接失败", data=graph_error)

    # Graph 失败 → IMAP(New) → IMAP(Old) 回退
    imap_new_result = imap_service.get_emails_imap_with_server(
        email_addr,
        account.get("client_id") or "",
        account.get("refresh_token") or "",
        folder,
        skip,
        top,
        IMAP_SERVER_NEW,
    )
    if imap_new_result.get("success"):
        method_label = "IMAP (New)"
        emails = [_build_message_summary(email_addr, e, method=method_label) for e in (imap_new_result.get("emails") or [])]
        return emails, method_label

    imap_old_result = imap_service.get_emails_imap_with_server(
        email_addr,
        account.get("client_id") or "",
        account.get("refresh_token") or "",
        folder,
        skip,
        top,
        IMAP_SERVER_OLD,
    )
    if imap_old_result.get("success"):
        method_label = "IMAP (Old)"
        emails = [_build_message_summary(email_addr, e, method=method_label) for e in (imap_old_result.get("emails") or [])]
        return emails, method_label

    raise UpstreamReadFailedError(
        "Graph/IMAP 均读取失败",
        data={"graph": graph_error, "imap_new": imap_new_result.get("error"), "imap_old": imap_old_result.get("error")},
    )


def filter_messages(
    emails: List[Dict[str, Any]],
    *,
    from_contains: str = "",
    subject_contains: str = "",
    since_minutes: Optional[int] = None,
    baseline_timestamp: Optional[int] = None,
) -> List[Dict[str, Any]]:
    from_contains = (from_contains or "").strip().lower()
    subject_contains = (subject_contains or "").strip().lower()

    since_dt: Optional[datetime] = None
    if since_minutes is not None:
        try:
            since_minutes_int = int(since_minutes)
            if since_minutes_int > 0:
                since_dt = _utcnow() - timedelta(minutes=since_minutes_int)
        except Exception:
            since_dt = None

    filtered: List[Dict[str, Any]] = []
    for e in emails or []:
        from_addr = str(e.get("from_address") or e.get("from") or "").lower()
        subj = str(e.get("subject") or "").lower()
        if from_contains and from_contains not in from_addr:
            continue
        if subject_contains and subject_contains not in subj:
            continue

        if since_dt is not None:
            dt = _parse_datetime(e.get("created_at") or e.get("date") or e.get("receivedDateTime") or "")
            if dt and dt < since_dt:
                continue

        if baseline_timestamp is not None:
            try:
                if int(e.get("timestamp") or 0) < int(baseline_timestamp):
                    continue
            except Exception:
                continue

        filtered.append(e)
    return filtered


def get_latest_message_for_external(
    *,
    email_addr: str,
    folder: str = "inbox",
    from_contains: str = "",
    subject_contains: str = "",
    since_minutes: Optional[int] = None,
    baseline_timestamp: Optional[int] = None,
) -> Dict[str, Any]:
    emails = list_messages_for_external(email_addr=email_addr, folder=folder, skip=0, top=20)[0]
    filtered = filter_messages(
        emails,
        from_contains=from_contains,
        subject_contains=subject_contains,
        since_minutes=since_minutes,
        baseline_timestamp=baseline_timestamp,
    )
    if not filtered:
        raise MailNotFoundError("未找到匹配邮件", data={"email": email_addr})
    # 保险起见按 timestamp 再排序一次（不同读取链路可能不严格有序）
    filtered.sort(key=lambda x: int(x.get("timestamp") or 0), reverse=True)
    return filtered[0]


def get_message_detail_for_external(
    *,
    email_addr: str,
    message_id: str,
    folder: str = "inbox",
) -> Dict[str, Any]:
    account = ensure_account_can_read(require_account(email_addr))
    message_id = (message_id or "").strip()
    if not message_id:
        raise InvalidParamError("message_id 不能为空")

    folder = (folder or "inbox").strip().lower() or "inbox"
    account_type = (account.get("account_type") or "outlook").strip().lower()

    if account_type == "imap":
        detail_result = get_email_detail_imap_generic_result(
            email_addr=email_addr,
            imap_password=account.get("imap_password", "") or "",
            imap_host=account.get("imap_host", "") or "",
            imap_port=account.get("imap_port", 993) or 993,
            message_id=message_id,
            folder=folder,
            provider=account.get("provider", "_default") or "_default",
        )
        if not detail_result.get("success"):
            error_payload = detail_result.get("error") or {}
            raise UpstreamReadFailedError(str(error_payload.get("message") or "IMAP 读取失败"), data=error_payload)
        detail = detail_result.get("email") or {}

        html_content = str(detail.get("body_html") or "")
        content = str(detail.get("body_text") or "") or extract_email_text({"body_html": html_content})
        raw_content = str(detail.get("raw_content") or "")
        created_at_raw = str(detail.get("date") or "")
        created_at, timestamp = _format_datetime(_parse_datetime(created_at_raw), created_at_raw)
        return {
            "id": detail.get("id") or message_id,
            "email_address": email_addr,
            "from_address": _extract_email_address(detail.get("from") or ""),
            "to_address": detail.get("to") or "",
            "subject": detail.get("subject") or "",
            "content": content,
            "html_content": html_content,
            "raw_content": raw_content,
            "timestamp": timestamp,
            "created_at": created_at,
            "has_html": bool(html_content),
            "method": "IMAP (Generic)",
        }

    proxy_url = _get_proxy_url(account)

    detail = graph_service.get_email_detail_graph(
        account.get("client_id") or "",
        account.get("refresh_token") or "",
        message_id,
        proxy_url,
    )
    method_label = "Graph API"
    graph_raw_content = None
    if detail:
        graph_raw_content = graph_service.get_email_raw_graph(
            account.get("client_id") or "",
            account.get("refresh_token") or "",
            message_id,
            proxy_url,
        )
    if not detail:
        detail = imap_service.get_email_detail_imap_with_server(
            email_addr,
            account.get("client_id") or "",
            account.get("refresh_token") or "",
            message_id,
            folder,
            IMAP_SERVER_NEW,
        )
        method_label = "IMAP (New)"

    if not detail:
        detail = imap_service.get_email_detail_imap_with_server(
            email_addr,
            account.get("client_id") or "",
            account.get("refresh_token") or "",
            message_id,
            folder,
            IMAP_SERVER_OLD,
        )
        method_label = "IMAP (Old)"

    if not detail:
        raise MailNotFoundError("未找到邮件详情", data={"email": email_addr, "message_id": message_id})

    created_at_raw = ""
    timestamp = 0
    created_at = ""

    if "body" in detail and isinstance(detail.get("body"), dict):
        body_obj = detail.get("body") or {}
        body_type = str(body_obj.get("contentType") or "text").lower()
        body_content = str(body_obj.get("content") or "")

        html_content = body_content if body_type == "html" else ""
        content = body_content if body_type == "text" else extract_email_text({"body_html": html_content})
        raw_content = str(graph_raw_content or body_content)

        from_address = (detail.get("from") or {}).get("emailAddress", {}).get("address", "")
        to_address = ",".join([r.get("emailAddress", {}).get("address", "") for r in (detail.get("toRecipients") or [])])
        created_at_raw = str(detail.get("receivedDateTime") or "")
        subject = str(detail.get("subject") or "")
    else:
        # IMAP dict 格式
        content = str(detail.get("body") or "")
        html_content = ""
        raw_content = str(detail.get("raw_content") or content)
        from_address = _extract_email_address(str(detail.get("from") or ""))
        to_address = str(detail.get("to") or "")
        created_at_raw = str(detail.get("date") or "")
        subject = str(detail.get("subject") or "")

    created_at, timestamp = _format_datetime(_parse_datetime(created_at_raw), created_at_raw)

    return {
        "id": message_id,
        "email_address": email_addr,
        "from_address": _extract_email_address(from_address),
        "to_address": to_address,
        "subject": subject,
        "content": content,
        "html_content": html_content,
        "raw_content": raw_content,
        "timestamp": timestamp,
        "created_at": created_at,
        "has_html": bool(html_content),
        "method": method_label,
    }


def get_verification_result(
    *,
    email_addr: str,
    folder: str = "inbox",
    from_contains: str = "",
    subject_contains: str = "",
    since_minutes: Optional[int] = None,
    baseline_timestamp: Optional[int] = None,
    claim_token: str | None = None,
    code_regex: str | None = None,
    code_length: str | None = None,
    code_source: str = "all",
) -> Dict[str, Any]:
    latest_summary = get_latest_message_for_external(
        email_addr=email_addr,
        folder=folder,
        from_contains=from_contains,
        subject_contains=subject_contains,
        since_minutes=since_minutes,
        baseline_timestamp=baseline_timestamp,
    )
    message_id = str(latest_summary.get("id") or "")
    method = str(latest_summary.get("method") or "")

    detail = get_message_detail_for_external(email_addr=email_addr, message_id=message_id, folder=folder)

    email_obj = {
        "subject": detail.get("subject") or "",
        "body": detail.get("content") or "",
        "body_html": detail.get("html_content") or "",
        "body_preview": latest_summary.get("content_preview") or "",
    }
    extracted = extract_verification_info_with_options(
        email_obj,
        code_regex=code_regex,
        code_length=code_length,
        code_source=code_source,
    )

    # ── 可信度门控：非高置信度结果不作为 external API 成功输出 ──
    if extracted.get("code_confidence") != "high":
        extracted["verification_code"] = None
    if extracted.get("link_confidence") != "high":
        extracted["verification_link"] = None
    # 重算 formatted（与清零后的值保持一致）
    parts = [v for v in (extracted.get("verification_code"), extracted.get("verification_link")) if v]
    extracted["formatted"] = " ".join(parts) if parts else None

    extracted["email"] = email_addr
    extracted["matched_email_id"] = message_id
    extracted["from"] = detail.get("from_address") or latest_summary.get("from_address") or ""
    extracted["subject"] = detail.get("subject") or latest_summary.get("subject") or ""
    extracted["received_at"] = detail.get("created_at") or latest_summary.get("created_at") or ""
    extracted["method"] = detail.get("method") or method
    if claim_token:
        extracted["claim_token"] = claim_token
    return extracted


def wait_for_message(
    *,
    email_addr: str,
    timeout_seconds: int = 30,
    poll_interval: int = 5,
    folder: str = "inbox",
    from_contains: str = "",
    subject_contains: str = "",
    since_minutes: Optional[int] = None,
    baseline_timestamp: Optional[int] = None,
    claim_token: str | None = None,
) -> Dict[str, Any]:
    try:
        timeout_seconds = int(timeout_seconds)
        poll_interval = int(poll_interval)
    except Exception as exc:
        raise InvalidParamError("timeout_seconds/poll_interval 参数无效") from exc

    if timeout_seconds <= 0 or timeout_seconds > MAX_TIMEOUT_SECONDS:
        raise InvalidParamError(f"timeout_seconds 必须在 1-{MAX_TIMEOUT_SECONDS} 秒之间")
    if poll_interval <= 0 or poll_interval > timeout_seconds:
        raise InvalidParamError("poll_interval 参数无效")

    # 记录进入等待接口时的时间戳，避免把请求开始前已存在的旧邮件误判成“新到达”。
    effective_baseline = int(baseline_timestamp or 0) or int(time.time())
    start = time.time()
    last_error: Optional[ExternalApiError] = None
    while True:
        try:
            latest_message = get_latest_message_for_external(
                email_addr=email_addr,
                folder=folder,
                from_contains=from_contains,
                subject_contains=subject_contains,
                since_minutes=since_minutes,
                baseline_timestamp=effective_baseline,
            )
            if int(latest_message.get("timestamp") or 0) >= effective_baseline:
                if claim_token:
                    latest_message["claim_token"] = claim_token
                return latest_message
        except MailNotFoundError as exc:
            last_error = exc

        if time.time() - start >= timeout_seconds:
            raise MailNotFoundError("等待超时，未检测到匹配邮件", data={"email": email_addr}) from last_error

        time.sleep(poll_interval)


# ── P2: 异步探测 (probe) ──────────────────────────────


def _validate_probe_params(
    email_addr: str,
    timeout_seconds: int,
    poll_interval: int,
) -> None:
    """校验探测参数，与 wait_for_message 保持一致。"""
    if not email_addr:
        raise InvalidParamError("email 参数不能为空")
    try:
        timeout_seconds = int(timeout_seconds)
        poll_interval = int(poll_interval)
    except Exception as exc:
        raise InvalidParamError("timeout_seconds/poll_interval 参数无效") from exc
    if timeout_seconds <= 0 or timeout_seconds > MAX_TIMEOUT_SECONDS:
        raise InvalidParamError(f"timeout_seconds 必须在 1-{MAX_TIMEOUT_SECONDS} 秒之间")
    if poll_interval <= 0 or poll_interval > timeout_seconds:
        raise InvalidParamError("poll_interval 参数无效")


def create_probe(
    *,
    email_addr: str,
    timeout_seconds: int = 30,
    poll_interval: int = 5,
    folder: str = "inbox",
    from_contains: str = "",
    subject_contains: str = "",
    since_minutes: Optional[int] = None,
    baseline_timestamp: Optional[int] = None,
    claim_token: str | None = None,
) -> Dict[str, Any]:
    """
    创建一个异步探测请求，后台 worker 会定期轮询直到匹配或超时。
    返回 probe_id 供后续查询。
    """
    import uuid

    from outlook_web.db import get_db

    _validate_probe_params(email_addr, timeout_seconds, poll_interval)

    # 检查账号是否存在
    ensure_account_can_read(require_account(email_addr))

    probe_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=int(timeout_seconds))

    db = get_db()
    db.execute(
        """
        INSERT INTO external_probe_cache
            (id, email_addr, folder, from_contains, subject_contains,
             since_minutes, timeout_seconds, poll_interval, status, expires_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
        """,
        (
            probe_id,
            email_addr,
            folder,
            from_contains,
            subject_contains,
            since_minutes,
            int(timeout_seconds),
            int(poll_interval),
            expires_at.isoformat(),
            (datetime.fromtimestamp(int(baseline_timestamp), timezone.utc).isoformat() if baseline_timestamp else now.isoformat()),
            now.isoformat(),
        ),
    )
    db.commit()

    return {
        "probe_id": probe_id,
        "status": "pending",
        "claim_token": str(claim_token or "").strip(),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "poll_url": f"/api/external/probe/{probe_id}",
    }


def get_probe_status(probe_id: str) -> Dict[str, Any]:
    """查询探测状态与结果。"""
    from outlook_web.db import get_db

    if not probe_id:
        raise InvalidParamError("probe_id 不能为空")

    db = get_db()
    row = db.execute("SELECT * FROM external_probe_cache WHERE id = ?", (probe_id,)).fetchone()

    if not row:
        raise MailNotFoundError("探测请求不存在", data={"probe_id": probe_id})

    result: Dict[str, Any] = {
        "probe_id": row["id"],
        "email": row["email_addr"],
        "status": row["status"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
    }

    if row["status"] == "matched" and row["result_json"]:
        try:
            result["message"] = json.loads(row["result_json"])
        except (json.JSONDecodeError, TypeError):
            result["message"] = None
    elif row["status"] == "timeout":
        result["error_code"] = "WAIT_TIMEOUT"
        result["error_message"] = row["error_message"] or "等待超时，未检测到匹配邮件"
    elif row["status"] == "error":
        result["error_code"] = row["error_code"] or "PROBE_ERROR"
        result["error_message"] = row["error_message"] or "探测过程中发生错误"

    return result


def _mark_expired_pending_probes(db: Any, now: str) -> None:
    db.execute(
        """
        UPDATE external_probe_cache
        SET status = 'timeout',
            error_message = '等待超时，未检测到匹配邮件',
            updated_at = ?
        WHERE status = 'pending' AND expires_at <= ?
        """,
        (now, now),
    )
    db.commit()


def _load_pending_probe_rows(db: Any, now: str, *, limit: int = 50) -> list[Any]:
    return db.execute(
        """
        SELECT * FROM external_probe_cache
        WHERE status = 'pending' AND expires_at > ?
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (now, limit),
    ).fetchall()


def _get_probe_baseline_timestamp(row: Any) -> int:
    try:
        created_str = row["created_at"] or ""
        if created_str.endswith("Z"):
            created_str = created_str[:-1] + "+00:00"
        created_dt = datetime.fromisoformat(created_str)
        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=timezone.utc)
        return int(created_dt.timestamp())
    except Exception:
        return int(time.time()) - int(row["timeout_seconds"] or 0)


def _mark_probe_matched(db: Any, probe_id: str, latest: Dict[str, Any], now: str) -> None:
    db.execute(
        """
        UPDATE external_probe_cache
        SET status = 'matched', result_json = ?, updated_at = ?
        WHERE id = ?
        """,
        (json.dumps(latest, ensure_ascii=False), now, probe_id),
    )
    db.commit()


def _mark_probe_error(db: Any, probe_id: str, exc: Exception, now: str) -> None:
    db.execute(
        """
        UPDATE external_probe_cache
        SET status = 'error', error_code = 'PROBE_ERROR',
            error_message = ?, updated_at = ?
        WHERE id = ?
        """,
        (str(exc)[:500], now, probe_id),
    )
    db.commit()


def _poll_single_probe(db: Any, row: Any, now: str) -> None:
    latest = get_latest_message_for_external(
        email_addr=row["email_addr"],
        folder=row["folder"],
        from_contains=row["from_contains"],
        subject_contains=row["subject_contains"],
        since_minutes=row["since_minutes"],
    )
    if int(latest.get("timestamp") or 0) >= _get_probe_baseline_timestamp(row):
        _mark_probe_matched(db, row["id"], latest, now)


def poll_pending_probes(app: Any = None) -> int:
    """
    后台任务：遍历所有 pending 状态的探测请求，执行一轮轮询。
    返回本轮处理的探测数量。
    """
    from outlook_web.db import get_db

    ctx = None
    if app is not None:
        ctx = app.app_context()
        ctx.push()

    try:
        db = get_db()
        now = datetime.now(timezone.utc).isoformat()
        _mark_expired_pending_probes(db, now)
        rows = _load_pending_probe_rows(db, now)

        processed = 0
        for row in rows:
            processed += 1
            try:
                _poll_single_probe(db, row, now)
            except MailNotFoundError:
                continue
            except Exception as exc:
                _mark_probe_error(db, row["id"], exc, now)

        return processed
    finally:
        if ctx is not None:
            ctx.pop()


def cleanup_expired_probes(app: Any = None, max_age_minutes: int = 30) -> int:
    """清理已完成/超时/错误的探测记录（默认清理 30 分钟前的）。"""
    from outlook_web.db import get_db

    ctx = None
    if app is not None:
        ctx = app.app_context()
        ctx.push()

    try:
        db = get_db()
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)).isoformat()
        cursor = db.execute(
            """
            DELETE FROM external_probe_cache
            WHERE status IN ('matched', 'timeout', 'error') AND updated_at < ?
            """,
            (cutoff,),
        )
        db.commit()
        return cursor.rowcount
    finally:
        if ctx is not None:
            ctx.pop()


def audit_external_api_access(
    *,
    action: str,
    email_addr: str,
    endpoint: str,
    status: str,
    details: Dict[str, Any] | None = None,
):
    safe_details: Dict[str, Any] = {"endpoint": endpoint, "status": status}
    consumer = get_current_external_api_consumer()
    if consumer:
        safe_details.update(
            {
                "consumer_id": consumer.get("id"),
                "consumer_key": consumer.get("consumer_key"),
                "consumer_name": consumer.get("name"),
                "consumer_source": consumer.get("source"),
            }
        )
        if consumer.get("allowed_emails"):
            safe_details["consumer_allowed_emails"] = consumer.get("allowed_emails")
    if details:
        # 避免日志中输出敏感信息（如 API Key）
        safe_details.update(details)

    try:
        details_text = json.dumps(safe_details, ensure_ascii=False)
    except Exception:
        details_text = str(safe_details)

    log_audit(action, "external_api", email_addr, details_text)
    try:
        if consumer:
            external_api_keys_repo.record_external_api_consumer_usage(
                consumer_key=str(consumer.get("consumer_key") or ""),
                consumer_name=str(consumer.get("name") or ""),
                endpoint=endpoint,
                status=status,
            )
    except Exception:
        pass
