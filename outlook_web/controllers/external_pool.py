from __future__ import annotations

from typing import Any

from flask import jsonify, request

from outlook_web.repositories import accounts as accounts_repo
from outlook_web.repositories import settings as settings_repo
from outlook_web.security.auth import api_key_required, get_external_api_consumer
from outlook_web.security.external_api_guard import external_api_guards
from outlook_web.services import external_api as external_api_service
from outlook_web.services.pool import (
    PoolServiceError,
    claim_random,
    complete_claim,
    get_pool_stats,
    release_claim,
)


def _audit(endpoint: str, status: str, *, details: dict[str, Any], email_addr: str = "") -> None:
    external_api_service.audit_external_api_access(
        action="external_api_access",
        email_addr=email_addr,
        endpoint=endpoint,
        status=status,
        details=details,
    )


def _pool_error_code(error_code: str) -> str:
    return str(error_code or "INTERNAL_ERROR").upper()


def _error_response(endpoint: str, exc: PoolServiceError):
    code = _pool_error_code(exc.error_code)
    _audit(endpoint, "error", details={"code": code})
    return jsonify(external_api_service.fail(code, str(exc))), exc.http_status


def _check_pool_external_enabled(endpoint: str):
    if settings_repo.get_pool_external_enabled():
        return None
    _audit(endpoint, "error", details={"code": "FEATURE_DISABLED", "feature": "external_pool"})
    return (
        jsonify(
            external_api_service.fail(
                "FEATURE_DISABLED",
                "功能 external_pool 当前未启用",
                data={"feature": "external_pool"},
            )
        ),
        403,
    )


def _check_pool_access(endpoint: str):
    consumer = get_external_api_consumer() or {}
    if bool(consumer.get("is_legacy")) or bool(consumer.get("pool_access")):
        return None
    _audit(
        endpoint,
        "error",
        details={"code": "FORBIDDEN", "feature": "external_pool", "reason": "pool_access_required"},
    )
    return (
        jsonify(
            external_api_service.fail(
                "FORBIDDEN",
                "当前 API Key 无权访问 external pool",
                data={"feature": "external_pool", "reason": "pool_access_required"},
            )
        ),
        403,
    )


def _get_consumer_key() -> str:
    consumer = get_external_api_consumer() or {}
    return str(consumer.get("consumer_key") or "").strip()


def _account_payload(account_id: int, *, pool_status: str) -> dict[str, Any]:
    account = accounts_repo.get_account_by_id(account_id) or {}
    return {
        "account_id": account_id,
        "pool_status": pool_status,
        "provider": account.get("provider") or "",
        "email_domain": account.get("email_domain") or "",
    }


def _parse_account_id(endpoint: str, raw_value) -> int | tuple:
    if raw_value is None:
        _audit(endpoint, "error", details={"code": "ACCOUNT_ID_MISSING"})
        return jsonify(external_api_service.fail("ACCOUNT_ID_MISSING", "account_id 不能为空")), 400
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        _audit(endpoint, "error", details={"code": "ACCOUNT_ID_INVALID"})
        return jsonify(external_api_service.fail("ACCOUNT_ID_INVALID", "account_id 必须为整数")), 400


@api_key_required
@external_api_guards(feature="pool_claim_random")
def api_external_pool_claim_random():
    endpoint = "/api/external/pool/claim-random"
    disabled_resp = _check_pool_external_enabled(endpoint)
    if disabled_resp is not None:
        return disabled_resp
    access_resp = _check_pool_access(endpoint)
    if access_resp is not None:
        return access_resp

    consumer_key = _get_consumer_key()
    body = request.get_json(silent=True) or {}
    caller_id = body.get("caller_id", "")
    task_id = body.get("task_id", "")
    project_key = body.get("project_key", "")
    provider = body.get("provider")
    email_domain = body.get("email_domain")

    try:
        account = claim_random(
            consumer_key=consumer_key,
            project_key=project_key,
            caller_id=caller_id,
            task_id=task_id,
            provider=provider,
            email_domain=email_domain,
        )
        data = {
            "account_id": account["id"],
            "email": account["email"],
            "provider": account.get("provider") or "",
            "email_domain": account.get("email_domain") or "",
            "claim_token": account["claim_token"],
            "claimed_at": account.get("claimed_at") or "",
            "lease_expires_at": account["lease_expires_at"],
        }
        _audit(
            endpoint,
            "ok",
            details={
                "provider": data["provider"],
                "email_domain": data["email_domain"],
                "project_key": project_key,
                "account_id": data["account_id"],
            },
            email_addr=data["email"],
        )
        return jsonify(external_api_service.ok(data))
    except PoolServiceError as exc:
        return _error_response(endpoint, exc)
    except Exception as exc:
        _audit(endpoint, "error", details={"code": "INTERNAL_ERROR", "err": type(exc).__name__})
        return jsonify(external_api_service.fail("INTERNAL_ERROR", "服务内部错误")), 500


@api_key_required
@external_api_guards(feature="pool_claim_release")
def api_external_pool_claim_release():
    endpoint = "/api/external/pool/claim-release"
    disabled_resp = _check_pool_external_enabled(endpoint)
    if disabled_resp is not None:
        return disabled_resp
    access_resp = _check_pool_access(endpoint)
    if access_resp is not None:
        return access_resp

    consumer_key = _get_consumer_key()
    body = request.get_json(silent=True) or {}
    account_id = _parse_account_id(endpoint, body.get("account_id"))
    if isinstance(account_id, tuple):
        return account_id

    claim_token = body.get("claim_token", "")
    caller_id = body.get("caller_id", "")
    task_id = body.get("task_id", "")
    project_key = body.get("project_key", "")
    reason = body.get("reason")

    try:
        release_claim(
            consumer_key=consumer_key,
            project_key=project_key,
            account_id=account_id,
            claim_token=claim_token,
            caller_id=caller_id,
            task_id=task_id,
            reason=reason,
        )
        _audit(endpoint, "ok", details={"account_id": account_id, "project_key": project_key})
        return jsonify(external_api_service.ok(_account_payload(account_id, pool_status="available")))
    except PoolServiceError as exc:
        return _error_response(endpoint, exc)
    except Exception as exc:
        _audit(endpoint, "error", details={"code": "INTERNAL_ERROR", "err": type(exc).__name__})
        return jsonify(external_api_service.fail("INTERNAL_ERROR", "服务内部错误")), 500


@api_key_required
@external_api_guards(feature="pool_claim_complete")
def api_external_pool_claim_complete():
    endpoint = "/api/external/pool/claim-complete"
    disabled_resp = _check_pool_external_enabled(endpoint)
    if disabled_resp is not None:
        return disabled_resp
    access_resp = _check_pool_access(endpoint)
    if access_resp is not None:
        return access_resp

    consumer_key = _get_consumer_key()
    body = request.get_json(silent=True) or {}
    account_id = _parse_account_id(endpoint, body.get("account_id"))
    if isinstance(account_id, tuple):
        return account_id

    claim_token = body.get("claim_token", "")
    caller_id = body.get("caller_id", "")
    task_id = body.get("task_id", "")
    project_key = body.get("project_key", "")
    result = body.get("result", "")
    detail = body.get("detail")

    try:
        new_status = complete_claim(
            consumer_key=consumer_key,
            project_key=project_key,
            account_id=account_id,
            claim_token=claim_token,
            caller_id=caller_id,
            task_id=task_id,
            result=result,
            detail=detail,
        )
        _audit(
            endpoint,
            "ok",
            details={
                "account_id": account_id,
                "project_key": project_key,
                "result": result,
                "pool_status": new_status,
            },
        )
        return jsonify(external_api_service.ok(_account_payload(account_id, pool_status=new_status)))
    except PoolServiceError as exc:
        return _error_response(endpoint, exc)
    except Exception as exc:
        _audit(endpoint, "error", details={"code": "INTERNAL_ERROR", "err": type(exc).__name__})
        return jsonify(external_api_service.fail("INTERNAL_ERROR", "服务内部错误")), 500


@api_key_required
@external_api_guards(feature="pool_stats")
def api_external_pool_stats():
    endpoint = "/api/external/pool/stats"
    disabled_resp = _check_pool_external_enabled(endpoint)
    if disabled_resp is not None:
        return disabled_resp
    access_resp = _check_pool_access(endpoint)
    if access_resp is not None:
        return access_resp
    try:
        stats = get_pool_stats()
        _audit(endpoint, "ok", details={"snapshot": True})
        return jsonify(external_api_service.ok(stats))
    except Exception as exc:
        _audit(endpoint, "error", details={"code": "INTERNAL_ERROR", "err": type(exc).__name__})
        return jsonify(external_api_service.fail("INTERNAL_ERROR", "服务内部错误")), 500
