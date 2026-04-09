import unittest
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

from tests._import_app import clear_login_attempts, import_web_app_module


class AccountDeleteWithPoolHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.db import get_db

            db = get_db()
            db.execute(
                "DELETE FROM account_claim_logs WHERE account_id IN (SELECT id FROM accounts WHERE email LIKE '%@issue32.test')"
            )
            db.execute(
                "DELETE FROM account_project_usage WHERE account_id IN (SELECT id FROM accounts WHERE email LIKE '%@issue32.test')"
            )
            db.execute("DELETE FROM accounts WHERE email LIKE '%@issue32.test'")
            db.commit()

    def _login(self, client):
        resp = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    def _insert_account_with_pool_history(
        self, prefix: str = "issue32"
    ) -> tuple[int, str]:
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            email_addr = f"{prefix}_{uuid.uuid4().hex[:12]}@issue32.test"
            cursor = db.execute(
                """
                INSERT INTO accounts (email, password, client_id, refresh_token, group_id, status, account_type, provider)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email_addr,
                    "pw",
                    "cid-test",
                    "rt-test",
                    1,
                    "active",
                    "outlook",
                    "outlook",
                ),
            )
            account_id = int(cursor.lastrowid)
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            db.execute(
                """
                INSERT INTO account_claim_logs
                (account_id, claim_token, caller_id, task_id, action, result, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    f"clm_{uuid.uuid4().hex[:10]}",
                    "issue32-bot",
                    f"task_{uuid.uuid4().hex[:8]}",
                    "claim",
                    "success",
                    "issue32 test fixture",
                    now,
                ),
            )
            db.execute(
                """
                INSERT INTO account_project_usage
                (account_id, consumer_key, project_key, first_claimed_at, last_claimed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (account_id, "issue32-consumer", "issue32-project", now, now),
            )
            db.commit()
            return account_id, email_addr

    def _assert_account_cascade_cleaned(self, account_id: int):
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            account_row = db.execute(
                "SELECT id FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
            claim_row = db.execute(
                "SELECT id FROM account_claim_logs WHERE account_id = ?", (account_id,)
            ).fetchone()
            usage_row = db.execute(
                "SELECT id FROM account_project_usage WHERE account_id = ?",
                (account_id,),
            ).fetchone()

            self.assertIsNone(account_row, "accounts 主表数据应已删除")
            self.assertIsNone(claim_row, "account_claim_logs 关联数据应已删除")
            self.assertIsNone(usage_row, "account_project_usage 关联数据应已删除")

    def test_delete_account_by_id_cleans_pool_related_tables(self):
        client = self.app.test_client()
        self._login(client)

        account_id, _ = self._insert_account_with_pool_history(prefix="single")
        resp = client.delete(f"/api/accounts/{account_id}")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertTrue(payload.get("success"))
        self._assert_account_cascade_cleaned(account_id)

    def test_batch_delete_returns_mixed_deleted_and_failed_counts(self):
        client = self.app.test_client()
        self._login(client)

        existing_id, _ = self._insert_account_with_pool_history(prefix="batch")
        missing_id = 987654321

        resp = client.post(
            "/api/accounts/batch-delete",
            json={"account_ids": [existing_id, missing_id]},
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertTrue(payload.get("success"))
        self.assertEqual(payload.get("deleted_count"), 1)
        self.assertEqual(payload.get("failed_count"), 1)
        self._assert_account_cascade_cleaned(existing_id)

    def test_delete_account_by_email_compat_route_reuses_delete_chain(self):
        client = self.app.test_client()
        self._login(client)

        account_id, email_addr = self._insert_account_with_pool_history(prefix="email")
        encoded_email = quote(email_addr, safe="")
        resp = client.delete(f"/api/accounts/email/{encoded_email}")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertTrue(payload.get("success"))
        self._assert_account_cascade_cleaned(account_id)
