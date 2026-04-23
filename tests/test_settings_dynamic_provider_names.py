"""测试 settings 模块中动态 provider 名称获取函数

验证 get_supported_temp_mail_provider_names()、is_supported_temp_mail_provider_name()
和 validate_temp_mail_provider_name() 三个函数在注册表不同状态下的行为。

测试通过直接操作 outlook_web.temp_mail_registry._REGISTRY 注入/清理测试数据，
每个测试前后确保注册表状态干净。
"""

from __future__ import annotations

import unittest


class _RegistryTestCase(unittest.TestCase):
    """为所有 registry 测试提供统一的 setUp / tearDown。"""

    def setUp(self):
        from outlook_web.temp_mail_registry import _REGISTRY

        self._snapshot = dict(_REGISTRY)
        _REGISTRY.clear()
        # 预填充内置 provider（供需要它的子类使用）
        _REGISTRY["cloudflare_temp_mail"] = type("CF", (), {})
        _REGISTRY["custom_domain_temp_mail"] = type("Custom", (), {})

    def tearDown(self):
        from outlook_web.temp_mail_registry import _REGISTRY

        _REGISTRY.clear()
        _REGISTRY.update(self._snapshot)


# ── 1. get_supported_temp_mail_provider_names ─────────────


class TestGetSupportedTempMailProviderNames(_RegistryTestCase):
    """测试动态获取已注册 provider 名称集合。"""

    def test_returns_empty_set_when_registry_is_empty(self):
        """注册表为空时，函数应返回空集合。"""
        from outlook_web.repositories.settings import get_supported_temp_mail_provider_names
        from outlook_web.temp_mail_registry import _REGISTRY

        _REGISTRY.clear()
        result = get_supported_temp_mail_provider_names()
        self.assertEqual(result, set())

    def test_returns_builtin_provider_names(self):
        """注册表中有内置 provider 时，函数应返回正确的名称集合。"""
        from outlook_web.repositories.settings import get_supported_temp_mail_provider_names

        result = get_supported_temp_mail_provider_names()
        self.assertEqual(result, {"cloudflare_temp_mail", "custom_domain_temp_mail"})

    def test_includes_dynamically_added_plugin_provider(self):
        """动态添加插件 provider 后，函数应包含新增名称。"""
        from outlook_web.repositories.settings import get_supported_temp_mail_provider_names
        from outlook_web.temp_mail_registry import _REGISTRY

        _REGISTRY["my_plugin_provider"] = type("Plugin", (), {})

        result = get_supported_temp_mail_provider_names()
        self.assertIn("my_plugin_provider", result)
        self.assertIn("cloudflare_temp_mail", result)

    def test_returns_copy_not_reference(self):
        """返回值应为注册表键的副本，修改返回值不影响注册表。"""
        from outlook_web.repositories.settings import get_supported_temp_mail_provider_names
        from outlook_web.temp_mail_registry import _REGISTRY

        result = get_supported_temp_mail_provider_names()
        result.add("fake_provider")
        self.assertNotIn("fake_provider", _REGISTRY)

    def test_reflects_registry_removal(self):
        """从注册表中移除 provider 后，函数不再包含该名称。"""
        from outlook_web.repositories.settings import get_supported_temp_mail_provider_names
        from outlook_web.temp_mail_registry import _REGISTRY

        del _REGISTRY["cloudflare_temp_mail"]

        result = get_supported_temp_mail_provider_names()
        self.assertNotIn("cloudflare_temp_mail", result)
        self.assertIn("custom_domain_temp_mail", result)


# ── 2. is_supported_temp_mail_provider_name ───────────────


class TestIsSupportedTempMailProviderName(_RegistryTestCase):
    """测试判断 provider 名称是否已注册。"""

    def test_returns_true_for_registered_name(self):
        """已注册名称应返回 True。"""
        from outlook_web.repositories.settings import is_supported_temp_mail_provider_name

        self.assertTrue(is_supported_temp_mail_provider_name("cloudflare_temp_mail"))
        self.assertTrue(is_supported_temp_mail_provider_name("custom_domain_temp_mail"))

    def test_returns_false_for_unregistered_name(self):
        """未注册名称应返回 False。"""
        from outlook_web.repositories.settings import is_supported_temp_mail_provider_name

        self.assertFalse(is_supported_temp_mail_provider_name("nonexistent_provider"))

    def test_returns_false_when_registry_is_empty(self):
        """注册表为空时，任何名称都应返回 False。"""
        from outlook_web.repositories.settings import is_supported_temp_mail_provider_name
        from outlook_web.temp_mail_registry import _REGISTRY

        _REGISTRY.clear()
        self.assertFalse(is_supported_temp_mail_provider_name("any_provider"))

    def test_returns_true_for_newly_added_plugin(self):
        """动态添加插件 provider 后，is_supported 应识别新名称。"""
        from outlook_web.repositories.settings import is_supported_temp_mail_provider_name
        from outlook_web.temp_mail_registry import _REGISTRY

        _REGISTRY["new_plugin"] = type("New", (), {})

        self.assertTrue(is_supported_temp_mail_provider_name("new_plugin"))

    def test_returns_false_after_provider_removed(self):
        """provider 被移除后，is_supported 应返回 False。"""
        from outlook_web.repositories.settings import is_supported_temp_mail_provider_name
        from outlook_web.temp_mail_registry import _REGISTRY

        del _REGISTRY["cloudflare_temp_mail"]

        self.assertFalse(is_supported_temp_mail_provider_name("cloudflare_temp_mail"))

    def test_none_input_returns_false_in_empty_registry(self):
        """None 输入在空注册表时应返回 False。"""
        from outlook_web.repositories.settings import is_supported_temp_mail_provider_name
        from outlook_web.temp_mail_registry import _REGISTRY

        _REGISTRY.clear()
        self.assertFalse(is_supported_temp_mail_provider_name(None))


# ── 3. validate_temp_mail_provider_name ───────────────────


class TestValidateTempMailProviderName(_RegistryTestCase):
    """测试验证并归一化 provider 名称。"""

    def test_returns_name_for_valid_provider(self):
        """有效名称应原样返回该名称。"""
        from outlook_web.repositories.settings import validate_temp_mail_provider_name

        self.assertEqual(validate_temp_mail_provider_name("cloudflare_temp_mail"), "cloudflare_temp_mail")

    def test_raises_value_error_for_invalid_provider(self):
        """无效名称应抛出 ValueError。"""
        from outlook_web.repositories.settings import validate_temp_mail_provider_name

        with self.assertRaises(ValueError) as ctx:
            validate_temp_mail_provider_name("nonexistent_provider")
        self.assertIn("临时邮箱 Provider 配置无效", str(ctx.exception))

    def test_raises_value_error_when_registry_is_empty(self):
        """注册表为空时，任何名称都应抛出 ValueError。"""
        from outlook_web.repositories.settings import validate_temp_mail_provider_name
        from outlook_web.temp_mail_registry import _REGISTRY

        _REGISTRY.clear()
        with self.assertRaises(ValueError) as ctx:
            validate_temp_mail_provider_name("any_provider")
        self.assertIn("临时邮箱 Provider 配置无效", str(ctx.exception))

    def test_validates_newly_added_plugin(self):
        """动态添加的插件 provider 应通过验证。"""
        from outlook_web.repositories.settings import validate_temp_mail_provider_name
        from outlook_web.temp_mail_registry import _REGISTRY

        _REGISTRY["plugin_provider"] = type("Plugin", (), {})

        self.assertEqual(validate_temp_mail_provider_name("plugin_provider"), "plugin_provider")

    def test_raises_after_provider_removed(self):
        """provider 被移除后，验证应抛出 ValueError。"""
        from outlook_web.repositories.settings import validate_temp_mail_provider_name
        from outlook_web.temp_mail_registry import _REGISTRY

        del _REGISTRY["cloudflare_temp_mail"]

        with self.assertRaises(ValueError) as ctx:
            validate_temp_mail_provider_name("cloudflare_temp_mail")
        self.assertIn("临时邮箱 Provider 配置无效", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
