from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

RESULT_TO_POOL_STATUS: Dict[str, str] = {
    "success": "used",
    "verification_timeout": "cooldown",
    "provider_blocked": "frozen",
    "credential_invalid": "retired",
    "network_error": "available",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_claimed_by(claimed_by: Optional[str]) -> tuple[str, str]:
    """从 claimed_by 字段解析 caller_id 和 task_id（兼容旧格式）。"""
    if not claimed_by:
        return "", ""
    parts = (claimed_by or ":").split(":", 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def claim_atomic(
    conn: sqlite3.Connection,
    caller_id: str,
    task_id: str,
    lease_seconds: int,
    provider: Optional[str] = None,
    group_id: Optional[int] = None,
    tags: Optional[List[str]] = None,
    exclude_recent_minutes: Optional[int] = None,
    project_key: Optional[str] = None,
    email_domain: Optional[str] = None,
) -> Optional[dict]:
    sql = """
        SELECT a.* FROM accounts a
        WHERE a.pool_status = 'available'
        AND a.status = 'active'
    """
    params: list = []

    if provider:
        sql += " AND a.provider = ?"
        params.append(provider)

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
        cutoff = (
            _utcnow() - timedelta(minutes=exclude_recent_minutes)
        ).isoformat() + "Z"
        sql += " AND (a.last_claimed_at IS NULL OR a.last_claimed_at < ?)"
        params.append(cutoff)

    # PR#27: email_domain 过滤
    if email_domain:
        sql += " AND a.email_domain = ? COLLATE NOCASE"
        params.append(email_domain.strip().lower())

    # PR#27: project_key 防止同项目复用已用账号
    if project_key and caller_id:
        sql += """
            AND NOT EXISTS (
                SELECT 1 FROM account_project_usage apu
                WHERE apu.account_id = a.id
                  AND apu.consumer_key = ?
                  AND apu.project_key = ?
            )
        """
        params.append(caller_id)
        params.append(project_key)

    sql += " ORDER BY RANDOM() LIMIT 1"

    conn.execute("BEGIN IMMEDIATE")
    account = conn.execute(sql, params).fetchone()

    if account is None:
        conn.execute("ROLLBACK")
        return None

    now_str = _utcnow().isoformat() + "Z"
    lease_expires_at_str = (
        _utcnow() + timedelta(seconds=lease_seconds)
    ).isoformat() + "Z"
    token = "clm_" + secrets.token_urlsafe(9)

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
            f"{caller_id}:{task_id}",
            now_str,
            lease_expires_at_str,
            token,
            now_str,
            now_str,
            account["id"],
        ),
    )
    conn.execute(
        """
        INSERT INTO account_claim_logs
            (account_id, claim_token, caller_id, task_id, action, result, detail, created_at)
        VALUES (?, ?, ?, ?, 'claim', NULL, NULL, ?)
        """,
        (account["id"], token, caller_id, task_id, now_str),
    )

    # PR#27: 记录 project 维度使用（project_key 存在时）
    if project_key and caller_id:
        conn.execute(
            """
            INSERT INTO account_project_usage
                (account_id, consumer_key, project_key, first_claimed_at, last_claimed_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(account_id, consumer_key, project_key)
            DO UPDATE SET last_claimed_at = excluded.last_claimed_at
            """,
            (account["id"], caller_id, project_key, now_str, now_str),
        )

    conn.execute("COMMIT")
    return dict(account) | {
        "claim_token": token,
        "lease_expires_at": lease_expires_at_str,
        "claimed_at": now_str,
    }


def get_claim_context(
    conn: sqlite3.Connection,
    claim_token: str,
) -> Optional[dict]:
    """
    根据 claim_token 查询 claimed_at 时间戳（用作邮件读取的 baseline）。
    返回包含 account_id / email / claimed_at / email_domain 的 dict，或 None。
    """
    row = conn.execute(
        """
        SELECT id, email, claimed_at, email_domain, pool_status
        FROM accounts
        WHERE claim_token = ?
        """,
        (claim_token,),
    ).fetchone()
    if row is None:
        return None
    return {
        "account_id": row["id"],
        "email": row["email"],
        "claimed_at": row["claimed_at"] or "",
        "email_domain": row["email_domain"] or "",
        "pool_status": row["pool_status"] or "",
    }


def append_claim_read_context(
    conn: sqlite3.Connection,
    account_id: int,
    claim_token: str,
    caller_id: str,
    task_id: str,
    detail: Optional[str] = None,
) -> None:
    """
    追加一条 'read' 动作的 claim log（用于记录邮件读取行为）。
    使用 BEGIN IMMEDIATE 事务，与 pool.py 其他写操作保持一致。
    """
    now_str = _utcnow().isoformat() + "Z"
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        """
        INSERT INTO account_claim_logs
            (account_id, claim_token, caller_id, task_id, action, result, detail, created_at)
        VALUES (?, ?, ?, ?, 'read', NULL, ?, ?)
        """,
        (account_id, claim_token, caller_id, task_id, detail, now_str),
    )
    conn.execute("COMMIT")


def release(
    conn: sqlite3.Connection,
    account_id: int,
    claim_token: str,
    caller_id: str,
    task_id: str,
    reason: Optional[str],
) -> None:
    now_str = _utcnow().isoformat() + "Z"
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
    # Bug #28 fix: release 意味着本次领取被放弃（未成功注册），
    # 需要同步清理 account_project_usage 里该账号由此 caller 产生的记录，
    # 否则下次使用相同 project_key 的 claim-random 会被 NOT EXISTS 子查询错误排除。
    conn.execute(
        """
        DELETE FROM account_project_usage
        WHERE account_id = ? AND consumer_key = ?
        """,
        (account_id, caller_id),
    )
    conn.execute(
        """
        INSERT INTO account_claim_logs
            (account_id, claim_token, caller_id, task_id, action, result, detail, created_at)
        VALUES (?, ?, ?, ?, 'release', 'manual_release', ?, ?)
        """,
        (account_id, claim_token, caller_id, task_id, reason, now_str),
    )
    conn.execute("COMMIT")


def complete(
    conn: sqlite3.Connection,
    account_id: int,
    claim_token: str,
    caller_id: str,
    task_id: str,
    result: str,
    detail: Optional[str],
) -> str:
    new_pool_status = RESULT_TO_POOL_STATUS[result]
    is_success = result == "success"
    now_str = _utcnow().isoformat() + "Z"

    conn.execute("BEGIN IMMEDIATE")
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
    conn.execute(
        """
        INSERT INTO account_claim_logs
            (account_id, claim_token, caller_id, task_id, action, result, detail, created_at)
        VALUES (?, ?, ?, ?, 'complete', ?, ?, ?)
        """,
        (account_id, claim_token, caller_id, task_id, result, detail, now_str),
    )
    conn.execute("COMMIT")
    return new_pool_status


def expire_stale_claims(conn: sqlite3.Connection) -> int:
    now_str = _utcnow().isoformat() + "Z"
    expired = conn.execute(
        """
        SELECT id, claim_token, claimed_by FROM accounts
        WHERE pool_status = 'claimed' AND lease_expires_at < ?
        """,
        (now_str,),
    ).fetchall()

    for account in expired:
        caller_id, task_id = _parse_claimed_by(account["claimed_by"])

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
        conn.execute(
            """
            INSERT INTO account_claim_logs
                (account_id, claim_token, caller_id, task_id, action, result, detail, created_at)
            VALUES (?, ?, ?, ?, 'expire', 'lease_expired', 'lease timeout, auto moved to cooldown', ?)
            """,
            (account["id"], account["claim_token"], caller_id, task_id, now_str),
        )
        conn.execute("COMMIT")

    return len(expired)


def recover_cooldown(conn: sqlite3.Connection, cooldown_seconds: int) -> int:
    cutoff_str = (_utcnow() - timedelta(seconds=cooldown_seconds)).isoformat() + "Z"
    now_str = _utcnow().isoformat() + "Z"
    cursor = conn.execute(
        """
        UPDATE accounts SET pool_status = 'available', updated_at = ?
        WHERE pool_status = 'cooldown' AND updated_at < ?
        """,
        (now_str, cutoff_str),
    )
    conn.commit()
    return cursor.rowcount


def get_stats(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("""
        SELECT pool_status, COUNT(*) as cnt FROM accounts
        GROUP BY pool_status
        """).fetchall()
    pool_counts: dict = {
        "available": 0,
        "claimed": 0,
        "used": 0,
        "cooldown": 0,
        "frozen": 0,
        "retired": 0,
    }
    for row in rows:
        # external API 只暴露池内状态；NULL/池外账号不应出现在契约里。
        key = row["pool_status"]
        if key in pool_counts:
            pool_counts[key] = row["cnt"]

    return {"pool_counts": pool_counts}
