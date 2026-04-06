from __future__ import annotations

from flask import Blueprint

from outlook_web.controllers import system as system_controller


def create_blueprint() -> Blueprint:
    """创建 system Blueprint"""
    bp = Blueprint("system", __name__)
    bp.add_url_rule("/healthz", view_func=system_controller.healthz, methods=["GET"])
    bp.add_url_rule(
        "/api/system/health",
        view_func=system_controller.api_system_health,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/system/diagnostics",
        view_func=system_controller.api_system_diagnostics,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/system/upgrade-status",
        view_func=system_controller.api_system_upgrade_status,
        methods=["GET"],
    )

    # PRD-00008 / FD-00008：对外开放系统自检接口（仅 API Key 鉴权）
    bp.add_url_rule(
        "/api/external/health",
        view_func=system_controller.api_external_health,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/external/capabilities",
        view_func=system_controller.api_external_capabilities,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/external/account-status",
        view_func=system_controller.api_external_account_status,
        methods=["GET"],
    )

    # FD: 版本更新检测与一键更新
    bp.add_url_rule(
        "/api/system/version-check",
        view_func=system_controller.api_version_check,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/system/trigger-update",
        view_func=system_controller.api_trigger_update,
        methods=["POST"],
    )

    return bp
