#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Outlook 邮件 Web 应用
基于 Flask 的 Web 界面，支持多邮箱管理和邮件查看
使用 SQLite 数据库存储邮箱信息，支持分组管理
支持 GPTMail 临时邮箱服务
"""

import email
import imaplib
import sqlite3
import os
import hashlib
import secrets
import time
import json
import re
import uuid
import bcrypt
import base64
import html
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from typing import Optional, List, Dict, Any
from pathlib import Path
from urllib.parse import quote
from flask import Flask, render_template, request, jsonify, g, session, redirect, url_for, Response
from functools import wraps
import requests
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from werkzeug.exceptions import HTTPException

from outlook_web import config
from outlook_web.errors import build_error_payload, generate_trace_id, sanitize_error_details
from outlook_web.security.crypto import (
    decrypt_data,
    encrypt_data,
    get_cipher,
    get_encryption_key,
    hash_password,
    is_encrypted,
    is_password_hashed,
    verify_password,
)
from outlook_web.db import (
    DB_SCHEMA_LAST_UPGRADE_ERROR_KEY,
    DB_SCHEMA_LAST_UPGRADE_TRACE_ID_KEY,
    DB_SCHEMA_VERSION,
    DB_SCHEMA_VERSION_KEY,
    create_sqlite_connection,
    get_db,
    init_db,
    migrate_sensitive_data,
    register_db,
)
from outlook_web.security.auth import (
    ATTEMPT_WINDOW,
    EXPORT_VERIFY_TOKEN_TTL_SECONDS,
    LOCKOUT_DURATION,
    MAX_LOGIN_ATTEMPTS,
    check_rate_limit,
    check_export_verify_token,
    consume_export_verify_token,
    get_client_ip,
    get_user_agent,
    issue_export_verify_token,
    login_required,
    record_login_failure,
    reset_login_attempts,
)
from outlook_web.security.csrf import CSRF_AVAILABLE, init_csrf
from outlook_web.audit import log_audit, query_audit_logs

_REPO_ROOT = Path(__file__).resolve().parents[1]

app = Flask(
    __name__,
    template_folder=str(_REPO_ROOT / "templates"),
    static_folder=str(_REPO_ROOT / "static"),
    static_url_path="/static",
)
# 强制从环境变量读取 secret_key，不提供默认值以防止安全漏洞
secret_key = config.require_secret_key()
app.secret_key = secret_key
# 设置 session 过期时间（默认 7 天）
app.config['PERMANENT_SESSION_LIFETIME'] = 60 * 60 * 24 * 7  # 7 天

# Session Cookie 配置（适用于 HTTPS 代理环境）
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# 信任代理头（适用于反向代理环境）
# 这确保 Flask 正确识别 HTTPS 请求
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# DB teardown（请求结束释放连接）
register_db(app)



# 初始化 CSRF 保护（如果可用）
csrf, csrf_exempt, generate_csrf = init_csrf(app)

# 登录密码配置（可以修改为你想要的密码）
LOGIN_PASSWORD = config.get_login_password_default()

# ==================== 配置 ====================
# Token 端点
TOKEN_URL_LIVE = "https://login.live.com/oauth20_token.srf"
TOKEN_URL_GRAPH = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
TOKEN_URL_IMAP = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"

# IMAP 服务器配置
IMAP_SERVER_OLD = "outlook.office365.com"
IMAP_SERVER_NEW = "outlook.live.com"
IMAP_PORT = 993

# 数据库文件
DATABASE = config.get_database_path()

# GPTMail API 配置
GPTMAIL_BASE_URL = config.get_gptmail_base_url()
GPTMAIL_API_KEY = config.get_gptmail_api_key_default()  # 测试 API Key，可以修改为正式 Key

# 临时邮箱分组 ID（系统保留）
TEMP_EMAIL_GROUP_ID = -1

# OAuth 配置
OAUTH_CLIENT_ID = config.get_oauth_client_id()
OAUTH_REDIRECT_URI = config.get_oauth_redirect_uri()
OAUTH_SCOPES = [
    "offline_access",
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/User.Read"
]


#
# 密码/加密工具已模块化到 outlook_web.security.crypto
#


# ==================== 错误处理工具 ====================
def utcnow() -> datetime:
    """返回 naive UTC 时间（等价于旧的 datetime.utcnow()），避免 Python 3.13+ deprecation warning。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@app.before_request
def ensure_trace_id():
    """为每个请求生成/透传 trace_id，便于前后端统一追踪"""
    incoming = request.headers.get('X-Trace-Id') or request.headers.get('X-Request-Id')
    if incoming:
        incoming = incoming.strip()
        g.trace_id = incoming[:64]
    else:
        g.trace_id = generate_trace_id()


def summarize_fallback_failures(method_errors: Dict[str, Any], labels: Dict[str, str]) -> str:
    """将多方式回退的失败原因聚合成“中文可理解”的摘要文本（用于 error.details 展示）。"""
    lines: List[str] = []

    for key, label in labels.items():
        if key not in method_errors:
            continue
        err = method_errors.get(key)
        if err is None:
            text = "未知错误"
        elif isinstance(err, dict):
            msg = (err.get("message") or err.get("error") or "").strip()
            code = (err.get("code") or "").strip()
            status = err.get("status")
            meta_parts: List[str] = []
            if code:
                meta_parts.append(f"code={code}")
            if status:
                meta_parts.append(f"status={status}")
            meta = f" ({', '.join(meta_parts)})" if meta_parts else ""
            if msg:
                text = f"{msg}{meta}"
            else:
                raw = json.dumps(err, ensure_ascii=False)
                text = raw[:400] + ("..." if len(raw) > 400 else "")
        elif isinstance(err, list):
            preview_items = [str(x) for x in err[:3]]
            preview = "; ".join(preview_items)
            if len(err) > 3:
                preview += f" ...(共 {len(err)} 条)"
            text = preview
        else:
            text = str(err)

        lines.append(f"{label}：{text}")

    return "\n".join(lines).strip()


@app.after_request
def attach_trace_id_and_normalize_errors(response):
    """统一写入 X-Trace-Id，并把 legacy 的字符串错误格式标准化为结构化错误"""
    trace_id_value = None
    try:
        trace_id_value = getattr(g, 'trace_id', None)
        if trace_id_value:
            response.headers.setdefault('X-Trace-Id', trace_id_value)
    except Exception:
        trace_id_value = None

    try:
        if response.is_streamed:
            return response

        content_type = response.headers.get('Content-Type', '') or ''
        if not content_type.startswith('application/json'):
            return response

        data = response.get_json(silent=True)
        if not isinstance(data, dict):
            return response

        if data.get('success') is not False:
            return response

        # 统一补齐 trace_id/status 等字段
        if isinstance(data.get('error'), dict):
            error_obj = dict(data['error'])
            mutated = False
            if not error_obj.get('trace_id') and trace_id_value:
                error_obj['trace_id'] = trace_id_value
                mutated = True
            if not error_obj.get('status'):
                error_obj['status'] = response.status_code if response.status_code >= 400 else 400
                mutated = True
            if not error_obj.get('code'):
                error_obj['code'] = 'UNKNOWN_ERROR'
                mutated = True
            if not error_obj.get('message'):
                error_obj['message'] = '请求失败'
                mutated = True
            if mutated:
                new_data = dict(data)
                new_data['error'] = error_obj
                response.set_data(json.dumps(new_data, ensure_ascii=False))
            return response

        # legacy：error 为字符串
        if isinstance(data.get('error'), str):
            legacy_message = data.get('error') or '请求失败'
            status_for_payload = response.status_code if response.status_code >= 400 else 400
            error_payload = build_error_payload(
                code='LEGACY_ERROR',
                message=legacy_message,
                err_type='LegacyError',
                status=status_for_payload,
                details='',
                trace_id=trace_id_value
            )
            new_data = dict(data)
            new_data['error'] = error_payload
            response.set_data(json.dumps(new_data, ensure_ascii=False))
            return response
    except Exception:
        return response

    return response


def get_response_details(response: requests.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text or response.reason


# ==================== 数据库操作 ====================

def create_sqlite_connection() -> sqlite3.Connection:
    """创建 SQLite 连接（带基础一致性/并发配置）"""
    conn = sqlite3.connect(DATABASE, timeout=30)
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


def get_db():
    """获取数据库连接"""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = create_sqlite_connection()
    return db


def init_db():
    """初始化数据库（含升级记录与可验证状态）"""
    db_existed = False
    try:
        db_existed = os.path.exists(DATABASE) and os.path.getsize(DATABASE) > 0
    except Exception:
        db_existed = False

    conn = create_sqlite_connection()
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
        cursor.execute('BEGIN IMMEDIATE')

        # 创建设置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 数据库迁移记录（用于升级可验证/可诊断）
        cursor.execute('''
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
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_schema_migrations_started_at
            ON schema_migrations(started_at)
        ''')

        # 在锁内读取当前 schema 版本（保证一致性）
        row = cursor.execute(
            "SELECT value FROM settings WHERE key = ?",
            (DB_SCHEMA_VERSION_KEY,)
        ).fetchone()
        try:
            current_version = int(row['value']) if row and row['value'] is not None else 0
        except Exception:
            current_version = 0

        upgrading = current_version < DB_SCHEMA_VERSION
        if upgrading:
            migration_trace_id = generate_trace_id()
            if db_existed:
                try:
                    print("=" * 60)
                    print(f"[升级提示] 检测到数据库需要升级：v{current_version} -> v{DB_SCHEMA_VERSION}")
                    print(f"[升级提示] 强烈建议先备份数据库文件：{DATABASE}")
                    print(f"[升级提示] 示例：cp \"{DATABASE}\" \"{DATABASE}.backup\"")
                    print(f"[升级提示] trace_id={migration_trace_id}")
                    print("=" * 60)
                except Exception:
                    pass

            cursor.execute('''
                INSERT INTO schema_migrations (from_version, to_version, status, started_at, trace_id)
                VALUES (?, ?, 'running', ?, ?)
            ''', (current_version, DB_SCHEMA_VERSION, time.time(), migration_trace_id))
            migration_id = cursor.lastrowid
            cursor.execute("SAVEPOINT migration_work")

        # -------------------- Schema 创建/迁移（幂等） --------------------

        # 分组表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                color TEXT DEFAULT '#1a1a1a',
                proxy_url TEXT,
                is_system INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 邮箱账号表
        cursor.execute('''
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
        ''')

        # 临时邮箱表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS temp_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 临时邮件表（存储从 GPTMail 获取的邮件）
        cursor.execute('''
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
        ''')

        # 刷新记录表（账号级）
        cursor.execute('''
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
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_account_refresh_logs_run_id
            ON account_refresh_logs(run_id)
        ''')

        # 审计日志表
        cursor.execute('''
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
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_audit_logs_trace_id
            ON audit_logs(trace_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at
            ON audit_logs(created_at)
        ''')

        # 标签表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                color TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 账号标签关联表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS account_tags (
                account_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (account_id, tag_id),
                FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags (id) ON DELETE CASCADE
            )
        ''')

        # 分布式锁（用于刷新冲突控制/多进程一致性）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS distributed_locks (
                name TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                acquired_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
        ''')

        # 导出二次验证 Token（持久化，支持重启/多进程）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS export_verify_tokens (
                token TEXT PRIMARY KEY,
                ip TEXT,
                user_agent TEXT,
                expires_at REAL NOT NULL,
                created_at REAL NOT NULL
            )
        ''')

        # 登录速率限制（持久化，支持重启/多进程）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS login_attempts (
                ip TEXT PRIMARY KEY,
                count INTEGER NOT NULL,
                last_attempt_at REAL NOT NULL,
                locked_until_at REAL
            )
        ''')

        # 刷新运行记录（用于“最近触发/来源/统计/运行中状态”的可验证性）
        cursor.execute('''
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
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_refresh_runs_started_at
            ON refresh_runs(started_at)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_refresh_runs_trigger_source
            ON refresh_runs(trigger_source)
        ''')

        # 兼容旧 schema：补齐缺失列
        cursor.execute("PRAGMA table_info(accounts)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'group_id' not in columns:
            cursor.execute('ALTER TABLE accounts ADD COLUMN group_id INTEGER DEFAULT 1')
        if 'remark' not in columns:
            cursor.execute('ALTER TABLE accounts ADD COLUMN remark TEXT')
        if 'status' not in columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN status TEXT DEFAULT 'active'")
        if 'updated_at' not in columns:
            cursor.execute('ALTER TABLE accounts ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        if 'last_refresh_at' not in columns:
            cursor.execute('ALTER TABLE accounts ADD COLUMN last_refresh_at TIMESTAMP')

        cursor.execute("PRAGMA table_info(groups)")
        group_columns = [col[1] for col in cursor.fetchall()]
        if 'is_system' not in group_columns:
            cursor.execute('ALTER TABLE groups ADD COLUMN is_system INTEGER DEFAULT 0')
        if 'proxy_url' not in group_columns:
            cursor.execute('ALTER TABLE groups ADD COLUMN proxy_url TEXT')

        cursor.execute("PRAGMA table_info(account_refresh_logs)")
        refresh_log_columns = [col[1] for col in cursor.fetchall()]
        if 'run_id' not in refresh_log_columns:
            cursor.execute('ALTER TABLE account_refresh_logs ADD COLUMN run_id TEXT')

        cursor.execute("PRAGMA table_info(audit_logs)")
        audit_columns = [col[1] for col in cursor.fetchall()]
        if 'trace_id' not in audit_columns:
            cursor.execute('ALTER TABLE audit_logs ADD COLUMN trace_id TEXT')

        # 默认分组
        cursor.execute('''
            INSERT OR IGNORE INTO groups (name, description, color)
            VALUES ('默认分组', '未分组的邮箱', '#666666')
        ''')

        # 临时邮箱分组（系统分组）
        cursor.execute('''
            INSERT OR IGNORE INTO groups (name, description, color, is_system)
            VALUES ('临时邮箱', 'GPTMail 临时邮箱服务', '#00bcf2', 1)
        ''')

        # 初始化默认设置：登录密码（自动迁移明文 -> 哈希）
        cursor.execute("SELECT value FROM settings WHERE key = 'login_password'")
        existing_password = cursor.fetchone()
        if existing_password:
            password_value = existing_password[0]
            if password_value and not is_password_hashed(password_value):
                hashed_password = hash_password(password_value)
                cursor.execute('''
                    UPDATE settings SET value = ? WHERE key = 'login_password'
                ''', (hashed_password,))
        else:
            hashed_password = hash_password(LOGIN_PASSWORD)
            cursor.execute('''
                INSERT INTO settings (key, value)
                VALUES ('login_password', ?)
            ''', (hashed_password,))

        cursor.execute('''
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('gptmail_api_key', ?)
        ''', (GPTMAIL_API_KEY,))

        # 初始化刷新配置
        cursor.execute('''
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('refresh_interval_days', '30')
        ''')
        cursor.execute('''
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('refresh_delay_seconds', '5')
        ''')
        cursor.execute('''
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('refresh_cron', '0 2 * * *')
        ''')
        cursor.execute('''
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('use_cron_schedule', 'false')
        ''')
        cursor.execute('''
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('enable_scheduled_refresh', 'true')
        ''')

        # 索引（性能基线）
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_accounts_last_refresh_at
            ON accounts(last_refresh_at)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_accounts_status
            ON accounts(status)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_accounts_group_id
            ON accounts(group_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_account_refresh_logs_account_id
            ON account_refresh_logs(account_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_account_refresh_logs_account_id_id
            ON account_refresh_logs(account_id, id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_account_tags_tag_id
            ON account_tags(tag_id)
        ''')

        # 迁移现有明文数据为加密数据
        migrate_sensitive_data(conn)

        # 升级完成标记：写入 schema 版本，便于“升级可验证”
        cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (DB_SCHEMA_VERSION_KEY, str(DB_SCHEMA_VERSION)))

        if upgrading and migration_id is not None:
            try:
                cursor.execute("RELEASE SAVEPOINT migration_work")
            except Exception:
                pass
            cursor.execute('''
                UPDATE schema_migrations
                SET status = 'success', finished_at = ?, error = NULL
                WHERE id = ?
            ''', (time.time(), migration_id))
            cursor.execute('''
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (DB_SCHEMA_LAST_UPGRADE_TRACE_ID_KEY, migration_trace_id))
            cursor.execute('''
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, '', CURRENT_TIMESTAMP)
            ''', (DB_SCHEMA_LAST_UPGRADE_ERROR_KEY,))

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

                cursor.execute('''
                    UPDATE schema_migrations
                    SET status = 'failed', finished_at = ?, error = ?
                    WHERE id = ?
                ''', (time.time(), error_text, migration_id))
                cursor.execute('''
                    INSERT OR REPLACE INTO settings (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                ''', (DB_SCHEMA_LAST_UPGRADE_TRACE_ID_KEY, migration_trace_id))
                cursor.execute('''
                    INSERT OR REPLACE INTO settings (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                ''', (DB_SCHEMA_LAST_UPGRADE_ERROR_KEY, error_text))
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


def migrate_sensitive_data(conn):
    """迁移现有明文敏感数据为加密数据"""
    cursor = conn.cursor()

    # 获取所有账号
    cursor.execute('SELECT id, password, refresh_token FROM accounts')
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
            cursor.execute('''
                UPDATE accounts
                SET password = ?, refresh_token = ?
                WHERE id = ?
            ''', (new_password, new_refresh_token, account_id))
            migrated_count += 1

    if migrated_count > 0:
        print(f"已迁移 {migrated_count} 个账号的敏感数据为加密存储")


# 兼容导出：数据库实现已集中到 outlook_web.db（迁移期保留旧函数名）
from outlook_web import db as _db  # noqa: E402

create_sqlite_connection = _db.create_sqlite_connection
get_db = _db.get_db
init_db = _db.init_db
migrate_sensitive_data = _db.migrate_sensitive_data


# ==================== 应用初始化 ====================

_APP_INITIALIZED = False

def init_app():
    """初始化应用（确保目录和数据库存在）"""
    global _APP_INITIALIZED
    if _APP_INITIALIZED:
        return

    # 确保 templates/static 目录存在（支持零构建前端拆分）
    try:
        (_REPO_ROOT / "templates").mkdir(parents=True, exist_ok=True)
    except Exception:
        os.makedirs("templates", exist_ok=True)

    try:
        (_REPO_ROOT / "static").mkdir(parents=True, exist_ok=True)
    except Exception:
        os.makedirs("static", exist_ok=True)

    # 确保数据目录存在
    data_dir = os.path.dirname(DATABASE)
    if data_dir:
        os.makedirs(data_dir, exist_ok=True)
    
    # 初始化数据库
    init_db()
    
    print("=" * 60)
    print("Outlook 邮件 Web 应用已初始化")
    print(f"数据库文件: {DATABASE}")
    print(f"GPTMail API: {GPTMAIL_BASE_URL}")
    print("=" * 60)

    _APP_INITIALIZED = True

# 注意：应用初始化由 outlook_web.app:create_app() 调用（避免 import-time 副作用）


# ==================== 设置操作 ====================
# 注：settings 相关函数已迁移到 outlook_web.repositories.settings，见第1275-1279行 re-export

# ==================== 分组操作 ====================
# 注：groups 相关函数已迁移到 outlook_web.repositories.groups，见第1281-1287行 re-export

# ==================== 邮箱账号操作 ====================

def load_accounts(group_id: int = None) -> List[Dict]:
    """从数据库加载邮箱账号"""
    db = get_db()
    if group_id:
        cursor = db.execute('''
            SELECT a.*, g.name as group_name, g.color as group_color
            FROM accounts a
            LEFT JOIN groups g ON a.group_id = g.id
            WHERE a.group_id = ?
            ORDER BY a.created_at DESC
        ''', (group_id,))
    else:
        cursor = db.execute('''
            SELECT a.*, g.name as group_name, g.color as group_color
            FROM accounts a
            LEFT JOIN groups g ON a.group_id = g.id
            ORDER BY a.created_at DESC
        ''')
    rows = cursor.fetchall()

    # 批量加载标签，避免 N+1 查询（1,000 账号场景）
    tags_by_account: Dict[int, List[Dict[str, Any]]] = {}
    account_ids: List[int] = []
    try:
        account_ids = [int(r['id']) for r in rows]
    except Exception:
        account_ids = []

    if account_ids:
        try:
            placeholders = ",".join(["?"] * len(account_ids))
            tag_rows = db.execute(f'''
                SELECT at.account_id as account_id, t.*
                FROM account_tags at
                JOIN tags t ON t.id = at.tag_id
                WHERE at.account_id IN ({placeholders})
                ORDER BY at.account_id ASC, t.created_at DESC
            ''', account_ids).fetchall()

            for tr in tag_rows:
                tag_dict = dict(tr)
                acc_id = tag_dict.pop('account_id', None)
                if acc_id is None:
                    continue
                tags_by_account.setdefault(int(acc_id), []).append(tag_dict)
        except Exception:
            tags_by_account = {}

    accounts: List[Dict[str, Any]] = []
    for row in rows:
        account = dict(row)

        # 解密敏感字段
        if account.get('password'):
            try:
                account['password'] = decrypt_data(account['password'])
            except Exception:
                pass  # 解密失败保持原值
        if account.get('refresh_token'):
            try:
                account['refresh_token'] = decrypt_data(account['refresh_token'])
            except Exception:
                pass  # 解密失败保持原值

        account_id_value = account.get('id')
        try:
            account_id_value = int(account_id_value)
        except Exception:
            account_id_value = None

        account['tags'] = tags_by_account.get(account_id_value, []) if account_id_value is not None else []
        accounts.append(account)
    return accounts


# ==================== 标签管理 ====================

def get_tags() -> List[Dict]:
    """获取所有标签"""
    db = get_db()
    cursor = db.execute('SELECT * FROM tags ORDER BY created_at DESC')
    return [dict(row) for row in cursor.fetchall()]


def add_tag(name: str, color: str) -> Optional[int]:
    """添加标签"""
    db = get_db()
    try:
        cursor = db.execute(
            'INSERT INTO tags (name, color) VALUES (?, ?)',
            (name, color)
        )
        db.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None


def delete_tag(tag_id: int) -> bool:
    """删除标签"""
    db = get_db()
    cursor = db.execute('DELETE FROM tags WHERE id = ?', (tag_id,))
    db.commit()
    return cursor.rowcount > 0


def get_account_tags(account_id: int) -> List[Dict]:
    """获取账号的标签"""
    db = get_db()
    cursor = db.execute('''
        SELECT t.*
        FROM tags t
        JOIN account_tags at ON t.id = at.tag_id
        WHERE at.account_id = ?
        ORDER BY t.created_at DESC
    ''', (account_id,))
    return [dict(row) for row in cursor.fetchall()]


def add_account_tag(account_id: int, tag_id: int) -> bool:
    """给账号添加标签"""
    db = get_db()
    try:
        db.execute(
            'INSERT OR IGNORE INTO account_tags (account_id, tag_id) VALUES (?, ?)',
            (account_id, tag_id)
        )
        db.commit()
        return True
    except Exception:
        return False


def remove_account_tag(account_id: int, tag_id: int) -> bool:
    """移除账号标签"""
    db = get_db()
    db.execute(
        'DELETE FROM account_tags WHERE account_id = ? AND tag_id = ?',
        (account_id, tag_id)
    )
    db.commit()
    return True



def get_account_by_email(email_addr: str) -> Optional[Dict]:
    """根据邮箱地址获取账号"""
    db = get_db()
    cursor = db.execute('SELECT * FROM accounts WHERE email = ?', (email_addr,))
    row = cursor.fetchone()
    if not row:
        return None
    account = dict(row)
    # 解密敏感字段
    if account.get('password'):
        try:
            account['password'] = decrypt_data(account['password'])
        except Exception:
            pass
    if account.get('refresh_token'):
        try:
            account['refresh_token'] = decrypt_data(account['refresh_token'])
        except Exception:
            pass
    return account


def get_account_by_id(account_id: int) -> Optional[Dict]:
    """根据 ID 获取账号"""
    db = get_db()
    cursor = db.execute('''
        SELECT a.*, g.name as group_name, g.color as group_color
        FROM accounts a
        LEFT JOIN groups g ON a.group_id = g.id
        WHERE a.id = ?
    ''', (account_id,))
    row = cursor.fetchone()
    if not row:
        return None
    account = dict(row)
    # 解密敏感字段
    if account.get('password'):
        try:
            account['password'] = decrypt_data(account['password'])
        except Exception:
            pass
    if account.get('refresh_token'):
        try:
            account['refresh_token'] = decrypt_data(account['refresh_token'])
        except Exception:
            pass
    return account


def add_account(
    email_addr: str,
    password: str,
    client_id: str,
    refresh_token: str,
    group_id: int = 1,
    remark: str = '',
    db: Optional[sqlite3.Connection] = None,
    commit: bool = True
) -> bool:
    """添加邮箱账号"""
    db = db or get_db()
    try:
        # 加密敏感字段
        encrypted_password = encrypt_data(password) if password else password
        encrypted_refresh_token = encrypt_data(refresh_token) if refresh_token else refresh_token

        db.execute('''
            INSERT INTO accounts (email, password, client_id, refresh_token, group_id, remark)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (email_addr, encrypted_password, client_id, encrypted_refresh_token, group_id, remark))
        if commit:
            db.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    except Exception:
        return False


def update_account(account_id: int, email_addr: str, password: Optional[str], client_id: Optional[str],
                   refresh_token: Optional[str], group_id: int, remark: str, status: str) -> bool:
    """更新邮箱账号"""
    db = get_db()
    try:
        existing = db.execute('''
            SELECT password, client_id, refresh_token
            FROM accounts
            WHERE id = ?
        ''', (account_id,)).fetchone()
        if not existing:
            return False

        new_client_id = client_id.strip() if isinstance(client_id, str) and client_id.strip() else existing['client_id']

        encrypted_password = existing['password']
        if isinstance(password, str) and password.strip():
            encrypted_password = encrypt_data(password)

        encrypted_refresh_token = existing['refresh_token']
        if isinstance(refresh_token, str) and refresh_token.strip():
            encrypted_refresh_token = encrypt_data(refresh_token)

        if not email_addr or not new_client_id or not encrypted_refresh_token:
            return False

        db.execute('''
            UPDATE accounts
            SET email = ?, password = ?, client_id = ?, refresh_token = ?,
                group_id = ?, remark = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (email_addr, encrypted_password, new_client_id, encrypted_refresh_token, group_id, remark, status, account_id))
        db.commit()
        return True
    except Exception:
        return False


def delete_account_by_id(account_id: int) -> bool:
    """删除邮箱账号"""
    db = get_db()
    try:
        db.execute('DELETE FROM accounts WHERE id = ?', (account_id,))
        db.commit()
        return True
    except Exception:
        return False


def delete_account_by_email(email_addr: str) -> bool:
    """根据邮箱地址删除账号"""
    db = get_db()
    try:
        db.execute('DELETE FROM accounts WHERE email = ?', (email_addr,))
        db.commit()
        return True
    except Exception:
        return False


# 兼容导出：repositories（SQL）已模块化到 outlook_web.repositories.*
from outlook_web.repositories import accounts as _accounts_repo  # noqa: E402
from outlook_web.repositories import groups as _groups_repo  # noqa: E402
from outlook_web.repositories import settings as _settings_repo  # noqa: E402
from outlook_web.repositories import tags as _tags_repo  # noqa: E402

get_setting = _settings_repo.get_setting
set_setting = _settings_repo.set_setting
get_all_settings = _settings_repo.get_all_settings
get_login_password = _settings_repo.get_login_password
get_gptmail_api_key = _settings_repo.get_gptmail_api_key

load_groups = _groups_repo.load_groups
get_group_by_id = _groups_repo.get_group_by_id
add_group = _groups_repo.add_group
update_group = _groups_repo.update_group
get_default_group_id = _groups_repo.get_default_group_id
delete_group = _groups_repo.delete_group
get_group_account_count = _groups_repo.get_group_account_count

load_accounts = _accounts_repo.load_accounts
get_account_by_email = _accounts_repo.get_account_by_email
get_account_by_id = _accounts_repo.get_account_by_id
add_account = _accounts_repo.add_account
update_account = _accounts_repo.update_account
delete_account_by_id = _accounts_repo.delete_account_by_id
delete_account_by_email = _accounts_repo.delete_account_by_email

get_tags = _tags_repo.get_tags
add_tag = _tags_repo.add_tag
delete_tag = _tags_repo.delete_tag
get_account_tags = _tags_repo.get_account_tags
add_account_tag = _tags_repo.add_account_tag
remove_account_tag = _tags_repo.remove_account_tag


# ==================== 工具函数 ====================

def sanitize_input(text: str, max_length: int = 500) -> str:
    """
    净化用户输入，防止XSS攻击
    - 转义HTML特殊字符
    - 限制长度
    - 移除控制字符
    """
    if not text:
        return ""

    # 限制长度
    text = text[:max_length]

    # 移除控制字符（保留换行和制表符）
    text = ''.join(char for char in text if char.isprintable() or char in '\n\t')

    # 转义HTML特殊字符
    text = html.escape(text, quote=True)

    return text


def decode_header_value(header_value: str) -> str:
    """解码邮件头字段"""
    if not header_value:
        return ""
    try:
        decoded_parts = decode_header(str(header_value))
        decoded_string = ""
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                try:
                    decoded_string += part.decode(charset if charset else 'utf-8', 'replace')
                except (LookupError, UnicodeDecodeError):
                    decoded_string += part.decode('utf-8', 'replace')
            else:
                decoded_string += str(part)
        return decoded_string
    except Exception:
        return str(header_value) if header_value else ""


def get_email_body(msg) -> str:
    """提取邮件正文"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or 'utf-8'
                    body = payload.decode(charset, errors='replace')
                    break
                except Exception:
                    continue
            elif content_type == "text/html" and "attachment" not in content_disposition and not body:
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or 'utf-8'
                    body = payload.decode(charset, errors='replace')
                except Exception:
                    continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or 'utf-8'
            body = payload.decode(charset, errors='replace')
        except Exception:
            body = str(msg.get_payload())
    
    return body


def parse_account_string(account_str: str) -> Optional[Dict]:
    """
    解析账号字符串
    格式: email----password----client_id----refresh_token
    """
    parts = account_str.strip().split('----')
    if len(parts) >= 4:
        return {
            'email': parts[0].strip(),
            'password': parts[1],
            'client_id': parts[2].strip(),
            # refresh_token 可能包含 '----'，这里把剩余部分合并回去
            'refresh_token': '----'.join(parts[3:]).strip()
        }
    return None


# ==================== Graph API 方式 ====================


def build_proxies(proxy_url: str) -> Optional[Dict[str, str]]:
    """构建 requests 的 proxies 参数"""
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def get_access_token_graph_result(client_id: str, refresh_token: str, proxy_url: str = None) -> Dict[str, Any]:
    """获取 Graph API access_token（包含错误详情）"""
    try:
        proxies = build_proxies(proxy_url)
        res = requests.post(
            TOKEN_URL_GRAPH,
            data={
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": "https://graph.microsoft.com/.default"
            },
            timeout=30,
            proxies=proxies
        )

        if res.status_code != 200:
            details = get_response_details(res)
            return {
                "success": False,
                "error": build_error_payload(
                    "GRAPH_TOKEN_FAILED",
                    "获取访问令牌失败",
                    "GraphAPIError",
                    res.status_code,
                    details
                )
            }

        payload = res.json()
        access_token = payload.get("access_token")
        if not access_token:
            return {
                "success": False,
                "error": build_error_payload(
                    "GRAPH_TOKEN_MISSING",
                    "获取访问令牌失败",
                    "GraphAPIError",
                    res.status_code,
                    payload
                )
            }

        return {"success": True, "access_token": access_token}
    except Exception as exc:
        return {
            "success": False,
            "error": build_error_payload(
                "GRAPH_TOKEN_EXCEPTION",
                "获取访问令牌失败",
                type(exc).__name__,
                500,
                str(exc)
            )
        }


def get_access_token_graph(client_id: str, refresh_token: str, proxy_url: str = None) -> Optional[str]:
    """获取 Graph API access_token"""
    result = get_access_token_graph_result(client_id, refresh_token, proxy_url)
    if result.get("success"):
        return result.get("access_token")
    return None


def get_emails_graph(client_id: str, refresh_token: str, folder: str = 'inbox', skip: int = 0, top: int = 20, proxy_url: str = None) -> Dict[str, Any]:
    """使用 Graph API 获取邮件列表（支持分页和文件夹选择）"""
    token_result = get_access_token_graph_result(client_id, refresh_token, proxy_url)
    if not token_result.get("success"):
        return {"success": False, "error": token_result.get("error")}

    access_token = token_result.get("access_token")

    try:
        # 根据文件夹类型选择 API 端点
        # 使用 Well-known folder names，这些是 Microsoft Graph API 的标准文件夹名称
        folder_map = {
            'inbox': 'inbox',
            'junkemail': 'junkemail',  # 垃圾邮件的标准名称
            'deleteditems': 'deleteditems',  # 已删除邮件的标准名称
            'trash': 'deleteditems'  # 垃圾箱的别名
        }
        folder_name = folder_map.get(folder.lower(), 'inbox')

        url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder_name}/messages"
        params = {
            "$top": top,
            "$skip": skip,
            "$select": "id,subject,from,receivedDateTime,isRead,hasAttachments,bodyPreview",
            "$orderby": "receivedDateTime desc"
        }
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Prefer": "outlook.body-content-type='text'"
        }

        proxies = build_proxies(proxy_url)
        res = requests.get(url, headers=headers, params=params, timeout=30, proxies=proxies)

        if res.status_code != 200:
            details = get_response_details(res)
            return {
                "success": False,
                "error": build_error_payload(
                    "EMAIL_FETCH_FAILED",
                    "获取邮件失败，请检查账号配置",
                    "GraphAPIError",
                    res.status_code,
                    details
                )
            }

        return {"success": True, "emails": res.json().get("value", [])}
    except Exception as exc:
        return {
            "success": False,
            "error": build_error_payload(
                "EMAIL_FETCH_FAILED",
                "获取邮件失败，请检查账号配置",
                type(exc).__name__,
                500,
                str(exc)
            )
        }


def get_email_detail_graph(client_id: str, refresh_token: str, message_id: str, proxy_url: str = None) -> Optional[Dict]:
    """使用 Graph API 获取邮件详情"""
    access_token = get_access_token_graph(client_id, refresh_token, proxy_url)
    if not access_token:
        return None
    
    try:
        url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}"
        params = {
            "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,isRead,hasAttachments,body,bodyPreview"
        }
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Prefer": "outlook.body-content-type='html'"
        }
        
        proxies = build_proxies(proxy_url)
        res = requests.get(url, headers=headers, params=params, timeout=30, proxies=proxies)
        
        if res.status_code != 200:
            return None
        
        return res.json()
    except Exception:
        return None


# ==================== IMAP 方式 ====================

def get_access_token_imap_result(client_id: str, refresh_token: str) -> Dict[str, Any]:
    """获取 IMAP access_token（包含错误详情）"""
    try:
        res = requests.post(
            TOKEN_URL_IMAP,
            data={
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
            },
            timeout=30
        )

        if res.status_code != 200:
            details = get_response_details(res)
            return {
                "success": False,
                "error": build_error_payload(
                    "IMAP_TOKEN_FAILED",
                    "获取访问令牌失败",
                    "IMAPError",
                    res.status_code,
                    details
                )
            }

        payload = res.json()
        access_token = payload.get("access_token")
        if not access_token:
            return {
                "success": False,
                "error": build_error_payload(
                    "IMAP_TOKEN_MISSING",
                    "获取访问令牌失败",
                    "IMAPError",
                    res.status_code,
                    payload
                )
            }

        return {"success": True, "access_token": access_token}
    except Exception as exc:
        return {
            "success": False,
            "error": build_error_payload(
                "IMAP_TOKEN_EXCEPTION",
                "获取访问令牌失败",
                type(exc).__name__,
                500,
                str(exc)
            )
        }


def get_access_token_imap(client_id: str, refresh_token: str) -> Optional[str]:
    """获取 IMAP access_token"""
    result = get_access_token_imap_result(client_id, refresh_token)
    if result.get("success"):
        return result.get("access_token")
    return None


def get_emails_imap(account: str, client_id: str, refresh_token: str, folder: str = 'inbox', skip: int = 0, top: int = 20) -> Dict[str, Any]:
    """使用 IMAP 获取邮件列表（支持分页和文件夹选择）- 默认使用新版服务器"""
    return get_emails_imap_with_server(account, client_id, refresh_token, folder, skip, top, IMAP_SERVER_NEW)


def get_emails_imap_with_server(account: str, client_id: str, refresh_token: str, folder: str = 'inbox', skip: int = 0, top: int = 20, server: str = IMAP_SERVER_NEW) -> Dict[str, Any]:
    """使用 IMAP 获取邮件列表（支持分页、文件夹选择和服务器选择）"""
    token_result = get_access_token_imap_result(client_id, refresh_token)
    if not token_result.get("success"):
        return {"success": False, "error": token_result.get("error")}

    access_token = token_result.get("access_token")

    connection = None
    try:
        connection = imaplib.IMAP4_SSL(server, IMAP_PORT)
        auth_string = f"user={account}\1auth=Bearer {access_token}\1\1".encode('utf-8')
        connection.authenticate('XOAUTH2', lambda x: auth_string)

        # 根据文件夹类型选择 IMAP 文件夹
        # 尝试多种可能的文件夹名称
        folder_map = {
            'inbox': ['"INBOX"', 'INBOX'],
            'junkemail': ['"Junk"', '"Junk Email"', 'Junk', '"垃圾邮件"'],
            'deleteditems': ['"Deleted"', '"Deleted Items"', '"Trash"', 'Deleted', '"已删除邮件"'],
            'trash': ['"Deleted"', '"Deleted Items"', '"Trash"', 'Deleted', '"已删除邮件"']
        }
        possible_folders = folder_map.get(folder.lower(), ['"INBOX"'])

        # 尝试选择文件夹
        selected_folder = None
        last_error = None
        for imap_folder in possible_folders:
            try:
                status, response = connection.select(imap_folder, readonly=True)
                if status == 'OK':
                    selected_folder = imap_folder
                    break
                else:
                    last_error = f"select {imap_folder} status={status}"
            except Exception as e:
                last_error = f"select {imap_folder} error={str(e)}"
                continue

        if not selected_folder:
            # 如果所有尝试都失败，列出所有可用文件夹以便调试
            try:
                status, folder_list = connection.list()
                available_folders = []
                if status == 'OK' and folder_list:
                    for folder_item in folder_list:
                        if isinstance(folder_item, bytes):
                            available_folders.append(folder_item.decode('utf-8', errors='ignore'))
                        else:
                            available_folders.append(str(folder_item))
                
                error_details = {
                    "last_error": last_error,
                    "tried_folders": possible_folders,
                    "available_folders": available_folders[:10]  # 只返回前10个
                }
            except Exception:
                error_details = {
                    "last_error": last_error,
                    "tried_folders": possible_folders
                }

            return {
                "success": False,
                "error": build_error_payload(
                    "EMAIL_FETCH_FAILED",
                    f"无法访问文件夹，请检查账号配置",
                    "IMAPSelectError",
                    500,
                    error_details
                )
            }

        status, messages = connection.search(None, 'ALL')
        if status != 'OK':
            return {
                "success": False,
                "error": build_error_payload(
                    "EMAIL_FETCH_FAILED",
                    "获取邮件失败，请检查账号配置",
                    "IMAPSearchError",
                    500,
                    f"search status={status}"
                )
            }
        if not messages or not messages[0]:
            return {"success": True, "emails": []}

        message_ids = messages[0].split()
        # 计算分页范围
        total = len(message_ids)
        start_idx = max(0, total - skip - top)
        end_idx = total - skip

        if start_idx >= end_idx:
            return {"success": True, "emails": []}

        paged_ids = message_ids[start_idx:end_idx][::-1]  # 倒序，最新的在前

        emails = []
        for msg_id in paged_ids:
            try:
                status, msg_data = connection.fetch(msg_id, '(RFC822)')
                if status == 'OK' and msg_data and msg_data[0]:
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    emails.append({
                        'id': msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id),
                        'subject': decode_header_value(msg.get("Subject", "无主题")),
                        'from': decode_header_value(msg.get("From", "未知发件人")),
                        'date': msg.get("Date", "未知时间"),
                        'body_preview': get_email_body(msg)[:200] + "..." if len(get_email_body(msg)) > 200 else get_email_body(msg)
                    })
            except Exception:
                continue

        return {"success": True, "emails": emails}
    except Exception as exc:
        return {
            "success": False,
            "error": build_error_payload(
                "EMAIL_FETCH_FAILED",
                "获取邮件失败，请检查账号配置",
                type(exc).__name__,
                500,
                str(exc)
            )
        }
    finally:
        if connection:
            try:
                connection.logout()
            except Exception:
                pass


def get_email_detail_imap(account: str, client_id: str, refresh_token: str, message_id: str, folder: str = 'inbox') -> Optional[Dict]:
    """使用 IMAP 获取邮件详情"""
    access_token = get_access_token_imap(client_id, refresh_token)
    if not access_token:
        return None

    connection = None
    try:
        connection = imaplib.IMAP4_SSL(IMAP_SERVER_NEW, IMAP_PORT)
        auth_string = f"user={account}\1auth=Bearer {access_token}\1\1".encode('utf-8')
        connection.authenticate('XOAUTH2', lambda x: auth_string)

        # 根据文件夹类型选择 IMAP 文件夹
        folder_map = {
            'inbox': ['"INBOX"', 'INBOX'],
            'junkemail': ['"Junk"', '"Junk Email"', 'Junk', '"垃圾邮件"'],
            'deleteditems': ['"Deleted"', '"Deleted Items"', '"Trash"', 'Deleted', '"已删除邮件"'],
            'trash': ['"Deleted"', '"Deleted Items"', '"Trash"', 'Deleted', '"已删除邮件"']
        }
        possible_folders = folder_map.get(folder.lower(), ['"INBOX"'])

        # 尝试选择文件夹
        selected_folder = None
        for imap_folder in possible_folders:
            try:
                status, response = connection.select(imap_folder, readonly=True)
                if status == 'OK':
                    selected_folder = imap_folder
                    break
            except Exception:
                continue

        if not selected_folder:
            return None

        status, msg_data = connection.fetch(message_id.encode() if isinstance(message_id, str) else message_id, '(RFC822)')
        if status != 'OK' or not msg_data or not msg_data[0]:
            return None

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        return {
            'id': message_id,
            'subject': decode_header_value(msg.get("Subject", "无主题")),
            'from': decode_header_value(msg.get("From", "未知发件人")),
            'to': decode_header_value(msg.get("To", "")),
            'cc': decode_header_value(msg.get("Cc", "")),
            'date': msg.get("Date", "未知时间"),
            'body': get_email_body(msg)
        }
    except Exception:
        return None
    finally:
        if connection:
            try:
                connection.logout()
            except Exception:
                pass


# 兼容导出：Graph/IMAP 服务已模块化到 outlook_web.services.graph / outlook_web.services.imap
from outlook_web.services import graph as _graph_service  # noqa: E402
from outlook_web.services import imap as _imap_service  # noqa: E402

build_proxies = _graph_service.build_proxies
get_access_token_graph_result = _graph_service.get_access_token_graph_result
get_access_token_graph = _graph_service.get_access_token_graph
get_emails_graph = _graph_service.get_emails_graph
get_email_detail_graph = _graph_service.get_email_detail_graph

get_access_token_imap_result = _imap_service.get_access_token_imap_result
get_access_token_imap = _imap_service.get_access_token_imap
get_emails_imap = _imap_service.get_emails_imap
get_emails_imap_with_server = _imap_service.get_emails_imap_with_server
get_email_detail_imap = _imap_service.get_email_detail_imap


# ==================== 登录验证 ====================
# 已模块化到 outlook_web.security.auth


# ==================== Flask 路由 ====================

@app.route('/login', methods=['GET', 'POST'])
@csrf_exempt  # 登录接口排除CSRF保护（用户未登录时无法获取token）
def login():
    """登录页面"""
    if request.method == 'POST':
        try:
            # 获取客户端 IP
            client_ip = get_client_ip()

            # 检查速率限制
            allowed, remaining_time = check_rate_limit(client_ip)
            if not allowed:
                trace_id_value = None
                try:
                    trace_id_value = getattr(g, 'trace_id', None)
                except Exception:
                    trace_id_value = None
                error_payload = build_error_payload(
                    code="LOGIN_RATE_LIMITED",
                    message=f"登录失败次数过多，请在 {remaining_time} 秒后重试",
                    err_type="RateLimitError",
                    status=429,
                    details=f"ip={client_ip}",
                    trace_id=trace_id_value
                )
                return jsonify({'success': False, 'error': error_payload}), 429

            data = request.json if request.is_json else request.form
            password = data.get('password', '')

            # 从数据库获取密码哈希
            stored_password = get_login_password()

            # 验证密码
            if verify_password(password, stored_password):
                # 登录成功，重置失败记录
                reset_login_attempts(client_ip)
                session['logged_in'] = True
                session.permanent = True
                session.modified = True  # 确保 Flask-Session 保存 session
                return jsonify({'success': True, 'message': '登录成功'})
            else:
                # 登录失败，记录失败次数
                record_login_failure(client_ip)
                trace_id_value = None
                try:
                    trace_id_value = getattr(g, 'trace_id', None)
                except Exception:
                    trace_id_value = None
                error_payload = build_error_payload(
                    code="LOGIN_INVALID_PASSWORD",
                    message="密码错误",
                    err_type="AuthError",
                    status=401,
                    details=f"ip={client_ip}",
                    trace_id=trace_id_value
                )
                return jsonify({'success': False, 'error': error_payload}), 401
        except Exception as e:
            trace_id_value = None
            try:
                trace_id_value = getattr(g, 'trace_id', None)
            except Exception:
                trace_id_value = None
            try:
                app.logger.exception("Login error trace_id=%s", trace_id_value or "unknown")
            except Exception:
                pass
            error_payload = build_error_payload(
                code="LOGIN_FAILED",
                message="登录处理失败",
                err_type="AuthError",
                status=500,
                details=str(e),
                trace_id=trace_id_value
            )
            return jsonify({'success': False, 'error': error_payload}), 500

    # GET 请求返回登录页面
    return render_template('login.html')


@app.route('/logout')
def logout():
    """退出登录"""
    session.pop('logged_in', None)
    return redirect(url_for('pages.login'))


@app.route('/')
@login_required
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/csrf-token', methods=['GET'])
@csrf_exempt  # CSRF token获取接口排除CSRF保护
def get_csrf_token():
    """获取CSRF Token"""
    if CSRF_AVAILABLE:
        token = generate_csrf()
        return jsonify({'csrf_token': token})
    else:
        return jsonify({'csrf_token': None, 'csrf_disabled': True})


# ==================== 分组 API ====================

@app.route('/api/groups', methods=['GET'])
@login_required
def api_get_groups():
    """获取所有分组"""
    groups = load_groups()
    # 添加每个分组的邮箱数量
    for group in groups:
        if group['name'] == '临时邮箱':
            # 临时邮箱分组从 temp_emails 表获取数量
            group['account_count'] = get_temp_email_count()
        else:
            group['account_count'] = get_group_account_count(group['id'])
    return jsonify({'success': True, 'groups': groups})


@app.route('/api/groups/<int:group_id>', methods=['GET'])
@login_required
def api_get_group(group_id):
    """获取单个分组"""
    group = get_group_by_id(group_id)
    if not group:
        return jsonify({'success': False, 'error': '分组不存在'})
    group['account_count'] = get_group_account_count(group_id)
    return jsonify({'success': True, 'group': group})


@app.route('/api/groups', methods=['POST'])
@login_required
def api_add_group():
    """添加分组"""
    data = request.json
    name = sanitize_input(data.get('name', '').strip(), max_length=100)
    description = sanitize_input(data.get('description', ''), max_length=500)
    color = data.get('color', '#1a1a1a')
    proxy_url = data.get('proxy_url', '').strip()

    if not name:
        return jsonify({'success': False, 'error': '分组名称不能为空'})

    group_id = add_group(name, description, color, proxy_url)
    if group_id:
        log_audit('create', 'group', str(group_id), f"创建分组：{name}")
        return jsonify({'success': True, 'message': '分组创建成功', 'group_id': group_id})
    else:
        return jsonify({'success': False, 'error': '分组名称已存在'})


@app.route('/api/groups/<int:group_id>', methods=['PUT'])
@login_required
def api_update_group(group_id):
    """更新分组"""
    data = request.json
    name = sanitize_input(data.get('name', '').strip(), max_length=100)
    description = sanitize_input(data.get('description', ''), max_length=500)
    color = data.get('color', '#1a1a1a')
    proxy_url = data.get('proxy_url', '').strip()

    if not name:
        return jsonify({'success': False, 'error': '分组名称不能为空'})

    existing = get_group_by_id(group_id)
    if not existing:
        error_payload = build_error_payload(
            code="GROUP_NOT_FOUND",
            message="分组不存在",
            err_type="NotFoundError",
            status=404,
            details=f"group_id={group_id}",
        )
        return jsonify({'success': False, 'error': error_payload}), 404

    # 系统分组保护：不允许重命名（避免破坏系统逻辑）
    if existing.get('is_system') and name != existing.get('name'):
        error_payload = build_error_payload(
            code="SYSTEM_GROUP_PROTECTED",
            message="系统分组不允许重命名",
            err_type="ForbiddenError",
            status=403,
            details=f"group_id={group_id}",
        )
        return jsonify({'success': False, 'error': error_payload}), 403

    if update_group(group_id, name, description, color, proxy_url):
        # 不记录 proxy_url 明文（可能包含代理账号/密码）
        details = json.dumps({
            "name": name,
            "has_description": bool(description),
            "color": color,
            "proxy_configured": bool(proxy_url)
        }, ensure_ascii=False)
        log_audit('update', 'group', str(group_id), details)
        return jsonify({'success': True, 'message': '分组更新成功'})
    else:
        return jsonify({'success': False, 'error': '更新失败'})


@app.route('/api/groups/<int:group_id>', methods=['DELETE'])
@login_required
def api_delete_group(group_id):
    """删除分组"""
    group = get_group_by_id(group_id)
    if not group:
        error_payload = build_error_payload(
            code="GROUP_NOT_FOUND",
            message="分组不存在",
            err_type="NotFoundError",
            status=404,
            details=f"group_id={group_id}",
        )
        return jsonify({'success': False, 'error': error_payload}), 404

    if group.get('is_system'):
        error_payload = build_error_payload(
            code="SYSTEM_GROUP_PROTECTED",
            message="系统分组不能删除",
            err_type="ForbiddenError",
            status=403,
            details=f"group_id={group_id}",
        )
        return jsonify({'success': False, 'error': error_payload}), 403

    default_group_id = get_default_group_id()
    if group_id == default_group_id or group.get('name') == '默认分组':
        error_payload = build_error_payload(
            code="DEFAULT_GROUP_PROTECTED",
            message="默认分组不能删除",
            err_type="ForbiddenError",
            status=403,
            details=f"group_id={group_id}",
        )
        return jsonify({'success': False, 'error': error_payload}), 403
    
    if delete_group(group_id):
        log_audit('delete', 'group', str(group_id), "删除分组并迁移账号到默认分组")
        return jsonify({'success': True, 'message': '分组已删除，邮箱已移至默认分组'})
    else:
        return jsonify({'success': False, 'error': '删除失败'})


@app.route('/api/groups/<int:group_id>/export')
@login_required
def api_export_group(group_id):
    """导出分组下的所有邮箱账号为 TXT 文件（需要二次验证）"""
    # 检查二次验证token（一次性）
    verify_token = request.args.get('verify_token')
    ok, error_message = consume_export_verify_token(verify_token)
    if not ok:
        return jsonify({'success': False, 'error': error_message, 'need_verify': True}), 401

    group = get_group_by_id(group_id)
    if not group:
        return jsonify({'success': False, 'error': '分组不存在'})

    # 使用 load_accounts 获取该分组下的所有账号（自动解密）
    accounts = load_accounts(group_id)

    if not accounts:
        return jsonify({'success': False, 'error': '该分组下没有邮箱账号'})

    # 记录审计日志
    log_audit('export', 'group', str(group_id), f"导出分组 '{group['name']}' 的 {len(accounts)} 个账号")

    # 生成导出内容（格式：email----password----client_id----refresh_token）
    lines = []
    for acc in accounts:
        line = f"{acc['email']}----{acc.get('password', '')}----{acc['client_id']}----{acc['refresh_token']}"
        lines.append(line)

    content = '\n'.join(lines)

    # 生成文件名（使用 URL 编码处理中文）
    filename = f"{group['name']}_accounts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    encoded_filename = quote(filename)

    # 返回文件下载响应
    return Response(
        content,
        mimetype='text/plain; charset=utf-8',
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


@app.route('/api/accounts/export')
@login_required
def api_export_all_accounts():
    """导出所有邮箱账号为 TXT 文件（需要二次验证）"""
    # 检查二次验证token（一次性）
    verify_token = request.args.get('verify_token')
    ok, error_message = consume_export_verify_token(verify_token)
    if not ok:
        return jsonify({'success': False, 'error': error_message, 'need_verify': True}), 401


    # 使用 load_accounts 获取所有账号（自动解密）
    accounts = load_accounts()

    if not accounts:
        return jsonify({'success': False, 'error': '没有邮箱账号'})

    # 记录审计日志
    log_audit('export', 'all_accounts', None, f"导出所有账号，共 {len(accounts)} 个")

    # 生成导出内容（格式：email----password----client_id----refresh_token）
    lines = []
    for acc in accounts:
        line = f"{acc['email']}----{acc.get('password', '')}----{acc['client_id']}----{acc['refresh_token']}"
        lines.append(line)

    content = '\n'.join(lines)

    # 生成文件名（使用 URL 编码处理中文）
    filename = f"all_accounts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    encoded_filename = quote(filename)

    # 返回文件下载响应
    return Response(
        content,
        mimetype='text/plain; charset=utf-8',
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


@app.route('/api/accounts/export-selected', methods=['POST'])
@login_required
def api_export_selected_accounts():
    """导出选中分组的邮箱账号为 TXT 文件（需要二次验证）"""
    data = request.json
    group_ids = data.get('group_ids', [])
    verify_token = data.get('verify_token')

    ok, error_message = consume_export_verify_token(verify_token)
    if not ok:
        return jsonify({'success': False, 'error': error_message, 'need_verify': True}), 401

    if not group_ids:
        return jsonify({'success': False, 'error': '请选择要导出的分组'})

    # 获取选中分组下的所有账号（使用 load_accounts 自动解密）
    all_accounts = []
    for group_id in group_ids:
        accounts = load_accounts(group_id)
        all_accounts.extend(accounts)

    if not all_accounts:
        return jsonify({'success': False, 'error': '选中的分组下没有邮箱账号'})

    # 记录审计日志
    log_audit('export', 'selected_groups', ','.join(map(str, group_ids)), f"导出选中分组的 {len(all_accounts)} 个账号")

    # 生成导出内容
    lines = []
    for acc in all_accounts:
        line = f"{acc['email']}----{acc.get('password', '')}----{acc['client_id']}----{acc['refresh_token']}"
        lines.append(line)

    content = '\n'.join(lines)

    # 生成文件名
    filename = f"selected_accounts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    encoded_filename = quote(filename)

    # 返回文件下载响应
    return Response(
        content,
        mimetype='text/plain; charset=utf-8',
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


@app.route('/api/export/verify', methods=['POST'])
@login_required
def api_generate_export_verify_token():
    """生成导出验证token（二次验证）"""
    data = request.json
    password = data.get('password', '')

    # 验证密码
    db = get_db()
    cursor = db.execute("SELECT value FROM settings WHERE key = 'login_password'")
    result = cursor.fetchone()

    if not result:
        return jsonify({'success': False, 'error': '系统配置错误'})

    stored_password = result[0]
    if not verify_password(password, stored_password):
        return jsonify({'success': False, 'error': '密码错误'})

    client_ip = get_client_ip()
    user_agent = get_user_agent()
    verify_token = issue_export_verify_token(client_ip, user_agent)
    return jsonify({'success': True, 'verify_token': verify_token})


# ==================== 邮箱账号 API ====================

@app.route('/api/accounts', methods=['GET'])
@login_required
def api_get_accounts():
    """获取所有账号"""
    group_id = request.args.get('group_id', type=int)
    accounts = load_accounts(group_id)

    # 获取每个账号的最后刷新状态（批量查询，避免 N+1）
    db = get_db()
    last_log_by_account: Dict[int, Dict[str, Any]] = {}
    try:
        account_ids = [int(a.get('id')) for a in accounts if a.get('id') is not None]
    except Exception:
        account_ids = []

    if account_ids:
        try:
            placeholders = ",".join(["?"] * len(account_ids))
            rows = db.execute(f'''
                SELECT l.account_id, l.status, l.error_message, l.created_at
                FROM account_refresh_logs l
                JOIN (
                    SELECT account_id, MAX(id) as max_id
                    FROM account_refresh_logs
                    WHERE account_id IN ({placeholders})
                    GROUP BY account_id
                ) latest
                ON l.account_id = latest.account_id AND l.id = latest.max_id
            ''', account_ids).fetchall()
            for r in rows:
                try:
                    last_log_by_account[int(r['account_id'])] = dict(r)
                except Exception:
                    continue
        except Exception:
            last_log_by_account = {}

    # 返回时隐藏敏感信息
    safe_accounts = []
    for acc in accounts:
        acc_id = acc.get('id')
        try:
            acc_id_int = int(acc_id)
        except Exception:
            acc_id_int = None
        last_refresh_log = last_log_by_account.get(acc_id_int) if acc_id_int is not None else None

        safe_accounts.append({
            'id': acc['id'],
            'email': acc['email'],
            'client_id': acc['client_id'][:8] + '...' if len(acc['client_id']) > 8 else acc['client_id'],
            'group_id': acc.get('group_id'),
            'group_name': acc.get('group_name', '默认分组'),
            'group_color': acc.get('group_color', '#666666'),
            'remark': acc.get('remark', ''),
            'status': acc.get('status', 'active'),
            'last_refresh_at': acc.get('last_refresh_at', ''),
            'last_refresh_status': last_refresh_log.get('status') if last_refresh_log else None,
            'last_refresh_error': last_refresh_log.get('error_message') if last_refresh_log else None,
            'created_at': acc.get('created_at', ''),
            'updated_at': acc.get('updated_at', ''),
            'tags': acc.get('tags', [])
        })
    return jsonify({'success': True, 'accounts': safe_accounts})


# ==================== 标签 API ====================

@app.route('/api/tags', methods=['GET'])
@login_required
def api_get_tags():
    """获取所有标签"""
    return jsonify({'success': True, 'tags': get_tags()})


@app.route('/api/tags', methods=['POST'])
@login_required
def api_add_tag():
    """添加标签"""
    data = request.json
    name = sanitize_input(data.get('name', '').strip(), max_length=50)
    color = data.get('color', '#1a1a1a')

    if not name:
        return jsonify({'success': False, 'error': '标签名称不能为空'})

    tag_id = add_tag(name, color)
    if tag_id:
        log_audit('create', 'tag', str(tag_id), json.dumps({'name': name, 'color': color}, ensure_ascii=False))
        return jsonify({'success': True, 'tag': {'id': tag_id, 'name': name, 'color': color}})
    else:
        return jsonify({'success': False, 'error': '标签名称已存在'})


@app.route('/api/tags/<int:tag_id>', methods=['DELETE'])
@login_required
def api_delete_tag(tag_id):
    """删除标签"""
    if delete_tag(tag_id):
        log_audit('delete', 'tag', str(tag_id), "删除标签")
        return jsonify({'success': True, 'message': '标签已删除'})
    else:
        return jsonify({'success': False, 'error': '删除失败'})


@app.route('/api/accounts/tags', methods=['POST'])
@login_required
def api_batch_manage_tags():
    """批量管理账号标签"""
    data = request.json
    account_ids = data.get('account_ids', [])
    tag_id = data.get('tag_id')
    action = data.get('action')  # add, remove

    if not account_ids or not tag_id or not action:
        return jsonify({'success': False, 'error': '参数不完整'})

    count = 0
    for acc_id in account_ids:
        if action == 'add':
            if add_account_tag(acc_id, tag_id):
                count += 1
        elif action == 'remove':
            if remove_account_tag(acc_id, tag_id):
                count += 1

    try:
        details = json.dumps({'action': action, 'tag_id': tag_id, 'accounts': len(account_ids), 'affected': count}, ensure_ascii=False)
    except Exception:
        details = f"action={action} tag_id={tag_id} accounts={len(account_ids)} affected={count}"
    log_audit('update', 'account_tags', str(tag_id), details)
    return jsonify({'success': True, 'message': f'成功处理 {count} 个账号'})


@app.route('/api/accounts/batch-update-group', methods=['POST'])
@login_required
def api_batch_update_account_group():
    """批量更新账号分组"""
    data = request.json
    account_ids = data.get('account_ids', [])
    group_id = data.get('group_id')

    if not account_ids:
        return jsonify({'success': False, 'error': '请选择要修改的账号'})

    if not group_id:
        return jsonify({'success': False, 'error': '请选择目标分组'})

    # 验证分组存在
    group = get_group_by_id(group_id)
    if not group:
        return jsonify({'success': False, 'error': '目标分组不存在'})

    # 检查是否是临时邮箱分组（系统保留分组）
    if group.get('is_system'):
        return jsonify({'success': False, 'error': '不能移动到系统分组'})

    # 批量更新
    db = get_db()
    try:
        placeholders = ','.join('?' * len(account_ids))
        db.execute(f'''
            UPDATE accounts SET group_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id IN ({placeholders})
        ''', [group_id] + account_ids)
        db.commit()
        log_audit('update', 'account_group', str(group_id), f"批量移动分组：账号数={len(account_ids)}")
        return jsonify({
            'success': True,
            'message': f'已将 {len(account_ids)} 个账号移动到「{group["name"]}」分组'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})



@app.route('/api/accounts/search', methods=['GET'])
@login_required
def api_search_accounts():
    """全局搜索账号"""
    query = request.args.get('q', '').strip()

    if not query:
        return jsonify({'success': True, 'accounts': []})

    db = get_db()
    # 支持搜索邮箱、备注和标签
    cursor = db.execute('''
        SELECT DISTINCT a.*, g.name as group_name, g.color as group_color
        FROM accounts a
        LEFT JOIN groups g ON a.group_id = g.id
        LEFT JOIN account_tags at ON a.id = at.account_id
        LEFT JOIN tags t ON at.tag_id = t.id
        WHERE a.email LIKE ? OR a.remark LIKE ? OR t.name LIKE ?
        ORDER BY a.created_at DESC
    ''', (f'%{query}%', f'%{query}%', f'%{query}%'))

    rows = cursor.fetchall()

    # 批量加载标签与最后刷新状态，避免 N+1 查询（1,000 账号场景）
    account_rows: List[Dict[str, Any]] = [dict(r) for r in rows]
    try:
        account_ids = [int(a.get('id')) for a in account_rows if a.get('id') is not None]
    except Exception:
        account_ids = []

    tags_by_account: Dict[int, List[Dict[str, Any]]] = {}
    last_log_by_account: Dict[int, Dict[str, Any]] = {}
    if account_ids:
        try:
            placeholders = ",".join(["?"] * len(account_ids))
            tag_rows = db.execute(f'''
                SELECT at.account_id as account_id, t.*
                FROM account_tags at
                JOIN tags t ON t.id = at.tag_id
                WHERE at.account_id IN ({placeholders})
                ORDER BY at.account_id ASC, t.created_at DESC
            ''', account_ids).fetchall()
            for tr in tag_rows:
                tag_dict = dict(tr)
                acc_id = tag_dict.pop('account_id', None)
                if acc_id is None:
                    continue
                tags_by_account.setdefault(int(acc_id), []).append(tag_dict)
        except Exception:
            tags_by_account = {}

        try:
            placeholders = ",".join(["?"] * len(account_ids))
            log_rows = db.execute(f'''
                SELECT l.account_id, l.status, l.error_message, l.created_at
                FROM account_refresh_logs l
                JOIN (
                    SELECT account_id, MAX(id) as max_id
                    FROM account_refresh_logs
                    WHERE account_id IN ({placeholders})
                    GROUP BY account_id
                ) latest
                ON l.account_id = latest.account_id AND l.id = latest.max_id
            ''', account_ids).fetchall()
            for lr in log_rows:
                try:
                    last_log_by_account[int(lr['account_id'])] = dict(lr)
                except Exception:
                    continue
        except Exception:
            last_log_by_account = {}

    safe_accounts = []
    for acc in account_rows:
        acc_id = acc.get('id')
        try:
            acc_id_int = int(acc_id)
        except Exception:
            acc_id_int = None

        tags = tags_by_account.get(acc_id_int, []) if acc_id_int is not None else []
        last_refresh_log = last_log_by_account.get(acc_id_int) if acc_id_int is not None else None

        safe_accounts.append({
            'id': acc['id'],
            'email': acc['email'],
            'client_id': acc['client_id'][:8] + '...' if len(acc['client_id']) > 8 else acc['client_id'],
            'group_id': acc['group_id'],
            'group_name': acc['group_name'] if acc['group_name'] else '默认分组',
            'group_color': acc['group_color'] if acc['group_color'] else '#666666',
            'remark': acc['remark'] if acc['remark'] else '',
            'status': acc['status'] if acc['status'] else 'active',
            'created_at': acc['created_at'] if acc['created_at'] else '',
            'updated_at': acc['updated_at'] if acc['updated_at'] else '',
            'tags': tags,
            'last_refresh_at': acc.get('last_refresh_at', ''),
            'last_refresh_status': last_refresh_log.get('status') if last_refresh_log else None,
            'last_refresh_error': last_refresh_log.get('error_message') if last_refresh_log else None
        })

    return jsonify({'success': True, 'accounts': safe_accounts})


@app.route('/api/accounts/<int:account_id>', methods=['GET'])
@login_required
def api_get_account(account_id):
    """获取单个账号详情"""
    account = get_account_by_id(account_id)
    if not account:
        return jsonify({'success': False, 'error': '账号不存在'})
    
    return jsonify({
        'success': True,
        'account': {
            'id': account['id'],
            'email': account['email'],
            # 敏感字段默认不回显（避免泄露）；如需查看请走“导出+二次验证”
            'password': '',
            'client_id': account['client_id'],
            'refresh_token': '',
            'has_password': bool(account.get('password')),
            'has_refresh_token': bool(account.get('refresh_token')),
            'group_id': account.get('group_id'),
            'group_name': account.get('group_name', '默认分组'),
            'remark': account.get('remark', ''),
            'status': account.get('status', 'active'),
            'created_at': account.get('created_at', ''),
            'updated_at': account.get('updated_at', '')
        }
    })


@app.route('/api/accounts', methods=['POST'])
@login_required
def api_add_account():
    """添加账号"""
    data = request.json
    account_str = data.get('account_string', '')
    group_id = data.get('group_id', 1)
    
    if not account_str:
        return jsonify({'success': False, 'error': '请输入账号信息'})
    
    # 校验分组
    target_group = get_group_by_id(group_id)
    if not target_group:
        return jsonify({'success': False, 'error': '分组不存在'})
    if target_group.get('is_system'):
        return jsonify({'success': False, 'error': '不能导入到系统分组'})

    def sanitize_credential_field(value: Any, max_length: int) -> str:
        if value is None:
            return ''
        text = str(value)
        text = text.replace('\r', '').replace('\n', '').replace('\t', '')
        text = text.strip()
        if len(text) > max_length:
            text = text[:max_length]
        # 移除不可见控制字符
        text = ''.join(ch for ch in text if ch.isprintable())
        return text

    # 支持批量导入（多行）+ 逐行校验与错误定位
    raw_lines = account_str.splitlines()
    imported = 0
    failed = 0
    errors: List[Dict[str, Any]] = []
    errors_total = 0
    max_error_details = 50

    db = get_db()
    for line_no, raw in enumerate(raw_lines, start=1):
        line = (raw or '').strip()
        if not line:
            continue

        parsed = parse_account_string(line)
        if not parsed:
            failed += 1
            errors_total += 1
            if len(errors) < max_error_details:
                errors.append({'line': line_no, 'error': '格式错误，应为：邮箱----密码----client_id----refresh_token'})
            continue

        email_addr = sanitize_credential_field(parsed.get('email'), 320)
        password = sanitize_credential_field(parsed.get('password'), 500)
        client_id = sanitize_credential_field(parsed.get('client_id'), 200)
        refresh_token = sanitize_credential_field(parsed.get('refresh_token'), 4096)

        if not email_addr or not client_id or not refresh_token:
            failed += 1
            errors_total += 1
            if len(errors) < max_error_details:
                errors.append({'line': line_no, 'email': email_addr, 'error': '邮箱、Client ID、Refresh Token 不能为空'})
            continue

        # 基础邮箱格式校验
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email_addr):
            failed += 1
            errors_total += 1
            if len(errors) < max_error_details:
                errors.append({'line': line_no, 'email': email_addr, 'error': '邮箱格式不正确'})
            continue

        ok = add_account(email_addr, password, client_id, refresh_token, group_id, db=db, commit=False)
        if ok:
            imported += 1
            continue

        failed += 1
        errors_total += 1
        reason = '写入失败'
        try:
            exists = db.execute('SELECT 1 FROM accounts WHERE email = ? LIMIT 1', (email_addr,)).fetchone()
            if exists:
                reason = '邮箱已存在'
        except Exception:
            pass
        if len(errors) < max_error_details:
            errors.append({'line': line_no, 'email': email_addr, 'error': reason})

    summary = {
        'group_id': group_id,
        'total_lines': len(raw_lines),
        'imported': imported,
        'failed': failed,
        'errors_total': errors_total,
        'errors_returned': len(errors),
        'errors_truncated': errors_total > len(errors)
    }

    message = f'导入完成：成功 {imported} 个，失败 {failed} 个'

    if imported > 0:
        try:
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            return jsonify({'success': False, 'error': '数据库写入失败，请重试'})
        log_audit('import', 'account', None, f"{message}，目标分组ID={group_id}")
        return jsonify({'success': True, 'message': message, 'summary': summary, 'errors': errors})

    return jsonify({'success': False, 'error': message, 'summary': summary, 'errors': errors})


@app.route('/api/accounts/<int:account_id>', methods=['PUT'])
@login_required
def api_update_account(account_id):
    """更新账号"""
    data = request.json

    # 检查是否只更新状态
    if 'status' in data and len(data) == 1:
        # 只更新状态
        return api_update_account_status(account_id, data['status'])

    email_addr = (data.get('email') or '').strip()
    password = data.get('password')
    client_id = data.get('client_id')
    refresh_token = data.get('refresh_token')
    try:
        group_id = int(data.get('group_id', 1) or 1)
    except Exception:
        group_id = 1
    remark = sanitize_input(data.get('remark', ''), max_length=200)
    status = data.get('status', 'active')

    if not email_addr:
        return jsonify({'success': False, 'error': '邮箱不能为空'})

    target_group = get_group_by_id(group_id)
    if not target_group:
        error_payload = build_error_payload(
            code="GROUP_NOT_FOUND",
            message="分组不存在",
            err_type="NotFoundError",
            status=404,
            details=f"group_id={group_id}",
        )
        return jsonify({'success': False, 'error': error_payload}), 404

    if target_group.get('is_system'):
        error_payload = build_error_payload(
            code="SYSTEM_GROUP_PROTECTED",
            message="不能移动到系统分组",
            err_type="ForbiddenError",
            status=403,
            details=f"group_id={group_id}",
        )
        return jsonify({'success': False, 'error': error_payload}), 403

    if update_account(account_id, email_addr, password, client_id, refresh_token, group_id, remark, status):
        changed_fields = []
        if isinstance(client_id, str) and client_id.strip():
            changed_fields.append('client_id')
        if isinstance(password, str) and password.strip():
            changed_fields.append('password')
        if isinstance(refresh_token, str) and refresh_token.strip():
            changed_fields.append('refresh_token')
        details = json.dumps({
            "email": email_addr,
            "group_id": group_id,
            "status": status,
            "changed_fields": changed_fields
        }, ensure_ascii=False)
        log_audit('update', 'account', str(account_id), details)
        return jsonify({'success': True, 'message': '账号更新成功'})
    else:
        return jsonify({'success': False, 'error': '更新失败'})


def api_update_account_status(account_id: int, status: str):
    """只更新账号状态"""
    db = get_db()
    try:
        db.execute('''
            UPDATE accounts
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (status, account_id))
        db.commit()
        return jsonify({'success': True, 'message': '状态更新成功'})
    except Exception:
        return jsonify({'success': False, 'error': '更新失败'})


@app.route('/api/accounts/<int:account_id>', methods=['DELETE'])
@login_required
def api_delete_account(account_id):
    """删除账号"""
    email_addr = ''
    try:
        db = get_db()
        row = db.execute('SELECT email FROM accounts WHERE id = ?', (account_id,)).fetchone()
        email_addr = row['email'] if row else ''
    except Exception:
        email_addr = ''
    if delete_account_by_id(account_id):
        log_audit('delete', 'account', str(account_id), f"删除账号：{email_addr}" if email_addr else "删除账号")
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': '删除失败'})


@app.route('/api/accounts/email/<email_addr>', methods=['DELETE'])
@login_required
def api_delete_account_by_email(email_addr):
    """根据邮箱地址删除账号"""
    if delete_account_by_email(email_addr):
        log_audit('delete', 'account', email_addr, f"删除账号：{email_addr}")
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': '删除失败'})


@app.route('/api/accounts/batch-delete', methods=['POST'])
@login_required
def api_batch_delete_accounts():
    """
    批量删除账号 API

    功能：支持一次性删除多个账号，记录审计日志

    请求体：
    {
        "account_ids": [1, 2, 3]  // 账号 ID 列表
    }

    返回：
    {
        "success": true,
        "message": "成功删除 N 个账号，失败 M 个",
        "deleted_count": N,
        "failed_count": M
    }

    注意事项：
    - 当前实现为循环删除，未使用事务保护
    - 部分删除失败时不会回滚已删除的账号
    - 建议后续优化为事务批量删除

    关联文档：PRD-批量操作与自动化增强
    """
    data = request.get_json()
    account_ids = data.get('account_ids', [])

    if not account_ids:
        return jsonify({'success': False, 'error': '请选择要删除的账号'})

    if not isinstance(account_ids, list):
        return jsonify({'success': False, 'error': '参数格式错误'})

    deleted_count = 0
    failed_count = 0

    for account_id in account_ids:
        try:
            # 获取邮箱地址用于审计日志
            db = get_db()
            row = db.execute('SELECT email FROM accounts WHERE id = ?', (account_id,)).fetchone()
            email_addr = row['email'] if row else ''

            if delete_account_by_id(account_id):
                log_audit('delete', 'account', str(account_id), f"批量删除账号：{email_addr}" if email_addr else "批量删除账号")
                deleted_count += 1
            else:
                failed_count += 1
        except Exception:
            failed_count += 1

    return jsonify({
        'success': True,
        'message': f'成功删除 {deleted_count} 个账号' + (f'，失败 {failed_count} 个' if failed_count > 0 else ''),
        'deleted_count': deleted_count,
        'failed_count': failed_count
    })


# ==================== 账号刷新 API ====================

REFRESH_LOCK_NAME = "token_refresh"
REFRESH_LOCK_TTL_SECONDS = 60 * 60 * 2  # 2 小时，避免异常中断导致长时间卡死


def compute_refresh_lock_ttl_seconds(total: int, delay_seconds: int) -> int:
    try:
        total = int(total or 0)
    except Exception:
        total = 0
    try:
        delay_seconds = int(delay_seconds or 0)
    except Exception:
        delay_seconds = 0

    # 粗略估算：每个账号至少 2 秒 + 配置延迟，再加 10 分钟缓冲
    estimated = int(total * (max(delay_seconds, 0) + 2) + 600)
    ttl = max(REFRESH_LOCK_TTL_SECONDS, estimated)
    return min(ttl, 60 * 60 * 24)  # 最大 24 小时


def acquire_distributed_lock(conn: sqlite3.Connection, name: str, owner_id: str, ttl_seconds: int) -> tuple[bool, Optional[Dict[str, Any]]]:
    """获取分布式锁（基于同一 SQLite 数据库），用于避免并发刷新冲突"""
    now_ts = time.time()
    expires_at = now_ts + ttl_seconds

    try:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('''
            SELECT owner_id, acquired_at, expires_at
            FROM distributed_locks
            WHERE name = ?
        ''', (name,)).fetchone()

        if not row:
            conn.execute('''
                INSERT INTO distributed_locks (name, owner_id, acquired_at, expires_at)
                VALUES (?, ?, ?, ?)
            ''', (name, owner_id, now_ts, expires_at))
            conn.commit()
            return True, None

        if row['expires_at'] < now_ts:
            conn.execute('''
                UPDATE distributed_locks
                SET owner_id = ?, acquired_at = ?, expires_at = ?
                WHERE name = ?
            ''', (owner_id, now_ts, expires_at, name))
            conn.commit()
            return True, {
                "previous_owner_id": row['owner_id'],
                "previous_acquired_at": row['acquired_at'],
                "previous_expires_at": row['expires_at']
            }

        conn.rollback()
        return False, {
            "owner_id": row['owner_id'],
            "acquired_at": row['acquired_at'],
            "expires_at": row['expires_at']
        }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return False, {"error": str(e)}


def release_distributed_lock(conn: sqlite3.Connection, name: str, owner_id: str) -> bool:
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''
            DELETE FROM distributed_locks
            WHERE name = ? AND owner_id = ?
        ''', (name, owner_id))
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False


def create_refresh_run(
    conn: sqlite3.Connection,
    trigger_source: str,
    trace_id: str,
    requested_by_ip: str = None,
    requested_by_user_agent: str = None,
    total: int = 0,
) -> str:
    run_id = uuid.uuid4().hex
    conn.execute('''
        INSERT INTO refresh_runs (
            id, trigger_source, status,
            requested_by_ip, requested_by_user_agent,
            total, success_count, failed_count,
            trace_id
        ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)
    ''', (run_id, trigger_source, 'running', requested_by_ip, requested_by_user_agent, total, trace_id))
    conn.commit()
    return run_id


def finish_refresh_run(
    conn: sqlite3.Connection,
    run_id: str,
    status: str,
    total: int,
    success_count: int,
    failed_count: int,
    message: str = None,
):
    conn.execute('''
        UPDATE refresh_runs
        SET status = ?, finished_at = CURRENT_TIMESTAMP,
            total = ?, success_count = ?, failed_count = ?, message = ?
        WHERE id = ?
    ''', (status, total, success_count, failed_count, message, run_id))
    conn.commit()


def log_refresh_result(
    account_id: int,
    account_email: str,
    refresh_type: str,
    status: str,
    error_message: str = None,
    run_id: str = None,
):
    """记录刷新结果到数据库"""
    db = get_db()
    try:
        db.execute('''
            INSERT INTO account_refresh_logs (account_id, account_email, refresh_type, status, error_message, run_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (account_id, account_email, refresh_type, status, error_message, run_id))

        # 更新账号的最后刷新时间
        if status == 'success':
            db.execute('''
                UPDATE accounts
                SET last_refresh_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (account_id,))

        db.commit()
        return True
    except Exception as e:
        print(f"记录刷新结果失败: {str(e)}")
        return False


def test_refresh_token(client_id: str, refresh_token: str, proxy_url: str = None) -> tuple[bool, str]:
    """测试 refresh token 是否有效，返回 (是否成功, 错误信息)"""
    try:
        # 尝试使用 Graph API 获取 access token
        # 使用与 get_access_token_graph 相同的 scope，确保一致性
        proxies = build_proxies(proxy_url)
        res = requests.post(
            TOKEN_URL_GRAPH,
            data={
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": "https://graph.microsoft.com/.default"
            },
            timeout=30,
            proxies=proxies
        )

        if res.status_code == 200:
            return True, None
        else:
            error_data = res.json()
            error_msg = error_data.get('error_description', error_data.get('error', '未知错误'))
            return False, error_msg
    except Exception as e:
        return False, f"请求异常: {str(e)}"


# 兼容导出：refresh token 校验已模块化到 outlook_web.services.graph
test_refresh_token = _graph_service.test_refresh_token

# 兼容导出：刷新相关 repositories/services 已模块化到 outlook_web.repositories.* / outlook_web.services.refresh
from outlook_web.repositories import distributed_locks as _locks_repo  # noqa: E402
from outlook_web.repositories import refresh_logs as _refresh_logs_repo  # noqa: E402
from outlook_web.repositories import refresh_runs as _refresh_runs_repo  # noqa: E402
from outlook_web.services import refresh as _refresh_service  # noqa: E402

compute_refresh_lock_ttl_seconds = _refresh_service.compute_refresh_lock_ttl_seconds
acquire_distributed_lock = _locks_repo.acquire_distributed_lock
release_distributed_lock = _locks_repo.release_distributed_lock
create_refresh_run = _refresh_runs_repo.create_refresh_run
finish_refresh_run = _refresh_runs_repo.finish_refresh_run
log_refresh_result = _refresh_logs_repo.log_refresh_result


@app.route('/api/accounts/<int:account_id>/refresh', methods=['POST'])
@login_required
def api_refresh_account(account_id):
    """刷新单个账号的 token"""
    db = get_db()
    cursor = db.execute('SELECT id, email, client_id, refresh_token, group_id FROM accounts WHERE id = ?', (account_id,))
    account = cursor.fetchone()

    if not account:
        error_payload = build_error_payload(
            "ACCOUNT_NOT_FOUND",
            "账号不存在",
            "NotFoundError",
            404,
            f"account_id={account_id}"
        )
        return jsonify({'success': False, 'error': error_payload})

    account_id = account['id']
    account_email = account['email']
    client_id = account['client_id']
    encrypted_refresh_token = account['refresh_token']

    # 获取分组代理设置
    proxy_url = ''
    if account['group_id']:
        group = get_group_by_id(account['group_id'])
        if group:
            proxy_url = group.get('proxy_url', '') or ''

    # 解密 refresh_token
    try:
        refresh_token = decrypt_data(encrypted_refresh_token) if encrypted_refresh_token else encrypted_refresh_token
    except Exception as e:
        error_msg = f"解密 token 失败: {str(e)}"
        log_refresh_result(account_id, account_email, 'manual', 'failed', error_msg)
        error_payload = build_error_payload(
            "TOKEN_DECRYPT_FAILED",
            "Token 解密失败",
            "DecryptionError",
            500,
            error_msg
        )
        return jsonify({'success': False, 'error': error_payload})

    # 测试 refresh token
    success, error_msg = test_refresh_token(client_id, refresh_token, proxy_url)

    # 记录刷新结果
    log_refresh_result(account_id, account_email, 'manual', 'success' if success else 'failed', error_msg)

    if success:
        return jsonify({'success': True, 'message': 'Token 刷新成功'})

    error_payload = build_error_payload(
        "TOKEN_REFRESH_FAILED",
        "Token 刷新失败",
        "RefreshTokenError",
        400,
        error_msg or "未知错误"
    )
    return jsonify({'success': False, 'error': error_payload})


@app.route('/api/accounts/refresh-all', methods=['GET'])
@login_required
def api_refresh_all_accounts():
    """刷新所有账号的 token（流式响应，实时返回进度）"""
    trace_id_value = None
    try:
        trace_id_value = getattr(g, 'trace_id', None)
    except Exception:
        trace_id_value = None
    requested_by_ip = get_client_ip()
    requested_by_user_agent = get_user_agent()

    def generate():
        yield from _refresh_service.stream_refresh_all_accounts(
            trace_id=trace_id_value,
            requested_by_ip=requested_by_ip,
            requested_by_user_agent=requested_by_user_agent,
            lock_name=REFRESH_LOCK_NAME,
            test_refresh_token=test_refresh_token,
        )
        return

        conn = create_sqlite_connection()
        lock_owner_id = uuid.uuid4().hex
        lock_acquired = False
        run_id = None

        try:
            # 获取刷新间隔配置
            delay_row = conn.execute("SELECT value FROM settings WHERE key = 'refresh_delay_seconds'").fetchone()
            delay_seconds = int(delay_row['value']) if delay_row else 5

            # 清理超过半年的刷新记录
            try:
                conn.execute("DELETE FROM account_refresh_logs WHERE created_at < datetime('now', '-6 months')")
                conn.execute("DELETE FROM refresh_runs WHERE started_at < datetime('now', '-6 months')")
                conn.execute("DELETE FROM distributed_locks WHERE expires_at < ?", (time.time(),))
                conn.commit()
            except Exception:
                pass

            accounts = conn.execute("SELECT id, email, client_id, refresh_token, group_id FROM accounts WHERE status = 'active'").fetchall()
            total = len(accounts)

            run_id = create_refresh_run(
                conn,
                trigger_source='manual_all',
                trace_id=trace_id_value or generate_trace_id(),
                requested_by_ip=requested_by_ip,
                requested_by_user_agent=requested_by_user_agent,
                total=total
            )

            ttl_seconds = compute_refresh_lock_ttl_seconds(total, delay_seconds)
            ok, lock_info = acquire_distributed_lock(conn, REFRESH_LOCK_NAME, lock_owner_id, ttl_seconds)
            if not ok:
                finish_refresh_run(conn, run_id, 'skipped', total, 0, 0, "刷新任务冲突：已有刷新在执行")
                error_payload = build_error_payload(
                    code="REFRESH_CONFLICT",
                    message="当前已有刷新任务执行中，请稍后再试",
                    err_type="ConflictError",
                    status=409,
                    details=lock_info or "",
                    trace_id=trace_id_value
                )
                yield f"data: {json.dumps({'type': 'error', 'error': error_payload}, ensure_ascii=False)}\n\n"
                return
            lock_acquired = True

            success_count = 0
            failed_count = 0
            failed_list = []

            yield f"data: {json.dumps({'type': 'start', 'total': total, 'delay_seconds': delay_seconds, 'run_id': run_id, 'trace_id': trace_id_value, 'refresh_type': 'manual_all'}, ensure_ascii=False)}\n\n"

            for index, account in enumerate(accounts, 1):
                account_id = account['id']
                account_email = account['email']
                client_id = account['client_id']
                encrypted_refresh_token = account['refresh_token']

                # 解密 refresh_token
                try:
                    refresh_token = decrypt_data(encrypted_refresh_token) if encrypted_refresh_token else encrypted_refresh_token
                except Exception as e:
                    failed_count += 1
                    error_msg = f"解密 token 失败: {str(e)}"
                    failed_list.append({'id': account_id, 'email': account_email, 'error': error_msg})
                    try:
                        conn.execute('''
                            INSERT INTO account_refresh_logs (account_id, account_email, refresh_type, status, error_message, run_id)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (account_id, account_email, 'manual_all', 'failed', error_msg, run_id))
                        conn.commit()
                    except Exception:
                        pass
                    continue

                yield f"data: {json.dumps({'type': 'progress', 'current': index, 'total': total, 'email': account_email, 'success_count': success_count, 'failed_count': failed_count}, ensure_ascii=False)}\n\n"

                # 获取分组代理设置
                proxy_url = ''
                group_id = account['group_id']
                if group_id:
                    try:
                        group_row = conn.execute('SELECT proxy_url FROM groups WHERE id = ?', (group_id,)).fetchone()
                        if group_row:
                            proxy_url = group_row['proxy_url'] or ''
                    except Exception:
                        proxy_url = ''

                success, error_msg = test_refresh_token(client_id, refresh_token, proxy_url)

                try:
                    conn.execute('''
                        INSERT INTO account_refresh_logs (account_id, account_email, refresh_type, status, error_message, run_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (account_id, account_email, 'manual_all', 'success' if success else 'failed', error_msg, run_id))

                    if success:
                        conn.execute('''
                            UPDATE accounts
                            SET last_refresh_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        ''', (account_id,))

                    conn.commit()
                except Exception:
                    pass

                if success:
                    success_count += 1
                else:
                    failed_count += 1
                    failed_list.append({'id': account_id, 'email': account_email, 'error': error_msg})

                if index < total and delay_seconds > 0:
                    yield f"data: {json.dumps({'type': 'delay', 'seconds': delay_seconds}, ensure_ascii=False)}\n\n"
                    time.sleep(delay_seconds)

            finish_refresh_run(
                conn,
                run_id,
                'completed',
                total,
                success_count,
                failed_count,
                f"完成：成功 {success_count}，失败 {failed_count}"
            )

            yield f"data: {json.dumps({'type': 'complete', 'total': total, 'success_count': success_count, 'failed_count': failed_count, 'failed_list': failed_list, 'run_id': run_id}, ensure_ascii=False)}\n\n"

        except Exception as e:
            try:
                if run_id:
                    finish_refresh_run(conn, run_id, 'failed', 0, 0, 0, str(e))
            except Exception:
                pass
            error_payload = build_error_payload(
                code="REFRESH_FAILED",
                message="刷新执行失败",
                err_type="RefreshError",
                status=500,
                details=str(e),
                trace_id=trace_id_value
            )
            yield f"data: {json.dumps({'type': 'error', 'error': error_payload}, ensure_ascii=False)}\n\n"
        finally:
            if lock_acquired:
                release_distributed_lock(conn, REFRESH_LOCK_NAME, lock_owner_id)
            conn.close()

    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/accounts/<int:account_id>/retry-refresh', methods=['POST'])
@login_required
def api_retry_refresh_account(account_id):
    """重试单个失败账号的刷新"""
    return api_refresh_account(account_id)


@app.route('/api/accounts/refresh-failed', methods=['POST'])
@login_required
def api_refresh_failed_accounts():
    """重试所有失败的账号"""
    db = get_db()
    trace_id_value = None
    try:
        trace_id_value = getattr(g, 'trace_id', None)
    except Exception:
        trace_id_value = None
    requested_by_ip = get_client_ip()
    requested_by_user_agent = get_user_agent()

    response_data, status_code = _refresh_service.refresh_failed_accounts(
        db=db,
        trace_id=trace_id_value,
        requested_by_ip=requested_by_ip,
        requested_by_user_agent=requested_by_user_agent,
        lock_name=REFRESH_LOCK_NAME,
        test_refresh_token=test_refresh_token,
    )
    return jsonify(response_data), status_code

    lock_owner_id = uuid.uuid4().hex

    # 获取最近一次刷新失败的账号列表
    cursor = db.execute('''
        SELECT DISTINCT a.id, a.email, a.client_id, a.refresh_token, a.group_id
        FROM accounts a
        INNER JOIN (
            SELECT account_id, MAX(created_at) as last_refresh
            FROM account_refresh_logs
            GROUP BY account_id
        ) latest ON a.id = latest.account_id
        INNER JOIN account_refresh_logs l ON a.id = l.account_id AND l.created_at = latest.last_refresh
        WHERE l.status = 'failed' AND a.status = 'active'
    ''')
    accounts = cursor.fetchall()

    total = len(accounts)
    run_id = create_refresh_run(
        db,
        trigger_source='retry_failed',
        trace_id=trace_id_value or generate_trace_id(),
        requested_by_ip=requested_by_ip,
        requested_by_user_agent=requested_by_user_agent,
        total=total
    )

    ttl_seconds = compute_refresh_lock_ttl_seconds(total, 0)
    ok, lock_info = acquire_distributed_lock(db, REFRESH_LOCK_NAME, lock_owner_id, ttl_seconds)
    if not ok:
        finish_refresh_run(db, run_id, 'skipped', total, 0, 0, "刷新任务冲突：已有刷新在执行")
        error_payload = build_error_payload(
            code="REFRESH_CONFLICT",
            message="当前已有刷新任务执行中，请稍后再试",
            err_type="ConflictError",
            status=409,
            details=lock_info or "",
            trace_id=trace_id_value
        )
        return jsonify({'success': False, 'error': error_payload}), 409

    success_count = 0
    failed_count = 0
    failed_list = []

    try:
        for account in accounts:
            account_id = account['id']
            account_email = account['email']
            client_id = account['client_id']
            encrypted_refresh_token = account['refresh_token']

            # 获取分组代理设置
            proxy_url = ''
            group_id = account['group_id']
            if group_id:
                try:
                    group = get_group_by_id(group_id)
                    if group:
                        proxy_url = group.get('proxy_url', '') or ''
                except Exception:
                    proxy_url = ''

            # 解密 refresh_token
            try:
                refresh_token = decrypt_data(encrypted_refresh_token) if encrypted_refresh_token else encrypted_refresh_token
            except Exception as e:
                failed_count += 1
                error_msg = f"解密 token 失败: {str(e)}"
                failed_list.append({'id': account_id, 'email': account_email, 'error': error_msg})
                log_refresh_result(account_id, account_email, 'retry', 'failed', error_msg, run_id=run_id)
                continue

            success, error_msg = test_refresh_token(client_id, refresh_token, proxy_url)
            log_refresh_result(account_id, account_email, 'retry', 'success' if success else 'failed', error_msg, run_id=run_id)

            if success:
                success_count += 1
            else:
                failed_count += 1
                failed_list.append({'id': account_id, 'email': account_email, 'error': error_msg})
    finally:
        release_distributed_lock(db, REFRESH_LOCK_NAME, lock_owner_id)

    finish_refresh_run(
        db,
        run_id,
        'completed',
        total,
        success_count,
        failed_count,
        f"完成：成功 {success_count}，失败 {failed_count}"
    )

    return jsonify({
        'success': True,
        'run_id': run_id,
        'total': total,
        'success_count': success_count,
        'failed_count': failed_count,
        'failed_list': failed_list
    })


@app.route('/api/accounts/trigger-scheduled-refresh', methods=['GET'])
@login_required
def api_trigger_scheduled_refresh():
    """手动触发定时刷新（支持强制刷新）"""
    force = request.args.get('force', 'false').lower() == 'true'
    trace_id_value = None
    try:
        trace_id_value = getattr(g, 'trace_id', None)
    except Exception:
        trace_id_value = None
    requested_by_ip = get_client_ip()
    requested_by_user_agent = get_user_agent()

    # 获取配置
    refresh_interval_days = int(get_setting('refresh_interval_days', '30'))
    use_cron = get_setting('use_cron_schedule', 'false').lower() == 'true'

    # 执行刷新（使用流式响应）
    def generate():
        yield from _refresh_service.stream_trigger_scheduled_refresh(
            force=force,
            refresh_interval_days=refresh_interval_days,
            use_cron=use_cron,
            trace_id=trace_id_value,
            requested_by_ip=requested_by_ip,
            requested_by_user_agent=requested_by_user_agent,
            lock_name=REFRESH_LOCK_NAME,
            test_refresh_token=test_refresh_token,
        )
        return

        from datetime import datetime, timedelta

        conn = create_sqlite_connection()
        lock_owner_id = uuid.uuid4().hex
        lock_acquired = False
        run_id = None
        total = 0
        success_count = 0
        failed_count = 0

        try:
            # 获取刷新间隔配置
            cursor_settings = conn.execute("SELECT value FROM settings WHERE key = 'refresh_delay_seconds'")
            delay_row = cursor_settings.fetchone()
            delay_seconds = int(delay_row['value']) if delay_row else 5

            # 清理超过半年的刷新记录
            try:
                conn.execute("DELETE FROM account_refresh_logs WHERE created_at < datetime('now', '-6 months')")
                conn.commit()
            except Exception as e:
                print(f"清理旧记录失败: {str(e)}")

            accounts = conn.execute("SELECT id, email, client_id, refresh_token, group_id FROM accounts WHERE status = 'active'").fetchall()

            total = len(accounts)
            run_id = create_refresh_run(
                conn,
                trigger_source='scheduled_manual',
                trace_id=trace_id_value or generate_trace_id(),
                requested_by_ip=requested_by_ip,
                requested_by_user_agent=requested_by_user_agent,
                total=total
            )

            # 按天数策略：未到周期则跳过（force=true 时跳过检查）
            if (not force) and (not use_cron):
                row = conn.execute('''
                    SELECT finished_at
                    FROM refresh_runs
                    WHERE trigger_source IN ('scheduled', 'scheduled_manual')
                      AND status IN ('completed', 'failed')
                      AND finished_at IS NOT NULL
                    ORDER BY finished_at DESC
                    LIMIT 1
                ''').fetchone()

                if row and row['finished_at']:
                    try:
                        last_time = datetime.fromisoformat(row['finished_at'])
                    except Exception:
                        last_time = None

                    if last_time:
                        next_due = last_time + timedelta(days=refresh_interval_days)
                        if utcnow() < next_due:
                            finish_refresh_run(
                                conn,
                                run_id,
                                'skipped',
                                0,
                                0,
                                0,
                                f"距离上次刷新未满 {refresh_interval_days} 天，下次最早：{next_due.strftime('%Y-%m-%d %H:%M:%S')}"
                            )
                            yield f"data: {json.dumps({'type': 'skipped', 'message': '未到刷新周期', 'next_due': next_due.isoformat(), 'run_id': run_id}, ensure_ascii=False)}\n\n"
                            return

            ttl_seconds = compute_refresh_lock_ttl_seconds(total, delay_seconds)
            ok, lock_info = acquire_distributed_lock(conn, REFRESH_LOCK_NAME, lock_owner_id, ttl_seconds)
            if not ok:
                finish_refresh_run(conn, run_id, 'skipped', total, 0, 0, "刷新任务冲突：已有刷新在执行")
                error_payload = build_error_payload(
                    code="REFRESH_CONFLICT",
                    message="当前已有刷新任务执行中，请稍后再试",
                    err_type="ConflictError",
                    status=409,
                    details=lock_info or "",
                    trace_id=trace_id_value
                )
                yield f"data: {json.dumps({'type': 'error', 'error': error_payload}, ensure_ascii=False)}\n\n"
                return
            lock_acquired = True

            success_count = 0
            failed_count = 0
            failed_list = []

            yield f"data: {json.dumps({'type': 'start', 'total': total, 'delay_seconds': delay_seconds, 'refresh_type': 'scheduled', 'run_id': run_id, 'trace_id': trace_id_value}, ensure_ascii=False)}\n\n"

            for index, account in enumerate(accounts, 1):
                account_id = account['id']
                account_email = account['email']
                client_id = account['client_id']
                encrypted_refresh_token = account['refresh_token']

                # 解密 refresh_token
                try:
                    refresh_token = decrypt_data(encrypted_refresh_token) if encrypted_refresh_token else encrypted_refresh_token
                except Exception as e:
                    # 解密失败，记录错误
                    failed_count += 1
                    error_msg = f"解密 token 失败: {str(e)}"
                    failed_list.append({
                        'id': account_id,
                        'email': account_email,
                        'error': error_msg
                    })
                    try:
                        conn.execute('''
                            INSERT INTO account_refresh_logs (account_id, account_email, refresh_type, status, error_message, run_id)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (account_id, account_email, 'scheduled', 'failed', error_msg, run_id))
                        conn.commit()
                    except Exception:
                        pass
                    continue

                yield f"data: {json.dumps({'type': 'progress', 'current': index, 'total': total, 'email': account_email, 'success_count': success_count, 'failed_count': failed_count}, ensure_ascii=False)}\n\n"

                # 获取分组代理设置
                proxy_url = ''
                group_id = account['group_id']
                if group_id:
                    group_cursor = conn.execute('SELECT proxy_url FROM groups WHERE id = ?', (group_id,))
                    group_row = group_cursor.fetchone()
                    if group_row:
                        proxy_url = group_row['proxy_url'] or ''

                success, error_msg = test_refresh_token(client_id, refresh_token, proxy_url)

                try:
                    conn.execute('''
                        INSERT INTO account_refresh_logs (account_id, account_email, refresh_type, status, error_message, run_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (account_id, account_email, 'scheduled', 'success' if success else 'failed', error_msg, run_id))

                    if success:
                        conn.execute('''
                            UPDATE accounts
                            SET last_refresh_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        ''', (account_id,))

                    conn.commit()
                except Exception as e:
                    print(f"记录刷新结果失败: {str(e)}")

                if success:
                    success_count += 1
                else:
                    failed_count += 1
                    failed_list.append({
                        'id': account_id,
                        'email': account_email,
                        'error': error_msg
                    })

                if index < total and delay_seconds > 0:
                    yield f"data: {json.dumps({'type': 'delay', 'seconds': delay_seconds}, ensure_ascii=False)}\n\n"
                    time.sleep(delay_seconds)

            finish_refresh_run(
                conn,
                run_id,
                'completed',
                total,
                success_count,
                failed_count,
                f"完成：成功 {success_count}，失败 {failed_count}"
            )

            yield f"data: {json.dumps({'type': 'complete', 'total': total, 'success_count': success_count, 'failed_count': failed_count, 'failed_list': failed_list, 'run_id': run_id}, ensure_ascii=False)}\n\n"

        except Exception as e:
            try:
                if run_id:
                    finish_refresh_run(conn, run_id, 'failed', total, success_count, failed_count, str(e))
            except Exception:
                pass
            error_payload = build_error_payload(
                code="REFRESH_FAILED",
                message="刷新执行失败",
                err_type="RefreshError",
                status=500,
                details=str(e),
                trace_id=trace_id_value
            )
            yield f"data: {json.dumps({'type': 'error', 'error': error_payload}, ensure_ascii=False)}\n\n"
        finally:
            if lock_acquired:
                release_distributed_lock(conn, REFRESH_LOCK_NAME, lock_owner_id)
            conn.close()

    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/accounts/refresh-logs', methods=['GET'])
@login_required
def api_get_refresh_logs():
    """获取所有账号的刷新历史（近半年）"""
    db = get_db()
    limit = int(request.args.get('limit', 1000))
    offset = int(request.args.get('offset', 0))

    cursor = db.execute('''
        SELECT l.*, a.email as account_email
        FROM account_refresh_logs l
        LEFT JOIN accounts a ON l.account_id = a.id
        WHERE l.refresh_type IN ('manual', 'manual_all', 'scheduled', 'retry')
        AND l.created_at >= datetime('now', '-6 months')
        ORDER BY l.created_at DESC
        LIMIT ? OFFSET ?
    ''', (limit, offset))

    logs = []
    for row in cursor.fetchall():
        logs.append({
            'id': row['id'],
            'account_id': row['account_id'],
            'account_email': row['account_email'] or row['account_email'],
            'refresh_type': row['refresh_type'],
            'status': row['status'],
            'error_message': row['error_message'],
            'created_at': row['created_at']
        })

    return jsonify({'success': True, 'logs': logs})


@app.route('/api/accounts/<int:account_id>/refresh-logs', methods=['GET'])
@login_required
def api_get_account_refresh_logs(account_id):
    """获取单个账号的刷新历史"""
    db = get_db()
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))

    cursor = db.execute('''
        SELECT * FROM account_refresh_logs
        WHERE account_id = ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    ''', (account_id, limit, offset))

    logs = []
    for row in cursor.fetchall():
        logs.append({
            'id': row['id'],
            'account_id': row['account_id'],
            'account_email': row['account_email'],
            'refresh_type': row['refresh_type'],
            'status': row['status'],
            'error_message': row['error_message'],
            'created_at': row['created_at']
        })

    return jsonify({'success': True, 'logs': logs})


@app.route('/api/accounts/refresh-logs/failed', methods=['GET'])
@login_required
def api_get_failed_refresh_logs():
    """获取所有失败的刷新记录"""
    db = get_db()

    # 获取每个账号最近一次失败的刷新记录
    cursor = db.execute('''
        SELECT l.*, a.email as account_email, a.status as account_status
        FROM account_refresh_logs l
        INNER JOIN (
            SELECT account_id, MAX(created_at) as last_refresh
            FROM account_refresh_logs
            GROUP BY account_id
        ) latest ON l.account_id = latest.account_id AND l.created_at = latest.last_refresh
        LEFT JOIN accounts a ON l.account_id = a.id
        WHERE l.status = 'failed'
        ORDER BY l.created_at DESC
    ''')

    logs = []
    for row in cursor.fetchall():
        logs.append({
            'id': row['id'],
            'account_id': row['account_id'],
            'account_email': row['account_email'] or row['account_email'],
            'account_status': row['account_status'],
            'refresh_type': row['refresh_type'],
            'status': row['status'],
            'error_message': row['error_message'],
            'created_at': row['created_at']
        })

    return jsonify({'success': True, 'logs': logs})


@app.route('/api/accounts/refresh-stats', methods=['GET'])
@login_required
def api_get_refresh_stats():
    """获取刷新统计信息（统计当前失败状态的邮箱数量）"""
    db = get_db()

    cursor = db.execute('''
        SELECT MAX(created_at) as last_refresh_time
        FROM account_refresh_logs
        WHERE refresh_type IN ('manual', 'manual_all', 'scheduled', 'retry')
    ''')
    row = cursor.fetchone()
    last_refresh_time = row['last_refresh_time'] if row else None

    cursor = db.execute('''
        SELECT COUNT(*) as total_accounts
        FROM accounts
        WHERE status = 'active'
    ''')
    total_accounts = cursor.fetchone()['total_accounts']

    cursor = db.execute('''
        SELECT COUNT(DISTINCT l.account_id) as failed_count
        FROM account_refresh_logs l
        INNER JOIN (
            SELECT account_id, MAX(created_at) as last_refresh
            FROM account_refresh_logs
            GROUP BY account_id
        ) latest ON l.account_id = latest.account_id AND l.created_at = latest.last_refresh
        INNER JOIN accounts a ON l.account_id = a.id
        WHERE l.status = 'failed' AND a.status = 'active'
    ''')
    failed_count = cursor.fetchone()['failed_count']

    return jsonify({
        'success': True,
        'stats': {
            'total': total_accounts,
            'success_count': total_accounts - failed_count,
            'failed_count': failed_count,
            'last_refresh_time': last_refresh_time
        }
    })


# ==================== 邮件 API ====================



# ==================== Email Deletion Helpers ====================

def delete_emails_graph(client_id: str, refresh_token: str, message_ids: List[str], proxy_url: str = None) -> Dict[str, Any]:
    """通过 Graph API 批量删除邮件（永久删除）"""
    token_result = get_access_token_graph_result(client_id, refresh_token, proxy_url)
    if not token_result.get("success"):
        return {"success": False, "error": token_result.get("error")}

    access_token = token_result.get("access_token")
    if not access_token:
        return {
            "success": False,
            "error": build_error_payload(
                "GRAPH_TOKEN_FAILED",
                "获取访问令牌失败",
                "GraphAPIError",
                500,
                "empty_access_token",
            ),
        }

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    # Graph API 不支持一次性批量删除所有邮件，需要逐个删除
    # 但可以使用 batch 请求来优化
    # https://learn.microsoft.com/en-us/graph/json-batching
    
    # 限制每批次请求数量（Graph API 限制为 20）
    BATCH_SIZE = 20
    success_count = 0
    failed_count = 0
    errors = []

    for i in range(0, len(message_ids), BATCH_SIZE):
        batch = message_ids[i:i + BATCH_SIZE]
        
        # 构造 batch 请求 body
        batch_requests = []
        for idx, msg_id in enumerate(batch):
            batch_requests.append({
                "id": str(idx),
                "method": "DELETE",
                "url": f"/me/messages/{msg_id}"
            })
        
        try:
            proxies = build_proxies(proxy_url)
            response = requests.post(
                "https://graph.microsoft.com/v1.0/$batch",
                headers=headers,
                json={"requests": batch_requests},
                timeout=30,
                proxies=proxies
            )
            
            if response.status_code == 200:
                results = response.json().get("responses", [])
                for res in results:
                    if res.get("status") in [200, 204]:
                        success_count += 1
                    else:
                        failed_count += 1
                        # 记录具体错误
                        errors.append(f"Msg ID: {batch[int(res['id'])]}, Status: {res.get('status')}")
            else:
                failed_count += len(batch)
                errors.append(f"Batch request failed: {response.text}")
                
        except Exception as e:
            failed_count += len(batch)
            errors.append(f"Network error: {str(e)}")

    result = {
        "success": success_count > 0,
        "partial_success": success_count > 0 and failed_count > 0,
        "success_count": success_count,
        "failed_count": failed_count,
        "errors": errors,
    }

    if not result["success"]:
        result["error"] = build_error_payload(
            "EMAIL_DELETE_FAILED",
            "删除邮件失败",
            "GraphAPIError",
            502,
            {"failed_count": failed_count, "errors": errors[:10]},
        )

    return result

def delete_emails_imap(email_addr: str, client_id: str, refresh_token: str, message_ids: List[str], server: str) -> Dict[str, Any]:
    """通过 IMAP 删除邮件（永久删除）"""
    access_token = get_access_token_graph(client_id, refresh_token)
    if not access_token:
        return {"success": False, "error": "获取 Access Token 失败"}
        
    try:
        # 生成 OAuth2 认证字符串
        auth_string = 'user=%s\x01auth=Bearer %s\x01\x01' % (email_addr, access_token)
        
        # 连接 IMAP
        imap = imaplib.IMAP4_SSL(server, IMAP_PORT)
        imap.authenticate('XOAUTH2', lambda x: auth_string.encode('utf-8'))
        
        # 选择文件夹
        imap.select('INBOX')
        
        # IMAP 删除需要 UID。如果我们没有 UID，这很难。
        # 鉴于我们只实现了 Graph 删除，并且 fallback 到 IMAP 比较复杂，
        # 这里暂时返回不支持，或仅做简单的尝试（如果 ID 恰好是 UID）
        # 但通常 Graph ID 不是 UID。
        
        return {"success": False, "error": "IMAP 删除暂不支持 (ID 格式不兼容)"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


# 兼容导出：邮件删除实现已模块化到 outlook_web.services.graph / outlook_web.services.imap
delete_emails_graph = _graph_service.delete_emails_graph
delete_emails_imap = _imap_service.delete_emails_imap


@app.route('/api/emails/<email_addr>')
@login_required
def api_get_emails(email_addr):
    """获取邮件列表（支持分页，不使用缓存）"""
    account = get_account_by_email(email_addr)

    if not account:
        error_payload = build_error_payload(
            "ACCOUNT_NOT_FOUND",
            "账号不存在",
            "NotFoundError",
            404,
            f"email={email_addr}"
        )
        return jsonify({'success': False, 'error': error_payload})

    folder = request.args.get('folder', 'inbox')  # inbox, junkemail, deleteditems
    skip = int(request.args.get('skip', 0))
    top = int(request.args.get('top', 20))

    # 获取分组代理设置
    proxy_url = ''
    if account.get('group_id'):
        group = get_group_by_id(account['group_id'])
        if group:
            proxy_url = group.get('proxy_url', '') or ''

    # 收集所有错误信息
    all_errors = {}

    # 1. 尝试 Graph API
    graph_result = get_emails_graph(account['client_id'], account['refresh_token'], folder, skip, top, proxy_url)
    if graph_result.get("success"):
        emails = graph_result.get("emails", [])
        # 更新刷新时间
        db = get_db()
        db.execute('''
            UPDATE accounts
            SET last_refresh_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE email = ?
        ''', (email_addr,))
        db.commit()

        # 格式化 Graph API 返回的数据
        formatted = []
        for e in emails:
            formatted.append({
                'id': e.get('id'),
                'subject': e.get('subject', '无主题'),
                'from': e.get('from', {}).get('emailAddress', {}).get('address', '未知'),
                'date': e.get('receivedDateTime', ''),
                'is_read': e.get('isRead', False),
                'has_attachments': e.get('hasAttachments', False),
                'body_preview': e.get('bodyPreview', '')
            })

        return jsonify({
            'success': True,
            'emails': formatted,
            'method': 'Graph API',
            'has_more': len(formatted) >= top
        })
    else:
        graph_error = graph_result.get("error")
        all_errors["graph"] = graph_error

        # 如果是代理错误，不再回退 IMAP
        if isinstance(graph_error, dict) and graph_error.get('type') in ('ProxyError', 'ConnectionError'):
            return jsonify({
                'success': False,
                'error': '代理连接失败，请检查分组代理设置',
                'details': all_errors
            })

    imap_new_result = get_emails_imap_with_server(
        account['email'], account['client_id'], account['refresh_token'],
        folder, skip, top, IMAP_SERVER_NEW
    )
    if imap_new_result.get("success"):
        return jsonify({
            'success': True,
            'emails': imap_new_result.get("emails", []),
            'method': 'IMAP (New)',
            'has_more': False # IMAP 分页暂未完全实现，视情况
        })
    else:
        all_errors["imap_new"] = imap_new_result.get("error")

    # 3. 尝试旧版 IMAP (outlook.office365.com)
    imap_old_result = get_emails_imap_with_server(
        account['email'], account['client_id'], account['refresh_token'],
        folder, skip, top, IMAP_SERVER_OLD
    )
    if imap_old_result.get("success"):
        return jsonify({
            'success': True,
            'emails': imap_old_result.get("emails", []),
            'method': 'IMAP (Old)',
            'has_more': False
        })
    else:
        all_errors["imap_old"] = imap_old_result.get("error")

    return jsonify({
        'success': False, 
        'error': '无法获取邮件，所有方式均失败',
        'details': all_errors
    })

@app.route('/api/emails/delete', methods=['POST'])
@login_required
def api_delete_emails():
    """批量删除邮件（永久删除）"""
    data = request.json
    email_addr = data.get('email', '')
    message_ids = data.get('ids', [])
    
    if not email_addr or not message_ids:
        return jsonify({'success': False, 'error': '参数不完整'})

    account = get_account_by_email(email_addr)
    if not account:
        return jsonify({'success': False, 'error': '账号不存在'})

    # 获取分组代理设置
    proxy_url = ''
    if account.get('group_id'):
        group = get_group_by_id(account['group_id'])
        if group:
            proxy_url = group.get('proxy_url', '') or ''

    from outlook_web.services import email_delete as _email_delete_service

    response_data, method_used = _email_delete_service.delete_emails_with_fallback(
        email_addr=email_addr,
        client_id=account["client_id"],
        refresh_token=account["refresh_token"],
        message_ids=message_ids,
        proxy_url=proxy_url,
        delete_emails_graph=delete_emails_graph,
        delete_emails_imap=delete_emails_imap,
        imap_server_new=IMAP_SERVER_NEW,
        imap_server_old=IMAP_SERVER_OLD,
    )

    if method_used == "graph":
        log_audit("delete", "email", email_addr, f"删除邮件 {len(message_ids)} 封（Graph API）")
    elif method_used == "imap_new":
        log_audit("delete", "email", email_addr, f"删除邮件 {len(message_ids)} 封（IMAP New）")
    elif method_used == "imap_old":
        log_audit("delete", "email", email_addr, f"删除邮件 {len(message_ids)} 封（IMAP Old）")

    return jsonify(response_data)



@app.route('/api/email/<email_addr>/<path:message_id>')
@login_required
def api_get_email_detail(email_addr, message_id):
    """获取邮件详情"""
    account = get_account_by_email(email_addr)

    if not account:
        return jsonify({'success': False, 'error': '账号不存在'})

    method = request.args.get('method', 'graph')
    folder = request.args.get('folder', 'inbox')

    if method == 'graph':
        # 获取分组代理设置
        proxy_url = ''
        if account.get('group_id'):
            group = get_group_by_id(account['group_id'])
            if group:
                proxy_url = group.get('proxy_url', '') or ''

        detail = get_email_detail_graph(account['client_id'], account['refresh_token'], message_id, proxy_url)
        if detail:
            return jsonify({
                'success': True,
                'email': {
                    'id': detail.get('id'),
                    'subject': detail.get('subject', '无主题'),
                    'from': detail.get('from', {}).get('emailAddress', {}).get('address', '未知'),
                    'to': ', '.join([r.get('emailAddress', {}).get('address', '') for r in detail.get('toRecipients', [])]),
                    'cc': ', '.join([r.get('emailAddress', {}).get('address', '') for r in detail.get('ccRecipients', [])]),
                    'date': detail.get('receivedDateTime', ''),
                    'body': detail.get('body', {}).get('content', ''),
                    'body_type': detail.get('body', {}).get('contentType', 'text')
                }
            })

    # 如果 Graph API 失败，尝试 IMAP
    detail = get_email_detail_imap(account['email'], account['client_id'], account['refresh_token'], message_id, folder)
    if detail:
        return jsonify({'success': True, 'email': detail})

    return jsonify({'success': False, 'error': '获取邮件详情失败'})


# ==================== 验证码提取 API ====================

@app.route('/api/emails/<email_addr>/extract-verification')
@login_required
def api_extract_verification(email_addr):
    """
    提取验证码和链接接口

    功能：从指定邮箱的最新邮件中提取验证码和链接

    实现策略（多 API 回退机制）：
    1. Graph API (inbox) - 优先从收件箱获取
    2. Graph API (junkemail) - 从垃圾邮件获取
    3. IMAP (新服务器) - Graph API 失败时回退
    4. IMAP (旧服务器) - 最后的回退方案

    提取算法：
    - 智能识别：基于关键词（"验证码"、"code"等）上下文提取
    - 保底提取：正则匹配 4-8 位数字/字母组合，过滤年份/时间
    - 链接提取：提取所有 HTTP/HTTPS 链接

    参数：
    - email_addr: 邮箱地址（路径参数）

    返回：
    成功：
    {
        "success": true,
        "data": {
            "verification_code": "123456",
            "links": ["https://example.com/verify"],
            "formatted": "123456 https://example.com/verify"
        },
        "message": "提取成功"
    }

    失败：
    {
        "success": false,
        "error": "未找到验证信息",
        "trace_id": "xxx"
    }

    性能考虑：
    - 最多 4 次 API 调用（2 Graph + 2 IMAP）
    - 建议添加缓存机制，避免短时间内重复提取

    关联文档：PRD-批量操作与自动化增强、TDD-验证码提取测试
    关联服务：outlook_web/services/verification_extractor.py
    """
    from outlook_web.services.verification_extractor import (
        extract_verification_info,
        extract_verification_info_from_text,
        extract_email_text
    )

    # 获取账号信息
    account = get_account_by_email(email_addr)

    if not account:
        error_payload = build_error_payload(
            "ACCOUNT_NOT_FOUND",
            "邮箱不存在",
            "NotFoundError",
            404,
            f"email={email_addr}"
        )
        return jsonify({'success': False, 'error': error_payload}), 404

    # 获取分组代理设置
    proxy_url = ''
    if account.get('group_id'):
        group = get_group_by_id(account['group_id'])
        if group:
            proxy_url = group.get('proxy_url', '') or ''

    # 收集邮件（同时从收件箱和垃圾邮件获取）
    emails = []
    graph_success = False

    # 1. 尝试 Graph API 从收件箱获取最新邮件
    try:
        inbox_result = get_emails_graph(
            account['client_id'],
            account['refresh_token'],
            folder='inbox',
            skip=0,
            top=1,
            proxy_url=proxy_url
        )
        if inbox_result.get("success"):
            emails.extend(inbox_result.get("emails", []))
            graph_success = True
    except Exception:
        pass

    # 2. 尝试 Graph API 从垃圾邮件获取最新邮件
    try:
        junk_result = get_emails_graph(
            account['client_id'],
            account['refresh_token'],
            folder='junkemail',
            skip=0,
            top=1,
            proxy_url=proxy_url
        )
        if junk_result.get("success"):
            emails.extend(junk_result.get("emails", []))
            graph_success = True
    except Exception:
        pass

    # 3. 如果 Graph API 失败，尝试 IMAP 回退
    if not graph_success or not emails:
        # 尝试新版 IMAP 服务器
        try:
            imap_new_result = get_emails_imap_with_server(
                account['email'], account['client_id'], account['refresh_token'],
                folder='inbox', skip=0, top=1, server=IMAP_SERVER_NEW
            )
            if imap_new_result.get("success"):
                emails.extend(imap_new_result.get("emails", []))
        except Exception:
            pass

        # 尝试旧版 IMAP 服务器
        try:
            imap_old_result = get_emails_imap_with_server(
                account['email'], account['client_id'], account['refresh_token'],
                folder='inbox', skip=0, top=1, server=IMAP_SERVER_OLD
            )
            if imap_old_result.get("success"):
                emails.extend(imap_old_result.get("emails", []))
        except Exception:
            pass

    if not emails:
        error_payload = build_error_payload(
            "EMAIL_NOT_FOUND",
            "未找到邮件",
            "NotFoundError",
            404,
            f"email={email_addr}"
        )
        return jsonify({'success': False, 'error': error_payload}), 404

    # 按时间排序，取最新的一封
    emails.sort(key=lambda x: x.get('receivedDateTime', '') or x.get('date', ''), reverse=True)
    latest_email = emails[0]

    # 获取邮件详情以获取完整内容
    email_detail = None

    # 尝试 Graph API 获取详情
    try:
        email_detail = get_email_detail_graph(
            account['client_id'],
            account['refresh_token'],
            latest_email.get('id'),
            proxy_url
        )
    except Exception:
        pass

    # 如果 Graph API 失败，尝试 IMAP 获取详情
    if not email_detail:
        try:
            email_detail = get_email_detail_imap(
                account['email'],
                account['client_id'],
                account['refresh_token'],
                latest_email.get('id'),
                'inbox'
            )
        except Exception:
            pass

    # 构建邮件对象用于提取
    email_obj = {
        'subject': latest_email.get('subject', ''),
        'body_preview': latest_email.get('bodyPreview', '') or latest_email.get('body_preview', '')
    }

    if email_detail:
        # Graph API 格式
        if 'body' in email_detail:
            body_content = email_detail.get('body', {})
            email_obj['body'] = body_content.get('content', '') if body_content.get('contentType') == 'text' else ''
            email_obj['body_html'] = body_content.get('content', '') if body_content.get('contentType') == 'html' else ''
            email_obj['bodyContent'] = body_content.get('content', '')
            email_obj['bodyContentType'] = body_content.get('contentType', 'text')
        # IMAP 格式
        elif 'body' in email_detail or 'body_html' in email_detail:
            email_obj['body'] = email_detail.get('body', '')
            email_obj['body_html'] = email_detail.get('body_html', '')

    try:
        # 尝试从邮件详情提取验证信息
        result = extract_verification_info(email_obj)

        return jsonify({
            'success': True,
            'data': result,
            'message': '提取成功'
        })

    except ValueError as e:
        # 未找到验证信息
        error_payload = build_error_payload(
            "VERIFICATION_NOT_FOUND",
            str(e),
            "NotFoundError",
            404,
            f"email={email_addr}"
        )
        return jsonify({'success': False, 'error': error_payload}), 404

    except Exception as e:
        # 其他错误
        error_payload = build_error_payload(
            "EXTRACT_ERROR",
            "提取失败",
            "ExtractError",
            500,
            str(e)
        )
        return jsonify({'success': False, 'error': error_payload}), 500


# ==================== GPTMail 临时邮箱 API ====================

def gptmail_request(method: str, endpoint: str, params: dict = None, json_data: dict = None) -> Optional[Dict]:
    """发送 GPTMail API 请求"""
    try:
        url = f"{GPTMAIL_BASE_URL}{endpoint}"
        # 从数据库获取 API Key
        api_key = get_gptmail_api_key()
        headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json"
        }
        
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers, params=params, timeout=30)
        elif method.upper() == 'POST':
            response = requests.post(url, headers=headers, json=json_data, timeout=30)
        elif method.upper() == 'DELETE':
            response = requests.delete(url, headers=headers, params=params, timeout=30)
        else:
            return None
        
        if response.status_code == 200:
            return response.json()
        else:
            return {'success': False, 'error': f'API 请求失败: {response.status_code}'}
    except Exception as e:
        return {'success': False, 'error': f'请求异常: {str(e)}'}


def generate_temp_email(prefix: str = None, domain: str = None) -> Optional[str]:
    """生成临时邮箱地址"""
    json_data = {}
    if prefix:
        json_data['prefix'] = prefix
    if domain:
        json_data['domain'] = domain
    
    if json_data:
        result = gptmail_request('POST', '/api/generate-email', json_data=json_data)
    else:
        result = gptmail_request('GET', '/api/generate-email')
    
    if result and result.get('success'):
        return result.get('data', {}).get('email')
    return None


def get_temp_emails_from_api(email_addr: str) -> Optional[List[Dict]]:
    """从 GPTMail API 获取邮件列表"""
    result = gptmail_request('GET', '/api/emails', params={'email': email_addr})
    
    if result and result.get('success'):
        return result.get('data', {}).get('emails', [])
    return None


def get_temp_email_detail_from_api(message_id: str) -> Optional[Dict]:
    """从 GPTMail API 获取邮件详情"""
    result = gptmail_request('GET', f'/api/email/{message_id}')
    
    if result and result.get('success'):
        return result.get('data')
    return None


def delete_temp_email_from_api(message_id: str) -> bool:
    """从 GPTMail API 删除邮件"""
    result = gptmail_request('DELETE', f'/api/email/{message_id}')
    return result and result.get('success', False)


def clear_temp_emails_from_api(email_addr: str) -> bool:
    """清空 GPTMail 邮箱的所有邮件"""
    result = gptmail_request('DELETE', '/api/emails/clear', params={'email': email_addr})
    return result and result.get('success', False)


# 兼容导出：GPTMail 服务已模块化到 outlook_web.services.gptmail
from outlook_web.services import gptmail as _gptmail_service  # noqa: E402

gptmail_request = _gptmail_service.gptmail_request
generate_temp_email = _gptmail_service.generate_temp_email
get_temp_emails_from_api = _gptmail_service.get_temp_emails_from_api
get_temp_email_detail_from_api = _gptmail_service.get_temp_email_detail_from_api
delete_temp_email_from_api = _gptmail_service.delete_temp_email_from_api
clear_temp_emails_from_api = _gptmail_service.clear_temp_emails_from_api


# ==================== 临时邮箱数据库操作 ====================

def get_temp_email_group_id() -> int:
    """获取临时邮箱分组的 ID"""
    db = get_db()
    cursor = db.execute("SELECT id FROM groups WHERE name = '临时邮箱'")
    row = cursor.fetchone()
    return row['id'] if row else 2


def load_temp_emails() -> List[Dict]:
    """加载所有临时邮箱"""
    db = get_db()
    cursor = db.execute('SELECT * FROM temp_emails ORDER BY created_at DESC')
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


def get_temp_email_by_address(email_addr: str) -> Optional[Dict]:
    """根据邮箱地址获取临时邮箱"""
    db = get_db()
    cursor = db.execute('SELECT * FROM temp_emails WHERE email = ?', (email_addr,))
    row = cursor.fetchone()
    return dict(row) if row else None


def add_temp_email(email_addr: str) -> bool:
    """添加临时邮箱"""
    db = get_db()
    try:
        db.execute('INSERT INTO temp_emails (email) VALUES (?)', (email_addr,))
        db.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def delete_temp_email(email_addr: str) -> bool:
    """删除临时邮箱及其所有邮件"""
    db = get_db()
    try:
        db.execute('DELETE FROM temp_email_messages WHERE email_address = ?', (email_addr,))
        db.execute('DELETE FROM temp_emails WHERE email = ?', (email_addr,))
        db.commit()
        return True
    except Exception:
        return False


def save_temp_email_messages(email_addr: str, messages: List[Dict]) -> int:
    """保存临时邮件到数据库"""
    db = get_db()
    saved = 0
    for msg in messages:
        try:
            db.execute('''
                INSERT OR REPLACE INTO temp_email_messages
                (message_id, email_address, from_address, subject, content, html_content, has_html, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                msg.get('id'),
                email_addr,
                msg.get('from_address', ''),
                msg.get('subject', ''),
                msg.get('content', ''),
                msg.get('html_content', ''),
                1 if msg.get('has_html') else 0,
                msg.get('timestamp', 0)
            ))
            saved += 1
        except Exception:
            continue
    db.commit()
    return saved


def get_temp_email_messages(email_addr: str) -> List[Dict]:
    """获取临时邮箱的所有邮件（从数据库）"""
    db = get_db()
    cursor = db.execute('''
        SELECT * FROM temp_email_messages
        WHERE email_address = ?
        ORDER BY timestamp DESC
    ''', (email_addr,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


def get_temp_email_message_by_id(message_id: str) -> Optional[Dict]:
    """根据 ID 获取临时邮件"""
    db = get_db()
    cursor = db.execute('SELECT * FROM temp_email_messages WHERE message_id = ?', (message_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


def delete_temp_email_message(message_id: str) -> bool:
    """删除临时邮件"""
    db = get_db()
    try:
        db.execute('DELETE FROM temp_email_messages WHERE message_id = ?', (message_id,))
        db.commit()
        return True
    except Exception:
        return False


def get_temp_email_count() -> int:
    """获取临时邮箱数量"""
    db = get_db()
    cursor = db.execute('SELECT COUNT(*) as count FROM temp_emails')
    row = cursor.fetchone()
    return row['count'] if row else 0


# 兼容导出：临时邮箱 repositories（SQL）已模块化到 outlook_web.repositories.temp_emails
from outlook_web.repositories import temp_emails as _temp_emails_repo  # noqa: E402

get_temp_email_group_id = _temp_emails_repo.get_temp_email_group_id
load_temp_emails = _temp_emails_repo.load_temp_emails
get_temp_email_by_address = _temp_emails_repo.get_temp_email_by_address
add_temp_email = _temp_emails_repo.add_temp_email
delete_temp_email = _temp_emails_repo.delete_temp_email
save_temp_email_messages = _temp_emails_repo.save_temp_email_messages
get_temp_email_messages = _temp_emails_repo.get_temp_email_messages
get_temp_email_message_by_id = _temp_emails_repo.get_temp_email_message_by_id
delete_temp_email_message = _temp_emails_repo.delete_temp_email_message
get_temp_email_count = _temp_emails_repo.get_temp_email_count


# ==================== 临时邮箱 API 路由 ====================

@app.route('/api/temp-emails', methods=['GET'])
@login_required
def api_get_temp_emails():
    """获取所有临时邮箱"""
    emails = load_temp_emails()
    return jsonify({'success': True, 'emails': emails})


@app.route('/api/temp-emails/generate', methods=['POST'])
@login_required
def api_generate_temp_email():
    """生成新的临时邮箱"""
    import logging
    logger = logging.getLogger(__name__)

    data = request.json or {}
    prefix = data.get('prefix')
    domain = data.get('domain')

    # 调用改进后的 generate_temp_email，返回 (email_addr, error_msg)
    email_addr, error_msg = generate_temp_email(prefix, domain)

    if email_addr:
        # 成功生成邮箱地址
        if add_temp_email(email_addr):
            log_audit('create', 'temp_email', email_addr, "生成临时邮箱")
            logger.info(f"临时邮箱生成成功: {email_addr}")
            return jsonify({'success': True, 'email': email_addr, 'message': '临时邮箱创建成功'})
        else:
            logger.warning(f"临时邮箱已存在: {email_addr}")
            return jsonify({'success': False, 'error': '邮箱已存在'})
    else:
        # 生成失败，返回详细错误信息
        logger.error(f"临时邮箱生成失败: {error_msg}, prefix={prefix}, domain={domain}")
        return jsonify({'success': False, 'error': error_msg or '生成临时邮箱失败，请稍后重试'})


@app.route('/api/temp-emails/<path:email_addr>', methods=['DELETE'])
@login_required
def api_delete_temp_email(email_addr):
    """删除临时邮箱"""
    if delete_temp_email(email_addr):
        log_audit('delete', 'temp_email', email_addr, "删除临时邮箱")
        return jsonify({'success': True, 'message': '临时邮箱已删除'})
    else:
        return jsonify({'success': False, 'error': '删除失败'})


@app.route('/api/temp-emails/<path:email_addr>/messages', methods=['GET'])
@login_required
def api_get_temp_email_messages(email_addr):
    """获取临时邮箱的邮件列表"""
    api_messages = get_temp_emails_from_api(email_addr)
    
    if api_messages:
        save_temp_email_messages(email_addr, api_messages)
    
    messages = get_temp_email_messages(email_addr)
    
    formatted = []
    for msg in messages:
        formatted.append({
            'id': msg.get('message_id'),
            'from': msg.get('from_address', '未知'),
            'subject': msg.get('subject', '无主题'),
            'body_preview': (msg.get('content', '') or '')[:200],
            'date': msg.get('created_at', ''),
            'timestamp': msg.get('timestamp', 0),
            'has_html': msg.get('has_html', 0)
        })
    
    return jsonify({
        'success': True,
        'emails': formatted,
        'count': len(formatted),
        'method': 'GPTMail'
    })


@app.route('/api/temp-emails/<path:email_addr>/messages/<path:message_id>', methods=['GET'])
@login_required
def api_get_temp_email_message_detail(email_addr, message_id):
    """获取临时邮件详情"""
    msg = get_temp_email_message_by_id(message_id)
    
    if not msg:
        api_msg = get_temp_email_detail_from_api(message_id)
        if api_msg:
            save_temp_email_messages(email_addr, [api_msg])
            msg = get_temp_email_message_by_id(message_id)
    
    if msg:
        return jsonify({
            'success': True,
            'email': {
                'id': msg.get('message_id'),
                'from': msg.get('from_address', '未知'),
                'to': email_addr,
                'subject': msg.get('subject', '无主题'),
                'body': msg.get('html_content') if msg.get('has_html') else msg.get('content', ''),
                'body_type': 'html' if msg.get('has_html') else 'text',
                'date': msg.get('created_at', ''),
                'timestamp': msg.get('timestamp', 0)
            }
        })
    else:
        return jsonify({'success': False, 'error': '邮件不存在'})


@app.route('/api/temp-emails/<path:email_addr>/messages/<path:message_id>', methods=['DELETE'])
@login_required
def api_delete_temp_email_message(email_addr, message_id):
    """删除临时邮件"""
    delete_temp_email_from_api(message_id)
    if delete_temp_email_message(message_id):
        log_audit('delete', 'temp_email_message', message_id, f"删除临时邮件（email={email_addr}）")
        return jsonify({'success': True, 'message': '邮件已删除'})
    else:
        return jsonify({'success': False, 'error': '删除失败'})


@app.route('/api/temp-emails/<path:email_addr>/clear', methods=['DELETE'])
@login_required
def api_clear_temp_email_messages(email_addr):
    """清空临时邮箱的所有邮件"""
    clear_temp_emails_from_api(email_addr)
    db = get_db()
    try:
        row = db.execute(
            'SELECT COUNT(*) as c FROM temp_email_messages WHERE email_address = ?',
            (email_addr,)
        ).fetchone()
        deleted_count = row['c'] if row else 0
        db.execute('DELETE FROM temp_email_messages WHERE email_address = ?', (email_addr,))
        db.commit()
        log_audit('delete', 'temp_email_messages', email_addr, f"清空临时邮箱邮件（count={deleted_count}）")
        return jsonify({'success': True, 'message': '邮件已清空'})
    except Exception:
        return jsonify({'success': False, 'error': '清空失败'})


@app.route('/api/temp-emails/<path:email_addr>/refresh', methods=['POST'])
@login_required
def api_refresh_temp_email_messages(email_addr):
    """刷新临时邮箱的邮件"""
    api_messages = get_temp_emails_from_api(email_addr)
    
    if api_messages is not None:
        saved = save_temp_email_messages(email_addr, api_messages)
        messages = get_temp_email_messages(email_addr)
        
        formatted = []
        for msg in messages:
            formatted.append({
                'id': msg.get('message_id'),
                'from': msg.get('from_address', '未知'),
                'subject': msg.get('subject', '无主题'),
                'body_preview': (msg.get('content', '') or '')[:200],
                'date': msg.get('created_at', ''),
                'timestamp': msg.get('timestamp', 0),
                'has_html': msg.get('has_html', 0)
            })
        
        return jsonify({
            'success': True,
            'emails': formatted,
            'count': len(formatted),
            'new_count': saved,
            'method': 'GPTMail'
        })
    else:
        return jsonify({'success': False, 'error': '获取邮件失败'})


# ==================== OAuth Token API ====================

@app.route('/api/oauth/auth-url', methods=['GET'])
@login_required
def api_get_oauth_auth_url():
    """生成 OAuth 授权 URL"""
    import urllib.parse

    base_auth_url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    params = {
        "client_id": OAUTH_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": OAUTH_REDIRECT_URI,
        "response_mode": "query",
        "scope": " ".join(OAUTH_SCOPES),
        "state": "12345"
    }
    auth_url = f"{base_auth_url}?{urllib.parse.urlencode(params)}"

    return jsonify({
        'success': True,
        'auth_url': auth_url,
        'client_id': OAUTH_CLIENT_ID,
        'redirect_uri': OAUTH_REDIRECT_URI
    })


@app.route('/api/oauth/exchange-token', methods=['POST'])
@login_required
def api_exchange_oauth_token():
    """使用授权码换取 Refresh Token"""
    import urllib.parse

    data = request.json
    redirected_url = data.get('redirected_url', '').strip()
    verify_token = data.get('verify_token')

    if not redirected_url:
        return jsonify({'success': False, 'error': '请提供授权后的完整 URL'})

    # 从 URL 中提取 code
    try:
        parsed_url = urllib.parse.urlparse(redirected_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        auth_code = query_params['code'][0]
    except (KeyError, IndexError):
        return jsonify({'success': False, 'error': '无法从 URL 中提取授权码，请检查 URL 是否正确'})

    # 二次验证（敏感信息：refresh_token 不默认明文返回）
    ok, error_message = check_export_verify_token(verify_token)
    if not ok:
        return jsonify({'success': False, 'error': error_message, 'need_verify': True}), 401

    # 使用 Code 换取 Token (Public Client 不需要 client_secret)
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    token_data = {
        "client_id": OAUTH_CLIENT_ID,
        "code": auth_code,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "grant_type": "authorization_code",
        "scope": " ".join(OAUTH_SCOPES)
    }

    try:
        response = requests.post(token_url, data=token_data, timeout=30)
    except Exception as e:
        return jsonify({'success': False, 'error': f'请求失败: {str(e)}'})

    if response.status_code == 200:
        tokens = response.json()
        refresh_token = tokens.get('refresh_token')

        if not refresh_token:
            return jsonify({'success': False, 'error': '未能获取 Refresh Token'})

        # 成功后再消费一次性验证 token（避免失败时消耗 token）
        ok, error_message = consume_export_verify_token(verify_token)
        if not ok:
            return jsonify({'success': False, 'error': error_message, 'need_verify': True}), 401

        log_audit('oauth_exchange', 'oauth', None, "换取 Refresh Token 成功（已二次验证）")

        return jsonify({
            'success': True,
            'refresh_token': refresh_token,
            'client_id': OAUTH_CLIENT_ID,
            'token_type': tokens.get('token_type'),
            'expires_in': tokens.get('expires_in'),
            'scope': tokens.get('scope')
        })
    else:
        error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
        error_msg = error_data.get('error_description', response.text)
        return jsonify({'success': False, 'error': f'获取令牌失败: {error_msg}'})


# ==================== 设置 API ====================

@app.route('/api/settings/validate-cron', methods=['POST'])
@login_required
def api_validate_cron():
    """验证 Cron 表达式"""
    try:
        from croniter import croniter
        from datetime import datetime
    except ImportError:
        return jsonify({'success': False, 'error': 'croniter 库未安装，请运行: pip install croniter'})

    data = request.json
    cron_expr = data.get('cron_expression', '').strip()

    if not cron_expr:
        return jsonify({'success': False, 'error': 'Cron 表达式不能为空'})

    try:
        base_time = datetime.now()
        cron = croniter(cron_expr, base_time)

        next_run = cron.get_next(datetime)

        future_runs = []
        temp_cron = croniter(cron_expr, base_time)
        for _ in range(5):
            future_runs.append(temp_cron.get_next(datetime).isoformat())

        return jsonify({
            'success': True,
            'valid': True,
            'next_run': next_run.isoformat(),
            'future_runs': future_runs
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'valid': False,
            'error': f'Cron 表达式无效: {str(e)}'
        })


@app.route('/api/settings', methods=['GET'])
@login_required
def api_get_settings():
    """获取所有设置"""
    all_settings = get_all_settings()

    def mask_secret_value(value: str, head: int = 4, tail: int = 4) -> str:
        if not value:
            return ''
        safe_value = str(value)
        if len(safe_value) <= head + tail:
            return '*' * len(safe_value)
        return safe_value[:head] + ('*' * (len(safe_value) - head - tail)) + safe_value[-tail:]

    # 仅返回前端需要的设置项（避免把敏感字段/内部状态直接返回）
    safe_settings = {
        'refresh_interval_days': all_settings.get('refresh_interval_days', '30'),
        'refresh_delay_seconds': all_settings.get('refresh_delay_seconds', '5'),
        'refresh_cron': all_settings.get('refresh_cron', '0 2 * * *'),
        'use_cron_schedule': all_settings.get('use_cron_schedule', 'false'),
        'enable_scheduled_refresh': all_settings.get('enable_scheduled_refresh', 'true'),
        # 轮询配置
        'enable_auto_polling': all_settings.get('enable_auto_polling', 'false') == 'true',
        'polling_interval': int(all_settings.get('polling_interval', '10')),
        'polling_count': int(all_settings.get('polling_count', '5'))
    }

    # 敏感字段：不返回明文/哈希，仅提供“是否已设置/脱敏展示”
    login_password_value = all_settings.get('login_password') or ''
    gptmail_api_key_value = all_settings.get('gptmail_api_key') or ''
    safe_settings['login_password_set'] = bool(login_password_value)
    safe_settings['gptmail_api_key_set'] = bool(gptmail_api_key_value)
    safe_settings['gptmail_api_key_masked'] = mask_secret_value(gptmail_api_key_value) if gptmail_api_key_value else ''

    return jsonify({'success': True, 'settings': safe_settings})


@app.route('/api/settings', methods=['PUT'])
@login_required
def api_update_settings():
    """更新设置"""
    data = request.json
    updated = []
    errors = []
    scheduler_reload_needed = False

    # 更新登录密码
    if 'login_password' in data:
        new_password = data['login_password'].strip()
        if new_password:
            if len(new_password) < 8:
                errors.append('密码长度至少为 8 位')
            else:
                # 哈希新密码
                hashed_password = hash_password(new_password)
                if set_setting('login_password', hashed_password):
                    updated.append('登录密码')
                else:
                    errors.append('更新登录密码失败')

    # 更新 GPTMail API Key
    if 'gptmail_api_key' in data:
        new_api_key = data['gptmail_api_key'].strip()
        if new_api_key:
            if set_setting('gptmail_api_key', new_api_key):
                updated.append('GPTMail API Key')
            else:
                errors.append('更新 GPTMail API Key 失败')

    # 更新刷新周期
    if 'refresh_interval_days' in data:
        try:
            days = int(data['refresh_interval_days'])
            if days < 1 or days > 90:
                errors.append('刷新周期必须在 1-90 天之间')
            elif set_setting('refresh_interval_days', str(days)):
                updated.append('刷新周期')
            else:
                errors.append('更新刷新周期失败')
        except ValueError:
            errors.append('刷新周期必须是数字')

    # 更新刷新间隔
    if 'refresh_delay_seconds' in data:
        try:
            seconds = int(data['refresh_delay_seconds'])
            if seconds < 0 or seconds > 60:
                errors.append('刷新间隔必须在 0-60 秒之间')
            elif set_setting('refresh_delay_seconds', str(seconds)):
                updated.append('刷新间隔')
            else:
                errors.append('更新刷新间隔失败')
        except ValueError:
            errors.append('刷新间隔必须是数字')

    # 更新 Cron 表达式
    if 'refresh_cron' in data:
        cron_expr = data['refresh_cron'].strip()
        if cron_expr:
            try:
                from croniter import croniter
                from datetime import datetime
                croniter(cron_expr, datetime.now())
                if set_setting('refresh_cron', cron_expr):
                    updated.append('Cron 表达式')
                    scheduler_reload_needed = True
                else:
                    errors.append('更新 Cron 表达式失败')
            except ImportError:
                errors.append('croniter 库未安装')
            except Exception as e:
                errors.append(f'Cron 表达式无效: {str(e)}')

    # 更新刷新策略
    if 'use_cron_schedule' in data:
        use_cron = str(data['use_cron_schedule']).lower()
        if use_cron in ('true', 'false'):
            if set_setting('use_cron_schedule', use_cron):
                updated.append('刷新策略')
                scheduler_reload_needed = True
            else:
                errors.append('更新刷新策略失败')
        else:
            errors.append('刷新策略必须是 true 或 false')

    # 更新定时刷新开关
    if 'enable_scheduled_refresh' in data:
        enable = str(data['enable_scheduled_refresh']).lower()
        if enable in ('true', 'false'):
            if set_setting('enable_scheduled_refresh', enable):
                updated.append('定时刷新开关')
                scheduler_reload_needed = True
            else:
                errors.append('更新定时刷新开关失败')
        else:
            errors.append('定时刷新开关必须是 true 或 false')

    # 更新轮询配置
    if 'enable_auto_polling' in data:
        enable_polling = str(data['enable_auto_polling']).lower()
        if enable_polling in ('true', 'false'):
            if set_setting('enable_auto_polling', enable_polling):
                updated.append('自动轮询开关')
            else:
                errors.append('更新自动轮询开关失败')
        else:
            errors.append('自动轮询开关必须是 true 或 false')

    if 'polling_interval' in data:
        try:
            interval = int(data['polling_interval'])
            if interval < 5 or interval > 300:
                errors.append('轮询间隔必须在 5-300 秒之间')
            elif set_setting('polling_interval', str(interval)):
                updated.append('轮询间隔')
            else:
                errors.append('更新轮询间隔失败')
        except ValueError:
            errors.append('轮询间隔必须是数字')

    if 'polling_count' in data:
        try:
            count = int(data['polling_count'])
            if count < 0 or count > 100:
                errors.append('轮询次数必须在 0-100 次之间（0 表示持续轮询）')
            elif set_setting('polling_count', str(count)):
                updated.append('轮询次数')
            else:
                errors.append('更新轮询次数失败')
        except ValueError:
            errors.append('轮询次数必须是数字')

    if errors:
        return jsonify({'success': False, 'error': '；'.join(errors)})

    if updated:
        scheduler_reloaded = None
        if scheduler_reload_needed:
            try:
                scheduler = init_scheduler()
                if scheduler:
                    configure_scheduler_jobs(scheduler)
                    scheduler_reloaded = True
                else:
                    scheduler_reloaded = False
            except Exception:
                scheduler_reloaded = False

        try:
            details = json.dumps({
                "updated": updated,
                "scheduler_reload_needed": scheduler_reload_needed,
                "scheduler_reloaded": scheduler_reloaded
            }, ensure_ascii=False)
        except Exception:
            details = f"updated={','.join(updated)}"
        log_audit('update', 'settings', None, details)
        return jsonify({
            'success': True,
            'message': f'已更新：{", ".join(updated)}',
            'scheduler_reloaded': scheduler_reloaded
        })
    else:
        return jsonify({'success': False, 'error': '没有需要更新的设置'})


@app.route('/api/scheduler/status', methods=['GET'])
@login_required
def api_get_scheduler_status():
    """获取调度器/定时刷新状态（用于验证“看起来已开启但实际未运行”的问题）"""
    conn = create_sqlite_connection()
    try:
        enable_scheduled = get_setting('enable_scheduled_refresh', 'true').lower() == 'true'
        use_cron = get_setting('use_cron_schedule', 'false').lower() == 'true'
        refresh_interval_days = int(get_setting('refresh_interval_days', '30'))
        refresh_cron = get_setting('refresh_cron', '0 2 * * *')

        # 心跳
        heartbeat_row = conn.execute('''
            SELECT value, updated_at
            FROM settings
            WHERE key = 'scheduler_heartbeat'
        ''').fetchone()

        heartbeat = None
        heartbeat_age_seconds = None
        if heartbeat_row:
            try:
                heartbeat = json.loads(heartbeat_row['value']) if heartbeat_row['value'] else None
            except Exception:
                heartbeat = {"raw": heartbeat_row['value']}
            try:
                hb_time = datetime.fromisoformat(heartbeat_row['updated_at'])
                heartbeat_age_seconds = int((utcnow() - hb_time).total_seconds())
            except Exception:
                heartbeat_age_seconds = None

        # 锁状态
        lock_row = conn.execute('''
            SELECT owner_id, acquired_at, expires_at
            FROM distributed_locks
            WHERE name = ?
        ''', (REFRESH_LOCK_NAME,)).fetchone()
        now_ts = time.time()
        lock_info = None
        if lock_row and lock_row['expires_at'] and lock_row['expires_at'] > now_ts:
            lock_info = {
                "locked": True,
                "owner_id": lock_row['owner_id'],
                "acquired_at": lock_row['acquired_at'],
                "expires_at": lock_row['expires_at']
            }
        else:
            lock_info = {"locked": False}

        # 最近一次定时刷新（含手动触发 scheduled_manual）
        last_scheduled_run = conn.execute('''
            SELECT id, trigger_source, status, started_at, finished_at,
                   total, success_count, failed_count, message, trace_id, requested_by_ip
            FROM refresh_runs
            WHERE trigger_source IN ('scheduled', 'scheduled_manual')
            ORDER BY started_at DESC
            LIMIT 1
        ''').fetchone()

        last_scheduled = dict(last_scheduled_run) if last_scheduled_run else None

        running_run = conn.execute('''
            SELECT id, trigger_source, status, started_at, total, success_count, failed_count, trace_id
            FROM refresh_runs
            WHERE status = 'running'
            ORDER BY started_at DESC
            LIMIT 1
        ''').fetchone()

        running = dict(running_run) if running_run else None

        # 未来触发时间预览
        future_runs = []
        next_due = None
        if enable_scheduled:
            if use_cron:
                try:
                    from croniter import croniter
                    base_time = datetime.now()
                    it = croniter(refresh_cron, base_time)
                    for _ in range(5):
                        future_runs.append(it.get_next(datetime).isoformat())
                except Exception:
                    future_runs = []
            else:
                # 按天数策略：基于最近一次已完成的 scheduled/scheduled_manual 计算 next_due
                row = conn.execute('''
                    SELECT finished_at
                    FROM refresh_runs
                    WHERE trigger_source IN ('scheduled', 'scheduled_manual')
                      AND status IN ('completed', 'failed')
                      AND finished_at IS NOT NULL
                    ORDER BY finished_at DESC
                    LIMIT 1
                ''').fetchone()
                last_finished_at = row['finished_at'] if row else None
                try:
                    last_time = datetime.fromisoformat(last_finished_at) if last_finished_at else None
                except Exception:
                    last_time = None

                base = last_time if last_time else utcnow()
                next_due_dt = base + timedelta(days=refresh_interval_days)
                next_due = next_due_dt.isoformat()
                future_runs.append(next_due_dt.isoformat())

        return jsonify({
            'success': True,
            'scheduler': {
                'autostart': config.get_scheduler_autostart_default(),
                'enabled': enable_scheduled,
                'use_cron': use_cron,
                'refresh_cron': refresh_cron,
                'refresh_interval_days': refresh_interval_days,
                'future_runs': future_runs,
                'next_due': next_due,
                'heartbeat': heartbeat,
                'heartbeat_updated_at': heartbeat_row['updated_at'] if heartbeat_row else None,
                'heartbeat_age_seconds': heartbeat_age_seconds
            },
            'refresh': {
                'lock': lock_info,
                'running': running,
                'last_scheduled': last_scheduled
            }
        })
    finally:
        conn.close()


@app.route('/healthz', methods=['GET'])
def healthz():
    """基础健康检查（用于容器/反代探活）"""
    return jsonify({'status': 'ok'}), 200


@app.route('/api/system/health', methods=['GET'])
@login_required
def api_system_health():
    """管理员健康检查：可服务/可刷新状态概览"""
    conn = create_sqlite_connection()
    try:
        # DB 可用性
        db_ok = True
        try:
            conn.execute("SELECT 1").fetchone()
        except Exception:
            db_ok = False

        # Scheduler 心跳
        heartbeat_row = conn.execute('''
            SELECT updated_at
            FROM settings
            WHERE key = 'scheduler_heartbeat'
        ''').fetchone()

        heartbeat_age_seconds = None
        if heartbeat_row and heartbeat_row['updated_at']:
            try:
                hb_time = datetime.fromisoformat(heartbeat_row['updated_at'])
                heartbeat_age_seconds = int((utcnow() - hb_time).total_seconds())
            except Exception:
                heartbeat_age_seconds = None

        scheduler_enabled = get_setting('enable_scheduled_refresh', 'true').lower() == 'true'
        scheduler_autostart = config.get_scheduler_autostart_default()
        scheduler_healthy = (heartbeat_age_seconds is not None) and (heartbeat_age_seconds <= 120)

        # 刷新锁/运行中
        lock_row = conn.execute('''
            SELECT owner_id, expires_at
            FROM distributed_locks
            WHERE name = ?
        ''', (REFRESH_LOCK_NAME,)).fetchone()
        locked = bool(lock_row and lock_row['expires_at'] and lock_row['expires_at'] > time.time())

        running_run = conn.execute('''
            SELECT id, trigger_source, started_at, trace_id
            FROM refresh_runs
            WHERE status = 'running'
            ORDER BY started_at DESC
            LIMIT 1
        ''').fetchone()

        return jsonify({
            'success': True,
            'health': {
                'service': 'ok',
                'database': 'ok' if db_ok else 'error',
                'scheduler': {
                    'enabled': scheduler_enabled,
                    'autostart': scheduler_autostart,
                    'heartbeat_age_seconds': heartbeat_age_seconds,
                    'healthy': scheduler_healthy if scheduler_enabled else True
                },
                'refresh': {
                    'locked': locked,
                    'running': dict(running_run) if running_run else None
                },
                'server_time_utc': utcnow().isoformat() + 'Z'
            }
        })
    finally:
        conn.close()


@app.route('/api/system/diagnostics', methods=['GET'])
@login_required
def api_system_diagnostics():
    """管理员诊断信息：关键状态一致性/过期清理可见性"""
    conn = create_sqlite_connection()
    try:
        now_ts = time.time()

        export_tokens_count = conn.execute('''
            SELECT COUNT(*) as c
            FROM export_verify_tokens
            WHERE expires_at > ?
        ''', (now_ts,)).fetchone()['c']

        locked_ip_count = conn.execute('''
            SELECT COUNT(*) as c
            FROM login_attempts
            WHERE locked_until_at IS NOT NULL AND locked_until_at > ?
        ''', (now_ts,)).fetchone()['c']

        running_runs = conn.execute('''
            SELECT id, trigger_source, started_at, trace_id
            FROM refresh_runs
            WHERE status = 'running'
            ORDER BY started_at DESC
            LIMIT 5
        ''').fetchall()

        last_runs = conn.execute('''
            SELECT id, trigger_source, status, started_at, finished_at, total, success_count, failed_count, trace_id
            FROM refresh_runs
            ORDER BY started_at DESC
            LIMIT 10
        ''').fetchall()

        locks = conn.execute('''
            SELECT name, owner_id, acquired_at, expires_at
            FROM distributed_locks
            ORDER BY name ASC
        ''').fetchall()

        # 数据库升级状态（可验证）
        schema_version_row = conn.execute(
            "SELECT value, updated_at FROM settings WHERE key = ?",
            (DB_SCHEMA_VERSION_KEY,)
        ).fetchone()
        try:
            schema_version = int(schema_version_row['value']) if schema_version_row else 0
        except Exception:
            schema_version = 0

        last_migration = None
        try:
            mig = conn.execute('''
                SELECT id, from_version, to_version, status, started_at, finished_at, error, trace_id
                FROM schema_migrations
                ORDER BY started_at DESC
                LIMIT 1
            ''').fetchone()
            last_migration = dict(mig) if mig else None
        except Exception:
            last_migration = None

        return jsonify({
            'success': True,
            'diagnostics': {
                'export_verify_tokens_active': export_tokens_count,
                'login_locked_ip_count': locked_ip_count,
                'running_runs': [dict(r) for r in running_runs],
                'last_runs': [dict(r) for r in last_runs],
                'locks': [dict(r) for r in locks],
                'schema': {
                    'version': schema_version,
                    'target_version': DB_SCHEMA_VERSION,
                    'up_to_date': schema_version >= DB_SCHEMA_VERSION,
                    'last_migration': last_migration
                }
            }
        })
    finally:
        conn.close()


@app.route('/api/system/upgrade-status', methods=['GET'])
@login_required
def api_system_upgrade_status():
    """数据库升级状态（用于验收“升级过程可验证/失败可定位”）"""
    conn = create_sqlite_connection()
    try:
        row = conn.execute(
            "SELECT value, updated_at FROM settings WHERE key = ?",
            (DB_SCHEMA_VERSION_KEY,)
        ).fetchone()
        try:
            schema_version = int(row['value']) if row and row['value'] is not None else 0
        except Exception:
            schema_version = 0

        last_trace_row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (DB_SCHEMA_LAST_UPGRADE_TRACE_ID_KEY,)
        ).fetchone()
        last_error_row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (DB_SCHEMA_LAST_UPGRADE_ERROR_KEY,)
        ).fetchone()

        last_migration = None
        try:
            mig = conn.execute('''
                SELECT id, from_version, to_version, status, started_at, finished_at, error, trace_id
                FROM schema_migrations
                ORDER BY started_at DESC
                LIMIT 1
            ''').fetchone()
            last_migration = dict(mig) if mig else None
        except Exception:
            last_migration = None

        backup_hint = {
            "database_path": DATABASE,
            "linux_example": f"cp \"{DATABASE}\" \"{DATABASE}.backup\"",
            "windows_example": f"copy \"{DATABASE}\" \"{DATABASE}.backup\""
        }

        return jsonify({
            "success": True,
            "upgrade": {
                "schema_version": schema_version,
                "target_version": DB_SCHEMA_VERSION,
                "up_to_date": schema_version >= DB_SCHEMA_VERSION,
                "last_upgrade_trace_id": (last_trace_row['value'] if last_trace_row else ""),
                "last_upgrade_error": (last_error_row['value'] if last_error_row else ""),
                "last_migration": last_migration,
                "backup_hint": backup_hint
            }
        })
    finally:
        conn.close()


@app.route('/api/audit-logs', methods=['GET'])
@login_required
def api_get_audit_logs():
    """获取审计日志（敏感操作可追溯）"""
    data = query_audit_logs(
        limit=request.args.get("limit", type=int) or 50,
        offset=request.args.get("offset", type=int) or 0,
        action=request.args.get("action") or "",
        resource_type=request.args.get("resource_type") or "",
    )
    return jsonify({"success": True, **data})


# ==================== 定时任务调度器 ====================

_scheduler_instance = None


def scheduler_heartbeat_task():
    """调度器心跳，用于验证后台任务是否真实运行"""
    try:
        payload = {
            "at": utcnow().isoformat() + "Z",
            "pid": os.getpid()
        }
        conn = create_sqlite_connection()
        try:
            conn.execute('''
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES ('scheduler_heartbeat', ?, CURRENT_TIMESTAMP)
            ''', (json.dumps(payload, ensure_ascii=False),))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def configure_scheduler_jobs(scheduler) -> None:
    """根据当前 settings 重新配置定时刷新 Job（配置变更即时生效）"""
    try:
        from apscheduler.triggers.cron import CronTrigger
    except Exception:
        return

    with app.app_context():
        enable_scheduled = get_setting('enable_scheduled_refresh', 'true').lower() == 'true'
        use_cron = get_setting('use_cron_schedule', 'false').lower() == 'true'
        refresh_interval_days = int(get_setting('refresh_interval_days', '30'))
        cron_expr = get_setting('refresh_cron', '0 2 * * *')

    # 心跳 Job：始终存在（可服务/可刷新可验证）
    try:
        scheduler.remove_job('scheduler_heartbeat')
    except Exception:
        pass
    scheduler.add_job(
        func=scheduler_heartbeat_task,
        trigger='interval',
        seconds=60,
        id='scheduler_heartbeat',
        name='Scheduler Heartbeat',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60
    )

    # 刷新 Job：根据 enable_scheduled 决定是否启用
    try:
        scheduler.remove_job('token_refresh')
    except Exception:
        pass

    if not enable_scheduled:
        print("✓ 定时刷新已禁用（调度器仍运行心跳）")
        return

    if use_cron:
        try:
            from croniter import croniter
            croniter(cron_expr, datetime.now())
            parts = cron_expr.split()
            if len(parts) != 5:
                raise ValueError("Cron 表达式格式错误，应为 5 段")
            minute, hour, day, month, day_of_week = parts
            trigger = CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week)
            scheduler.add_job(
                func=scheduled_refresh_task,
                trigger=trigger,
                id='token_refresh',
                name='Token 定时刷新',
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=600
            )
            print(f"✓ 定时任务已配置：Cron 表达式 '{cron_expr}'")
            return
        except Exception as e:
            print(f"⚠ Cron 配置无效：{str(e)}，回退到默认配置")

    scheduler.add_job(
        func=scheduled_refresh_task,
        trigger=CronTrigger(hour=2, minute=0),
        id='token_refresh',
        name='Token 定时刷新',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=600
    )
    print(f"✓ 定时任务已配置：每天凌晨 2:00 检查刷新（周期：{refresh_interval_days} 天）")


def init_scheduler():
    """初始化定时任务调度器"""
    global _scheduler_instance

    if _scheduler_instance is not None:
        return _scheduler_instance

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        import atexit

        scheduler = BackgroundScheduler()
        configure_scheduler_jobs(scheduler)
        atexit.register(lambda: scheduler.shutdown())

        scheduler.start()
        _scheduler_instance = scheduler
        print("✓ 调度器已启动")
        return scheduler
    except ImportError:
        print("⚠ APScheduler 未安装，定时任务功能不可用")
        print("  安装命令：pip install APScheduler>=3.10.0")
        return None
    except Exception as e:
        print(f"⚠ 定时任务初始化失败：{str(e)}")
        return None


def scheduled_refresh_task():
    """定时刷新任务（由调度器调用）"""
    from datetime import datetime, timedelta

    trace_id = generate_trace_id()
    run_id = None
    lock_owner_id = uuid.uuid4().hex
    lock_acquired = False

    conn = create_sqlite_connection()

    try:
        with app.app_context():
            enable_scheduled = get_setting('enable_scheduled_refresh', 'true').lower() == 'true'
            use_cron = get_setting('use_cron_schedule', 'false').lower() == 'true'
            refresh_interval_days = int(get_setting('refresh_interval_days', '30'))
            delay_seconds = int(get_setting('refresh_delay_seconds', '5'))

        run_id = create_refresh_run(conn, 'scheduled', trace_id, total=0)

        if not enable_scheduled:
            finish_refresh_run(conn, run_id, 'skipped', 0, 0, 0, "定时刷新已禁用")
            return

        # 按天数策略：未到周期则跳过（不产生账号级刷新日志）
        if not use_cron:
            row = conn.execute('''
                SELECT finished_at
                FROM refresh_runs
                WHERE trigger_source = 'scheduled'
                  AND status IN ('completed', 'failed')
                  AND finished_at IS NOT NULL
                ORDER BY finished_at DESC
                LIMIT 1
            ''').fetchone()

            if row and row['finished_at']:
                try:
                    last_time = datetime.fromisoformat(row['finished_at'])
                except Exception:
                    last_time = None

                if last_time:
                    next_due = last_time + timedelta(days=refresh_interval_days)
                    if utcnow() < next_due:
                        finish_refresh_run(
                            conn,
                            run_id,
                            'skipped',
                            0,
                            0,
                            0,
                            f"距离上次刷新未满 {refresh_interval_days} 天，下次最早：{next_due.strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        return

        # 清理过期/历史状态
        try:
            conn.execute("DELETE FROM account_refresh_logs WHERE created_at < datetime('now', '-6 months')")
            conn.execute("DELETE FROM refresh_runs WHERE started_at < datetime('now', '-6 months')")
            conn.execute("DELETE FROM export_verify_tokens WHERE expires_at < ?", (time.time(),))
            conn.execute("DELETE FROM distributed_locks WHERE expires_at < ?", (time.time(),))
            conn.commit()
        except Exception:
            pass

        accounts = conn.execute('''
            SELECT id, email, client_id, refresh_token, group_id
            FROM accounts
            WHERE status = 'active'
        ''').fetchall()

        total = len(accounts)
        conn.execute('UPDATE refresh_runs SET total = ? WHERE id = ?', (total, run_id))
        conn.commit()

        ttl_seconds = compute_refresh_lock_ttl_seconds(total, delay_seconds)
        ok, _info = acquire_distributed_lock(conn, REFRESH_LOCK_NAME, lock_owner_id, ttl_seconds)
        if not ok:
            finish_refresh_run(conn, run_id, 'skipped', total, 0, 0, "刷新任务冲突：已有刷新在执行")
            return
        lock_acquired = True

        print(f"[定时任务] 开始执行 Token 刷新... trace_id={trace_id} run_id={run_id}")
        result = trigger_refresh_internal(conn, accounts, refresh_type='scheduled', run_id=run_id, delay_seconds=delay_seconds)
        finish_refresh_run(
            conn,
            run_id,
            'completed',
            total,
            result['success_count'],
            result['failed_count'],
            f"完成：成功 {result['success_count']}，失败 {result['failed_count']}"
        )
        print(f"[定时任务] Token 刷新完成 trace_id={trace_id} run_id={run_id}")

    except Exception as e:
        try:
            if run_id:
                finish_refresh_run(conn, run_id, 'failed', 0, 0, 0, str(e))
        except Exception:
            pass
        try:
            app.logger.exception("Scheduled refresh task failed trace_id=%s", trace_id)
        except Exception:
            pass
    finally:
        if lock_acquired:
            release_distributed_lock(conn, REFRESH_LOCK_NAME, lock_owner_id)
        conn.close()


def trigger_refresh_internal(
    conn: sqlite3.Connection,
    accounts: List[sqlite3.Row],
    refresh_type: str,
    run_id: str,
    delay_seconds: int,
) -> Dict[str, Any]:
    """内部触发刷新（不通过 HTTP），返回统计"""
    total = len(accounts)
    success_count = 0
    failed_count = 0

    for index, account in enumerate(accounts, 1):
        account_id = account['id']
        account_email = account['email']
        client_id = account['client_id']
        encrypted_refresh_token = account['refresh_token']

        # 解密 refresh_token
        try:
            refresh_token = decrypt_data(encrypted_refresh_token) if encrypted_refresh_token else encrypted_refresh_token
        except Exception as e:
            failed_count += 1
            error_msg = f"解密 token 失败: {str(e)}"
            try:
                conn.execute('''
                    INSERT INTO account_refresh_logs (account_id, account_email, refresh_type, status, error_message, run_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (account_id, account_email, refresh_type, 'failed', error_msg, run_id))
                conn.commit()
            except Exception:
                pass
            continue

        # 获取分组代理设置
        proxy_url = ''
        group_id = account['group_id']
        if group_id:
            try:
                group_row = conn.execute('SELECT proxy_url FROM groups WHERE id = ?', (group_id,)).fetchone()
                if group_row:
                    proxy_url = group_row['proxy_url'] or ''
            except Exception:
                proxy_url = ''

        success, error_msg = test_refresh_token(client_id, refresh_token, proxy_url)

        try:
            conn.execute('''
                INSERT INTO account_refresh_logs (account_id, account_email, refresh_type, status, error_message, run_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (account_id, account_email, refresh_type, 'success' if success else 'failed', error_msg, run_id))

            if success:
                conn.execute('''
                    UPDATE accounts
                    SET last_refresh_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (account_id,))

            conn.commit()
        except Exception:
            pass

        if success:
            success_count += 1
        else:
            failed_count += 1

        if index < total and delay_seconds > 0:
            time.sleep(delay_seconds)

    return {
        "total": total,
        "success_count": success_count,
        "failed_count": failed_count
    }


def should_autostart_scheduler() -> bool:
    """在 WSGI/Gunicorn 场景下自动启动调度器；避免 Flask CLI/重载器导致重复启动"""
    autostart = config.get_scheduler_autostart_default()
    if not autostart:
        return False

    # Flask CLI (flask run) + reloader：父进程不启动
    if config.env_true('FLASK_RUN_FROM_CLI', False) and not config.env_true('WERKZEUG_RUN_MAIN', False):
        return False

    return True


# 注意：调度器启动由 outlook_web.app:create_app() / __main__ 入口控制（避免 import-time 副作用）


# ==================== 错误处理 ====================

@app.errorhandler(HTTPException)
def handle_http_exception(error: HTTPException):
    """处理可预期的 HTTP 异常，返回统一错误结构（仅对 API/JSON 请求返回 JSON）"""
    status_code = error.code or 500

    message_map = {
        400: "请求参数错误",
        401: "未授权",
        403: "无权限",
        404: "资源不存在",
        405: "请求方法不被允许",
        429: "请求过于频繁，请稍后再试",
    }
    message = message_map.get(status_code, "请求失败")

    trace_id_value = None
    try:
        trace_id_value = getattr(g, 'trace_id', None)
    except Exception:
        trace_id_value = None

    error_payload = build_error_payload(
        code="HTTP_ERROR",
        message=message,
        err_type="HttpError",
        status=status_code,
        details=str(error),
        trace_id=trace_id_value
    )

    if request.path.startswith('/api/') or request.is_json:
        return jsonify({'success': False, 'error': error_payload}), status_code

    return f"{message} (trace_id={error_payload.get('trace_id')})", status_code


@app.errorhandler(Exception)
def handle_exception(error):
    """处理未捕获的异常"""
    trace_id_value = None
    try:
        trace_id_value = getattr(g, 'trace_id', None)
    except Exception:
        trace_id_value = None

    try:
        app.logger.exception("Unhandled exception trace_id=%s", trace_id_value or "unknown")
    except Exception:
        pass

    error_payload = build_error_payload(
        code="INTERNAL_ERROR",
        message="服务器内部错误",
        err_type="UnhandledException",
        status=500,
        details=str(error),
        trace_id=trace_id_value
    )

    if request.path.startswith('/api/') or request.is_json:
        return jsonify({'success': False, 'error': error_payload}), 500

    return f"服务器内部错误 (trace_id={error_payload.get('trace_id')})", 500


# ==================== 主程序 ====================

if __name__ == '__main__':
    # 从环境变量获取配置
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('HOST', '0.0.0.0')
    debug = os.getenv('FLASK_ENV', 'production') != 'production'

    print("=" * 60)
    print("Outlook 邮件 Web 应用")
    print("=" * 60)
    print(f"访问地址: http://{host}:{port}")
    print(f"运行模式: {'开发' if debug else '生产'}")
    print("=" * 60)

    # 初始化定时任务
    if not debug or os.getenv('WERKZEUG_RUN_MAIN') == 'true':
        init_scheduler()
    else:
        print("✓ 调试重载器父进程：跳过启动调度器")

    app.run(debug=debug, host=host, port=port)
