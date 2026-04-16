from __future__ import annotations

import json
import logging
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 邮箱池 Repository 层 — 邮箱领取/释放/完成的核心原子操作
#
# 业务背景:
#   - PRD: docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md (项目维度成功复用)
#   - PRD: docs/PRD/2026-04-09-CF临时邮箱接入邮箱池PRD.md (CF 临时邮箱)
#
# 设计决策:
#   - FD: docs/FD/2026-04-16-邮箱池项目维度成功复用FD.md
#   - 同 caller+project 只防 success，不防失败/release/expire（FD §2.2）
#   - success_count > 0 是 claim 排除的唯一门控（TDD §4.1 N-02）

RESULT_TO_POOL_STATUS: Dict[str, str] = {
    "success": "used",
    "verification_timeout": "cooldown",
    "provider_blocked": "frozen",
    "credential_invalid": "retired",
    "network_error": "available",
}


class PoolRepositoryError(Exception):
    """Repository 层业务错误，包含错误码。"""

    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.error_code = error_code


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_claimed_by(claimed_by: Optional[str]) -> tuple[str, str]:
    """从 claimed_by 字段解析 caller_id 和 task_id（兼容旧格式）。"""
    if not claimed_by:
        return "", ""
    parts = (claimed_by or ":").split(":", 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def insert_claimed_account(
    conn: sqlite3.Connection,
    *,
    email: str,
    caller_id: str,
    task_id: str,
    lease_seconds: int,
    provider: str,
    account_type: str = "temp_mail",
    project_key: Optional[str] = None,
    temp_mail_meta: Optional[dict] = None,
    claim_log_detail: str = "动态创建",
) -> dict:
    """插入一个新账号并直接标记为 claimed（供 Service 层动态创建邮箱后写入池）。

    - Repository 层不允许依赖 services，因此这里仅做 DB 写入，不做任何上游网络调用。
    - 该函数内部包含 BEGIN IMMEDIATE / COMMIT。
    """

    normalized_email = str(email or "").strip()
    if not normalized_email:
        raise PoolRepositoryError("email 不能为空", "invalid_email")

    # 提取 email_domain
    extracted_domain = ""
    if "@" in normalized_email:
        extracted_domain = normalized_email.split("@", 1)[1].strip().lower()

    # 生成 claim_token
    now_str = _utcnow().isoformat() + "Z"
    lease_expires_at_str = (_utcnow() + timedelta(seconds=lease_seconds)).isoformat() + "Z"
    token = "clm_" + secrets.token_urlsafe(9)

    # 序列化 meta（明文 JSON）
    meta_obj = temp_mail_meta or {}
    if isinstance(meta_obj, str):
        temp_mail_meta_json = meta_obj
    else:
        temp_mail_meta_json = json.dumps(meta_obj, ensure_ascii=False) if meta_obj else "{}"

    try:
        conn.execute("BEGIN IMMEDIATE")

        cursor = conn.execute(
            """
            INSERT INTO accounts (
                email, password, client_id, refresh_token,
                account_type, provider, status,
                pool_status, claimed_by, claimed_at, lease_expires_at, claim_token,
                claimed_project_key, last_claimed_at, temp_mail_meta, email_domain,
                created_at, updated_at
            ) VALUES (?, '', '', '',
                      ?, ?, 'active',
                      'claimed', ?, ?, ?, ?,
                      ?, ?, ?, ?,
                      ?, ?)
            """,
            (
                normalized_email,
                account_type,
                provider,
                f"{caller_id}:{task_id}",
                now_str,
                lease_expires_at_str,
                token,
                project_key,
                now_str,
                temp_mail_meta_json,
                extracted_domain,
                now_str,
                now_str,
            ),
        )
        account_id = cursor.lastrowid

        conn.execute(
            """
            INSERT INTO account_claim_logs
                (account_id, claim_token, caller_id, task_id, action, result, detail, created_at)
            VALUES (?, ?, ?, ?, 'claim', NULL, ?, ?)
            """,
            (account_id, token, caller_id, task_id, claim_log_detail, now_str),
        )

        # project_key 存在时写入 project usage
        if project_key and caller_id:
            conn.execute(
                """
                INSERT INTO account_project_usage
                    (account_id, consumer_key, project_key, first_claimed_at, last_claimed_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(account_id, consumer_key, project_key)
                DO UPDATE SET last_claimed_at = excluded.last_claimed_at
                """,
                (account_id, caller_id, project_key, now_str, now_str),
            )

        conn.execute("COMMIT")

        logger.info(
            "[pool] 动态插入账号并 claim: %s (provider=%s, account_id=%s)",
            normalized_email,
            provider,
            account_id,
        )

        return {
            "id": account_id,
            "email": normalized_email,
            "provider": provider,
            "account_type": account_type,
            "pool_status": "claimed",
            "claim_token": token,
            "claimed_at": now_str,
            "lease_expires_at": lease_expires_at_str,
            "temp_mail_meta": temp_mail_meta_json,
            "email_domain": extracted_domain,
        }
    except sqlite3.IntegrityError as e:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise PoolRepositoryError(f"插入账号失败: {e}", "db_integrity_error") from e
    except Exception as e:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise PoolRepositoryError(f"插入账号失败: {e}", "db_error") from e


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
        cutoff = (_utcnow() - timedelta(minutes=exclude_recent_minutes)).isoformat() + "Z"
        sql += " AND (a.last_claimed_at IS NULL OR a.last_claimed_at < ?)"
        params.append(cutoff)

    # PR#27: email_domain 过滤
    if email_domain:
        sql += " AND a.email_domain = ? COLLATE NOCASE"
        params.append(email_domain.strip().lower())

    # PR#27 + v22 语义变更: project_key 防同项目复用
    # v22 前：NOT EXISTS 即排除（含 claim trace），导致 release 后需删 usage 行（Bug #28）
    # v22 后：只排除 success_count > 0 的记录，release/expire 产生的 trace 不阻断再次领取
    if project_key and caller_id:
        sql += """
            AND NOT EXISTS (
                SELECT 1 FROM account_project_usage apu
                WHERE apu.account_id = a.id
                  AND apu.consumer_key = ?
                  AND apu.project_key = ?
                  AND apu.success_count > 0
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
    lease_expires_at_str = (_utcnow() + timedelta(seconds=lease_seconds)).isoformat() + "Z"
    token = "clm_" + secrets.token_urlsafe(9)

    conn.execute(
        """
        UPDATE accounts SET
            pool_status = 'claimed',
            claimed_by = ?,
            claimed_at = ?,
            lease_expires_at = ?,
            claim_token = ?,
            claimed_project_key = ?,
            last_claimed_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            f"{caller_id}:{task_id}",
            now_str,
            lease_expires_at_str,
            token,
            project_key,
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
    """释放已领取的账号，恢复为 available。

    v22 语义变更 (FD §2.2): release 不再删除 account_project_usage 记录。
    旧逻辑（Bug #28 fix）通过 DELETE 防止同 project 二次 claim 被排除，
    但 v22 改用 success_count > 0 门控后，未成功的 usage 行天然不会阻断，无需清理。
    仅清除 accounts.claimed_project_key，让 complete 阶段无法走复用路径。
    """
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
            claimed_project_key = NULL,
            updated_at = ?
        WHERE id = ?
        """,
        (now_str, account_id),
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
    *,
    claimed_project_key: Optional[str] = None,
    enable_project_reuse: Optional[bool] = None,
) -> str:
    """完成领取流程，根据结果更新池状态。

    v22 新增项目复用路径 (FD §2.3):
    - 当 enable_project_reuse=True 且 claimed_project_key 非空且 result='success' 时，
      pool_status 回 'available'（而非旧语义的 'used'），同时写入/更新 success 记录。
    - 旧路径（无 project_key 或非长期邮箱）行为不变：success → used。
    - enable_project_reuse 由 Service 层根据 _is_project_reuse_eligible_account 判定后传入。
    """
    # 读取 claim 时写入的 claimed_project_key 作为复用路径的自动判定依据
    # 即使 API 层未传 project_key，只要 claim 时带了就能正确走复用路径（TDD §4.1 N-03）
    current_row = conn.execute(
        "SELECT claimed_project_key FROM accounts WHERE id = ?",
        (account_id,),
    ).fetchone()
    if current_row is None:
        raise PoolRepositoryError("账号不存在", "account_not_found")

    effective_claimed_project_key = claimed_project_key
    if effective_claimed_project_key is None:
        effective_claimed_project_key = current_row["claimed_project_key"]
    effective_claimed_project_key = str(effective_claimed_project_key or "").strip() or None
    effective_enable_project_reuse = (
        bool(effective_claimed_project_key) if enable_project_reuse is None else enable_project_reuse
    )

    is_success = result == "success"
    reuse_success = bool(effective_enable_project_reuse and effective_claimed_project_key and is_success)
    new_pool_status = "available" if reuse_success else RESULT_TO_POOL_STATUS[result]
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
            claimed_project_key = NULL,
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
    if reuse_success:
        # 成功复用路径：写入/更新 project 维度的 success 统计
        # ON CONFLICT DO UPDATE 实现幂等：重复 success 不会产生重复行
        # COALESCE(first_success_at) 保留首次成功时间戳，仅更新 last_success_at 和 success_count
        conn.execute(
            """
            INSERT INTO account_project_usage (
                account_id, consumer_key, project_key,
                first_claimed_at, last_claimed_at,
                first_success_at, last_success_at, success_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(account_id, consumer_key, project_key)
            DO UPDATE SET
                last_success_at = excluded.last_success_at,
                success_count = account_project_usage.success_count + 1,
                first_success_at = COALESCE(account_project_usage.first_success_at, excluded.first_success_at)
            """,
            (
                account_id,
                caller_id,
                effective_claimed_project_key,
                now_str,
                now_str,
                now_str,
                now_str,
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
                claimed_project_key = NULL,
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
