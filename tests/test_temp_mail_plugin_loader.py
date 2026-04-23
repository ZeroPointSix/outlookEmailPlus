"""层 C：插件目录扫描与热刷新测试

验证 load_plugins() 和 reload_plugins() 的行为，重点是错误隔离。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

MOCK_PLUGIN_CODE = """
from outlook_web.services.temp_mail_provider_base import TempMailProviderBase, register_provider

@register_provider
class MockLoadProvider(TempMailProviderBase):
    provider_name = "mock_load"
    provider_label = "Mock Load"
    provider_version = "0.1.0"
    def get_options(self): return {}
    def create_mailbox(self, **kw): return {}
    def delete_mailbox(self, mailbox): return True
    def list_messages(self, mailbox): return []
    def get_message_detail(self, mailbox, message_id): return None
    def delete_message(self, mailbox, message_id): return True
    def clear_messages(self, mailbox): return True
"""

BAD_SYNTAX_PLUGIN = """
def this is bad syntax ( :
"""

IMPORT_ERROR_PLUGIN = """
import nonexistent_module_xyz
from outlook_web.services.temp_mail_provider_base import TempMailProviderBase
class NoRegProvider(TempMailProviderBase):
    provider_name = "import_err"
    def get_options(self): return {}
    def create_mailbox(self, **kw): return {}
    def delete_mailbox(self, mailbox): return True
    def list_messages(self, mailbox): return []
    def get_message_detail(self, mailbox, message_id): return None
    def delete_message(self, mailbox, message_id): return True
    def clear_messages(self, mailbox): return True
"""

NO_DECORATOR_PLUGIN = """
from outlook_web.services.temp_mail_provider_base import TempMailProviderBase
class NoDecorProvider(TempMailProviderBase):
    provider_name = "no_decor"
    def get_options(self): return {}
    def create_mailbox(self, **kw): return {}
    def delete_mailbox(self, mailbox): return True
    def list_messages(self, mailbox): return []
    def get_message_detail(self, mailbox, message_id): return None
    def delete_message(self, mailbox, message_id): return True
    def clear_messages(self, mailbox): return True
"""

SECOND_PLUGIN_CODE = """
from outlook_web.services.temp_mail_provider_base import TempMailProviderBase, register_provider

@register_provider
class MockSecondProvider(TempMailProviderBase):
    provider_name = "mock_second"
    provider_label = "Mock Second"
    provider_version = "0.2.0"
    def get_options(self): return {}
    def create_mailbox(self, **kw): return {}
    def delete_mailbox(self, mailbox): return True
    def list_messages(self, mailbox): return []
    def get_message_detail(self, mailbox, message_id): return None
    def delete_message(self, mailbox, message_id): return True
    def clear_messages(self, mailbox): return True
"""


class TestPluginLoader(unittest.TestCase):
    """TDD-C: 插件目录扫描与加载"""

    def _cleanup_test_plugins(self):
        if not self._tmp_dir.exists():
            return
        for pattern in ("mock_*.py", "bad_*.py", "no_*.py", "import_*.py"):
            for file in self._tmp_dir.glob(pattern):
                file.unlink(missing_ok=True)

    def setUp(self):
        from outlook_web.services import temp_mail_provider_factory as factory
        from tests._import_app import import_web_app_module

        self._app_mod = import_web_app_module()
        self._app = self._app_mod.app
        self._tmp_dir = Path(self._app_mod.app.config["DATABASE_PATH"]).parent / "plugins" / "temp_mail_providers"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

        from outlook_web.services.temp_mail_provider_base import _REGISTRY

        self._registry = _REGISTRY
        self._initial_keys = set(_REGISTRY.keys())
        factory._FAILED_PLUGIN_MTIMES.clear()
        factory._PLUGIN_LOAD_STATE.clear()
        self._cleanup_test_plugins()

    def tearDown(self):
        from outlook_web.services import temp_mail_provider_factory as factory

        # 清理测试注册的 provider
        for key in set(self._registry.keys()) - self._initial_keys:
            del self._registry[key]
        # 清理 sys.modules 中的测试模块
        for key in list(sys.modules.keys()):
            if key.startswith("_plugin_"):
                del sys.modules[key]
        factory._FAILED_PLUGIN_MTIMES.clear()
        factory._PLUGIN_LOAD_STATE.clear()
        self._cleanup_test_plugins()

    def _write_plugin(self, name: str, content: str):
        (self._tmp_dir / f"{name}.py").write_text(content, encoding="utf-8")

    # C-LOAD-01
    def test_load_plugins_empty_dir(self):
        """空目录返回空列表，不报错"""
        from outlook_web.services.temp_mail_provider_factory import load_plugins

        results = load_plugins()
        self.assertEqual(results, [])

    # C-LOAD-02
    def test_load_plugins_valid_plugin(self):
        """目录中有一个合法插件时正确加载"""
        from outlook_web.services.temp_mail_provider_factory import load_plugins

        self._write_plugin("mock_load", MOCK_PLUGIN_CODE)
        results = load_plugins()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "mock_load")
        self.assertEqual(results[0]["status"], "loaded")
        self.assertIn("mock_load", self._registry)

    # C-LOAD-03
    def test_load_plugins_syntax_error(self):
        """插件文件有语法错误时返回失败项，内置 provider 不受影响"""
        from outlook_web.services.temp_mail_provider_factory import load_plugins

        self._write_plugin("bad_syntax", BAD_SYNTAX_PLUGIN)
        results = load_plugins()

        failed = [r for r in results if r["status"] == "failed"]
        self.assertTrue(len(failed) > 0)
        self.assertIn("bad_syntax", failed[0]["name"])
        self.assertIn("SyntaxError", failed[0]["error"])
        # 内置 provider 仍在
        self.assertIn("cloudflare_temp_mail", self._registry)
        self.assertIn("custom_domain_temp_mail", self._registry)

    # C-LOAD-04
    def test_load_plugins_import_error(self):
        """插件 import 了不存在的模块"""
        from outlook_web.services.temp_mail_provider_factory import load_plugins

        self._write_plugin("import_err", IMPORT_ERROR_PLUGIN)
        results = load_plugins()

        failed = [r for r in results if r["status"] == "failed"]
        self.assertTrue(len(failed) > 0)
        self.assertIn("import_err", failed[0]["name"])

    # C-LOAD-05
    def test_load_plugins_missing_decorator(self):
        """插件类未加 @register_provider 时加载成功但不注册"""
        from outlook_web.services.temp_mail_provider_factory import load_plugins

        self._write_plugin("no_decor", NO_DECORATOR_PLUGIN)
        results = load_plugins()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "loaded")
        self.assertNotIn("no_decor", self._registry)

    # C-LOAD-06
    def test_load_plugins_skips_underscore_files(self):
        """以 _ 开头的文件被忽略"""
        from outlook_web.services.temp_mail_provider_factory import load_plugins

        self._write_plugin("_helper", MOCK_PLUGIN_CODE)
        results = load_plugins()
        names = [r["name"] for r in results]
        self.assertNotIn("_helper", names)

    # C-LOAD-07
    def test_load_plugins_multiple_files(self):
        """多个插件文件按文件名字母序依次加载"""
        from outlook_web.services.temp_mail_provider_factory import load_plugins

        self._write_plugin("mock_second", SECOND_PLUGIN_CODE)
        self._write_plugin("mock_load", MOCK_PLUGIN_CODE)
        results = load_plugins()

        loaded = [r for r in results if r["status"] == "loaded"]
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["name"], "mock_load")  # 字母序
        self.assertEqual(loaded[1]["name"], "mock_second")

    # C-LOAD-08
    def test_load_plugins_partial_failure(self):
        """部分成功部分失败"""
        from outlook_web.services.temp_mail_provider_factory import load_plugins

        self._write_plugin("mock_load", MOCK_PLUGIN_CODE)
        self._write_plugin("bad_syntax", BAD_SYNTAX_PLUGIN)
        results = load_plugins()

        loaded = [r for r in results if r["status"] == "loaded"]
        failed = [r for r in results if r["status"] == "failed"]
        self.assertEqual(len(loaded), 1)
        self.assertEqual(len(failed), 1)
        self.assertIn("mock_load", self._registry)

    # C-REL-01
    def test_reload_preserves_builtin_providers(self):
        """热刷新后内置 provider 仍在注册表"""
        from outlook_web.services.temp_mail_provider_factory import reload_plugins

        result = reload_plugins()
        self.assertIn("cloudflare_temp_mail", self._registry)
        self.assertIn("custom_domain_temp_mail", self._registry)

    # C-REL-02
    def test_reload_clears_third_party_before_scan(self):
        """有已注册的第三方插件时，刷新后旧条目被移除，重新从文件加载"""
        from outlook_web.services.temp_mail_provider_base import register_provider
        from outlook_web.services.temp_mail_provider_factory import load_plugins, reload_plugins

        # 手动注册一个不在文件中的第三方 provider
        @register_provider
        class GhostProvider:
            provider_name = "ghost_provider"
            pass

        self.assertIn("ghost_provider", self._registry)
        reload_plugins()
        # ghost_provider 不在文件中，刷新后应被清除
        self.assertNotIn("ghost_provider", self._registry)

    # C-REL-03
    def test_reload_refreshes_updated_plugin(self):
        """修改插件文件后刷新，新版本覆盖旧版本"""
        from outlook_web.services.temp_mail_provider_factory import reload_plugins

        self._write_plugin("mock_load", MOCK_PLUGIN_CODE)
        reload_plugins()
        v1_cls = self._registry.get("mock_load")

        updated_code = MOCK_PLUGIN_CODE.replace('provider_version = "0.1.0"', 'provider_version = "2.0.0"')
        self._write_plugin("mock_load", updated_code)
        reload_plugins()
        v2_cls = self._registry.get("mock_load")

        self.assertIsNot(v1_cls, v2_cls)
        self.assertEqual(v2_cls.provider_version, "2.0.0")

    # C-REL-04
    def test_reload_removed_plugin_gone(self):
        """删除插件文件后刷新，该 provider 从注册表消失"""
        from outlook_web.services.temp_mail_provider_factory import reload_plugins

        self._write_plugin("mock_load", MOCK_PLUGIN_CODE)
        reload_plugins()
        self.assertIn("mock_load", self._registry)

        (self._tmp_dir / "mock_load.py").unlink()
        reload_plugins()
        self.assertNotIn("mock_load", self._registry)

    # C-REL-05
    def test_reload_cleans_sys_modules(self):
        """热刷新后 sys.modules 中 _plugin_ 前缀的模块被清理"""
        from outlook_web.services.temp_mail_provider_factory import reload_plugins

        self._write_plugin("mock_load", MOCK_PLUGIN_CODE)
        reload_plugins()
        # 验证模块被加载到 sys.modules
        self.assertIn("_plugin_mock_load", sys.modules)

        reload_plugins()
        # 模块应被清理后重新加载
        self.assertIn("_plugin_mock_load", sys.modules)

    # C-REL-06
    def test_reload_retains_failed_plugin_state_for_api_consumption(self):
        """同一故障插件重复刷新时，failed 状态仍可被后续接口读取"""
        from outlook_web.services.temp_mail_provider_factory import get_plugin_load_state, reload_plugins

        self._write_plugin("mock_bad_import", IMPORT_ERROR_PLUGIN)

        first = reload_plugins()
        second = reload_plugins()

        self.assertTrue(any(item["name"] == "mock_bad_import" for item in first["failed"]))
        self.assertTrue(any(item["name"] == "mock_bad_import" for item in second["failed"]))
        state = get_plugin_load_state()
        self.assertEqual(state["mock_bad_import"]["status"], "failed")
        self.assertIn("ModuleNotFoundError", state["mock_bad_import"]["error"])


if __name__ == "__main__":
    unittest.main()
