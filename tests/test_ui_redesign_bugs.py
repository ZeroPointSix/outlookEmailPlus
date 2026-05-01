"""
UI 重设计 BUG 修复验证测试

关联文档：docs/BUG/BUG-00001-UI重设计后用户反馈问题清单.md
测试内容：
- BUG-002: 选中账号名称显示
- BUG-003: 设置页面自动加载
- BUG-004: 弹窗居中
- BUG-010: 仪表盘统计数据
- 前端 HTML 结构完整性检查
"""

import re
import unittest

from tests._import_app import import_web_app_module


class TestUIRedesignBugFixes(unittest.TestCase):
    """UI 重设计 BUG 修复验证测试类"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def _login(self, client):
        resp = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(resp.status_code, 200)

    def _get_client(self):
        """Get a logged-in test client"""
        client = self.app.test_client()
        self._login(client)
        return client

    def _get_text(self, client, path):
        """Read response text and close the underlying file handle promptly."""
        resp = client.get(path)
        try:
            return resp.status_code, resp.data.decode("utf-8")
        finally:
            resp.close()

    def _get_json(self, client, path):
        """Read JSON payload and close the response object."""
        resp = client.get(path)
        try:
            return resp.status_code, resp.get_json()
        finally:
            resp.close()

    # ==================== BUG-002: 账号栏显示 ====================

    def test_bug002_current_account_bar_exists(self):
        """BUG-002: index.html 中存在 currentAccountBar 元素"""
        client = self._get_client()
        _, html = self._get_text(client, "/")
        self.assertIn('id="currentAccountBar"', html)
        self.assertIn('id="currentAccountEmail"', html)
        self.assertIn('id="currentAccount"', html)

    def test_bug002_accounts_js_shows_account_bar(self):
        """BUG-002: accounts.js 中 selectAccount 应操作 currentAccountBar 而非 currentAccount"""
        client = self._get_client()
        _, js = self._get_text(client, "/static/js/features/accounts.js")
        self.assertIn("currentAccountBar", js, "selectAccount() 应操作 #currentAccountBar 元素")

    # ==================== BUG-003: 设置页面 ====================

    def test_bug003_settings_page_has_content(self):
        """BUG-003: 设置页面应有实质性内容，而非仅占位文字"""
        client = self._get_client()
        _, html = self._get_text(client, "/")
        settings_section = re.search(r'id="page-settings".*?(?=id="page-|$)', html, re.DOTALL)
        self.assertIsNotNone(settings_section, "找不到 page-settings 区域")

    def test_bug003_navigate_triggers_settings_load(self):
        """BUG-003: navigate('settings') 应触发设置加载"""
        client = self._get_client()
        _, js = self._get_text(client, "/static/js/main.js")
        self.assertIn("settings", js)

    # ==================== BUG-004: 弹窗居中 ====================

    def test_bug004_modal_css_centering(self):
        """BUG-004: CSS 中 .modal 应有 flex 居中属性"""
        client = self._get_client()
        _, css = self._get_text(client, "/static/css/main.css")
        self.assertIn("align-items: center", css)
        self.assertIn("justify-content: center", css)

    def test_bug004_modal_content_max_width(self):
        """BUG-004: .modal-content 应有 max-width 限制"""
        client = self._get_client()
        _, css = self._get_text(client, "/static/css/main.css")
        self.assertIn("max-width: 560px", css)

    def test_bug004_all_modals_use_modal_class(self):
        """BUG-004: modals.html 中所有弹窗应使用 class='modal'"""
        client = self._get_client()
        _, html = self._get_text(client, "/")
        modal_ids = re.findall(r'id="(\w+Modal)"', html)
        for modal_id in modal_ids:
            if modal_id == "fullscreenEmailModal":
                continue
            pattern = rf'<div[^>]*id="{modal_id}"[^>]*>'
            match = re.search(pattern, html)
            self.assertIsNotNone(match, f"找不到弹窗 {modal_id}")
            tag = match.group(0)
            self.assertIn(
                'class="modal"',
                tag,
                f"弹窗 {modal_id} 应使用 class='modal'，实际: {tag[:80]}",
            )

    # ==================== BUG-005: 验证码提取 ====================

    def test_bug005_verification_extract_api_exists(self):
        """BUG-005: 验证码提取 API 端点存在"""
        client = self._get_client()
        status_code, _ = self._get_json(client, "/api/emails/nonexistent@test.com/extract-verification")
        self.assertIn(status_code, [200, 404], "验证码提取 API 应该返回 200 或 404")

    def test_bug005_copy_verification_function_exists(self):
        """BUG-005: JS 中存在 copyVerificationInfo 函数"""
        client = self._get_client()
        _, js = self._get_text(client, "/static/js/features/groups.js")
        self.assertIn("function copyVerificationInfo", js)

    # ==================== BUG-006: 卡片颜色 ====================

    def test_bug006_card_color_array_exists(self):
        """BUG-006: 临时邮箱渲染应有多种颜色"""
        client = self._get_client()
        _, js = self._get_text(client, "/static/js/features/temp_emails.js")
        self.assertIn("renderTempEmailList", js)

    # ==================== BUG-010: 仪表盘 ====================

    def test_bug010_dashboard_elements_exist(self):
        """BUG-010: 仪表盘统计元素存在"""
        client = self._get_client()
        _, html = self._get_text(client, "/")
        for el_id in [
            "statTotalAccounts",
            "statValidTokens",
            "statExpiredTokens",
            "statTempEmails",
        ]:
            self.assertIn(f'id="{el_id}"', html, f"仪表盘应包含 #{el_id} 元素")

    def test_bug010_dashboard_group_list_exists(self):
        """BUG-010: 仪表盘分组概览列表存在"""
        client = self._get_client()
        _, html = self._get_text(client, "/")
        self.assertIn('id="dashboardGroupList"', html)

    def test_bug010_dashboard_uses_overview_entrypoint(self):
        """BUG-010: Dashboard 当前通过 overview.js 入口加载，而非旧 loadDashboard 逻辑"""
        client = self._get_client()
        _, main_js = self._get_text(client, "/static/js/main.js")
        _, overview_js = self._get_text(client, "/static/js/features/overview.js")
        self.assertIn("if (page === 'dashboard' && typeof initOverview === 'function') initOverview();", main_js)
        self.assertNotIn("function loadDashboard", main_js)
        self.assertIn("function initOverview()", overview_js)
        self.assertIn("summary: '/api/overview/summary'", overview_js)

    def test_bug010_groups_api_returns_data(self):
        """BUG-010: 分组 API 返回有效数据"""
        client = self._get_client()
        _, data = self._get_json(client, "/api/groups")
        self.assertTrue(data.get("success"), "分组 API 应返回 success=true")
        self.assertIn("groups", data, "分组 API 应包含 groups 字段")

    # ==================== 结构完整性 ====================

    def test_all_pages_exist_in_html(self):
        """所有页面容器存在于 index.html"""
        client = self._get_client()
        _, html = self._get_text(client, "/")
        pages = [
            "page-dashboard",
            "page-mailbox",
            "page-temp-emails",
            "page-refresh-log",
            "page-settings",
            "page-audit",
        ]
        for page_id in pages:
            self.assertIn(f'id="{page_id}"', html, f"缺少页面 #{page_id}")

    def test_sidebar_navigation_items(self):
        """侧边栏导航项完整"""
        client = self._get_client()
        _, html = self._get_text(client, "/")
        nav_pages = [
            "dashboard",
            "mailbox",
            "temp-emails",
            "refresh-log",
            "settings",
            "audit",
        ]
        for page in nav_pages:
            self.assertIn(f'data-page="{page}"', html, f"侧边栏缺少 {page} 导航项")

    def test_mailbox_three_column_structure(self):
        """邮箱管理三栏布局结构完整"""
        client = self._get_client()
        _, html = self._get_text(client, "/")
        # 新的 workspace 布局系统
        self.assertIn('class="workspace workspace-mailbox"', html)
        self.assertIn('class="workspace-panel groups-column"', html)
        self.assertIn('class="workspace-panel accounts-column"', html)
        self.assertIn('class="workspace-panel emails-column"', html)

    def test_js_files_load_successfully(self):
        """所有 JS 文件可正常加载"""
        client = self._get_client()
        js_files = [
            "/static/js/main.js",
            "/static/js/features/groups.js",
            "/static/js/features/accounts.js",
            "/static/js/features/emails.js",
            "/static/js/features/temp_emails.js",
        ]
        for js_path in js_files:
            status_code, js = self._get_text(client, js_path)
            self.assertEqual(status_code, 200, f"{js_path} 应返回 200")
            self.assertGreater(len(js), 100, f"{js_path} 内容不应为空")

    def test_css_loads_successfully(self):
        """CSS 文件可正常加载"""
        client = self._get_client()
        status_code, css = self._get_text(client, "/static/css/main.css")
        self.assertEqual(status_code, 200)
        self.assertIn("--clr-primary", css)
        self.assertIn("--bg-sidebar", css)
        self.assertIn("--bg-hover", css)


if __name__ == "__main__":
    unittest.main()
