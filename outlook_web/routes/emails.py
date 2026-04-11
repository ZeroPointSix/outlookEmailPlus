from __future__ import annotations

from flask import Blueprint

from outlook_web.controllers import emails as emails_controller


def create_blueprint() -> Blueprint:
    """创建 emails Blueprint"""
    bp = Blueprint("emails", __name__)
    bp.add_url_rule(
        "/api/emails/<email_addr>",
        view_func=emails_controller.api_get_emails,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/emails/<email_addr>/stream",
        view_func=emails_controller.api_stream_emails,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/emails/<email_addr>/extract-verification",
        view_func=emails_controller.api_extract_verification,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/emails/delete",
        view_func=emails_controller.api_delete_emails,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/api/email/<email_addr>/<path:message_id>",
        view_func=emails_controller.api_get_email_detail,
        methods=["GET"],
    )

    # PRD-00008 / FD-00008：对外开放 API（仅 API Key 鉴权，不依赖登录态）
    bp.add_url_rule(
        "/api/external/messages",
        view_func=emails_controller.api_external_get_messages,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/external/messages/latest",
        view_func=emails_controller.api_external_get_latest_message,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/external/messages/<path:message_id>",
        view_func=emails_controller.api_external_get_message_detail,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/external/messages/<path:message_id>/raw",
        view_func=emails_controller.api_external_get_message_raw,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/external/verification-code",
        view_func=emails_controller.api_external_get_verification_code,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/external/verification-link",
        view_func=emails_controller.api_external_get_verification_link,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/external/wait-message",
        view_func=emails_controller.api_external_wait_message,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/external/probe/<probe_id>",
        view_func=emails_controller.api_external_get_probe_status,
        methods=["GET"],
    )
    return bp
