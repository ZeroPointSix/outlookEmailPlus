"""tests/test_settings_tab_refactor_frontend.py — B 类：前端契约测试

目标：验证设置页面 UI 重构（Tab 化 + 临时邮箱配置区分离）的前端代码已正确存在：
  - index.html: 4 个 Tab 按钮、4 个 Tab 面板、Provider radio button（非 select）
  - index.html: GPTMail 配置面板字段、CF Worker 配置面板字段、只读属性
  - main.js:  switchSettingsTab / onTempMailProviderChange / autoSaveSettings 函数
  - main.css: .settings-tab-nav / .settings-tab / .settings-tab-pane / .provider-radio-group / .readonly-field 样式

关联文档：
  - TDD: docs/TDD/2026-04-04-设置页面UI重构-TDD.md
  - FD:  docs/FD/2026-04-04-设置页面UI重构-FD.md
"""

from __future__ import annotations

import unittest

from tests._import_app import import_web_app_module


class SettingsTabRefactorFrontendTests(unittest.TestCase):
    """B 类：前端契约测试 — 设置页面 Tab 重构"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    def _get_text(self, client, path: str = "/") -> str:
        resp = client.get(path)
        try:
            return resp.data.decode("utf-8")
        finally:
            resp.close()

    # ──────────────────────────────────────────────────────
    # TC-B01：index.html 包含 4 个 Tab 按钮
    # ──────────────────────────────────────────────────────

    def test_index_html_contains_four_settings_tabs(self):
        """index.html 应包含 4 个 settings-tab 按钮及导航栏"""
        client = self.app.test_client()
        self._login(client)
        html = self._get_text(client)

        # Tab 导航栏容器
        self.assertIn(
            'class="settings-tab-nav"', html, "应包含 .settings-tab-nav 导航栏"
        )

        # 4 个 Tab 的 data-tab 属性
        self.assertIn('data-tab="basic"', html, "应包含基础 Tab 按钮")
        self.assertIn('data-tab="temp-mail"', html, "应包含临时邮箱 Tab 按钮")
        self.assertIn('data-tab="api-security"', html, "应包含 API 安全 Tab 按钮")
        self.assertIn('data-tab="automation"', html, "应包含自动化 Tab 按钮")

    # ──────────────────────────────────────────────────────
    # TC-B02：index.html 包含 4 个 Tab 面板
    # ──────────────────────────────────────────────────────

    def test_index_html_contains_four_tab_panes(self):
        """index.html 应包含 4 个 settings-tab-pane 内容面板"""
        client = self.app.test_client()
        self._login(client)
        html = self._get_text(client)

        self.assertIn('id="settings-tab-basic"', html, "应包含基础 Tab 面板")
        self.assertIn('id="settings-tab-temp-mail"', html, "应包含临时邮箱 Tab 面板")
        self.assertIn(
            'id="settings-tab-api-security"', html, "应包含 API 安全 Tab 面板"
        )
        self.assertIn('id="settings-tab-automation"', html, "应包含自动化 Tab 面板")

    # ──────────────────────────────────────────────────────
    # TC-B03：index.html 包含 Provider 单选按钮组（非下拉框）
    # ──────────────────────────────────────────────────────

    def test_index_html_contains_provider_radio_buttons(self):
        """index.html 应包含 Provider 单选按钮，且不再有旧的 <select> 元素"""
        client = self.app.test_client()
        self._login(client)
        html = self._get_text(client)

        # 存在 radio 类型的 Provider 选择
        self.assertIn(
            'name="tempMailProvider"', html, "应包含 tempMailProvider 单选按钮组"
        )
        self.assertIn('value="legacy_bridge"', html, "应包含 legacy_bridge 选项")
        self.assertIn(
            'value="cloudflare_temp_mail"', html, "应包含 cloudflare_temp_mail 选项"
        )

        # 不应再有旧的 Provider 下拉框
        self.assertNotIn(
            '<select id="settingsTempMailProvider"',
            html,
            "不应保留旧的 Provider <select> 元素",
        )

    # ──────────────────────────────────────────────────────
    # TC-B04：index.html 包含 GPTMail 配置面板及其字段
    # ──────────────────────────────────────────────────────

    def test_index_html_contains_gptmail_config_panel(self):
        """index.html 应包含 GPTMail 配置面板及所有必要字段"""
        client = self.app.test_client()
        self._login(client)
        html = self._get_text(client)

        self.assertIn(
            'id="gptmailConfigPanel"',
            html,
            "应包含 GPTMail 配置面板 #gptmailConfigPanel",
        )
        self.assertIn(
            'id="settingsTempMailApiBaseUrl"', html, "应包含 GPTMail API Base URL 字段"
        )
        self.assertIn(
            'id="settingsTempMailApiKey"', html, "应包含 GPTMail API Key 字段"
        )
        self.assertIn(
            'id="settingsTempMailDomains"', html, "应包含 GPTMail 可用域名字段"
        )
        self.assertIn(
            'id="settingsTempMailDefaultDomain"', html, "应包含 GPTMail 默认域名字段"
        )
        self.assertIn(
            'id="settingsTempMailPrefixRules"', html, "应包含 GPTMail 前缀规则字段"
        )

    # ──────────────────────────────────────────────────────
    # TC-B05：index.html 包含 CF Worker 配置面板及只读字段
    # ──────────────────────────────────────────────────────

    def test_index_html_contains_cf_worker_config_panel(self):
        """index.html 应包含 CF Worker 配置面板及只读域名字段"""
        client = self.app.test_client()
        self._login(client)
        html = self._get_text(client)

        self.assertIn(
            'id="cfWorkerConfigPanel"',
            html,
            "应包含 CF Worker 配置面板 #cfWorkerConfigPanel",
        )
        self.assertIn(
            'id="settingsCfWorkerBaseUrl"', html, "应包含 CF Worker 部署地址字段"
        )
        self.assertIn(
            'id="settingsCfWorkerAdminKey"', html, "应包含 CF Worker Admin 密码字段"
        )
        self.assertIn(
            'id="settingsCfWorkerDomains"',
            html,
            "应包含 CF Worker 已同步域名字段（只读）",
        )
        self.assertIn(
            'id="settingsCfWorkerDefaultDomain"',
            html,
            "应包含 CF Worker 默认域名字段（只读）",
        )
        self.assertIn(
            'id="settingsCfWorkerPrefixRules"',
            html,
            "应包含 CF Worker 前缀规则字段（可编辑）",
        )
        self.assertIn('id="cfWorkerSyncTime"', html, "应包含上次同步时间显示区域")

    # ──────────────────────────────────────────────────────
    # TC-B06：index.html 中 CF Worker 只读字段有 readonly 属性
    # ──────────────────────────────────────────────────────

    def test_cf_worker_domain_fields_have_readonly_attribute(self):
        """CF Worker 域名字段应有 readonly HTML 属性"""
        client = self.app.test_client()
        self._login(client)
        html = self._get_text(client)

        # 检查 settingsCfWorkerDomains 元素有 readonly 属性
        idx_domains = html.find('id="settingsCfWorkerDomains"')
        self.assertNotEqual(idx_domains, -1, "settingsCfWorkerDomains 元素应存在")
        # 查找该元素标签内（向前找起始 < 处）的 readonly 属性
        tag_start = html.rfind("<", 0, idx_domains)
        tag_end = html.find(">", idx_domains)
        if tag_start != -1 and tag_end != -1:
            tag_html = html[tag_start : tag_end + 1]
            self.assertIn(
                "readonly", tag_html, "settingsCfWorkerDomains 元素应有 readonly 属性"
            )

        # 检查 settingsCfWorkerDefaultDomain 元素有 readonly 属性
        idx_domain = html.find('id="settingsCfWorkerDefaultDomain"')
        self.assertNotEqual(idx_domain, -1, "settingsCfWorkerDefaultDomain 元素应存在")
        tag_start2 = html.rfind("<", 0, idx_domain)
        tag_end2 = html.find(">", idx_domain)
        if tag_start2 != -1 and tag_end2 != -1:
            tag_html2 = html[tag_start2 : tag_end2 + 1]
            self.assertIn(
                "readonly",
                tag_html2,
                "settingsCfWorkerDefaultDomain 元素应有 readonly 属性",
            )

    # ──────────────────────────────────────────────────────
    # TC-B07：main.js 包含 switchSettingsTab 函数
    # ──────────────────────────────────────────────────────

    def test_main_js_contains_switch_settings_tab_function(self):
        """main.js 应包含 switchSettingsTab 函数定义"""
        client = self.app.test_client()
        resp = client.get("/static/js/main.js")
        js_text = resp.data.decode("utf-8")

        self.assertIn(
            "function switchSettingsTab",
            js_text,
            "main.js 应包含 switchSettingsTab 函数",
        )

    # ──────────────────────────────────────────────────────
    # TC-B08：main.js 包含 onTempMailProviderChange 函数
    # ──────────────────────────────────────────────────────

    def test_main_js_contains_on_temp_mail_provider_change(self):
        """main.js 应包含 onTempMailProviderChange 函数定义"""
        client = self.app.test_client()
        resp = client.get("/static/js/main.js")
        js_text = resp.data.decode("utf-8")

        self.assertIn(
            "function onTempMailProviderChange",
            js_text,
            "main.js 应包含 onTempMailProviderChange 函数",
        )

    # ──────────────────────────────────────────────────────
    # TC-B09：main.js 包含 autoSaveSettings 函数
    # ──────────────────────────────────────────────────────

    def test_main_js_contains_auto_save_settings_function(self):
        """main.js 应包含 autoSaveSettings 函数定义"""
        client = self.app.test_client()
        resp = client.get("/static/js/main.js")
        js_text = resp.data.decode("utf-8")

        self.assertIn(
            "function autoSaveSettings", js_text, "main.js 应包含 autoSaveSettings 函数"
        )

    # ──────────────────────────────────────────────────────
    # TC-B10：main.css 包含 Tab 相关样式类
    # ──────────────────────────────────────────────────────

    def test_main_css_contains_tab_styles(self):
        """main.css 应包含 .settings-tab-nav / .settings-tab / .settings-tab-pane 样式"""
        client = self.app.test_client()
        resp = client.get("/static/css/main.css")
        css_text = resp.data.decode("utf-8")

        self.assertIn(
            ".settings-tab-nav", css_text, "main.css 应包含 .settings-tab-nav 样式"
        )
        self.assertIn(".settings-tab", css_text, "main.css 应包含 .settings-tab 样式")
        self.assertIn(
            ".settings-tab-pane", css_text, "main.css 应包含 .settings-tab-pane 样式"
        )

    # ──────────────────────────────────────────────────────
    # TC-B11：main.css 包含 Provider 单选按钮样式
    # ──────────────────────────────────────────────────────

    def test_main_css_contains_provider_radio_styles(self):
        """main.css 应包含 .provider-radio-group 和 .provider-radio 样式"""
        client = self.app.test_client()
        resp = client.get("/static/css/main.css")
        css_text = resp.data.decode("utf-8")

        self.assertIn(
            ".provider-radio-group",
            css_text,
            "main.css 应包含 .provider-radio-group 样式",
        )
        self.assertIn(
            ".provider-radio", css_text, "main.css 应包含 .provider-radio 样式"
        )

    # ──────────────────────────────────────────────────────
    # TC-B12：main.css 包含只读字段样式
    # ──────────────────────────────────────────────────────

    def test_main_css_contains_readonly_field_styles(self):
        """main.css 应包含 .readonly-field 样式"""
        client = self.app.test_client()
        resp = client.get("/static/css/main.css")
        css_text = resp.data.decode("utf-8")

        self.assertIn(
            ".readonly-field", css_text, "main.css 应包含 .readonly-field 样式"
        )


if __name__ == "__main__":
    unittest.main()
