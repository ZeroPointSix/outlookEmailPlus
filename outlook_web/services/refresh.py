from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from outlook_web.db import create_sqlite_connection
from outlook_web.errors import build_error_payload, generate_trace_id
from outlook_web.repositories.distributed_locks import (
    acquire_distributed_lock,
    release_distributed_lock,
)
from outlook_web.repositories.refresh_runs import create_refresh_run, finish_refresh_run
from outlook_web.security.crypto import decrypt_data, encrypt_data

REFRESH_LOCK_TTL_SECONDS = 60 * 60 * 2  # 2 小时，避免异常中断导致长时间卡死


def build_refreshable_outlook_account_where(column: str = "account_type") -> str:
    """构造 Outlook-only 刷新规则，兼容历史空 account_type 数据。"""
    return f"({column} = 'outlook' OR {column} IS NULL)"


REFRESHABLE_OUTLOOK_ACCOUNT_WHERE = build_refreshable_outlook_account_where()
REFRESHABLE_OUTLOOK_ACCOUNT_SELECT = f"""
    SELECT id, email, client_id, refresh_token, group_id
    FROM accounts
    WHERE status = 'active'
      AND {REFRESHABLE_OUTLOOK_ACCOUNT_WHERE}
"""


def is_refreshable_outlook_account(account_type: Optional[str]) -> bool:
    """仅 Outlook（以及历史空 account_type）允许进入 OAuth token 刷新链路。"""
    if account_type is None:
        return True
    return isinstance(account_type, str) and account_type.strip().lower() == "outlook"


def utcnow() -> datetime:
    """返回 naive UTC 时间（等价于旧的 datetime.utcnow()）"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def compute_refresh_lock_ttl_seconds(total: int, delay_seconds: int) -> int:
    try:
        total = int(total or 0)
    except Exception:
        total = 0
    try:
        delay_seconds = int(delay_seconds or 0)
    except Exception:
        delay_seconds = 0

    estimated = int(total * (max(delay_seconds, 0) + 2) + 600)
    ttl = max(REFRESH_LOCK_TTL_SECONDS, estimated)
    return min(ttl, 60 * 60 * 24)  # 最大 24 小时


def stream_refresh_all_accounts(
    *,
    trace_id: Optional[str],
    requested_by_ip: str,
    requested_by_user_agent: str,
    lock_name: str,
    test_refresh_token: Callable[
        [str, str, Optional[str]], Tuple[bool, Optional[str], Optional[str]]
    ],
) -> Iterator[str]:
    """刷新所有账号 token（SSE 流式输出）"""
    conn = create_sqlite_connection()
    lock_owner_id = uuid.uuid4().hex
    lock_acquired = False
    run_id = None

    try:
        delay_row = conn.execute(
            "SELECT value FROM settings WHERE key = 'refresh_delay_seconds'"
        ).fetchone()
        delay_seconds = int(delay_row["value"]) if delay_row else 5

        try:
            conn.execute(
                "DELETE FROM account_refresh_logs WHERE created_at < datetime('now', '-6 months')"
            )
            conn.execute(
                "DELETE FROM refresh_runs WHERE started_at < datetime('now', '-6 months')"
            )
            conn.execute(
                "DELETE FROM distributed_locks WHERE expires_at < ?", (time.time(),)
            )
            conn.commit()
        except Exception:
            pass

        accounts = conn.execute(REFRESHABLE_OUTLOOK_ACCOUNT_SELECT).fetchall()
        total = len(accounts)

        run_id = create_refresh_run(
            conn,
            trigger_source="manual_all",
            trace_id=trace_id or generate_trace_id(),
            requested_by_ip=requested_by_ip,
            requested_by_user_agent=requested_by_user_agent,
            total=total,
        )

        ttl_seconds = compute_refresh_lock_ttl_seconds(total, delay_seconds)
        ok, lock_info = acquire_distributed_lock(
            conn, lock_name, lock_owner_id, ttl_seconds
        )
        if not ok:
            finish_refresh_run(
                conn, run_id, "skipped", total, 0, 0, "刷新任务冲突：已有刷新在执行"
            )
            error_payload = build_error_payload(
                code="REFRESH_CONFLICT",
                message="当前已有刷新任务执行中，请稍后再试",
                err_type="ConflictError",
                status=409,
                details=lock_info or "",
                trace_id=trace_id,
            )
            yield f"data: {json.dumps({'type': 'error', 'error': error_payload}, ensure_ascii=False)}\n\n"
            return
        lock_acquired = True

        success_count = 0
        failed_count = 0
        failed_list: List[Dict[str, Any]] = []

        yield (
            "data: "
            + json.dumps(
                {
                    "type": "start",
                    "total": total,
                    "delay_seconds": delay_seconds,
                    "run_id": run_id,
                    "trace_id": trace_id,
                    "refresh_type": "manual_all",
                },
                ensure_ascii=False,
            )
            + "\n\n"
        )

        for index, account in enumerate(accounts, 1):
            account_id = account["id"]
            account_email = account["email"]
            client_id = account["client_id"]
            encrypted_refresh_token = account["refresh_token"]

            try:
                refresh_token = (
                    decrypt_data(encrypted_refresh_token)
                    if encrypted_refresh_token
                    else encrypted_refresh_token
                )
            except Exception as e:
                failed_count += 1
                error_msg = f"解密 token 失败: {str(e)}"
                failed_list.append(
                    {"id": account_id, "email": account_email, "error": error_msg}
                )
                try:
                    conn.execute(
                        """
                        INSERT INTO account_refresh_logs (account_id, account_email, refresh_type, status, error_message, run_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            account_id,
                            account_email,
                            "manual_all",
                            "failed",
                            error_msg,
                            run_id,
                        ),
                    )
                    conn.commit()
                except Exception:
                    pass
                continue

            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "progress",
                        "current": index,
                        "total": total,
                        "email": account_email,
                        "success_count": success_count,
                        "failed_count": failed_count,
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )

            proxy_url = ""
            group_id = account["group_id"]
            if group_id:
                try:
                    group_row = conn.execute(
                        "SELECT proxy_url FROM groups WHERE id = ?", (group_id,)
                    ).fetchone()
                    if group_row:
                        proxy_url = group_row["proxy_url"] or ""
                except Exception:
                    proxy_url = ""

            success, error_msg, new_refresh_token = test_refresh_token(
                client_id, refresh_token, proxy_url
            )

            try:
                conn.execute(
                    """
                    INSERT INTO account_refresh_logs (account_id, account_email, refresh_type, status, error_message, run_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        account_id,
                        account_email,
                        "manual_all",
                        "success" if success else "failed",
                        error_msg,
                        run_id,
                    ),
                )

                if success:
                    if (
                        isinstance(new_refresh_token, str)
                        and new_refresh_token.strip()
                        and new_refresh_token != refresh_token
                    ):
                        conn.execute(
                            """
                            UPDATE accounts
                            SET refresh_token = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """,
                            (encrypt_data(new_refresh_token), account_id),
                        )
                    conn.execute(
                        """
                        UPDATE accounts
                        SET last_refresh_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """,
                        (account_id,),
                    )
                conn.commit()
            except Exception:
                pass

            if success:
                success_count += 1
            else:
                failed_count += 1
                failed_list.append(
                    {"id": account_id, "email": account_email, "error": error_msg}
                )

            if index < total and delay_seconds > 0:
                yield f"data: {json.dumps({'type': 'delay', 'seconds': delay_seconds}, ensure_ascii=False)}\n\n"
                time.sleep(delay_seconds)

        finish_refresh_run(
            conn,
            run_id,
            "completed",
            total,
            success_count,
            failed_count,
            f"完成：成功 {success_count}，失败 {failed_count}",
        )

        yield (
            "data: "
            + json.dumps(
                {
                    "type": "complete",
                    "total": total,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "failed_list": failed_list,
                    "run_id": run_id,
                },
                ensure_ascii=False,
            )
            + "\n\n"
        )
    except Exception as e:
        try:
            if run_id:
                finish_refresh_run(conn, run_id, "failed", 0, 0, 0, str(e))
        except Exception:
            pass
        error_payload = build_error_payload(
            code="REFRESH_FAILED",
            message="刷新执行失败",
            err_type="RefreshError",
            status=500,
            details=str(e),
            trace_id=trace_id,
        )
        yield f"data: {json.dumps({'type': 'error', 'error': error_payload}, ensure_ascii=False)}\n\n"
    finally:
        if lock_acquired:
            release_distributed_lock(conn, lock_name, lock_owner_id)
        try:
            conn.close()
        except Exception:
            pass


def stream_trigger_scheduled_refresh(
    *,
    force: bool,
    refresh_interval_days: int,
    use_cron: bool,
    trace_id: Optional[str],
    requested_by_ip: str,
    requested_by_user_agent: str,
    lock_name: str,
    test_refresh_token: Callable[
        [str, str, Optional[str]], Tuple[bool, Optional[str], Optional[str]]
    ],
) -> Iterator[str]:
    """手动触发定时刷新（SSE 流式输出）"""
    conn = create_sqlite_connection()
    lock_owner_id = uuid.uuid4().hex
    lock_acquired = False
    run_id = None
    total = 0
    success_count = 0
    failed_count = 0

    try:
        delay_row = conn.execute(
            "SELECT value FROM settings WHERE key = 'refresh_delay_seconds'"
        ).fetchone()
        delay_seconds = int(delay_row["value"]) if delay_row else 5

        try:
            conn.execute(
                "DELETE FROM account_refresh_logs WHERE created_at < datetime('now', '-6 months')"
            )
            conn.commit()
        except Exception:
            pass

        accounts = conn.execute(REFRESHABLE_OUTLOOK_ACCOUNT_SELECT).fetchall()

        total = len(accounts)
        run_id = create_refresh_run(
            conn,
            trigger_source="scheduled_manual",
            trace_id=trace_id or generate_trace_id(),
            requested_by_ip=requested_by_ip,
            requested_by_user_agent=requested_by_user_agent,
            total=total,
        )

        if (not force) and (not use_cron):
            row = conn.execute("""
                SELECT finished_at
                FROM refresh_runs
                WHERE trigger_source IN ('scheduled', 'scheduled_manual')
                  AND status IN ('completed', 'failed')
                  AND finished_at IS NOT NULL
                ORDER BY finished_at DESC
                LIMIT 1
            """).fetchone()

            if row and row["finished_at"]:
                try:
                    last_time = datetime.fromisoformat(row["finished_at"])
                except Exception:
                    last_time = None

                if last_time:
                    next_due = last_time + timedelta(days=refresh_interval_days)
                    if utcnow() < next_due:
                        finish_refresh_run(
                            conn,
                            run_id,
                            "skipped",
                            0,
                            0,
                            0,
                            f"距离上次刷新未满 {refresh_interval_days} 天，下次最早：{next_due.strftime('%Y-%m-%d %H:%M:%S')}",
                        )
                        yield (
                            "data: "
                            + json.dumps(
                                {
                                    "type": "skipped",
                                    "message": "未到刷新周期",
                                    "next_due": next_due.isoformat(),
                                    "run_id": run_id,
                                },
                                ensure_ascii=False,
                            )
                            + "\n\n"
                        )
                        return

        ttl_seconds = compute_refresh_lock_ttl_seconds(total, delay_seconds)
        ok, lock_info = acquire_distributed_lock(
            conn, lock_name, lock_owner_id, ttl_seconds
        )
        if not ok:
            finish_refresh_run(
                conn, run_id, "skipped", total, 0, 0, "刷新任务冲突：已有刷新在执行"
            )
            error_payload = build_error_payload(
                code="REFRESH_CONFLICT",
                message="当前已有刷新任务执行中，请稍后再试",
                err_type="ConflictError",
                status=409,
                details=lock_info or "",
                trace_id=trace_id,
            )
            yield f"data: {json.dumps({'type': 'error', 'error': error_payload}, ensure_ascii=False)}\n\n"
            return
        lock_acquired = True

        success_count = 0
        failed_count = 0
        failed_list: List[Dict[str, Any]] = []

        yield (
            "data: "
            + json.dumps(
                {
                    "type": "start",
                    "total": total,
                    "delay_seconds": delay_seconds,
                    "refresh_type": "scheduled",
                    "run_id": run_id,
                    "trace_id": trace_id,
                },
                ensure_ascii=False,
            )
            + "\n\n"
        )

        for index, account in enumerate(accounts, 1):
            account_id = account["id"]
            account_email = account["email"]
            client_id = account["client_id"]
            encrypted_refresh_token = account["refresh_token"]

            try:
                refresh_token = (
                    decrypt_data(encrypted_refresh_token)
                    if encrypted_refresh_token
                    else encrypted_refresh_token
                )
            except Exception as e:
                failed_count += 1
                error_msg = f"解密 token 失败: {str(e)}"
                failed_list.append(
                    {"id": account_id, "email": account_email, "error": error_msg}
                )
                try:
                    conn.execute(
                        """
                        INSERT INTO account_refresh_logs (account_id, account_email, refresh_type, status, error_message, run_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """,
                        (
                            account_id,
                            account_email,
                            "scheduled",
                            "failed",
                            error_msg,
                            run_id,
                        ),
                    )
                    conn.commit()
                except Exception:
                    pass
                continue

            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "progress",
                        "current": index,
                        "total": total,
                        "email": account_email,
                        "success_count": success_count,
                        "failed_count": failed_count,
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )

            proxy_url = ""
            group_id = account["group_id"]
            if group_id:
                group_row = conn.execute(
                    "SELECT proxy_url FROM groups WHERE id = ?", (group_id,)
                ).fetchone()
                if group_row:
                    proxy_url = group_row["proxy_url"] or ""

            success, error_msg, new_refresh_token = test_refresh_token(
                client_id, refresh_token, proxy_url
            )

            try:
                conn.execute(
                    """
                    INSERT INTO account_refresh_logs (account_id, account_email, refresh_type, status, error_message, run_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        account_id,
                        account_email,
                        "scheduled",
                        "success" if success else "failed",
                        error_msg,
                        run_id,
                    ),
                )

                if success:
                    if (
                        isinstance(new_refresh_token, str)
                        and new_refresh_token.strip()
                        and new_refresh_token != refresh_token
                    ):
                        conn.execute(
                            """
                            UPDATE accounts
                            SET refresh_token = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """,
                            (encrypt_data(new_refresh_token), account_id),
                        )
                    conn.execute(
                        """
                        UPDATE accounts
                        SET last_refresh_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """,
                        (account_id,),
                    )

                conn.commit()
            except Exception:
                pass

            if success:
                success_count += 1
            else:
                failed_count += 1
                failed_list.append(
                    {"id": account_id, "email": account_email, "error": error_msg}
                )

            if index < total and delay_seconds > 0:
                yield f"data: {json.dumps({'type': 'delay', 'seconds': delay_seconds}, ensure_ascii=False)}\n\n"
                time.sleep(delay_seconds)

        finish_refresh_run(
            conn,
            run_id,
            "completed",
            total,
            success_count,
            failed_count,
            f"完成：成功 {success_count}，失败 {failed_count}",
        )

        yield (
            "data: "
            + json.dumps(
                {
                    "type": "complete",
                    "total": total,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "failed_list": failed_list,
                    "run_id": run_id,
                },
                ensure_ascii=False,
            )
            + "\n\n"
        )
    except Exception as e:
        try:
            if run_id:
                finish_refresh_run(
                    conn, run_id, "failed", total, success_count, failed_count, str(e)
                )
        except Exception:
            pass
        error_payload = build_error_payload(
            code="REFRESH_FAILED",
            message="刷新执行失败",
            err_type="RefreshError",
            status=500,
            details=str(e),
            trace_id=trace_id,
        )
        yield f"data: {json.dumps({'type': 'error', 'error': error_payload}, ensure_ascii=False)}\n\n"
    finally:
        if lock_acquired:
            release_distributed_lock(conn, lock_name, lock_owner_id)
        try:
            conn.close()
        except Exception:
            pass


def stream_refresh_selected_accounts(
    *,
    account_ids: List[int],
    trace_id: Optional[str],
    requested_by_ip: str,
    requested_by_user_agent: str,
    lock_name: str,
    test_refresh_token: Callable[
        [str, str, Optional[str]], Tuple[bool, Optional[str], Optional[str]]
    ],
) -> Iterator[str]:
    """刷新指定账号列表的 token（SSE 流式输出）"""
    conn = create_sqlite_connection()
    lock_owner_id = uuid.uuid4().hex
    lock_acquired = False
    run_id = None

    try:
        delay_row = conn.execute(
            "SELECT value FROM settings WHERE key = 'refresh_delay_seconds'"
        ).fetchone()
        delay_seconds = int(delay_row["value"]) if delay_row else 5

        try:
            conn.execute(
                "DELETE FROM account_refresh_logs WHERE created_at < datetime('now', '-6 months')"
            )
            conn.execute(
                "DELETE FROM refresh_runs WHERE started_at < datetime('now', '-6 months')"
            )
            conn.execute(
                "DELETE FROM distributed_locks WHERE expires_at < ?", (time.time(),)
            )
            conn.commit()
        except Exception:
            pass

        # 查询指定 ID 的账号，过滤出 Outlook 类型（IMAP 账号跳过）
        placeholders = ",".join("?" * len(account_ids))
        all_rows = conn.execute(
            f"""
            SELECT id, email, client_id, refresh_token, group_id, account_type
            FROM accounts
            WHERE id IN ({placeholders})
              AND status = 'active'
            """,
            account_ids,
        ).fetchall()

        accounts = [
            row
            for row in all_rows
            if is_refreshable_outlook_account(row["account_type"])
        ]
        skipped_count = len(all_rows) - len(accounts)
        total = len(accounts)

        run_id = create_refresh_run(
            conn,
            trigger_source="manual_selected",
            trace_id=trace_id or generate_trace_id(),
            requested_by_ip=requested_by_ip,
            requested_by_user_agent=requested_by_user_agent,
            total=total,
        )

        ttl_seconds = compute_refresh_lock_ttl_seconds(total, delay_seconds)
        ok, lock_info = acquire_distributed_lock(
            conn, lock_name, lock_owner_id, ttl_seconds
        )
        if not ok:
            finish_refresh_run(
                conn, run_id, "skipped", total, 0, 0, "刷新任务冲突：已有刷新在执行"
            )
            error_payload = build_error_payload(
                code="REFRESH_CONFLICT",
                message="当前已有刷新任务执行中，请稍后再试",
                err_type="ConflictError",
                status=409,
                details=lock_info or "",
                trace_id=trace_id,
            )
            yield f"data: {json.dumps({'type': 'error', 'error': error_payload}, ensure_ascii=False)}\n\n"
            return
        lock_acquired = True

        success_count = 0
        failed_count = 0
        failed_list: List[Dict[str, Any]] = []

        yield (
            "data: "
            + json.dumps(
                {
                    "type": "start",
                    "total": total,
                    "skipped_count": skipped_count,
                    "delay_seconds": delay_seconds,
                    "run_id": run_id,
                    "trace_id": trace_id,
                    "refresh_type": "manual_selected",
                },
                ensure_ascii=False,
            )
            + "\n\n"
        )

        for index, account in enumerate(accounts, 1):
            account_id = account["id"]
            account_email = account["email"]
            client_id = account["client_id"]
            encrypted_refresh_token = account["refresh_token"]

            try:
                refresh_token = (
                    decrypt_data(encrypted_refresh_token)
                    if encrypted_refresh_token
                    else encrypted_refresh_token
                )
            except Exception as e:
                failed_count += 1
                error_msg = f"解密 token 失败: {str(e)}"
                failed_list.append(
                    {"id": account_id, "email": account_email, "error": error_msg}
                )
                try:
                    conn.execute(
                        """
                        INSERT INTO account_refresh_logs (account_id, account_email, refresh_type, status, error_message, run_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            account_id,
                            account_email,
                            "manual_selected",
                            "failed",
                            error_msg,
                            run_id,
                        ),
                    )
                    conn.commit()
                except Exception:
                    pass
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "progress",
                            "current": index,
                            "total": total,
                            "email": account_email,
                            "account_id": account_id,
                            "result": "failed",
                            "error_message": error_msg,
                            "last_refresh_at": None,
                            "success_count": success_count,
                            "failed_count": failed_count,
                        },
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
                continue

            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "progress",
                        "current": index,
                        "total": total,
                        "email": account_email,
                        "account_id": account_id,
                        "result": "processing",
                        "error_message": None,
                        "last_refresh_at": None,
                        "success_count": success_count,
                        "failed_count": failed_count,
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )

            proxy_url = ""
            group_id = account["group_id"]
            if group_id:
                try:
                    group_row = conn.execute(
                        "SELECT proxy_url FROM groups WHERE id = ?", (group_id,)
                    ).fetchone()
                    if group_row:
                        proxy_url = group_row["proxy_url"] or ""
                except Exception:
                    proxy_url = ""

            success, error_msg, new_refresh_token = test_refresh_token(
                client_id, refresh_token, proxy_url
            )

            last_refresh_at = None
            try:
                conn.execute(
                    """
                    INSERT INTO account_refresh_logs (account_id, account_email, refresh_type, status, error_message, run_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        account_id,
                        account_email,
                        "manual_selected",
                        "success" if success else "failed",
                        error_msg,
                        run_id,
                    ),
                )

                if success:
                    if (
                        isinstance(new_refresh_token, str)
                        and new_refresh_token.strip()
                        and new_refresh_token != refresh_token
                    ):
                        conn.execute(
                            """
                            UPDATE accounts
                            SET refresh_token = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """,
                            (encrypt_data(new_refresh_token), account_id),
                        )
                    conn.execute(
                        """
                        UPDATE accounts
                        SET last_refresh_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """,
                        (account_id,),
                    )
                    # 取最新的 last_refresh_at 用于返回给前端
                    row = conn.execute(
                        "SELECT last_refresh_at FROM accounts WHERE id = ?",
                        (account_id,),
                    ).fetchone()
                    if row:
                        last_refresh_at = row["last_refresh_at"]
                conn.commit()
            except Exception:
                pass

            if success:
                success_count += 1
            else:
                failed_count += 1
                failed_list.append(
                    {"id": account_id, "email": account_email, "error": error_msg}
                )

            # 发送带 account_id 和 result 的完整 progress 事件
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "progress",
                        "current": index,
                        "total": total,
                        "email": account_email,
                        "account_id": account_id,
                        "result": "success" if success else "failed",
                        "error_message": error_msg if not success else None,
                        "last_refresh_at": last_refresh_at,
                        "success_count": success_count,
                        "failed_count": failed_count,
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )

            if index < total and delay_seconds > 0:
                yield f"data: {json.dumps({'type': 'delay', 'seconds': delay_seconds}, ensure_ascii=False)}\n\n"
                time.sleep(delay_seconds)

        finish_refresh_run(
            conn,
            run_id,
            "completed",
            total,
            success_count,
            failed_count,
            f"完成：成功 {success_count}，失败 {failed_count}",
        )

        yield (
            "data: "
            + json.dumps(
                {
                    "type": "complete",
                    "total": total,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "failed_list": failed_list,
                    "run_id": run_id,
                },
                ensure_ascii=False,
            )
            + "\n\n"
        )
    except Exception as e:
        try:
            if run_id:
                finish_refresh_run(conn, run_id, "failed", 0, 0, 0, str(e))
        except Exception:
            pass
        error_payload = build_error_payload(
            code="REFRESH_FAILED",
            message="刷新执行失败",
            err_type="RefreshError",
            status=500,
            details=str(e),
            trace_id=trace_id,
        )
        yield f"data: {json.dumps({'type': 'error', 'error': error_payload}, ensure_ascii=False)}\n\n"
    finally:
        if lock_acquired:
            release_distributed_lock(conn, lock_name, lock_owner_id)
        try:
            conn.close()
        except Exception:
            pass


def refresh_failed_accounts(
    *,
    db,
    trace_id: Optional[str],
    requested_by_ip: str,
    requested_by_user_agent: str,
    lock_name: str,
    test_refresh_token: Callable[
        [str, str, Optional[str]], Tuple[bool, Optional[str], Optional[str]]
    ],
) -> Tuple[Dict[str, Any], int]:
    """重试所有失败的账号（非流式）"""
    lock_owner_id = uuid.uuid4().hex

    cursor = db.execute(f"""
        SELECT DISTINCT a.id, a.email, a.client_id, a.refresh_token, a.group_id
        FROM accounts a
        INNER JOIN (
            SELECT account_id, MAX(created_at) as last_refresh
            FROM account_refresh_logs
            GROUP BY account_id
        ) latest ON a.id = latest.account_id
        INNER JOIN account_refresh_logs l ON a.id = l.account_id AND l.created_at = latest.last_refresh
        WHERE l.status = 'failed'
          AND a.status = 'active'
          AND {build_refreshable_outlook_account_where("a.account_type")}
    """)
    accounts = cursor.fetchall()

    total = len(accounts)
    run_id = create_refresh_run(
        db,
        trigger_source="retry_failed",
        trace_id=trace_id or generate_trace_id(),
        requested_by_ip=requested_by_ip,
        requested_by_user_agent=requested_by_user_agent,
        total=total,
    )

    ttl_seconds = compute_refresh_lock_ttl_seconds(total, 0)
    ok, lock_info = acquire_distributed_lock(db, lock_name, lock_owner_id, ttl_seconds)
    if not ok:
        finish_refresh_run(
            db, run_id, "skipped", total, 0, 0, "刷新任务冲突：已有刷新在执行"
        )
        error_payload = build_error_payload(
            code="REFRESH_CONFLICT",
            message="当前已有刷新任务执行中，请稍后再试",
            err_type="ConflictError",
            status=409,
            details=lock_info or "",
            trace_id=trace_id,
        )
        return {"success": False, "error": error_payload}, 409

    success_count = 0
    failed_count = 0
    failed_list: List[Dict[str, Any]] = []

    try:
        for account in accounts:
            account_id = account["id"]
            account_email = account["email"]
            client_id = account["client_id"]
            encrypted_refresh_token = account["refresh_token"]

            proxy_url = ""
            group_id = account["group_id"]
            if group_id:
                try:
                    group_row = db.execute(
                        "SELECT proxy_url FROM groups WHERE id = ?", (group_id,)
                    ).fetchone()
                    if group_row:
                        proxy_url = group_row["proxy_url"] or ""
                except Exception:
                    proxy_url = ""

            try:
                refresh_token = (
                    decrypt_data(encrypted_refresh_token)
                    if encrypted_refresh_token
                    else encrypted_refresh_token
                )
            except Exception as e:
                failed_count += 1
                error_msg = f"解密 token 失败: {str(e)}"
                failed_list.append(
                    {"id": account_id, "email": account_email, "error": error_msg}
                )
                try:
                    from outlook_web.repositories.refresh_logs import log_refresh_result

                    log_refresh_result(
                        account_id,
                        account_email,
                        "retry",
                        "failed",
                        error_msg,
                        run_id=run_id,
                    )
                except Exception:
                    pass
                continue

            success, error_msg, new_refresh_token = test_refresh_token(
                client_id, refresh_token, proxy_url
            )
            try:
                from outlook_web.repositories.refresh_logs import log_refresh_result

                log_refresh_result(
                    account_id,
                    account_email,
                    "retry",
                    "success" if success else "failed",
                    error_msg,
                    run_id=run_id,
                )
            except Exception:
                pass

            if success:
                try:
                    if (
                        isinstance(new_refresh_token, str)
                        and new_refresh_token.strip()
                        and new_refresh_token != refresh_token
                    ):
                        db.execute(
                            """
                            UPDATE accounts
                            SET refresh_token = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """,
                            (encrypt_data(new_refresh_token), account_id),
                        )
                    db.execute(
                        """
                        UPDATE accounts
                        SET last_refresh_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """,
                        (account_id,),
                    )
                    db.commit()
                except Exception:
                    pass
                success_count += 1
            else:
                failed_count += 1
                failed_list.append(
                    {"id": account_id, "email": account_email, "error": error_msg}
                )
    finally:
        release_distributed_lock(db, lock_name, lock_owner_id)

    finish_refresh_run(
        db,
        run_id,
        "completed",
        total,
        success_count,
        failed_count,
        f"完成：成功 {success_count}，失败 {failed_count}",
    )

    return (
        {
            "success": True,
            "run_id": run_id,
            "total": total,
            "success_count": success_count,
            "failed_count": failed_count,
            "failed_list": failed_list,
        },
        200,
    )
