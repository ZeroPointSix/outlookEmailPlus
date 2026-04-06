from __future__ import annotations

from flask import Blueprint

from outlook_web.controllers import accounts as accounts_controller


def create_blueprint() -> Blueprint:
    bp = Blueprint("accounts", __name__)

    # 基础 CRUD（已迁移到 controllers）
    bp.add_url_rule(
        "/api/accounts", view_func=accounts_controller.api_get_accounts, methods=["GET"]
    )
    bp.add_url_rule(
        "/api/accounts", view_func=accounts_controller.api_add_account, methods=["POST"]
    )
    bp.add_url_rule(
        "/api/providers",
        view_func=accounts_controller.api_get_providers,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/accounts/<int:account_id>",
        view_func=accounts_controller.api_get_account,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/accounts/<int:account_id>",
        view_func=accounts_controller.api_update_account,
        methods=["PUT"],
    )
    bp.add_url_rule(
        "/api/accounts/<int:account_id>",
        view_func=accounts_controller.api_delete_account,
        methods=["DELETE"],
    )
    bp.add_url_rule(
        "/api/accounts/<int:account_id>/remark",
        view_func=accounts_controller.api_update_account_remark,
        methods=["PATCH"],
    )
    bp.add_url_rule(
        "/api/accounts/email/<email_addr>",
        view_func=accounts_controller.api_delete_account_by_email,
        methods=["DELETE"],
    )

    # 批量操作（已迁移到 controllers）
    bp.add_url_rule(
        "/api/accounts/search",
        view_func=accounts_controller.api_search_accounts,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/accounts/batch-update-group",
        view_func=accounts_controller.api_batch_update_account_group,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/api/accounts/batch-delete",
        view_func=accounts_controller.api_batch_delete_accounts,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/api/accounts/tags",
        view_func=accounts_controller.api_batch_manage_tags,
        methods=["POST"],
    )

    # 导出功能（已迁移到 controllers）
    bp.add_url_rule(
        "/api/accounts/export",
        view_func=accounts_controller.api_export_all_accounts,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/accounts/export-selected",
        view_func=accounts_controller.api_export_selected_accounts,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/api/export/verify",
        view_func=accounts_controller.api_generate_export_verify_token,
        methods=["POST"],
    )

    # Token 刷新（已迁移到 controllers）
    bp.add_url_rule(
        "/api/accounts/<int:account_id>/refresh",
        view_func=accounts_controller.api_refresh_account,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/api/accounts/refresh-all",
        view_func=accounts_controller.api_refresh_all_accounts,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/accounts/<int:account_id>/retry-refresh",
        view_func=accounts_controller.api_retry_refresh_account,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/api/accounts/refresh-failed",
        view_func=accounts_controller.api_refresh_failed_accounts,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/api/accounts/trigger-scheduled-refresh",
        view_func=accounts_controller.api_trigger_scheduled_refresh,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/accounts/refresh/selected",
        view_func=accounts_controller.api_refresh_selected_accounts,
        methods=["POST"],
    )

    # 刷新日志（已迁移到 controllers）
    bp.add_url_rule(
        "/api/accounts/refresh-logs",
        view_func=accounts_controller.api_get_refresh_logs,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/accounts/<int:account_id>/refresh-logs",
        view_func=accounts_controller.api_get_account_refresh_logs,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/accounts/refresh-logs/failed",
        view_func=accounts_controller.api_get_failed_refresh_logs,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/accounts/refresh-stats",
        view_func=accounts_controller.api_get_refresh_stats,
        methods=["GET"],
    )

    # Telegram 推送开关
    bp.add_url_rule(
        "/api/accounts/<int:account_id>/telegram-toggle",
        view_func=accounts_controller.api_telegram_toggle,
        methods=["POST"],
    )

    return bp
