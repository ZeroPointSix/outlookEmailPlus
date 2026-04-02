from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from outlook_web.services.providers import extract_email_domain

RESULT_TO_POOL_STATUS: Dict[str, str] = {
    "success": "cooldown",
    "verification_timeout": "cooldown",
    "provider_blocked": "frozen",
    "credential_invalid": "retired",
    "network_error": "available",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso_now() -> str:
    return _utcnow().isoformat() + "Z"


def _build_claimed_by(*, consumer_key: str, project_key: str, caller_id: str, task_id: str) -> str:
    return "||".join([consumer_key, project_key, caller_id, task_id])


def parse_claimed_by(claimed_by: str | None) -> dict:
    parts = str(claimed_by or "").split("||")
    if len(parts) == 4:
        return {
            "consumer_key": parts[0],
            "project_key": parts[1],
            "caller_id": parts[2],
            "task_id": parts[3],
        }

    legacy_parts = str(claimed_by or ":").split(":", 1)
    caller_id = legacy_parts[0]
    task_id = legacy_parts[1] if len(legacy_parts) > 1 else ""
    return {
        "consumer_key": "",
        "project_key": "",
        "caller_id": caller_id,
        "task_id": task_id,
    }


def _write_claim_log(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    claim_token: str,
    consumer_key: str,
    project_key: str,
    caller_id: str,
    task_id: str,
    action: str,
    result: str | None,
    detail: str | None,
    claim_read_context: dict | None = None,
    created_at: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO account_claim_logs (
            account_id, claim_token, consumer_key, project_key,
            caller_id, task_id, action, result, detail, claim_read_context, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            claim_token,
            consumer_key,
            project_key,
            caller_id,
            task_id,
            action,
            result,
            detail,
            json.dumps(claim_read_context, ensure_ascii=False) if claim_read_context else None,
            created_at or _iso_now(),
        ),
    )


def _normalized_email_domain_from_row(row) -> str:
    return str(row["email_domain"] or "").strip().lower() or extract_email_domain(row["email"] or "")


def claim_atomic(
    conn: sqlite3.Connection,
    *,
    consumer_key: str,
    project_key: str,
    caller_id: str,
    task_id: str,
    lease_seconds: int,
    provider: Optional[str] = None,
    email_domain: Optional[str] = None,
    group_id: Optional[int] = None,
    tags: Optional[List[str]] = None,
    exclude_recent_minutes: Optional[int] = None,
) -> Optional[dict]:
    sql = """
        SELECT a.* FROM accounts a
        WHERE a.pool_status = 'available'
        AND a.status = 'active'
        AND NOT EXISTS (
            SELECT 1
            FROM account_project_usage apu
            WHERE apu.account_id = a.id
              AND apu.consumer_key = ?
              AND apu.project_key = ?
        )
    """
    params: list = [consumer_key, project_key]

    if provider:
        sql += " AND a.provider = ?"
        params.append(provider)

    if email_domain:
        sql += " AND a.email_domain = ?"
        params.append(email_domain)

    if group_id is not None:
        sql += " AND a.group_id = ?"
        params.append(group_id)

    if tags:
        for tag_name in tags:
            sql += """
                AND EXISTS (
                    SELECT 1 FROM account_tags at2
                    JOIN tags t2 ON at2.tag_id = t2.id
                    WHERE at2.account_id = a.id AND t2.name = ?
                )
            """
            params.append(tag_name)

    if exclude_recent_minutes and exclude_recent_minutes > 0:
        cutoff = (_utcnow() - timedelta(minutes=exclude_recent_minutes)).isoformat() + "Z"
        sql += " AND (a.last_claimed_at IS NULL OR a.last_claimed_at < ?)"
        params.append(cutoff)

    sql += " ORDER BY RANDOM() LIMIT 1"

    conn.execute("BEGIN IMMEDIATE")
    account = conn.execute(sql, params).fetchone()
    if account is None:
        conn.execute("ROLLBACK")
        return None

    now_str = _iso_now()
    lease_expires_at_str = (_utcnow() + timedelta(seconds=lease_seconds)).isoformat() + "Z"
    token = "clm_" + secrets.token_urlsafe(9)
    claimed_by = _build_claimed_by(
        consumer_key=consumer_key,
        project_key=project_key,
        caller_id=caller_id,
        task_id=task_id,
    )

    conn.execute(
        """
        UPDATE accounts SET
            pool_status = 'claimed',
            claimed_by = ?,
            claimed_at = ?,
            lease_expires_at = ?,
            claim_token = ?,
            last_claimed_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            claimed_by,
            now_str,
            lease_expires_at_str,
            token,
            now_str,
            now_str,
            account["id"],
        ),
    )
    _write_claim_log(
        conn,
        account_id=account["id"],
        claim_token=token,
        consumer_key=consumer_key,
        project_key=project_key,
        caller_id=caller_id,
        task_id=task_id,
        action="claim",
        result=None,
        detail=None,
        claim_read_context={
            "email": account["email"],
            "email_domain": _normalized_email_domain_from_row(account),
            "provider": account["provider"] or "",
            "claimed_at": now_str,
        },
        created_at=now_str,
    )
    conn.execute("COMMIT")
    return dict(account) | {
        "email_domain": _normalized_email_domain_from_row(account),
        "claim_token": token,
        "lease_expires_at": lease_expires_at_str,
        "claimed_at": now_str,
    }


def release(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    claim_token: str,
    consumer_key: str,
    project_key: str,
    caller_id: str,
    task_id: str,
    reason: Optional[str],
) -> None:
    now_str = _iso_now()
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        """
        UPDATE accounts SET
            pool_status = 'available',
            claimed_by = NULL,
            claimed_at = NULL,
            lease_expires_at = NULL,
            claim_token = NULL,
            updated_at = ?
        WHERE id = ?
        """,
        (now_str, account_id),
    )
    _write_claim_log(
        conn,
        account_id=account_id,
        claim_token=claim_token,
        consumer_key=consumer_key,
        project_key=project_key,
        caller_id=caller_id,
        task_id=task_id,
        action="release",
        result="manual_release",
        detail=reason,
        created_at=now_str,
    )
    conn.execute("COMMIT")


def complete(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    claim_token: str,
    consumer_key: str,
    project_key: str,
    caller_id: str,
    task_id: str,
    result: str,
    detail: Optional[str],
) -> str:
    new_pool_status = RESULT_TO_POOL_STATUS[result]
    is_success = result == "success"
    now_str = _iso_now()

    conn.execute("BEGIN IMMEDIATE")
    if is_success:
        conn.execute(
            """
            INSERT OR IGNORE INTO account_project_usage (
                account_id, consumer_key, project_key, created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (account_id, consumer_key, project_key, now_str),
        )

    conn.execute(
        """
        UPDATE accounts SET
            pool_status = ?,
            claimed_by = NULL,
            claimed_at = NULL,
            lease_expires_at = NULL,
            claim_token = NULL,
            last_result = ?,
            last_result_detail = ?,
            success_count = success_count + ?,
            fail_count = fail_count + ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            new_pool_status,
            result,
            detail,
            1 if is_success else 0,
            0 if is_success else 1,
            now_str,
            account_id,
        ),
    )
    _write_claim_log(
        conn,
        account_id=account_id,
        claim_token=claim_token,
        consumer_key=consumer_key,
        project_key=project_key,
        caller_id=caller_id,
        task_id=task_id,
        action="complete",
        result=result,
        detail=detail,
        created_at=now_str,
    )
    conn.execute("COMMIT")
    return new_pool_status


def expire_stale_claims(conn: sqlite3.Connection) -> int:
    now_str = _iso_now()
    expired = conn.execute(
        """
        SELECT id, claim_token, claimed_by
        FROM accounts
        WHERE pool_status = 'claimed' AND lease_expires_at < ?
        """,
        (now_str,),
    ).fetchall()

    for account in expired:
        claimed_context = parse_claimed_by(account["claimed_by"])
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            UPDATE accounts SET
                pool_status = 'cooldown',
                claimed_by = NULL,
                claimed_at = NULL,
                lease_expires_at = NULL,
                claim_token = NULL,
                fail_count = fail_count + 1,
                last_result = 'lease_expired',
                updated_at = ?
            WHERE id = ?
            """,
            (now_str, account["id"]),
        )
        _write_claim_log(
            conn,
            account_id=account["id"],
            claim_token=account["claim_token"],
            consumer_key=claimed_context["consumer_key"],
            project_key=claimed_context["project_key"],
            caller_id=claimed_context["caller_id"],
            task_id=claimed_context["task_id"],
            action="expire",
            result="lease_expired",
            detail="lease timeout, auto moved to cooldown",
            created_at=now_str,
        )
        conn.execute("COMMIT")

    return len(expired)


def recover_cooldown(conn: sqlite3.Connection, cooldown_seconds: int) -> int:
    cutoff_str = (_utcnow() - timedelta(seconds=cooldown_seconds)).isoformat() + "Z"
    now_str = _iso_now()
    cursor = conn.execute(
        """
        UPDATE accounts SET pool_status = 'available', updated_at = ?
        WHERE pool_status = 'cooldown' AND updated_at < ?
        """,
        (now_str, cutoff_str),
    )
    conn.commit()
    return cursor.rowcount


def get_claim_context_by_token(conn: sqlite3.Connection, claim_token: str) -> Optional[dict]:
    row = conn.execute(
        """
        SELECT
            a.id,
            a.email,
            a.email_domain,
            a.provider,
            a.claim_token,
            a.claimed_at,
            a.claimed_by,
            a.pool_status
        FROM accounts a
        WHERE a.claim_token = ?
        """,
        (claim_token,),
    ).fetchone()
    if row is None:
        return None

    claimed_context = parse_claimed_by(row["claimed_by"])
    return {
        "account_id": row["id"],
        "email": row["email"],
        "email_domain": _normalized_email_domain_from_row(row),
        "provider": row["provider"] or "",
        "claim_token": row["claim_token"],
        "claimed_at": row["claimed_at"] or "",
        "pool_status": row["pool_status"] or "",
        "consumer_key": claimed_context["consumer_key"],
        "project_key": claimed_context["project_key"],
        "caller_id": claimed_context["caller_id"],
        "task_id": claimed_context["task_id"],
    }


def get_project_usage(conn: sqlite3.Connection, *, account_id: int, consumer_key: str, project_key: str) -> Optional[dict]:
    row = conn.execute(
        """
        SELECT account_id, consumer_key, project_key, created_at
        FROM account_project_usage
        WHERE account_id = ? AND consumer_key = ? AND project_key = ?
        """,
        (account_id, consumer_key, project_key),
    ).fetchone()
    return dict(row) if row is not None else None


def append_claim_read_context(
    conn: sqlite3.Connection,
    *,
    claim_token: str,
    action: str,
    payload: dict,
) -> None:
    row = conn.execute(
        """
        SELECT id, claim_read_context
        FROM account_claim_logs
        WHERE claim_token = ? AND action = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (claim_token, action),
    ).fetchone()
    if row is None:
        return

    merged_payload = {}
    raw_context = row["claim_read_context"]
    if raw_context:
        try:
            existing = json.loads(raw_context)
            if isinstance(existing, dict):
                merged_payload.update(existing)
        except Exception:
            pass
    merged_payload.update(payload)

    conn.execute(
        "UPDATE account_claim_logs SET claim_read_context = ? WHERE id = ?",
        (json.dumps(merged_payload, ensure_ascii=False), row["id"]),
    )
    conn.commit()


def get_stats(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """
        SELECT pool_status, COUNT(*) as cnt FROM accounts
        GROUP BY pool_status
        """
    ).fetchall()
    pool_counts: dict = {
        "available": 0,
        "claimed": 0,
        "used": 0,
        "cooldown": 0,
        "frozen": 0,
        "retired": 0,
    }
    for row in rows:
        key = row["pool_status"]
        if key in pool_counts:
            pool_counts[key] = row["cnt"]

    return {"pool_counts": pool_counts}
