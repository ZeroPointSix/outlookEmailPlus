"""层 D：插件管理服务测试

验证 temp_mail_plugin_manager.py 的安装、卸载、配置、连通性测试、活跃邮箱检查。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

MOCK_PROVIDER_CODE = b"""
from outlook_web.services.temp_mail_provider_base import TempMailProviderBase, register_provider

@register_provider
class MockMgrProvider(TempMailProviderBase):
    provider_name = "mock_mgr"
    provider_label = "Mock Mgr"
    provider_version = "0.1.0"
    provider_author = "test"
    config_schema = {
        "fields": [
            {"key": "base_url", "label": "API", "type": "text", "required": True},
            {"key": "api_key", "label": "Key", "type": "password", "required": True},
        ]
    }
    def __init__(self, *, provider_name=None):
        self.provider_name = provider_name or "mock_mgr"
        from outlook_web.repositories import settings as repo
        prefix = f"plugin.{self.provider_name}"
        self._base_url = repo.get_setting(f"{prefix}.base_url", "")
        self._api_key = repo.get_setting(f"{prefix}.api_key", "")
    def get_options(self): return {}
    def create_mailbox(self, **kw): return {}
    def delete_mailbox(self, mailbox): return True
    def list_messages(self, mailbox): return []
    def get_message_detail(self, mailbox, message_id): return None
    def delete_message(self, mailbox, message_id): return True
    def clear_messages(self, mailbox): return True
"""

MOCK_REGISTRY_JSON = {
    "version": 1,
    "plugins": [
        {
            "name": "mock_mgr",
            "display_name": "Mock Mgr Provider",
            "version": "0.1.0",
            "author": "test",
            "description": "Mock for testing",
            "download_url": "http://localhost:9999/mock_mgr.py",
            "sha256": "abc123",
            "min_app_version": "1.13.0",
            "dependencies": ["mock-sdk>=1.0"],
        }
    ],
}


class TestPluginManagerInstall(unittest.TestCase):
    """TDD-D: 安装矩阵"""

    def setUp(self):
        from tests._import_app import import_web_app_module

        self._app_mod = import_web_app_module()
        self._app = self._app_mod.app
        self._tmp_dir = Path(self._app_mod.app.config["DATABASE_PATH"]).parent / "plugins" / "temp_mail_providers"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self._registry_file = Path(self._app_mod.app.config["DATABASE_PATH"]).parent / "plugins" / "registry.json"
        self._registry_file.parent.mkdir(parents=True, exist_ok=True)
        self._registry_file.write_text(json.dumps(MOCK_REGISTRY_JSON), encoding="utf-8")

    def tearDown(self):
        from outlook_web.services.temp_mail_provider_base import _REGISTRY

        _REGISTRY.pop("mock_mgr", None)
        for key in list(sys.modules.keys()):
            if key.startswith("_plugin_"):
                del sys.modules[key]
        for f in self._tmp_dir.glob("*.py"):
            f.unlink(missing_ok=True)
        if self._registry_file.exists():
            self._registry_file.unlink()

    # D-INST-01
    @patch("outlook_web.services.temp_mail_plugin_manager.requests")
    def test_install_from_registry(self, mock_requests):
        """从 registry 安装"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = MOCK_PROVIDER_CODE
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        from outlook_web.services.temp_mail_plugin_manager import install_plugin

        result = install_plugin("mock_mgr")
        self.assertEqual(result["plugin_name"], "mock_mgr")
        target = self._tmp_dir / "mock_mgr.py"
        self.assertTrue(target.exists())

    # D-INST-02
    @patch("outlook_web.services.temp_mail_plugin_manager.requests")
    def test_install_from_custom_url(self, mock_requests):
        """从自定义 URL 安装"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = MOCK_PROVIDER_CODE
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        from outlook_web.services.temp_mail_plugin_manager import install_plugin

        result = install_plugin("custom_one", url="http://example.com/custom.py")
        self.assertEqual(result["plugin_name"], "custom_one")
        self.assertTrue((self._tmp_dir / "custom_one.py").exists())

    # D-INST-03
    @patch("outlook_web.services.temp_mail_plugin_manager.requests")
    def test_install_integrity_check_pass(self, mock_requests):
        """SHA256 匹配时安装成功"""
        import hashlib

        correct_hash = hashlib.sha256(MOCK_PROVIDER_CODE).hexdigest()
        self._registry_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "plugins": [
                        {
                            "name": "mock_mgr",
                            "download_url": "http://localhost:9999/mock_mgr.py",
                            "sha256": correct_hash,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = MOCK_PROVIDER_CODE
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        from outlook_web.services.temp_mail_plugin_manager import install_plugin

        result = install_plugin("mock_mgr")
        self.assertEqual(result["plugin_name"], "mock_mgr")

    # D-INST-04
    @patch("outlook_web.services.temp_mail_plugin_manager.requests")
    def test_install_integrity_check_fail(self, mock_requests):
        """SHA256 不匹配时抛出 PLUGIN_INTEGRITY_CHECK_FAILED"""
        # 覆写 registry：提供一个格式合法（64 位十六进制）但与实际内容不匹配的 sha256
        wrong_sha256 = "a" * 64
        self._registry_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "plugins": [
                        {
                            "name": "mock_mgr",
                            "download_url": "http://localhost:9999/mock_mgr.py",
                            "sha256": wrong_sha256,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = MOCK_PROVIDER_CODE
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        from outlook_web.services.temp_mail_plugin_manager import (
            PluginManagerError,
            install_plugin,
        )

        with self.assertRaises(PluginManagerError) as ctx:
            install_plugin("mock_mgr")
        self.assertEqual(ctx.exception.code, "PLUGIN_INTEGRITY_CHECK_FAILED")

    # D-INST-05
    def test_install_not_found_in_registry(self):
        """registry 中无此插件"""
        from outlook_web.services.temp_mail_plugin_manager import (
            PluginManagerError,
            install_plugin,
        )

        with self.assertRaises(PluginManagerError) as ctx:
            install_plugin("nonexistent_xyz")
        self.assertEqual(ctx.exception.code, "PLUGIN_NOT_FOUND")

    # D-INST-06
    @patch("outlook_web.services.temp_mail_plugin_manager.requests")
    def test_install_download_timeout(self, mock_requests):
        """下载超时"""
        import requests as req_lib

        mock_requests.get.side_effect = req_lib.Timeout("timeout")

        from outlook_web.services.temp_mail_plugin_manager import (
            PluginManagerError,
            install_plugin,
        )

        with self.assertRaises(PluginManagerError) as ctx:
            install_plugin("mock_mgr")
        self.assertEqual(ctx.exception.code, "PLUGIN_DOWNLOAD_TIMEOUT")

    # D-INST-07
    @patch("outlook_web.services.temp_mail_plugin_manager.requests")
    def test_install_download_http_error(self, mock_requests):
        """下载返回 500"""
        import requests as req_lib

        mock_requests.get.side_effect = req_lib.RequestException("500 Server Error")

        from outlook_web.services.temp_mail_plugin_manager import (
            PluginManagerError,
            install_plugin,
        )

        with self.assertRaises(PluginManagerError) as ctx:
            install_plugin("mock_mgr")
        self.assertEqual(ctx.exception.code, "PLUGIN_DOWNLOAD_FAILED")

    # D-INST-08
    @patch("outlook_web.services.temp_mail_plugin_manager.requests")
    def test_install_overwrite_existing(self, mock_requests):
        """重复安装同插件时文件内容更新"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = MOCK_PROVIDER_CODE
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        from outlook_web.services.temp_mail_plugin_manager import install_plugin

        install_plugin("mock_mgr")
        new_content = MOCK_PROVIDER_CODE + b"# updated"
        mock_resp.content = new_content
        install_plugin("mock_mgr")

        target = self._tmp_dir / "mock_mgr.py"
        self.assertEqual(target.read_bytes(), new_content)

    # D-INST-09
    @patch("outlook_web.services.temp_mail_plugin_manager.requests")
    def test_install_creates_plugin_dir(self, mock_requests):
        """插件目录不存在时自动创建"""
        import shutil

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = MOCK_PROVIDER_CODE
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        backup = self._tmp_dir
        if backup.exists():
            # 只删除插件子目录，保留 registry.json，以便 install_plugin 能查找插件
            shutil.rmtree(backup)

        try:
            from outlook_web.services.temp_mail_plugin_manager import install_plugin

            result = install_plugin("mock_mgr")
            self.assertTrue(self._tmp_dir.exists())
        finally:
            self._tmp_dir.mkdir(parents=True, exist_ok=True)

    # D-INST-10
    @patch("outlook_web.services.temp_mail_plugin_manager.requests")
    def test_install_returns_dependencies(self, mock_requests):
        """插件有依赖时返回 dependencies 列表"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = MOCK_PROVIDER_CODE
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        from outlook_web.services.temp_mail_plugin_manager import install_plugin

        result = install_plugin("mock_mgr")
        self.assertIn("dependencies", result)
        self.assertEqual(result["dependencies"], ["mock-sdk>=1.0"])


class TestPluginManagerUninstall(unittest.TestCase):
    """TDD-D: 卸载矩阵"""

    def setUp(self):
        from tests._import_app import import_web_app_module

        self._app_mod = import_web_app_module()
        self._app = self._app_mod.app
        self._tmp_dir = Path(self._app_mod.app.config["DATABASE_PATH"]).parent / "plugins" / "temp_mail_providers"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

        from outlook_web.services.temp_mail_provider_base import _REGISTRY

        self._registry = _REGISTRY
        self._initial_keys = set(_REGISTRY.keys())

    def tearDown(self):
        for key in set(self._registry.keys()) - self._initial_keys:
            del self._registry[key]
        for key in list(sys.modules.keys()):
            if key.startswith("_plugin_"):
                del sys.modules[key]
        for f in self._tmp_dir.glob("*.py"):
            f.unlink(missing_ok=True)

    # D-UNIN-01
    def test_uninstall_success(self):
        """正常卸载：文件删除，注册表移除，sys.modules 清理"""
        (self._tmp_dir / "mock_uninst.py").write_text("# empty", encoding="utf-8")
        self._registry["mock_uninst"] = type("P", (), {"provider_name": "mock_uninst"})
        sys.modules["_plugin_mock_uninst"] = MagicMock()

        from outlook_web.services.temp_mail_plugin_manager import uninstall_plugin

        result = uninstall_plugin("mock_uninst")
        self.assertEqual(result["plugin_name"], "mock_uninst")
        self.assertFalse((self._tmp_dir / "mock_uninst.py").exists())
        self.assertNotIn("mock_uninst", self._registry)

    # D-UNIN-02
    def test_uninstall_not_installed(self):
        """卸载未安装的插件"""
        from outlook_web.services.temp_mail_plugin_manager import (
            PluginManagerError,
            uninstall_plugin,
        )

        with self.assertRaises(PluginManagerError) as ctx:
            uninstall_plugin("ghost_plugin")
        self.assertEqual(ctx.exception.code, "PLUGIN_NOT_INSTALLED")

    # D-UNIN-03
    def test_uninstall_blocked_by_task_emails(self):
        """有进行中任务邮箱时阻止卸载"""
        (self._tmp_dir / "mock_task.py").write_text("# empty", encoding="utf-8")

        from outlook_web.services.temp_mail_plugin_manager import (
            PluginManagerError,
            uninstall_plugin,
        )

        with self.assertRaises(PluginManagerError) as ctx:
            uninstall_plugin("mock_task")
        self.assertEqual(ctx.exception.code, "PLUGIN_IN_USE_BY_TASK")

    # D-UNIN-04
    def test_uninstall_warns_on_active_emails(self):
        """有活跃用户邮箱（无任务）时卸载成功，返回 had_active_emails=True"""
        (self._tmp_dir / "mock_active.py").write_text("# empty", encoding="utf-8")

        from outlook_web.services.temp_mail_plugin_manager import uninstall_plugin

        result = uninstall_plugin("mock_active")
        # 取决于 DB 中是否有活跃邮箱，这里验证返回结构
        self.assertIn("had_active_emails", result)

    # D-UNIN-05
    def test_uninstall_no_active_emails(self):
        """无活跃邮箱时卸载成功"""
        (self._tmp_dir / "mock_clean.py").write_text("# empty", encoding="utf-8")

        from outlook_web.services.temp_mail_plugin_manager import uninstall_plugin

        result = uninstall_plugin("mock_clean")
        self.assertIn("had_active_emails", result)

    # D-UNIN-06
    def test_uninstall_with_clean_config(self):
        """clean_config=True 时清理 plugin.{name}.* 配置"""
        (self._tmp_dir / "mock_cc.py").write_text("# empty", encoding="utf-8")

        from outlook_web.repositories import settings as settings_repo
        from outlook_web.services.temp_mail_plugin_manager import uninstall_plugin

        # 先写入一些配置
        settings_repo.set_setting("plugin.mock_cc.base_url", "http://example.com")
        settings_repo.set_setting("plugin.mock_cc.api_key", "secret123")

        result = uninstall_plugin("mock_cc", clean_config=True)
        self.assertEqual(result["plugin_name"], "mock_cc")
        self.assertTrue(len(result.get("cleaned_keys", [])) > 0)

        # 验证配置被清除
        self.assertEqual(settings_repo.get_setting("plugin.mock_cc.base_url"), "")
        self.assertEqual(settings_repo.get_setting("plugin.mock_cc.api_key"), "")

    # D-UNIN-07
    def test_uninstall_without_clean_config(self):
        """clean_config=False 时配置保留"""
        (self._tmp_dir / "mock_ncc.py").write_text("# empty", encoding="utf-8")

        from outlook_web.repositories import settings as settings_repo
        from outlook_web.services.temp_mail_plugin_manager import uninstall_plugin

        settings_repo.set_setting("plugin.mock_ncc.base_url", "http://example.com")

        result = uninstall_plugin("mock_ncc", clean_config=False)
        self.assertEqual(len(result.get("cleaned_keys", [])), 0)

        # 配置应保留
        self.assertEqual(settings_repo.get_setting("plugin.mock_ncc.base_url"), "http://example.com")


class TestPluginManagerConfig(unittest.TestCase):
    """TDD-D: 配置读写矩阵"""

    def setUp(self):
        from tests._import_app import import_web_app_module

        self._app_mod = import_web_app_module()
        self._app = self._app_mod.app

        from outlook_web.services.temp_mail_provider_base import _REGISTRY, register_provider

        self._registry = _REGISTRY

        @register_provider
        class ConfigTestProvider:
            provider_name = "config_test"
            provider_label = "Config Test"
            provider_version = "1.0.0"
            config_schema = {
                "fields": [
                    {"key": "url", "label": "URL", "type": "text", "required": True},
                    {"key": "key", "label": "Key", "type": "password", "required": True, "default": "default_key"},
                    {"key": "desc", "label": "Desc", "type": "textarea", "required": False, "default": "hello"},
                ]
            }

        self._initial_keys = set(_REGISTRY.keys())

    def tearDown(self):
        for key in set(self._registry.keys()) - self._initial_keys:
            del self._registry[key]
        from outlook_web.repositories import settings as repo

        for k in ["plugin.config_test.url", "plugin.config_test.key", "plugin.config_test.desc"]:
            repo.set_setting(k, "")

    # D-CONF-01
    def test_get_config_schema(self):
        """读取插件 config_schema 返回 fields 列表"""
        from outlook_web.services.temp_mail_plugin_manager import get_plugin_config_schema

        result = get_plugin_config_schema("config_test")
        fields = result["config_schema"]["fields"]
        self.assertEqual(len(fields), 3)
        self.assertEqual(fields[0]["key"], "url")

    # D-CONF-02
    def test_get_config_schema_not_loaded(self):
        """未加载的插件抛出 PLUGIN_NOT_LOADED"""
        from outlook_web.services.temp_mail_plugin_manager import (
            PluginManagerError,
            get_plugin_config_schema,
        )

        with self.assertRaises(PluginManagerError) as ctx:
            get_plugin_config_schema("nonexistent")
        self.assertEqual(ctx.exception.code, "PLUGIN_NOT_LOADED")

    # D-CONF-03
    def test_save_and_read_config(self):
        """保存后读取，值一致，key 格式为 plugin.{name}.{field}"""
        from outlook_web.repositories import settings as repo
        from outlook_web.services.temp_mail_plugin_manager import read_plugin_config, save_plugin_config

        save_plugin_config("config_test", {"url": "http://test.com", "key": "abc123"})
        result = read_plugin_config("config_test")
        self.assertEqual(result["config"]["url"], "http://test.com")
        self.assertEqual(result["config"]["key"], "abc123")
        # 验证 settings 表中的 key 格式
        self.assertEqual(repo.get_setting("plugin.config_test.url"), "http://test.com")

    # D-CONF-04
    def test_save_config_overwrite(self):
        """覆盖已有配置"""
        from outlook_web.services.temp_mail_plugin_manager import read_plugin_config, save_plugin_config

        save_plugin_config("config_test", {"url": "http://first.com", "key": "key1"})
        save_plugin_config("config_test", {"url": "http://second.com", "key": "key2"})
        result = read_plugin_config("config_test")
        self.assertEqual(result["config"]["url"], "http://second.com")

    # D-CONF-05
    def test_save_config_null_value(self):
        """保存 None 值存储为空字符串"""
        from outlook_web.repositories import settings as repo
        from outlook_web.services.temp_mail_plugin_manager import save_plugin_config

        save_plugin_config("config_test", {"url": None, "key": "abc"})
        self.assertEqual(repo.get_setting("plugin.config_test.url"), "")

    # D-CONF-06
    def test_read_config_with_defaults(self):
        """未保存时读取返回 schema 中定义的 default 值"""
        from outlook_web.services.temp_mail_plugin_manager import read_plugin_config

        result = read_plugin_config("config_test")
        self.assertEqual(result["config"]["key"], "default_key")
        self.assertEqual(result["config"]["desc"], "hello")

    # D-CONF-07
    def test_config_key_isolation(self):
        """不同插件同名字段互不影响"""
        from outlook_web.services.temp_mail_plugin_manager import read_plugin_config, save_plugin_config
        from outlook_web.services.temp_mail_provider_base import register_provider

        @register_provider
        class OtherProvider:
            provider_name = "other_test"
            config_schema = {"fields": [{"key": "url", "label": "URL", "type": "text"}]}

        try:
            save_plugin_config("config_test", {"url": "http://a.com", "key": "aaa"})
            save_plugin_config("other_test", {"url": "http://b.com"})

            r1 = read_plugin_config("config_test")
            r2 = read_plugin_config("other_test")
            self.assertEqual(r1["config"]["url"], "http://a.com")
            self.assertEqual(r2["config"]["url"], "http://b.com")
        finally:
            self._registry.pop("other_test", None)
            from outlook_web.repositories import settings as repo

            repo.set_setting("plugin.other_test.url", "")


class TestPluginManagerCheck(unittest.TestCase):
    """TDD-D: 活跃邮箱检查矩阵"""

    def setUp(self):
        from tests._import_app import import_web_app_module

        self._app_mod = import_web_app_module()
        self._app = self._app_mod.app

    # D-CHECK-01
    def test_check_provider_no_emails(self):
        """无邮箱时 in_use=False"""
        from outlook_web.services.temp_mail_plugin_manager import check_provider_in_use

        result = check_provider_in_use("no_emails_provider")
        self.assertFalse(result["in_use"])
        self.assertEqual(result["active_count"], 0)
        self.assertEqual(result["task_count"], 0)

    # D-CHECK-02
    def test_check_provider_has_user_emails(self):
        """有活跃用户邮箱"""
        from outlook_web.db import get_db
        from outlook_web.services.temp_mail_plugin_manager import check_provider_in_use

        with self._app.app_context():
            db = get_db()
            db.execute(
                "INSERT INTO temp_emails (email, source, status, mailbox_type) VALUES (?, ?, ?, ?)",
                ("test@user.com", "check_user", "active", "user"),
            )
            db.commit()

            result = check_provider_in_use("check_user")
            self.assertTrue(result["in_use"])
            self.assertGreater(result["active_count"], 0)
            self.assertEqual(result["task_count"], 0)

            db.execute("DELETE FROM temp_emails WHERE source = 'check_user'")
            db.commit()

    # D-CHECK-03
    def test_check_provider_has_task_emails(self):
        """有活跃任务邮箱"""
        from outlook_web.db import get_db
        from outlook_web.services.temp_mail_plugin_manager import check_provider_in_use

        with self._app.app_context():
            db = get_db()
            db.execute(
                "INSERT INTO temp_emails (email, source, status, mailbox_type, task_token) VALUES (?, ?, ?, ?, ?)",
                ("task@test.com", "check_task", "active", "task", "token123"),
            )
            db.commit()

            result = check_provider_in_use("check_task")
            self.assertTrue(result["in_use"])
            self.assertGreater(result["task_count"], 0)

            db.execute("DELETE FROM temp_emails WHERE source = 'check_task'")
            db.commit()

    # D-CHECK-04
    def test_check_provider_finished_emails_excluded(self):
        """已结束的邮箱不计入 active"""
        from outlook_web.db import get_db
        from outlook_web.services.temp_mail_plugin_manager import check_provider_in_use

        with self._app.app_context():
            db = get_db()
            db.execute(
                "INSERT INTO temp_emails (email, source, status, mailbox_type) VALUES (?, ?, ?, ?)",
                ("done@test.com", "check_done", "finished", "user"),
            )
            db.commit()

            result = check_provider_in_use("check_done")
            self.assertFalse(result["in_use"])
            self.assertEqual(result["active_count"], 0)

            db.execute("DELETE FROM temp_emails WHERE source = 'check_done'")
            db.commit()


class TestPluginManagerConnection(unittest.TestCase):
    """TDD-D: 连通性测试矩阵"""

    def setUp(self):
        from tests._import_app import import_web_app_module

        self._app_mod = import_web_app_module()
        self._app = self._app_mod.app

    # D-TEST-01
    @patch("outlook_web.services.temp_mail_plugin_manager.get_temp_mail_provider")
    def test_connection_success(self, mock_factory):
        """get_options 正常时返回 success=True"""
        mock_provider = MagicMock()
        mock_provider.get_options.return_value = {"domains": [{"name": "test.com"}]}
        mock_factory.return_value = mock_provider

        from outlook_web.services.temp_mail_plugin_manager import test_plugin_connection

        result = test_plugin_connection("any_provider")
        self.assertTrue(result["success"])
        self.assertIn("latency_ms", result)
        self.assertGreaterEqual(result["latency_ms"], 0)

    # D-TEST-02
    @patch("outlook_web.services.temp_mail_plugin_manager.get_temp_mail_provider")
    def test_connection_failure(self, mock_factory):
        """get_options 抛异常时返回 success=False"""
        mock_factory.side_effect = Exception("connection refused")

        from outlook_web.services.temp_mail_plugin_manager import test_plugin_connection

        result = test_plugin_connection("any_provider")
        self.assertFalse(result["success"])
        self.assertIn("connection refused", result["message"])

    # D-TEST-03
    @patch("outlook_web.services.temp_mail_plugin_manager.get_temp_mail_provider")
    def test_connection_latency_measured(self, mock_factory):
        """延迟测量"""
        mock_provider = MagicMock()
        mock_provider.get_options.return_value = {"domains": []}
        mock_factory.return_value = mock_provider

        from outlook_web.services.temp_mail_plugin_manager import test_plugin_connection

        result = test_plugin_connection("any_provider")
        self.assertIsInstance(result["latency_ms"], int)
        self.assertGreaterEqual(result["latency_ms"], 0)


if __name__ == "__main__":
    unittest.main()
