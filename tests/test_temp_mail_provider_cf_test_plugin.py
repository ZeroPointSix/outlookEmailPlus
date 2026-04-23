from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests._import_app import clear_login_attempts, import_web_app_module


def _load_cf_test_module(module_name: str = "_test_plugin_cf_temp_mail"):
    plugin_path = (
        Path(__file__).resolve().parents[1]
        / "plugins"
        / "temp_mail_providers"
        / "test_plugin"
        / "cloudflare_temp_mail_test_plugin.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, plugin_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 cloudflare_temp_mail_test_plugin 模块")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class CloudflareTempMailTestPluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("plugin.cloudflare_temp_mail_test_plugin.base_url", "https://cf-temp.example.com")
            settings_repo.set_setting("plugin.cloudflare_temp_mail_test_plugin.admin_key", "admin-key")
            settings_repo.set_setting("plugin.cloudflare_temp_mail_test_plugin.custom_auth", "")
            settings_repo.set_setting("plugin.cloudflare_temp_mail_test_plugin.domains", "cfmail.example.com\nalt.example.com")
            settings_repo.set_setting("plugin.cloudflare_temp_mail_test_plugin.default_domain", "cfmail.example.com")
            settings_repo.set_setting("plugin.cloudflare_temp_mail_test_plugin.request_timeout", "30")

        from outlook_web.temp_mail_registry import _REGISTRY

        self._registry = _REGISTRY
        self._initial_keys = set(_REGISTRY.keys())

    def tearDown(self):
        from outlook_web.services import temp_mail_provider_factory as factory

        for key in set(self._registry.keys()) - self._initial_keys:
            self._registry.pop(key, None)

        for module_name in list(sys.modules.keys()):
            if module_name in {"_test_plugin_cf_temp_mail", "_plugin_cloudflare_temp_mail_test_plugin"}:
                del sys.modules[module_name]

        factory._FAILED_PLUGIN_MTIMES.clear()
        factory._PLUGIN_LOAD_STATE.clear()

    def test_provider_register_discover_without_overriding_builtin(self):
        from outlook_web.services import temp_mail_provider_factory as factory
        from outlook_web.services.temp_mail_provider_factory import get_available_providers, reload_plugins

        plugin_dir = Path(__file__).resolve().parents[1] / "plugins" / "temp_mail_providers" / "test_plugin"

        with patch.object(factory, "_get_plugin_dir", return_value=plugin_dir):
            result = reload_plugins()

        self.assertIn("cloudflare_temp_mail_test_plugin", self._registry)
        self.assertIn("cloudflare_temp_mail", self._registry)  # 内置保持不变
        self.assertIn("cloudflare_temp_mail_test_plugin", result["loaded"])

        names = {item["name"] for item in get_available_providers()}
        self.assertIn("cloudflare_temp_mail_test_plugin", names)
        self.assertIn("cloudflare_temp_mail", names)

    def test_get_options_returns_stable_structure(self):
        module = _load_cf_test_module()
        provider_cls = module.CloudflareTempMailTestPluginProvider

        with self.app.app_context():
            provider = provider_cls(provider_name="cloudflare_temp_mail_test_plugin")
            options = provider.get_options()

        self.assertEqual(options["provider"], "cloudflare_temp_mail_test_plugin")
        self.assertEqual(options["provider_name"], "cloudflare_temp_mail_test_plugin")
        self.assertTrue(isinstance(options["domains"], list))
        self.assertTrue(isinstance(options["prefix_rules"], dict))
        self.assertGreaterEqual(len(options["domains"]), 1)

    def test_create_mailbox_success_and_failure(self):
        module = _load_cf_test_module()
        provider_cls = module.CloudflareTempMailTestPluginProvider

        with self.app.app_context():
            provider = provider_cls(provider_name="cloudflare_temp_mail_test_plugin")

            ok_resp = MagicMock()
            ok_resp.ok = True
            ok_resp.status_code = 200
            ok_resp.json.return_value = {
                "address": "demo@cfmail.example.com",
                "jwt": "jwt-token",
                "address_id": "addr-1",
            }
            with patch("requests.post", return_value=ok_resp):
                success = provider.create_mailbox(prefix="demo", domain="cfmail.example.com")

        self.assertTrue(success["success"])
        self.assertEqual(success["email"], "demo@cfmail.example.com")
        self.assertEqual(success["meta"]["provider_jwt"], "jwt-token")
        self.assertEqual(success["meta"]["provider_mailbox_id"], "addr-1")

        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("plugin.cloudflare_temp_mail_test_plugin.admin_key", "")
            provider_no_key = provider_cls(provider_name="cloudflare_temp_mail_test_plugin")
            failed = provider_no_key.create_mailbox(prefix="demo", domain="cfmail.example.com")

        self.assertFalse(failed["success"])
        self.assertEqual(failed["error_code"], "TEMP_MAIL_PROVIDER_NOT_CONFIGURED")

    def test_list_messages_normalizes_payload(self):
        module = _load_cf_test_module()
        provider_cls = module.CloudflareTempMailTestPluginProvider

        mailbox = {
            "email": "demo@cfmail.example.com",
            "meta": {
                "provider_mailbox_id": "addr-1",
                "provider_jwt": "jwt-token",
            },
        }

        with self.app.app_context():
            provider = provider_cls(provider_name="cloudflare_temp_mail_test_plugin")

            resp = MagicMock()
            resp.ok = True
            resp.status_code = 200
            resp.json.return_value = {
                "mails": [
                    {
                        "id": 101,
                        "source": "noreply@example.com",
                        "raw": "From: noreply@example.com\r\nSubject: Verify\r\n\r\nCode 123456",
                        "created_at": "2025-12-07T10:30:00.000Z",
                    }
                ]
            }

            with patch("requests.get", return_value=resp):
                messages = provider.list_messages(mailbox)

        self.assertEqual(len(messages), 1)
        msg = messages[0]
        self.assertEqual(msg["id"], "cf_test_101")
        self.assertEqual(msg["message_id"], "cf_test_101")
        self.assertEqual(msg["from_address"], "noreply@example.com")
        self.assertEqual(msg["subject"], "Verify")
        self.assertIsInstance(msg["timestamp"], int)
        self.assertGreater(msg["timestamp"], 0)

    def test_get_message_detail_fallback_to_list_when_api_mail_unavailable(self):
        module = _load_cf_test_module()
        provider_cls = module.CloudflareTempMailTestPluginProvider

        mailbox = {
            "email": "demo@cfmail.example.com",
            "meta": {
                "provider_mailbox_id": "addr-1",
                "provider_jwt": "jwt-token",
            },
        }

        with self.app.app_context():
            provider = provider_cls(provider_name="cloudflare_temp_mail_test_plugin")

            detail_404 = MagicMock()
            detail_404.ok = False
            detail_404.status_code = 404
            detail_404.text = "not found"

            list_ok = MagicMock()
            list_ok.ok = True
            list_ok.status_code = 200
            list_ok.json.return_value = {
                "mails": [
                    {
                        "id": 11,
                        "source": "sender@test.com",
                        "subject": "fallback",
                        "content": "body",
                        "created_at": 1710000000,
                    }
                ]
            }

            with patch("requests.get", side_effect=[detail_404, list_ok]):
                detail = provider.get_message_detail(mailbox, "cf_test_11")

        self.assertIsNotNone(detail)
        self.assertEqual(detail["id"], "cf_test_11")
        self.assertEqual(detail["subject"], "fallback")


if __name__ == "__main__":
    unittest.main()
