"""tests/test_batch_fetch_frontend_contract.py — A/D 类：前端契约与回归测试

目标：
  - 验证标准模式“批量拉取邮件”入口与函数骨架
  - 验证紧凑模式批量栏不被顺带扩展
  - 验证现有批量动作与单账号邮件语义保持不变

注意（RED 阶段）：
  Issue #55 功能尚未实现时，新增断言预期失败。
"""

from __future__ import annotations

import re
import unittest

from tests._import_app import clear_login_attempts, import_web_app_module


class BatchFetchFrontendContractTests(unittest.TestCase):
    """A/D 类：标准模式批量拉取邮件的前端契约与回归。"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()

    def _login(self, client):
        resp = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    def _get_text(self, client, path: str) -> str:
        resp = client.get(path)
        try:
            return resp.data.decode("utf-8")
        finally:
            resp.close()

    def _get_index_html(self) -> str:
        client = self.app.test_client()
        self._login(client)
        return self._get_text(client, "/")

    def _get_main_js(self) -> str:
        client = self.app.test_client()
        return self._get_text(client, "/static/js/main.js")

    def test_index_html_contains_batch_fetch_button_in_standard_batch_bar(self):
        """PRD 5.1 / TDD A-01,A-08：标准模式批量栏应包含 ghost 样式的批量拉取按钮。"""
        html = self._get_index_html()

        standard_start = html.index('id="batchActionBar"')
        compact_start = html.index('id="compactBatchActionBar"')
        standard_section = html[standard_start:compact_start]

        self.assertRegex(
            standard_section,
            re.compile(
                r'<button class="btn btn-sm btn-ghost" onclick="showBatchFetchConfirm\(\)">\s*批量拉取邮件\s*</button>'
            ),
        )

    def test_compact_batch_action_bar_does_not_contain_batch_fetch_button(self):
        """PRD 3.2 / TDD A-07：紧凑模式批量栏不应出现批量拉取按钮。"""
        html = self._get_index_html()

        compact_start = html.index('id="compactBatchActionBar"')
        temp_mail_start = html.index("<!-- ===== Page: Temp Emails ===== -->")
        compact_section = html[compact_start:temp_mail_start]

        self.assertNotIn("批量拉取邮件", compact_section)
        self.assertNotIn("showBatchFetchConfirm()", compact_section)

    def test_main_js_contains_batch_fetch_entry_functions(self):
        """TDD A-02,A-03,A-04：main.js 应声明批量拉取的入口与核心函数骨架。"""
        js = self._get_main_js()

        self.assertIn("function showBatchFetchConfirm()", js)
        self.assertIn("function resolveSelectedAccountsForBatchFetch()", js)
        self.assertIn("async function batchFetchSelectedEmails(", js)
        self.assertIn("async function fetchLatestFoldersForAccount(", js)
        self.assertIn("function cacheBatchFetchedFolder(", js)
        self.assertIn("function refreshCurrentMailboxIfNeeded(", js)
        self.assertIn("syncAccountSummaryToAccountCache", js)

    def test_main_js_does_not_introduce_new_batch_fetch_backend_api(self):
        """TDD A-06：V1 不应引入新的 selected batch fetch 后端接口。"""
        js = self._get_main_js()

        self.assertNotIn("/api/accounts/fetch-selected", js)
        self.assertNotIn("/api/accounts/selected/fetch", js)
        self.assertNotIn("/api/emails/selected", js)

    def test_i18n_contains_batch_fetch_labels(self):
        """TDD A-05：批量拉取入口与进度提示文案应加入 i18n。"""
        client = self.app.test_client()
        i18n_js = self._get_text(client, "/static/js/i18n.js")

        self.assertIn("'批量拉取邮件':", i18n_js)
        self.assertIn("请选择要批量拉取邮件的账号", i18n_js)
        self.assertIn("正在批量拉取邮件", i18n_js)
        self.assertIn("批量拉取完成", i18n_js)
        self.assertIn("收件箱 + 垃圾箱", i18n_js)

    def test_existing_batch_refresh_entry_still_present(self):
        """TDD D-01：现有批量刷新 Token 入口保持不变。"""
        html = self._get_index_html()
        js = self._get_main_js()

        self.assertIn("showBatchRefreshConfirm()", html)
        self.assertIn("function showBatchRefreshConfirm()", js)
        self.assertIn("async function batchRefreshSelected(accountIds)", js)

    def test_existing_batch_delete_entry_still_present(self):
        """TDD D-02：现有批量删除入口保持不变。"""
        html = self._get_index_html()
        js = self._get_main_js()

        self.assertIn("showBatchDeleteConfirm()", html)
        self.assertIn("function showBatchDeleteConfirm()", js)
        self.assertIn("async function batchDeleteAccounts()", js)

    def test_load_emails_still_uses_single_account_model(self):
        """TDD D-03：单账号邮件区仍按 currentAccount/currentFolder 语义工作。"""
        client = self.app.test_client()
        emails_js = self._get_text(client, "/static/js/features/emails.js")

        self.assertIn("async function loadEmails(email, forceRefresh = false)", emails_js)
        self.assertIn("const cacheKey = `${email}_${currentFolder}`;", emails_js)
        self.assertIn(
            "`/api/emails/${encodeURIComponent(email)}?method=${currentMethod}&folder=${currentFolder}&skip=0&top=20`",
            emails_js,
        )

    def test_selected_account_ids_semantics_unchanged(self):
        """TDD D-04：selectedAccountIds 仍是跨分组的批量选择主状态。"""
        js = self._get_main_js()

        self.assertIn("let selectedAccountIds = new Set();", js)
        self.assertIn("selectedAccountIds.add(accountId);", js)
        self.assertIn("selectedAccountIds.delete(accountId);", js)
        self.assertIn("countSpan.textContent = formatSelectedItemsLabel(selectedAccountIds.size);", js)


if __name__ == "__main__":
    unittest.main()
