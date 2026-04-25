"""tests/test_batch_fetch_email_api_contract.py — C 类：邮件 API 复用契约测试

目标：
  - 验证 `/api/emails/<email_addr>` 的成功响应字段足以支撑批量拉取前端
  - 验证失败响应仍保持统一错误结构
  - 验证 `junkemail` 与 `inbox` 的返回形状一致

注意（RED 阶段）：
  本文件不新增接口，只验证当前单账号邮件接口的契约。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tests._import_app import clear_login_attempts, import_web_app_module


class BatchFetchEmailApiContractTests(unittest.TestCase):
    """C 类：批量拉取前置依赖的邮件 API 契约测试。"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()

    def _login(self, client):
        resp = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    @staticmethod
    def _build_outlook_account(email_addr: str) -> dict:
        return {
            "id": 101,
            "email": email_addr,
            "client_id": "cid-test",
            "refresh_token": "rt-test",
            "group_id": None,
            "account_type": "outlook",
            "provider": "outlook",
        }

    @patch("outlook_web.controllers.emails.accounts_repo.touch_last_refresh_at", return_value=True)
    @patch(
        "outlook_web.controllers.emails.compact_summary_service.update_summary_from_message_list",
        return_value={
            "latest_email_subject": "验证码 123456",
            "latest_email_from": "noreply@example.com",
            "latest_email_folder": "inbox",
            "latest_verification_code": "123456",
            "latest_verification_folder": "inbox",
        },
    )
    @patch(
        "outlook_web.controllers.emails.graph_service.get_emails_graph",
        return_value={
            "success": True,
            "emails": [
                {
                    "id": "msg-1",
                    "subject": "验证码 123456",
                    "from": {"emailAddress": {"address": "noreply@example.com"}},
                    "receivedDateTime": "2030-01-01T00:00:00Z",
                    "isRead": False,
                    "hasAttachments": False,
                    "bodyPreview": "preview",
                }
            ],
        },
    )
    @patch("outlook_web.controllers.emails.accounts_repo.get_account_by_email")
    def test_email_api_success_payload_contains_fields_used_by_batch_fetch(
        self,
        mock_get_account_by_email,
        _mock_graph_get_emails,
        _mock_update_summary,
        _mock_touch_refresh_at,
    ):
        """TDD C-01,C-02：成功响应应包含批量拉取前端使用的核心字段。"""
        email_addr = "batch-success@example.com"
        mock_get_account_by_email.return_value = self._build_outlook_account(email_addr)

        client = self.app.test_client()
        self._login(client)
        resp = client.get(f"/api/emails/{email_addr}?folder=inbox&skip=0&top=10")

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("emails", data)
        self.assertIn("method", data)
        self.assertIn("has_more", data)
        self.assertIn("account_summary", data)
        self.assertIsInstance(data.get("emails"), list)
        self.assertIsInstance(data.get("account_summary"), dict)

    @patch("outlook_web.controllers.emails.imap_service.get_emails_imap_with_server")
    @patch(
        "outlook_web.controllers.emails.graph_service.get_emails_graph",
        return_value={
            "success": False,
            "error": {
                "code": "EMAIL_FETCH_FAILED",
                "message": "代理连接失败",
                "type": "ProxyError",
                "status": 502,
            },
        },
    )
    @patch("outlook_web.controllers.emails.accounts_repo.get_account_by_email")
    def test_email_api_failure_payload_remains_compatible_with_batch_failure_aggregation(
        self,
        mock_get_account_by_email,
        _mock_graph_get_emails,
        mock_imap_get_emails,
    ):
        """TDD C-03：失败响应应继续遵循统一错误结构。"""
        email_addr = "batch-failure@example.com"
        mock_get_account_by_email.return_value = self._build_outlook_account(email_addr)

        client = self.app.test_client()
        self._login(client)
        resp = client.get(f"/api/emails/{email_addr}?folder=inbox&skip=0&top=10")

        mock_imap_get_emails.assert_not_called()
        self.assertEqual(resp.status_code, 502)
        data = resp.get_json()
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data.get("error", {}).get("code"), "EMAIL_PROXY_CONNECTION_FAILED")
        self.assertEqual(data.get("status"), 502)
        self.assertTrue(data.get("trace_id"))

    @patch("outlook_web.controllers.emails.accounts_repo.touch_last_refresh_at", return_value=True)
    @patch(
        "outlook_web.controllers.emails.compact_summary_service.update_summary_from_message_list",
        return_value={"latest_email_folder": "junkemail"},
    )
    @patch(
        "outlook_web.controllers.emails.graph_service.get_emails_graph",
        return_value={
            "success": True,
            "emails": [
                {
                    "id": "msg-junk-1",
                    "subject": "spam candidate",
                    "from": {"emailAddress": {"address": "noreply@example.com"}},
                    "receivedDateTime": "2030-01-01T00:00:00Z",
                    "isRead": False,
                    "hasAttachments": False,
                    "bodyPreview": "preview",
                }
            ],
        },
    )
    @patch("outlook_web.controllers.emails.accounts_repo.get_account_by_email")
    def test_email_api_junkemail_folder_returns_same_shape_as_inbox(
        self,
        mock_get_account_by_email,
        _mock_graph_get_emails,
        _mock_update_summary,
        _mock_touch_refresh_at,
    ):
        """TDD C-04：junkemail 的成功响应形状应与 inbox 一致。"""
        email_addr = "batch-junk@example.com"
        mock_get_account_by_email.return_value = self._build_outlook_account(email_addr)

        client = self.app.test_client()
        self._login(client)
        resp = client.get(f"/api/emails/{email_addr}?folder=junkemail&skip=0&top=10")

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("emails", data)
        self.assertIn("method", data)
        self.assertIn("has_more", data)
        self.assertIn("account_summary", data)

    @patch("outlook_web.controllers.emails.accounts_repo.touch_last_refresh_at", return_value=True)
    @patch(
        "outlook_web.controllers.emails.compact_summary_service.update_summary_from_message_list",
        return_value=None,
    )
    @patch(
        "outlook_web.controllers.emails.graph_service.get_emails_graph",
        return_value={
            "success": True,
            "emails": [],
        },
    )
    @patch("outlook_web.controllers.emails.accounts_repo.get_account_by_email")
    def test_email_api_account_summary_field_is_optional_but_safe(
        self,
        mock_get_account_by_email,
        _mock_graph_get_emails,
        _mock_update_summary,
        _mock_touch_refresh_at,
    ):
        """TDD C-02：account_summary 为 None 时，响应仍应安全包含该字段。"""
        email_addr = "batch-summary-none@example.com"
        mock_get_account_by_email.return_value = self._build_outlook_account(email_addr)

        client = self.app.test_client()
        self._login(client)
        resp = client.get(f"/api/emails/{email_addr}?folder=inbox&skip=0&top=10")

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("account_summary", data)
        self.assertIsNone(data.get("account_summary"))


if __name__ == "__main__":
    unittest.main()
