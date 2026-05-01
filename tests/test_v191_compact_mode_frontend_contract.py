from __future__ import annotations

import re
import unittest

from tests._import_app import import_web_app_module


class V191CompactModeFrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), True)

    def _get_text(self, client, path: str) -> str:
        resp = client.get(path)
        try:
            return resp.data.decode("utf-8")
        finally:
            resp.close()

    def test_index_html_contains_only_standard_and_compact_mailbox_modes(self):
        client = self.app.test_client()
        self._login(client)
        index_html = self._get_text(client, "/")

        self.assertIn("标准模式", index_html)
        self.assertIn("简洁模式", index_html)
        self.assertNotIn("自动模式", index_html)
        self.assertIn('id="mailboxViewModeSwitcherTemplate"', index_html)

    def test_index_html_keeps_route_b_mailbox_and_temp_email_layout_contract(self):
        client = self.app.test_client()
        self._login(client)
        index_html = self._get_text(client, "/")

        self.assertIn('id="mailboxStandardLayout"', index_html)
        self.assertIn('class="workspace workspace-mailbox"', index_html)
        self.assertIn('class="workspace workspace-temp-emails"', index_html)
        self.assertIn('id="emailDetailSection"', index_html)
        self.assertIn('id="emailListPanel"', index_html)
        self.assertIn('id="mailboxCompactLayout"', index_html)

        temp_section = re.search(r'id="page-temp-emails".*?(?=id="page-refresh-log")', index_html, re.DOTALL)
        self.assertIsNotNone(temp_section)
        temp_html = temp_section.group(0)
        self.assertIn('id="tempEmailPanel"', temp_html)
        self.assertIn('id="tempEmailMessagePanel"', temp_html)
        self.assertNotIn('id="tempEmailDetailPanel"', temp_html)

        mailbox_section = re.search(r'id="mailboxStandardLayout".*?(?=id="mailboxCompactLayout")', index_html, re.DOTALL)
        self.assertIsNotNone(mailbox_section)
        mailbox_html = mailbox_section.group(0)
        self.assertIn('id="emailListPanel"', mailbox_html)
        self.assertIn('id="emailDetailSection"', mailbox_html)
        self.assertNotIn('id="emailDetailPanel"', mailbox_html)

    def test_index_html_loads_compact_module_but_not_legacy_layout_manager_assets(self):
        client = self.app.test_client()
        self._login(client)
        index_html = self._get_text(client, "/")

        self.assertIn("/static/js/features/mailbox_compact.js", index_html)
        self.assertNotIn("/static/js/layout-manager.js", index_html)
        self.assertNotIn("/static/js/layout-bootstrap.js", index_html)
        self.assertNotIn("/static/js/state-manager.js", index_html)
        self.assertNotIn("/static/css/layout.css", index_html)

    def test_frontend_exposes_mailbox_view_mode_state_and_scoped_batch_context(self):
        client = self.app.test_client()
        main_js = self._get_text(client, "/static/js/main.js")

        self.assertIn("let mailboxViewMode = localStorage.getItem('ol_mailbox_view_mode') || 'standard';", main_js)
        self.assertIn("let batchTagContext = { scopedAccountIds: null };", main_js)
        self.assertIn("let batchMoveGroupContext = { scopedAccountIds: null };", main_js)
        self.assertIn("async function showBatchTagModal(type, options = {})", main_js)
        self.assertIn("async function showBatchMoveGroupModal(options = {})", main_js)
        self.assertIn("scopedAccountIds", main_js)

    def test_compact_mode_module_exists_and_exposes_key_functions(self):
        client = self.app.test_client()
        module_js = self._get_text(client, "/static/js/features/mailbox_compact.js")

        for symbol in [
            "switchMailboxViewMode",
            "renderCompactGroupStrip",
            "renderCompactAccountList",
            "copyCompactVerification",
        ]:
            self.assertIn(symbol, module_js)

    def test_compact_switch_controls_standard_and_compact_layout_visibility(self):
        client = self.app.test_client()
        module_js = self._get_text(client, "/static/js/features/mailbox_compact.js")

        self.assertIn("standardLayout.style.display = mailboxViewMode === 'standard' ? '' : 'none';", module_js)
        self.assertIn("compactLayout.style.display = mailboxViewMode === 'compact' ? 'block' : 'none';", module_js)

    def test_compact_mode_reuses_global_selection_and_does_not_depend_on_detail_panel(self):
        client = self.app.test_client()
        main_js = self._get_text(client, "/static/js/main.js")
        compact_js = self._get_text(client, "/static/js/features/mailbox_compact.js")

        self.assertIn("let selectedAccountIds = new Set();", main_js)
        self.assertNotIn("let compactSelectedAccountIds", compact_js)
        self.assertNotIn("emailDetailSection", compact_js)
        self.assertNotIn("document.getElementById('emailDetail')", compact_js)

    def test_compact_mode_renders_backend_summary_fields(self):
        client = self.app.test_client()
        compact_js = self._get_text(client, "/static/js/features/mailbox_compact.js")

        for field in [
            "latest_email_subject",
            "latest_email_from",
            "latest_email_folder",
            "latest_email_received_at",
            "latest_verification_code",
        ]:
            self.assertIn(field, compact_js)

    def test_compact_mode_exposes_server_pagination_controls(self):
        client = self.app.test_client()
        compact_js = self._get_text(client, "/static/js/features/mailbox_compact.js")

        self.assertIn("const pagination = typeof getAccountListMeta === 'function' ? getAccountListMeta() :", compact_js)
        self.assertIn('class="account-pagination compact-account-pagination"', compact_js)
        self.assertIn('onclick="goToAccountPage(${Number(pagination.page || 1) - 1})"', compact_js)
        self.assertIn('onclick="goToAccountPage(${Number(pagination.page || 1) + 1})"', compact_js)

    def test_accounts_import_uses_refresh_mailbox_after_import(self):
        client = self.app.test_client()
        accounts_js = self._get_text(client, "/static/js/features/accounts.js")

        self.assertIn("function resolveImportGroupId(rawGroupId)", accounts_js)
        self.assertIn("async function refreshMailboxAfterImport(provider, importedGroupId)", accounts_js)
        self.assertIn("await loadGroups();", accounts_js)
        self.assertIn("await selectGroup(importedGroupId);", accounts_js)
        self.assertIn("await refreshMailboxAfterImport(provider, importedGroupId);", accounts_js)

    def test_groups_module_uses_per_account_verification_lock_and_summary_sync(self):
        client = self.app.test_client()
        groups_js = self._get_text(client, "/static/js/features/groups.js")

        self.assertIn("const verificationCopyInFlight = new Set();", groups_js)
        self.assertIn("verificationCopyInFlight.has(requestKey)", groups_js)
        self.assertIn("syncAccountSummaryToAccountCache", groups_js)
        self.assertIn("syncExtractedVerificationToAccountCache", groups_js)
        self.assertNotIn("let copyVerificationInProgress = false;", groups_js)

    def test_compact_action_menu_does_not_restore_extra_copy_menu_items(self):
        client = self.app.test_client()
        compact_js = self._get_text(client, "/static/js/features/mailbox_compact.js")

        self.assertNotIn(
            """<button class="menu-item" onclick="event.preventDefault(); event.stopPropagation(); closeCompactMenu(this); copyEmail('${escapeJs(account.email)}')">""",
            compact_js,
        )
        self.assertNotIn(
            """<button class="menu-item" onclick="event.preventDefault(); event.stopPropagation(); closeCompactMenu(this); copyCompactVerification(getCompactAccountById(${account.id}), this)">""",
            compact_js,
        )


if __name__ == "__main__":
    unittest.main()
