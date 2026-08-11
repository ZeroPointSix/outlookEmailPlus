from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

from tests._import_app import clear_login_attempts, import_web_app_module


class WebhookPushServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("webhook_notification_enabled", "false")
            settings_repo.set_setting("webhook_notification_url", "")
            settings_repo.set_setting("webhook_notification_token", "")

    def _resp(self, status_code: int, text: str = "", json_data=None):
        resp = Mock()
        resp.status_code = status_code
        resp.text = text
        if json_data is None:
            resp.json.side_effect = ValueError("not json")
        else:
            resp.json.return_value = json_data
        return resp

    def test_send_webhook_message_success_on_2xx(self):
        from outlook_web.services import webhook_push

        with patch(
            "outlook_web.services.webhook_push.requests.post",
            return_value=self._resp(204),
        ) as post_mock:
            webhook_push.send_webhook_message(
                url="https://example.com/hook",
                token="",
                text_body="hello",
                timeout_sec=10,
                retry=1,
            )

        post_mock.assert_called_once()
        kwargs = post_mock.call_args.kwargs
        self.assertEqual(kwargs.get("timeout"), 10)
        self.assertEqual(kwargs.get("headers", {}).get("Content-Type"), "text/plain; charset=utf-8")
        self.assertEqual(kwargs.get("data"), b"hello")
        self.assertNotIn("json", kwargs)
        self.assertNotIn("X-Webhook-Token", kwargs.get("headers", {}))

    def test_send_feishu_v2_webhook_uses_json_payload(self):
        from outlook_web.services import webhook_push

        with patch(
            "outlook_web.services.webhook_push.requests.post",
            return_value=self._resp(200, json_data={"code": 0, "msg": "success"}),
        ) as post_mock:
            webhook_push.send_webhook_message(
                url="https://open.feishu.cn/open-apis/bot/v2/hook/secret-hook-id",
                token="",
                text_body="hello 飞书",
            )

        kwargs = post_mock.call_args.kwargs
        self.assertEqual(kwargs.get("headers", {}).get("Content-Type"), "application/json; charset=utf-8")
        self.assertEqual(
            kwargs.get("json"),
            {"msg_type": "text", "content": {"text": "hello 飞书"}},
        )
        self.assertNotIn("data", kwargs)

    def test_send_lark_v2_webhook_uses_json_payload(self):
        from outlook_web.services import webhook_push

        with patch(
            "outlook_web.services.webhook_push.requests.post",
            return_value=self._resp(200, json_data={"code": 0}),
        ) as post_mock:
            webhook_push.send_webhook_message(
                url="https://open.larksuite.com/open-apis/bot/v2/hook/secret-hook-id",
                token="",
                text_body="hello Lark",
            )

        self.assertIn("json", post_mock.call_args.kwargs)
        self.assertNotIn("data", post_mock.call_args.kwargs)

    def test_feishu_lookalike_host_keeps_generic_plain_text_protocol(self):
        from outlook_web.services import webhook_push

        with patch(
            "outlook_web.services.webhook_push.requests.post",
            return_value=self._resp(200),
        ) as post_mock:
            webhook_push.send_webhook_message(
                url="https://open.feishu.cn.example.com/open-apis/bot/v2/hook/not-feishu",
                token="",
                text_body="hello",
            )

        kwargs = post_mock.call_args.kwargs
        self.assertEqual(kwargs.get("headers", {}).get("Content-Type"), "text/plain; charset=utf-8")
        self.assertEqual(kwargs.get("data"), b"hello")
        self.assertNotIn("json", kwargs)

    def test_send_webhook_message_retries_once_then_success(self):
        from outlook_web.services import webhook_push

        with patch(
            "outlook_web.services.webhook_push.requests.post",
            side_effect=[self._resp(500, "err"), self._resp(200, "ok")],
        ) as post_mock:
            webhook_push.send_webhook_message(
                url="https://example.com/hook",
                token="",
                text_body="hello",
                timeout_sec=10,
                retry=1,
            )

        self.assertEqual(post_mock.call_count, 2)

    def test_send_webhook_message_retries_once_then_fail(self):
        from outlook_web.services import webhook_push

        with patch(
            "outlook_web.services.webhook_push.requests.post",
            side_effect=[self._resp(500, "err"), self._resp(500, "err2")],
        ) as post_mock:
            with self.assertRaises(webhook_push.WebhookPushError) as ctx:
                webhook_push.send_webhook_message(
                    url="https://example.com/hook",
                    token="",
                    text_body="hello",
                    timeout_sec=10,
                    retry=1,
                )

        self.assertEqual(post_mock.call_count, 2)
        self.assertEqual(ctx.exception.code, "WEBHOOK_SEND_FAILED")

    def test_feishu_failure_log_redacts_url_and_response_body(self):
        from outlook_web.services import webhook_push

        secret = "secret-hook-id"
        response = self._resp(
            400,
            text=f"bad request for {secret}",
            json_data={"code": 9499, "msg": f"bad request for {secret}"},
        )
        with patch(
            "outlook_web.services.webhook_push.requests.post",
            return_value=response,
        ), patch("outlook_web.services.webhook_push.logger.warning") as warning_mock:
            with self.assertRaises(webhook_push.WebhookPushError) as ctx:
                webhook_push.send_webhook_message(
                    url=f"https://open.feishu.cn/open-apis/bot/v2/hook/{secret}?debug={secret}",
                    token="",
                    text_body="hello",
                    retry=0,
                )

        formatted_log = warning_mock.call_args.args[0] % warning_mock.call_args.args[1:]
        self.assertNotIn(secret, formatted_log)
        self.assertNotIn(secret, str(ctx.exception.details))
        self.assertIn("https://open.feishu.cn/<redacted>", formatted_log)
        self.assertIn("status=400 code=9499", formatted_log)

    def test_request_exception_details_do_not_expose_webhook_secret(self):
        from outlook_web.services import webhook_push

        secret = "secret-hook-id"
        with patch(
            "outlook_web.services.webhook_push.requests.post",
            side_effect=requests.ConnectionError(f"failed url=/open-apis/bot/v2/hook/{secret}"),
        ), patch("outlook_web.services.webhook_push.logger.warning") as warning_mock:
            with self.assertRaises(webhook_push.WebhookPushError) as ctx:
                webhook_push.send_webhook_message(
                    url=f"https://open.feishu.cn/open-apis/bot/v2/hook/{secret}",
                    token="",
                    text_body="hello",
                    retry=0,
                )

        formatted_log = warning_mock.call_args.args[0] % warning_mock.call_args.args[1:]
        self.assertEqual(ctx.exception.details, "connection_error")
        self.assertNotIn(secret, formatted_log)

    def test_safe_url_for_log_strips_credentials_path_query_and_fragment(self):
        from outlook_web.services import webhook_push

        safe_url = webhook_push._safe_url_for_log(
            "https://user:password@open.feishu.cn:443/open-apis/bot/v2/hook/secret?token=secret#secret"
        )

        self.assertEqual(safe_url, "https://open.feishu.cn:443/<redacted>")

    def test_invalid_webhook_url_error_does_not_echo_input(self):
        from outlook_web.services import webhook_push

        secret = "secret-hook-id"
        with self.assertRaises(webhook_push.WebhookPushError) as ctx:
            webhook_push.validate_webhook_url(f"ftp://example.com/hook/{secret}")

        self.assertEqual(ctx.exception.code, "WEBHOOK_URL_INVALID")
        self.assertNotIn(secret, str(ctx.exception.details))

    def test_send_webhook_message_timeout_uses_10_seconds(self):
        from outlook_web.services import webhook_push

        with patch(
            "outlook_web.services.webhook_push.requests.post",
            side_effect=requests.Timeout("timeout"),
        ) as post_mock:
            with self.assertRaises(webhook_push.WebhookPushError):
                webhook_push.send_webhook_message(
                    url="https://example.com/hook",
                    token="",
                    text_body="hello",
                    timeout_sec=10,
                    retry=0,
                )

        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(post_mock.call_args.kwargs.get("timeout"), 10)

    def test_send_webhook_message_without_token_omits_header(self):
        from outlook_web.services import webhook_push

        with patch(
            "outlook_web.services.webhook_push.requests.post",
            return_value=self._resp(200),
        ) as post_mock:
            webhook_push.send_webhook_message(
                url="https://example.com/hook",
                token="",
                text_body="hello",
            )

        headers = post_mock.call_args.kwargs.get("headers", {})
        self.assertNotIn("X-Webhook-Token", headers)

    def test_send_webhook_message_with_token_sets_header(self):
        from outlook_web.services import webhook_push

        with patch(
            "outlook_web.services.webhook_push.requests.post",
            return_value=self._resp(200),
        ) as post_mock:
            webhook_push.send_webhook_message(
                url="https://example.com/hook",
                token="token-123",
                text_body="hello",
            )

        headers = post_mock.call_args.kwargs.get("headers", {})
        self.assertEqual(headers.get("X-Webhook-Token"), "token-123")

    def test_build_business_webhook_text_contains_minimum_fields(self):
        from outlook_web.services import webhook_push

        source = {
            "source_type": "account",
            "label": "sender@example.com",
        }
        message = {
            "folder": "inbox",
            "sender": "from@example.com",
            "subject": "hello",
            "received_at": "2026-04-14T12:00:00",
            "preview": "body preview",
        }

        text = webhook_push.build_business_webhook_text(source, message)
        self.assertIn("来源邮箱:", text)
        self.assertIn("来源类型:", text)
        self.assertIn("文件夹:", text)
        self.assertIn("发件人:", text)
        self.assertIn("主题:", text)
        self.assertIn("时间:", text)
        self.assertIn("正文摘要:", text)


if __name__ == "__main__":
    unittest.main()
