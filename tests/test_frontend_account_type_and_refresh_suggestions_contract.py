from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

from tests._import_app import import_web_app_module


class FrontendAccountTypeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def _login(self, client):
        resp = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(resp.status_code, 200)

    def _get_text(self, client, path: str) -> str:
        resp = client.get(path)
        try:
            return resp.data.decode("utf-8")
        finally:
            resp.close()

    def test_dashboard_refresh_health_uses_overview_summary_feed(self):
        client = self.app.test_client()
        overview_js = self._get_text(client, "/static/js/features/overview.js")
        main_js = self._get_text(client, "/static/js/main.js")

        self.assertIn("function initOverview()", overview_js)
        self.assertIn("summary: '/api/overview/summary',", overview_js)
        self.assertIn("const refresh = data.refresh_health || {};", overview_js)
        self.assertIn("const accountStatus = data.account_status || {};", overview_js)
        self.assertIn("最近刷新成功率", overview_js)
        self.assertNotIn("function loadDashboard()", main_js)

    def test_group_cards_split_outlook_and_imap_status_rendering(self):
        client = self.app.test_client()
        groups_js = self._get_text(client, "/static/js/features/groups.js")

        self.assertIn("const supportsTokenRefresh = isRefreshableOutlookAccount(acc);", groups_js)
        self.assertIn(
            "const isFailed = supportsTokenRefresh && acc.last_refresh_status === 'failed';",
            groups_js,
        )
        self.assertIn(
            "const defaultMethodLabel = supportsTokenRefresh ? 'Graph' : 'IMAP';",
            groups_js,
        )
        self.assertIn('let tokenBadge = `<span class="badge badge-gray">IMAP</span>`;', groups_js)
        self.assertIn("if (supportsTokenRefresh) {", groups_js)
        self.assertIn(
            '<span class="account-api-tag">${acc.method || defaultMethodLabel}</span>',
            groups_js,
        )

    def test_group_refresh_error_button_passes_account_type_and_provider(self):
        client = self.app.test_client()
        groups_js = self._get_text(client, "/static/js/features/groups.js")

        self.assertIn("showRefreshError(${acc.id}", groups_js)
        self.assertIn("${escapeJs(acc.account_type || 'outlook')}", groups_js)
        self.assertIn("${escapeJs(acc.provider || 'outlook')}", groups_js)

    def test_refresh_error_modal_uses_dynamic_suggestions_container(self):
        client = self.app.test_client()
        self._login(client)
        main_js = self._get_text(client, "/static/js/main.js")
        index_html = self._get_text(client, "/")

        self.assertIn(
            "const suggestionsEl = document.getElementById('refreshErrorSuggestions');",
            main_js,
        )
        self.assertIn(
            "const suggestions = buildRefreshErrorSuggestions({ accountType, provider, errorMessage });",
            main_js,
        )
        self.assertIn(
            "suggestionsEl.innerHTML = suggestions.map(item => `<li>${escapeHtml(item)}</li>`).join('');",
            main_js,
        )
        self.assertIn('id="refreshErrorSuggestions"', index_html)

    def test_refresh_all_sse_error_branch_handles_refresh_conflict(self):
        client = self.app.test_client()
        main_js = self._get_text(client, "/static/js/main.js")

        self.assertIn("} else if (data.type === 'error') {", main_js)
        self.assertIn("const errCode = data.error && data.error.code;", main_js)
        self.assertIn("if (errCode === 'REFRESH_CONFLICT') {", main_js)
        self.assertIn("showToast(userMessage, 'warning', data.error || null, true);", main_js)

    def test_retry_failed_conflict_branch_uses_warning_with_actionable_message(self):
        client = self.app.test_client()
        main_js = self._get_text(client, "/static/js/main.js")

        self.assertIn("if (errCode === 'REFRESH_CONFLICT') {", main_js)
        self.assertIn("Wait for it to finish and retry.", main_js)
        self.assertIn("showToast(msg, 'warning', data.error || null, true);", main_js)

    def test_refresh_all_no_mail_permission_uses_actionable_summary(self):
        client = self.app.test_client()
        main_js = self._get_text(client, "/static/js/main.js")

        self.assertIn("function buildRefreshAllPermissionErrorSummary(errorPayload)", main_js)
        self.assertIn("if (errCode === 'NO_MAIL_PERMISSION') {", main_js)
        self.assertIn("[Code] NO_MAIL_PERMISSION", main_js)
        self.assertIn("Mail.Read 或 Mail.ReadWrite", main_js)
        self.assertIn(
            "showToast(buildRefreshAllPermissionErrorSummary(data.error || {}), 'error', data.error || null, true);",
            main_js,
        )

    def test_remark_entry_copy_is_updated_in_i18n_template_and_compact_menu(self):
        client = self.app.test_client()
        self._login(client)
        i18n_js = self._get_text(client, "/static/js/i18n.js")
        index_html = self._get_text(client, "/")
        compact_js = self._get_text(client, "/static/js/features/mailbox_compact.js")
        groups_js = self._get_text(client, "/static/js/features/groups.js")

        self.assertIn("'编辑备注': 'Edit Remark'", i18n_js)
        self.assertIn("'单独编辑备注': 'Edit Remark Only'", i18n_js)
        self.assertIn("'保存备注': 'Save Remark'", i18n_js)
        self.assertIn("单独编辑备注", index_html)
        self.assertIn("保存备注", index_html)
        self.assertIn("备注支持单独保存，不会连带修改账号凭据等其他字段。", index_html)
        self.assertIn("这里会调用轻量 PATCH 接口，只更新备注本身。", index_html)
        self.assertIn("translateCompactText('编辑备注')", compact_js)
        self.assertNotIn("translateCompactText('编辑便签')", compact_js)
        self.assertIn("translateAppTextLocal('备注')", groups_js)


class RefreshErrorSuggestionsBehaviorNodeTests(unittest.TestCase):
    def test_build_refresh_error_suggestions_branches_by_account_type_provider_and_error(
        self,
    ):
        if shutil.which("node") is None:
            self.skipTest("node is not installed")

        repo_root = Path(__file__).resolve().parents[1]
        main_js_path = repo_root / "static" / "js" / "main.js"
        self.assertTrue(main_js_path.exists(), f"missing {main_js_path}")

        node_script = r"""
const fs = require('fs');
const vm = require('vm');

const filePath = process.argv[2] || process.argv[1];
if (!filePath) {
  throw new Error('missing main.js path');
}

const code = fs.readFileSync(filePath, 'utf8');

const noop = () => {};
function createClassList() {
  return {
    values: new Set(),
    add(value) { this.values.add(value); },
    remove(value) { this.values.delete(value); },
    contains(value) { return this.values.has(value); },
  };
}
const elements = new Map([
  ['refreshErrorModal', { classList: createClassList() }],
  ['refreshErrorEmail', { textContent: '' }],
  ['refreshErrorMessage', { textContent: '' }],
  ['refreshErrorSuggestions', { innerHTML: '' }],
  ['editAccountFromErrorBtn', { onclick: null }],
]);
const localStorage = {
  store: {},
  getItem(key) { return Object.prototype.hasOwnProperty.call(this.store, key) ? this.store[key] : null; },
  setItem(key, value) { this.store[key] = String(value); },
};

const context = {
  console,
  localStorage,
  setTimeout,
  clearTimeout,
  requestAnimationFrame: (fn) => { fn(); return 1; },
  cancelAnimationFrame: noop,
  window: {
    getCurrentUiLanguage: () => 'en',
    fetch: async () => ({ status: 200, clone: () => ({ json: async () => ({}) }) }),
    addEventListener: noop,
    translateAppText: (text) => text,
  },
  document: {
    getElementById(id) { return elements.get(id) || null; },
    querySelectorAll() { return []; },
    querySelector() { return null; },
    createElement() {
      return {
        _textContent: '',
        set textContent(value) { this._textContent = String(value); },
        get textContent() { return this._textContent; },
        get innerHTML() {
          return this._textContent
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
        },
      };
    },
    addEventListener: noop,
  },
  showEditAccountModal(accountId) {
    context.lastEditedAccountId = accountId;
  },
  lastEditedAccountId: null,
};

vm.createContext(context);
vm.runInContext(code, context, { filename: filePath });

if (typeof context.buildRefreshErrorSuggestions !== 'function') {
  throw new Error('buildRefreshErrorSuggestions is not defined');
}
if (typeof context.showRefreshError !== 'function') {
  throw new Error('showRefreshError is not defined');
}

context.window.getCurrentUiLanguage = () => 'en';
const gmailWithRefreshError = context.buildRefreshErrorSuggestions({
  accountType: 'imap',
  provider: 'gmail',
  errorMessage: 'refresh_token invalid AADSTS900144'
});
if (!Array.isArray(gmailWithRefreshError) || gmailWithRefreshError.length < 3) {
  throw new Error('gmailWithRefreshError should return >=3 suggestions');
}
if (!gmailWithRefreshError.some(item => String(item).includes('old Outlook token-refresh error'))) {
  throw new Error('gmailWithRefreshError should mention old Outlook token-refresh error');
}
if (!gmailWithRefreshError.some(item => String(item).toLowerCase().includes('app password'))) {
  throw new Error('gmailWithRefreshError should mention app password');
}

context.window.getCurrentUiLanguage = () => 'zh';
const genericImapZh = context.buildRefreshErrorSuggestions({
  accountType: 'imap',
  provider: 'qq',
  errorMessage: 'connection timeout'
});
if (!genericImapZh.some(item => String(item).includes('IMAP'))) {
  throw new Error('genericImapZh should mention IMAP checks');
}

context.window.getCurrentUiLanguage = () => 'en';
const outlookTokenError = context.buildRefreshErrorSuggestions({
  accountType: 'outlook',
  provider: 'outlook',
  errorMessage: 'AADSTS700082 expired refresh token'
});
if (!outlookTokenError.some(item => String(item).includes('Client ID and Refresh Token'))) {
  throw new Error('outlookTokenError should mention Client ID and Refresh Token');
}

context.window.getCurrentUiLanguage = () => 'zh';
context.showRefreshError(17, 'AADSTS900144 refresh_token invalid', 'user@gmail.com', 'imap', 'gmail');
if (!elements.get('refreshErrorModal').classList.contains('show')) {
  throw new Error('showRefreshError should open the modal');
}
if (!String(elements.get('refreshErrorSuggestions').innerHTML).includes('应用专用密码')) {
  throw new Error('showRefreshError should render gmail IMAP suggestions');
}
if (typeof elements.get('editAccountFromErrorBtn').onclick !== 'function') {
  throw new Error('showRefreshError should bind the edit account action');
}
elements.get('editAccountFromErrorBtn').onclick();
if (context.lastEditedAccountId !== 17) {
  throw new Error('showRefreshError should preserve the target account id for editing');
}

process.stdout.write('OK');
"""

        result = subprocess.run(
            ["node", "-e", node_script, "--", str(main_js_path)],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=f"node stdout:\n{result.stdout}\nnode stderr:\n{result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
