from __future__ import annotations

import os
import sqlite3
import time
from typing import Optional

from flask import g

from outlook_web import config
from outlook_web.errors import generate_trace_id, sanitize_error_details
from outlook_web.security.crypto import (
    encrypt_data,
    hash_password,
    is_encrypted,
    is_password_hashed,
)

# 数据库 Schema 版本（用于升级可验证/可诊断）
DB_SCHEMA_VERSION = 2
DB_SCHEMA_VERSION_KEY = "db_schema_version"
DB_SCHEMA_LAST_UPGRADE_TRACE_ID_KEY = "db_schema_last_upgrade_trace_id"
DB_SCHEMA_LAST_UPGRADE_ERROR_KEY = "db_schema_last_upgrade_error"


def create_sqlite_connection(database_path: Optional[str] = None) -> sqlite3.Connection:
    """创建 SQLite 连接（带基础一致性/并发配置）"""
    path = database_path or config.get_database_path()
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
    except Exception:
        pass
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
    except Exception:
        pass
    return conn


def get_db() -> sqlite3.Connection:
    """获取数据库连接（绑定到 flask.g 生命周期）"""
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = create_sqlite_connection()
    return db


def close_db(_exception=None):
    """关闭数据库连接"""
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def register_db(app):
    """向 Flask app 注册 teardown，保证请求结束释放连接"""
    app.teardown_appcontext(close_db)


def init_db(database_path: Optional[str] = None):
    """初始化数据库（含升级记录与可验证状态）"""
    path = database_path or config.get_database_path()
    login_password_default = config.get_login_password_default()
    gptmail_api_key_default = config.get_gptmail_api_key_default()

    db_existed = False
    try:
        db_existed = os.path.exists(path) and os.path.getsize(path) > 0
    except Exception:
        db_existed = False

    conn = create_sqlite_connection(path)
    cursor = conn.cursor()

    # 基础并发配置（对既存数据库同样生效）
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        pass

    migration_id = None
    migration_trace_id = None
    upgrading = False

    try:
        # 获取写锁：避免多进程启动时并发迁移导致的偶发失败
        cursor.execute("BEGIN IMMEDIATE")

        # 创建设置表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 数据库迁移记录（用于升级可验证/可诊断）
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_version INTEGER NOT NULL,
                to_version INTEGER NOT NULL,
                status TEXT NOT NULL,
                started_at REAL NOT NULL,
                finished_at REAL,
                error TEXT,
                trace_id TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_schema_migrations_started_at
            ON schema_migrations(started_at)
            """
        )

        # 在锁内读取当前 schema 版本（保证一致性）
        row = cursor.execute(
            "SELECT value FROM settings WHERE key = ?",
            (DB_SCHEMA_VERSION_KEY,),
        ).fetchone()
        try:
            current_version = int(row["value"]) if row and row["value"] is not None else 0
        except Exception:
            current_version = 0

        upgrading = current_version < DB_SCHEMA_VERSION
        if upgrading:
            migration_trace_id = generate_trace_id()
            if db_existed:
                try:
                    print("=" * 60)
                    print(f"[升级提示] 检测到数据库需要升级：v{current_version} -> v{DB_SCHEMA_VERSION}")
                    print(f"[升级提示] 强烈建议先备份数据库文件：{path}")
                    print(f"[升级提示] 示例：cp \"{path}\" \"{path}.backup\"")
                    print(f"[升级提示] trace_id={migration_trace_id}")
                    print("=" * 60)
                except Exception:
                    pass

            cursor.execute(
                """
                INSERT INTO schema_migrations (from_version, to_version, status, started_at, trace_id)
                VALUES (?, ?, 'running', ?, ?)
                """,
                (current_version, DB_SCHEMA_VERSION, time.time(), migration_trace_id),
            )
            migration_id = cursor.lastrowid
            cursor.execute("SAVEPOINT migration_work")

        # -------------------- Schema 创建/迁移（幂等） --------------------

        # 分组表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                color TEXT DEFAULT '#1a1a1a',
                proxy_url TEXT,
                is_system INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 邮箱账号表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT,
                client_id TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                group_id INTEGER,
                remark TEXT,
                status TEXT DEFAULT 'active',
                last_refresh_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (group_id) REFERENCES groups (id)
            )
            """
        )

        # 临时邮箱表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS temp_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 临时邮件表（存储从 GPTMail 获取的邮件）
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS temp_email_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE NOT NULL,
                email_address TEXT NOT NULL,
                from_address TEXT,
                subject TEXT,
                content TEXT,
                html_content TEXT,
                has_html INTEGER DEFAULT 0,
                timestamp INTEGER,
                raw_content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (email_address) REFERENCES temp_emails (email)
            )
            """
        )

        # 刷新记录表（账号级）
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS account_refresh_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                account_email TEXT NOT NULL,
                refresh_type TEXT DEFAULT 'manual',
                status TEXT NOT NULL,
                error_message TEXT,
                run_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_account_refresh_logs_run_id
            ON account_refresh_logs(run_id)
            """
        )

        # 审计日志表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT,
                user_ip TEXT,
                details TEXT,
                trace_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_logs_trace_id
            ON audit_logs(trace_id)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at
            ON audit_logs(created_at)
            """
        )

        # 标签表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                color TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 账号标签关联表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS account_tags (
                account_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (account_id, tag_id),
                FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags (id) ON DELETE CASCADE
            )
            """
        )

        # 分布式锁（用于刷新冲突控制/多进程一致性）
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS distributed_locks (
                name TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                acquired_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
            """
        )

        # 导出二次验证 Token（持久化，支持重启/多进程）
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS export_verify_tokens (
                token TEXT PRIMARY KEY,
                ip TEXT,
                user_agent TEXT,
                expires_at REAL NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )

        # 登录速率限制（持久化，支持重启/多进程）
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS login_attempts (
                ip TEXT PRIMARY KEY,
                count INTEGER NOT NULL,
                last_attempt_at REAL NOT NULL,
                locked_until_at REAL
            )
            """
        )

        # 刷新运行记录（用于“最近触发/来源/统计/运行中状态”的可验证性）
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS refresh_runs (
                id TEXT PRIMARY KEY,
                trigger_source TEXT NOT NULL,
                status TEXT NOT NULL,
                requested_by_ip TEXT,
                requested_by_user_agent TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP,
                total INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                message TEXT,
                trace_id TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_refresh_runs_started_at
            ON refresh_runs(started_at)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_refresh_runs_trigger_source
            ON refresh_runs(trigger_source)
            """
        )

        # 兼容旧 schema：补齐缺失列
        cursor.execute("PRAGMA table_info(accounts)")
        columns = [col[1] for col in cursor.fetchall()]

        if "group_id" not in columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN group_id INTEGER DEFAULT 1")
        if "remark" not in columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN remark TEXT")
        if "status" not in columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN status TEXT DEFAULT 'active'")
        if "updated_at" not in columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        if "last_refresh_at" not in columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN last_refresh_at TIMESTAMP")

        cursor.execute("PRAGMA table_info(groups)")
        group_columns = [col[1] for col in cursor.fetchall()]
        if "is_system" not in group_columns:
            cursor.execute("ALTER TABLE groups ADD COLUMN is_system INTEGER DEFAULT 0")
        if "proxy_url" not in group_columns:
            cursor.execute("ALTER TABLE groups ADD COLUMN proxy_url TEXT")

        cursor.execute("PRAGMA table_info(account_refresh_logs)")
        refresh_log_columns = [col[1] for col in cursor.fetchall()]
        if "run_id" not in refresh_log_columns:
            cursor.execute("ALTER TABLE account_refresh_logs ADD COLUMN run_id TEXT")

        cursor.execute("PRAGMA table_info(audit_logs)")
        audit_columns = [col[1] for col in cursor.fetchall()]
        if "trace_id" not in audit_columns:
            cursor.execute("ALTER TABLE audit_logs ADD COLUMN trace_id TEXT")

        # 默认分组
        cursor.execute(
            """
            INSERT OR IGNORE INTO groups (name, description, color)
            VALUES ('默认分组', '未分组的邮箱', '#666666')
            """
        )

        # 临时邮箱分组（系统分组）
        cursor.execute(
            """
            INSERT OR IGNORE INTO groups (name, description, color, is_system)
            VALUES ('临时邮箱', 'GPTMail 临时邮箱服务', '#00bcf2', 1)
            """
        )

        # 初始化默认设置：登录密码（自动迁移明文 -> 哈希）
        cursor.execute("SELECT value FROM settings WHERE key = 'login_password'")
        existing_password = cursor.fetchone()
        if existing_password:
            password_value = existing_password[0]
            if password_value and not is_password_hashed(password_value):
                hashed_password = hash_password(password_value)
                cursor.execute(
                    """
                    UPDATE settings SET value = ? WHERE key = 'login_password'
                    """,
                    (hashed_password,),
                )
        else:
            hashed_password = hash_password(login_password_default)
            cursor.execute(
                """
                INSERT INTO settings (key, value)
                VALUES ('login_password', ?)
                """,
                (hashed_password,),
            )

        cursor.execute(
            """
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('gptmail_api_key', ?)
            """,
            (gptmail_api_key_default,),
        )

        # 初始化刷新配置
        cursor.execute(
            """
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('refresh_interval_days', '30')
            """
        )
        cursor.execute(
            """
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('refresh_delay_seconds', '5')
            """
        )
        cursor.execute(
            """
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('refresh_cron', '0 2 * * *')
            """
        )
        cursor.execute(
            """
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('use_cron_schedule', 'false')
            """
        )
        cursor.execute(
            """
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('enable_scheduled_refresh', 'true')
            """
        )

        # 初始化轮询配置
        cursor.execute(
            """
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('enable_auto_polling', 'false')
            """
        )
        cursor.execute(
            """
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('polling_interval', '10')
            """
        )
        cursor.execute(
            """
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('polling_count', '5')
            """
        )

        # 索引（性能基线）
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_accounts_last_refresh_at
            ON accounts(last_refresh_at)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_accounts_status
            ON accounts(status)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_accounts_group_id
            ON accounts(group_id)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_account_refresh_logs_account_id
            ON account_refresh_logs(account_id)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_account_refresh_logs_account_id_id
            ON account_refresh_logs(account_id, id)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_account_tags_tag_id
            ON account_tags(tag_id)
            """
        )

        # 迁移现有明文数据为加密数据
        migrate_sensitive_data(conn)

        # 升级完成标记：写入 schema 版本，便于“升级可验证”
        cursor.execute(
            """
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (DB_SCHEMA_VERSION_KEY, str(DB_SCHEMA_VERSION)),
        )

        if upgrading and migration_id is not None:
            try:
                cursor.execute("RELEASE SAVEPOINT migration_work")
            except Exception:
                pass
            cursor.execute(
                """
                UPDATE schema_migrations
                SET status = 'success', finished_at = ?, error = NULL
                WHERE id = ?
                """,
                (time.time(), migration_id),
            )
            cursor.execute(
                """
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (DB_SCHEMA_LAST_UPGRADE_TRACE_ID_KEY, migration_trace_id),
            )
            cursor.execute(
                """
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, '', CURRENT_TIMESTAMP)
                """,
                (DB_SCHEMA_LAST_UPGRADE_ERROR_KEY,),
            )

        conn.commit()

    except Exception as e:
        error_text = sanitize_error_details(str(e))
        try:
            if upgrading and migration_id is not None:
                try:
                    cursor.execute("ROLLBACK TO SAVEPOINT migration_work")
                    cursor.execute("RELEASE SAVEPOINT migration_work")
                except Exception:
                    pass

                cursor.execute(
                    """
                    UPDATE schema_migrations
                    SET status = 'failed', finished_at = ?, error = ?
                    WHERE id = ?
                    """,
                    (time.time(), error_text, migration_id),
                )
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO settings (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    """,
                    (DB_SCHEMA_LAST_UPGRADE_TRACE_ID_KEY, migration_trace_id),
                )
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO settings (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    """,
                    (DB_SCHEMA_LAST_UPGRADE_ERROR_KEY, error_text),
                )
                conn.commit()
            else:
                conn.rollback()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def migrate_sensitive_data(conn: sqlite3.Connection):
    """迁移现有明文敏感数据为加密数据"""
    cursor = conn.cursor()

    # 获取所有账号
    cursor.execute("SELECT id, password, refresh_token FROM accounts")
    accounts = cursor.fetchall()

    migrated_count = 0
    for account_id, password, refresh_token in accounts:
        needs_update = False
        new_password = password
        new_refresh_token = refresh_token

        # 检查并加密 password
        if password and not is_encrypted(password):
            new_password = encrypt_data(password)
            needs_update = True

        # 检查并加密 refresh_token
        if refresh_token and not is_encrypted(refresh_token):
            new_refresh_token = encrypt_data(refresh_token)
            needs_update = True

        # 更新数据库
        if needs_update:
            cursor.execute(
                """
                UPDATE accounts
                SET password = ?, refresh_token = ?
                WHERE id = ?
                """,
                (new_password, new_refresh_token, account_id),
            )
            migrated_count += 1

    if migrated_count > 0:
        print(f"已迁移 {migrated_count} 个账号的敏感数据为加密存储")

