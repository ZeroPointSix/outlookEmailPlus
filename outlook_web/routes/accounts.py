from __future__ import annotations

from flask import Blueprint


def create_blueprint(*, impl) -> Blueprint:
    bp = Blueprint("accounts", __name__)

    bp.add_url_rule("/api/accounts", view_func=impl.api_get_accounts, methods=["GET"])
    bp.add_url_rule("/api/accounts", view_func=impl.api_add_account, methods=["POST"])
    bp.add_url_rule("/api/accounts/<int:account_id>", view_func=impl.api_get_account, methods=["GET"])
    bp.add_url_rule("/api/accounts/<int:account_id>", view_func=impl.api_update_account, methods=["PUT"])
    bp.add_url_rule("/api/accounts/<int:account_id>", view_func=impl.api_delete_account, methods=["DELETE"])
    bp.add_url_rule("/api/accounts/email/<email_addr>", view_func=impl.api_delete_account_by_email, methods=["DELETE"])

    bp.add_url_rule("/api/accounts/search", view_func=impl.api_search_accounts, methods=["GET"])
    bp.add_url_rule("/api/accounts/batch-update-group", view_func=impl.api_batch_update_account_group, methods=["POST"])
    bp.add_url_rule("/api/accounts/batch-delete", view_func=impl.api_batch_delete_accounts, methods=["POST"])
    bp.add_url_rule("/api/accounts/tags", view_func=impl.api_batch_manage_tags, methods=["POST"])

    bp.add_url_rule("/api/accounts/export", view_func=impl.api_export_all_accounts, methods=["GET"])
    bp.add_url_rule("/api/accounts/export-selected", view_func=impl.api_export_selected_accounts, methods=["POST"])
    bp.add_url_rule("/api/export/verify", view_func=impl.api_generate_export_verify_token, methods=["POST"])

    bp.add_url_rule("/api/accounts/<int:account_id>/refresh", view_func=impl.api_refresh_account, methods=["POST"])
    bp.add_url_rule("/api/accounts/refresh-all", view_func=impl.api_refresh_all_accounts, methods=["GET"])
    bp.add_url_rule("/api/accounts/<int:account_id>/retry-refresh", view_func=impl.api_retry_refresh_account, methods=["POST"])
    bp.add_url_rule("/api/accounts/refresh-failed", view_func=impl.api_refresh_failed_accounts, methods=["POST"])
    bp.add_url_rule("/api/accounts/trigger-scheduled-refresh", view_func=impl.api_trigger_scheduled_refresh, methods=["GET"])

    bp.add_url_rule("/api/accounts/refresh-logs", view_func=impl.api_get_refresh_logs, methods=["GET"])
    bp.add_url_rule("/api/accounts/<int:account_id>/refresh-logs", view_func=impl.api_get_account_refresh_logs, methods=["GET"])
    bp.add_url_rule("/api/accounts/refresh-logs/failed", view_func=impl.api_get_failed_refresh_logs, methods=["GET"])
    bp.add_url_rule("/api/accounts/refresh-stats", view_func=impl.api_get_refresh_stats, methods=["GET"])

    return bp

