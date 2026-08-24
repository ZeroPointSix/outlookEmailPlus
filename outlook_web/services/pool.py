"""
邮箱池服务层（PRD-00009 MT-1）

职责：
- 输入校验（caller_id / task_id / lease_seconds / result / detail 长度）
- 读取 settings（在 Flask app_context 下用 get_db，或直接接受 conn）
- 调用 repositories/pool.py 的原子操作
- 将 repository 层的异常转换为业务错误码
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from outlook_web.db import create_sqlite_connection
from outlook_web.repositories import pool as pool_repo

logger = logging.getLogger(__name__)

CALLER_ID_MAX_LEN = 64
TASK_ID_MAX_LEN = 128
PROJECT_KEY_MAX_LEN = 128
EMAIL_DOMAIN_MAX_LEN = 128
REASON_MAX_LEN = 256
DETAIL_MAX_LEN = 512

VALID_RESULTS = set(pool_repo.RESULT_TO_POOL_STATUS.keys())

# CF 邮箱 complete 时需要删除远程邮箱的 result 值
CF_DELETE_ON_RESULTS = {"success", "credential_invalid"}

# 内置账号 Provider 与临时邮箱兼容别名。第三方 Provider 从运行时注册表读取。
VALID_PROVIDERS = {
    "cloudflare_temp_mail",
    "custom",
    "gptmail",
    "imap",
    "outlook",
}

_TEMP_PROVIDER_ALIASES = {
    "custom": "custom_domain_temp_mail",
    "gptmail": "legacy_bridge",
}


def _registered_temp_provider_names() -> set[str]:
    """返回当前已注册的临时邮箱 Provider 名称。"""
    try:
        from outlook_web.services.temp_mail_provider_factory import get_available_providers

        return {
            str(item.get("name") or "").strip().lower()
            for item in get_available_providers()
            if str(item.get("name") or "").strip()
        }
    except Exception:
        return set()


def _resolve_temp_provider_name(provider: Optional[str]) -> Optional[str]:
    """把兼容别名解析为注册表中的 Provider 名称。"""
    if provider is None:
        return None
    normalized = str(provider or "").strip().lower()
    resolved = _TEMP_PROVIDER_ALIASES.get(normalized, normalized)
    return resolved if resolved in _registered_temp_provider_names() else None


def _validate_provider(provider: Optional[str]) -> Optional[str]:
    """
    校验 provider 参数。

    - 空字符串视为 None
    - 非空时校验是否为内置 Provider、兼容别名或已注册插件
    - 返回规范化后的 provider（None 或有效值）
    """
    if provider is None:
        return None
    p = provider.strip().lower()
    if not p:
        return None
    valid_providers = VALID_PROVIDERS | _registered_temp_provider_names()
    if p not in valid_providers:
        raise PoolServiceError(
            f"provider 必须是 {sorted(valid_providers)} 之一，或留空",
            "invalid_provider",
        )
    return p


class PoolServiceError(Exception):
    """业务错误，包含 HTTP 状态码和错误码。"""

    def __init__(self, message: str, error_code: str, http_status: int = 400):
        super().__init__(message)
        self.error_code = error_code
        self.http_status = http_status


def _validate_caller_id(caller_id: str) -> None:
    if not caller_id or not caller_id.strip():
        raise PoolServiceError("caller_id 不能为空", "caller_id_empty")
    if len(caller_id) > CALLER_ID_MAX_LEN:
        raise PoolServiceError(f"caller_id 超过最大长度 {CALLER_ID_MAX_LEN}", "caller_id_too_long")


def _validate_task_id(task_id: str) -> None:
    if not task_id or not task_id.strip():
        raise PoolServiceError("task_id 不能为空", "task_id_empty")
    if len(task_id) > TASK_ID_MAX_LEN:
        raise PoolServiceError(f"task_id 超过最大长度 {TASK_ID_MAX_LEN}", "task_id_too_long")


def _validate_lease_seconds(lease_seconds: int, max_lease: int = 3600) -> None:
    if lease_seconds <= 0:
        raise PoolServiceError("lease_seconds 必须大于 0", "lease_seconds_invalid")
    if lease_seconds > max_lease:
        raise PoolServiceError(f"lease_seconds 不能超过 {max_lease} 秒", "lease_seconds_too_large")


def _validate_project_key(project_key: Optional[str]) -> Optional[str]:
    if project_key is None:
        return None
    pk = project_key.strip()
    if not pk:
        return None
    if len(pk) > PROJECT_KEY_MAX_LEN:
        raise PoolServiceError(f"project_key 超过最大长度 {PROJECT_KEY_MAX_LEN}", "project_key_too_long")
    return pk


def _validate_email_domain(email_domain: Optional[str]) -> Optional[str]:
    if email_domain is None:
        return None
    d = email_domain.strip().lower()
    if not d:
        return None
    if len(d) > EMAIL_DOMAIN_MAX_LEN:
        raise PoolServiceError(f"email_domain 超过最大长度 {EMAIL_DOMAIN_MAX_LEN}", "email_domain_too_long")
    return d


def _read_settings_via_conn(conn) -> dict:
    """在独立连接场景下直接从 settings 表读取池相关配置。"""
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


def _is_project_reuse_eligible_account(
    *,
    provider: Optional[str],
    account_type: Optional[str],
    claimed_project_key: Optional[str],
) -> bool:
    """判定账号是否适用项目维度成功复用路径 (FD §2.1)。

    三重门控缺一不可：
    1. claimed_project_key 非空 — 必须在 claim 时显式传入
    2. 非 cloudflare_temp_mail — CF 临时邮箱不在本期覆盖范围
    3. 非 temp_mail — 一次性临时邮箱不在本期覆盖范围
    """
    if not claimed_project_key:
        return False
    if (provider or "").strip() == "cloudflare_temp_mail":
        return False
    if (account_type or "").strip() == "temp_mail":
        return False
    return True


def claim_random(
    *,
    caller_id: str,
    task_id: str,
    provider: Optional[str] = None,
    project_key: Optional[str] = None,
    email_domain: Optional[str] = None,
) -> dict:
    _validate_caller_id(caller_id)
    _validate_task_id(task_id)
    provider = _validate_provider(provider)
    temp_provider_name = _resolve_temp_provider_name(provider)
    project_key = _validate_project_key(project_key)
    email_domain = _validate_email_domain(email_domain)

    conn = create_sqlite_connection()
    try:
        settings = _read_settings_via_conn(conn)
        default_lease = settings["pool_default_lease_seconds"]
        _validate_lease_seconds(default_lease)

        try:
            account = pool_repo.claim_atomic(
                conn,
                caller_id=caller_id,
                task_id=task_id,
                lease_seconds=default_lease,
                provider=provider,
                project_key=project_key,
                email_domain=email_domain,
            )
        except pool_repo.PoolRepositoryError as e:
            # 将 Repository 层异常转换为 Service 层异常
            raise PoolServiceError(str(e), e.error_code, http_status=500) from e

        if account is not None:
            return account

        # accounts 池无命中：未指定 Provider 或已注册临时邮箱 Provider 时回退到 temp_emails。
        if provider is None or temp_provider_name is not None:
            try:
                temp_account = pool_repo.claim_temp_mailbox_atomic(
                    conn,
                    caller_id=caller_id,
                    task_id=task_id,
                    lease_seconds=default_lease,
                    provider=temp_provider_name,
                    email_domain=email_domain,
                )
            except pool_repo.PoolRepositoryError as e:
                raise PoolServiceError(str(e), e.error_code, http_status=500) from e
            if temp_account is not None:
                return temp_account

        # 池为空：显式指定 provider 时，调用对应 Provider 动态创建邮箱。
        if provider == "cloudflare_temp_mail":
            created_email, created_meta = _create_cf_mailbox_for_pool(email_domain=email_domain)

            try:
                inserted = pool_repo.insert_claimed_account(
                    conn,
                    email=created_email,
                    caller_id=caller_id,
                    task_id=task_id,
                    lease_seconds=default_lease,
                    provider="cloudflare_temp_mail",
                    account_type="temp_mail",
                    project_key=project_key,
                    temp_mail_meta=created_meta,
                    claim_log_detail="CF邮箱动态创建",
                )
                return inserted
            except pool_repo.PoolRepositoryError as e:
                # DB 写入失败时，尽力删除已创建的远程邮箱，避免资源泄漏（非阻塞）
                _delete_cf_mailbox_nonblocking(email=created_email, meta=created_meta)
                raise PoolServiceError(str(e), e.error_code, http_status=500) from e
            except Exception as e:
                _delete_cf_mailbox_nonblocking(email=created_email, meta=created_meta)
                raise PoolServiceError("动态写入 CF 邮箱失败", "db_error", http_status=500) from e

        # 任何已注册的临时邮箱 Provider 均可通过同一工厂动态创建。
        if temp_provider_name is not None and provider != "cloudflare_temp_mail":
            created_email, created_meta = _create_provider_mailbox_for_pool(
                provider_name=temp_provider_name,
                email_domain=email_domain,
            )
            try:
                return pool_repo.insert_claimed_temp_mailbox(
                    conn,
                    email=created_email,
                    caller_id=caller_id,
                    task_id=task_id,
                    lease_seconds=default_lease,
                    provider=temp_provider_name,
                    temp_mail_meta=created_meta,
                )
            except pool_repo.PoolRepositoryError as e:
                _delete_provider_mailbox_nonblocking(
                    provider_name=temp_provider_name,
                    email=created_email,
                    meta=created_meta,
                )
                raise PoolServiceError(str(e), e.error_code, http_status=500) from e
            except Exception as e:
                _delete_provider_mailbox_nonblocking(
                    provider_name=temp_provider_name,
                    email=created_email,
                    meta=created_meta,
                )
                raise PoolServiceError("动态写入 Provider 邮箱失败", "db_error", http_status=500) from e

        raise PoolServiceError("池中没有符合条件的可用邮箱", "no_available_account", http_status=200)
    finally:
        conn.close()


def _validate_claim_ownership(
    row: Optional[dict],
    *,
    action: str,
    claim_token: str,
    caller_id: str,
    task_id: str,
) -> None:
    """校验 release/complete 的领取归属（accounts 与 temp_emails 共用）。"""
    if row is None:
        raise PoolServiceError("账号不存在", "account_not_found", http_status=400)
    if row.get("pool_status") != "claimed":
        raise PoolServiceError(
            f"账号当前状态为 '{row.get('pool_status')}'，无法 {action}",
            "not_claimed",
            http_status=409,
        )
    if row.get("claim_token") != claim_token:
        raise PoolServiceError("claim_token 不匹配", "token_mismatch", http_status=403)
    if row.get("claimed_by") != f"{caller_id}:{task_id}":
        raise PoolServiceError(
            "caller_id 或 task_id 与领取记录不一致",
            "caller_mismatch",
            http_status=403,
        )


def release_claim(
    *,
    account_id: int,
    claim_token: str,
    caller_id: str,
    task_id: str,
    reason: Optional[str] = None,
) -> None:
    """释放已领取的邮箱账号（不计入成功/失败统计，直接回 available）。"""
    _validate_caller_id(caller_id)
    _validate_task_id(task_id)
    if not claim_token or not claim_token.strip():
        raise PoolServiceError("claim_token 不能为空", "claim_token_empty")
    if reason and len(reason) > REASON_MAX_LEN:
        raise PoolServiceError(f"reason 超过最大长度 {REASON_MAX_LEN}", "reason_too_long")

    conn = create_sqlite_connection()
    try:
        # 临时邮箱池账号：account_id 带偏移，路由到 temp_emails
        if pool_repo.is_temp_pool_account_id(account_id):
            temp_id = pool_repo.temp_id_from_account_id(account_id)
            temp_row = pool_repo.get_temp_mailbox_pool_row(conn, temp_id)
            _validate_claim_ownership(
                temp_row, action="release", claim_token=claim_token, caller_id=caller_id, task_id=task_id
            )
            pool_repo.release_temp_mailbox(conn, temp_id, claim_token, caller_id, task_id, reason)
            return

        row = conn.execute(
            "SELECT id, claim_token, claimed_by, pool_status FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        _validate_claim_ownership(
            dict(row) if row is not None else None,
            action="release",
            claim_token=claim_token,
            caller_id=caller_id,
            task_id=task_id,
        )

        pool_repo.release(conn, account_id, claim_token, caller_id, task_id, reason)
    finally:
        conn.close()


def complete_claim(
    *,
    account_id: int,
    claim_token: str,
    caller_id: str,
    task_id: str,
    result: str,
    detail: Optional[str] = None,
) -> str:
    """
    标记领取结果并驱动状态机流转。

    返回账号的新 pool_status。
    """
    _validate_caller_id(caller_id)
    _validate_task_id(task_id)
    if not claim_token or not claim_token.strip():
        raise PoolServiceError("claim_token 不能为空", "claim_token_empty")
    if result not in VALID_RESULTS:
        raise PoolServiceError(
            f"result 必须是 {sorted(VALID_RESULTS)} 之一",
            "invalid_result",
        )
    if detail and len(detail) > DETAIL_MAX_LEN:
        raise PoolServiceError(f"detail 超过最大长度 {DETAIL_MAX_LEN}", "detail_too_long")

    conn = create_sqlite_connection()
    try:
        # 临时邮箱池账号：account_id 带偏移，路由到 temp_emails（一次性资源，无项目复用/CF 删除）
        if pool_repo.is_temp_pool_account_id(account_id):
            temp_id = pool_repo.temp_id_from_account_id(account_id)
            temp_row = pool_repo.get_temp_mailbox_pool_row(conn, temp_id)
            _validate_claim_ownership(
                temp_row, action="complete", claim_token=claim_token, caller_id=caller_id, task_id=task_id
            )
            return pool_repo.complete_temp_mailbox(conn, temp_id, claim_token, caller_id, task_id, result, detail)

        row = conn.execute(
            """
            SELECT id, email, provider, account_type, temp_mail_meta,
                   claimed_project_key,
                   claim_token, claimed_by, pool_status
            FROM accounts
            WHERE id = ?
            """,
            (account_id,),
        ).fetchone()
        _validate_claim_ownership(
            dict(row) if row is not None else None,
            action="complete",
            claim_token=claim_token,
            caller_id=caller_id,
            task_id=task_id,
        )

        # 从 claim 上下文读取 claimed_project_key，而非依赖 API 入参
        # 保证 claim-complete 即使未传 project_key 也能正确判定复用路径（TDD §4.1 N-03）
        claimed_project_key = str(row["claimed_project_key"] or "").strip() or None
        enable_project_reuse = _is_project_reuse_eligible_account(
            provider=row["provider"],
            account_type=row["account_type"],
            claimed_project_key=claimed_project_key,
        )

        # complete 先更新本地状态（事务内），再做 CF 删除（非阻塞）
        new_status = pool_repo.complete(
            conn,
            account_id,
            claim_token,
            caller_id,
            task_id,
            result,
            detail,
            claimed_project_key=claimed_project_key,
            enable_project_reuse=enable_project_reuse,
        )

        if (row["provider"] or "").strip() == "cloudflare_temp_mail" and result in CF_DELETE_ON_RESULTS:
            meta_str = row["temp_mail_meta"]
            meta_obj = {}
            if isinstance(meta_str, str) and meta_str.strip():
                try:
                    meta_obj = json.loads(meta_str)
                except Exception:
                    meta_obj = {}
            _delete_cf_mailbox_nonblocking(email=row["email"], meta=meta_obj)

        return new_status
    finally:
        conn.close()


def _create_cf_mailbox_for_pool(*, email_domain: Optional[str]) -> tuple[str, dict]:
    """调用 CF Worker 创建邮箱（Service 层），返回 (email, meta_dict)。"""
    try:
        from outlook_web.services.temp_mail_provider_cf import (
            CloudflareTempMailProvider,
        )

        provider = CloudflareTempMailProvider()
        result = provider.create_mailbox(prefix=None, domain=email_domain)
    except Exception as e:
        # 上游异常：统一映射为 UPSTREAM_SERVER_ERROR
        logger.warning("[pool] CF create_mailbox exception: %s", e)
        raise PoolServiceError("CF Worker 创建邮箱异常", "UPSTREAM_SERVER_ERROR", http_status=500) from e

    if not isinstance(result, dict):
        raise PoolServiceError("CF Worker 返回格式错误", "UPSTREAM_BAD_PAYLOAD", http_status=500)

    if not result.get("success"):
        error_code = str(result.get("error_code") or "UPSTREAM_SERVER_ERROR")
        error_msg = str(result.get("error") or "CF Worker 创建邮箱失败")
        raise PoolServiceError(error_msg, error_code, http_status=500)

    email = str(result.get("email") or "").strip()
    if not email:
        raise PoolServiceError("CF Worker 未返回邮箱地址", "UPSTREAM_BAD_PAYLOAD", http_status=500)

    meta = result.get("meta") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}

    if not isinstance(meta, dict):
        meta = {}

    return email, meta


def _create_provider_mailbox_for_pool(
    *,
    provider_name: str,
    email_domain: Optional[str],
) -> tuple[str, dict]:
    """通过插件工厂创建邮箱，供支持动态创建的 Provider 接入邮箱池。"""
    try:
        from outlook_web.services.temp_mail_provider_factory import (
            TempMailProviderFactoryError,
            get_temp_mail_provider,
        )

        provider = get_temp_mail_provider(provider_name)
        result = provider.create_mailbox(prefix=None, domain=email_domain)
    except TempMailProviderFactoryError as exc:
        logger.warning("[pool] %s Provider 未就绪: code=%s", provider_name, exc.code)
        raise PoolServiceError(exc.message, exc.code, http_status=exc.status) from exc
    except Exception as exc:
        logger.warning("[pool] %s create_mailbox exception: %s", provider_name, exc)
        raise PoolServiceError(
            f"{provider_name} 创建邮箱异常",
            "UPSTREAM_SERVER_ERROR",
            http_status=500,
        ) from exc

    if not isinstance(result, dict):
        raise PoolServiceError(f"{provider_name} 返回格式错误", "UPSTREAM_BAD_PAYLOAD", http_status=500)

    if not result.get("success"):
        error_code = str(result.get("error_code") or "UPSTREAM_SERVER_ERROR")
        error_msg = str(result.get("error") or f"{provider_name} 创建邮箱失败")
        raise PoolServiceError(error_msg, error_code, http_status=500)

    email = str(result.get("email") or "").strip()
    if not email:
        raise PoolServiceError(f"{provider_name} 未返回邮箱地址", "UPSTREAM_BAD_PAYLOAD", http_status=500)

    meta = result.get("meta") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    if not isinstance(meta, dict):
        meta = {}
    meta["provider_name"] = provider_name
    capabilities = getattr(provider, "provider_capabilities", {})
    if isinstance(capabilities, dict):
        meta["provider_capabilities"] = {str(key): bool(value) for key, value in capabilities.items()}
    return email, meta


def _delete_provider_mailbox_nonblocking(*, provider_name: str, email: str, meta: dict) -> None:
    """数据库写入失败时，尽力回收刚创建的 Provider 邮箱。"""
    try:
        from outlook_web.services.temp_mail_provider_factory import get_temp_mail_provider

        provider = get_temp_mail_provider(provider_name)
        capabilities = getattr(provider, "provider_capabilities", {})
        if isinstance(capabilities, dict) and capabilities.get("delete_mailbox") is False:
            return
        if provider.delete_mailbox({"email": email, "meta": meta}):
            logger.info("[pool] 已回收 %s 远程邮箱: %s", provider_name, email)
        else:
            logger.warning("[pool] 回收 %s 远程邮箱失败: %s", provider_name, email)
    except Exception as exc:
        logger.warning("[pool] 回收 %s 远程邮箱异常: %s, error=%s", provider_name, email, exc)


def _delete_cf_mailbox_nonblocking(*, email: str, meta: dict) -> None:
    """非阻塞删除远程 CF 邮箱（仅记录日志，不抛异常）。"""
    try:
        from outlook_web.services.temp_mail_provider_cf import (
            CloudflareTempMailProvider,
        )

        provider = CloudflareTempMailProvider()
        success = provider.delete_mailbox({"email": email, "meta": meta})
        if success:
            logger.info("[pool] 已删除 CF 远程邮箱: %s", email)
        else:
            logger.warning("[pool] 删除 CF 远程邮箱失败(返回 False): %s", email)
    except Exception as e:
        logger.warning("[pool] 删除 CF 远程邮箱异常: %s, error=%s", email, e)


def get_claim_context(*, claim_token: str) -> Optional[dict]:
    """
    根据 claim_token 查询领取上下文（email / claimed_at / email_domain 等）。
    返回 dict 或 None（token 不存在时）。
    """
    if not claim_token or not claim_token.strip():
        return None
    conn = create_sqlite_connection()
    try:
        return pool_repo.get_claim_context(conn, claim_token.strip())
    finally:
        conn.close()


def append_claim_read_context(
    *,
    account_id: int,
    claim_token: str,
    caller_id: str,
    task_id: str,
    detail: Optional[str] = None,
) -> None:
    """
    追加一条读取上下文日志（claim 邮箱被用于邮件读取时记录）。
    """
    if not claim_token or not claim_token.strip():
        return
    # 临时邮箱池账号不写 account_claim_logs（该表 account_id 对 accounts 有外键约束）
    if pool_repo.is_temp_pool_account_id(account_id):
        return
    conn = create_sqlite_connection()
    try:
        pool_repo.append_claim_read_context(conn, account_id, claim_token, caller_id, task_id, detail)
    finally:
        conn.close()


def get_pool_stats() -> dict:
    """返回池状态统计（不修改任何数据）。"""
    conn = create_sqlite_connection()
    try:
        return pool_repo.get_stats(conn)
    finally:
        conn.close()
