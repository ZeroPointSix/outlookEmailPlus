from __future__ import annotations

from flask import Blueprint

from outlook_web.controllers import settings as settings_controller


def create_blueprint() -> Blueprint:
    """创建 settings Blueprint"""
    bp = Blueprint("settings", __name__)
    bp.add_url_rule(
        "/api/settings/validate-cron",
        view_func=settings_controller.api_validate_cron,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/api/settings/telegram-test",
        view_func=settings_controller.api_test_telegram,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/api/settings/test-telegram-proxy",
        view_func=settings_controller.api_test_telegram_proxy,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/api/settings/email-test",
        view_func=settings_controller.api_test_email,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/api/settings/cf-worker-sync-domains",
        view_func=settings_controller.api_sync_cf_worker_domains,
        methods=["POST"],
    )
    bp.add_url_rule("/api/settings", view_func=settings_controller.api_get_settings, methods=["GET"])
    bp.add_url_rule(
        "/api/settings",
        view_func=settings_controller.api_update_settings,
        methods=["PUT"],
    )
    return bp
