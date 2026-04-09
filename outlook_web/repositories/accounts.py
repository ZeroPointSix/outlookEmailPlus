from __future__ import annotations

import logging
import sqlite3
from typing import Any, Dict, List, Optional

from outlook_web.db import get_db
from outlook_web.security.crypto import decrypt_data, encrypt_data

COMPACT_SUMMARY_FIELDS = (
    "latest_email_subject",
    "latest_email_from",
    "latest_email_folder",
    "latest_email_received_at",
    "latest_verification_code",
    "latest_verification_folder",
    "latest_verification_received_at",
)

logger = logging.getLogger(__name__)


def _normalize_account_email_domain(email: str) -> str:
    """从邮箱地址提取并规范化域名（小写，去空白）。"""
    if not email or "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1].strip().lower()


def _decrypt_account_field(account: Dict[str, Any], field_name: str) -> None:
    value = account.get(field_name)
    if not value:
        return
    try:
        account[field_name] = decrypt_data(value)
    except Exception as exc:
        credential_errors = account.setdefault("_credential_errors", [])
        credential_errors.append(
            {
                "field": field_name,
                "reason": "decrypt_failed",
                "detail": str(exc),
            }
        )


def load_accounts(group_id: int = None) -> List[Dict]:
    """从数据库加载邮箱账号（自动解密敏感字段，批量加载 tags 避免 N+1）"""
    db = get_db()
    if group_id:
        cursor = db.execute(
            """
            SELECT a.*, g.name as group_name, g.color as group_color
            FROM accounts a
            LEFT JOIN groups g ON a.group_id = g.id
            WHERE a.group_id = ?
            ORDER BY a.created_at DESC
        """,
            (group_id,),
        )
    else:
        cursor = db.execute("""
            SELECT a.*, g.name as group_name, g.color as group_color
            FROM accounts a
            LEFT JOIN groups g ON a.group_id = g.id
            ORDER BY a.created_at DESC
        """)
    rows = cursor.fetchall()

    tags_by_account: Dict[int, List[Dict[str, Any]]] = {}
    try:
        account_ids = [int(r["id"]) for r in rows]
    except Exception:
        account_ids = []

    if account_ids:
        try:
            placeholders = ",".join(["?"] * len(account_ids))
            tag_rows = db.execute(
                f"""
                SELECT at.account_id as account_id, t.*
                FROM account_tags at
                JOIN tags t ON t.id = at.tag_id
                WHERE at.account_id IN ({placeholders})
                ORDER BY at.account_id ASC, t.created_at DESC
                """,
                account_ids,
            ).fetchall()

            for tr in tag_rows:
                tag_dict = dict(tr)
                acc_id = tag_dict.pop("account_id", None)
                if acc_id is None:
                    continue
                tags_by_account.setdefault(int(acc_id), []).append(tag_dict)
        except Exception:
            tags_by_account = {}

    accounts: List[Dict[str, Any]] = []
    for row in rows:
        account = dict(row)
        _decrypt_account_field(account, "password")
        _decrypt_account_field(account, "refresh_token")
        _decrypt_account_field(account, "imap_password")

        account_id_value = account.get("id")
        try:
            account_id_value = int(account_id_value)
        except Exception:
            account_id_value = None

        account["tags"] = (
            tags_by_account.get(account_id_value, [])
            if account_id_value is not None
            else []
        )
        accounts.append(account)
    return accounts


def get_account_by_email(email_addr: str) -> Optional[Dict]:
    """根据邮箱地址获取账号（自动解密敏感字段）"""
    db = get_db()
    cursor = db.execute("SELECT * FROM accounts WHERE email = ?", (email_addr,))
    row = cursor.fetchone()
    if not row:
        return None
    account = dict(row)
    _decrypt_account_field(account, "password")
    _decrypt_account_field(account, "refresh_token")
    _decrypt_account_field(account, "imap_password")
    return account


def get_account_by_id(account_id: int) -> Optional[Dict]:
    """根据 ID 获取账号（含 group_name/group_color，自动解密敏感字段）"""
    db = get_db()
    cursor = db.execute(
        """
        SELECT a.*, g.name as group_name, g.color as group_color
        FROM accounts a
        LEFT JOIN groups g ON a.group_id = g.id
        WHERE a.id = ?
    """,
        (account_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    account = dict(row)
    _decrypt_account_field(account, "password")
    _decrypt_account_field(account, "refresh_token")
    _decrypt_account_field(account, "imap_password")
    return account


def add_account(
    email_addr: str,
    password: str,
    client_id: str,
    refresh_token: str,
    group_id: int = 1,
    remark: str = "",
    account_type: str = "outlook",
    provider: str = "outlook",
    imap_host: str = "",
    imap_port: int = 993,
    imap_password: str = "",
    add_to_pool: bool = False,
    db: Optional[sqlite3.Connection] = None,
    commit: bool = True,
) -> bool:
    """添加邮箱账号（支持外部事务批量导入）"""
    db = db or get_db()
    try:
        account_type = (account_type or "outlook").strip().lower()
        provider = (
            (provider or ("outlook" if account_type != "imap" else "custom"))
            .strip()
            .lower()
        )

        # PRD-00005 / TDD-00005：
        # - Outlook：必须提供 client_id/refresh_token（OAuth2）
        # - IMAP：必须提供 imap_password；client_id/refresh_token 在 DB 中使用空字符串占位（保持 NOT NULL 约束）
        if account_type == "imap":
            if not (imap_password or "").strip():
                return False
            if provider == "custom" and not (imap_host or "").strip():
                return False
        else:
            if not (client_id or "").strip() or not (refresh_token or "").strip():
                return False

        encrypted_password = encrypt_data(password) if password else password
        encrypted_refresh_token = (
            encrypt_data(refresh_token) if refresh_token else refresh_token
        )
        encrypted_imap_password = (
            encrypt_data(imap_password) if imap_password else imap_password
        )
        initial_pool_status = "available" if add_to_pool else None
        email_domain = _normalize_account_email_domain(email_addr)

        db.execute(
            """
            INSERT INTO accounts (
                email, password, client_id, refresh_token,
                account_type, provider, imap_host, imap_port, imap_password,
                group_id, remark, pool_status, email_domain
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                email_addr,
                encrypted_password,
                client_id or "",
                encrypted_refresh_token,
                account_type,
                provider,
                imap_host or "",
                int(imap_port) if imap_port else 993,
                encrypted_imap_password,
                group_id,
                remark,
                initial_pool_status,
                email_domain,
            ),
        )
        if commit:
            db.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    except Exception:
        return False


def update_account(
    account_id: int,
    email_addr: str,
    password: Optional[str],
    client_id: Optional[str],
    refresh_token: Optional[str],
    group_id: int,
    remark: str,
    status: str,
) -> bool:
    """更新邮箱账号"""
    db = get_db()
    try:
        existing = db.execute(
            """
            SELECT password, client_id, refresh_token, account_type, imap_password
            FROM accounts
            WHERE id = ?
        """,
            (account_id,),
        ).fetchone()
        if not existing:
            return False

        account_type = (existing["account_type"] or "outlook").strip().lower()

        # PRD-00005 / TDD-00005：IMAP 账号不要求 client_id/refresh_token（DB 约束使用空字符串占位）
        # 允许更新：email/group/remark/status；如用户在 UI 的“密码”栏输入内容，则视为更新 imap_password。
        if account_type == "imap":
            encrypted_imap_password = existing["imap_password"]
            if isinstance(password, str) and password.strip():
                encrypted_imap_password = encrypt_data(password)

            if not email_addr:
                return False

            db.execute(
                """
                UPDATE accounts
                SET email = ?,
                    imap_password = ?,
                    group_id = ?,
                    remark = ?,
                    status = ?,
                    email_domain = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (
                    email_addr,
                    encrypted_imap_password,
                    group_id,
                    remark,
                    status,
                    _normalize_account_email_domain(email_addr),
                    account_id,
                ),
            )
            db.commit()
            return True

        new_client_id = (
            client_id.strip()
            if isinstance(client_id, str) and client_id.strip()
            else existing["client_id"]
        )

        encrypted_password = existing["password"]
        if isinstance(password, str) and password.strip():
            encrypted_password = encrypt_data(password)

        encrypted_refresh_token = existing["refresh_token"]
        if isinstance(refresh_token, str) and refresh_token.strip():
            encrypted_refresh_token = encrypt_data(refresh_token)

        if not email_addr or not new_client_id or not encrypted_refresh_token:
            return False

        db.execute(
            """
            UPDATE accounts
            SET email = ?, password = ?, client_id = ?, refresh_token = ?,
                group_id = ?, remark = ?, status = ?, email_domain = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (
                email_addr,
                encrypted_password,
                new_client_id,
                encrypted_refresh_token,
                group_id,
                remark,
                status,
                _normalize_account_email_domain(email_addr),
                account_id,
            ),
        )
        db.commit()
        return True
    except Exception:
        return False


def delete_account_by_id(account_id: int) -> bool:
    """删除邮箱账号"""
    db = get_db()
    try:
        db.execute("DELETE FROM account_claim_logs WHERE account_id = ?", (account_id,))
        db.execute(
            "DELETE FROM account_project_usage WHERE account_id = ?", (account_id,)
        )
        cursor = db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        db.commit()
        return cursor.rowcount > 0
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        logger.exception("delete_account_by_id failed: account_id=%s", account_id)
        return False


def delete_account_by_email(email_addr: str) -> bool:
    """根据邮箱地址删除账号"""
    db = get_db()
    try:
        row = db.execute(
            "SELECT id FROM accounts WHERE email = ?", (email_addr,)
        ).fetchone()
        if not row:
            return False
        return delete_account_by_id(int(row["id"]))
    except Exception:
        logger.exception("delete_account_by_email failed: email=%s", email_addr)
        return False


def update_account_credentials(account_id: int, **fields) -> bool:
    """仅更新账号的凭据相关字段（用于覆盖导入场景），敏感字段自动加密。"""
    allowed = {
        "password",
        "client_id",
        "refresh_token",
        "imap_password",
        "imap_host",
        "imap_port",
        "account_type",
        "provider",
        "group_id",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False

    # 加密敏感字段
    for key in ("password", "refresh_token", "imap_password"):
        if key in updates and updates[key]:
            updates[key] = encrypt_data(updates[key])

    db = get_db()
    try:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [account_id]
        db.execute(
            f"UPDATE accounts SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values,
        )
        db.commit()
        return True
    except Exception:
        return False


def get_account_compact_summary(account_id: int) -> Optional[Dict[str, str]]:
    db = get_db()
    fields_sql = ", ".join(COMPACT_SUMMARY_FIELDS)
    row = db.execute(
        f"SELECT {fields_sql} FROM accounts WHERE id = ?",
        (account_id,),
    ).fetchone()
    if not row:
        return None
    return {field: str(row[field] or "") for field in COMPACT_SUMMARY_FIELDS}


def update_account_compact_summary(account_id: int, summary: Dict[str, Any]) -> bool:
    db = get_db()
    existing = db.execute(
        "SELECT id FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    if not existing:
        return False

    values = [str(summary.get(field) or "") for field in COMPACT_SUMMARY_FIELDS]
    assignments = ", ".join(f"{field} = ?" for field in COMPACT_SUMMARY_FIELDS)
    db.execute(
        f"""
        UPDATE accounts
        SET {assignments}, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        values + [account_id],
    )
    db.commit()
    return True


def toggle_telegram_push(account_id: int, enabled: bool) -> bool:
    """切换账号 Telegram 推送开关。从禁用切换到启用时重置游标为当前 UTC 时间，
    已启用时重复调用不改变游标（幂等）。"""
    from datetime import datetime, timezone

    def _build_source_key(source_type: str, raw_key: str) -> str:
        return f"{source_type}:{(raw_key or '').strip().lower()}"

    db = get_db()
    row = db.execute(
        "SELECT id, email, telegram_push_enabled, telegram_last_checked_at FROM accounts WHERE id = ?",
        (account_id,),
    ).fetchone()
    if not row:
        return False

    if enabled:
        already_enabled = bool(row["telegram_push_enabled"])
        if already_enabled:
            return True
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        db.execute(
            "UPDATE accounts SET telegram_push_enabled = 1, telegram_last_checked_at = ? WHERE id = ?",
            (now_utc, account_id),
        )
        source_type = "account"
        source_key = _build_source_key(source_type, row["email"] or "")
        for channel in ("email", "telegram"):
            db.execute(
                """
                INSERT INTO notification_cursor_states (
                    channel, source_type, source_key, last_cursor_value, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(channel, source_type, source_key)
                DO UPDATE SET
                    last_cursor_value = excluded.last_cursor_value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (channel, source_type, source_key, now_utc),
            )
    else:
        db.execute(
            "UPDATE accounts SET telegram_push_enabled = 0 WHERE id = ?", (account_id,)
        )

    db.commit()
    return True


def update_telegram_cursor(account_id: int, checked_at: str) -> None:
    """更新账号的 telegram_last_checked_at 游标。"""
    db = get_db()
    db.execute(
        "UPDATE accounts SET telegram_last_checked_at = ? WHERE id = ?",
        (checked_at, account_id),
    )
    db.commit()


def get_telegram_push_accounts() -> List[Dict]:
    """返回所有 telegram_push_enabled=1 且处于 active 状态的账号。"""
    db = get_db()
    rows = db.execute("""SELECT a.id, a.email, a.account_type, a.provider, a.client_id, a.refresh_token,
                  a.imap_host, a.imap_port, a.imap_password,
                  a.telegram_last_checked_at, a.group_id,
                  g.proxy_url
           FROM accounts a
           LEFT JOIN groups g ON a.group_id = g.id
           WHERE a.telegram_push_enabled = 1 AND a.status = 'active'""").fetchall()
    return [dict(r) for r in rows]
