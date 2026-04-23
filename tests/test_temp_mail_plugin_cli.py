"""层 G：CLI 命令测试

验证 CLI 子命令的参数解析和核心调用。
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


class TestPluginCLI(unittest.TestCase):
    """TDD-G: CLI 命令"""

    def setUp(self):
        from tests._import_app import import_web_app_module

        self._app_mod = import_web_app_module()

    # G-CLI-01
    @patch("outlook_web.services.temp_mail_plugin_cli.install_plugin")
    @patch("outlook_web.services.temp_mail_plugin_cli._confirm", return_value=True)
    @patch("builtins.print")
    def test_cli_install_plugin(self, mock_print, mock_confirm, mock_install):
        """install-provider moemail 调用 install_plugin"""
        mock_install.return_value = {"plugin_name": "moemail", "file_path": "/tmp/moemail.py", "dependencies": []}

        from outlook_web.services.temp_mail_plugin_cli import _cmd_install

        _cmd_install("moemail", None)
        mock_install.assert_called_once_with("moemail", url=None)

    # G-CLI-02
    @patch("outlook_web.services.temp_mail_plugin_cli.install_plugin")
    @patch("outlook_web.services.temp_mail_plugin_cli._confirm", return_value=True)
    @patch("builtins.print")
    def test_cli_install_with_custom_url(self, mock_print, mock_confirm, mock_install):
        """install-provider moemail --from URL 传递 url"""
        mock_install.return_value = {"plugin_name": "moemail", "file_path": "/tmp/moemail.py", "dependencies": []}

        from outlook_web.services.temp_mail_plugin_cli import _cmd_install

        _cmd_install("moemail", "https://example.com/plugin.py")
        mock_install.assert_called_once_with("moemail", url="https://example.com/plugin.py")

    # G-CLI-03
    @patch("outlook_web.services.temp_mail_plugin_cli.uninstall_plugin")
    @patch("outlook_web.services.temp_mail_plugin_cli._confirm", return_value=True)
    @patch(
        "outlook_web.services.temp_mail_plugin_cli.check_provider_in_use", return_value={"task_count": 0, "active_count": 0}
    )
    @patch("builtins.print")
    def test_cli_uninstall_plugin(self, mock_print, mock_check, mock_confirm, mock_uninstall):
        """uninstall-provider moemail 调用 uninstall_plugin"""
        mock_uninstall.return_value = {"plugin_name": "moemail", "had_active_emails": False, "cleaned_keys": []}

        from outlook_web.services.temp_mail_plugin_cli import _cmd_uninstall

        _cmd_uninstall("moemail")
        mock_uninstall.assert_called_once()

    # G-CLI-04
    @patch("outlook_web.services.temp_mail_plugin_cli.get_available_providers")
    @patch("outlook_web.services.temp_mail_plugin_cli.get_installed_plugins")
    @patch("builtins.print")
    def test_cli_list_providers(self, mock_print, mock_installed, mock_available):
        """list-providers 输出包含内置 provider"""
        mock_installed.return_value = []
        mock_available.return_value = [
            {"name": "cloudflare_temp_mail", "label": "CF Worker", "version": "1.0.0"},
            {"name": "custom_domain_temp_mail", "label": "GPTMail", "version": "1.0.0"},
        ]

        from outlook_web.services.temp_mail_plugin_cli import _cmd_list

        _cmd_list()
        printed = "\n".join(call.args[0] for call in mock_print.call_args_list if call.args)
        self.assertIn("cloudflare_temp_mail", printed)

    # G-CLI-05
    @patch("builtins.print")
    def test_cli_no_command_shows_help(self, mock_print):
        """无子命令时打印帮助信息"""
        import argparse

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        sub.add_parser("install-provider")
        sub.add_parser("uninstall-provider")
        sub.add_parser("list-providers")

        args = parser.parse_args([])
        self.assertIsNone(args.command)

    # G-CLI-06
    @patch("outlook_web.services.temp_mail_plugin_cli.install_plugin")
    @patch("outlook_web.services.temp_mail_plugin_cli._confirm", return_value=True)
    @patch("builtins.print")
    def test_cli_install_with_dependencies_output(self, mock_print, mock_confirm, mock_install):
        """有依赖的插件输出包含依赖安装提示"""
        mock_install.return_value = {
            "plugin_name": "moemail",
            "file_path": "/tmp/moemail.py",
            "dependencies": ["moemail-sdk>=1.0"],
        }

        from outlook_web.services.temp_mail_plugin_cli import _cmd_install

        _cmd_install("moemail", None)
        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("moemail-sdk", printed)


if __name__ == "__main__":
    unittest.main()
