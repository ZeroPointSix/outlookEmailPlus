"""
邮箱池服务层。

职责：
- 输入校验（caller_id / task_id / project_key / result / detail 等）
- 读取 settings 并驱动仓储层的原子操作
- 统一 provider / email_domain 规则校验
- 提供 claim 上下文读取能力，供外部读信链路复用
"""

from __future__ import annotations

from typing import Optional

from outlook_web.db import create_sqlite_connection
from outlook_web.repositories import pool as pool_repo
from outlook_web.services.providers import (
    KNOWN_PROVIDER_KEYS,
    normalize_email_domain,
    provider_supports_email_domain,
)

CALLER_ID_MAX_LEN = 64
TASK_ID_MAX_LEN = 128
PROJECT_KEY_MAX_LEN = 128
REASON_MAX_LEN = 256
DETAIL_MAX_LEN = 512

VALID_RESULTS = set(pool_repo.RESULT_TO_POOL_STATUS.keys())


class PoolServiceError(Exception):
    """业务错误，包含 HTTP 状态码和错误码。"""

    def __init__(self, message: str, error_code: str, http_status: int = 400):
        super().__init__(message)
        self.error_code = error_code
        self.http_status = http_status


def _validate_consumer_key(consumer_key: str) -> str:
    normalized = str(consumer_key or "").strip()
    if not normalized:
        raise PoolServiceError("consumer_key 不能为空", "consumer_key_empty", http_status=403)
    return normalized


def _validate_project_key(project_key: str) -> str:
    normalized = str(project_key or "").strip()
    if not normalized:
        raise PoolServiceError("project_key 不能为空", "project_key_empty")
    if len(normalized) > PROJECT_KEY_MAX_LEN:
        raise PoolServiceError(f"project_key 超过最大长度 {PROJECT_KEY_MAX_LEN}", "project_key_too_long")
    return normalized


def _validate_caller_id(caller_id: str) -> str:
    normalized = str(caller_id or "").strip()
    if not normalized:
        raise PoolServiceError("caller_id 不能为空", "caller_id_empty")
    if len(normalized) > CALLER_ID_MAX_LEN:
        raise PoolServiceError(f"caller_id 超过最大长度 {CALLER_ID_MAX_LEN}", "caller_id_too_long")
    return normalized


def _validate_task_id(task_id: str) -> str:
    normalized = str(task_id or "").strip()
    if not normalized:
        raise PoolServiceError("task_id 不能为空", "task_id_empty")
    if len(normalized) > TASK_ID_MAX_LEN:
        raise PoolServiceError(f"task_id 超过最大长度 {TASK_ID_MAX_LEN}", "task_id_too_long")
    return normalized


def _validate_lease_seconds(lease_seconds: int, max_lease: int = 3600) -> None:
    if lease_seconds <= 0:
        raise PoolServiceError("lease_seconds 必须大于 0", "lease_seconds_invalid")
    if lease_seconds > max_lease:
        raise PoolServiceError(f"lease_seconds 不能超过 {max_lease} 秒", "lease_seconds_too_large")


def _normalize_provider(provider: Optional[str]) -> str:
    normalized = str(provider or "").strip().lower()
    if normalized and normalized not in KNOWN_PROVIDER_KEYS:
        raise PoolServiceError("provider 参数无效", "invalid_provider")
    return normalized


def _normalize_email_domain(provider: str, email_domain: Optional[str]) -> str:
    normalized_domain = normalize_email_domain(email_domain)
    if not normalized_domain:
        return ""
    if not provider:
        raise PoolServiceError("email_domain 需要配合 provider 使用", "email_domain_requires_provider")
    if not provider_supports_email_domain(provider, normalized_domain):
        raise PoolServiceError("provider 与 email_domain 不匹配", "provider_email_domain_mismatch")
    return normalized_domain


def _read_settings_via_conn(conn) -> dict:
    rows = conn.execute(
        "SELECT key, value FROM settings WHERE key IN (?, ?)",
        ("pool_cooldown_seconds", "pool_default_lease_seconds"),
    ).fetchall()
    result = {"pool_cooldown_seconds": 86400, "pool_default_lease_seconds": 600}
    for row in rows:
        try:
            result[row["key"]] = int(row["value"])
        except (TypeError, ValueError):
            pass
    return result


def _load_claim_row(conn, account_id: int):
    return conn.execute(
        """
        SELECT id, claim_token, claimed_by, pool_status
        FROM accounts
        WHERE id = ?
        """,
        (account_id,),
    ).fetchone()


def _validate_claim_record(
    *,
    row,
    claim_token: str,
    consumer_key: str,
    project_key: str,
    caller_id: str,
    task_id: str,
    operation: str,
) -> None:
    if row is None:
        raise PoolServiceError("账号不存在", "account_not_found", http_status=400)
    if row["pool_status"] != "claimed":
        raise PoolServiceError(
            f"账号当前状态为 '{row['pool_status']}'，无法 {operation}",
            "not_claimed",
            http_status=409,
        )
    if row["claim_token"] != claim_token:
        raise PoolServiceError("claim_token 不匹配", "token_mismatch", http_status=403)

    claimed_context = pool_repo.parse_claimed_by(row["claimed_by"])
    if claimed_context["consumer_key"] and claimed_context["consumer_key"] != consumer_key:
        raise PoolServiceError("consumer_key 与领取记录不一致", "consumer_mismatch", http_status=403)
    if claimed_context["project_key"] and claimed_context["project_key"] != project_key:
        raise PoolServiceError("project_key 与领取记录不一致", "project_mismatch", http_status=403)
    if claimed_context["caller_id"] != caller_id:
        raise PoolServiceError("caller_id 与领取记录不一致", "caller_mismatch", http_status=403)
    if claimed_context["task_id"] != task_id:
        raise PoolServiceError("task_id 与领取记录不一致", "task_mismatch", http_status=403)


def claim_random(
    *,
    consumer_key: str,
    project_key: str,
    caller_id: str,
    task_id: str,
    provider: Optional[str] = None,
    email_domain: Optional[str] = None,
) -> dict:
    consumer_key = _validate_consumer_key(consumer_key)
    project_key = _validate_project_key(project_key)
    caller_id = _validate_caller_id(caller_id)
    task_id = _validate_task_id(task_id)
    provider_key = _normalize_provider(provider)
    normalized_domain = _normalize_email_domain(provider_key, email_domain)

    conn = create_sqlite_connection()
    try:
        settings = _read_settings_via_conn(conn)
        default_lease = settings["pool_default_lease_seconds"]
        _validate_lease_seconds(default_lease)

        account = pool_repo.claim_atomic(
            conn,
            consumer_key=consumer_key,
            project_key=project_key,
            caller_id=caller_id,
            task_id=task_id,
            lease_seconds=default_lease,
            provider=provider_key or None,
            email_domain=normalized_domain or None,
        )
        if account is None:
            raise PoolServiceError("池中没有符合条件的可用邮箱", "no_available_account", http_status=200)
        return account
    finally:
        conn.close()


def release_claim(
    *,
    consumer_key: str,
    project_key: str,
    account_id: int,
    claim_token: str,
    caller_id: str,
    task_id: str,
    reason: Optional[str] = None,
) -> None:
    consumer_key = _validate_consumer_key(consumer_key)
    project_key = _validate_project_key(project_key)
    caller_id = _validate_caller_id(caller_id)
    task_id = _validate_task_id(task_id)
    normalized_token = str(claim_token or "").strip()
    if not normalized_token:
        raise PoolServiceError("claim_token 不能为空", "claim_token_empty")
    if reason and len(reason) > REASON_MAX_LEN:
        raise PoolServiceError(f"reason 超过最大长度 {REASON_MAX_LEN}", "reason_too_long")

    conn = create_sqlite_connection()
    try:
        row = _load_claim_row(conn, account_id)
        _validate_claim_record(
            row=row,
            claim_token=normalized_token,
            consumer_key=consumer_key,
            project_key=project_key,
            caller_id=caller_id,
            task_id=task_id,
            operation="release",
        )
        pool_repo.release(
            conn,
            account_id=account_id,
            claim_token=normalized_token,
            consumer_key=consumer_key,
            project_key=project_key,
            caller_id=caller_id,
            task_id=task_id,
            reason=reason,
        )
    finally:
        conn.close()


def complete_claim(
    *,
    consumer_key: str,
    project_key: str,
    account_id: int,
    claim_token: str,
    caller_id: str,
    task_id: str,
    result: str,
    detail: Optional[str] = None,
) -> str:
    consumer_key = _validate_consumer_key(consumer_key)
    project_key = _validate_project_key(project_key)
    caller_id = _validate_caller_id(caller_id)
    task_id = _validate_task_id(task_id)
    normalized_token = str(claim_token or "").strip()
    if not normalized_token:
        raise PoolServiceError("claim_token 不能为空", "claim_token_empty")
    if result not in VALID_RESULTS:
        raise PoolServiceError(f"result 必须是 {sorted(VALID_RESULTS)} 之一", "invalid_result")
    if detail and len(detail) > DETAIL_MAX_LEN:
        raise PoolServiceError(f"detail 超过最大长度 {DETAIL_MAX_LEN}", "detail_too_long")

    conn = create_sqlite_connection()
    try:
        row = _load_claim_row(conn, account_id)
        _validate_claim_record(
            row=row,
            claim_token=normalized_token,
            consumer_key=consumer_key,
            project_key=project_key,
            caller_id=caller_id,
            task_id=task_id,
            operation="complete",
        )
        return pool_repo.complete(
            conn,
            account_id=account_id,
            claim_token=normalized_token,
            consumer_key=consumer_key,
            project_key=project_key,
            caller_id=caller_id,
            task_id=task_id,
            result=result,
            detail=detail,
        )
    finally:
        conn.close()


def get_claim_context(*, claim_token: str) -> dict:
    normalized_token = str(claim_token or "").strip()
    if not normalized_token:
        raise PoolServiceError("claim_token 不能为空", "claim_token_empty")

    conn = create_sqlite_connection()
    try:
        claim_context = pool_repo.get_claim_context_by_token(conn, normalized_token)
        if claim_context is None:
            raise PoolServiceError("claim_token 不存在或已失效", "claim_token_not_found", http_status=404)
        return claim_context
    finally:
        conn.close()


def append_claim_read_context(*, claim_token: str, action: str, payload: dict) -> None:
    normalized_token = str(claim_token or "").strip()
    if not normalized_token:
        return

    conn = create_sqlite_connection()
    try:
        pool_repo.append_claim_read_context(
            conn,
            claim_token=normalized_token,
            action=action,
            payload=payload,
        )
    finally:
        conn.close()


def get_pool_stats() -> dict:
    conn = create_sqlite_connection()
    try:
        return pool_repo.get_stats(conn)
    finally:
        conn.close()
