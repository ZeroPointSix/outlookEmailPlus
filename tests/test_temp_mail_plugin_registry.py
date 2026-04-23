"""层 A：注册表与装饰器测试

验证 _REGISTRY、register_provider 装饰器和 get_registry 的基础行为。
"""

from __future__ import annotations

import unittest


class TestPluginRegistry(unittest.TestCase):
    """TDD-A: 注册表与装饰器"""

    def setUp(self):
        """每个测试前，导入基类模块并记录注册表初始状态"""
        from outlook_web.services.temp_mail_provider_base import _REGISTRY, TempMailProviderBase

        self._registry = _REGISTRY
        self._base_cls = TempMailProviderBase
        self._initial_keys = set(_REGISTRY.keys())

    def tearDown(self):
        """每个测试后，清理测试注册的 provider，恢复注册表"""
        for key in set(self._registry.keys()) - self._initial_keys:
            del self._registry[key]

    # A-REG-01
    def test_register_provider_adds_to_registry(self):
        """正常注册：装饰器将 provider 注册到 _REGISTRY"""
        from outlook_web.services.temp_mail_provider_base import register_provider

        @register_provider
        class TestProviderA(self._base_cls):
            provider_name = "test_provider_a"
            provider_label = "Test A"
            provider_version = "1.0.0"

            def get_options(self):
                return {}

            def create_mailbox(self, **kw):
                return {}

            def delete_mailbox(self, mailbox):
                return True

            def list_messages(self, mailbox):
                return []

            def get_message_detail(self, mailbox, message_id):
                return None

            def delete_message(self, mailbox, message_id):
                return True

            def clear_messages(self, mailbox):
                return True

        self.assertIn("test_provider_a", self._registry)
        self.assertIs(self._registry["test_provider_a"], TestProviderA)

    # A-REG-02
    def test_register_provider_empty_name_ignored(self):
        """provider_name 为空字符串时不注册"""
        from outlook_web.services.temp_mail_provider_base import register_provider

        @register_provider
        class EmptyNameProvider(self._base_cls):
            provider_name = ""
            provider_label = "Empty"
            provider_version = "1.0.0"

            def get_options(self):
                return {}

            def create_mailbox(self, **kw):
                return {}

            def delete_mailbox(self, mailbox):
                return True

            def list_messages(self, mailbox):
                return []

            def get_message_detail(self, mailbox, message_id):
                return None

            def delete_message(self, mailbox, message_id):
                return True

            def clear_messages(self, mailbox):
                return True

        self.assertNotIn("", self._registry)

    # A-REG-03
    def test_register_provider_nonstring_name_ignored(self):
        """provider_name 为非字符串时不注册"""
        from outlook_web.services.temp_mail_provider_base import register_provider

        @register_provider
        class IntNameProvider(self._base_cls):
            provider_name = 123

            def get_options(self):
                return {}

            def create_mailbox(self, **kw):
                return {}

            def delete_mailbox(self, mailbox):
                return True

            def list_messages(self, mailbox):
                return []

            def get_message_detail(self, mailbox, message_id):
                return None

            def delete_message(self, mailbox, message_id):
                return True

            def clear_messages(self, mailbox):
                return True

        self.assertNotIn(123, self._registry)

    # A-REG-04
    def test_register_provider_overwrites_duplicate(self):
        """同名重复注册时，后注册的覆盖先注册的"""
        from outlook_web.services.temp_mail_provider_base import register_provider

        @register_provider
        class ProviderV1(self._base_cls):
            provider_name = "dup_provider"
            provider_version = "1.0.0"

            def get_options(self):
                return {}

            def create_mailbox(self, **kw):
                return {}

            def delete_mailbox(self, mailbox):
                return True

            def list_messages(self, mailbox):
                return []

            def get_message_detail(self, mailbox, message_id):
                return None

            def delete_message(self, mailbox, message_id):
                return True

            def clear_messages(self, mailbox):
                return True

        @register_provider
        class ProviderV2(self._base_cls):
            provider_name = "dup_provider"
            provider_version = "2.0.0"

            def get_options(self):
                return {}

            def create_mailbox(self, **kw):
                return {}

            def delete_mailbox(self, mailbox):
                return True

            def list_messages(self, mailbox):
                return []

            def get_message_detail(self, mailbox, message_id):
                return None

            def delete_message(self, mailbox, message_id):
                return True

            def clear_messages(self, mailbox):
                return True

        self.assertIs(self._registry["dup_provider"], ProviderV2)
        self.assertEqual(self._registry["dup_provider"].provider_version, "2.0.0")

    # A-REG-05
    def test_get_registry_returns_snapshot(self):
        """get_registry 返回注册表快照（只读副本）"""
        from outlook_web.services.temp_mail_provider_base import get_registry, register_provider

        snapshot1 = get_registry()

        @register_provider
        class SnapshotTestProvider(self._base_cls):
            provider_name = "snapshot_test"
            provider_version = "1.0.0"

            def get_options(self):
                return {}

            def create_mailbox(self, **kw):
                return {}

            def delete_mailbox(self, mailbox):
                return True

            def list_messages(self, mailbox):
                return []

            def get_message_detail(self, mailbox, message_id):
                return None

            def delete_message(self, mailbox, message_id):
                return True

            def clear_messages(self, mailbox):
                return True

        snapshot2 = get_registry()
        self.assertNotIn("snapshot_test", snapshot1)
        self.assertIn("snapshot_test", snapshot2)

    # A-REG-06
    def test_builtin_providers_auto_registered(self):
        """内置 provider 通过 import 自动注册到 _REGISTRY"""
        from outlook_web.services.temp_mail_provider_base import _REGISTRY

        self.assertIn("cloudflare_temp_mail", _REGISTRY)
        self.assertIn("custom_domain_temp_mail", _REGISTRY)


if __name__ == "__main__":
    unittest.main()
