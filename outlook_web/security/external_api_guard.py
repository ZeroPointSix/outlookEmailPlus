"""
P1 对外 API 安全守卫 — 公网模式控制层

职责：IP 白名单校验、高风险接口禁用、基础限流。
位于 api_key_required 之后、controller 逻辑之前。

错误码：
  - IP_NOT_ALLOWED (403)
  - FEATURE_DISABLED (403)
  - RATE_LIMIT_EXCEEDED (429)
"""

from __future__ import annotations

import ipaddress
import time
from functools import wraps
from typing import Any, Callable, Optional

from flask import jsonify

from outlook_web.db import get_db
from outlook_web.repositories import settings as settings_repo
from outlook_web.security.auth import get_client_ip as get_trusted_client_ip
from outlook_web.services import external_api as external_api_service

# ── IP 白名单 ────────────────────────────────────────


def _get_client_ip() -> str:
    """获取客户端真实 IP。

    安全策略：仅当请求来自受信任代理（TRUSTED_PROXIES）时才信任 X-Forwarded-For，
    否则使用 remote_addr，避免客户端伪造 XFF 绕过白名单/限流。

    该逻辑与登录/其它鉴权场景保持一致（见 outlook_web.security.auth.get_client_ip）。
    """

    # Keep return value stable for downstream code (never None).
    return get_trusted_client_ip() or "unknown"


def _ip_in_whitelist(ip: str, whitelist: list) -> bool:
    """检查 IP 是否在白名单内（支持 CIDR 和精确匹配）。"""
    if not whitelist:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in whitelist:
        try:
            if "/" in str(entry):
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            else:
                if addr == ipaddress.ip_address(entry):
                    return True
        except (ValueError, TypeError):
            continue
    return False


def check_ip_whitelist() -> Optional[Any]:
    """
    检查 IP 白名单。仅在公网模式开启且白名单非空时生效。
    返回 None 表示通过，返回 Response 表示拒绝。
    """
    if not settings_repo.get_external_api_public_mode():
        return None
    whitelist = settings_repo.get_external_api_ip_whitelist()
    if not whitelist:
        return None
    client_ip = _get_client_ip()
    if _ip_in_whitelist(client_ip, whitelist):
        return None
    return (
        jsonify(
            external_api_service.fail(
                code="IP_NOT_ALLOWED",
                message="当前 IP 不在白名单中",
                data={"ip": client_ip},
            )
        ),
        403,
    )


# ── 高风险接口禁用 ────────────────────────────────────


def check_feature_enabled(feature: str) -> Optional[Any]:
    """
    检查功能是否被禁用。仅在公网模式开启时生效。
    feature: 'wait_message' | 'raw_content'
    返回 None 表示通过，返回 Response 表示拒绝。
    """
    if not settings_repo.get_external_api_public_mode():
        return None
    disabled = False
    if feature == "wait_message":
        disabled = settings_repo.get_external_api_disable_wait_message()
    elif feature == "raw_content":
        disabled = settings_repo.get_external_api_disable_raw_content()
    if not disabled:
        return None
    return (
        jsonify(
            external_api_service.fail(
                code="FEATURE_DISABLED",
                message=f"功能 {feature} 在公网模式下已禁用",
                data={"feature": feature},
            )
        ),
        403,
    )


# ── 基础限流（滑动窗口，按 IP + 分钟桶） ─────────────


def _current_minute_bucket() -> int:
    return int(time.time()) // 60


def _cleanup_old_buckets(db: Any) -> None:
    """清理 5 分钟前的限流记录。"""
    cutoff = _current_minute_bucket() - 5
    try:
        db.execute(
            "DELETE FROM external_api_rate_limits WHERE minute_bucket < ?",
            (cutoff,),
        )
    except Exception:
        pass


def check_rate_limit() -> Optional[Any]:
    """
    检查限流。仅在公网模式开启时生效。
    返回 None 表示通过，返回 Response 表示拒绝。
    """
    if not settings_repo.get_external_api_public_mode():
        return None
    limit = settings_repo.get_external_api_rate_limit()
    client_ip = _get_client_ip()
    bucket = _current_minute_bucket()
    try:
        db = get_db()
        _cleanup_old_buckets(db)
        # 原子递增
        db.execute(
            """
            INSERT INTO external_api_rate_limits (ip_address, minute_bucket, request_count)
            VALUES (?, ?, 1)
            ON CONFLICT(ip_address, minute_bucket)
            DO UPDATE SET request_count = request_count + 1
            """,
            (client_ip, bucket),
        )
        db.commit()
        row = db.execute(
            "SELECT request_count FROM external_api_rate_limits WHERE ip_address = ? AND minute_bucket = ?",
            (client_ip, bucket),
        ).fetchone()
        count = row["request_count"] if row else 0
    except Exception:
        return None

    if count > limit:
        return (
            jsonify(
                external_api_service.fail(
                    code="RATE_LIMIT_EXCEEDED",
                    message=f"请求频率超限（{limit} 次/分钟）",
                    data={"limit": limit, "current": count, "ip": client_ip},
                )
            ),
            429,
        )
    return None


# ── 组合守卫装饰器 ────────────────────────────────────


def external_api_guards(feature: Optional[str] = None) -> Callable:
    """
    组合守卫装饰器：IP 白名单 → 限流 → 功能禁用检查。
    放在 @api_key_required 之后。

    用法：
        @api_key_required
        @external_api_guards(feature="raw_content")
        def api_external_raw(message_id):
            ...
    """

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args: Any, **kwargs: Any) -> Any:
            # 1. IP 白名单
            resp = check_ip_whitelist()
            if resp is not None:
                return resp
            # 2. 限流
            resp = check_rate_limit()
            if resp is not None:
                return resp
            # 3. 功能禁用
            if feature:
                resp = check_feature_enabled(feature)
                if resp is not None:
                    return resp
            return f(*args, **kwargs)

        return decorated

    return decorator
