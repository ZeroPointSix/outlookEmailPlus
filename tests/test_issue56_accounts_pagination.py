from __future__ import annotations

import unittest
import uuid

from tests._import_app import clear_login_attempts, import_web_app_module


class Issue56AccountsPaginationTests(unittest.TestCase):
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
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), True)

    def _db(self):
        return self.module.create_sqlite_connection()

    def _create_group(self, name: str | None = None) -> int:
        unique = uuid.uuid4().hex
        group_name = name or f"issue56_group_{unique}"
        conn = self._db()
        try:
            cur = conn.execute(
                """
                INSERT INTO groups (name, description, color, proxy_url, is_system)
                VALUES (?, ?, ?, ?, 0)
                """,
                (group_name, "issue56 pagination test group", "#2E6B8A", ""),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def _create_account(
        self,
        *,
        group_id: int,
        email_addr: str,
        remark: str = "",
        last_refresh_at: str = "",
    ) -> int:
        unique = uuid.uuid4().hex
        conn = self._db()
        try:
            cur = conn.execute(
                """
                INSERT INTO accounts (
                    email, password, client_id, refresh_token, group_id, remark, status, last_refresh_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (email_addr, "", f"cid_{unique}", f"rt_{unique}", group_id, remark, last_refresh_at),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def _create_tag(self, name: str | None = None) -> int:
        unique = uuid.uuid4().hex
        tag_name = name or f"issue56_tag_{unique}"
        conn = self._db()
        try:
            cur = conn.execute("INSERT INTO tags (name, color) VALUES (?, ?)", (tag_name, "#B85C38"))
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def _attach_tag(self, account_id: int, tag_id: int) -> None:
        conn = self._db()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO account_tags (account_id, tag_id) VALUES (?, ?)",
                (account_id, tag_id),
            )
            conn.commit()
        finally:
            conn.close()

    def test_accounts_api_returns_pagination_metadata_and_page_slice(self):
        client = self.app.test_client()
        self._login(client)
        group_id = self._create_group()
        for index in range(55):
            self._create_account(group_id=group_id, email_addr=f"issue56_page_{index:03d}@example.com")

        resp = client.get(f"/api/accounts?group_id={group_id}&page=2&page_size=20")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), True)

        pagination = data.get("pagination") or {}
        self.assertEqual(pagination.get("page"), 2)
        self.assertEqual(pagination.get("page_size"), 20)
        self.assertEqual(pagination.get("total_count"), 55)
        self.assertEqual(pagination.get("total_pages"), 3)
        self.assertEqual(len(data.get("accounts") or []), 20)

    def test_accounts_api_search_is_scoped_to_requested_group(self):
        client = self.app.test_client()
        self._login(client)
        group_a = self._create_group(name="issue56_scope_a")
        group_b = self._create_group(name="issue56_scope_b")

        target_email = f"scope_a_{uuid.uuid4().hex}@example.com"
        other_email = f"scope_b_{uuid.uuid4().hex}@example.com"
        self._create_account(group_id=group_a, email_addr=target_email, remark="shared-search-key")
        self._create_account(group_id=group_b, email_addr=other_email, remark="shared-search-key")

        resp = client.get(f"/api/accounts?group_id={group_a}&search=shared-search-key&page=1&page_size=50")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), True)

        accounts = data.get("accounts") or []
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].get("email"), target_email)
        self.assertEqual(accounts[0].get("group_id"), group_a)
        self.assertEqual((data.get("pagination") or {}).get("total_count"), 1)

    def test_accounts_api_supports_tag_filter_and_email_sort(self):
        client = self.app.test_client()
        self._login(client)
        group_id = self._create_group()
        tag_id = self._create_tag(name="issue56-filter")

        account_c = self._create_account(group_id=group_id, email_addr=f"c_{uuid.uuid4().hex}@example.com")
        account_b = self._create_account(group_id=group_id, email_addr=f"b_{uuid.uuid4().hex}@example.com")
        self._create_account(group_id=group_id, email_addr=f"a_{uuid.uuid4().hex}@example.com")
        self._attach_tag(account_c, tag_id)
        self._attach_tag(account_b, tag_id)

        resp = client.get(
            f"/api/accounts?group_id={group_id}&tag_id={tag_id}&sort_by=email&sort_order=desc&page=1&page_size=50"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), True)

        accounts = data.get("accounts") or []
        self.assertEqual(len(accounts), 2)
        emails = [account.get("email") for account in accounts]
        self.assertEqual(emails, sorted(emails, reverse=True))
        self.assertEqual((data.get("pagination") or {}).get("total_count"), 2)

    def test_accounts_api_clamps_page_to_last_available_page(self):
        client = self.app.test_client()
        self._login(client)
        group_id = self._create_group()
        for index in range(21):
            self._create_account(group_id=group_id, email_addr=f"issue56_clamp_{index:03d}@example.com")

        resp = client.get(f"/api/accounts?group_id={group_id}&page=99&page_size=10")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), True)

        pagination = data.get("pagination") or {}
        self.assertEqual(pagination.get("page"), 3)
        self.assertEqual(pagination.get("total_pages"), 3)
        self.assertEqual(len(data.get("accounts") or []), 1)

    def test_accounts_api_falls_back_to_default_refresh_time_sort_for_invalid_sort_params(self):
        client = self.app.test_client()
        self._login(client)
        group_id = self._create_group()
        newest_email = f"issue56_sort_new_{uuid.uuid4().hex}@example.com"
        middle_email = f"issue56_sort_mid_{uuid.uuid4().hex}@example.com"
        oldest_email = f"issue56_sort_old_{uuid.uuid4().hex}@example.com"
        newest = self._create_account(
            group_id=group_id,
            email_addr=newest_email,
            last_refresh_at="2026-05-01 12:00:00",
        )
        middle = self._create_account(
            group_id=group_id,
            email_addr=middle_email,
            last_refresh_at="2026-05-01 11:00:00",
        )
        oldest = self._create_account(
            group_id=group_id,
            email_addr=oldest_email,
            last_refresh_at="2026-05-01 10:00:00",
        )

        self.assertTrue(all(account_id > 0 for account_id in [newest, middle, oldest]))

        resp = client.get(f"/api/accounts?group_id={group_id}&sort_by=unexpected&sort_order=unexpected&page=1&page_size=50")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertEqual(data.get("success"), True)

        emails = [account.get("email") for account in (data.get("accounts") or [])]
        self.assertGreaterEqual(len(emails), 3)
        self.assertEqual(
            emails[:3],
            [
                oldest_email,
                middle_email,
                newest_email,
            ],
        )
