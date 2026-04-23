"""层 H：模拟插件端到端测试

通过一个完整的模拟插件，验证从安装到使用的全链路。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

E2E_PLUGIN_CODE = b"""
from outlook_web.services.temp_mail_provider_base import TempMailProviderBase, register_provider

@register_provider
class E2ETestProvider(TempMailProviderBase):
    provider_name = "e2e_test"
    provider_label = "E2E Test Provider"
    provider_version = "1.0.0"
    provider_author = "e2e"

    config_schema = {
        "fields": [
            {"key": "base_url", "label": "API", "type": "text", "required": True},
            {"key": "api_key", "label": "Key", "type": "password", "required": True},
        ]
    }

    def __init__(self, *, provider_name=None):
        self.provider_name = provider_name or "e2e_test"
        from outlook_web.repositories import settings as repo
        prefix = f"plugin.{self.provider_name}"
        self._base_url = repo.get_setting(f"{prefix}.base_url", "")
        self._api_key = repo.get_setting(f"{prefix}.api_key", "")

    def get_options(self):
        return {
            "domains": [{"name": "e2etest.com", "enabled": True}],
            "provider": self.provider_name,
        }

    def create_mailbox(self, *, prefix=None, domain=None):
        email = f"{prefix or 'user'}@{domain or 'e2etest.com'}"
        return {"success": True, "email": email, "meta": {"test": True}}

    def delete_mailbox(self, mailbox):
        return True

    def list_messages(self, mailbox):
        return [
            {"id": "msg1", "from": "sender@test.com", "subject": "Hello", "body": "Code: 123456"},
            {"id": "msg2", "from": "noreply@test.com", "subject": "Verify", "body": "Your code is 654321"},
        ]

    def get_message_detail(self, mailbox, message_id):
        if message_id == "msg1":
            return {"id": "msg1", "from": "sender@test.com", "subject": "Hello", "text": "Code: 123456", "html": "<b>Code: 123456</b>"}
        return None

    def delete_message(self, mailbox, message_id):
        return True

    def clear_messages(self, mailbox):
        return True
"""

E2E_REGISTRY = {
    "version": 1,
    "plugins": [
        {
            "name": "e2e_test",
            "display_name": "E2E Test Provider",
            "version": "1.0.0",
            "author": "e2e",
            "description": "End-to-end test plugin",
            "download_url": "http://localhost:9999/e2e_test.py",
            "sha256": "abc123",
            "min_app_version": "1.13.0",
        }
    ],
}


class TestPluginE2E(unittest.TestCase):
    """TDD-H: 模拟插件端到端"""

    def setUp(self):
        from outlook_web.config import get_database_path
        from tests._import_app import import_web_app_module

        self._app_mod = import_web_app_module()
        self._app = self._app_mod.app
        self._client = self._app.test_client()
        self._base_dir = Path(get_database_path()).parent
        self._tmp_dir = self._base_dir / "plugins" / "temp_mail_providers"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self._registry_file = self._base_dir / "plugins" / "registry.json"
        self._registry_file.parent.mkdir(parents=True, exist_ok=True)

        from outlook_web.services.temp_mail_provider_base import _REGISTRY

        self._registry = _REGISTRY
        self._initial_keys = set(_REGISTRY.keys())

        # 模拟登录 session
        with self._client.session_transaction() as sess:
            sess["user_id"] = 1

    def tearDown(self):
        for key in set(self._registry.keys()) - self._initial_keys:
            del self._registry[key]
        for key in list(sys.modules.keys()):
            if key.startswith("_plugin_"):
                del sys.modules[key]
        for f in self._tmp_dir.glob("e2e_*.py"):
            f.unlink(missing_ok=True)
        if self._registry_file.exists():
            self._registry_file.unlink()
        # 清理配置
        from outlook_web.repositories import settings as repo

        for k in ["plugin.e2e_test.base_url", "plugin.e2e_test.api_key"]:
            repo.set_setting(k, "")

    def _write_registry(self):
        self._registry_file.write_text(json.dumps(E2E_REGISTRY), encoding="utf-8")

    # H-E2E-01
    @patch("outlook_web.services.temp_mail_plugin_manager.requests")
    def test_e2e_install_configure_reload_use(self, mock_requests):
        """安装 → 配置 → 热刷新 → 使用"""
        self._write_registry()

        # 1. 安装
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = E2E_PLUGIN_CODE
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        from outlook_web.services.temp_mail_plugin_manager import install_plugin

        result = install_plugin("e2e_test")
        self.assertEqual(result["plugin_name"], "e2e_test")
        self.assertTrue((self._tmp_dir / "e2e_test.py").exists())

        # 2. 配置
        from outlook_web.services.temp_mail_plugin_manager import save_plugin_config

        save_plugin_config("e2e_test", {"base_url": "http://e2e.test", "api_key": "test_key"})

        # 3. 热刷新
        from outlook_web.services.temp_mail_provider_factory import reload_plugins

        reload_result = reload_plugins()
        self.assertIn("e2e_test", self._registry)

        # 4. 使用 - get_options
        provider_cls = self._registry["e2e_test"]
        provider = provider_cls(provider_name="e2e_test")
        options = provider.get_options()
        self.assertEqual(len(options["domains"]), 1)
        self.assertEqual(options["domains"][0]["name"], "e2etest.com")

    # H-E2E-02
    def test_e2e_install_bad_plugin_error_isolation(self):
        """安装有语法错误的插件，系统正常运行"""
        bad_plugin = b"def this is broken ( :\n"
        (self._tmp_dir / "bad_e2e.py").write_bytes(bad_plugin)

        from outlook_web.services.temp_mail_provider_factory import reload_plugins

        result = reload_plugins()
        failed_names = [f["name"] for f in result["failed"]]
        self.assertIn("bad_e2e", failed_names)

        # 内置 provider 不受影响
        self.assertIn("cloudflare_temp_mail", self._registry)

        # 系统仍可正常使用内置 provider
        resp = self._client.get("/api/system/health")
        self.assertEqual(resp.status_code, 200)

    # H-E2E-03
    @patch("outlook_web.services.temp_mail_plugin_manager.requests")
    def test_e2e_uninstall_after_use(self, mock_requests):
        """使用后卸载，文件删除，历史邮箱记录保留"""
        self._write_registry()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = E2E_PLUGIN_CODE
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        from outlook_web.services.temp_mail_plugin_manager import install_plugin, uninstall_plugin
        from outlook_web.services.temp_mail_provider_factory import reload_plugins

        install_plugin("e2e_test")
        reload_plugins()
        self.assertIn("e2e_test", self._registry)

        # 模拟创建邮箱记录
        from outlook_web.db import get_db

        with self._app.app_context():
            db = get_db()
            db.execute(
                "INSERT INTO temp_emails (email, source, status) VALUES (?, ?, ?)",
                ("user@e2etest.com", "e2e_test", "active"),
            )
            db.commit()

        # 卸载（clean_config=False 保留配置和邮箱记录）
        result = uninstall_plugin("e2e_test", clean_config=False)
        self.assertEqual(result["plugin_name"], "e2e_test")
        self.assertFalse((self._tmp_dir / "e2e_test.py").exists())

        # 历史邮箱记录保留
        with self._app.app_context():
            db = get_db()
            row = db.execute("SELECT * FROM temp_emails WHERE source = 'e2e_test'").fetchone()
            self.assertIsNotNone(row)

            db.execute("DELETE FROM temp_emails WHERE source = 'e2e_test'")
            db.commit()

    # H-E2E-04
    @patch("outlook_web.services.temp_mail_plugin_manager.requests")
    def test_e2e_config_persistence(self, mock_requests):
        """配置后重启读取，settings 表中配置值持久化"""
        self._write_registry()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = E2E_PLUGIN_CODE
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        from outlook_web.repositories import settings as repo
        from outlook_web.services.temp_mail_plugin_manager import install_plugin, read_plugin_config, save_plugin_config
        from outlook_web.services.temp_mail_provider_factory import reload_plugins

        install_plugin("e2e_test")
        reload_plugins()  # 加载插件到注册表，使 read_plugin_config 可读取 config_schema
        save_plugin_config("e2e_test", {"base_url": "http://persist.test", "api_key": "persist_key"})

        # 直接从 settings 表读取验证持久化
        url = repo.get_setting("plugin.e2e_test.base_url")
        key = repo.get_setting("plugin.e2e_test.api_key")
        self.assertEqual(url, "http://persist.test")
        self.assertEqual(key, "persist_key")

        # 通过 read_plugin_config 读取
        result = read_plugin_config("e2e_test")
        self.assertEqual(result["config"]["base_url"], "http://persist.test")

    # H-E2E-05
    @patch("outlook_web.services.temp_mail_plugin_manager.requests")
    def test_e2e_reload_with_updated_plugin(self, mock_requests):
        """更新插件后刷新，注册表使用新版本"""
        self._write_registry()

        # 安装 v1
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = E2E_PLUGIN_CODE
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        from outlook_web.services.temp_mail_plugin_manager import install_plugin
        from outlook_web.services.temp_mail_provider_factory import reload_plugins

        install_plugin("e2e_test")
        reload_plugins()
        v1_cls = self._registry["e2e_test"]
        self.assertEqual(v1_cls.provider_version, "1.0.0")

        # 更新为 v2
        updated = E2E_PLUGIN_CODE.replace(b'provider_version = "1.0.0"', b'provider_version = "2.0.0"')
        (self._tmp_dir / "e2e_test.py").write_bytes(updated)
        reload_plugins()
        v2_cls = self._registry["e2e_test"]
        self.assertEqual(v2_cls.provider_version, "2.0.0")
        self.assertIsNot(v1_cls, v2_cls)

    # H-E2E-06
    @patch("outlook_web.services.temp_mail_plugin_manager.requests")
    def test_e2e_plugin_provider_business_chain(self, mock_requests):
        """使用插件 provider 完成创建→读信→提取全链路"""
        self._write_registry()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = E2E_PLUGIN_CODE
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        from outlook_web.services.temp_mail_plugin_manager import install_plugin
        from outlook_web.services.temp_mail_provider_factory import reload_plugins

        install_plugin("e2e_test")
        reload_plugins()

        provider_cls = self._registry["e2e_test"]
        provider = provider_cls(provider_name="e2e_test")

        # 创建邮箱
        mailbox = provider.create_mailbox(prefix="testuser", domain="e2etest.com")
        self.assertTrue(mailbox["success"])
        self.assertEqual(mailbox["email"], "testuser@e2etest.com")

        # 读信
        messages = provider.list_messages(mailbox)
        self.assertIsNotNone(messages)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["id"], "msg1")

        # 获取邮件详情
        detail = provider.get_message_detail(mailbox, "msg1")
        self.assertIsNotNone(detail)
        self.assertIn("123456", detail["text"])


if __name__ == "__main__":
    unittest.main()
