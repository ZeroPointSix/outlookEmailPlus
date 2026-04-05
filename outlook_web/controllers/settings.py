from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from flask import jsonify, request

from outlook_web import config
from outlook_web.audit import log_audit
from outlook_web.db import get_db
from outlook_web.errors import build_error_payload
from outlook_web.repositories import external_api_keys as external_api_keys_repo
from outlook_web.repositories import settings as settings_repo
from outlook_web.security.auth import login_required
from outlook_web.security.crypto import (
    decrypt_data,
    encrypt_data,
    hash_password,
    is_encrypted,
)

# ==================== 设置 API ====================


def _mask_secret_value(value: str, head: int = 4, tail: int = 4) -> str:
    if not value:
        return ""
    safe_value = str(value)
    if len(safe_value) <= head + tail:
        return "*" * len(safe_value)
    return (
        safe_value[:head] + ("*" * (len(safe_value) - head - tail)) + safe_value[-tail:]
    )


def _parse_allowed_emails_input(raw: Any) -> list[str]:
    if raw in (None, "", []):
        return []
    if isinstance(raw, list):
        values = raw
    else:
        text = str(raw).strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            values = parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            values = [
                item.strip()
                for item in text.replace("\r", "\n").replace(",", "\n").split("\n")
            ]

    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        email_addr = str(item or "").strip().lower()
        if not email_addr or "@" not in email_addr or email_addr in seen:
            continue
        seen.add(email_addr)
        result.append(email_addr)
    return result


def _parse_bool_input(raw: Any, *, default: bool = False) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    text = str(raw).strip().lower()
    if text in ("true", "1", "yes", "on"):
        return True
    if text in ("false", "0", "no", "off"):
        return False
    return default


def _coerce_int_range(raw: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _parse_temp_mail_domains_input(raw: Any) -> list[dict[str, Any]]:
    if raw in (None, "", []):
        return []

    values = raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            values = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            values = [item.strip() for item in text.replace("\r", "\n").split("\n")]

    if not isinstance(values, list):
        raise ValueError("temp_mail_domains 必须是数组")

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in values:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            enabled = _parse_bool_input(item.get("enabled"), default=True)
        else:
            name = str(item or "").strip()
            enabled = True
        if not name or name in seen:
            continue
        seen.add(name)
        result.append({"name": name, "enabled": enabled})
    return result


def _parse_temp_mail_prefix_rules_input(raw: Any) -> dict[str, Any]:
    if raw in (None, "", {}):
        return {
            "min_length": 1,
            "max_length": 32,
            "pattern": r"^[a-z0-9][a-z0-9._-]*$",
        }

    value = raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            value = {}
        else:
            value = json.loads(text)

    if not isinstance(value, dict):
        raise ValueError("temp_mail_prefix_rules 必须是对象")

    min_length = _coerce_int_range(value.get("min_length", 1), 1, minimum=1, maximum=64)
    max_length = _coerce_int_range(
        value.get("max_length", 32), 32, minimum=min_length, maximum=128
    )
    pattern = str(value.get("pattern") or r"^[a-z0-9][a-z0-9._-]*$").strip()
    if not pattern:
        pattern = r"^[a-z0-9][a-z0-9._-]*$"
    return {
        "min_length": min_length,
        "max_length": max_length,
        "pattern": pattern,
    }


def _is_valid_notification_email(value: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value or ""))


def _json_error(
    code: str,
    message: str,
    *,
    status: int = 400,
    message_en: str | None = None,
    details: Any = None,
    http_status: int | None = None,
    extra: dict[str, Any] | None = None,
):
    payload = build_error_payload(
        code=code,
        message=message,
        message_en=message_en,
        err_type="ValidationError" if status < 500 else "ServiceError",
        status=status,
        details=details,
    )
    body: dict[str, Any] = {"success": False, "error": payload}
    if extra:
        body.update(extra)
    return jsonify(body), (http_status if http_status is not None else status)


def _ensure_email_service_available() -> None:
    from outlook_web.services import email_push

    email_push.get_email_push_service_config()


@login_required
def api_get_settings() -> Any:
    """获取所有设置"""
    all_settings = settings_repo.get_all_settings()

    # 仅返回前端需要的设置项（避免把敏感字段/内部状态直接返回）
    safe_settings = {
        "refresh_interval_days": all_settings.get("refresh_interval_days", "30"),
        "refresh_delay_seconds": all_settings.get("refresh_delay_seconds", "5"),
        "refresh_cron": all_settings.get("refresh_cron", "0 2 * * *"),
        "use_cron_schedule": all_settings.get("use_cron_schedule", "false"),
        "enable_scheduled_refresh": all_settings.get(
            "enable_scheduled_refresh", "true"
        ),
        # 轮询配置
        "enable_auto_polling": all_settings.get("enable_auto_polling", "false")
        == "true",
        "polling_interval": int(all_settings.get("polling_interval", "10")),
        "polling_count": int(all_settings.get("polling_count", "5")),
        # [Phase 3 deprecated] 简洁模式自动轮询配置 — 保留读取，向后兼容
        "enable_compact_auto_poll": all_settings.get(
            "enable_compact_auto_poll", "false"
        )
        == "true",
        "compact_poll_interval": int(all_settings.get("compact_poll_interval", "10")),
        "compact_poll_max_count": int(all_settings.get("compact_poll_max_count", "5")),
        "email_notification_enabled": all_settings.get(
            "email_notification_enabled", "false"
        ).lower()
        == "true",
        "email_notification_recipient": all_settings.get(
            "email_notification_recipient", ""
        ),
    }

    # 敏感字段：不返回明文/哈希，仅提供"是否已设置/脱敏展示"
    login_password_value = all_settings.get("login_password") or ""
    temp_mail_api_key_value = settings_repo.get_temp_mail_api_key()
    external_api_key_value = settings_repo.get_external_api_key()
    external_api_keys = external_api_keys_repo.list_external_api_keys(
        include_disabled=True
    )
    usage_summary = external_api_keys_repo.get_external_api_usage_summary(
        [item.get("consumer_key") or "" for item in external_api_keys]
    )
    for item in external_api_keys:
        item.update(
            usage_summary.get(
                item.get("consumer_key") or "",
                {
                    "today_total_count": 0,
                    "today_success_count": 0,
                    "today_error_count": 0,
                    "today_last_used_at": "",
                },
            )
        )
    safe_settings["login_password_set"] = bool(login_password_value)
    safe_settings["allow_login_password_change"] = (
        config.get_allow_login_password_change()
    )
    safe_settings["temp_mail_provider"] = settings_repo.get_temp_mail_provider()
    safe_settings["temp_mail_provider_label"] = "temp_mail"
    safe_settings["temp_mail_api_base_url"] = settings_repo.get_temp_mail_api_base_url()
    safe_settings["temp_mail_api_key_set"] = bool(temp_mail_api_key_value)
    safe_settings["temp_mail_api_key_masked"] = (
        _mask_secret_value(temp_mail_api_key_value) if temp_mail_api_key_value else ""
    )
    safe_settings["temp_mail_domains"] = settings_repo.get_temp_mail_domains()
    safe_settings["temp_mail_default_domain"] = (
        settings_repo.get_temp_mail_default_domain()
    )
    safe_settings["temp_mail_prefix_rules"] = settings_repo.get_temp_mail_prefix_rules()
    # v0.3: CF Worker 独立域名配置（Tab 重构）
    safe_settings["cf_worker_domains"] = settings_repo.get_cf_worker_domains()
    safe_settings["cf_worker_default_domain"] = (
        settings_repo.get_cf_worker_default_domain()
    )
    safe_settings["cf_worker_prefix_rules"] = settings_repo.get_cf_worker_prefix_rules()
    # Cloudflare Worker 独立配置（与 GPTMail 设置隔离）
    cf_admin_key_value = settings_repo.get_cf_worker_admin_key()
    safe_settings["cf_worker_base_url"] = settings_repo.get_cf_worker_base_url()
    safe_settings["cf_worker_admin_key_set"] = bool(cf_admin_key_value)
    safe_settings["cf_worker_admin_key_masked"] = (
        _mask_secret_value(cf_admin_key_value) if cf_admin_key_value else ""
    )
    safe_settings["external_api_key_set"] = bool(external_api_key_value)
    safe_settings["external_api_key_masked"] = (
        _mask_secret_value(external_api_key_value) if external_api_key_value else ""
    )
    safe_settings["external_api_keys"] = external_api_keys
    safe_settings["external_api_keys_count"] = len(external_api_keys)
    safe_settings["external_api_multi_key_set"] = bool(external_api_keys)

    # P1：公网模式安全配置
    safe_settings["external_api_public_mode"] = (
        settings_repo.get_external_api_public_mode()
    )
    safe_settings["external_api_ip_whitelist"] = (
        settings_repo.get_external_api_ip_whitelist()
    )
    safe_settings["external_api_rate_limit_per_minute"] = (
        settings_repo.get_external_api_rate_limit()
    )
    safe_settings["external_api_disable_raw_content"] = (
        settings_repo.get_external_api_disable_raw_content()
    )
    safe_settings["external_api_disable_wait_message"] = (
        settings_repo.get_external_api_disable_wait_message()
    )
    safe_settings["external_api_disable_pool_claim_random"] = (
        settings_repo.get_external_api_disable_pool_claim_random()
    )
    safe_settings["external_api_disable_pool_claim_release"] = (
        settings_repo.get_external_api_disable_pool_claim_release()
    )
    safe_settings["external_api_disable_pool_claim_complete"] = (
        settings_repo.get_external_api_disable_pool_claim_complete()
    )
    safe_settings["external_api_disable_pool_stats"] = (
        settings_repo.get_external_api_disable_pool_stats()
    )
    safe_settings["pool_external_enabled"] = settings_repo.get_pool_external_enabled()

    # Telegram 推送配置
    tg_bot_token_raw = all_settings.get("telegram_bot_token", "")
    if tg_bot_token_raw and is_encrypted(tg_bot_token_raw):
        try:
            plain_token = decrypt_data(tg_bot_token_raw)
            safe_settings["telegram_bot_token"] = (
                "****" + plain_token[-4:] if len(plain_token) > 4 else "****"
            )
        except Exception:
            safe_settings["telegram_bot_token"] = "****"
    else:
        safe_settings["telegram_bot_token"] = ""
    safe_settings["telegram_chat_id"] = all_settings.get("telegram_chat_id", "")
    safe_settings["telegram_poll_interval"] = _coerce_int_range(
        all_settings.get("telegram_poll_interval", "600") or "600",
        600,
        minimum=10,
        maximum=86400,
    )

    # 读取 ui_layout_v2 布局状态
    ui_layout = settings_repo.get_ui_layout_v2()
    if not ui_layout or ui_layout.get("version") != 2:
        ui_layout = {
            "version": 2,
            "sidebar": {"collapsed": False},
            "mailbox": {"groupPanelWidth": 220, "accountPanelWidth": 280},
            "tempEmails": {"listPanelWidth": 300},
        }
    safe_settings["ui_layout_v2"] = ui_layout

    response = {"success": True, "settings": safe_settings}
    # 同时在顶层暴露 telegram 字段（兼容前端直接访问）
    response["telegram_bot_token"] = safe_settings.get("telegram_bot_token", "")
    response["telegram_chat_id"] = safe_settings.get("telegram_chat_id", "")
    response["telegram_poll_interval"] = safe_settings.get(
        "telegram_poll_interval", 600
    )

    return jsonify(response)


@login_required
def api_update_settings() -> Any:
    """更新设置"""
    # 延迟导入避免循环依赖
    from flask import current_app

    from outlook_web.services import email_push
    from outlook_web.services import graph as graph_service
    from outlook_web.services import scheduler as scheduler_service

    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return _json_error(
            "LEGACY_ERROR",
            "请求体必须是 JSON 对象",
            message_en="Request body must be a JSON object",
        )

    updated = []
    errors = []
    scheduler_reload_needed = False
    pending_operations: list[Any] = []

    def queue_setting_update(key: str, value: str) -> None:
        pending_operations.append(
            lambda key=key, value=value: settings_repo.set_setting(
                key, value, commit=False
            )
        )

    def queue_operation(op: Any) -> None:
        pending_operations.append(op)

    current_email_notification_enabled = (
        settings_repo.get_setting("email_notification_enabled", "false").lower()
        == "true"
    )
    current_email_notification_recipient = settings_repo.get_setting(
        "email_notification_recipient", ""
    ).strip()
    target_email_notification_enabled = current_email_notification_enabled
    target_email_notification_recipient = current_email_notification_recipient

    if "email_notification_enabled" in data:
        target_email_notification_enabled = _parse_bool_input(
            data.get("email_notification_enabled"),
            default=current_email_notification_enabled,
        )
    if "email_notification_recipient" in data:
        target_email_notification_recipient = str(
            data.get("email_notification_recipient") or ""
        ).strip()

    if "email_notification_enabled" in data or "email_notification_recipient" in data:
        if (
            target_email_notification_enabled
            and not target_email_notification_recipient
        ):
            return _json_error(
                "EMAIL_NOTIFICATION_RECIPIENT_REQUIRED",
                "请填写接收通知邮箱",
                message_en="Please provide a notification recipient email address",
            )
        if target_email_notification_recipient and not _is_valid_notification_email(
            target_email_notification_recipient
        ):
            return _json_error(
                "EMAIL_NOTIFICATION_RECIPIENT_INVALID",
                "接收通知邮箱格式无效",
                message_en="Invalid notification recipient email address",
            )
        if target_email_notification_enabled:
            try:
                _ensure_email_service_available()
            except email_push.EmailPushError as exc:
                return _json_error(
                    exc.code,
                    exc.message,
                    status=exc.status,
                    message_en=exc.message_en,
                    details=exc.details,
                )
        if "email_notification_enabled" in data:
            queue_setting_update(
                "email_notification_enabled",
                "true" if target_email_notification_enabled else "false",
            )
            updated.append("邮件通知开关")
            scheduler_reload_needed = True
        if "email_notification_recipient" in data:
            queue_setting_update(
                "email_notification_recipient", target_email_notification_recipient
            )
            updated.append("邮件通知接收邮箱")
            scheduler_reload_needed = True

    # 更新登录密码
    if "login_password" in data:
        new_password = data["login_password"].strip()
        if new_password:
            if not config.get_allow_login_password_change():
                return _json_error(
                    "LOGIN_PASSWORD_CHANGE_DISABLED",
                    "当前站点已禁用登录密码修改",
                    status=403,
                    message_en="Login password changes are disabled on this site",
                )
            if len(new_password) < 8:
                errors.append("密码长度至少为 8 位")
            else:
                # 哈希新密码
                hashed_password = hash_password(new_password)
                queue_setting_update("login_password", hashed_password)
                updated.append("登录密码")

    # 更新临时邮箱配置
    if "temp_mail_provider" in data:
        try:
            provider = settings_repo.validate_temp_mail_provider_name(
                data["temp_mail_provider"]
            )
        except ValueError:
            return _json_error(
                "TEMP_MAIL_PROVIDER_INVALID",
                "临时邮箱 Provider 配置无效",
                status=400,
                message_en="Invalid temp mail provider",
            )
        queue_setting_update("temp_mail_provider", provider)
        updated.append("临时邮箱 Provider")

    if "temp_mail_api_base_url" in data:
        queue_setting_update(
            "temp_mail_api_base_url", str(data["temp_mail_api_base_url"] or "").strip()
        )
        updated.append("临时邮箱 API 地址")

    if "temp_mail_api_key" in data:
        new_api_key = str(data["temp_mail_api_key"] or "").strip()
        existing_api_key = settings_repo.get_temp_mail_api_key()
        if (
            new_api_key
            and existing_api_key
            and new_api_key == _mask_secret_value(existing_api_key)
        ):
            updated.append("临时邮箱 API Key（未变更）")
        elif new_api_key:
            queue_setting_update("temp_mail_api_key", new_api_key)
            queue_setting_update("gptmail_api_key", new_api_key)
            updated.append("临时邮箱 API Key")
        else:
            updated.append("临时邮箱 API Key（空值已忽略）")

    if "temp_mail_domains" in data:
        try:
            domains = _parse_temp_mail_domains_input(data["temp_mail_domains"])
            queue_setting_update(
                "temp_mail_domains", json.dumps(domains, ensure_ascii=False)
            )
            updated.append("临时邮箱可用域名")
        except ValueError as exc:
            errors.append(str(exc))
        except (TypeError, json.JSONDecodeError):
            errors.append("temp_mail_domains 格式无效")

    if "temp_mail_default_domain" in data:
        queue_setting_update(
            "temp_mail_default_domain",
            str(data["temp_mail_default_domain"] or "").strip(),
        )
        updated.append("临时邮箱默认域名")

    if "temp_mail_prefix_rules" in data:
        try:
            prefix_rules = _parse_temp_mail_prefix_rules_input(
                data["temp_mail_prefix_rules"]
            )
            queue_setting_update(
                "temp_mail_prefix_rules", json.dumps(prefix_rules, ensure_ascii=False)
            )
            updated.append("临时邮箱前缀规则")
        except ValueError as exc:
            errors.append(str(exc))
        except (TypeError, json.JSONDecodeError):
            errors.append("temp_mail_prefix_rules 格式无效")

    # v0.3: CF Worker 独立域名配置（Tab 重构）
    if "cf_worker_domains" in data:
        try:
            domains = _parse_temp_mail_domains_input(data["cf_worker_domains"])
            queue_setting_update(
                "cf_worker_domains", json.dumps(domains, ensure_ascii=False)
            )
            updated.append("CF Worker 可用域名")
        except ValueError as exc:
            errors.append(str(exc))
        except (TypeError, json.JSONDecodeError):
            errors.append("cf_worker_domains 格式无效")

    if "cf_worker_default_domain" in data:
        queue_setting_update(
            "cf_worker_default_domain",
            str(data["cf_worker_default_domain"] or "").strip(),
        )
        updated.append("CF Worker 默认域名")

    if "cf_worker_prefix_rules" in data:
        try:
            cf_prefix_rules = _parse_temp_mail_prefix_rules_input(
                data["cf_worker_prefix_rules"]
            )
            queue_setting_update(
                "cf_worker_prefix_rules",
                json.dumps(cf_prefix_rules, ensure_ascii=False),
            )
            updated.append("CF Worker 前缀规则")
        except ValueError as exc:
            errors.append(str(exc))
        except (TypeError, json.JSONDecodeError):
            errors.append("cf_worker_prefix_rules 格式无效")

    # Cloudflare Worker 独立配置（与 GPTMail 设置完全隔离）
    if "cf_worker_base_url" in data:
        queue_setting_update(
            "cf_worker_base_url", str(data["cf_worker_base_url"] or "").strip()
        )
        updated.append("CF Worker 地址")

    if "cf_worker_admin_key" in data:
        new_cf_key = str(data["cf_worker_admin_key"] or "").strip()
        existing_cf_key = settings_repo.get_cf_worker_admin_key()
        if (
            new_cf_key
            and existing_cf_key
            and new_cf_key == _mask_secret_value(existing_cf_key)
        ):
            updated.append("CF Worker Admin Key（未变更）")
        elif new_cf_key:
            # 加密存储（与 telegram_bot_token / external_api_key 保持一致）
            encrypted_cf_key = encrypt_data(new_cf_key)
            queue_setting_update("cf_worker_admin_key", encrypted_cf_key)
            updated.append("CF Worker Admin Key")
        else:
            updated.append("CF Worker Admin Key（空值已忽略）")

    # 更新 gptmail_api_key（兼容旧字段）
    if "gptmail_api_key" in data:
        new_api_key = str(data["gptmail_api_key"] or "").strip()
        existing_api_key = settings_repo.get_temp_mail_api_key()
        if (
            new_api_key
            and existing_api_key
            and new_api_key == _mask_secret_value(existing_api_key)
        ):
            updated.append("兼容旧版临时邮箱 API Key 字段（未变更）")
        elif new_api_key:
            queue_setting_update("gptmail_api_key", new_api_key)
            updated.append("兼容旧版临时邮箱 API Key 字段（已更新）")
        else:
            # legacy 字段仅做兼容，不允许空值反向清空正式 temp_mail_api_key。
            updated.append("兼容旧版临时邮箱 API Key 字段（空值已忽略）")

    # 更新对外开放 API Key（建议加密存储）
    if "external_api_key" in data:
        new_external_api_key = str(data["external_api_key"] or "").strip()
        existing_external_api_key = settings_repo.get_external_api_key()
        if (
            new_external_api_key
            and existing_external_api_key
            and new_external_api_key == _mask_secret_value(existing_external_api_key)
        ):
            updated.append("对外 API Key（未变更）")
        elif new_external_api_key:
            encrypted_key = encrypt_data(new_external_api_key)
            queue_setting_update("external_api_key", encrypted_key)
            updated.append("对外 API Key")
        else:
            queue_setting_update("external_api_key", "")
            updated.append("对外 API Key（已清空）")

    # P2：对外 API 多 Key 配置
    if "external_api_keys" in data:
        raw_items = data["external_api_keys"]
        if not isinstance(raw_items, list):
            errors.append("external_api_keys 必须是数组")
        else:
            existing_keys = {
                int(item["id"]): item
                for item in external_api_keys_repo.list_external_api_keys(
                    include_disabled=True
                )
            }
            normalized_items: list[dict[str, Any]] = []
            seen_names: set[str] = set()
            for index, item in enumerate(raw_items):
                if not isinstance(item, dict):
                    errors.append(f"external_api_keys[{index}] 必须是对象")
                    continue

                key_id_raw = item.get("id")
                key_id = None
                if key_id_raw not in (None, ""):
                    try:
                        key_id = int(key_id_raw)
                    except (ValueError, TypeError):
                        errors.append(f"external_api_keys[{index}].id 无效")
                        continue
                    if key_id not in existing_keys:
                        errors.append(f"external_api_keys[{index}].id 不存在")
                        continue

                name = str(item.get("name") or "").strip()
                if not name:
                    errors.append(f"external_api_keys[{index}].name 不能为空")
                    continue
                name_key = name.lower()
                if name_key in seen_names:
                    errors.append(f"external_api_keys[{index}].name 重复")
                    continue
                seen_names.add(name_key)

                api_key_value = item.get("api_key")
                if api_key_value is not None:
                    api_key_value = str(api_key_value).strip()

                if key_id is None and not api_key_value:
                    errors.append(f"external_api_keys[{index}].api_key 不能为空")
                    continue

                existing = existing_keys.get(key_id) if key_id is not None else None
                if existing and api_key_value == existing.get("api_key_masked"):
                    api_key_value = None

                allowed_emails = _parse_allowed_emails_input(item.get("allowed_emails"))
                if (
                    item.get("allowed_emails") not in (None, "", [])
                    and not allowed_emails
                ):
                    errors.append(
                        f"external_api_keys[{index}].allowed_emails 至少包含一个合法邮箱"
                    )
                    continue

                normalized_items.append(
                    {
                        "id": key_id,
                        "name": name,
                        "api_key": api_key_value,
                        "allowed_emails": allowed_emails,
                        "pool_access": _parse_bool_input(
                            item.get("pool_access"), default=False
                        ),
                        "enabled": _parse_bool_input(item.get("enabled"), default=True),
                    }
                )

            if not errors:
                queue_operation(
                    lambda normalized_items=normalized_items: external_api_keys_repo.replace_external_api_keys(
                        normalized_items, commit=False
                    )
                )
                updated.append("对外 API 多 Key 配置")

    # P1：公网模式安全配置
    if "external_api_public_mode" in data:
        val = str(data["external_api_public_mode"]).lower()
        if val in ("true", "false"):
            queue_setting_update("external_api_public_mode", val)
            updated.append("对外 API 公网模式")
        else:
            errors.append("公网模式必须是 true 或 false")

    if "external_api_ip_whitelist" in data:
        raw = data["external_api_ip_whitelist"]
        if isinstance(raw, list):
            whitelist_str = json.dumps(raw, ensure_ascii=False)
        else:
            whitelist_str = str(raw).strip()
        # 简单校验 JSON 数组格式
        try:
            parsed = json.loads(whitelist_str)
            if not isinstance(parsed, list):
                errors.append("IP 白名单必须是 JSON 数组格式")
            else:
                queue_setting_update("external_api_ip_whitelist", whitelist_str)
                updated.append("对外 API IP 白名单")
        except (json.JSONDecodeError, TypeError):
            errors.append("IP 白名单格式无效（应为 JSON 数组）")

    if "external_api_rate_limit_per_minute" in data:
        try:
            limit = int(data["external_api_rate_limit_per_minute"])
            if limit < 1 or limit > 10000:
                errors.append("限流阈值必须在 1-10000 之间")
            else:
                queue_setting_update("external_api_rate_limit_per_minute", str(limit))
                updated.append("对外 API 限流阈值")
        except (ValueError, TypeError):
            errors.append("限流阈值必须是数字")

    if "external_api_disable_raw_content" in data:
        val = str(data["external_api_disable_raw_content"]).lower()
        if val in ("true", "false"):
            queue_setting_update("external_api_disable_raw_content", val)
            updated.append("对外 API 禁用 raw 端点")
        else:
            errors.append("禁用 raw 端点必须是 true 或 false")

    if "external_api_disable_wait_message" in data:
        val = str(data["external_api_disable_wait_message"]).lower()
        if val in ("true", "false"):
            queue_setting_update("external_api_disable_wait_message", val)
            updated.append("对外 API 禁用 wait-message 端点")
        else:
            errors.append("禁用 wait-message 端点必须是 true 或 false")

    if "pool_external_enabled" in data:
        val = str(data["pool_external_enabled"]).lower()
        if val in ("true", "false"):
            queue_setting_update("pool_external_enabled", val)
            updated.append("external pool 总开关")
        else:
            errors.append("external pool 总开关必须是 true 或 false")

    if "external_api_disable_pool_claim_random" in data:
        val = str(data["external_api_disable_pool_claim_random"]).lower()
        if val in ("true", "false"):
            queue_setting_update("external_api_disable_pool_claim_random", val)
            updated.append("对外 API 禁用 pool claim-random")
        else:
            errors.append("禁用 pool claim-random 必须是 true 或 false")

    if "external_api_disable_pool_claim_release" in data:
        val = str(data["external_api_disable_pool_claim_release"]).lower()
        if val in ("true", "false"):
            queue_setting_update("external_api_disable_pool_claim_release", val)
            updated.append("对外 API 禁用 pool claim-release")
        else:
            errors.append("禁用 pool claim-release 必须是 true 或 false")

    if "external_api_disable_pool_claim_complete" in data:
        val = str(data["external_api_disable_pool_claim_complete"]).lower()
        if val in ("true", "false"):
            queue_setting_update("external_api_disable_pool_claim_complete", val)
            updated.append("对外 API 禁用 pool claim-complete")
        else:
            errors.append("禁用 pool claim-complete 必须是 true 或 false")

    if "external_api_disable_pool_stats" in data:
        val = str(data["external_api_disable_pool_stats"]).lower()
        if val in ("true", "false"):
            queue_setting_update("external_api_disable_pool_stats", val)
            updated.append("对外 API 禁用 pool stats")
        else:
            errors.append("禁用 pool stats 必须是 true 或 false")

    # 更新刷新周期
    if "refresh_interval_days" in data:
        try:
            days = int(data["refresh_interval_days"])
            if days < 1 or days > 90:
                errors.append("刷新周期必须在 1-90 天之间")
            else:
                queue_setting_update("refresh_interval_days", str(days))
                updated.append("刷新周期")
        except ValueError:
            errors.append("刷新周期必须是数字")

    # 更新刷新间隔
    if "refresh_delay_seconds" in data:
        try:
            seconds = int(data["refresh_delay_seconds"])
            if seconds < 0 or seconds > 60:
                errors.append("刷新间隔必须在 0-60 秒之间")
            else:
                queue_setting_update("refresh_delay_seconds", str(seconds))
                updated.append("刷新间隔")
        except ValueError:
            errors.append("刷新间隔必须是数字")

    # 更新 Cron 表达式
    if "refresh_cron" in data:
        cron_expr = data["refresh_cron"].strip()
        if cron_expr:
            try:
                from croniter import croniter

                croniter(cron_expr, datetime.now())
                queue_setting_update("refresh_cron", cron_expr)
                updated.append("Cron 表达式")
                scheduler_reload_needed = True
            except ImportError:
                errors.append("croniter 库未安装")
            except Exception as e:
                errors.append(f"Cron 表达式无效: {str(e)}")

    # 更新刷新策略
    if "use_cron_schedule" in data:
        use_cron = str(data["use_cron_schedule"]).lower()
        if use_cron in ("true", "false"):
            queue_setting_update("use_cron_schedule", use_cron)
            updated.append("刷新策略")
            scheduler_reload_needed = True
        else:
            errors.append("刷新策略必须是 true 或 false")

    # 更新定时刷新开关
    if "enable_scheduled_refresh" in data:
        enable = str(data["enable_scheduled_refresh"]).lower()
        if enable in ("true", "false"):
            queue_setting_update("enable_scheduled_refresh", enable)
            updated.append("定时刷新开关")
            scheduler_reload_needed = True
        else:
            errors.append("定时刷新开关必须是 true 或 false")

    # 更新轮询配置
    if "enable_auto_polling" in data:
        enable_polling = str(data["enable_auto_polling"]).lower()
        if enable_polling in ("true", "false"):
            queue_setting_update("enable_auto_polling", enable_polling)
            updated.append("自动轮询开关")
        else:
            errors.append("自动轮询开关必须是 true 或 false")

    if "polling_interval" in data:
        try:
            interval = int(data["polling_interval"])
            if interval < 3 or interval > 300:
                errors.append("轮询间隔必须在 3-300 秒之间")
            else:
                queue_setting_update("polling_interval", str(interval))
                updated.append("轮询间隔")
        except ValueError:
            errors.append("轮询间隔必须是数字")

    if "polling_count" in data:
        try:
            count = int(data["polling_count"])
            if count < 0 or count > 100:
                errors.append("轮询次数必须在 0-100 次之间（0 表示持续轮询）")
            else:
                queue_setting_update("polling_count", str(count))
                updated.append("轮询次数")
        except ValueError:
            errors.append("轮询次数必须是数字")

    # [Phase 3 deprecated] 简洁模式自动轮询配置 — 保留写入，向后兼容
    if "enable_compact_auto_poll" in data:
        enable_compact = str(data["enable_compact_auto_poll"]).lower()
        if enable_compact in ("true", "false"):
            queue_setting_update("enable_compact_auto_poll", enable_compact)
            updated.append("简洁轮询开关")
        else:
            errors.append("简洁模式自动轮询开关必须是 true 或 false")

    if "compact_poll_interval" in data:
        try:
            compact_interval = int(data["compact_poll_interval"])
            if compact_interval < 3 or compact_interval > 60:
                errors.append("简洁模式轮询间隔必须在 3-60 秒之间")
            else:
                queue_setting_update("compact_poll_interval", str(compact_interval))
                updated.append("简洁轮询间隔")
        except (ValueError, TypeError):
            errors.append("简洁模式轮询间隔必须是数字")

    if "compact_poll_max_count" in data:
        try:
            compact_max_count = int(data["compact_poll_max_count"])
            if compact_max_count < 0 or compact_max_count > 100:
                errors.append("简洁模式最多轮询次数必须在 0-100 之间")
            else:
                queue_setting_update("compact_poll_max_count", str(compact_max_count))
                updated.append("简洁轮询次数")
        except (ValueError, TypeError):
            errors.append("简洁模式最多轮询次数必须是数字")

    # Telegram 推送配置
    if "telegram_poll_interval" in data:
        try:
            tg_interval = int(data["telegram_poll_interval"])
            if tg_interval < 10 or tg_interval > 86400:
                errors.append("Telegram 轮询间隔必须在 10-86400 秒之间")
            else:
                queue_setting_update("telegram_poll_interval", str(tg_interval))
                updated.append("Telegram 轮询间隔")
                scheduler_reload_needed = True
        except (ValueError, TypeError):
            errors.append("Telegram 轮询间隔必须是数字")

    if "telegram_bot_token" in data:
        tg_token = str(data["telegram_bot_token"]).strip()
        if tg_token and not tg_token.startswith("****"):
            encrypted_token = encrypt_data(tg_token)
            queue_setting_update("telegram_bot_token", encrypted_token)
            updated.append("Telegram Bot Token")
        elif not tg_token:
            queue_setting_update("telegram_bot_token", "")
            updated.append("Telegram Bot Token（已清空）")
        else:
            # 脱敏占位符（****xxx），跳过不覆盖
            updated.append("Telegram Bot Token（未变更）")

    if "telegram_chat_id" in data:
        tg_chat_id = str(data["telegram_chat_id"]).strip()
        queue_setting_update("telegram_chat_id", tg_chat_id)
        updated.append("Telegram Chat ID")

    # 更新 ui_layout_v2 布局状态
    if "ui_layout_v2" in data:
        new_layout = data["ui_layout_v2"]
        if not isinstance(new_layout, dict):
            errors.append("ui_layout_v2 必须是 JSON 对象")
        elif new_layout.get("version") != 2:
            errors.append("ui_layout_v2.version 必须为 2")
        else:
            queue_setting_update(
                "ui_layout_v2", json.dumps(new_layout, ensure_ascii=False)
            )
            updated.append("界面布局状态")

    if errors:
        return _json_error(
            "LEGACY_ERROR",
            "；".join(errors),
            message_en="Invalid settings payload",
        )

    if updated:
        db = get_db()
        try:
            db.execute("BEGIN")
            for op in pending_operations:
                result = op()
                if result is False:
                    raise RuntimeError("settings_update_failed")
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            return _json_error(
                "INTERNAL_ERROR",
                "设置保存失败，请重试",
                status=500,
                message_en="Failed to save settings. Please try again",
            )

        scheduler_reloaded = None
        email_notification_just_enabled = (
            not current_email_notification_enabled
        ) and target_email_notification_enabled
        if email_notification_just_enabled:
            try:
                from outlook_web.services import notification_dispatch

                notification_dispatch.bootstrap_channel_cursors(
                    notification_dispatch.CHANNEL_EMAIL
                )
            except Exception:
                pass

        if scheduler_reload_needed:
            try:
                scheduler = scheduler_service.get_scheduler_instance()
                if scheduler:
                    # FD-00007 / TDD-00007：调度器 Job 在后台线程运行，必须传入真实 Flask app 实例；
                    # 避免将 current_app(LocalProxy) 直接作为 job 参数，导致后续执行时报“Working outside of application context”。
                    app_obj = current_app._get_current_object()
                    scheduler_service.configure_scheduler_jobs(
                        scheduler,
                        app_obj,
                        graph_service.test_refresh_token_with_rotation,
                    )
                    scheduler_reloaded = True
                else:
                    scheduler_reloaded = False
            except Exception:
                scheduler_reloaded = False

        try:
            details = json.dumps(
                {
                    "updated": updated,
                    "scheduler_reload_needed": scheduler_reload_needed,
                    "scheduler_reloaded": scheduler_reloaded,
                },
                ensure_ascii=False,
            )
        except Exception:
            details = f"updated={','.join(updated)}"
        log_audit("update", "settings", None, details)
        return jsonify(
            {
                "success": True,
                "message": f"已更新：{', '.join(updated)}",
                "message_en": "Settings updated successfully",
                "scheduler_reloaded": scheduler_reloaded,
            }
        )
    else:
        return _json_error(
            "LEGACY_ERROR",
            "没有需要更新的设置",
            message_en="No settings changes were provided",
        )


@login_required
def api_validate_cron() -> Any:
    """验证 Cron 表达式"""
    try:
        from croniter import croniter
    except ImportError:
        return _json_error(
            "CRONITER_NOT_INSTALLED",
            "croniter 库未安装，请运行: pip install croniter",
            status=500,
            message_en="croniter is not installed. Please run: pip install croniter",
        )

    data = request.json
    cron_expr = data.get("cron_expression", "").strip()

    if not cron_expr:
        return _json_error(
            "CRON_EXPRESSION_REQUIRED",
            "Cron 表达式不能为空",
            status=400,
            message_en="Cron expression is required",
            extra={"valid": False},
        )

    try:
        base_time = datetime.now()
        cron = croniter(cron_expr, base_time)

        next_run = cron.get_next(datetime)

        future_runs = []
        temp_cron = croniter(cron_expr, base_time)
        for _ in range(5):
            future_runs.append(temp_cron.get_next(datetime).isoformat())

        return jsonify(
            {
                "success": True,
                "valid": True,
                "next_run": next_run.isoformat(),
                "future_runs": future_runs,
            }
        )
    except Exception as e:
        return _json_error(
            "CRON_EXPRESSION_INVALID",
            "Cron 表达式无效",
            status=400,
            message_en="Invalid cron expression",
            details=str(e),
            extra={"valid": False},
        )


@login_required
def api_test_email() -> Any:
    """发送邮件通知测试消息。按“先保存，再测试”规则，仅使用已保存的接收邮箱。"""
    from outlook_web.services import email_push

    try:
        recipient = email_push.send_test_email()
    except email_push.EmailPushError as exc:
        return _json_error(
            exc.code,
            exc.message,
            status=exc.status,
            message_en=exc.message_en,
            details=exc.details,
        )

    log_audit("email_notification_test", "settings", None, f"recipient={recipient}")
    return jsonify(
        {
            "success": True,
            "message": "测试邮件已提交，请检查收件箱",
            "message_en": "Test email accepted. Please check your inbox",
            "recipient": recipient,
        }
    )


@login_required
def api_sync_cf_worker_domains() -> Any:
    """
    从 CF Worker 的 /open_api/settings 接口同步域名列表到本地配置。

    成功后自动写入：
    - cf_worker_domains：CF Worker 上配置的所有域名（v0.3: 独立 key，不覆盖 GPTMail）
    - cf_worker_default_domain：CF Worker 的默认域名（defaultDomains 第一个）

    返回：{"success": True, "domains": [...], "default_domain": "...", "message": "..."}
    """
    from outlook_web.services.temp_mail_provider_cf import CloudflareTempMailProvider
    from outlook_web.services.temp_mail_provider_factory import (
        TempMailProviderFactoryError,
    )

    cf_base_url = settings_repo.get_cf_worker_base_url()
    if not cf_base_url:
        return _json_error(
            "CF_WORKER_NOT_CONFIGURED",
            "请先配置 CF Worker 地址（cf_worker_base_url）",
            status=400,
        )

    try:
        provider = CloudflareTempMailProvider()
        result = provider.get_cf_worker_domains()
    except Exception as exc:
        return _json_error(
            "CF_WORKER_SYNC_FAILED",
            f"CF Worker 域名同步失败: {exc}",
            status=502,
        )

    if not result.get("success"):
        return _json_error(
            result.get("error_code") or "CF_WORKER_SYNC_FAILED",
            result.get("error") or "CF Worker 域名同步失败",
            status=502,
        )

    domains: list[str] = result.get("domains") or []
    default_domain: str = result.get("default_domain") or ""

    if not domains:
        return _json_error(
            "CF_WORKER_NO_DOMAINS",
            "CF Worker 未返回任何域名，请检查 CF Worker 配置",
            status=502,
        )

    # 构建 cf_worker_domains 格式（带 enabled/is_default 标记）
    # v0.3: 同步到独立的 cf_worker_* key，不覆盖 GPTMail 的 temp_mail_* key
    domains_payload = [
        {
            "name": d,
            "enabled": True,
        }
        for d in domains
    ]
    db = get_db()
    try:
        db.execute("BEGIN")
        settings_repo.set_setting(
            "cf_worker_domains",
            __import__("json").dumps(domains_payload, ensure_ascii=False),
            commit=False,
        )
        if default_domain:
            settings_repo.set_setting(
                "cf_worker_default_domain", default_domain, commit=False
            )
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        return _json_error(
            "INTERNAL_ERROR",
            f"域名同步写入失败: {exc}",
            status=500,
        )

    log_audit(
        "sync",
        "settings",
        None,
        f"cf_worker_domains_synced domains={','.join(domains)} default={default_domain}",
    )
    return jsonify(
        {
            "success": True,
            "domains": domains,
            "default_domain": default_domain,
            "title": result.get("title") or "",
            "version": result.get("version") or "",
            "message": f"已同步 {len(domains)} 个域名，默认域名：{default_domain or '（未指定）'}",
        }
    )


@login_required
def api_test_telegram() -> Any:
    """发送 Telegram 测试消息，验证 bot_token + chat_id 配置是否正确"""
    from outlook_web.services.telegram_push import _send_telegram_message

    bot_token_raw = settings_repo.get_setting("telegram_bot_token", "")
    chat_id = settings_repo.get_setting("telegram_chat_id", "")

    if not bot_token_raw or not chat_id:
        return _json_error(
            "TELEGRAM_NOT_CONFIGURED",
            "请先配置 Telegram Bot Token 和 Chat ID",
            message_en="Please configure Telegram Bot Token and Chat ID first",
        )

    bot_token = (
        decrypt_data(bot_token_raw) if is_encrypted(bot_token_raw) else bot_token_raw
    )

    ok = _send_telegram_message(
        bot_token, chat_id, "✅ Outlook Email Plus 测试消息：配置正确！"
    )
    if ok:
        log_audit("telegram_test", "settings", None, "测试消息发送成功")
        return jsonify(
            {
                "success": True,
                "message": "测试消息已发送，请检查 Telegram",
                "message_en": "Test message sent successfully. Please check Telegram",
            }
        )
    return _json_error(
        "TELEGRAM_TEST_SEND_FAILED",
        "发送失败，请检查 Bot Token 和 Chat ID 是否正确",
        message_en="Failed to send test message. Please check whether the Bot Token and Chat ID are correct",
    )
