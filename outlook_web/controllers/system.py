from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from flask import jsonify, request

from outlook_web import __version__ as APP_VERSION
from outlook_web import config

# ==================== 版本检测缓存（模块级，重启后清空） ====================
_version_cache: dict | None = None
_version_cache_at: float = 0.0
_VERSION_CACHE_TTL = 600  # 10 分钟
from outlook_web.db import (
    DB_SCHEMA_LAST_UPGRADE_ERROR_KEY,
    DB_SCHEMA_LAST_UPGRADE_TRACE_ID_KEY,
    DB_SCHEMA_VERSION,
    DB_SCHEMA_VERSION_KEY,
    create_sqlite_connection,
)
from outlook_web.repositories import accounts as accounts_repo
from outlook_web.repositories import settings as settings_repo
from outlook_web.security.auth import api_key_required, login_required
from outlook_web.security.external_api_guard import external_api_guards
from outlook_web.services import external_api as external_api_service
from outlook_web.services.scheduler import REFRESH_LOCK_NAME


def utcnow() -> datetime:
    """返回 naive UTC 时间（等价于旧的 datetime.utcnow()）"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ==================== 系统 API ====================


def healthz() -> Any:
    """基础健康检查（用于容器/反代探活）"""
    return jsonify({"status": "ok"}), 200


@login_required
def api_system_health() -> Any:
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
        heartbeat_row = conn.execute("""
            SELECT updated_at
            FROM settings
            WHERE key = 'scheduler_heartbeat'
        """).fetchone()

        heartbeat_age_seconds = None
        if heartbeat_row and heartbeat_row["updated_at"]:
            try:
                hb_time = datetime.fromisoformat(heartbeat_row["updated_at"])
                heartbeat_age_seconds = int((utcnow() - hb_time).total_seconds())
            except Exception:
                heartbeat_age_seconds = None

        scheduler_enabled = (
            settings_repo.get_setting("enable_scheduled_refresh", "true").lower()
            == "true"
        )
        scheduler_autostart = config.get_scheduler_autostart_default()
        scheduler_healthy = (heartbeat_age_seconds is not None) and (
            heartbeat_age_seconds <= 120
        )

        # 刷新锁/运行中
        lock_row = conn.execute(
            """
            SELECT owner_id, expires_at
            FROM distributed_locks
            WHERE name = ?
        """,
            (REFRESH_LOCK_NAME,),
        ).fetchone()
        locked = bool(
            lock_row and lock_row["expires_at"] and lock_row["expires_at"] > time.time()
        )

        running_run = conn.execute("""
            SELECT id, trigger_source, started_at, trace_id
            FROM refresh_runs
            WHERE status = 'running'
            ORDER BY started_at DESC
            LIMIT 1
        """).fetchone()

        return jsonify(
            {
                "success": True,
                "health": {
                    "service": "ok",
                    "database": "ok" if db_ok else "error",
                    "scheduler": {
                        "enabled": scheduler_enabled,
                        "autostart": scheduler_autostart,
                        "heartbeat_age_seconds": heartbeat_age_seconds,
                        "healthy": scheduler_healthy if scheduler_enabled else True,
                    },
                    "refresh": {
                        "locked": locked,
                        "running": dict(running_run) if running_run else None,
                    },
                    "server_time_utc": utcnow().isoformat() + "Z",
                },
            }
        )
    finally:
        conn.close()


@login_required
def api_system_diagnostics() -> Any:
    """管理员诊断信息：关键状态一致性/过期清理可见性"""
    conn = create_sqlite_connection()
    try:
        now_ts = time.time()

        export_tokens_count = conn.execute(
            """
            SELECT COUNT(*) as c
            FROM export_verify_tokens
            WHERE expires_at > ?
        """,
            (now_ts,),
        ).fetchone()["c"]

        locked_ip_count = conn.execute(
            """
            SELECT COUNT(*) as c
            FROM login_attempts
            WHERE locked_until_at IS NOT NULL AND locked_until_at > ?
        """,
            (now_ts,),
        ).fetchone()["c"]

        running_runs = conn.execute("""
            SELECT id, trigger_source, started_at, trace_id
            FROM refresh_runs
            WHERE status = 'running'
            ORDER BY started_at DESC
            LIMIT 5
        """).fetchall()

        last_runs = conn.execute("""
            SELECT id, trigger_source, status, started_at, finished_at, total, success_count, failed_count, trace_id
            FROM refresh_runs
            ORDER BY started_at DESC
            LIMIT 10
        """).fetchall()

        locks = conn.execute("""
            SELECT name, owner_id, acquired_at, expires_at
            FROM distributed_locks
            ORDER BY name ASC
        """).fetchall()

        # 数据库升级状态（可验证）
        schema_version_row = conn.execute(
            "SELECT value, updated_at FROM settings WHERE key = ?",
            (DB_SCHEMA_VERSION_KEY,),
        ).fetchone()
        schema_version = int(schema_version_row["value"]) if schema_version_row else 0

        last_migration = None
        try:
            mig = conn.execute("""
                SELECT id, from_version, to_version, status, started_at, finished_at, error, trace_id
                FROM schema_migrations
                ORDER BY started_at DESC
                LIMIT 1
            """).fetchone()
            last_migration = dict(mig) if mig else None
        except Exception:
            last_migration = None

        return jsonify(
            {
                "success": True,
                "diagnostics": {
                    "export_verify_tokens_active": export_tokens_count,
                    "login_locked_ip_count": locked_ip_count,
                    "running_runs": [dict(r) for r in running_runs],
                    "last_runs": [dict(r) for r in last_runs],
                    "locks": [dict(r) for r in locks],
                    "schema": {
                        "version": schema_version,
                        "target_version": DB_SCHEMA_VERSION,
                        "up_to_date": schema_version >= DB_SCHEMA_VERSION,
                        "last_migration": last_migration,
                    },
                },
            }
        )
    finally:
        conn.close()


@login_required
def api_system_upgrade_status() -> Any:
    """数据库升级状态（用于验收"升级过程可验证/失败可定位"）"""
    from outlook_web import config as app_config

    conn = create_sqlite_connection()
    try:
        row = conn.execute(
            "SELECT value, updated_at FROM settings WHERE key = ?",
            (DB_SCHEMA_VERSION_KEY,),
        ).fetchone()
        schema_version = int(row["value"]) if row and row["value"] is not None else 0

        last_trace_row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (DB_SCHEMA_LAST_UPGRADE_TRACE_ID_KEY,),
        ).fetchone()
        last_error_row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (DB_SCHEMA_LAST_UPGRADE_ERROR_KEY,),
        ).fetchone()

        last_migration = None
        try:
            mig = conn.execute("""
                SELECT id, from_version, to_version, status, started_at, finished_at, error, trace_id
                FROM schema_migrations
                ORDER BY started_at DESC
                LIMIT 1
            """).fetchone()
            last_migration = dict(mig) if mig else None
        except Exception:
            last_migration = None

        database_path = app_config.get_database_path()
        backup_hint = {
            "database_path": database_path,
            "linux_example": f'cp "{database_path}" "{database_path}.backup"',
            "windows_example": f'copy "{database_path}" "{database_path}.backup"',
        }

        return jsonify(
            {
                "success": True,
                "upgrade": {
                    "schema_version": schema_version,
                    "target_version": DB_SCHEMA_VERSION,
                    "up_to_date": schema_version >= DB_SCHEMA_VERSION,
                    "last_upgrade_trace_id": (
                        last_trace_row["value"] if last_trace_row else ""
                    ),
                    "last_upgrade_error": (
                        last_error_row["value"] if last_error_row else ""
                    ),
                    "last_migration": last_migration,
                    "backup_hint": backup_hint,
                },
            }
        )
    finally:
        conn.close()


# ==================== External System API ====================


@api_key_required
@external_api_guards()
def api_external_health() -> Any:
    """对外健康检查（不依赖登录态）"""
    conn = create_sqlite_connection()
    try:
        db_ok = True
        try:
            conn.execute("SELECT 1").fetchone()
        except Exception:
            db_ok = False

        probe_summary: dict[str, Any] = {
            "upstream_probe_ok": None,
            "last_probe_at": "",
            "last_probe_error": "",
        }
        if db_ok:
            try:
                probe_summary = external_api_service.probe_instance_upstream(
                    cache_ttl_seconds=60
                )
            except Exception:
                probe_summary = {
                    "upstream_probe_ok": False,
                    "last_probe_at": utcnow().isoformat() + "Z",
                    "last_probe_error": "实例上游探测执行失败",
                }

        data = {
            "status": "ok",
            "service": "outlook-email-plus",
            "version": APP_VERSION,
            "server_time_utc": utcnow().isoformat() + "Z",
            "database": "ok" if db_ok else "error",
            "upstream_probe_ok": probe_summary.get("upstream_probe_ok"),
            "last_probe_at": probe_summary.get("last_probe_at") or "",
            "last_probe_error": probe_summary.get("last_probe_error") or "",
        }
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr="",
            endpoint="/api/external/health",
            status="ok",
            details={
                "database": data["database"],
                "upstream_probe_ok": data["upstream_probe_ok"],
            },
        )
        return jsonify(external_api_service.ok(data))
    except Exception as exc:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr="",
            endpoint="/api/external/health",
            status="error",
            details={"code": "INTERNAL_ERROR", "err": type(exc).__name__},
        )
        return jsonify(external_api_service.fail("INTERNAL_ERROR", "服务内部错误")), 500
    finally:
        conn.close()


# ==================== 版本更新检测 ====================


def _version_gt(a: str, b: str) -> bool:
    """判断版本 a 是否严格大于版本 b（仅支持语义化版本 x.y.z）"""
    try:
        return tuple(int(x) for x in a.split(".")) > tuple(int(x) for x in b.split("."))
    except Exception:
        return False


@login_required
def api_version_check() -> Any:
    """检查是否有新版本可用（内存缓存，10 分钟 TTL）"""
    import json as _json
    import urllib.request

    global _version_cache, _version_cache_at

    now = time.time()
    if _version_cache is not None and (now - _version_cache_at) < _VERSION_CACHE_TTL:
        return jsonify(_version_cache)

    current = APP_VERSION

    try:
        GITHUB_API = (
            "https://api.github.com/repos/hshaokang/outlookemail-plus/releases/latest"
        )
        req = urllib.request.Request(
            GITHUB_API,
            headers={"User-Agent": "outlook-email-plus"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = _json.loads(resp.read())
        latest = data.get("tag_name", "").lstrip("v")
        release_url = data.get("html_url", "")
        has_update = _version_gt(latest, current)
        result = {
            "success": True,
            "has_update": has_update,
            "current_version": current,
            "latest_version": latest,
            "release_url": release_url,
        }
    except Exception:
        # GitHub API 调用失败：静默降级，返回无更新
        result = {
            "success": True,
            "has_update": False,
            "current_version": current,
            "latest_version": current,
            "release_url": "",
        }

    _version_cache = result
    _version_cache_at = now
    return jsonify(result)


@login_required
def api_trigger_update() -> Any:
    """触发 Watchtower 一键更新（调用 Watchtower HTTP API）"""
    import os
    import urllib.error
    import urllib.request

    watchtower_url = os.getenv("WATCHTOWER_API_URL", "http://watchtower:8080")
    watchtower_token = os.getenv("WATCHTOWER_HTTP_API_TOKEN", "")

    if not watchtower_token:
        return jsonify(
            {"success": False, "message": "WATCHTOWER_HTTP_API_TOKEN 未配置"}
        ), 500

    try:
        req = urllib.request.Request(
            f"{watchtower_url}/v1/update",
            method="POST",
            headers={
                "Authorization": f"Bearer {watchtower_token}",
                "Content-Length": "0",
            },
            data=b"",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
        if status == 200:
            return jsonify({"success": True, "message": "更新触发成功，容器即将重启"})
        else:
            return jsonify(
                {"success": False, "message": f"Watchtower 返回状态码 {status}"}
            ), 502
    except urllib.error.URLError as e:
        return jsonify(
            {"success": False, "message": f"无法连接 Watchtower: {e.reason}"}
        ), 503
    except Exception as e:
        return jsonify({"success": False, "message": f"触发更新失败: {str(e)}"}), 500


@api_key_required
@external_api_guards()
def api_external_capabilities() -> Any:
    """对外能力说明接口"""
    public_mode = settings_repo.get_external_api_public_mode()
    restricted = []
    all_features = [
        "message_list",
        "message_detail",
        "raw_content",
        "verification_code",
        "verification_link",
        "wait_message",
    ]
    if public_mode:
        if settings_repo.get_external_api_disable_raw_content():
            restricted.append("raw_content")
        if settings_repo.get_external_api_disable_wait_message():
            restricted.append("wait_message")
    available = [f for f in all_features if f not in restricted]
    data = {
        "service": "outlook-email-plus",
        "version": APP_VERSION,
        "public_mode": public_mode,
        "features": available,
        "restricted_features": restricted,
    }
    external_api_service.audit_external_api_access(
        action="external_api_access",
        email_addr="",
        endpoint="/api/external/capabilities",
        status="ok",
        details={"feature_count": len(data["features"])},
    )
    return jsonify(external_api_service.ok(data))


@api_key_required
@external_api_guards()
def api_external_account_status() -> Any:
    """对外账号状态检查"""
    email_addr = (request.args.get("email") or "").strip()
    if not email_addr or "@" not in email_addr:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=email_addr,
            endpoint="/api/external/account-status",
            status="error",
            details={"code": "INVALID_PARAM"},
        )
        return jsonify(
            external_api_service.fail("INVALID_PARAM", "email 参数不合法")
        ), 400
    try:
        external_api_service.ensure_external_email_scope(email_addr)
    except external_api_service.ExternalApiError as exc:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=email_addr,
            endpoint="/api/external/account-status",
            status="error",
            details={"code": exc.code},
        )
        return jsonify(
            external_api_service.fail(exc.code, exc.message, data=exc.data)
        ), exc.status

    account = accounts_repo.get_account_by_email(email_addr)
    if not account:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=email_addr,
            endpoint="/api/external/account-status",
            status="error",
            details={"code": "ACCOUNT_NOT_FOUND"},
        )
        return jsonify(
            external_api_service.fail(
                "ACCOUNT_NOT_FOUND", "账号不存在", data={"email": email_addr}
            )
        ), 404

    account_type = (account.get("account_type") or "outlook").strip().lower()
    provider = (account.get("provider") or account_type or "outlook").strip().lower()
    preferred_method = "imap_generic" if account_type == "imap" else "graph"
    can_read = external_api_service.can_account_read(account)

    data = {
        "email": email_addr,
        "exists": True,
        "account_type": account_type,
        "provider": provider,
        "email_domain": account.get("email_domain") or "",
        "group_id": account.get("group_id"),
        "status": account.get("status"),
        "last_refresh_at": account.get("last_refresh_at"),
        "preferred_method": preferred_method,
        "can_read": can_read,
        "upstream_probe_ok": None,
        "probe_method": "",
        "last_probe_at": "",
        "last_probe_error": "",
    }
    if can_read:
        probe_summary = external_api_service.probe_account_upstream(account)
        data["upstream_probe_ok"] = probe_summary.get("upstream_probe_ok")
        data["probe_method"] = probe_summary.get("probe_method") or preferred_method
        data["last_probe_at"] = probe_summary.get("last_probe_at") or ""
        data["last_probe_error"] = probe_summary.get("last_probe_error") or ""
    external_api_service.audit_external_api_access(
        action="external_api_access",
        email_addr=email_addr,
        endpoint="/api/external/account-status",
        status="ok",
        details={
            "preferred_method": preferred_method,
            "can_read": can_read,
            "upstream_probe_ok": data["upstream_probe_ok"],
        },
    )
    return jsonify(external_api_service.ok(data))
