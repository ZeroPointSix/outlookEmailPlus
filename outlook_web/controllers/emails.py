from __future__ import annotations

import logging
from typing import Any

from flask import jsonify, request

from outlook_web import config
from outlook_web.audit import log_audit
from outlook_web.db import get_db
from outlook_web.errors import build_error_payload, build_error_response
from outlook_web.repositories import accounts as accounts_repo
from outlook_web.repositories import groups as groups_repo
from outlook_web.security.auth import api_key_required, login_required
from outlook_web.security.external_api_guard import external_api_guards
from outlook_web.services import account_compact_summary as compact_summary_service
from outlook_web.services import email_delete as email_delete_service
from outlook_web.services import external_api as external_api_service
from outlook_web.services import graph as graph_service
from outlook_web.services import imap as imap_service
from outlook_web.services.imap_generic import get_email_detail_imap_generic_result, get_emails_imap_generic

_LOGGER = logging.getLogger("outlook_web.controllers.emails")

# IMAP 服务器配置
IMAP_SERVER_OLD = "outlook.office365.com"
IMAP_SERVER_NEW = "outlook.live.com"
_EXTERNAL_NESTED_UPSTREAM_CODES = {"IMAP_AUTH_FAILED", "IMAP_CONNECT_FAILED", "IMAP_FOLDER_NOT_FOUND"}


def _build_response_from_error_payload(error_payload: dict[str, Any]):
    return build_error_response(
        str(error_payload.get("code") or "INTERNAL_ERROR"),
        str(error_payload.get("message") or "请求失败"),
        message_en=str(error_payload.get("message_en") or "Request failed"),
        err_type=str(error_payload.get("type") or "Error"),
        status=int(error_payload.get("status") or 500),
        details=error_payload.get("details") or "",
        trace_id=error_payload.get("trace_id"),
    )


def _build_account_credential_decrypt_failed_response(account: dict[str, Any]):
    credential_errors = account.get("_credential_errors") or []
    if not credential_errors:
        return None

    fields = sorted({str(item.get("field") or "").strip() for item in credential_errors if item.get("field")})
    details = {
        "fields": fields,
        "errors": credential_errors,
    }
    return build_error_response(
        "ACCOUNT_CREDENTIAL_DECRYPT_FAILED",
        "账号凭据解密失败，请重新保存该账号后重试",
        message_en="Account credentials could not be decrypted. Re-save the account and try again.",
        err_type="CredentialDecryptError",
        status=500,
        details=credential_errors,
        extra={"details": details},
    )


# ==================== 邮件 API ====================


@login_required
def api_get_emails(email_addr: str) -> Any:
    """获取邮件列表（支持分页，不使用缓存）"""
    account = accounts_repo.get_account_by_email(email_addr)

    if not account:
        return build_error_response(
            "ACCOUNT_NOT_FOUND",
            "账号不存在",
            message_en="Account not found",
            err_type="NotFoundError",
            status=404,
            details=f"email={email_addr}",
        )

    folder = request.args.get("folder", "inbox")  # inbox, junkemail, deleteditems
    skip = int(request.args.get("skip", 0))
    top = int(request.args.get("top", 20))

    # PRD-00005 / FD-00005 / TDD-00005：按 account_type 路由分发（Outlook 链路保持原样，IMAP 走通用 IMAP 服务）
    account_type = (account.get("account_type") or "outlook").strip().lower()
    if account_type != "imap":
        decrypt_error_response = _build_account_credential_decrypt_failed_response(account)
        if decrypt_error_response:
            return decrypt_error_response

    if account_type == "imap":
        result = get_emails_imap_generic(
            email_addr=email_addr,
            imap_password=account.get("imap_password", "") or "",
            imap_host=account.get("imap_host", "") or "",
            imap_port=account.get("imap_port", 993) or 993,
            folder=folder,
            provider=account.get("provider", "_default") or "_default",
            skip=skip,
            top=top,
        )
        if result.get("success"):
            result["account_summary"] = compact_summary_service.update_summary_from_message_list(
                int(account["id"]),
                result.get("emails") or [],
                folder=folder,
            )
        return jsonify(result)

    # 获取分组代理设置
    proxy_url = ""
    if account.get("group_id"):
        group = groups_repo.get_group_by_id(account["group_id"])
        if group:
            proxy_url = group.get("proxy_url", "") or ""

    # 收集所有错误信息
    all_errors = {}

    # 1. 尝试 Graph API
    graph_result = graph_service.get_emails_graph(account["client_id"], account["refresh_token"], folder, skip, top, proxy_url)
    if graph_result.get("success"):
        emails = graph_result.get("emails", [])
        account_summary = compact_summary_service.update_summary_from_message_list(
            int(account["id"]),
            emails,
            folder=folder,
        )
        # 更新刷新时间
        db = get_db()
        db.execute(
            """
            UPDATE accounts
            SET last_refresh_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE email = ?
        """,
            (email_addr,),
        )
        db.commit()

        # 格式化 Graph API 返回的数据
        formatted = []
        for e in emails:
            formatted.append(
                {
                    "id": e.get("id"),
                    "subject": e.get("subject", "无主题"),
                    "from": e.get("from", {}).get("emailAddress", {}).get("address", "未知"),
                    "date": e.get("receivedDateTime", ""),
                    "is_read": e.get("isRead", False),
                    "has_attachments": e.get("hasAttachments", False),
                    "body_preview": e.get("bodyPreview", ""),
                }
            )

        return jsonify(
            {
                "success": True,
                "emails": formatted,
                "method": "Graph API",
                "has_more": len(formatted) >= top,
                "account_summary": account_summary,
            }
        )
    else:
        graph_error = graph_result.get("error")
        all_errors["graph"] = graph_error

        # 如果是代理错误，不再回退 IMAP
        if isinstance(graph_error, dict) and graph_error.get("type") in (
            "ProxyError",
            "ConnectionError",
        ):
            return build_error_response(
                "EMAIL_PROXY_CONNECTION_FAILED",
                "代理连接失败，请检查分组代理设置",
                message_en="Proxy connection failed. Please check the group proxy settings",
                err_type="ProxyError",
                status=502,
                details=all_errors,
                extra={"details": all_errors},
            )

    imap_new_result = imap_service.get_emails_imap_with_server(
        account["email"],
        account["client_id"],
        account["refresh_token"],
        folder,
        skip,
        top,
        IMAP_SERVER_NEW,
    )
    if imap_new_result.get("success"):
        account_summary = compact_summary_service.update_summary_from_message_list(
            int(account["id"]),
            imap_new_result.get("emails", []),
            folder=folder,
        )
        return jsonify(
            {
                "success": True,
                "emails": imap_new_result.get("emails", []),
                "method": "IMAP (New)",
                "has_more": False,  # IMAP 分页暂未完全实现
                "account_summary": account_summary,
            }
        )
    else:
        all_errors["imap_new"] = imap_new_result.get("error")

    # 3. 尝试旧版 IMAP (outlook.office365.com)
    imap_old_result = imap_service.get_emails_imap_with_server(
        account["email"],
        account["client_id"],
        account["refresh_token"],
        folder,
        skip,
        top,
        IMAP_SERVER_OLD,
    )
    if imap_old_result.get("success"):
        account_summary = compact_summary_service.update_summary_from_message_list(
            int(account["id"]),
            imap_old_result.get("emails", []),
            folder=folder,
        )
        return jsonify(
            {
                "success": True,
                "emails": imap_old_result.get("emails", []),
                "method": "IMAP (Old)",
                "has_more": False,
                "account_summary": account_summary,
            }
        )
    else:
        all_errors["imap_old"] = imap_old_result.get("error")

    return build_error_response(
        "EMAIL_FETCH_ALL_METHODS_FAILED",
        "无法获取邮件，所有方式均失败",
        message_en="Failed to fetch emails. All methods failed",
        status=502,
        details=all_errors,
        extra={"details": all_errors},
    )


@login_required
def api_delete_emails() -> Any:
    """批量删除邮件（永久删除）"""
    data = request.json
    email_addr = data.get("email", "")
    message_ids = data.get("ids", [])

    if not email_addr or not message_ids:
        return build_error_response("INVALID_PARAM", "参数不完整", message_en="Missing required parameters")

    account = accounts_repo.get_account_by_email(email_addr)
    if not account:
        return build_error_response("ACCOUNT_NOT_FOUND", "账号不存在", message_en="Account not found", status=404)

    # PRD-00005：IMAP 账号不支持远程删除（避免误操作与跨厂商副作用）
    account_type = (account.get("account_type") or "outlook").strip().lower()
    if account_type == "imap":
        error_payload = build_error_payload(
            "IMAP_DELETE_NOT_SUPPORTED",
            "IMAP 邮箱不支持远程删除，请在邮箱客户端中操作",
            "NotSupportedError",
            400,
            f"email={email_addr}",
        )
        return jsonify({"success": False, "error": error_payload}), 400

    # 获取分组代理设置
    proxy_url = ""
    if account.get("group_id"):
        group = groups_repo.get_group_by_id(account["group_id"])
        if group:
            proxy_url = group.get("proxy_url", "") or ""

    response_data, method_used = email_delete_service.delete_emails_with_fallback(
        email_addr=email_addr,
        client_id=account["client_id"],
        refresh_token=account["refresh_token"],
        message_ids=message_ids,
        proxy_url=proxy_url,
        delete_emails_graph=graph_service.delete_emails_graph,
        delete_emails_imap=imap_service.delete_emails_imap,
        imap_server_new=IMAP_SERVER_NEW,
        imap_server_old=IMAP_SERVER_OLD,
    )

    if method_used == "graph":
        log_audit(
            "delete",
            "email",
            email_addr,
            f"删除邮件 {len(message_ids)} 封（Graph API）",
        )
    elif method_used == "imap_new":
        log_audit("delete", "email", email_addr, f"删除邮件 {len(message_ids)} 封（IMAP New）")
    elif method_used == "imap_old":
        log_audit("delete", "email", email_addr, f"删除邮件 {len(message_ids)} 封（IMAP Old）")

    return jsonify(response_data)


@login_required
def api_get_email_detail(email_addr: str, message_id: str) -> Any:
    """获取邮件详情"""
    _LOGGER.info("email_detail_request email=%s message_id=%s", email_addr, message_id)
    account = accounts_repo.get_account_by_email(email_addr)

    if not account:
        _LOGGER.warning("email_detail_account_not_found email=%s", email_addr)
        return build_error_response("ACCOUNT_NOT_FOUND", "账号不存在", message_en="Account not found", status=404)

    account_type = (account.get("account_type") or "outlook").strip().lower()
    folder = request.args.get("folder", "inbox")
    _LOGGER.info("email_detail_type=%s provider=%s folder=%s", account_type, account.get("provider", "N/A"), folder)

    if account_type == "imap":
        detail_result = get_email_detail_imap_generic_result(
            email_addr=email_addr,
            imap_password=account.get("imap_password", "") or "",
            imap_host=account.get("imap_host", "") or "",
            imap_port=account.get("imap_port", 993) or 993,
            message_id=message_id,
            folder=folder,
            provider=account.get("provider", "_default") or "_default",
        )
        if detail_result.get("success"):
            detail = detail_result.get("email") or {}
            _LOGGER.info("email_detail_imap_ok email=%s subject=%s", email_addr, detail.get("subject", "?")[:40])
            return jsonify({"success": True, "email": detail})
        error_payload = detail_result.get("error") or {}
        _LOGGER.warning("email_detail_imap_failed email=%s message_id=%s", email_addr, message_id)
        return _build_response_from_error_payload(error_payload)

    method = request.args.get("method", "graph")

    if method == "graph":
        # 获取分组代理设置
        proxy_url = ""
        if account.get("group_id"):
            group = groups_repo.get_group_by_id(account["group_id"])
            if group:
                proxy_url = group.get("proxy_url", "") or ""

        detail = graph_service.get_email_detail_graph(account["client_id"], account["refresh_token"], message_id, proxy_url)
        if detail:
            return jsonify(
                {
                    "success": True,
                    "email": {
                        "id": detail.get("id"),
                        "subject": detail.get("subject", "无主题"),
                        "from": detail.get("from", {}).get("emailAddress", {}).get("address", "未知"),
                        "to": ", ".join(
                            [r.get("emailAddress", {}).get("address", "") for r in detail.get("toRecipients", [])]
                        ),
                        "cc": ", ".join(
                            [r.get("emailAddress", {}).get("address", "") for r in detail.get("ccRecipients", [])]
                        ),
                        "date": detail.get("receivedDateTime", ""),
                        "body": detail.get("body", {}).get("content", ""),
                        "body_type": detail.get("body", {}).get("contentType", "text"),
                    },
                }
            )

    # 如果 Graph API 失败，尝试 IMAP
    detail = imap_service.get_email_detail_imap(
        account["email"],
        account["client_id"],
        account["refresh_token"],
        message_id,
        folder,
    )
    if detail:
        return jsonify({"success": True, "email": detail})

    return build_error_response(
        "EMAIL_DETAIL_FETCH_FAILED",
        "获取邮件详情失败",
        message_en="Failed to fetch email details",
        status=502,
        details=f"email={email_addr} message_id={message_id}",
    )


@login_required
def api_extract_verification(email_addr: str) -> Any:
    """
    提取验证码和链接接口

    功能：从指定邮箱的最新邮件中提取验证码和链接

    实现策略（多 API 回退机制）：
    1. Graph API (inbox) - 优先从收件箱获取
    2. Graph API (junkemail) - 从垃圾邮件获取
    3. IMAP (新服务器) - Graph API 失败时回退
    4. IMAP (旧服务器) - 最后的回退方案
    """
    from outlook_web.services.verification_extractor import extract_verification_info

    # 获取账号信息
    account = accounts_repo.get_account_by_email(email_addr)

    if not account:
        error_payload = build_error_payload(
            "ACCOUNT_NOT_FOUND",
            "邮箱不存在",
            "NotFoundError",
            404,
            f"email={email_addr}",
        )
        return jsonify({"success": False, "error": error_payload}), 404

    # PRD-00005：IMAP 账号验证码提取走 IMAP（Generic）→ 详情 → extractor；Outlook 保持原 Graph→IMAP XOAUTH2 回退链
    account_type = (account.get("account_type") or "outlook").strip().lower()
    if account_type != "imap":
        decrypt_error_response = _build_account_credential_decrypt_failed_response(account)
        if decrypt_error_response:
            return decrypt_error_response

    if account_type == "imap":
        emails_result = get_emails_imap_generic(
            email_addr=email_addr,
            imap_password=account.get("imap_password", "") or "",
            imap_host=account.get("imap_host", "") or "",
            imap_port=account.get("imap_port", 993) or 993,
            folder="inbox",
            provider=account.get("provider", "_default") or "_default",
            skip=0,
            top=1,
        )

        if not emails_result.get("success"):
            error_payload = emails_result.get("error") or {}
            if isinstance(error_payload, dict) and error_payload.get("code"):
                return _build_response_from_error_payload(error_payload)
            return build_error_response(
                "EMAIL_FETCH_FAILED",
                "获取邮件失败",
                message_en="Failed to fetch email",
                err_type="IMAPError",
                status=500,
                details=emails_result,
            )

        emails = emails_result.get("emails") or []
        if not emails:
            error_payload = build_error_payload(
                "EMAIL_NOT_FOUND",
                "未找到邮件",
                "NotFoundError",
                404,
                f"email={email_addr}",
            )
            return jsonify({"success": False, "error": error_payload}), 404

        latest_email = emails[0]
        detail_result = get_email_detail_imap_generic_result(
            email_addr=email_addr,
            imap_password=account.get("imap_password", "") or "",
            imap_host=account.get("imap_host", "") or "",
            imap_port=account.get("imap_port", 993) or 993,
            message_id=latest_email.get("id") or "",
            folder="inbox",
            provider=account.get("provider", "_default") or "_default",
        )

        if not detail_result.get("success"):
            return _build_response_from_error_payload(detail_result.get("error") or {})
        detail = detail_result.get("email") or {}

        # 构建邮件对象用于提取（避免把 HTML 放进 body 导致 extractor 不走 HTML->text）
        email_obj = {
            "subject": detail.get("subject", ""),
            "body": detail.get("body_text", ""),
            "body_html": detail.get("body_html", ""),
            "body_preview": latest_email.get("body_preview", ""),
        }

        try:
            result = extract_verification_info(email_obj)
            account_summary = compact_summary_service.update_summary_from_verification(
                int(account["id"]),
                message=latest_email,
                verification_code=str(result.get("verification_code") or ""),
                folder="inbox",
            )
            result.update(
                {
                    "email": email_addr,
                    "subject": latest_email.get("subject", ""),
                    "from": latest_email.get("from", ""),
                    "received_at": latest_email.get("date", ""),
                    "folder": "inbox",
                }
            )
            return jsonify({"success": True, "data": result, "message": "提取成功", "account_summary": account_summary})
        except ValueError as e:
            error_payload = build_error_payload(
                "VERIFICATION_NOT_FOUND",
                str(e),
                "NotFoundError",
                404,
                f"email={email_addr}",
            )
            return jsonify({"success": False, "error": error_payload}), 404
        except Exception as e:
            error_payload = build_error_payload("EXTRACT_ERROR", "提取失败", "ExtractError", 500, str(e))
            return jsonify({"success": False, "error": error_payload}), 500

    # 获取分组代理设置
    proxy_url = ""
    if account.get("group_id"):
        group = groups_repo.get_group_by_id(account["group_id"])
        if group:
            proxy_url = group.get("proxy_url", "") or ""

    # 收集邮件（同时从收件箱和垃圾邮件获取）
    emails = []
    graph_success = False

    # 1. 尝试 Graph API 从收件箱获取最新邮件
    try:
        inbox_result = graph_service.get_emails_graph(
            account["client_id"],
            account["refresh_token"],
            folder="inbox",
            skip=0,
            top=1,
            proxy_url=proxy_url,
        )
        if inbox_result.get("success"):
            for item in inbox_result.get("emails", []):
                enriched = dict(item)
                enriched["folder"] = "inbox"
                emails.append(enriched)
            graph_success = True
    except Exception:
        pass

    # 2. 尝试 Graph API 从垃圾邮件获取最新邮件
    try:
        junk_result = graph_service.get_emails_graph(
            account["client_id"],
            account["refresh_token"],
            folder="junkemail",
            skip=0,
            top=1,
            proxy_url=proxy_url,
        )
        if junk_result.get("success"):
            for item in junk_result.get("emails", []):
                enriched = dict(item)
                enriched["folder"] = "junkemail"
                emails.append(enriched)
            graph_success = True
    except Exception:
        pass

    # 3. 如果 Graph API 失败，尝试 IMAP 回退
    if not graph_success or not emails:
        # 尝试新版 IMAP 服务器
        try:
            imap_new_result = imap_service.get_emails_imap_with_server(
                account["email"],
                account["client_id"],
                account["refresh_token"],
                folder="inbox",
                skip=0,
                top=1,
                server=IMAP_SERVER_NEW,
            )
            if imap_new_result.get("success"):
                for item in imap_new_result.get("emails", []):
                    enriched = dict(item)
                    enriched["folder"] = "inbox"
                    emails.append(enriched)
        except Exception:
            pass

        # 尝试旧版 IMAP 服务器
        try:
            imap_old_result = imap_service.get_emails_imap_with_server(
                account["email"],
                account["client_id"],
                account["refresh_token"],
                folder="inbox",
                skip=0,
                top=1,
                server=IMAP_SERVER_OLD,
            )
            if imap_old_result.get("success"):
                for item in imap_old_result.get("emails", []):
                    enriched = dict(item)
                    enriched["folder"] = "inbox"
                    emails.append(enriched)
        except Exception:
            pass

    if not emails:
        error_payload = build_error_payload("EMAIL_NOT_FOUND", "未找到邮件", "NotFoundError", 404, f"email={email_addr}")
        return jsonify({"success": False, "error": error_payload}), 404

    # 按时间排序，取最新的一封
    emails.sort(key=lambda x: x.get("receivedDateTime", "") or x.get("date", ""), reverse=True)
    latest_email = emails[0]

    # 获取邮件详情以获取完整内容
    email_detail = None

    # 尝试 Graph API 获取详情
    try:
        email_detail = graph_service.get_email_detail_graph(
            account["client_id"],
            account["refresh_token"],
            latest_email.get("id"),
            proxy_url,
        )
    except Exception:
        pass

    # 如果 Graph API 失败，尝试 IMAP 获取详情
    if not email_detail:
        try:
            email_detail = imap_service.get_email_detail_imap(
                account["email"],
                account["client_id"],
                account["refresh_token"],
                latest_email.get("id"),
                "inbox",
            )
        except Exception:
            pass

    # 构建邮件对象用于提取
    email_obj = {
        "subject": latest_email.get("subject", ""),
        "body_preview": latest_email.get("bodyPreview", "") or latest_email.get("body_preview", ""),
    }

    if email_detail:
        # Graph API 格式
        if "body" in email_detail:
            body_content = email_detail.get("body", {})
            email_obj["body"] = body_content.get("content", "") if body_content.get("contentType") == "text" else ""
            email_obj["body_html"] = body_content.get("content", "") if body_content.get("contentType") == "html" else ""
            email_obj["bodyContent"] = body_content.get("content", "")
            email_obj["bodyContentType"] = body_content.get("contentType", "text")
        # IMAP 格式
        elif "body" in email_detail or "body_html" in email_detail:
            email_obj["body"] = email_detail.get("body", "")
            email_obj["body_html"] = email_detail.get("body_html", "")

    try:
        # 尝试从邮件详情提取验证信息
        result = extract_verification_info(email_obj)
        matched_folder = latest_email.get("folder", "inbox")
        received_at = latest_email.get("receivedDateTime", "") or latest_email.get("date", "")
        sender = latest_email.get("from", {})
        if isinstance(sender, dict):
            sender = sender.get("emailAddress", {}).get("address", "") or sender.get("address", "") or ""

        account_summary = compact_summary_service.update_summary_from_verification(
            int(account["id"]),
            message=latest_email,
            verification_code=str(result.get("verification_code") or ""),
            folder=matched_folder,
        )
        result.update(
            {
                "email": email_addr,
                "subject": latest_email.get("subject", ""),
                "from": sender or latest_email.get("from_address", ""),
                "received_at": received_at,
                "folder": matched_folder,
            }
        )

        return jsonify({"success": True, "data": result, "message": "提取成功", "account_summary": account_summary})

    except ValueError as e:
        # 未找到验证信息
        error_payload = build_error_payload(
            "VERIFICATION_NOT_FOUND",
            str(e),
            "NotFoundError",
            404,
            f"email={email_addr}",
        )
        return jsonify({"success": False, "error": error_payload}), 404

    except Exception as e:
        # 其他错误
        error_payload = build_error_payload("EXTRACT_ERROR", "提取失败", "ExtractError", 500, str(e))
        return jsonify({"success": False, "error": error_payload}), 500


# ==================== External Emails API ====================


def _parse_external_common_args(*, default_since_minutes: int | None = None) -> dict:
    """解析 external API 通用 query 参数（按 TDD-00008 做基础校验）。"""
    claim_token = (request.args.get("claim_token") or "").strip()
    email_addr = (request.args.get("email") or "").strip()
    scope = external_api_service.resolve_external_mail_scope(
        email_addr=email_addr or None,
        claim_token=claim_token or None,
    )
    resolved_email = scope["email"]
    claim_context = scope.get("claim_context")
    baseline_timestamp = external_api_service.claimed_at_to_timestamp(scope.get("claimed_at"))

    folder = (request.args.get("folder") or "inbox").strip().lower() or "inbox"
    if folder not in {"inbox", "junkemail", "deleteditems"}:
        raise external_api_service.InvalidParamError("folder 参数无效")

    def _int_arg(name: str, default: int) -> int:
        raw = request.args.get(name, None)
        if raw is None or raw == "":
            return default
        try:
            return int(raw)
        except Exception as exc:
            raise external_api_service.InvalidParamError(f"{name} 参数无效") from exc

    skip = _int_arg("skip", 0)
    top = _int_arg("top", 20)
    if skip < 0:
        raise external_api_service.InvalidParamError("skip 参数无效")
    if top < 1 or top > 50:
        raise external_api_service.InvalidParamError("top 参数无效")

    since_minutes_raw = request.args.get("since_minutes", None)
    since_minutes = default_since_minutes
    if since_minutes_raw not in (None, ""):
        try:
            since_minutes = int(since_minutes_raw)
        except Exception as exc:
            raise external_api_service.InvalidParamError("since_minutes 参数无效") from exc
        if since_minutes < 1:
            raise external_api_service.InvalidParamError("since_minutes 参数无效")

    return {
        "email": resolved_email,
        "claim_token": claim_token,
        "claim_context": claim_context,
        "baseline_timestamp": baseline_timestamp,
        "folder": folder,
        "skip": skip,
        "top": top,
        "from_contains": (request.args.get("from_contains") or "").strip(),
        "subject_contains": (request.args.get("subject_contains") or "").strip(),
        "since_minutes": since_minutes,
    }


def _resolve_external_error(
    exc: external_api_service.ExternalApiError, *, allow_nested_upstream: bool = False
) -> dict[str, Any]:
    resolved_code = str(exc.code)
    resolved_message = str(exc.message)
    resolved_status = int(exc.status)

    nested_error = exc.data if isinstance(exc.data, dict) else None
    if allow_nested_upstream and isinstance(exc, external_api_service.UpstreamReadFailedError) and nested_error:
        nested_code = str(nested_error.get("code") or "").strip().upper()
        if nested_code in _EXTERNAL_NESTED_UPSTREAM_CODES:
            resolved_code = nested_code
            resolved_message = str(nested_error.get("message") or exc.message)
            try:
                resolved_status = int(nested_error.get("status") or exc.status)
            except Exception:
                resolved_status = int(exc.status)

    return {
        "code": resolved_code,
        "message": resolved_message,
        "status": resolved_status,
        "data": exc.data,
    }


def _external_error_response(exc: external_api_service.ExternalApiError, *, allow_nested_upstream: bool = False):
    resolved = _resolve_external_error(exc, allow_nested_upstream=allow_nested_upstream)
    return jsonify(external_api_service.fail(resolved["code"], resolved["message"], data=resolved["data"])), resolved["status"]


@api_key_required
@external_api_guards()
def api_external_get_messages() -> Any:
    try:
        args = _parse_external_common_args()
        emails, method = external_api_service.list_messages_for_external(
            email_addr=args["email"],
            folder=args["folder"],
            skip=args["skip"],
            top=args["top"],
        )
        filtered = external_api_service.filter_messages(
            emails,
            from_contains=args["from_contains"],
            subject_contains=args["subject_contains"],
            since_minutes=args["since_minutes"],
            baseline_timestamp=args["baseline_timestamp"],
        )

        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=args["email"] or "",
            endpoint="/api/external/messages",
            status="ok",
            details={"method": method, "count": len(filtered)},
        )

        return jsonify(external_api_service.ok({"emails": filtered, "count": len(filtered), "has_more": False}))
    except external_api_service.ExternalApiError as exc:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=(request.args.get("email") or "").strip(),
            endpoint="/api/external/messages",
            status="error",
            details={"code": exc.code},
        )
        return _external_error_response(exc)
    except Exception as exc:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=(request.args.get("email") or "").strip(),
            endpoint="/api/external/messages",
            status="error",
            details={"code": "INTERNAL_ERROR", "err": type(exc).__name__},
        )
        return jsonify(external_api_service.fail("INTERNAL_ERROR", "服务内部错误")), 500


@api_key_required
@external_api_guards()
def api_external_get_latest_message() -> Any:
    try:
        args = _parse_external_common_args()
        latest = external_api_service.get_latest_message_for_external(
            email_addr=args["email"],
            folder=args["folder"],
            from_contains=args["from_contains"],
            subject_contains=args["subject_contains"],
            since_minutes=args["since_minutes"],
            baseline_timestamp=args["baseline_timestamp"],
        )
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=args["email"] or "",
            endpoint="/api/external/messages/latest",
            status="ok",
            details={"method": latest.get("method")},
        )
        return jsonify(external_api_service.ok(latest))
    except external_api_service.ExternalApiError as exc:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=(request.args.get("email") or "").strip(),
            endpoint="/api/external/messages/latest",
            status="error",
            details={"code": exc.code},
        )
        return _external_error_response(exc)
    except Exception as exc:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=(request.args.get("email") or "").strip(),
            endpoint="/api/external/messages/latest",
            status="error",
            details={"code": "INTERNAL_ERROR", "err": type(exc).__name__},
        )
        return jsonify(external_api_service.fail("INTERNAL_ERROR", "服务内部错误")), 500


@api_key_required
@external_api_guards()
def api_external_get_message_detail(message_id: str) -> Any:
    try:
        args = _parse_external_common_args()
        detail = external_api_service.get_message_detail_for_external(
            email_addr=args["email"],
            message_id=message_id,
            folder=args["folder"],
        )
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=args["email"] or "",
            endpoint="/api/external/messages/{message_id}",
            status="ok",
            details={"method": detail.get("method")},
        )
        return jsonify(external_api_service.ok(detail))
    except external_api_service.ExternalApiError as exc:
        resolved = _resolve_external_error(exc, allow_nested_upstream=True)
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=(request.args.get("email") or "").strip(),
            endpoint="/api/external/messages/{message_id}",
            status="error",
            details={"code": resolved["code"]},
        )
        return _external_error_response(exc, allow_nested_upstream=True)
    except Exception as exc:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=(request.args.get("email") or "").strip(),
            endpoint="/api/external/messages/{message_id}",
            status="error",
            details={"code": "INTERNAL_ERROR", "err": type(exc).__name__},
        )
        return jsonify(external_api_service.fail("INTERNAL_ERROR", "服务内部错误")), 500


@api_key_required
@external_api_guards(feature="raw_content")
def api_external_get_message_raw(message_id: str) -> Any:
    try:
        args = _parse_external_common_args()
        detail = external_api_service.get_message_detail_for_external(
            email_addr=args["email"],
            message_id=message_id,
            folder=args["folder"],
        )
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=args["email"] or "",
            endpoint="/api/external/messages/{message_id}/raw",
            status="ok",
            details={"method": detail.get("method")},
        )
        return jsonify(
            external_api_service.ok(
                {
                    "id": message_id,
                    "email_address": args["email"],
                    "raw_content": detail.get("raw_content", ""),
                    "method": detail.get("method", ""),
                }
            )
        )
    except external_api_service.ExternalApiError as exc:
        resolved = _resolve_external_error(exc, allow_nested_upstream=True)
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=(request.args.get("email") or "").strip(),
            endpoint="/api/external/messages/{message_id}/raw",
            status="error",
            details={"code": resolved["code"]},
        )
        return _external_error_response(exc, allow_nested_upstream=True)
    except Exception as exc:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=(request.args.get("email") or "").strip(),
            endpoint="/api/external/messages/{message_id}/raw",
            status="error",
            details={"code": "INTERNAL_ERROR", "err": type(exc).__name__},
        )
        return jsonify(external_api_service.fail("INTERNAL_ERROR", "服务内部错误")), 500


@api_key_required
@external_api_guards()
def api_external_get_verification_code() -> Any:
    try:
        args = _parse_external_common_args(default_since_minutes=10)
        code_length = (request.args.get("code_length") or "").strip() or None
        code_regex = (request.args.get("code_regex") or "").strip() or None
        code_source = (request.args.get("code_source") or "all").strip().lower()
        if code_source not in {"subject", "content", "html", "all"}:
            raise external_api_service.InvalidParamError("code_source 参数无效")

        result = external_api_service.get_verification_result(
            email_addr=args["email"],
            folder=args["folder"],
            from_contains=args["from_contains"],
            subject_contains=args["subject_contains"],
            since_minutes=args["since_minutes"],
            baseline_timestamp=args["baseline_timestamp"],
            claim_token=args["claim_token"] or None,
            code_regex=code_regex,
            code_length=code_length,
            code_source=code_source,
        )
        if not result.get("verification_code"):
            raise external_api_service.VerificationCodeNotFoundError("未找到符合条件的验证码邮件")

        external_api_service.record_claim_read_context(
            claim_token=args["claim_token"] or None,
            action="claim",
            payload={
                "last_read_action": "verification-code",
                "matched_email_id": result.get("matched_email_id"),
                "received_at": result.get("received_at"),
            },
        )

        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=args["email"] or "",
            endpoint="/api/external/verification-code",
            status="ok",
            details={"matched_email_id": result.get("matched_email_id"), "method": result.get("method")},
        )
        return jsonify(external_api_service.ok(result))
    except external_api_service.ExternalApiError as exc:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=(request.args.get("email") or "").strip(),
            endpoint="/api/external/verification-code",
            status="error",
            details={"code": exc.code},
        )
        return _external_error_response(exc)
    except ValueError:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=(request.args.get("email") or "").strip(),
            endpoint="/api/external/verification-code",
            status="error",
            details={"code": "INVALID_PARAM"},
        )
        return jsonify(external_api_service.fail("INVALID_PARAM", "参数错误")), 400
    except Exception:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=(request.args.get("email") or "").strip(),
            endpoint="/api/external/verification-code",
            status="error",
            details={"code": "INTERNAL_ERROR"},
        )
        return jsonify(external_api_service.fail("INTERNAL_ERROR", "服务内部错误")), 500


@api_key_required
@external_api_guards()
def api_external_get_verification_link() -> Any:
    try:
        args = _parse_external_common_args(default_since_minutes=10)
        result = external_api_service.get_verification_result(
            email_addr=args["email"],
            folder=args["folder"],
            from_contains=args["from_contains"],
            subject_contains=args["subject_contains"],
            since_minutes=args["since_minutes"],
            baseline_timestamp=args["baseline_timestamp"],
            claim_token=args["claim_token"] or None,
        )
        if not result.get("verification_link"):
            raise external_api_service.VerificationLinkNotFoundError("未找到符合条件的验证链接邮件")

        external_api_service.record_claim_read_context(
            claim_token=args["claim_token"] or None,
            action="claim",
            payload={
                "last_read_action": "verification-link",
                "matched_email_id": result.get("matched_email_id"),
                "received_at": result.get("received_at"),
            },
        )

        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=args["email"] or "",
            endpoint="/api/external/verification-link",
            status="ok",
            details={"matched_email_id": result.get("matched_email_id"), "method": result.get("method")},
        )
        return jsonify(external_api_service.ok(result))
    except external_api_service.ExternalApiError as exc:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=(request.args.get("email") or "").strip(),
            endpoint="/api/external/verification-link",
            status="error",
            details={"code": exc.code},
        )
        return _external_error_response(exc)
    except Exception:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=(request.args.get("email") or "").strip(),
            endpoint="/api/external/verification-link",
            status="error",
            details={"code": "INTERNAL_ERROR"},
        )
        return jsonify(external_api_service.fail("INTERNAL_ERROR", "服务内部错误")), 500


@api_key_required
@external_api_guards(feature="wait_message")
def api_external_wait_message() -> Any:
    try:
        args = _parse_external_common_args()
        timeout_seconds = request.args.get("timeout_seconds", "30")
        poll_interval = request.args.get("poll_interval", "5")
        mode = request.args.get("mode", "sync").lower()

        if mode == "async":
            # P2 异步模式：创建探测请求，立即返回 probe_id
            probe_result = external_api_service.create_probe(
                email_addr=args["email"],
                timeout_seconds=int(timeout_seconds),
                poll_interval=int(poll_interval),
                folder=args["folder"],
                from_contains=args["from_contains"],
                subject_contains=args["subject_contains"],
                since_minutes=args["since_minutes"],
                baseline_timestamp=args["baseline_timestamp"],
                claim_token=args["claim_token"] or None,
            )
            external_api_service.audit_external_api_access(
                action="external_api_access",
                email_addr=args["email"] or "",
                endpoint="/api/external/wait-message?mode=async",
                status="ok",
                details={"probe_id": probe_result["probe_id"]},
            )
            return jsonify(external_api_service.ok(probe_result)), 202
        else:
            # P0 同步模式：阻塞等待（向下兼容）
            result = external_api_service.wait_for_message(
                email_addr=args["email"],
                timeout_seconds=int(timeout_seconds),
                poll_interval=int(poll_interval),
                folder=args["folder"],
                from_contains=args["from_contains"],
                subject_contains=args["subject_contains"],
                since_minutes=args["since_minutes"],
                baseline_timestamp=args["baseline_timestamp"],
                claim_token=args["claim_token"] or None,
            )
            external_api_service.record_claim_read_context(
                claim_token=args["claim_token"] or None,
                action="claim",
                payload={
                    "last_read_action": "wait-message",
                    "matched_email_id": result.get("id"),
                    "received_at": result.get("created_at"),
                },
            )
            external_api_service.audit_external_api_access(
                action="external_api_access",
                email_addr=args["email"] or "",
                endpoint="/api/external/wait-message",
                status="ok",
                details={"matched_email_id": result.get("id"), "method": result.get("method")},
            )
            return jsonify(external_api_service.ok(result))
    except external_api_service.ExternalApiError as exc:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=(request.args.get("email") or "").strip(),
            endpoint="/api/external/wait-message",
            status="error",
            details={"code": exc.code},
        )
        return _external_error_response(exc)
    except Exception as exc:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=(request.args.get("email") or "").strip(),
            endpoint="/api/external/wait-message",
            status="error",
            details={"code": "INTERNAL_ERROR", "err": type(exc).__name__},
        )
        return jsonify(external_api_service.fail("INTERNAL_ERROR", "服务内部错误")), 500


@api_key_required
@external_api_guards()
def api_external_get_probe_status(probe_id: str) -> Any:
    """P2: 查询异步探测状态与结果"""
    try:
        result = external_api_service.get_probe_status(probe_id)
        external_api_service.ensure_external_email_access(result.get("email") or "")
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr=result.get("email") or "",
            endpoint="/api/external/probe/{probe_id}",
            status="ok",
            details={"probe_id": probe_id, "probe_status": result.get("status")},
        )
        return jsonify(external_api_service.ok(result))
    except external_api_service.ExternalApiError as exc:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr="",
            endpoint="/api/external/probe/{probe_id}",
            status="error",
            details={"code": exc.code, "probe_id": probe_id},
        )
        return _external_error_response(exc)
    except Exception:
        external_api_service.audit_external_api_access(
            action="external_api_access",
            email_addr="",
            endpoint="/api/external/probe/{probe_id}",
            status="error",
            details={"code": "INTERNAL_ERROR", "probe_id": probe_id},
        )
        return jsonify(external_api_service.fail("INTERNAL_ERROR", "服务内部错误")), 500
