from __future__ import annotations

import unittest

from tests._import_app import clear_login_attempts, import_web_app_module


class _FakeTempMailProvider:
    def __init__(self):
        self.generated = []
        self.list_payload = []
        self.detail_payload = {}
        self.list_exception = None
        self.detail_exception = None
        self.delete_result = True
        self.clear_result = True

    def get_options(self):
        return {
            "domain_strategy": "auto_or_manual",
            "default_mode": "auto",
            "domains": [
                {"name": "mail.service.test", "enabled": True, "is_default": True},
                {"name": "temp.service.test", "enabled": True, "is_default": False},
            ],
            "prefix_rules": {
                "min_length": 1,
                "max_length": 32,
                "pattern": r"^[a-z0-9][a-z0-9._-]*$",
            },
        }

    def generate_mailbox(self, *, prefix=None, domain=None):
        email_addr = f"{prefix or 'auto'}@{domain or 'mail.service.test'}"
        self.generated.append({"prefix": prefix, "domain": domain, "email": email_addr})
        return {"success": True, "email": email_addr}

    def list_messages(self, email_addr):
        if self.list_exception is not None:
            raise self.list_exception
        return list(self.list_payload)

    def get_message_detail(self, email_addr, message_id):
        if self.detail_exception is not None:
            raise self.detail_exception
        return dict(self.detail_payload.get(message_id) or {})

    def delete_message(self, email_addr, message_id):
        return self.delete_result

    def clear_messages(self, email_addr):
        return self.clear_result


class TempMailServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.db import get_db

            db = get_db()
            db.execute("DELETE FROM temp_email_messages WHERE email_address LIKE '%@service.test'")
            db.execute("DELETE FROM temp_emails WHERE email LIKE '%@service.test'")
            db.commit()

    def test_generate_user_mailbox_persists_prefix_domain_and_visibility(self):
        with self.app.app_context():
            from outlook_web.services.temp_mail_service import TempMailService

            provider = _FakeTempMailProvider()
            service = TempMailService(provider=provider)

            mailbox = service.generate_user_mailbox(prefix="demo123", domain="mail.service.test")

        self.assertEqual(mailbox["email"], "demo123@mail.service.test")
        self.assertEqual(mailbox["prefix"], "demo123")
        self.assertEqual(mailbox["domain"], "mail.service.test")
        self.assertTrue(mailbox["visible_in_ui"])
        self.assertEqual(mailbox["created_by"], "user")

    def test_generate_user_mailbox_persists_provider_name_from_provider(self):
        with self.app.app_context():
            from outlook_web.repositories import temp_emails as temp_emails_repo
            from outlook_web.services.temp_mail_service import TempMailService

            provider = _FakeTempMailProvider()
            provider.provider_name = "plugin_provider"
            service = TempMailService(provider=provider)
            mailbox = service.generate_user_mailbox(prefix="hme", domain="mail.service.test")
            saved = temp_emails_repo.get_temp_email_by_address(mailbox["email"])

        self.assertEqual(saved["provider_name"], "plugin_provider")
        self.assertEqual(saved["meta_json"]["provider_name"], "plugin_provider")

    def test_apply_and_finish_task_mailbox_records_task_fields(self):
        with self.app.app_context():
            from outlook_web.repositories import temp_emails as temp_emails_repo
            from outlook_web.services.temp_mail_service import TempMailService

            provider = _FakeTempMailProvider()
            service = TempMailService(provider=provider)

            mailbox = service.apply_task_mailbox(
                consumer_key="key:task-owner",
                caller_id="worker-1",
                task_id="job-001",
                prefix="runner",
                domain="temp.service.test",
            )
            saved = temp_emails_repo.get_temp_email_by_task_token(mailbox["task_token"])
            finished = service.finish_task_mailbox(mailbox["task_token"])

        self.assertEqual(mailbox["email"], "runner@temp.service.test")
        self.assertFalse(mailbox["visible_in_ui"])
        self.assertEqual(saved["mailbox_type"], "task")
        self.assertEqual(saved["consumer_key"], "key:task-owner")
        self.assertEqual(saved["caller_id"], "worker-1")
        self.assertEqual(saved["task_id"], "job-001")
        self.assertEqual(finished["status"], "finished")

    def test_extract_verification_returns_shared_extractor_fields(self):
        with self.app.app_context():
            from outlook_web.services.temp_mail_service import TempMailService

            provider = _FakeTempMailProvider()
            provider.list_payload = [
                {
                    "id": "msg-1",
                    "from_address": "noreply@example.com",
                    "subject": "Your verification code",
                    "content": "Code: 654321",
                    "timestamp": 1711111111,
                }
            ]
            provider.detail_payload["msg-1"] = {
                "id": "msg-1",
                "from_address": "noreply@example.com",
                "subject": "Your verification code",
                "content": "Use verification code 654321 to continue.",
                "html_content": "",
                "timestamp": 1711111111,
            }
            service = TempMailService(provider=provider)
            service.generate_user_mailbox(prefix="verify", domain="mail.service.test")

            result = service.extract_verification("verify@mail.service.test")

        self.assertEqual(result["verification_code"], "654321")
        self.assertEqual(result["matched_email_id"], "msg-1")
        self.assertIn("formatted", result)

    def test_list_messages_does_not_mask_upstream_failure_as_cached_result(self):
        with self.app.app_context():
            from outlook_web.repositories import temp_emails as temp_emails_repo
            from outlook_web.services.temp_mail_provider_custom import TempMailProviderReadError
            from outlook_web.services.temp_mail_service import TempMailError, TempMailService

            provider = _FakeTempMailProvider()
            provider.list_exception = TempMailProviderReadError(
                "UPSTREAM_TIMEOUT",
                "API 请求超时",
                data={"bridge_error_type": "TIMEOUT_ERROR"},
            )
            service = TempMailService(provider=provider)
            service.generate_user_mailbox(prefix="cached", domain="mail.service.test")
            temp_emails_repo.save_temp_email_messages(
                "cached@mail.service.test",
                [
                    {
                        "id": "msg-cached-1",
                        "from_address": "sender@example.com",
                        "subject": "Cached",
                        "content": "stale",
                        "timestamp": 1711111199,
                    }
                ],
            )

            with self.assertRaises(TempMailError) as ctx:
                service.list_messages("cached@mail.service.test", sync_remote=True)

        self.assertEqual(ctx.exception.code, "TEMP_EMAIL_UPSTREAM_READ_FAILED")
        self.assertEqual(ctx.exception.status, 502)
        self.assertEqual(ctx.exception.data["operation"], "list_messages")
        self.assertEqual(ctx.exception.data["provider_error_code"], "UPSTREAM_TIMEOUT")

    def test_get_message_detail_does_not_map_upstream_failure_to_not_found(self):
        with self.app.app_context():
            from outlook_web.services.temp_mail_provider_custom import TempMailProviderReadError
            from outlook_web.services.temp_mail_service import TempMailError, TempMailService

            provider = _FakeTempMailProvider()
            provider.detail_exception = TempMailProviderReadError(
                "UPSTREAM_SERVER_ERROR",
                "临时邮箱服务暂时不可用",
                data={"bridge_error_type": "SERVER_ERROR"},
            )
            service = TempMailService(provider=provider)
            service.generate_user_mailbox(prefix="detailfail", domain="mail.service.test")

            with self.assertRaises(TempMailError) as ctx:
                service.get_message_detail("detailfail@mail.service.test", "msg-missing", refresh_if_missing=True)

        self.assertEqual(ctx.exception.code, "TEMP_EMAIL_UPSTREAM_READ_FAILED")
        self.assertEqual(ctx.exception.status, 502)
        self.assertEqual(ctx.exception.data["operation"], "get_message_detail")
        self.assertEqual(ctx.exception.data["message_id"], "msg-missing")

    def test_refresh_message_detail_surfaces_upstream_failure(self):
        with self.app.app_context():
            from outlook_web.services.temp_mail_provider_custom import TempMailProviderReadError
            from outlook_web.services.temp_mail_service import TempMailError, TempMailService

            provider = _FakeTempMailProvider()
            provider.detail_exception = TempMailProviderReadError(
                "UPSTREAM_TIMEOUT",
                "API 请求超时",
                data={"bridge_error_type": "TIMEOUT_ERROR"},
            )
            service = TempMailService(provider=provider)
            service.generate_user_mailbox(prefix="refreshfail", domain="mail.service.test")

            with self.assertRaises(TempMailError) as ctx:
                service.refresh_message_detail("refreshfail@mail.service.test", "msg-1")

        self.assertEqual(ctx.exception.code, "TEMP_EMAIL_UPSTREAM_READ_FAILED")
        self.assertEqual(ctx.exception.status, 502)
        self.assertEqual(ctx.exception.data["operation"], "refresh_message_detail")

    def test_unsupported_message_mutations_return_capability_errors(self):
        with self.app.app_context():
            from outlook_web.repositories import temp_emails as temp_emails_repo
            from outlook_web.services.temp_mail_service import TempMailError, TempMailService

            service = TempMailService(provider=_FakeTempMailProvider())
            mailbox = {
                "kind": temp_emails_repo.TEMP_MAIL_KIND,
                "email": "unsupported@service.test",
                "meta": {
                    "provider_capabilities": {
                        "delete_message": False,
                        "clear_messages": False,
                    }
                },
            }

            with self.assertRaises(TempMailError) as delete_ctx:
                service.delete_message(mailbox, "message-1")
            with self.assertRaises(TempMailError) as clear_ctx:
                service.clear_messages(mailbox)

        self.assertEqual(delete_ctx.exception.code, "TEMP_EMAIL_MESSAGE_DELETE_UNSUPPORTED")
        self.assertEqual(delete_ctx.exception.status, 400)
        self.assertEqual(clear_ctx.exception.code, "TEMP_EMAIL_MESSAGES_CLEAR_UNSUPPORTED")
        self.assertEqual(clear_ctx.exception.status, 400)

    def test_delete_message_keeps_local_cache_when_provider_delete_fails(self):
        with self.app.app_context():
            from outlook_web.repositories import temp_emails as temp_emails_repo
            from outlook_web.services.temp_mail_service import TempMailError, TempMailService

            provider = _FakeTempMailProvider()
            provider.delete_result = False
            service = TempMailService(provider=provider)
            service.generate_user_mailbox(prefix="deletecase", domain="mail.service.test")
            temp_emails_repo.save_temp_email_messages(
                "deletecase@mail.service.test",
                [
                    {
                        "id": "msg-delete-1",
                        "from_address": "sender@example.com",
                        "subject": "Delete me",
                        "content": "body",
                        "timestamp": 1711111112,
                    }
                ],
            )

            with self.assertRaises(TempMailError) as ctx:
                service.delete_message("deletecase@mail.service.test", "msg-delete-1")

            cached = temp_emails_repo.get_temp_email_message_by_id(
                "msg-delete-1",
                email_addr="deletecase@mail.service.test",
            )

        self.assertEqual(ctx.exception.code, "TEMP_EMAIL_MESSAGE_DELETE_FAILED")
        self.assertIsNotNone(cached)

    def test_clear_messages_keeps_local_cache_when_provider_clear_fails(self):
        with self.app.app_context():
            from outlook_web.repositories import temp_emails as temp_emails_repo
            from outlook_web.services.temp_mail_service import TempMailError, TempMailService

            provider = _FakeTempMailProvider()
            provider.clear_result = False
            service = TempMailService(provider=provider)
            service.generate_user_mailbox(prefix="clearcase", domain="mail.service.test")
            temp_emails_repo.save_temp_email_messages(
                "clearcase@mail.service.test",
                [
                    {
                        "id": "msg-clear-1",
                        "from_address": "sender@example.com",
                        "subject": "Keep me",
                        "content": "body",
                        "timestamp": 1711111113,
                    }
                ],
            )

            with self.assertRaises(TempMailError) as ctx:
                service.clear_messages("clearcase@mail.service.test")

            cached = temp_emails_repo.get_temp_email_messages("clearcase@mail.service.test")

        self.assertEqual(ctx.exception.code, "TEMP_EMAIL_MESSAGES_CLEAR_FAILED")
        self.assertEqual(len(cached), 1)
