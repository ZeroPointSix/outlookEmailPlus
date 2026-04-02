import json
import unittest
import uuid

from tests._import_app import import_web_app_module


class PoolFlowSuiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app
        cls.client = cls.app.test_client()
        from outlook_web.db import create_sqlite_connection

        cls.create_conn = staticmethod(lambda: create_sqlite_connection())

    def setUp(self):
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.repositories import settings as settings_repo

            db = get_db()
            db.execute("DELETE FROM external_api_keys")
            db.execute("DELETE FROM external_api_rate_limits")
            db.execute("DELETE FROM account_project_usage")
            db.commit()
            settings_repo.set_setting("external_api_key", "abc123")
            settings_repo.set_setting("pool_external_enabled", "true")
            settings_repo.set_setting("external_api_public_mode", "false")
            settings_repo.set_setting("external_api_ip_whitelist", "[]")
            settings_repo.set_setting("external_api_rate_limit_per_minute", "60")
            settings_repo.set_setting("external_api_disable_pool_claim_random", "false")
            settings_repo.set_setting("external_api_disable_pool_claim_release", "false")
            settings_repo.set_setting("external_api_disable_pool_claim_complete", "false")
            settings_repo.set_setting("external_api_disable_pool_stats", "false")

    @staticmethod
    def _auth_headers():
        return {"X-API-Key": "abc123"}

    def _make_pool_account(self, *, email_domain: str = "outlook.com", provider: str = "outlook", pool_status: str = "available") -> dict:
        conn = self.create_conn()
        try:
            email_addr = f"flow_{uuid.uuid4().hex}@{email_domain}"
            conn.execute(
                """
                INSERT INTO accounts (
                    email, email_domain, client_id, refresh_token, status,
                    account_type, provider, group_id, pool_status
                )
                VALUES (?, ?, 'test_client', 'test_token', 'active', 'outlook', ?, 1, ?)
                """,
                (email_addr, email_domain, provider, pool_status),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id, email, email_domain, pool_status, provider FROM accounts WHERE email = ?",
                (email_addr,),
            ).fetchone()
            return dict(row)
        finally:
            conn.close()

    def _claim(self, *, task_id: str, project_key: str, provider: str = "outlook", email_domain: str | None = None):
        payload = {
            "caller_id": "suite_bot",
            "task_id": task_id,
            "project_key": project_key,
            "provider": provider,
        }
        if email_domain is not None:
            payload["email_domain"] = email_domain
        return self.client.post(
            "/api/external/pool/claim-random",
            headers=self._auth_headers(),
            json=payload,
        )

    def test_claim_complete_success_changes_status_to_cooldown(self):
        self._make_pool_account()

        claim_resp = self._claim(task_id="success_flow", project_key="register")
        self.assertEqual(claim_resp.status_code, 200)
        claim_data = json.loads(claim_resp.data)
        self.assertTrue(claim_data["success"])
        self.assertEqual(claim_data["data"]["provider"], "outlook")
        self.assertEqual(claim_data["data"]["email_domain"], "outlook.com")

        complete_resp = self.client.post(
            "/api/external/pool/claim-complete",
            headers=self._auth_headers(),
            json={
                "account_id": claim_data["data"]["account_id"],
                "claim_token": claim_data["data"]["claim_token"],
                "caller_id": "suite_bot",
                "task_id": "success_flow",
                "project_key": "register",
                "result": "success",
                "detail": "manual suite success",
            },
        )
        self.assertEqual(complete_resp.status_code, 200)
        complete_data = json.loads(complete_resp.data)
        self.assertTrue(complete_data["success"])
        self.assertEqual(complete_data["data"]["pool_status"], "cooldown")
        self.assertEqual(complete_data["data"]["provider"], "outlook")
        self.assertEqual(complete_data["data"]["email_domain"], "outlook.com")

        conn = self.create_conn()
        try:
            row = conn.execute(
                "SELECT pool_status, success_count, fail_count FROM accounts WHERE id = ?",
                (claim_data["data"]["account_id"],),
            ).fetchone()
            self.assertEqual(row["pool_status"], "cooldown")
            self.assertEqual(row["success_count"], 1)
            self.assertEqual(row["fail_count"], 0)

            usage = conn.execute(
                """
                SELECT consumer_key, project_key
                FROM account_project_usage
                WHERE account_id = ?
                """,
                (claim_data["data"]["account_id"],),
            ).fetchone()
            self.assertIsNotNone(usage)
            self.assertEqual(usage["project_key"], "register")
        finally:
            conn.close()

    def test_claim_complete_failure_changes_status_to_cooldown(self):
        self._make_pool_account()

        claim_resp = self._claim(task_id="cooldown_flow", project_key="register")
        self.assertEqual(claim_resp.status_code, 200)
        claim_data = json.loads(claim_resp.data)
        self.assertTrue(claim_data["success"])

        complete_resp = self.client.post(
            "/api/external/pool/claim-complete",
            headers=self._auth_headers(),
            json={
                "account_id": claim_data["data"]["account_id"],
                "claim_token": claim_data["data"]["claim_token"],
                "caller_id": "suite_bot",
                "task_id": "cooldown_flow",
                "project_key": "register",
                "result": "verification_timeout",
                "detail": "manual suite timeout",
            },
        )
        self.assertEqual(complete_resp.status_code, 200)
        complete_data = json.loads(complete_resp.data)
        self.assertTrue(complete_data["success"])
        self.assertEqual(complete_data["data"]["pool_status"], "cooldown")

    def test_same_project_cannot_reclaim_after_success_but_other_project_can(self):
        account = self._make_pool_account(email_domain="hotmail.com")

        first_claim = self._claim(task_id="same_project_1", project_key="register", email_domain="hotmail.com")
        self.assertEqual(first_claim.status_code, 200)
        first_data = first_claim.get_json()["data"]
        self.assertEqual(first_data["account_id"], account["id"])

        complete_resp = self.client.post(
            "/api/external/pool/claim-complete",
            headers=self._auth_headers(),
            json={
                "account_id": first_data["account_id"],
                "claim_token": first_data["claim_token"],
                "caller_id": "suite_bot",
                "task_id": "same_project_1",
                "project_key": "register",
                "result": "success",
            },
        )
        self.assertEqual(complete_resp.status_code, 200)

        conn = self.create_conn()
        try:
            conn.execute("UPDATE accounts SET pool_status = 'available' WHERE id = ?", (account["id"],))
            conn.commit()
        finally:
            conn.close()

        second_claim = self._claim(task_id="same_project_2", project_key="register", email_domain="hotmail.com")
        self.assertEqual(second_claim.status_code, 200)
        second_data = second_claim.get_json()
        self.assertFalse(second_data["success"])
        self.assertEqual(second_data["code"], "NO_AVAILABLE_ACCOUNT")

        other_project_claim = self._claim(task_id="other_project", project_key="login", email_domain="hotmail.com")
        self.assertEqual(other_project_claim.status_code, 200)
        other_project_data = other_project_claim.get_json()
        self.assertTrue(other_project_data["success"])
        self.assertEqual(other_project_data["data"]["account_id"], account["id"])

    def test_claim_random_filters_by_email_domain(self):
        self._make_pool_account(email_domain="outlook.com")
        hotmail_account = self._make_pool_account(email_domain="hotmail.com")

        claim_resp = self._claim(task_id="domain_filter", project_key="register", email_domain="HotMail.COM")
        self.assertEqual(claim_resp.status_code, 200)
        data = claim_resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["account_id"], hotmail_account["id"])
        self.assertEqual(data["data"]["email_domain"], "hotmail.com")


if __name__ == "__main__":
    unittest.main()
