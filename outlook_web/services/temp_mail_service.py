from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from typing import Any

from outlook_web.repositories import temp_emails as temp_emails_repo
from outlook_web.services.temp_mail_provider_factory import (
    TempMailProviderFactoryError,
    get_temp_mail_provider,
)
from outlook_web.services.temp_mail_provider_custom import TempMailProviderReadError
from outlook_web.services.verification_extractor import (
    apply_confidence_gate,
    extract_verification_info_with_options,
)

TEMP_MAIL_SOURCE = temp_emails_repo.DEFAULT_TEMP_MAIL_SOURCE
TEMP_MAIL_METHOD = "Temp Mail"


class TempMailError(Exception):
    def __init__(self, code: str, message: str, *, status: int = 400, data: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.data = data


def _utc_iso_from_timestamp(value: Any, fallback: str = "") -> str:
    try:
        timestamp = int(value or 0)
    except (TypeError, ValueError):
        timestamp = 0
    if timestamp > 0:
        return (
            datetime.fromtimestamp(timestamp, tz=timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    return str(fallback or "")


def _mailbox_from_record(record: dict[str, Any]) -> dict[str, Any]:
    mailbox = temp_emails_repo.build_temp_mailbox_public_dto(record)
    mailbox["created_by"] = "task" if mailbox["mailbox_type"] == "task" else "user"
    return mailbox


def _message_summary(
    email_addr: str, row: dict[str, Any], *, method: str = "Temp Mail"
) -> dict[str, Any]:
    created_at = _utc_iso_from_timestamp(
        row.get("timestamp"), row.get("created_at") or ""
    )
    content_preview = str(row.get("content") or "")[:200]
    return {
        "id": str(row.get("message_id") or ""),
        "email_address": email_addr,
        "from_address": str(row.get("from_address") or ""),
        "subject": str(row.get("subject") or "无主题"),
        "content_preview": content_preview,
        "has_html": bool(row.get("has_html")),
        "timestamp": int(row.get("timestamp") or 0),
        "created_at": created_at,
        "method": method,
    }


def _message_detail(
    email_addr: str, row: dict[str, Any], *, method: str = "Temp Mail"
) -> dict[str, Any]:
    created_at = _utc_iso_from_timestamp(
        row.get("timestamp"), row.get("created_at") or ""
    )
    return {
        "id": str(row.get("message_id") or ""),
        "email_address": email_addr,
        "from_address": str(row.get("from_address") or ""),
        "to_address": email_addr,
        "subject": str(row.get("subject") or "无主题"),
        "content": str(row.get("content") or ""),
        "html_content": str(row.get("html_content") or ""),
        "raw_content": str(row.get("raw_content") or ""),
        "timestamp": int(row.get("timestamp") or 0),
        "created_at": created_at,
        "has_html": bool(row.get("has_html") or row.get("html_content")),
        "method": method,
    }


class TempMailService:
    def __init__(
        self, provider: Any | None = None, provider_factory: Any | None = None
    ):
        self._provider = provider
        self._provider_factory = provider_factory or get_temp_mail_provider

    def _provider_error(
        self, exc: TempMailProviderFactoryError, *, purpose: str
    ) -> TempMailError:
        if purpose == "options":
            return TempMailError(
                "TEMP_MAIL_OPTIONS_UNAVAILABLE", exc.message, status=503, data=exc.data
            )
        return TempMailError(exc.code, exc.message, status=exc.status, data=exc.data)

    def _get_provider(
        self,
        *,
        provider_name: str | None = None,
        mailbox: dict[str, Any] | None = None,
        purpose: str = "runtime",
    ):
        if self._provider is not None:
            return self._provider
        resolved_provider_name = (
            str(
                provider_name
                or (mailbox or {}).get("provider_name")
                or ((mailbox or {}).get("meta") or {}).get("provider_name")
                or ""
            ).strip()
            or None
        )
        try:
            return self._provider_factory(resolved_provider_name)
        except TempMailProviderFactoryError as exc:
            raise self._provider_error(exc, purpose=purpose) from exc

    def _get_mailbox_descriptor(
        self, email_or_mailbox: str | dict[str, Any]
    ) -> dict[str, Any]:
        if isinstance(email_or_mailbox, dict):
            if email_or_mailbox.get("kind") == temp_emails_repo.TEMP_MAIL_KIND:
                return email_or_mailbox
            if email_or_mailbox.get("record"):
                return temp_emails_repo.build_temp_mailbox_descriptor(
                    email_or_mailbox["record"]
                )
            if email_or_mailbox.get("email"):
                return temp_emails_repo.build_temp_mailbox_descriptor(email_or_mailbox)

        email_addr = str(email_or_mailbox or "").strip()
        descriptor = temp_emails_repo.get_temp_email_by_address(
            email_addr, view="descriptor"
        )
        if not descriptor:
            raise TempMailError("TEMP_EMAIL_NOT_FOUND", "临时邮箱不存在", status=404)
        return descriptor

    def _provider_read_failed(
        self,
        exc: TempMailProviderReadError | None,
        *,
        mailbox: dict[str, Any],
        operation: str,
        message_id: str | None = None,
    ) -> TempMailError:
        data = {
            "provider_name": str(
                mailbox.get("provider_name")
                or ((mailbox.get("meta") or {}).get("provider_name") or "")
            ),
            "email": str(mailbox.get("email") or ""),
            "operation": operation,
            "message_id": message_id,
        }
        if exc is not None:
            data["provider_error_code"] = exc.code
            data["provider_error_message"] = exc.message
            if isinstance(exc.data, dict):
                data.update(exc.data)
        else:
            data["provider_error_code"] = "UPSTREAM_BAD_PAYLOAD"
            data["provider_error_message"] = (
                "temp mail provider returned empty read result"
            )

        return TempMailError(
            "TEMP_EMAIL_UPSTREAM_READ_FAILED",
            "临时邮箱上游读取失败",
            status=502,
            data=data,
        )

    def _create_mailbox(
        self, provider: Any, *, prefix: str | None, domain: str | None
    ) -> dict[str, Any]:
        if hasattr(provider, "create_mailbox"):
            return provider.create_mailbox(prefix=prefix, domain=domain)
        return provider.generate_mailbox(prefix=prefix, domain=domain)

    def _create_or_load_mailbox_record(
        self,
        *,
        email_addr: str,
        mailbox_type: str = "user",
        visible_in_ui: bool = True,
        source: str = TEMP_MAIL_SOURCE,
        prefix: str | None = None,
        domain: str | None = None,
        task_token: str | None = None,
        consumer_key: str | None = None,
        caller_id: str | None = None,
        task_id: str | None = None,
        meta: dict[str, Any] | None = None,
        provider_name: str | None = None,
        status: str = "active",
        failure_code: str = "TEMP_EMAIL_CREATE_FAILED",
        failure_message: str = "临时邮箱创建失败",
        failure_status: int = 502,
        allow_existing: bool = True,
    ) -> dict[str, Any]:
        normalized_email = str(email_addr or "").strip()
        created = temp_emails_repo.create_temp_email(
            email_addr=normalized_email,
            mailbox_type=mailbox_type,
            visible_in_ui=visible_in_ui,
            source=source,
            prefix=prefix,
            domain=domain,
            task_token=task_token,
            consumer_key=consumer_key,
            caller_id=caller_id,
            task_id=task_id,
            meta=meta,
            provider_name=provider_name,
            status=status,
        )
        if not created:
            existing = temp_emails_repo.get_temp_email_by_address(normalized_email)
            if existing:
                if not allow_existing:
                    raise TempMailError("TEMP_EMAIL_EXISTS", "邮箱已存在", status=409)
                return _mailbox_from_record(existing)
            raise TempMailError(failure_code, failure_message, status=failure_status)
        return _mailbox_from_record(self.get_mailbox(normalized_email))

    def get_options(self) -> dict[str, Any]:
        provider = self._get_provider(purpose="options")
        options = provider.get_options()
        options.setdefault("provider_name", str(options.get("provider") or ""))
        options.setdefault("provider_label", "temp_mail")
        return options

    def _validate_prefix_and_domain(
        self,
        prefix: str | None,
        domain: str | None,
        *,
        provider_name: str | None = None,
    ) -> tuple[str | None, str | None]:
        if provider_name:
            # 指定了特定 provider：使用该 provider 的域名配置进行校验
            target_provider = self._get_provider(
                provider_name=provider_name, purpose="options"
            )
            options = target_provider.get_options()
            options.setdefault("provider_name", str(options.get("provider") or ""))
            options.setdefault("provider_label", "temp_mail")
        else:
            options = self.get_options()
        normalized_prefix = str(prefix or "").strip() or None
        normalized_domain = str(domain or "").strip() or None

        if normalized_prefix:
            rules = options.get("prefix_rules") or {}
            min_length = int(rules.get("min_length", 1))
            max_length = int(rules.get("max_length", 32))
            pattern = str(rules.get("pattern") or r"^[a-z0-9][a-z0-9._-]*$")
            if (
                len(normalized_prefix) < min_length
                or len(normalized_prefix) > max_length
            ):
                raise TempMailError("PREFIX_INVALID", "前缀长度不符合要求", status=400)
            if not re.match(pattern, normalized_prefix):
                raise TempMailError("PREFIX_INVALID", "前缀格式非法", status=400)

        if normalized_domain:
            allowed_domains = {
                str(item.get("name") or "").strip()
                for item in (options.get("domains") or [])
                if bool(item.get("enabled", True))
            }
            if allowed_domains and normalized_domain not in allowed_domains:
                raise TempMailError(
                    "DOMAIN_NOT_AVAILABLE", "指定域名不可用", status=400
                )

        return normalized_prefix, normalized_domain

    def list_user_mailboxes(self) -> list[dict[str, Any]]:
        return temp_emails_repo.load_temp_emails(
            visible_only=True,
            mailbox_type="user",
            status="active",
            view="public",
        )

    def get_mailbox(self, email_addr: str, *, view: str = "record") -> dict[str, Any]:
        record = temp_emails_repo.get_temp_email_by_address(email_addr, view=view)
        if not record:
            raise TempMailError("TEMP_EMAIL_NOT_FOUND", "临时邮箱不存在", status=404)
        return record

    def delete_mailbox(self, email_or_mailbox: str | dict[str, Any]) -> bool:
        mailbox = self._get_mailbox_descriptor(email_or_mailbox)
        capabilities = (mailbox.get("meta") or {}).get("provider_capabilities") or {}
        if bool(capabilities.get("delete_mailbox")):
            provider = self._get_provider(mailbox=mailbox)
            if not provider.delete_mailbox(mailbox):
                raise TempMailError("TEMP_EMAIL_DELETE_FAILED", "删除失败", status=502)
        email_addr = str(mailbox.get("email") or "")
        if not temp_emails_repo.delete_temp_email(email_addr):
            raise TempMailError("TEMP_EMAIL_DELETE_FAILED", "删除失败", status=500)
        return True

    def generate_user_mailbox(
        self,
        *,
        prefix: str | None = None,
        domain: str | None = None,
        provider_name: str | None = None,
    ) -> dict[str, Any]:
        # 标准化 provider_name（空字符串视为未指定，回退到全局设置）
        normalized_pn = str(provider_name or "").strip() or None
        normalized_prefix, normalized_domain = self._validate_prefix_and_domain(
            prefix, domain, provider_name=normalized_pn
        )
        provider = self._get_provider(provider_name=normalized_pn, purpose="runtime")
        result = self._create_mailbox(
            provider, prefix=normalized_prefix, domain=normalized_domain
        )
        if not result.get("success"):
            error_code = (
                str(result.get("error_code") or "TEMP_EMAIL_CREATE_FAILED").strip()
                or "TEMP_EMAIL_CREATE_FAILED"
            )
            raise TempMailError(
                error_code,
                str(result.get("error") or "生成临时邮箱失败"),
                status=502,
            )
        email_addr = str(result.get("email") or "").strip()
        if not email_addr:
            raise TempMailError(
                "TEMP_EMAIL_CREATE_FAILED", "临时邮箱创建失败：缺少邮箱地址", status=502
            )
        mailbox = self._create_or_load_mailbox_record(
            email_addr=email_addr,
            mailbox_type="user",
            visible_in_ui=True,
            source=TEMP_MAIL_SOURCE,
            prefix=normalized_prefix,
            domain=normalized_domain,
            meta=result.get("meta"),
            provider_name=result.get("provider_name"),
            failure_code="TEMP_EMAIL_CREATE_FAILED",
            failure_message="临时邮箱创建失败",
            failure_status=502,
            allow_existing=False,
        )
        return mailbox

    def import_user_mailbox(
        self, email_addr: str, *, allow_local_fallback: bool = True
    ) -> dict[str, Any]:
        normalized_email = str(email_addr or "").strip()
        if not normalized_email:
            raise TempMailError("INVALID_PARAM", "邮箱地址不能为空", status=400)

        existing = temp_emails_repo.get_temp_email_by_address(normalized_email)
        if existing:
            return _mailbox_from_record(existing)

        prefix = None
        domain = None
        if "@" in normalized_email:
            prefix, domain = normalized_email.rsplit("@", 1)

        provider = None
        provider_name = None
        try:
            provider = self._get_provider(purpose="runtime")
            provider_name = (
                str(getattr(provider, "provider_name", "") or "").strip() or None
            )
        except TempMailError:
            if not allow_local_fallback:
                raise

        if provider is not None:
            probe_mailbox = {
                "kind": temp_emails_repo.TEMP_MAIL_KIND,
                "email": normalized_email,
                "provider_name": provider_name,
                "mailbox_type": "user",
                "status": "active",
                "visible_in_ui": True,
                "source": TEMP_MAIL_SOURCE,
                "prefix": prefix,
                "domain": domain,
                "meta": {"provider_name": provider_name} if provider_name else {},
            }
            try:
                probe_result = provider.list_messages(probe_mailbox)
            except Exception:
                probe_result = None
            else:
                # BUG-02: probe_result=[] 也会被误判为“上游存在”，导致导入假成功。
                # 这里收紧：必须探测到至少 1 条有效消息才允许落库。
                if isinstance(probe_result, list) and len(probe_result) > 0:
                    return self._create_or_load_mailbox_record(
                        email_addr=normalized_email,
                        mailbox_type="user",
                        visible_in_ui=True,
                        source=TEMP_MAIL_SOURCE,
                        prefix=prefix,
                        domain=domain,
                        meta=probe_mailbox["meta"],
                        provider_name=provider_name,
                    )

            try:
                create_result = self._create_mailbox(
                    provider, prefix=prefix, domain=domain
                )
            except Exception:
                create_result = None
            if isinstance(create_result, dict) and create_result.get("success"):
                created_email = (
                    str(create_result.get("email") or "").strip() or normalized_email
                )
                return self._create_or_load_mailbox_record(
                    email_addr=created_email,
                    mailbox_type="user",
                    visible_in_ui=True,
                    source=TEMP_MAIL_SOURCE,
                    meta=create_result.get("meta"),
                    provider_name=create_result.get("provider_name") or provider_name,
                )

        if not allow_local_fallback:
            raise TempMailError(
                "TEMP_EMAIL_CREATE_FAILED", "临时邮箱导入失败", status=502
            )

        return self._create_or_load_mailbox_record(
            email_addr=normalized_email,
            mailbox_type="user",
            visible_in_ui=True,
            source=TEMP_MAIL_SOURCE,
            prefix=prefix,
            domain=domain,
            meta={"provider_name": provider_name} if provider_name else None,
            provider_name=provider_name,
        )

    def _generate_task_token(self) -> str:
        for _ in range(10):
            token = f"tmptask_{secrets.token_urlsafe(18)}"
            if not temp_emails_repo.get_temp_email_by_task_token(token):
                return token
        raise TempMailError("TEMP_EMAIL_CREATE_FAILED", "任务令牌生成失败", status=500)

    def apply_task_mailbox(
        self,
        *,
        consumer_key: str,
        caller_id: str,
        task_id: str,
        prefix: str | None = None,
        domain: str | None = None,
    ) -> dict[str, Any]:
        if not caller_id:
            raise TempMailError("INVALID_PARAM", "caller_id 必填", status=400)
        if not task_id:
            raise TempMailError("INVALID_PARAM", "task_id 必填", status=400)
        normalized_prefix, normalized_domain = self._validate_prefix_and_domain(
            prefix, domain
        )
        provider = self._get_provider(purpose="runtime")
        result = self._create_mailbox(
            provider, prefix=normalized_prefix, domain=normalized_domain
        )
        if not result.get("success"):
            error_code = (
                str(result.get("error_code") or "TEMP_EMAIL_CREATE_FAILED").strip()
                or "TEMP_EMAIL_CREATE_FAILED"
            )
            raise TempMailError(
                error_code,
                str(result.get("error") or "生成临时邮箱失败"),
                status=502,
            )
        email_addr = str(result.get("email") or "").strip()
        task_token = self._generate_task_token()
        mailbox = self._create_or_load_mailbox_record(
            email_addr=email_addr,
            mailbox_type="task",
            visible_in_ui=False,
            source=TEMP_MAIL_SOURCE,
            prefix=normalized_prefix,
            domain=normalized_domain,
            task_token=task_token,
            consumer_key=consumer_key,
            caller_id=caller_id,
            task_id=task_id,
            meta=result.get("meta"),
            provider_name=result.get("provider_name"),
            failure_code="TEMP_EMAIL_CREATE_FAILED",
            failure_message="任务邮箱创建失败",
            failure_status=502,
            allow_existing=False,
        )
        mailbox["task_token"] = task_token
        return mailbox

    def finish_task_mailbox(self, task_token: str) -> dict[str, Any]:
        mailbox = self.get_task_mailbox(task_token)
        if not mailbox:
            raise TempMailError("TASK_TOKEN_INVALID", "任务令牌无效", status=404)
        status = str(mailbox.get("status") or "active").strip().lower()
        if status == "finished":
            raise TempMailError("TASK_ALREADY_FINISHED", "任务已结束", status=409)
        if not temp_emails_repo.finish_task_temp_email(task_token):
            raise TempMailError("INTERNAL_ERROR", "结束任务邮箱失败", status=500)
        finished = temp_emails_repo.get_temp_email_by_task_token(task_token) or mailbox
        return {
            "task_token": task_token,
            "status": str(finished.get("status") or "finished"),
            "email": str(finished.get("email") or ""),
        }

    def get_task_mailbox(
        self, task_token: str, *, view: str = "record"
    ) -> dict[str, Any] | None:
        return temp_emails_repo.get_temp_email_by_task_token(task_token, view=view)

    def list_messages(
        self, email_or_mailbox: str | dict[str, Any], *, sync_remote: bool = True
    ) -> list[dict[str, Any]]:
        mailbox = self._get_mailbox_descriptor(email_or_mailbox)
        email_addr = str(mailbox.get("email") or "")
        if sync_remote:
            # BUG-03: cache-only 场景（sync_remote=False）不得依赖 provider 初始化。
            provider = self._get_provider(mailbox=mailbox)
            try:
                api_messages = provider.list_messages(mailbox)
            except TempMailProviderReadError as exc:
                raise self._provider_read_failed(
                    exc, mailbox=mailbox, operation="list_messages"
                ) from exc
            if api_messages is None:
                raise self._provider_read_failed(
                    None, mailbox=mailbox, operation="list_messages"
                )
            temp_emails_repo.save_temp_email_messages(email_addr, api_messages)
        rows = temp_emails_repo.get_temp_email_messages(email_addr)
        return [_message_summary(email_addr, row) for row in rows]

    def get_message_detail(
        self,
        email_or_mailbox: str | dict[str, Any],
        message_id: str,
        *,
        refresh_if_missing: bool = True,
    ) -> dict[str, Any]:
        mailbox = self._get_mailbox_descriptor(email_or_mailbox)
        email_addr = str(mailbox.get("email") or "")
        row = temp_emails_repo.get_temp_email_message_by_id(
            message_id, email_addr=email_addr
        )
        if refresh_if_missing and row is None:
            # BUG-03: cache-only 场景（refresh_if_missing=False）不得依赖 provider 初始化。
            provider = self._get_provider(mailbox=mailbox)
            try:
                api_row = provider.get_message_detail(mailbox, message_id)
            except TempMailProviderReadError as exc:
                raise self._provider_read_failed(
                    exc,
                    mailbox=mailbox,
                    operation="get_message_detail",
                    message_id=message_id,
                ) from exc
            if api_row:
                temp_emails_repo.save_temp_email_messages(email_addr, [api_row])
                row = temp_emails_repo.get_temp_email_message_by_id(
                    message_id, email_addr=email_addr
                )
        if not row:
            raise TempMailError(
                "TEMP_EMAIL_MESSAGE_NOT_FOUND", "邮件不存在", status=404
            )
        return _message_detail(email_addr, row)

    def get_cached_message_row(
        self, email_or_mailbox: str | dict[str, Any], message_id: str
    ) -> dict[str, Any] | None:
        mailbox = self._get_mailbox_descriptor(email_or_mailbox)
        email_addr = str(mailbox.get("email") or "")
        return temp_emails_repo.get_temp_email_message_by_id(
            message_id, email_addr=email_addr
        )

    def refresh_message_detail(
        self, email_or_mailbox: str | dict[str, Any], message_id: str
    ) -> dict[str, Any]:
        mailbox = self._get_mailbox_descriptor(email_or_mailbox)
        email_addr = str(mailbox.get("email") or "")
        provider = self._get_provider(mailbox=mailbox)
        try:
            api_row = provider.get_message_detail(mailbox, message_id)
        except TempMailProviderReadError as exc:
            raise self._provider_read_failed(
                exc,
                mailbox=mailbox,
                operation="refresh_message_detail",
                message_id=message_id,
            ) from exc
        if api_row:
            temp_emails_repo.save_temp_email_messages(email_addr, [api_row])
        row = temp_emails_repo.get_temp_email_message_by_id(
            message_id, email_addr=email_addr
        )
        if not row:
            raise TempMailError(
                "TEMP_EMAIL_MESSAGE_NOT_FOUND", "邮件不存在", status=404
            )
        return _message_detail(email_addr, row)

    def delete_message(
        self, email_or_mailbox: str | dict[str, Any], message_id: str
    ) -> bool:
        mailbox = self._get_mailbox_descriptor(email_or_mailbox)
        email_addr = str(mailbox.get("email") or "")
        provider = self._get_provider(mailbox=mailbox)
        if not provider.delete_message(mailbox, message_id):
            raise TempMailError(
                "TEMP_EMAIL_MESSAGE_DELETE_FAILED", "删除失败", status=502
            )
        return temp_emails_repo.delete_temp_email_message(
            message_id, email_addr=email_addr
        )

    def clear_messages(self, email_or_mailbox: str | dict[str, Any]) -> bool:
        mailbox = self._get_mailbox_descriptor(email_or_mailbox)
        email_addr = str(mailbox.get("email") or "")
        provider = self._get_provider(mailbox=mailbox)
        if not provider.clear_messages(mailbox):
            raise TempMailError(
                "TEMP_EMAIL_MESSAGES_CLEAR_FAILED", "清空失败", status=502
            )
        from outlook_web.db import get_db

        db = get_db()
        db.execute(
            "DELETE FROM temp_email_messages WHERE email_address = ?", (email_addr,)
        )
        db.commit()
        return True

    def extract_verification(
        self,
        email_or_mailbox: str | dict[str, Any],
        *,
        code_regex: str | None = None,
        code_length: str | None = None,
        code_source: str = "all",
    ) -> dict[str, Any]:
        mailbox = self._get_mailbox_descriptor(email_or_mailbox)
        email_addr = str(mailbox.get("email") or "")
        messages = self.list_messages(mailbox, sync_remote=True)
        if not messages:
            raise TempMailError(
                "TEMP_EMAIL_MESSAGE_NOT_FOUND", "未找到邮件", status=404
            )
        latest = messages[0]
        detail = self.get_message_detail(mailbox, latest["id"])
        extracted = extract_verification_info_with_options(
            {
                "subject": detail.get("subject") or "",
                "body": detail.get("content") or "",
                "body_html": detail.get("html_content") or "",
                "body_preview": latest.get("content_preview") or "",
            },
            code_regex=code_regex,
            code_length=code_length,
            code_source=code_source,
        )
        # 与外部 API 保持一致：应用置信度门控
        extracted = apply_confidence_gate(extracted)
        extracted["matched_email_id"] = latest["id"]
        extracted["from"] = (
            detail.get("from_address") or latest.get("from_address") or ""
        )
        extracted["subject"] = detail.get("subject") or latest.get("subject") or ""
        extracted["received_at"] = (
            detail.get("created_at") or latest.get("created_at") or ""
        )
        if not extracted.get("verification_code") and not extracted.get(
            "verification_link"
        ):
            raise TempMailError(
                "VERIFICATION_CODE_NOT_FOUND",
                "未找到验证码或验证链接",
                status=404,
                data=extracted,
            )
        return extracted


_service: TempMailService | None = None


def get_temp_mail_service() -> TempMailService:
    global _service
    if _service is None:
        _service = TempMailService()
    return _service
