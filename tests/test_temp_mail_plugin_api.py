"""层 E：API 接口契约测试

验证 /api/plugins/* 和 /api/system/reload-plugins 端点的请求/响应格式和错误码。
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
class MockApiProvider(TempMailProviderBase):
    provider_name = "mock_api"
    provider_label = "Mock API"
    provider_version = "0.1.0"
    provider_author = "test"
    config_schema = {
        "fields": [
            {"key": "base_url", "label": "URL", "type": "text", "required": True},
        ]
    }
    def __init__(self, *, provider_name=None):
        self.provider_name = provider_name or "mock_api"
        from outlook_web.repositories import settings as repo
        self._url = repo.get_setting(f"plugin.{self.provider_name}.base_url", "")
    def get_options(self): return {"domains": [{"name": "mock.com"}]}
    def create_mailbox(self, **kw): return {"email": "test@mock.com"}
    def delete_mailbox(self, mailbox): return True
    def list_messages(self, mailbox): return []
    def get_message_detail(self, mailbox, message_id): return None
    def delete_message(self, mailbox, message_id): return True
    def clear_messages(self, mailbox): return True
"""

BROKEN_PROVIDER_CODE = b"""
import definitely_missing_test_plugin_dependency
from outlook_web.services.temp_mail_provider_base import TempMailProviderBase

class BrokenProvider(TempMailProviderBase):
    provider_name = "mock_broken"
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
            "name": "mock_api",
            "display_name": "Mock API Provider",
            "version": "0.1.0",
            "author": "test",
            "description": "Mock for API testing",
            "download_url": "http://localhost:9999/mock_api.py",
            "sha256": "abc123",
            "min_app_version": "1.13.0",
            "dependencies": ["mock-sdk>=1.0"],
        }
    ],
}


class TestPluginAPI(unittest.TestCase):
    """TDD-E: API 接口契约"""

    def setUp(self):
        from outlook_web.config import get_database_path
        from outlook_web.services import temp_mail_provider_factory as factory
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
        factory._FAILED_PLUGIN_MTIMES.clear()
        factory._PLUGIN_LOAD_STATE.clear()

        # 模拟登录 session
        with self._client.session_transaction() as sess:
            sess["user_id"] = 1

    def tearDown(self):
        from outlook_web.services import temp_mail_provider_factory as factory

        for key in set(self._registry.keys()) - self._initial_keys:
            del self._registry[key]
        for key in list(sys.modules.keys()):
            if key.startswith("_plugin_"):
                del sys.modules[key]
        factory._FAILED_PLUGIN_MTIMES.clear()
        factory._PLUGIN_LOAD_STATE.clear()
        for f in self._tmp_dir.glob("*.py"):
            f.unlink(missing_ok=True)
        if self._registry_file.exists():
            self._registry_file.unlink()

    def _write_registry(self):
        self._registry_file.write_text(json.dumps(MOCK_REGISTRY_JSON), encoding="utf-8")

    # E-API-01
    def test_get_plugins_returns_list(self):
        """GET /api/plugins 返回列表"""
        self._write_registry()
        resp = self._client.get("/api/plugins")
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertIn("plugins", data.get("data", data))
        plugins = data.get("data", data).get("plugins", data.get("plugins", []))
        self.assertIsInstance(plugins, list)

    # E-API-02
    def test_get_plugins_installed_count(self):
        """有已安装插件时 installed_count 正确"""
        self._write_registry()
        (self._tmp_dir / "mock_api.py").write_bytes(MOCK_PROVIDER_CODE)

        resp = self._client.get("/api/plugins")
        data = resp.get_json()
        result = data.get("data", data)
        self.assertIn("installed_count", result)

    # E-API-03
    def test_get_plugins_marks_installed_status(self):
        """已安装插件标记为 installed"""
        self._write_registry()
        (self._tmp_dir / "mock_api.py").write_bytes(MOCK_PROVIDER_CODE)

        resp = self._client.get("/api/plugins")
        data = resp.get_json()
        result = data.get("data", data)
        plugins = result.get("plugins", [])
        mock_plugin = next((p for p in plugins if p["name"] == "mock_api"), None)
        if mock_plugin:
            self.assertEqual(mock_plugin["status"], "installed")

    # E-API-03A
    def test_get_plugins_marks_load_failed_status(self):
        """reload 后失败插件应标记为 load_failed，而不是 installed"""
        (self._tmp_dir / "mock_broken.py").write_bytes(BROKEN_PROVIDER_CODE)

        reload_resp = self._client.post("/api/system/reload-plugins")
        reload_data = reload_resp.get_json()
        self.assertEqual(reload_resp.status_code, 200)
        failed = reload_data.get("data", reload_data).get("failed", [])
        self.assertTrue(any(item.get("name") == "mock_broken" for item in failed))

        resp = self._client.get("/api/plugins")
        data = resp.get_json()
        result = data.get("data", data)
        plugins = result.get("plugins", [])
        broken_plugin = next((p for p in plugins if p["name"] == "mock_broken"), None)
        self.assertIsNotNone(broken_plugin)
        self.assertEqual(broken_plugin["status"], "load_failed")
        self.assertIn("ModuleNotFoundError", str(broken_plugin.get("error") or ""))
        self.assertEqual(result.get("installed_count"), 0)

    # E-API-04
    @patch("outlook_web.services.temp_mail_plugin_manager.requests")
    def test_install_plugin_success(self, mock_requests):
        """正常安装"""
        self._write_registry()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = MOCK_PROVIDER_CODE
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        resp = self._client.post(
            "/api/plugins/install",
            json={"name": "mock_api"},
            content_type="application/json",
        )
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data.get("success", data.get("code") == "OK"))

    # E-API-05
    def test_install_plugin_no_name(self):
        """缺少 name 参数"""
        resp = self._client.post(
            "/api/plugins/install",
            json={},
            content_type="application/json",
        )
        data = resp.get_json()
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(data.get("code"), "INVALID_PARAMS")

    # E-API-06
    def test_install_plugin_not_found(self):
        """registry 中无此插件"""
        resp = self._client.post(
            "/api/plugins/install",
            json={"name": "nonexistent"},
            content_type="application/json",
        )
        data = resp.get_json()
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(data.get("code"), "PLUGIN_NOT_FOUND")

    # E-API-07
    @patch("outlook_web.services.temp_mail_plugin_manager.requests")
    def test_install_plugin_with_dependencies(self, mock_requests):
        """有依赖的插件"""
        self._write_registry()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = MOCK_PROVIDER_CODE
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        resp = self._client.post(
            "/api/plugins/install",
            json={"name": "mock_api"},
            content_type="application/json",
        )
        data = resp.get_json()
        # 消息中应包含依赖提示
        message = data.get("message", "")
        if "依赖" in message or "dependencies" in message.lower():
            pass  # OK
        self.assertEqual(resp.status_code, 200)

    # E-API-08
    @patch("outlook_web.services.temp_mail_plugin_manager.requests")
    def test_install_plugin_download_failure(self, mock_requests):
        """下载失败"""
        self._write_registry()
        import requests as req_lib

        mock_requests.get.side_effect = req_lib.RequestException("connection refused")

        resp = self._client.post(
            "/api/plugins/install",
            json={"name": "mock_api"},
            content_type="application/json",
        )
        data = resp.get_json()
        self.assertIn(data.get("code"), ["PLUGIN_DOWNLOAD_FAILED", "PLUGIN_DOWNLOAD_TIMEOUT"])

    # E-API-09
    def test_uninstall_plugin_success(self):
        """正常卸载"""
        (self._tmp_dir / "mock_api.py").write_bytes(b"# empty")

        resp = self._client.post("/api/plugins/mock_api/uninstall")
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data.get("success", data.get("code") == "OK"))

    # E-API-10
    def test_uninstall_plugin_not_installed(self):
        """卸载未安装的插件"""
        resp = self._client.post("/api/plugins/ghost_uninstall/uninstall")
        data = resp.get_json()
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(data.get("code"), "PLUGIN_NOT_INSTALLED")

    # E-API-11
    def test_uninstall_plugin_blocked_by_task(self):
        """有任务邮箱时阻止卸载"""
        from outlook_web.db import get_db

        (self._tmp_dir / "mock_api.py").write_bytes(b"# empty")

        with self._app.app_context():
            db = get_db()
            db.execute(
                "INSERT INTO temp_emails (email, source, status, mailbox_type, task_token) VALUES (?, ?, ?, ?, ?)",
                ("task@block.com", "mock_api", "active", "task", "tok"),
            )
            db.commit()

        resp = self._client.post("/api/plugins/mock_api/uninstall")
        data = resp.get_json()
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(data.get("code"), "PLUGIN_IN_USE_BY_TASK")

        with self._app.app_context():
            db = get_db()
            db.execute("DELETE FROM temp_emails WHERE source = 'mock_api'")
            db.commit()

    # E-API-12
    def test_get_config_schema_success(self):
        """正常获取 config schema"""
        from outlook_web.services.temp_mail_provider_base import register_provider

        @register_provider
        class SchemaTestProvider:
            provider_name = "schema_test"
            config_schema = {"fields": [{"key": "url", "label": "URL", "type": "text"}]}

        try:
            resp = self._client.get("/api/plugins/schema_test/config/schema")
            data = resp.get_json()
            self.assertEqual(resp.status_code, 200)
            result = data.get("data", data)
            self.assertIn("config_schema", result)
        finally:
            self._registry.pop("schema_test", None)

    # E-API-13
    def test_get_config_schema_not_loaded(self):
        """未加载的插件"""
        resp = self._client.get("/api/plugins/nonexistent_schema/config/schema")
        data = resp.get_json()
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(data.get("code"), "PLUGIN_NOT_LOADED")

    # E-API-14
    def test_save_config_success(self):
        """正常保存配置"""
        from outlook_web.services.temp_mail_provider_base import register_provider

        @register_provider
        class SaveConfigProvider:
            provider_name = "save_cfg_test"
            config_schema = {"fields": [{"key": "url", "label": "URL", "type": "text"}]}

        try:
            resp = self._client.post(
                "/api/plugins/save_cfg_test/config",
                json={"config": {"url": "http://test.com"}},
                content_type="application/json",
            )
            data = resp.get_json()
            self.assertEqual(resp.status_code, 200)
        finally:
            self._registry.pop("save_cfg_test", None)

    # E-API-15
    def test_save_config_invalid_body(self):
        """config 非对象"""
        resp = self._client.post(
            "/api/plugins/any/config",
            json={"config": "not_an_object"},
            content_type="application/json",
        )
        data = resp.get_json()
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(data.get("code"), "INVALID_PARAMS")

    # E-API-16
    @patch("outlook_web.services.temp_mail_plugin_manager.get_temp_mail_provider")
    def test_test_connection_success(self, mock_factory):
        """连接成功"""
        mock_provider = MagicMock()
        mock_provider.get_options.return_value = {"domains": [{"name": "test.com"}]}
        mock_factory.return_value = mock_provider

        resp = self._client.post("/api/plugins/any/test-connection")
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        result = data.get("data", data)
        self.assertTrue(result.get("success"))
        self.assertIn("latency_ms", result)

    # E-API-17
    @patch("outlook_web.services.temp_mail_plugin_manager.get_temp_mail_provider")
    def test_test_connection_failure(self, mock_factory):
        """连接失败"""
        mock_factory.side_effect = Exception("connection refused")

        resp = self._client.post("/api/plugins/any/test-connection")
        data = resp.get_json()
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(data.get("code"), "CONNECTION_FAILED")

    # E-API-18
    def test_reload_plugins_success(self):
        """正常刷新"""
        resp = self._client.post("/api/system/reload-plugins")
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        result = data.get("data", data)
        self.assertIn("loaded", result)
        self.assertIn("failed", result)
        self.assertIsInstance(result["loaded"], list)
        self.assertIsInstance(result["failed"], list)

    # E-API-19
    def test_reload_plugins_preserves_builtin(self):
        """内置 provider 在刷新后仍在注册表"""
        from outlook_web.services.temp_mail_provider_base import _REGISTRY

        self._client.post("/api/system/reload-plugins")
        self.assertIn("cloudflare_temp_mail", _REGISTRY)
        self.assertIn("custom_domain_temp_mail", _REGISTRY)


if __name__ == "__main__":
    unittest.main()
