from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests._import_app import clear_login_attempts, import_web_app_module


def _load_moemail_module(module_name: str = "_test_plugin_moemail"):
    plugin_path = Path(__file__).resolve().parents[1] / "plugins" / "temp_mail_providers" / "test_plugin" / "moemail.py"
    spec = importlib.util.spec_from_file_location(module_name, plugin_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 moemail 插件模块")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class MoemailProviderPluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("plugin.moemail.base_url", "https://moemail.example.com")
            settings_repo.set_setting("plugin.moemail.api_key", "test-api-key")
            settings_repo.set_setting("plugin.moemail.domains", "moemail.app\nmail.example.com")
            settings_repo.set_setting("plugin.moemail.default_domain", "moemail.app")
            settings_repo.set_setting("plugin.moemail.default_expiry_ms", "3600000")
            settings_repo.set_setting("plugin.moemail.request_timeout", "30")

        from outlook_web.temp_mail_registry import _REGISTRY

        self._registry = _REGISTRY
        self._initial_keys = set(_REGISTRY.keys())

    def tearDown(self):
        from outlook_web.services import temp_mail_provider_factory as factory

        for key in set(self._registry.keys()) - self._initial_keys:
            self._registry.pop(key, None)

        for module_name in list(sys.modules.keys()):
            if module_name in {"_test_plugin_moemail", "_plugin_moemail"}:
                del sys.modules[module_name]

        factory._FAILED_PLUGIN_MTIMES.clear()
        factory._PLUGIN_LOAD_STATE.clear()

    def test_provider_can_be_registered_and_discovered(self):
        from outlook_web.services import temp_mail_provider_factory as factory
        from outlook_web.services.temp_mail_provider_factory import get_available_providers, reload_plugins

        plugin_dir = Path(__file__).resolve().parents[1] / "plugins" / "temp_mail_providers" / "test_plugin"
        with patch.object(factory, "_get_plugin_dir", return_value=plugin_dir):
            result = reload_plugins()

        self.assertIn("moemail", self._registry)
        self.assertIn("moemail", result["loaded"])
        available = get_available_providers()
        names = {item["name"] for item in available}
        self.assertIn("moemail", names)

    def test_get_options_returns_stable_structure(self):
        module = _load_moemail_module()
        provider_cls = module.MoemailTempMailProvider

        with self.app.app_context():
            provider = provider_cls(provider_name="moemail")
            options = provider.get_options()

        self.assertEqual(options["provider"], "moemail")
        self.assertEqual(options["provider_name"], "moemail")
        self.assertEqual(options["provider_label"], "Moemail")
        self.assertTrue(isinstance(options["domains"], list))
        self.assertTrue(isinstance(options["prefix_rules"], dict))

    def test_create_mailbox_success_and_failure_branches(self):
        module = _load_moemail_module()
        provider_cls = module.MoemailTempMailProvider

        with self.app.app_context():
            provider = provider_cls(provider_name="moemail")

            ok_resp = MagicMock()
            ok_resp.ok = True
            ok_resp.status_code = 200
            ok_resp.json.return_value = {
                "id": "mailbox_1",
                "email": "demo@moemail.app",
            }
            with patch("requests.post", return_value=ok_resp):
                success = provider.create_mailbox(prefix="demo", domain="moemail.app")

        self.assertTrue(success["success"])
        self.assertEqual(success["email"], "demo@moemail.app")
        self.assertEqual(success["meta"]["provider_mailbox_id"], "mailbox_1")

        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("plugin.moemail.base_url", "")
            provider_without_base = provider_cls(provider_name="moemail")
            failed = provider_without_base.create_mailbox(prefix="demo", domain="moemail.app")

        self.assertFalse(failed["success"])
        self.assertEqual(failed["error_code"], "TEMP_MAIL_PROVIDER_NOT_CONFIGURED")

    def test_list_messages_normalizes_upstream_payload(self):
        module = _load_moemail_module()
        provider_cls = module.MoemailTempMailProvider

        mailbox = {
            "email": "demo@moemail.app",
            "meta": {"provider_mailbox_id": "mailbox_1"},
        }

        with self.app.app_context():
            provider = provider_cls(provider_name="moemail")

            resp = MagicMock()
            resp.ok = True
            resp.status_code = 200
            resp.json.return_value = {
                "messages": [
                    {
                        "id": "msg_1",
                        "from_address": "noreply@example.com",
                        "subject": "Your code",
                        "content": "验证码 123456",
                        "html": "<p>验证码 <b>123456</b></p>",
                        "received_at": 1710000000000,
                    }
                ]
            }
            with patch("requests.get", return_value=resp):
                messages = provider.list_messages(mailbox)

        self.assertEqual(len(messages), 1)
        msg = messages[0]
        self.assertEqual(msg["id"], "moemail_msg_1")
        self.assertEqual(msg["message_id"], "moemail_msg_1")
        self.assertEqual(msg["from_address"], "noreply@example.com")
        self.assertTrue(msg["has_html"])
        self.assertEqual(msg["timestamp"], 1710000000)

    def test_get_message_detail_uses_list_fallback_when_detail_unavailable(self):
        module = _load_moemail_module()
        provider_cls = module.MoemailTempMailProvider

        mailbox = {
            "email": "demo@moemail.app",
            "meta": {"provider_mailbox_id": "mailbox_1"},
        }

        with self.app.app_context():
            provider = provider_cls(provider_name="moemail")

            detail_404 = MagicMock()
            detail_404.ok = False
            detail_404.status_code = 404
            detail_404.text = "not found"

            list_ok = MagicMock()
            list_ok.ok = True
            list_ok.status_code = 200
            list_ok.json.return_value = {
                "messages": [
                    {
                        "id": "msg_1",
                        "from": "sender@example.com",
                        "subject": "welcome",
                        "text": "hello",
                        "received_at": 1710000000,
                    }
                ]
            }

            with patch("requests.get", side_effect=[detail_404, list_ok]):
                detail = provider.get_message_detail(mailbox, "moemail_msg_1")

        self.assertIsNotNone(detail)
        self.assertEqual(detail["id"], "moemail_msg_1")
        self.assertEqual(detail["subject"], "welcome")


if __name__ == "__main__":
    unittest.main()
