"""响应式 detail-focus 机制与 groups 折叠 — 前端契约测试

覆盖范围:
  - HTML 结构: btnToggleGroups、tempEmailDetailSection 默认 display:none、CSS 版本号
  - CSS 契约: 平板/移动端断点中 detail-focus 和 groups-expanded 规则存在
  - JS 契约: emails.js 导出 setMailboxDetailFocus/setTempDetailFocus、main.js 导出 toggleGroupsColumn
  - i18n 契约: 「展开分组」「收起分组」翻译词条
"""

from __future__ import annotations

import re
import unittest

from tests._import_app import import_web_app_module


class ResponsiveDetailFocusContractTests(unittest.TestCase):
    """响应式 detail-focus 机制前端契约测试"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)

    def _get_index_html(self) -> str:
        client = self.app.test_client()
        self._login(client)
        resp = client.get("/")
        try:
            return resp.data.decode("utf-8")
        finally:
            resp.close()

    # ==================== HTML 结构测试 ====================

    def test_btn_toggle_groups_exists_in_accounts_column(self):
        """btnToggleGroups 按钮应存在于 accounts-column header 中"""
        html = self._get_index_html()
        self.assertIn('id="btnToggleGroups"', html)
        self.assertIn("toggleGroupsColumn()", html)
        self.assertIn("btn-toggle-groups", html)

    def test_temp_email_detail_section_default_hidden(self):
        """tempEmailDetailSection 应默认 display:none（移动端/平板端由 JS 控制）"""
        html = self._get_index_html()
        self.assertIn('id="tempEmailDetailSection"', html)
        section = re.search(r'id="tempEmailDetailSection"[^>]*>', html)
        self.assertIsNotNone(section)
        self.assertIn("display:none", section.group(0))

    def test_email_list_panel_exists(self):
        """emailListPanel 应存在于 mailbox workspace 中"""
        html = self._get_index_html()
        self.assertIn('id="emailListPanel"', html)

    def test_css_version_includes_resp_suffix(self):
        """CSS 引用应包含 -resp 版本标识"""
        html = self._get_index_html()
        self.assertIn("-resp", html)

    # ==================== JS 函数导出测试 ====================

    def test_emails_js_contains_detail_focus_functions(self):
        """emails.js 应包含 setMailboxDetailFocus 和 setTempDetailFocus"""
        from pathlib import Path

        emails_js = Path("static/js/features/emails.js").read_text(encoding="utf-8")
        self.assertIn("function setMailboxDetailFocus", emails_js)
        self.assertIn("function setTempDetailFocus", emails_js)
        self.assertIn("function isNarrowWorkspaceViewport", emails_js)

    def test_main_js_contains_toggle_groups_column(self):
        """main.js 应包含 toggleGroupsColumn 和 handleResponsiveGroups"""
        from pathlib import Path

        main_js = Path("static/js/main.js").read_text(encoding="utf-8")
        self.assertIn("function toggleGroupsColumn", main_js)
        self.assertIn("function handleResponsiveGroups", main_js)

    # ==================== CSS 断点规则测试 ====================

    def test_css_tablet_has_detail_focus_rules(self):
        """平板断点 (769-1024px) 应包含 detail-focus 和 groups 折叠规则"""
        from pathlib import Path

        css = Path("static/css/main.css").read_text(encoding="utf-8")
        tablet_section = re.search(
            r"@media\s*\(max-width:\s*1024px\)\s+and\s+\(min-width:\s*769px\).*?(?=@media)",
            css,
            re.DOTALL,
        )
        self.assertIsNotNone(tablet_section, "应找到平板断点 @media 块")
        tablet = tablet_section.group(0)
        self.assertIn("detail-focus", tablet)
        self.assertIn("groups-column", tablet)
        self.assertIn("groups-expanded", tablet)
        self.assertIn("btn-toggle-groups", tablet)

    def test_css_mobile_has_detail_focus_rules(self):
        """移动端断点 (<=768px) 应包含 detail-focus 规则"""
        from pathlib import Path

        css = Path("static/css/main.css").read_text(encoding="utf-8")
        mobile_section = re.search(
            r"@media\s*\([^)]*max-width:\s*768px[^)]*\).*",
            css,
            re.DOTALL,
        )
        self.assertIsNotNone(mobile_section, "应找到移动端断点 @media 块")
        mobile = mobile_section.group(0)
        self.assertIn("detail-focus", mobile)
        self.assertIn("tempEmailDetailSection", mobile)

    def test_css_desktop_hides_toggle_groups_button(self):
        """桌面端全局样式应隐藏 btn-toggle-groups"""
        from pathlib import Path

        css = Path("static/css/main.css").read_text(encoding="utf-8")
        self.assertIn(".btn-toggle-groups { display: none; }", css)

    # ==================== i18n 翻译词条测试 ====================

    def test_i18n_contains_groups_toggle_translations(self):
        """i18n.js 应包含「展开分组」和「收起分组」翻译"""
        from pathlib import Path

        i18n = Path("static/js/i18n.js").read_text(encoding="utf-8")
        self.assertIn("'展开分组': 'Expand Groups'", i18n)
        self.assertIn("'收起分组': 'Collapse Groups'", i18n)

    # ==================== 交互逻辑契约测试 ====================

    def test_accounts_js_resets_detail_focus_on_switch(self):
        """accounts.js 切换账户时应重置 detail-focus 状态"""
        from pathlib import Path

        accounts_js = Path("static/js/features/accounts.js").read_text(encoding="utf-8")
        self.assertIn("setMailboxDetailFocus(false)", accounts_js)

    def test_temp_emails_js_handles_focus_toggle(self):
        """temp_emails.js 应在刷新时退出 detail-focus、在查看时进入"""
        from pathlib import Path

        temp_js = Path("static/js/features/temp_emails.js").read_text(encoding="utf-8")
        self.assertIn("setTempDetailFocus(false)", temp_js)
        self.assertIn("setTempDetailFocus(true)", temp_js)

    def test_emails_js_show_email_list_resets_focus(self):
        """emails.js showEmailList 应重置 mailbox 和 temp 两种 focus"""
        from pathlib import Path

        emails_js = Path("static/js/features/emails.js").read_text(encoding="utf-8")
        show_list_section = re.search(
            r"function showEmailList\(\).*?(?=function\s)",
            emails_js,
            re.DOTALL,
        )
        self.assertIsNotNone(show_list_section)
        self.assertIn("setMailboxDetailFocus(false)", show_list_section.group(0))
        self.assertIn("setTempDetailFocus(false)", show_list_section.group(0))


if __name__ == "__main__":
    unittest.main()
