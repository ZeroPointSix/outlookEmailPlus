from __future__ import annotations

import unittest
from unittest.mock import patch

from tests._import_app import clear_login_attempts, import_web_app_module


class SettingsVerificationAiProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("verification_ai_enabled", "true")
            settings_repo.set_setting("verification_ai_base_url", "")
            settings_repo.set_setting("verification_ai_api_key", "")
            settings_repo.set_setting("verification_ai_model", "")

    def _login(self, client):
        resp = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    def test_verification_ai_test_endpoint_requires_auth(self):
        client = self.app.test_client()
        resp = client.post("/api/settings/verification-ai-test", json={})
        self.assertNotEqual(resp.status_code, 200)

    def test_verification_ai_test_returns_config_incomplete(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.post("/api/settings/verification-ai-test", json={})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body.get("success"))
        self.assertFalse(body.get("ok"))

        probe = body.get("probe") or {}
        self.assertEqual(probe.get("error"), "config_incomplete")
        self.assertIn("verification_ai_base_url", probe.get("missing_fields") or [])
        self.assertIn("verification_ai_api_key", probe.get("missing_fields") or [])
        self.assertIn("verification_ai_model", probe.get("missing_fields") or [])
        self.assertEqual(probe.get("error_category"), "configuration")

    def test_verification_ai_test_rejects_invalid_base_url(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.post(
            "/api/settings/verification-ai-test",
            json={
                "verification_ai_base_url": "api.example.com/v1",
                "verification_ai_api_key": "sk-temporary",
                "verification_ai_model": "gpt-test",
            },
        )
        probe = (resp.get_json() or {}).get("probe") or {}
        self.assertEqual(probe.get("error"), "invalid_base_url")
        self.assertEqual(probe.get("error_category"), "configuration")

    @patch("outlook_web.services.verification_extractor.requests.post")
    def test_verification_ai_test_success_when_runtime_reachable(self, mock_post):
        class _Resp:
            status_code = 200

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": '{"schema_version":"verification_ai_v1","verification_code":"123456","verification_link":"","confidence":"high","reason":"ok"}'
                            }
                        }
                    ]
                }

        mock_post.return_value = _Resp()

        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting(
                "verification_ai_base_url",
                "https://api.example.com/v1/chat/completions",
            )
            settings_repo.set_setting("verification_ai_api_key", "sk-test-123")
            settings_repo.set_setting("verification_ai_model", "gpt-4.1-mini")

        client = self.app.test_client()
        self._login(client)

        resp = client.post("/api/settings/verification-ai-test", json={})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body.get("success"))
        self.assertTrue(body.get("ok"))
        self.assertTrue(body.get("connectivity_ok"))
        self.assertTrue(body.get("contract_ok"))
        probe = body.get("probe") or {}
        self.assertTrue(probe.get("ok"))
        self.assertEqual(
            (probe.get("parsed_output") or {}).get("schema_version"),
            "verification_ai_v1",
        )

    @patch("outlook_web.services.verification_extractor.requests.post")
    def test_verification_ai_test_connectivity_ok_when_contract_invalid(self, mock_post):
        class _Resp:
            status_code = 200

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": '{"schema_version":"verification_ai_v1","verification_code":"123456","verification_link":null,"confidence":1.0,"reason":"ok"}'
                            }
                        }
                    ]
                }

        mock_post.return_value = _Resp()

        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting(
                "verification_ai_base_url",
                "https://api.example.com/v1/chat/completions",
            )
            settings_repo.set_setting("verification_ai_api_key", "sk-test-123")
            settings_repo.set_setting("verification_ai_model", "gpt-4.1-mini")

        client = self.app.test_client()
        self._login(client)

        resp = client.post("/api/settings/verification-ai-test", json={})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body.get("success"))
        # 彻底放宽解析后：2xx 且存在 code/link 即可 contract_ok
        self.assertTrue(body.get("ok"))
        self.assertTrue(body.get("connectivity_ok"))
        self.assertTrue(body.get("contract_ok"))
        probe = body.get("probe") or {}
        self.assertTrue(probe.get("ok"))
        self.assertEqual((probe.get("parsed_output") or {}).get("verification_code"), "123456")

    @patch("outlook_web.services.verification_extractor.requests.post")
    def test_verification_ai_test_uses_unsaved_form_values(self, mock_post):
        class _Resp:
            status_code = 200

            def json(self):
                return {
                    "model": "resolved-test-model",
                    "choices": [
                        {
                            "message": {
                                "content": '{"schema_version":"verification_ai_v1","verification_code":"123456","verification_link":"","confidence":"high","reason":"ok"}'
                            }
                        }
                    ],
                }

        mock_post.return_value = _Resp()
        client = self.app.test_client()
        self._login(client)

        resp = client.post(
            "/api/settings/verification-ai-test",
            json={
                "verification_ai_base_url": "https://api.temporary.example/v1",
                "verification_ai_api_key": "sk-temporary",
                "verification_ai_model": "requested-test-model",
            },
        )
        probe = (resp.get_json() or {}).get("probe") or {}
        self.assertTrue(probe.get("ok"))
        self.assertEqual(probe.get("model"), "resolved-test-model")
        self.assertEqual(probe.get("requested_model"), "requested-test-model")
        self.assertEqual(
            mock_post.call_args.args[0],
            "https://api.temporary.example/v1/chat/completions",
        )
        self.assertEqual(
            mock_post.call_args.kwargs["json"]["model"],
            "requested-test-model",
        )

    @patch("outlook_web.services.verification_extractor.requests.post")
    def test_verification_ai_test_classifies_authentication_failure(self, mock_post):
        class _Resp:
            status_code = 401
            text = "Unauthorized"

        mock_post.return_value = _Resp()
        client = self.app.test_client()
        self._login(client)

        resp = client.post(
            "/api/settings/verification-ai-test",
            json={
                "verification_ai_base_url": "https://api.example.com/v1",
                "verification_ai_api_key": "sk-invalid",
                "verification_ai_model": "gpt-test",
            },
        )
        probe = (resp.get_json() or {}).get("probe") or {}
        self.assertEqual(probe.get("http_status"), 401)
        self.assertEqual(probe.get("error_category"), "authentication")
        self.assertIn("API Key", probe.get("hint") or "")


if __name__ == "__main__":
    unittest.main()