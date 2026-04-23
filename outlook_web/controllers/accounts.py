from __future__ import annotations

import html
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from flask import Response, g, jsonify, request

from outlook_web import config
from outlook_web.audit import log_audit
from outlook_web.db import get_db
from outlook_web.errors import (
    build_error_payload,
    build_error_response,
    build_export_verify_failure_response,
)
from outlook_web.repositories import accounts as accounts_repo
from outlook_web.repositories import groups as groups_repo
from outlook_web.repositories import refresh_logs as refresh_logs_repo
from outlook_web.repositories import settings as settings_repo
from outlook_web.repositories import tags as tags_repo
from outlook_web.repositories.distributed_locks import (
    acquire_distributed_lock,
    release_distributed_lock,
)
from outlook_web.repositories.refresh_runs import create_refresh_run, finish_refresh_run
from outlook_web.security.auth import get_client_ip, get_user_agent, login_required
from outlook_web.security.crypto import decrypt_data
from outlook_web.services import graph as graph_service
from outlook_web.services import refresh as refresh_service


def sanitize_input(text: str, max_length: int = 500) -> str:
    """
    净化用户输入，防止XSS攻击
    - 转义HTML特殊字符
    - 限制长度
    - 移除控制字符
    """
    if not text:
        return ""

    # 限制长度
    text = text[:max_length]

    # 移除控制字符（保留换行和制表符）
    text = "".join(char for char in text if char.isprintable() or char in "\n\t")

    # 转义HTML特殊字符
    text = html.escape(text, quote=True)

    return text


def _parse_bool_flag(value: Any, default: bool = False) -> bool:
    """解析请求中的布尔开关，兼容 bool / 数字 / 字符串。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_account_status(status: Any) -> Optional[str]:
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in {"active", "inactive", "disabled"}:
        return None
    return normalized_status


def _build_account_import_failure_response(
    message: str,
    *,
    summary: dict[str, Any],
    errors: list[dict[str, Any]],
):
    return build_error_response(
        "ACCOUNT_IMPORT_FAILED",
        message,
        message_en="Account import failed",
        status=400,
        extra={"summary": summary, "errors": errors},
    )


def _parse_imap_port(value: Any) -> int | None:
    try:
        port = int((value or "").strip() if isinstance(value, str) else value)
    except Exception:
        return None
    return port if 1 <= port <= 65535 else None


def _looks_like_imap_host(value: str) -> bool:
    text = (value or "").strip().lower()
    return bool(text and "." in text and "@" not in text and " " not in text)


def _is_outlook_basic_auth_target(email_addr: str, host: str = "", provider_key: str = "") -> bool:
    from outlook_web.services.providers import infer_provider_from_email

    inferred_provider = infer_provider_from_email(email_addr)
    normalized_host = (host or "").strip().lower()
    normalized_provider = (provider_key or "").strip().lower()
    return (
        inferred_provider == "outlook"
        or normalized_provider == "outlook"
        or normalized_host in {"outlook.live.com", "outlook.office365.com"}
    )


def _outlook_basic_auth_import_error() -> str:
    return "Outlook 邮箱不支持 IMAP Basic Auth 直连（包括 custom host 导入），请使用 4 段 OAuth 格式：邮箱----密码----client_id----refresh_token"


# ==================== 账号基础 CRUD API ====================


@login_required
def api_get_accounts() -> Any:
    """获取所有账号"""
    group_id = request.args.get("group_id", type=int)
    accounts = accounts_repo.load_accounts(group_id)

    # 获取每个账号的最后刷新状态（批量查询，避免 N+1）
    db = get_db()
    last_log_by_account: Dict[int, Dict[str, Any]] = {}
    try:
        account_ids = [int(a.get("id")) for a in accounts if a.get("id") is not None]
    except Exception:
        account_ids = []

    if account_ids:
        try:
            placeholders = ",".join(["?"] * len(account_ids))
            rows = db.execute(
                f"""
                SELECT l.account_id, l.status, l.error_message, l.created_at
                FROM account_refresh_logs l
                JOIN (
                    SELECT account_id, MAX(id) as max_id
                    FROM account_refresh_logs
                    WHERE account_id IN ({placeholders})
                    GROUP BY account_id
                ) latest
                ON l.account_id = latest.account_id AND l.id = latest.max_id
            """,
                account_ids,
            ).fetchall()
            for r in rows:
                try:
                    last_log_by_account[int(r["account_id"])] = dict(r)
                except Exception:
                    continue
        except Exception:
            last_log_by_account = {}

    # 返回时隐藏敏感信息
    safe_accounts = []
    for acc in accounts:
        acc_id = acc.get("id")
        try:
            acc_id_int = int(acc_id)
        except Exception:
            acc_id_int = None
        last_refresh_log = last_log_by_account.get(acc_id_int) if acc_id_int is not None else None

        safe_accounts.append(
            {
                "id": acc["id"],
                "email": acc["email"],
                "account_type": acc.get("account_type") or "outlook",
                "provider": acc.get("provider") or "outlook",
                "client_id": (acc["client_id"][:8] + "..." if len(acc["client_id"]) > 8 else acc["client_id"]),
                "group_id": acc.get("group_id"),
                "group_name": acc.get("group_name", "默认分组"),
                "group_color": acc.get("group_color", "#666666"),
                "remark": acc.get("remark", ""),
                "status": acc.get("status", "active"),
                "last_refresh_at": acc.get("last_refresh_at", ""),
                "last_refresh_status": (last_refresh_log.get("status") if last_refresh_log else None),
                "last_refresh_error": (last_refresh_log.get("error_message") if last_refresh_log else None),
                "created_at": acc.get("created_at", ""),
                "updated_at": acc.get("updated_at", ""),
                "tags": acc.get("tags", []),
                "telegram_push_enabled": bool(acc.get("telegram_push_enabled")),
                "notification_enabled": bool(acc.get("telegram_push_enabled")),
                "latest_email_subject": acc.get("latest_email_subject", ""),
                "latest_email_from": acc.get("latest_email_from", ""),
                "latest_email_folder": acc.get("latest_email_folder", ""),
                "latest_email_received_at": acc.get("latest_email_received_at", ""),
                "latest_verification_code": acc.get("latest_verification_code", ""),
                "latest_verification_folder": acc.get("latest_verification_folder", ""),
                "latest_verification_received_at": acc.get("latest_verification_received_at", ""),
            }
        )
    return jsonify({"success": True, "accounts": safe_accounts})


@login_required
def api_get_account(account_id: int) -> Any:
    """获取单个账号详情"""
    account = accounts_repo.get_account_by_id(account_id)
    if not account:
        return build_error_response(
            "ACCOUNT_NOT_FOUND",
            "账号不存在",
            message_en="Account not found",
            status=404,
        )

    return jsonify(
        {
            "success": True,
            "account": {
                "id": account["id"],
                "email": account["email"],
                # 敏感字段默认不回显（避免泄露）；如需查看请走"导出+二次验证"
                "password": "",
                "client_id": account["client_id"],
                "refresh_token": "",
                "has_password": bool(account.get("password")),
                "has_refresh_token": bool(account.get("refresh_token")),
                "group_id": account.get("group_id"),
                "group_name": account.get("group_name", "默认分组"),
                "remark": account.get("remark", ""),
                "status": account.get("status", "active"),
                "account_type": account.get("account_type") or "outlook",
                "provider": account.get("provider") or "outlook",
                "telegram_push_enabled": bool(account.get("telegram_push_enabled")),
                "notification_enabled": bool(account.get("telegram_push_enabled")),
                "latest_email_subject": account.get("latest_email_subject", ""),
                "latest_email_from": account.get("latest_email_from", ""),
                "latest_email_folder": account.get("latest_email_folder", ""),
                "latest_email_received_at": account.get("latest_email_received_at", ""),
                "latest_verification_code": account.get("latest_verification_code", ""),
                "latest_verification_folder": account.get("latest_verification_folder", ""),
                "latest_verification_received_at": account.get("latest_verification_received_at", ""),
                "created_at": account.get("created_at", ""),
                "updated_at": account.get("updated_at", ""),
            },
        }
    )


@login_required
def api_add_account() -> Any:
    """添加账号"""
    data = request.json or {}
    account_str = data.get("account_string", "")
    group_id = data.get("group_id", 1)
    provider = (data.get("provider") or "outlook").strip().lower()
    custom_imap_host = (data.get("imap_host") or "").strip()
    custom_imap_port = data.get("imap_port")
    add_to_pool = _parse_bool_flag(data.get("add_to_pool"), default=False)

    if not account_str:
        return build_error_response(
            "ACCOUNT_IMPORT_INPUT_REQUIRED",
            "请输入账号信息",
            message_en="Please enter account information",
        )

    # FD-00006: auto 模式允许 group_id=null（自动分组），需在分组校验前分流
    if provider == "auto":
        return _handle_auto_import(data, add_to_pool=add_to_pool)

    # 校验分组
    target_group = groups_repo.get_group_by_id(group_id)
    if not target_group:
        return build_error_response("GROUP_NOT_FOUND", "分组不存在", message_en="Group not found", status=404)
    if target_group.get("is_system"):
        return build_error_response(
            "SYSTEM_GROUP_PROTECTED",
            "不能导入到系统分组",
            message_en="Cannot import accounts into a system group",
            status=403,
        )

    def sanitize_credential_field(value: Any, max_length: int) -> str:
        if value is None:
            return ""
        text = str(value)
        text = text.replace("\r", "").replace("\n", "").replace("\t", "")
        text = text.strip()
        if len(text) > max_length:
            text = text[:max_length]
        # 移除不可见控制字符
        text = "".join(ch for ch in text if ch.isprintable())
        return text

    def parse_account_string(line: str) -> Optional[Dict[str, str]]:
        """解析账号字符串（格式：email----password----client_id----refresh_token）"""
        parts = line.strip().split("----")
        if len(parts) >= 4:
            return {
                "email": parts[0].strip(),
                "password": parts[1],
                "client_id": parts[2].strip(),
                # refresh_token 可能包含 '----'，这里把剩余部分合并回去
                "refresh_token": "----".join(parts[3:]).strip(),
            }
        return None

    def is_comment_line(line: str) -> bool:
        return bool(line) and line.lstrip().startswith("#")

    # 支持批量导入（多行）+ 逐行校验与错误定位
    raw_lines = account_str.splitlines()
    imported = 0
    failed = 0
    errors: List[Dict[str, Any]] = []
    errors_total = 0
    max_error_details = 50

    db = get_db()

    # -------------------- IMAP provider 导入分支 --------------------
    # 对齐：PRD-00005 / FD-00005 / TDD-00005
    # 约束：不改动 Outlook 旧格式；IMAP 账号使用 client_id/refresh_token 空字符串占位（DB NOT NULL 约束不变）。
    if provider and provider != "outlook":
        from outlook_web.services.providers import MAIL_PROVIDERS

        provider_cfg = MAIL_PROVIDERS.get(provider, {})
        default_imap_host = (provider_cfg.get("imap_host") or "").strip()
        default_imap_port = int(provider_cfg.get("imap_port") or 993)

        # custom 可从 request body 提供全局 host/port（兼容前端“自定义 IMAP 配置”输入）
        if provider == "custom":
            if custom_imap_port is None or str(custom_imap_port).strip() == "":
                custom_port_val = 993
            else:
                custom_port_val = _parse_imap_port(custom_imap_port)
                if custom_port_val is None:
                    return build_error_response(
                        "INVALID_PARAM",
                        "自定义 IMAP 端口无效，应为 1-65535",
                        message_en="Custom IMAP port is invalid. Expected 1-65535",
                        status=400,
                    )
        else:
            custom_port_val = None

        for line_no, raw in enumerate(raw_lines, start=1):
            line = (raw or "").strip()
            if not line or is_comment_line(line):
                continue

            parts = [p.strip() for p in line.split("----")]
            email_addr = sanitize_credential_field(parts[0] if len(parts) > 0 else "", 320)
            imap_pwd = sanitize_credential_field(parts[1] if len(parts) > 1 else "", 500)

            if len(parts) < 2 or not email_addr or not imap_pwd:
                failed += 1
                errors_total += 1
                if len(errors) < max_error_details:
                    errors.append(
                        {
                            "line": line_no,
                            "email": email_addr,
                            "error": "格式错误，应为：邮箱----IMAP授权码/应用密码（custom 可包含 host/port）",
                        }
                    )
                continue

            # 基础邮箱格式校验
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email_addr):
                failed += 1
                errors_total += 1
                if len(errors) < max_error_details:
                    errors.append(
                        {
                            "line": line_no,
                            "email": email_addr,
                            "error": "邮箱格式不正确",
                        }
                    )
                continue

            imap_host = default_imap_host
            imap_port = default_imap_port

            if provider == "custom":
                # 兼容两类输入：
                # 1) 5 段（导出格式）：email----imap_password----custom----imap_host----imap_port
                # 2) 4 段（文本批量）：email----imap_password----imap_host----imap_port
                # 3) 2 段（配合输入框）：email----imap_password（host/port 从 request body 取）
                if len(parts) >= 5 and (parts[2] or "").strip().lower() == "custom":
                    imap_host = (parts[3] or "").strip()
                    raw_port = (parts[4] or "").strip()
                    if not raw_port:
                        failed += 1
                        errors_total += 1
                        if len(errors) < max_error_details:
                            errors.append(
                                {
                                    "line": line_no,
                                    "email": email_addr,
                                    "error": "custom 5段格式缺少 IMAP 端口",
                                }
                            )
                        continue
                    imap_port = _parse_imap_port(raw_port)
                    if imap_port is None:
                        failed += 1
                        errors_total += 1
                        if len(errors) < max_error_details:
                            errors.append(
                                {
                                    "line": line_no,
                                    "email": email_addr,
                                    "error": "custom IMAP 端口无效，应为 1-65535",
                                }
                            )
                        continue
                elif len(parts) >= 4:
                    imap_host = (parts[2] or "").strip()
                    raw_port = (parts[3] or "").strip()
                    if not raw_port:
                        failed += 1
                        errors_total += 1
                        if len(errors) < max_error_details:
                            errors.append(
                                {
                                    "line": line_no,
                                    "email": email_addr,
                                    "error": "custom 4段格式缺少 IMAP 端口",
                                }
                            )
                        continue
                    imap_port = _parse_imap_port(raw_port)
                    if imap_port is None:
                        failed += 1
                        errors_total += 1
                        if len(errors) < max_error_details:
                            errors.append(
                                {
                                    "line": line_no,
                                    "email": email_addr,
                                    "error": "custom IMAP 端口无效，应为 1-65535",
                                }
                            )
                        continue
                else:
                    imap_host = custom_imap_host
                    imap_port = custom_port_val if custom_port_val is not None else 993

                if not imap_host:
                    failed += 1
                    errors_total += 1
                    if len(errors) < max_error_details:
                        errors.append(
                            {
                                "line": line_no,
                                "email": email_addr,
                                "error": "自定义 IMAP 必须提供服务器地址（imap_host）",
                            }
                        )
                    continue
            else:
                # 兼容导出格式：email----imap_password----provider
                if len(parts) >= 3:
                    line_provider = (parts[2] or "").strip().lower()
                    if line_provider and line_provider != provider:
                        # 明确不一致：提示用户切换 provider 或修正文本
                        failed += 1
                        errors_total += 1
                        if len(errors) < max_error_details:
                            errors.append(
                                {
                                    "line": line_no,
                                    "email": email_addr,
                                    "error": f"provider 不匹配：当前选择 {provider}，文本为 {line_provider}",
                                }
                            )
                        continue

                if not imap_host:
                    failed += 1
                    errors_total += 1
                    if len(errors) < max_error_details:
                        errors.append(
                            {
                                "line": line_no,
                                "email": email_addr,
                                "error": "未找到该 provider 的默认 IMAP 配置，请使用自定义 IMAP",
                            }
                        )
                    continue

            if _is_outlook_basic_auth_target(email_addr, imap_host, provider):
                failed += 1
                errors_total += 1
                if len(errors) < max_error_details:
                    errors.append(
                        {
                            "line": line_no,
                            "email": email_addr,
                            "error": _outlook_basic_auth_import_error(),
                        }
                    )
                continue

            ok = accounts_repo.add_account(
                email_addr,
                password="",
                client_id="",
                refresh_token="",
                group_id=group_id,
                remark="",
                account_type="imap",
                provider=provider,
                imap_host=imap_host,
                imap_port=imap_port,
                imap_password=imap_pwd,
                add_to_pool=add_to_pool,
                db=db,
                commit=False,
            )
            if ok:
                imported += 1
                continue

            failed += 1
            errors_total += 1
            reason = "写入失败"
            try:
                exists = db.execute("SELECT 1 FROM accounts WHERE email = ? LIMIT 1", (email_addr,)).fetchone()
                if exists:
                    reason = "邮箱已存在"
            except Exception:
                pass
            if len(errors) < max_error_details:
                errors.append({"line": line_no, "email": email_addr, "error": reason})

        summary = {
            "group_id": group_id,
            "total_lines": len(raw_lines),
            "imported": imported,
            "failed": failed,
            "errors_total": errors_total,
            "errors_returned": len(errors),
            "errors_truncated": errors_total > len(errors),
        }

        message = f"导入完成：成功 {imported} 个，失败 {failed} 个"

        if imported > 0:
            try:
                db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
                return build_error_response(
                    "ACCOUNT_IMPORT_DB_WRITE_FAILED",
                    "数据库写入失败，请重试",
                    message_en="Database write failed. Please try again",
                    status=500,
                )
            log_audit(
                "import",
                "account",
                None,
                f"{message}，目标分组ID={group_id}，provider={provider}",
            )
            return jsonify(
                {
                    "success": True,
                    "message": message,
                    "summary": summary,
                    "errors": errors,
                }
            )

        return _build_account_import_failure_response(message, summary=summary, errors=errors)

    # -------------------- Outlook（旧格式）导入分支：保持现有逻辑完全不动 --------------------
    for line_no, raw in enumerate(raw_lines, start=1):
        line = (raw or "").strip()
        if not line:
            continue
        if is_comment_line(line):
            continue

        parsed = parse_account_string(line)
        if not parsed:
            failed += 1
            errors_total += 1
            if len(errors) < max_error_details:
                errors.append(
                    {
                        "line": line_no,
                        "error": "格式错误，应为：邮箱----密码----client_id----refresh_token",
                    }
                )
            continue

        email_addr = sanitize_credential_field(parsed.get("email"), 320)
        password = sanitize_credential_field(parsed.get("password"), 500)
        client_id = sanitize_credential_field(parsed.get("client_id"), 200)
        refresh_token = sanitize_credential_field(parsed.get("refresh_token"), 4096)

        if not email_addr or not client_id or not refresh_token:
            failed += 1
            errors_total += 1
            if len(errors) < max_error_details:
                errors.append(
                    {
                        "line": line_no,
                        "email": email_addr,
                        "error": "邮箱、Client ID、Refresh Token 不能为空",
                    }
                )
            continue

        # 基础邮箱格式校验
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email_addr):
            failed += 1
            errors_total += 1
            if len(errors) < max_error_details:
                errors.append({"line": line_no, "email": email_addr, "error": "邮箱格式不正确"})
            continue

        ok = accounts_repo.add_account(
            email_addr,
            password,
            client_id,
            refresh_token,
            group_id,
            add_to_pool=add_to_pool,
            db=db,
            commit=False,
        )
        if ok:
            imported += 1
            continue

        failed += 1
        errors_total += 1
        reason = "写入失败"
        try:
            exists = db.execute("SELECT 1 FROM accounts WHERE email = ? LIMIT 1", (email_addr,)).fetchone()
            if exists:
                reason = "邮箱已存在"
        except Exception:
            pass
        if len(errors) < max_error_details:
            errors.append({"line": line_no, "email": email_addr, "error": reason})

    summary = {
        "group_id": group_id,
        "total_lines": len(raw_lines),
        "imported": imported,
        "failed": failed,
        "errors_total": errors_total,
        "errors_returned": len(errors),
        "errors_truncated": errors_total > len(errors),
    }

    message = f"导入完成：成功 {imported} 个，失败 {failed} 个"

    if imported > 0:
        try:
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            return build_error_response(
                "ACCOUNT_IMPORT_DB_WRITE_FAILED",
                "数据库写入失败，请重试",
                message_en="Database write failed. Please try again",
                status=500,
            )
        log_audit("import", "account", None, f"{message}，目标分组ID={group_id}")
        return jsonify({"success": True, "message": message, "summary": summary, "errors": errors})

    return _build_account_import_failure_response(message, summary=summary, errors=errors)


@login_required
def api_get_providers() -> Any:
    """返回邮箱提供商列表，用于前端下拉选择（PRD-00005 / TDD-00005）"""
    from outlook_web.services.providers import get_provider_list

    return jsonify({"success": True, "providers": get_provider_list()})


# ==================== Auto 混合导入 (FD-00006) ====================


def _detect_line_type(
    line: str,
    fallback_host: str = "",
    fallback_port: int = 993,
) -> Dict[str, Any]:
    """
    根据分隔后的段数和内容特征，自动判断一行账号的类型。
    返回 {"type", "provider", "fields", "error", "auto_group_name"}。
    """
    from outlook_web.services.providers import (
        KNOWN_PROVIDER_KEYS,
        MAIL_PROVIDERS,
        PROVIDER_GROUP_NAME,
        infer_provider_from_email,
    )

    parts = line.split("----")
    n = len(parts)

    def _err(msg: str) -> Dict[str, Any]:
        return {
            "type": "error",
            "provider": "",
            "fields": {},
            "error": msg,
            "auto_group_name": "",
        }

    # n >= 5 且 parts[2] == "custom" → 自定义 IMAP
    if n >= 5 and (parts[2] or "").strip().lower() == "custom":
        email = parts[0].strip()
        imap_pwd = parts[1].strip()
        host = (parts[3] or "").strip()
        raw_port = (parts[4] or "").strip()
        if not email or not imap_pwd or not host:
            return _err("custom 5段格式缺少必要字段")
        if not raw_port:
            return _err("custom 5段格式缺少 IMAP 端口")
        port = _parse_imap_port(raw_port)
        if port is None:
            return _err("custom IMAP 端口无效，应为 1-65535")
        if _is_outlook_basic_auth_target(email, host, "custom"):
            return _err(_outlook_basic_auth_import_error())
        return {
            "type": "imap",
            "provider": "custom",
            "fields": {
                "email": email,
                "imap_password": imap_pwd,
                "imap_host": host,
                "imap_port": port,
            },
            "error": None,
            "auto_group_name": PROVIDER_GROUP_NAME.get("custom", "自定义IMAP"),
        }

    if n == 4:
        email = parts[0].strip()
        imap_pwd = parts[1].strip()
        host = (parts[2] or "").strip()
        raw_port = (parts[3] or "").strip()
        if _looks_like_imap_host(host):
            if not email or not imap_pwd:
                return _err("4段格式缺少邮箱或密码")
            if not raw_port:
                return _err("custom 4段格式缺少 IMAP 端口")
            port = _parse_imap_port(raw_port)
            if port is None:
                return _err("custom IMAP 端口无效，应为 1-65535")
            if _is_outlook_basic_auth_target(email, host, "custom"):
                return _err(_outlook_basic_auth_import_error())
            return {
                "type": "imap",
                "provider": "custom",
                "fields": {
                    "email": email,
                    "imap_password": imap_pwd,
                    "imap_host": host,
                    "imap_port": port,
                },
                "error": None,
                "auto_group_name": PROVIDER_GROUP_NAME.get("custom", "自定义IMAP"),
            }

    # n >= 4 → Outlook（OAuth）
    if n >= 4:
        email = parts[0].strip()
        password = parts[1].strip()
        client_id = parts[2].strip()
        refresh_token = "----".join(parts[3:]).strip()
        if not email or not client_id or not refresh_token:
            return _err("Outlook 格式缺少 client_id 或 refresh_token")
        return {
            "type": "outlook",
            "provider": "outlook",
            "fields": {
                "email": email,
                "password": password,
                "client_id": client_id,
                "refresh_token": refresh_token,
            },
            "error": None,
            "auto_group_name": PROVIDER_GROUP_NAME.get("outlook", "Outlook"),
        }

    # n == 3 → 检查第3段是否为已知 provider
    if n == 3:
        email = parts[0].strip()
        imap_pwd = parts[1].strip()
        prov = (parts[2] or "").strip().lower()
        if not email or not imap_pwd:
            return _err("3段格式缺少邮箱或密码")
        if prov not in KNOWN_PROVIDER_KEYS:
            return _err(f"未知的 provider: {prov}")
        if prov == "outlook":
            return _err("Outlook 三段格式不支持密码直连，请使用 4 段 OAuth 格式：邮箱----密码----client_id----refresh_token")
        cfg = MAIL_PROVIDERS.get(prov, {})
        host = cfg.get("imap_host", "")
        port = int(cfg.get("imap_port", 993))
        if prov == "custom":
            return _err("3段格式不支持 custom（需要5段包含 host/port）")
        return {
            "type": "imap",
            "provider": prov,
            "fields": {
                "email": email,
                "imap_password": imap_pwd,
                "imap_host": host,
                "imap_port": port,
            },
            "error": None,
            "auto_group_name": PROVIDER_GROUP_NAME.get(prov, prov),
        }

    # n == 2 → 域名推断
    if n == 2:
        email = parts[0].strip()
        imap_pwd = parts[1].strip()
        if not email or not imap_pwd:
            return _err("2段格式缺少邮箱或密码")
        prov = infer_provider_from_email(email)
        if prov:
            if prov == "outlook":
                return _err(
                    "Outlook 两段格式不支持密码直连，请使用 4 段 OAuth 格式：邮箱----密码----client_id----refresh_token"
                )
            cfg = MAIL_PROVIDERS.get(prov, {})
            host = cfg.get("imap_host", "")
            port = int(cfg.get("imap_port", 993))
            return {
                "type": "imap",
                "provider": prov,
                "fields": {
                    "email": email,
                    "imap_password": imap_pwd,
                    "imap_host": host,
                    "imap_port": port,
                },
                "error": None,
                "auto_group_name": PROVIDER_GROUP_NAME.get(prov, prov),
            }
        # 推断失败 → custom 兜底
        if fallback_host:
            return {
                "type": "imap",
                "provider": "custom",
                "fields": {
                    "email": email,
                    "imap_password": imap_pwd,
                    "imap_host": fallback_host,
                    "imap_port": fallback_port,
                },
                "error": None,
                "auto_group_name": PROVIDER_GROUP_NAME.get("custom", "自定义IMAP"),
            }
        return _err("未知域名且未提供兜底 IMAP 服务器地址")

    # n == 1 → 临时邮箱
    if n == 1:
        email = parts[0].strip()
        if not email or "@" not in email:
            return _err("无法解析的行")
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            return _err("邮箱格式不正确")
        return {
            "type": "temp_mail",
            "provider": "temp_mail",
            "fields": {"email": email},
            "error": None,
            "auto_group_name": PROVIDER_GROUP_NAME.get("temp_mail", "临时邮箱"),
        }

    return _err("无法解析的行")


def _resolve_auto_group(
    provider: str,
    group_cache: Dict[str, int],
    groups_created: List[str],
) -> int:
    """根据 provider 查找或创建分组，使用缓存避免重复查询。"""
    from outlook_web.services.providers import PROVIDER_GROUP_NAME

    if provider in group_cache:
        return group_cache[provider]

    group_name = PROVIDER_GROUP_NAME.get(provider, provider)
    existing = groups_repo.get_group_by_name(group_name)
    if existing:
        group_cache[provider] = existing["id"]
        return existing["id"]

    new_id = groups_repo.add_group(group_name)
    if new_id:
        group_cache[provider] = new_id
        groups_created.append(group_name)
        return new_id

    # 创建失败时尝试再次查找（可能并发创建）
    existing = groups_repo.get_group_by_name(group_name)
    if existing:
        group_cache[provider] = existing["id"]
        return existing["id"]

    # 兜底：使用默认分组
    default_id = groups_repo.get_default_group_id()
    group_cache[provider] = default_id
    return default_id


def _overwrite_account(existing: Dict, detect_result: Dict, group_id: int, add_to_pool: bool = False) -> bool:
    """覆盖更新已存在账号的凭据字段，保留 remark/tags/status。"""
    fields: Dict[str, Any] = {"group_id": group_id}
    d = detect_result
    prov = d["provider"]
    f = d["fields"]

    if d["type"] == "outlook":
        fields["password"] = f.get("password", "")
        fields["client_id"] = f.get("client_id", "")
        fields["refresh_token"] = f.get("refresh_token", "")
        fields["account_type"] = "outlook"
        fields["provider"] = "outlook"
    elif d["type"] == "imap":
        fields["imap_password"] = f.get("imap_password", "")
        fields["imap_host"] = f.get("imap_host", "")
        fields["imap_port"] = f.get("imap_port", 993)
        fields["account_type"] = "imap"
        fields["provider"] = prov

    # 若勾选了"加入邮箱池"且该账号尚未处于 available 状态（含 NULL / claimed 等），则同步设置 pool_status
    if add_to_pool and existing.get("pool_status") != "available":
        fields["pool_status"] = "available"

    return accounts_repo.update_account_credentials(existing["id"], **fields)


def _handle_temp_mail_import(
    email: str,
    errors: List[Dict[str, Any]],
    line_num: int,
    temp_mail_count: int,
    max_temp_mail: int = 20,
) -> bool:
    """处理临时邮箱的导入，写入 temp_emails 表。"""
    from outlook_web.repositories import temp_emails as temp_emails_repo
    from outlook_web.services.temp_mail_service import (
        TEMP_MAIL_SOURCE,
        get_temp_mail_service,
    )

    if temp_mail_count >= max_temp_mail:
        errors.append(
            {
                "line": line_num,
                "email": email,
                "error": f"临时邮箱单次导入上限 {max_temp_mail} 个",
                "detected_type": "temp_mail",
            }
        )
        return False

    # 检查是否已存在
    existing = temp_emails_repo.get_temp_email_by_address(email)
    if existing:
        return True  # 已存在视为跳过（成功）

    # BUG-02: 严格导入（不做本地兜底写入）
    temp_mail_service = get_temp_mail_service()
    try:
        mailbox = temp_mail_service.import_user_mailbox(email, allow_local_fallback=False)
    except Exception as exc:
        errors.append(
            {
                "line": line_num,
                "email": email,
                "error": f"临时邮箱导入失败：{str(exc) or '上游探测失败'}",
                "detected_type": "temp_mail",
            }
        )
        return False

    actual_email = str((mailbox or {}).get("email") or "").strip() or email
    # 导入成功后应已落库；这里做一次确认
    if temp_emails_repo.get_temp_email_by_address(actual_email):
        return True
    errors.append(
        {
            "line": line_num,
            "email": email,
            "error": "临时邮箱导入失败：导入未落库",
            "detected_type": "temp_mail",
        }
    )
    return False


def _handle_auto_import(data: Dict[str, Any], *, add_to_pool: bool = False) -> Any:
    """处理 provider="auto" 的智能混合导入。"""
    account_str = data.get("account_string", "")
    duplicate_strategy = (data.get("duplicate_strategy") or "skip").strip().lower()
    if duplicate_strategy not in ("skip", "overwrite"):
        duplicate_strategy = "skip"
    fallback_host = (data.get("imap_host") or "").strip()
    try:
        fallback_port = int(data.get("imap_port") or 993)
    except Exception:
        fallback_port = 993
    explicit_group_id = data.get("group_id")

    # 验证显式 group_id（如果提供）
    use_auto_group = explicit_group_id is None
    if not use_auto_group:
        try:
            explicit_group_id = int(explicit_group_id)
        except Exception:
            explicit_group_id = None
            use_auto_group = True
        if explicit_group_id is not None:
            target_group = groups_repo.get_group_by_id(explicit_group_id)
            if not target_group:
                return build_error_response(
                    "GROUP_NOT_FOUND",
                    "指定的分组不存在",
                    message_en="Target group not found",
                    status=404,
                )
            if target_group.get("is_system"):
                return build_error_response(
                    "SYSTEM_GROUP_PROTECTED",
                    "不能导入到系统分组",
                    message_en="Cannot import accounts into a system group",
                    status=403,
                )

    raw_lines = account_str.splitlines()

    # 合并续行：从其他地方复制的凭据中 refresh_token 可能包含换行符（行宽折行），
    # splitlines() 会将其切碎；续行特征：不含 '----' 分隔符且不是注释行
    _merged: list[str] = []
    for _line in raw_lines:
        _stripped = _line.strip()
        if not _stripped:
            continue
        if _merged and not _merged[-1].lstrip().startswith("#") and "----" not in _stripped and not _stripped.startswith("#"):
            _merged[-1] += _stripped
        else:
            _merged.append(_stripped)
    raw_lines = _merged

    imported = 0
    skipped = 0
    failed = 0
    by_provider: Dict[str, Dict[str, int]] = {}
    groups_created: List[str] = []
    errors: List[Dict[str, Any]] = []
    errors_total = 0
    max_error_details = 50
    group_cache: Dict[str, int] = {}
    temp_mail_count = 0

    for line_num, raw in enumerate(raw_lines, 1):
        line = (raw or "").strip()
        if not line or line.startswith("#"):
            continue

        result = _detect_line_type(line, fallback_host, fallback_port)

        if result["type"] == "error":
            failed += 1
            errors_total += 1
            if len(errors) < max_error_details:
                errors.append({"line": line_num, "email": "", "error": result["error"]})
            continue

        fields = result["fields"]
        email = fields.get("email", "").strip()
        prov = result["provider"]

        # 邮箱格式校验
        if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            failed += 1
            errors_total += 1
            if len(errors) < max_error_details:
                errors.append(
                    {
                        "line": line_num,
                        "email": email,
                        "error": "邮箱格式不正确",
                        "detected_type": result["type"],
                    }
                )
            continue

        # 初始化 provider 统计
        if prov not in by_provider:
            by_provider[prov] = {"imported": 0, "skipped": 0, "failed": 0}

        # 临时邮箱特殊处理：写入 temp_emails
        if result["type"] == "temp_mail":
            from outlook_web.repositories import temp_emails as temp_emails_repo

            existing_temp = temp_emails_repo.get_temp_email_by_address(email)
            if existing_temp:
                if duplicate_strategy == "skip":
                    skipped += 1
                    by_provider[prov]["skipped"] += 1
                    continue
                # overwrite 对临时邮箱无意义（无凭据可更新），视为跳过
                skipped += 1
                by_provider[prov]["skipped"] += 1
                continue

            ok = _handle_temp_mail_import(email, errors, line_num, temp_mail_count)
            if ok:
                imported += 1
                temp_mail_count += 1
                by_provider[prov]["imported"] += 1
            else:
                failed += 1
                errors_total += 1
                by_provider[prov]["failed"] += 1
            continue

        # 解析分组（Outlook/IMAP）
        if use_auto_group:
            group_id = _resolve_auto_group(prov, group_cache, groups_created)
        else:
            group_id = explicit_group_id

        # 检查重复
        existing = accounts_repo.get_account_by_email(email)
        if existing:
            if duplicate_strategy == "skip":
                skipped += 1
                by_provider[prov]["skipped"] += 1
                continue
            elif duplicate_strategy == "overwrite":
                ok = _overwrite_account(existing, result, group_id, add_to_pool=add_to_pool)
                if ok:
                    imported += 1
                    by_provider[prov]["imported"] += 1
                    log_audit(
                        "overwrite",
                        "account",
                        str(existing["id"]),
                        f"覆盖更新 email={email}, provider={prov}",
                    )
                else:
                    failed += 1
                    errors_total += 1
                    by_provider[prov]["failed"] += 1
                    if len(errors) < max_error_details:
                        errors.append(
                            {
                                "line": line_num,
                                "email": email,
                                "error": "覆盖更新失败",
                                "detected_type": result["type"],
                            }
                        )
                continue

        # 新增账号
        if result["type"] == "outlook":
            ok = accounts_repo.add_account(
                email_addr=email,
                password=fields.get("password", ""),
                client_id=fields.get("client_id", ""),
                refresh_token=fields.get("refresh_token", ""),
                group_id=group_id,
                account_type="outlook",
                provider="outlook",
                add_to_pool=add_to_pool,
            )
        elif result["type"] == "imap":
            ok = accounts_repo.add_account(
                email_addr=email,
                password="",
                client_id="",
                refresh_token="",
                group_id=group_id,
                account_type="imap",
                provider=prov,
                imap_host=fields.get("imap_host", ""),
                imap_port=fields.get("imap_port", 993),
                imap_password=fields.get("imap_password", ""),
                add_to_pool=add_to_pool,
            )
        else:
            ok = False

        if ok:
            imported += 1
            by_provider[prov]["imported"] += 1
        else:
            failed += 1
            errors_total += 1
            by_provider[prov]["failed"] += 1
            reason = "写入失败"
            try:
                exists = get_db().execute("SELECT 1 FROM accounts WHERE email = ? LIMIT 1", (email,)).fetchone()
                if exists:
                    reason = "邮箱已存在"
            except Exception:
                pass
            if len(errors) < max_error_details:
                errors.append(
                    {
                        "line": line_num,
                        "email": email,
                        "error": reason,
                        "detected_type": result["type"],
                    }
                )

    summary = {
        "mode": "auto",
        "total_lines": len(raw_lines),
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
        "by_provider": by_provider,
        "groups_created": groups_created,
        "duplicate_strategy": duplicate_strategy,
        "errors_total": errors_total,
        "errors_returned": len(errors),
        "errors_truncated": errors_total > len(errors),
    }

    success = imported > 0 or skipped > 0
    message = f"混合导入完成：成功 {imported} 个，跳过 {skipped} 个，失败 {failed} 个"

    if imported > 0 or skipped > 0:
        log_audit(
            "import",
            "account",
            None,
            f"{message}，mode=auto，duplicate_strategy={duplicate_strategy}",
        )

    return jsonify({"success": success, "message": message, "summary": summary, "errors": errors})


@login_required
def api_update_account(account_id: int) -> Any:
    """更新账号（邮箱池管理的 CF 临时邮箱不允许手动编辑）"""
    # 邮箱池管理的 CF 临时邮箱不允许手动编辑
    db = get_db()
    cf_row = db.execute("SELECT provider FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if cf_row and (cf_row["provider"] or "").lower() == "cloudflare_temp_mail":
        return build_error_response(
            "POOL_ACCOUNT_UPDATE_DENIED",
            "邮箱池管理的 CF 临时邮箱不允许手动编辑",
            message_en="CF temp mail accounts managed by pool cannot be edited manually.",
            status=403,
        )

    data = request.json

    # 检查是否只更新状态
    if "status" in data and len(data) == 1:
        # 只更新状态
        return _api_update_account_status(account_id, data["status"])

    email_addr = (data.get("email") or "").strip()
    password = data.get("password")
    client_id = data.get("client_id")
    refresh_token = data.get("refresh_token")
    try:
        group_id = int(data.get("group_id", 1) or 1)
    except Exception:
        group_id = 1
    remark = sanitize_input(data.get("remark", ""), max_length=200)
    status = data.get("status", "active")

    if not email_addr:
        return build_error_response(
            "ACCOUNT_EMAIL_REQUIRED",
            "邮箱不能为空",
            message_en="Email address is required",
        )

    target_group = groups_repo.get_group_by_id(group_id)
    if not target_group:
        error_payload = build_error_payload(
            code="GROUP_NOT_FOUND",
            message="分组不存在",
            err_type="NotFoundError",
            status=404,
            details=f"group_id={group_id}",
        )
        return jsonify({"success": False, "error": error_payload}), 404

    if target_group.get("is_system"):
        error_payload = build_error_payload(
            code="SYSTEM_GROUP_PROTECTED",
            message="不能移动到系统分组",
            err_type="ForbiddenError",
            status=403,
            details=f"group_id={group_id}",
        )
        return jsonify({"success": False, "error": error_payload}), 403

    existing_account = accounts_repo.get_account_by_id(account_id)
    if not existing_account:
        return build_error_response(
            "ACCOUNT_NOT_FOUND",
            "账号不存在",
            message_en="Account not found",
            status=404,
        )

    account_type = (existing_account.get("account_type") or "outlook").strip().lower()
    if account_type != "imap":
        submitted_client_id = client_id.strip() if isinstance(client_id, str) else ""
        submitted_refresh_token = refresh_token.strip() if isinstance(refresh_token, str) else ""
        existing_client_id = (existing_account.get("client_id") or "").strip()
        client_id_changed = bool(submitted_client_id) and submitted_client_id != existing_client_id

        if client_id_changed and not submitted_refresh_token:
            return build_error_response(
                "OUTLOOK_REFRESH_TOKEN_REQUIRED",
                "修改 Client ID 时必须同时提供 Refresh Token",
                message_en="Refresh Token is required when changing Client ID",
                status=400,
            )

    if accounts_repo.update_account(
        account_id,
        email_addr,
        password,
        client_id,
        refresh_token,
        group_id,
        remark,
        status,
    ):
        changed_fields = []
        if isinstance(client_id, str) and client_id.strip():
            changed_fields.append("client_id")
        if isinstance(password, str) and password.strip():
            changed_fields.append("password")
        if isinstance(refresh_token, str) and refresh_token.strip():
            changed_fields.append("refresh_token")
        details = json.dumps(
            {
                "email": email_addr,
                "group_id": group_id,
                "status": status,
                "changed_fields": changed_fields,
            },
            ensure_ascii=False,
        )
        log_audit("update", "account", str(account_id), details)
        return jsonify(
            {
                "success": True,
                "message": "账号更新成功",
                "message_en": "Account updated successfully",
            }
        )
    return build_error_response(
        "ACCOUNT_UPDATE_FAILED",
        "更新失败",
        message_en="Failed to update account",
        status=500,
    )


@login_required
def api_update_account_remark(account_id: int) -> Any:
    """仅更新账号备注，不要求重复提交其他字段。"""
    data = request.get_json(silent=True) or {}
    remark = sanitize_input(data.get("remark", ""), max_length=200)

    existing_account = accounts_repo.get_account_by_id(account_id)
    if not existing_account:
        return build_error_response(
            "ACCOUNT_NOT_FOUND",
            "账号不存在",
            message_en="Account not found",
            status=404,
        )

    email_addr = (existing_account.get("email") or "").strip()
    password = None
    client_id = existing_account.get("client_id")
    refresh_token = None
    group_id = int(existing_account.get("group_id") or 1)
    status = existing_account.get("status") or "active"

    if not accounts_repo.update_account(
        account_id,
        email_addr,
        password,
        client_id,
        refresh_token,
        group_id,
        remark,
        status,
    ):
        return build_error_response(
            "ACCOUNT_UPDATE_FAILED",
            "更新失败",
            message_en="Failed to update account",
            status=500,
        )

    log_audit(
        "update",
        "account",
        str(account_id),
        json.dumps({"remark": remark}, ensure_ascii=False),
    )
    return jsonify(
        {
            "success": True,
            "message": "备注更新成功",
            "message_en": "Remark updated successfully",
        }
    )


def _api_update_account_status(account_id: int, status: str) -> Any:
    """只更新账号状态"""
    normalized_status = _normalize_account_status(status)
    if not normalized_status:
        return build_error_response(
            "INVALID_PARAM",
            "状态值无效",
            message_en="Invalid account status",
            status=400,
        )

    db = get_db()
    try:
        cursor = db.execute(
            """
            UPDATE accounts
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (normalized_status, account_id),
        )
        db.commit()
        if cursor.rowcount <= 0:
            return build_error_response(
                "ACCOUNT_NOT_FOUND",
                "账号不存在",
                message_en="Account not found",
                status=404,
            )
        return jsonify({"success": True, "message": "状态更新成功"})
    except Exception:
        return build_error_response(
            "ACCOUNT_STATUS_UPDATE_FAILED",
            "更新失败",
            message_en="Failed to update account status",
            status=500,
        )


@login_required
def api_batch_update_status() -> Any:
    """批量更新账号状态（用于失效账号治理主动作）。"""
    data = request.get_json(silent=True) or {}
    account_ids = data.get("account_ids", [])
    normalized_status = _normalize_account_status(data.get("status"))

    if not isinstance(account_ids, list) or not account_ids:
        return build_error_response(
            "ACCOUNT_IDS_REQUIRED",
            "请选择要修改状态的账号",
            message_en="Please select accounts to update status",
        )

    if not normalized_status:
        return build_error_response(
            "INVALID_PARAM",
            "状态值无效",
            message_en="Invalid account status",
            status=400,
        )

    try:
        parsed_ids = [int(aid) for aid in account_ids]
    except (TypeError, ValueError):
        return build_error_response(
            "INVALID_PARAM",
            "account_ids 必须为整数列表",
            message_en="account_ids must be a list of integers",
            status=400,
        )

    deduped_ids: List[int] = []
    seen_ids = set()
    for aid in parsed_ids:
        if aid in seen_ids:
            continue
        seen_ids.add(aid)
        deduped_ids.append(aid)

    db = get_db()
    placeholders = ",".join("?" * len(deduped_ids))
    try:
        existing_rows = db.execute(
            f"SELECT id FROM accounts WHERE id IN ({placeholders})",
            deduped_ids,
        ).fetchall()
        existing_ids = {int(row["id"]) for row in existing_rows}

        missing_ids = [aid for aid in deduped_ids if aid not in existing_ids]
        if existing_ids:
            existing_id_list = sorted(existing_ids)
            update_placeholders = ",".join("?" * len(existing_id_list))
            db.execute(
                f"""
                UPDATE accounts
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({update_placeholders})
                """,
                [normalized_status] + existing_id_list,
            )
            db.commit()

        updated_count = len(existing_ids)
        failed_count = len(missing_ids)
        log_audit(
            "update",
            "account_status",
            None,
            f"批量更新账号状态：status={normalized_status}，成功={updated_count}，失败={failed_count}",
        )
        return jsonify(
            {
                "success": True,
                "message": f"成功更新 {updated_count} 个账号状态" + (f"，失败 {failed_count} 个" if failed_count > 0 else ""),
                "status": normalized_status,
                "updated_count": updated_count,
                "failed_count": failed_count,
                "missing_ids": missing_ids,
            }
        )
    except Exception as e:
        return build_error_response(
            "ACCOUNT_STATUS_BATCH_UPDATE_FAILED",
            "批量更新账号状态失败",
            message_en="Failed to batch update account status",
            status=500,
            details=str(e),
        )


@login_required
def api_delete_account(account_id: int) -> Any:
    """删除账号（邮箱池管理的 CF 临时邮箱不允许手动删除）"""
    email_addr = ""
    try:
        db = get_db()
        row = db.execute("SELECT email, provider FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if row:
            email_addr = row["email"]
            # 邮箱池管理的 CF 临时邮箱不允许手动删除
            if (row["provider"] or "").lower() == "cloudflare_temp_mail":
                return build_error_response(
                    "POOL_ACCOUNT_DELETE_DENIED",
                    "邮箱池管理的 CF 临时邮箱不允许手动删除，请通过邮箱池接口释放",
                    message_en="CF temp mail accounts managed by pool cannot be deleted manually. Use pool release API instead.",
                    status=403,
                )
    except Exception:
        email_addr = ""
    if accounts_repo.delete_account_by_id(account_id):
        log_audit(
            "delete",
            "account",
            str(account_id),
            f"删除账号：{email_addr}" if email_addr else "删除账号",
        )
        return jsonify({"success": True})
    return build_error_response(
        "ACCOUNT_DELETE_FAILED",
        "删除失败",
        message_en="Failed to delete account",
        status=500,
    )


@login_required
def api_delete_account_by_email(email_addr: str) -> Any:
    """根据邮箱地址删除账号（邮箱池管理的 CF 临时邮箱不允许手动删除）"""
    db = get_db()
    row = db.execute("SELECT provider FROM accounts WHERE email = ?", (email_addr,)).fetchone()
    if row and (row["provider"] or "").lower() == "cloudflare_temp_mail":
        return build_error_response(
            "POOL_ACCOUNT_DELETE_DENIED",
            "邮箱池管理的 CF 临时邮箱不允许手动删除，请通过邮箱池接口释放",
            message_en="CF temp mail accounts managed by pool cannot be deleted manually. Use pool release API instead.",
            status=403,
        )
    if accounts_repo.delete_account_by_email(email_addr):
        log_audit("delete", "account", email_addr, f"删除账号：{email_addr}")
        return jsonify({"success": True})
    return build_error_response(
        "ACCOUNT_DELETE_FAILED",
        "删除失败",
        message_en="Failed to delete account",
        status=500,
    )


@login_required
def api_batch_delete_accounts() -> Any:
    """
    批量删除账号 API

    功能：支持一次性删除多个账号，记录审计日志
    """
    data = request.get_json()
    account_ids = data.get("account_ids", [])

    if not account_ids:
        return build_error_response(
            "ACCOUNT_IDS_REQUIRED",
            "请选择要删除的账号",
            message_en="Please select the accounts to delete",
        )

    if not isinstance(account_ids, list):
        return build_error_response("INVALID_PARAM", "参数格式错误", message_en="Invalid request parameters")

    deleted_count = 0
    failed_count = 0

    for account_id in account_ids:
        try:
            # 获取邮箱地址和 provider 用于审计日志和保护判断
            db = get_db()
            row = db.execute("SELECT email, provider FROM accounts WHERE id = ?", (account_id,)).fetchone()
            email_addr = row["email"] if row else ""

            # 邮箱池管理的 CF 临时邮箱不允许手动删除，跳过
            if row and (row["provider"] or "").lower() == "cloudflare_temp_mail":
                failed_count += 1
                continue

            if accounts_repo.delete_account_by_id(account_id):
                log_audit(
                    "delete",
                    "account",
                    str(account_id),
                    f"批量删除账号：{email_addr}" if email_addr else "批量删除账号",
                )
                deleted_count += 1
            else:
                failed_count += 1
        except Exception:
            failed_count += 1

    return jsonify(
        {
            "success": True,
            "message": f"成功删除 {deleted_count} 个账号" + (f"，失败 {failed_count} 个" if failed_count > 0 else ""),
            "deleted_count": deleted_count,
            "failed_count": failed_count,
        }
    )


# ==================== 批量操作 API ====================


@login_required
def api_batch_manage_tags() -> Any:
    """批量管理账号标签"""
    data = request.json
    account_ids: List[int] = data.get("account_ids", [])
    tag_id = data.get("tag_id")
    action = data.get("action")  # add, remove

    if not account_ids or not tag_id or not action:
        return build_error_response("INVALID_PARAM", "参数不完整", message_en="Missing required parameters")

    count = 0
    for acc_id in account_ids:
        if action == "add":
            if tags_repo.add_account_tag(acc_id, tag_id):
                count += 1
        elif action == "remove":
            if tags_repo.remove_account_tag(acc_id, tag_id):
                count += 1

    try:
        details = json.dumps(
            {
                "action": action,
                "tag_id": tag_id,
                "accounts": len(account_ids),
                "affected": count,
            },
            ensure_ascii=False,
        )
    except Exception:
        details = f"action={action} tag_id={tag_id} accounts={len(account_ids)} affected={count}"
    log_audit("update", "account_tags", str(tag_id), details)
    return jsonify({"success": True, "message": f"成功处理 {count} 个账号"})


@login_required
def api_batch_update_account_group() -> Any:
    """批量更新账号分组"""
    data = request.json
    account_ids = data.get("account_ids", [])
    group_id = data.get("group_id")

    if not account_ids:
        return build_error_response(
            "ACCOUNT_IDS_REQUIRED",
            "请选择要修改的账号",
            message_en="Please select the accounts to update",
        )

    if not group_id:
        return build_error_response(
            "GROUP_ID_REQUIRED",
            "请选择目标分组",
            message_en="Please select a target group",
        )

    # 验证分组存在
    group = groups_repo.get_group_by_id(group_id)
    if not group:
        return build_error_response(
            "GROUP_NOT_FOUND",
            "目标分组不存在",
            message_en="Target group not found",
            status=404,
        )

    # 检查是否是临时邮箱分组（系统保留分组）
    if group.get("is_system"):
        return build_error_response(
            "SYSTEM_GROUP_PROTECTED",
            "不能移动到系统分组",
            message_en="Cannot move accounts into a system group",
            status=403,
        )

    # 批量更新
    db = get_db()
    try:
        placeholders = ",".join("?" * len(account_ids))
        db.execute(
            f"""
            UPDATE accounts SET group_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id IN ({placeholders})
        """,
            [group_id] + account_ids,
        )
        db.commit()
        log_audit(
            "update",
            "account_group",
            str(group_id),
            f"批量移动分组：账号数={len(account_ids)}",
        )
        return jsonify(
            {
                "success": True,
                "message": f"已将 {len(account_ids)} 个账号移动到「{group['name']}」分组",
            }
        )
    except Exception as e:
        return build_error_response(
            "ACCOUNT_GROUP_BATCH_UPDATE_FAILED",
            "批量移动分组失败",
            message_en="Failed to move accounts to the target group",
            status=500,
            details=str(e),
        )


@login_required
def api_search_accounts() -> Any:
    """全局搜索账号"""
    query = request.args.get("q", "").strip()

    if not query:
        return jsonify({"success": True, "accounts": []})

    db = get_db()
    # 支持搜索邮箱、备注和标签
    cursor = db.execute(
        """
        SELECT DISTINCT a.*, g.name as group_name, g.color as group_color
        FROM accounts a
        LEFT JOIN groups g ON a.group_id = g.id
        LEFT JOIN account_tags at ON a.id = at.account_id
        LEFT JOIN tags t ON at.tag_id = t.id
        WHERE a.email LIKE ? OR a.remark LIKE ? OR t.name LIKE ?
        ORDER BY a.created_at DESC
    """,
        (f"%{query}%", f"%{query}%", f"%{query}%"),
    )

    rows = cursor.fetchall()

    # 批量加载标签与最后刷新状态，避免 N+1 查询
    account_rows: List[Dict[str, Any]] = [dict(r) for r in rows]
    try:
        account_ids = [int(a.get("id")) for a in account_rows if a.get("id") is not None]
    except Exception:
        account_ids = []

    tags_by_account: Dict[int, List[Dict[str, Any]]] = {}
    last_log_by_account: Dict[int, Dict[str, Any]] = {}
    if account_ids:
        try:
            placeholders = ",".join(["?"] * len(account_ids))
            tag_rows = db.execute(
                f"""
                SELECT at.account_id as account_id, t.*
                FROM account_tags at
                JOIN tags t ON t.id = at.tag_id
                WHERE at.account_id IN ({placeholders})
                ORDER BY at.account_id ASC, t.created_at DESC
            """,
                account_ids,
            ).fetchall()
            for tr in tag_rows:
                tag_dict = dict(tr)
                acc_id = tag_dict.pop("account_id", None)
                if acc_id is None:
                    continue
                tags_by_account.setdefault(int(acc_id), []).append(tag_dict)
        except Exception:
            tags_by_account = {}

        try:
            placeholders = ",".join(["?"] * len(account_ids))
            log_rows = db.execute(
                f"""
                SELECT l.account_id, l.status, l.error_message, l.created_at
                FROM account_refresh_logs l
                JOIN (
                    SELECT account_id, MAX(id) as max_id
                    FROM account_refresh_logs
                    WHERE account_id IN ({placeholders})
                    GROUP BY account_id
                ) latest
                ON l.account_id = latest.account_id AND l.id = latest.max_id
            """,
                account_ids,
            ).fetchall()
            for lr in log_rows:
                try:
                    last_log_by_account[int(lr["account_id"])] = dict(lr)
                except Exception:
                    continue
        except Exception:
            last_log_by_account = {}

    safe_accounts = []
    for acc in account_rows:
        acc_id = acc.get("id")
        try:
            acc_id_int = int(acc_id)
        except Exception:
            acc_id_int = None

        tags = tags_by_account.get(acc_id_int, []) if acc_id_int is not None else []
        last_refresh_log = last_log_by_account.get(acc_id_int) if acc_id_int is not None else None

        safe_accounts.append(
            {
                "id": acc["id"],
                "email": acc["email"],
                "account_type": acc.get("account_type") or "outlook",
                "provider": acc.get("provider") or "outlook",
                "client_id": (acc["client_id"][:8] + "..." if len(acc["client_id"]) > 8 else acc["client_id"]),
                "group_id": acc["group_id"],
                "group_name": acc["group_name"] if acc["group_name"] else "默认分组",
                "group_color": acc["group_color"] if acc["group_color"] else "#666666",
                "remark": acc["remark"] if acc["remark"] else "",
                "status": acc["status"] if acc["status"] else "active",
                "created_at": acc["created_at"] if acc["created_at"] else "",
                "updated_at": acc["updated_at"] if acc["updated_at"] else "",
                "tags": tags,
                "telegram_push_enabled": bool(acc.get("telegram_push_enabled")),
                "notification_enabled": bool(acc.get("telegram_push_enabled")),
                "last_refresh_status": (last_refresh_log.get("status") if last_refresh_log else None),
                "last_refresh_error": (last_refresh_log.get("error_message") if last_refresh_log else None),
                "latest_email_subject": acc.get("latest_email_subject", ""),
                "latest_email_from": acc.get("latest_email_from", ""),
                "latest_email_folder": acc.get("latest_email_folder", ""),
                "latest_email_received_at": acc.get("latest_email_received_at", ""),
                "latest_verification_code": acc.get("latest_verification_code", ""),
                "latest_verification_folder": acc.get("latest_verification_folder", ""),
                "latest_verification_received_at": acc.get("latest_verification_received_at", ""),
            }
        )

    return jsonify({"success": True, "accounts": safe_accounts})


# ==================== 导出功能 API ====================


def _build_export_text(accounts: List[Dict[str, Any]], temp_emails: Optional[List[Dict]] = None) -> str:
    """构建导出文本 v2：头部元信息 + 分段 + 临时邮箱分段。"""
    import io

    from outlook_web.services.providers import MAIL_PROVIDERS, get_provider_list

    outlook_lines: List[str] = []
    imap_groups: Dict[str, List[str]] = {}
    temp_mail_lines: List[str] = []

    for acc in accounts or []:
        atype = (acc.get("account_type") or "outlook").strip().lower()
        prov = (acc.get("provider") or "").strip().lower()

        # 兼容历史 provider，统一按临时邮箱导出
        if prov in {"gptmail", "temp_mail"}:
            temp_mail_lines.append(acc.get("email", ""))
            continue

        if atype == "outlook":
            line = f"{acc.get('email', '')}----{acc.get('password', '')}----{acc.get('client_id', '')}----{acc.get('refresh_token', '')}"
            outlook_lines.append(line)
            continue

        provider = prov or "custom"
        imap_pwd = acc.get("imap_password", "") or ""
        if provider == "custom":
            line = f"{acc.get('email', '')}----{imap_pwd}----{provider}----{acc.get('imap_host', '') or ''}----{acc.get('imap_port', 993) or 993}"
        else:
            line = f"{acc.get('email', '')}----{imap_pwd}----{provider}"

        imap_groups.setdefault(provider, []).append(line)

    # 追加 temp_emails 中的临时邮箱
    for te in temp_emails or []:
        email = te.get("email", "")
        if email and email not in temp_mail_lines:
            temp_mail_lines.append(email)

    # 统计
    total = len(outlook_lines) + sum(len(v) for v in imap_groups.values()) + len(temp_mail_lines)
    buf = io.StringIO()

    # 头部元信息
    buf.write("# ============================================\n")
    buf.write("# Outlook Email Plus — 账号导出\n")
    buf.write(f"# 导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    buf.write(f"# 账号总数：{total}\n")
    if outlook_lines:
        buf.write(f"#   Outlook：{len(outlook_lines)}\n")
    for prov_key, lines in imap_groups.items():
        label = (MAIL_PROVIDERS.get(prov_key, {}) or {}).get("label", prov_key)
        buf.write(f"#   {label}：{len(lines)}\n")
    if temp_mail_lines:
        buf.write(f"#   临时邮箱：{len(temp_mail_lines)}\n")
    buf.write("# 格式版本：v2\n")
    buf.write("# ============================================\n")

    # Outlook 分段
    if outlook_lines:
        buf.write("\n# === Outlook 账号 ===\n")
        for line in outlook_lines:
            buf.write(line + "\n")

    # IMAP 分段（按 provider 排序）
    provider_order = [p.get("key") for p in get_provider_list() if p.get("key")]
    provider_order = [p for p in provider_order if p not in ("outlook", "auto")]
    appended = set()
    for provider in provider_order:
        lines = imap_groups.get(provider) or []
        if not lines:
            continue
        label = (MAIL_PROVIDERS.get(provider, {}) or {}).get("label", provider)
        buf.write(f"\n# === IMAP 账号（{label}）===\n")
        for line in lines:
            buf.write(line + "\n")
        appended.add(provider)

    for provider, lines in imap_groups.items():
        if provider in appended:
            continue
        label = (MAIL_PROVIDERS.get(provider, {}) or {}).get("label", provider)
        buf.write(f"\n# === IMAP 账号（{label}）===\n")
        for line in lines:
            buf.write(line + "\n")

    # 临时邮箱分段
    if temp_mail_lines:
        buf.write("\n# === 临时邮箱（自建）===\n")
        for line in temp_mail_lines:
            buf.write(line + "\n")

    return buf.getvalue()


@login_required
def api_export_all_accounts() -> Any:
    """导出所有邮箱账号为 TXT 文件（需要二次验证）"""
    from outlook_web.security.auth import (
        consume_export_verify_token,
        get_client_ip,
        get_user_agent,
    )

    # 从请求头获取二次验证 token（避免 URL 泄露）
    verify_token = request.headers.get("X-Export-Token")
    client_ip = get_client_ip()
    user_agent = get_user_agent()

    ok, error_message = consume_export_verify_token(verify_token, client_ip, user_agent)
    if not ok:
        return build_export_verify_failure_response(error_message)

    # 使用 load_accounts 获取所有账号（自动解密）
    accounts = accounts_repo.load_accounts()

    # 加载临时邮箱
    from outlook_web.repositories import temp_emails as temp_emails_repo

    temp_emails = temp_emails_repo.load_temp_emails()

    if not accounts and not temp_emails:
        return build_error_response(
            "ACCOUNT_EXPORT_EMPTY",
            "没有邮箱账号",
            message_en="No mail accounts are available for export",
            status=404,
        )

    # 记录审计日志
    log_audit(
        "export",
        "all_accounts",
        None,
        f"导出所有账号，共 {len(accounts)} 个账号 + {len(temp_emails)} 个临时邮箱",
    )

    content = _build_export_text(accounts, temp_emails)

    # 生成文件名（使用 URL 编码处理中文）
    filename = f"accounts_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    encoded_filename = quote(filename)

    # 返回文件下载响应
    return Response(
        content,
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


@login_required
def api_export_selected_accounts() -> Any:
    """导出选中分组的邮箱账号为 TXT 文件（需要二次验证）"""
    from outlook_web.security.auth import (
        consume_export_verify_token,
        get_client_ip,
        get_user_agent,
    )

    data = request.json or {}
    group_ids = data.get("group_ids", [])
    verify_token = request.headers.get("X-Export-Token") or data.get("verify_token")
    client_ip = get_client_ip()
    user_agent = get_user_agent()

    ok, error_message = consume_export_verify_token(verify_token, client_ip, user_agent)
    if not ok:
        return build_export_verify_failure_response(error_message)

    if not group_ids:
        return build_error_response(
            "GROUP_IDS_REQUIRED",
            "请选择要导出的分组",
            message_en="Please select at least one group to export",
        )

    # 获取选中分组下的所有账号（使用 load_accounts 自动解密）
    all_accounts = []
    for group_id in group_ids:
        accounts = accounts_repo.load_accounts(group_id)
        all_accounts.extend(accounts)

    # 仅当选中了"临时邮箱"系统分组时才附加临时邮箱
    from outlook_web.repositories import temp_emails as temp_emails_repo

    temp_emails: List[Dict] = []
    temp_group = groups_repo.get_group_by_name("临时邮箱")
    if temp_group and temp_group["id"] in group_ids:
        temp_emails = temp_emails_repo.load_temp_emails()

    if not all_accounts and not temp_emails:
        return build_error_response(
            "ACCOUNT_EXPORT_EMPTY",
            "选中的分组下没有邮箱账号",
            message_en="No mail accounts were found in the selected groups",
            status=404,
        )

    # 记录审计日志
    log_audit(
        "export",
        "selected_groups",
        ",".join(map(str, group_ids)),
        f"导出选中分组的 {len(all_accounts)} 个账号 + {len(temp_emails)} 个临时邮箱",
    )

    content = _build_export_text(all_accounts, temp_emails)

    # 生成文件名
    filename = f"accounts_export_selected_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    encoded_filename = quote(filename)

    # 返回文件下载响应
    return Response(
        content,
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


@login_required
def api_generate_export_verify_token() -> Any:
    """生成导出验证token（二次验证）"""
    from outlook_web.repositories import settings as settings_repo
    from outlook_web.security.auth import (
        get_client_ip,
        get_user_agent,
        issue_export_verify_token,
    )
    from outlook_web.security.crypto import verify_password

    data = request.json
    password = data.get("password", "")

    # 验证密码
    stored_password = settings_repo.get_login_password()
    if not verify_password(password, stored_password):
        return build_error_response(
            "LOGIN_INVALID_PASSWORD",
            "密码错误",
            message_en="Invalid password",
            status=401,
        )

    # 生成一次性 token
    client_ip = get_client_ip()
    user_agent = get_user_agent()
    verify_token = issue_export_verify_token(client_ip, user_agent)
    return jsonify({"success": True, "verify_token": verify_token})


# ==================== Token 刷新 API ====================

REFRESH_LOCK_NAME = "refresh_all_tokens"


@login_required
def api_refresh_account(account_id: int) -> Any:
    """刷新单个账号的 token"""
    db = get_db()
    cursor = db.execute(
        "SELECT id, email, client_id, refresh_token, group_id, account_type FROM accounts WHERE id = ?",
        (account_id,),
    )
    account = cursor.fetchone()

    if not account:
        error_payload = build_error_payload(
            "ACCOUNT_NOT_FOUND",
            "账号不存在",
            "NotFoundError",
            404,
            f"account_id={account_id}",
        )
        return jsonify({"success": False, "error": error_payload})

    account_id = account["id"]
    account_email = account["email"]
    client_id = account["client_id"]
    encrypted_refresh_token = account["refresh_token"]

    if not refresh_service.is_refreshable_outlook_account(account["account_type"]):
        return build_error_response(
            "ACCOUNT_REFRESH_UNSUPPORTED",
            "IMAP 账号不支持 Token 刷新",
            message_en="IMAP accounts do not support token refresh",
            err_type="UnsupportedOperationError",
            status=400,
            details=f"account_id={account_id}, account_type={account['account_type']}",
        )

    # 获取分组代理设置
    proxy_url = ""
    if account["group_id"]:
        group = groups_repo.get_group_by_id(account["group_id"])
        if group:
            proxy_url = group.get("proxy_url", "") or ""

    # 解密 refresh_token
    try:
        refresh_token = decrypt_data(encrypted_refresh_token) if encrypted_refresh_token else encrypted_refresh_token
    except Exception as e:
        error_msg = f"解密 token 失败: {str(e)}"
        refresh_logs_repo.log_refresh_result(account_id, account_email, "manual", "failed", error_msg)
        error_payload = build_error_payload("TOKEN_DECRYPT_FAILED", "Token 解密失败", "DecryptionError", 500, error_msg)
        return jsonify({"success": False, "error": error_payload})

    # 测试 refresh token（并支持滚动更新 refresh_token）
    success, error_msg, new_refresh_token = graph_service.test_refresh_token_with_rotation(client_id, refresh_token, proxy_url)

    # 记录刷新结果
    refresh_logs_repo.log_refresh_result(
        account_id,
        account_email,
        "manual",
        "success" if success else "failed",
        error_msg,
    )

    if success:
        try:
            if isinstance(new_refresh_token, str) and new_refresh_token.strip() and new_refresh_token != refresh_token:
                accounts_repo.update_account_credentials(account_id, refresh_token=new_refresh_token)
            db.execute(
                "UPDATE accounts SET last_refresh_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (account_id,),
            )
            db.commit()
        except Exception:
            pass
        return jsonify({"success": True, "message": "Token 刷新成功"})

    error_payload = build_error_payload(
        "TOKEN_REFRESH_FAILED",
        "Token 刷新失败",
        "RefreshTokenError",
        400,
        error_msg or "未知错误",
    )
    return jsonify({"success": False, "error": error_payload})


@login_required
def api_refresh_all_accounts() -> Any:
    """刷新所有账号的 token（流式响应，实时返回进度）"""
    trace_id_value = None
    try:
        trace_id_value = getattr(g, "trace_id", None)
    except Exception:
        trace_id_value = None
    requested_by_ip = get_client_ip()
    requested_by_user_agent = get_user_agent()

    def generate():
        yield from refresh_service.stream_refresh_all_accounts(
            trace_id=trace_id_value,
            requested_by_ip=requested_by_ip,
            requested_by_user_agent=requested_by_user_agent,
            lock_name=REFRESH_LOCK_NAME,
            test_refresh_token=graph_service.test_refresh_token_with_rotation,
        )

    return Response(generate(), mimetype="text/event-stream")


@login_required
def api_retry_refresh_account(account_id: int) -> Any:
    """重试单个失败账号的刷新"""
    return api_refresh_account(account_id)


@login_required
def api_refresh_failed_accounts() -> Any:
    """重试所有失败的账号"""
    db = get_db()
    trace_id_value = None
    try:
        trace_id_value = getattr(g, "trace_id", None)
    except Exception:
        trace_id_value = None
    requested_by_ip = get_client_ip()
    requested_by_user_agent = get_user_agent()

    response_data, status_code = refresh_service.refresh_failed_accounts(
        db=db,
        trace_id=trace_id_value,
        requested_by_ip=requested_by_ip,
        requested_by_user_agent=requested_by_user_agent,
        lock_name=REFRESH_LOCK_NAME,
        test_refresh_token=graph_service.test_refresh_token_with_rotation,
    )
    return jsonify(response_data), status_code


@login_required
def api_trigger_scheduled_refresh() -> Any:
    """手动触发定时刷新（支持强制刷新）"""
    force = request.args.get("force", "false").lower() == "true"
    trace_id_value = None
    try:
        trace_id_value = getattr(g, "trace_id", None)
    except Exception:
        trace_id_value = None
    requested_by_ip = get_client_ip()
    requested_by_user_agent = get_user_agent()

    # 获取配置
    refresh_interval_days = int(settings_repo.get_setting("refresh_interval_days", "30"))
    use_cron = settings_repo.get_setting("use_cron_schedule", "false").lower() == "true"

    # 执行刷新（使用流式响应）
    def generate():
        yield from refresh_service.stream_trigger_scheduled_refresh(
            force=force,
            refresh_interval_days=refresh_interval_days,
            use_cron=use_cron,
            trace_id=trace_id_value,
            requested_by_ip=requested_by_ip,
            requested_by_user_agent=requested_by_user_agent,
            lock_name=REFRESH_LOCK_NAME,
            test_refresh_token=graph_service.test_refresh_token_with_rotation,
        )

    return Response(generate(), mimetype="text/event-stream")


# ==================== 刷新日志 API ====================


@login_required
def api_get_refresh_logs() -> Any:
    """获取所有账号的刷新历史（近半年）"""
    db = get_db()
    limit = int(request.args.get("limit", 1000))
    offset = int(request.args.get("offset", 0))

    cursor = db.execute(
        """
        SELECT l.*, a.email as account_email
        FROM account_refresh_logs l
        LEFT JOIN accounts a ON l.account_id = a.id
        WHERE l.refresh_type IN ('manual', 'manual_all', 'scheduled', 'retry')
        AND l.created_at >= datetime('now', '-6 months')
        ORDER BY l.created_at DESC
        LIMIT ? OFFSET ?
    """,
        (limit, offset),
    )

    logs = []
    for row in cursor.fetchall():
        logs.append(
            {
                "id": row["id"],
                "account_id": row["account_id"],
                "account_email": row["account_email"] or row["account_email"],
                "refresh_type": row["refresh_type"],
                "status": row["status"],
                "error_message": row["error_message"],
                "created_at": row["created_at"],
            }
        )

    return jsonify({"success": True, "logs": logs})


@login_required
def api_get_account_refresh_logs(account_id: int) -> Any:
    """获取单个账号的刷新历史"""
    db = get_db()
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    cursor = db.execute(
        """
        SELECT * FROM account_refresh_logs
        WHERE account_id = ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """,
        (account_id, limit, offset),
    )

    logs = []
    for row in cursor.fetchall():
        logs.append(
            {
                "id": row["id"],
                "account_id": row["account_id"],
                "account_email": row["account_email"],
                "refresh_type": row["refresh_type"],
                "status": row["status"],
                "error_message": row["error_message"],
                "created_at": row["created_at"],
            }
        )

    return jsonify({"success": True, "logs": logs})


@login_required
def api_get_failed_refresh_logs() -> Any:
    """获取所有失败的刷新记录"""
    db = get_db()

    # 获取每个账号最近一次失败的刷新记录
    cursor = db.execute("""
        SELECT l.*, a.email as account_email, a.status as account_status
        FROM account_refresh_logs l
        INNER JOIN (
            SELECT account_id, MAX(created_at) as last_refresh
            FROM account_refresh_logs
            GROUP BY account_id
        ) latest ON l.account_id = latest.account_id AND l.created_at = latest.last_refresh
        LEFT JOIN accounts a ON l.account_id = a.id
        WHERE l.status = 'failed'
        ORDER BY l.created_at DESC
    """)

    logs = []
    for row in cursor.fetchall():
        logs.append(
            {
                "id": row["id"],
                "account_id": row["account_id"],
                "account_email": row["account_email"] or row["account_email"],
                "account_status": row["account_status"],
                "refresh_type": row["refresh_type"],
                "status": row["status"],
                "error_message": row["error_message"],
                "created_at": row["created_at"],
            }
        )

    return jsonify({"success": True, "logs": logs})


@login_required
def api_get_invalid_token_candidates() -> Any:
    """获取最近一次刷新失败且命中 invalid token 判定的候选账号列表。"""
    db = get_db()
    limit = request.args.get("limit", default=200, type=int)
    offset = request.args.get("offset", default=0, type=int)

    if limit is None:
        limit = 200
    if offset is None:
        offset = 0
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)

    rows = db.execute(
        """
        SELECT
            l.id as refresh_log_id,
            l.account_id,
            COALESCE(a.email, l.account_email) as account_email,
            a.status as account_status,
            l.refresh_type,
            l.error_message,
            l.created_at
        FROM account_refresh_logs l
        INNER JOIN (
            SELECT account_id, MAX(id) AS max_id
            FROM account_refresh_logs
            GROUP BY account_id
        ) latest
            ON l.account_id = latest.account_id
            AND l.id = latest.max_id
        LEFT JOIN accounts a
            ON a.id = l.account_id
        WHERE l.status = 'failed'
          AND (
              LOWER(COALESCE(l.error_message, '')) LIKE '%invalid_grant%'
              OR LOWER(COALESCE(l.error_message, '')) LIKE '%aadsts70000%'
          )
        ORDER BY l.id DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()

    candidates = []
    for row in rows:
        classified = refresh_service._classify_refresh_failure(row["error_message"])
        if not classified.get("is_invalid_token"):
            continue

        candidates.append(
            {
                "refresh_log_id": row["refresh_log_id"],
                "account_id": row["account_id"],
                "account_email": row["account_email"],
                "account_status": row["account_status"],
                "refresh_type": row["refresh_type"],
                "error_message": row["error_message"],
                "created_at": row["created_at"],
                "reason_code": classified.get("reason_code"),
                "reason_label": classified.get("reason_label"),
                "is_invalid_token": True,
            }
        )

    return jsonify(
        {
            "success": True,
            "candidates": candidates,
            "total": len(candidates),
            "limit": limit,
            "offset": offset,
        }
    )


@login_required
def api_get_refresh_stats() -> Any:
    """获取刷新统计信息（统计当前失败状态的邮箱数量）"""
    db = get_db()

    cursor = db.execute("""
        SELECT MAX(created_at) as last_refresh_time
        FROM account_refresh_logs
        WHERE refresh_type IN ('manual', 'manual_all', 'scheduled', 'retry')
    """)
    row = cursor.fetchone()
    last_refresh_time = row["last_refresh_time"] if row else None

    cursor = db.execute("""
        SELECT COUNT(*) as total_accounts
        FROM accounts
        WHERE status = 'active'
    """)
    total_accounts = cursor.fetchone()["total_accounts"]

    cursor = db.execute("""
        SELECT COUNT(DISTINCT l.account_id) as failed_count
        FROM account_refresh_logs l
        INNER JOIN (
            SELECT account_id, MAX(created_at) as last_refresh
            FROM account_refresh_logs
            GROUP BY account_id
        ) latest ON l.account_id = latest.account_id AND l.created_at = latest.last_refresh
        INNER JOIN accounts a ON l.account_id = a.id
        WHERE l.status = 'failed' AND a.status = 'active'
    """)
    failed_count = cursor.fetchone()["failed_count"]

    return jsonify(
        {
            "success": True,
            "stats": {
                "total": total_accounts,
                "success_count": total_accounts - failed_count,
                "failed_count": failed_count,
                "last_refresh_time": last_refresh_time,
            },
        }
    )


# ==================== 通知参与 API（兼容旧 Telegram 路径） ====================


@login_required
def api_telegram_toggle(account_id: int) -> Any:
    """切换账号通知参与开关。兼容旧 Telegram 专用接口路径。"""
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled", False))
    success = accounts_repo.toggle_telegram_push(account_id, enabled)
    if not success:
        error_payload = build_error_payload(
            "ACCOUNT_NOT_FOUND",
            "账号不存在",
            "NotFoundError",
            404,
            f"account_id={account_id}",
            message_en="Account not found",
        )
        return jsonify({"success": False, "error": error_payload}), 404
    action = "开启" if enabled else "关闭"
    log_audit(f"telegram_push_{action}", "account", str(account_id))
    return jsonify(
        {
            "success": True,
            "enabled": enabled,
            "notification_enabled": enabled,
            "message": f"该邮箱通知参与已{action}",
            "message_en": f"Mailbox notifications {'enabled' if enabled else 'disabled'}",
        }
    )


# ==================== 指定账号批量刷新 Token ====================


@login_required
def api_refresh_selected_accounts() -> Any:
    """刷新指定账号列表的 token（SSE 流式响应）"""
    data = request.get_json(silent=True) or {}
    account_ids = data.get("account_ids", [])

    if not account_ids or not isinstance(account_ids, list):
        error_payload = build_error_payload(
            "INVALID_PARAMS",
            "account_ids 不能为空",
            "ValidationError",
            400,
            "account_ids must be a non-empty list of integers",
        )
        return jsonify({"success": False, "error": error_payload}), 400

    # 确保所有 ID 为整数
    try:
        account_ids = [int(aid) for aid in account_ids]
    except (TypeError, ValueError):
        error_payload = build_error_payload(
            "INVALID_PARAMS",
            "account_ids 必须为整数列表",
            "ValidationError",
            400,
            "account_ids must be a list of integers",
        )
        return jsonify({"success": False, "error": error_payload}), 400

    trace_id_value = None
    try:
        trace_id_value = getattr(g, "trace_id", None)
    except Exception:
        trace_id_value = None
    requested_by_ip = get_client_ip()
    requested_by_user_agent = get_user_agent()

    def generate():
        yield from refresh_service.stream_refresh_selected_accounts(
            account_ids=account_ids,
            trace_id=trace_id_value,
            requested_by_ip=requested_by_ip,
            requested_by_user_agent=requested_by_user_agent,
            lock_name=REFRESH_LOCK_NAME,
            test_refresh_token=graph_service.test_refresh_token_with_rotation,
        )

    return Response(generate(), mimetype="text/event-stream")
