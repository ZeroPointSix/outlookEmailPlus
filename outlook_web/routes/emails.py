from __future__ import annotations

from flask import Blueprint


def create_blueprint(*, impl) -> Blueprint:
    bp = Blueprint("emails", __name__)
    bp.add_url_rule("/api/emails/<email_addr>", view_func=impl.api_get_emails, methods=["GET"])
    bp.add_url_rule("/api/emails/<email_addr>/extract-verification", view_func=impl.api_extract_verification, methods=["GET"])
    bp.add_url_rule("/api/emails/delete", view_func=impl.api_delete_emails, methods=["POST"])
    bp.add_url_rule("/api/email/<email_addr>/<path:message_id>", view_func=impl.api_get_email_detail, methods=["GET"])
    return bp

