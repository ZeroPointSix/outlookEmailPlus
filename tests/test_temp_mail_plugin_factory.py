"""层 B：工厂改造测试

验证 get_temp_mail_provider() 的查表逻辑和 get_available_providers() 的返回格式。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch


class TestPluginFactory(unittest.TestCase):
    """TDD-B: 工厂改造"""

    def setUp(self):
        from tests._import_app import import_web_app_module

        self._app_mod = import_web_app_module()
        self._app = self._app_mod.app

    # B-FAC-01
    def test_factory_returns_cf_provider(self):
        """查询 CF provider 返回 CloudflareTempMailProvider 实例"""
        from outlook_web.services.temp_mail_provider_cf import CloudflareTempMailProvider
        from outlook_web.services.temp_mail_provider_factory import get_temp_mail_provider

        with patch("outlook_web.services.temp_mail_provider_factory.settings_repo") as mock_repo:
            mock_repo.get_temp_mail_runtime_provider_name.return_value = "cloudflare_temp_mail"
            provider = get_temp_mail_provider("cloudflare_temp_mail")
            self.assertIsInstance(provider, CloudflareTempMailProvider)

    # B-FAC-02
    def test_factory_returns_custom_provider(self):
        """查询 GPTMail provider 返回 CustomTempMailProvider 实例"""
        from outlook_web.services.temp_mail_provider_custom import CustomTempMailProvider
        from outlook_web.services.temp_mail_provider_factory import get_temp_mail_provider

        with patch("outlook_web.services.temp_mail_provider_factory.settings_repo") as mock_repo:
            mock_repo.get_temp_mail_runtime_provider_name.return_value = "custom_domain_temp_mail"
            provider = get_temp_mail_provider("custom_domain_temp_mail")
            self.assertIsInstance(provider, CustomTempMailProvider)

    # B-FAC-03
    def test_factory_raises_on_unknown_provider(self):
        """查询不存在的 provider 抛出 TEMP_MAIL_PROVIDER_INVALID"""
        from outlook_web.services.temp_mail_provider_factory import (
            TempMailProviderFactoryError,
            get_temp_mail_provider,
        )

        with patch("outlook_web.services.temp_mail_provider_factory.settings_repo") as mock_repo:
            mock_repo.get_temp_mail_runtime_provider_name.return_value = "nonexistent_provider"
            with self.assertRaises(TempMailProviderFactoryError) as ctx:
                get_temp_mail_provider("nonexistent_provider")
            self.assertEqual(ctx.exception.code, "TEMP_MAIL_PROVIDER_INVALID")

    # B-FAC-04
    def test_factory_raises_on_not_configured(self):
        """未配置 provider（返回空）抛出 TEMP_MAIL_PROVIDER_NOT_CONFIGURED"""
        from outlook_web.services.temp_mail_provider_factory import (
            TempMailProviderFactoryError,
            get_temp_mail_provider,
        )

        with patch("outlook_web.services.temp_mail_provider_factory.settings_repo") as mock_repo:
            mock_repo.get_temp_mail_runtime_provider_name.return_value = ""
            with self.assertRaises(TempMailProviderFactoryError) as ctx:
                get_temp_mail_provider()
            self.assertEqual(ctx.exception.code, "TEMP_MAIL_PROVIDER_NOT_CONFIGURED")

    # B-FAC-05
    def test_factory_resolves_via_settings(self):
        """通过 settings 表解析 provider 名并返回对应实例"""
        from outlook_web.services.temp_mail_provider_cf import CloudflareTempMailProvider
        from outlook_web.services.temp_mail_provider_factory import get_temp_mail_provider

        with patch("outlook_web.services.temp_mail_provider_factory.settings_repo") as mock_repo:
            mock_repo.get_temp_mail_runtime_provider_name.return_value = "cloudflare_temp_mail"
            provider = get_temp_mail_provider(provider_name="cloudflare_temp_mail")
            self.assertIsInstance(provider, CloudflareTempMailProvider)
            mock_repo.get_temp_mail_runtime_provider_name.assert_called_with("cloudflare_temp_mail")

    # B-FAC-06
    def test_get_available_providers_includes_all(self):
        """获取可用列表包含所有已注册 provider（含内置 + 插件）"""
        from outlook_web.services.temp_mail_provider_base import _REGISTRY, register_provider
        from outlook_web.services.temp_mail_provider_factory import get_available_providers

        # 注册一个测试插件
        @register_provider
        class TestAvailProvider:
            pass

        try:
            providers = get_available_providers()
            names = [p["name"] for p in providers]
            self.assertIn("cloudflare_temp_mail", names)
            self.assertIn("custom_domain_temp_mail", names)
            self.assertIn("test_avail_provider", names)
        finally:
            _REGISTRY.pop("test_avail_provider", None)

    # B-FAC-07
    def test_get_available_providers_sorted(self):
        """列表按 provider_name 字母序排列"""
        from outlook_web.services.temp_mail_provider_factory import get_available_providers

        providers = get_available_providers()
        names = [p["name"] for p in providers]
        self.assertEqual(names, sorted(names))

    # B-FAC-08
    def test_get_available_providers_captures_metadata(self):
        """每项包含 name、label、version、author 元信息"""
        from outlook_web.services.temp_mail_provider_factory import get_available_providers

        providers = get_available_providers()
        self.assertTrue(len(providers) > 0)
        for p in providers:
            self.assertIn("name", p)
            self.assertIn("label", p)
            self.assertIn("version", p)
            self.assertIn("author", p)


if __name__ == "__main__":
    unittest.main()
