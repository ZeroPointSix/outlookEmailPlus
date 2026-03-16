import unittest
import uuid

from tests._import_app import clear_login_attempts, import_web_app_module


class ExternalPoolApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.db import get_db
            from outlook_web.repositories import settings as settings_repo

            db = get_db()
            db.execute("DELETE FROM audit_logs WHERE resource_type = 'external_api'")
            db.execute("DELETE FROM external_api_keys")
            db.execute("DELETE FROM external_api_consumer_usage_daily")
            db.execute(
                "DELETE FROM account_claim_logs WHERE account_id IN (SELECT id FROM accounts WHERE email LIKE '%@extpool.test')"
            )
            db.execute("DELETE FROM accounts WHERE email LIKE '%@extpool.test'")
            db.commit()
            settings_repo.set_setting("external_api_key", "")
            settings_repo.set_setting("external_api_public_mode", "false")
            settings_repo.set_setting("pool_external_enabled", "false")
            settings_repo.set_setting("external_api_ip_whitelist", "[]")
            settings_repo.set_setting("external_api_disable_pool_claim_random", "false")
            settings_repo.set_setting(
                "external_api_disable_pool_claim_release", "false"
            )
            settings_repo.set_setting(
                "external_api_disable_pool_claim_complete", "false"
            )
            settings_repo.set_setting("external_api_disable_pool_stats", "false")

    @staticmethod
    def _auth_headers(value: str = "abc123"):
        return {"X-API-Key": value}

    def _set_external_api_key(self, value: str):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("external_api_key", value)

    def _create_external_api_key(
        self,
        name: str,
        api_key: str,
        *,
        pool_access: bool = False,
        enabled: bool = True,
    ):
        with self.app.app_context():
            from outlook_web.repositories import (
                external_api_keys as external_api_keys_repo,
            )

            return external_api_keys_repo.create_external_api_key(
                name=name,
                api_key=api_key,
                allowed_emails=[],
                pool_access=pool_access,
                enabled=enabled,
            )

    def _set_public_mode(self, enabled: bool):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting(
                "external_api_public_mode", "true" if enabled else "false"
            )

    def _set_ip_whitelist(self, ips: list[str]):
        import json

        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("external_api_ip_whitelist", json.dumps(ips))

    def _set_disable_feature(self, setting_key: str, enabled: bool):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting(setting_key, "true" if enabled else "false")

    def _insert_pool_account(
        self, *, provider: str = "outlook", pool_status: str = "available"
    ) -> int:
        email_addr = f"{uuid.uuid4().hex}@extpool.test"
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            db.execute(
                """
                INSERT INTO accounts (
                    email, password, client_id, refresh_token,
                    group_id, status, account_type, provider, pool_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email_addr,
                    "pw",
                    "cid-test",
                    "rt-test",
                    1,
                    "active",
                    "outlook",
                    provider,
                    pool_status,
                ),
            )
            db.commit()
            row = db.execute(
                "SELECT id FROM accounts WHERE email = ?", (email_addr,)
            ).fetchone()
            return int(row["id"])

    def test_external_pool_stats_requires_api_key(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")

        resp = client.get("/api/external/pool/stats")

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.get_json().get("code"), "UNAUTHORIZED")

    def test_external_pool_claim_random_success(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("pool_external_enabled", "true")
        self._insert_pool_account(provider="outlook")

        resp = client.post(
            "/api/external/pool/claim-random",
            headers=self._auth_headers(),
            json={
                "caller_id": "ext-worker-01",
                "task_id": "task-ext-001",
                "provider": "outlook",
            },
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("code"), "OK")
        payload = data.get("data", {})
        self.assertIn("account_id", payload)
        self.assertIn("claim_token", payload)
        self.assertIn("lease_expires_at", payload)

    def test_external_pool_claim_release_caller_mismatch(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("pool_external_enabled", "true")
        self._insert_pool_account(provider="outlook")

        claim_resp = client.post(
            "/api/external/pool/claim-random",
            headers=self._auth_headers(),
            json={
                "caller_id": "ext-worker-01",
                "task_id": "task-ext-002",
                "provider": "outlook",
            },
        )
        self.assertEqual(claim_resp.status_code, 200)
        claim_data = claim_resp.get_json()["data"]

        release_resp = client.post(
            "/api/external/pool/claim-release",
            headers=self._auth_headers(),
            json={
                "account_id": claim_data["account_id"],
                "claim_token": claim_data["claim_token"],
                "caller_id": "ext-worker-02",
                "task_id": "task-ext-002",
            },
        )

        self.assertEqual(release_resp.status_code, 403)
        data = release_resp.get_json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data.get("code"), "CALLER_MISMATCH")

    def test_external_pool_claim_complete_success(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("pool_external_enabled", "true")
        self._insert_pool_account(provider="outlook")

        claim_resp = client.post(
            "/api/external/pool/claim-random",
            headers=self._auth_headers(),
            json={
                "caller_id": "ext-worker-01",
                "task_id": "task-ext-complete",
                "provider": "outlook",
            },
        )
        self.assertEqual(claim_resp.status_code, 200)
        claim_data = claim_resp.get_json()["data"]

        complete_resp = client.post(
            "/api/external/pool/claim-complete",
            headers=self._auth_headers(),
            json={
                "account_id": claim_data["account_id"],
                "claim_token": claim_data["claim_token"],
                "caller_id": "ext-worker-01",
                "task_id": "task-ext-complete",
                "result": "success",
                "detail": "done",
            },
        )

        self.assertEqual(complete_resp.status_code, 200)
        data = complete_resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("code"), "OK")
        self.assertEqual(data.get("data", {}).get("pool_status"), "used")

    def test_external_pool_stats_success(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("pool_external_enabled", "true")
        self._insert_pool_account(pool_status="available")
        self._insert_pool_account(pool_status="used")

        resp = client.get("/api/external/pool/stats", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("code"), "OK")
        self.assertIn("pool_counts", data.get("data", {}))

    def test_external_pool_stats_returns_feature_disabled_when_switch_off(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")

        resp = client.get("/api/external/pool/stats", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data.get("code"), "FEATURE_DISABLED")

    def test_external_pool_stats_disabled_in_public_mode(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("pool_external_enabled", "true")
        self._set_public_mode(True)
        self._set_ip_whitelist(["127.0.0.1"])
        self._set_disable_feature("external_api_disable_pool_stats", True)

        resp = client.get("/api/external/pool/stats", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertEqual(data.get("code"), "FEATURE_DISABLED")
        self.assertEqual(data.get("data", {}).get("feature"), "pool_stats")

    def test_external_pool_claim_random_disabled_in_public_mode(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("pool_external_enabled", "true")
        self._set_public_mode(True)
        self._set_ip_whitelist(["127.0.0.1"])
        self._set_disable_feature("external_api_disable_pool_claim_random", True)

        resp = client.post(
            "/api/external/pool/claim-random",
            headers=self._auth_headers(),
            json={"caller_id": "ext-worker-01", "task_id": "task-ext-disabled"},
        )

        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertEqual(data.get("code"), "FEATURE_DISABLED")
        self.assertEqual(data.get("data", {}).get("feature"), "pool_claim_random")

    def test_external_pool_claim_release_disabled_in_public_mode(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("pool_external_enabled", "true")
        self._insert_pool_account(provider="outlook")
        claim_resp = client.post(
            "/api/external/pool/claim-random",
            headers=self._auth_headers(),
            json={
                "caller_id": "ext-worker-01",
                "task_id": "task-ext-rel",
                "provider": "outlook",
            },
        )
        self.assertEqual(claim_resp.status_code, 200)
        claim_data = claim_resp.get_json()["data"]

        self._set_public_mode(True)
        self._set_ip_whitelist(["127.0.0.1"])
        self._set_disable_feature("external_api_disable_pool_claim_release", True)

        resp = client.post(
            "/api/external/pool/claim-release",
            headers=self._auth_headers(),
            json={
                "account_id": claim_data["account_id"],
                "claim_token": claim_data["claim_token"],
                "caller_id": "ext-worker-01",
                "task_id": "task-ext-rel",
            },
        )

        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertEqual(data.get("code"), "FEATURE_DISABLED")
        self.assertEqual(data.get("data", {}).get("feature"), "pool_claim_release")

    def test_external_pool_claim_complete_disabled_in_public_mode(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("pool_external_enabled", "true")
        self._insert_pool_account(provider="outlook")
        claim_resp = client.post(
            "/api/external/pool/claim-random",
            headers=self._auth_headers(),
            json={
                "caller_id": "ext-worker-01",
                "task_id": "task-ext-comp",
                "provider": "outlook",
            },
        )
        self.assertEqual(claim_resp.status_code, 200)
        claim_data = claim_resp.get_json()["data"]

        self._set_public_mode(True)
        self._set_ip_whitelist(["127.0.0.1"])
        self._set_disable_feature("external_api_disable_pool_claim_complete", True)

        resp = client.post(
            "/api/external/pool/claim-complete",
            headers=self._auth_headers(),
            json={
                "account_id": claim_data["account_id"],
                "claim_token": claim_data["claim_token"],
                "caller_id": "ext-worker-01",
                "task_id": "task-ext-comp",
                "result": "success",
            },
        )

        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertEqual(data.get("code"), "FEATURE_DISABLED")
        self.assertEqual(data.get("data", {}).get("feature"), "pool_claim_complete")

    def test_external_pool_requires_pool_access_for_multi_key(self):
        client = self.app.test_client()
        self._create_external_api_key("partner-a", "multi-pool-deny", pool_access=False)
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("pool_external_enabled", "true")
        self._insert_pool_account(provider="outlook")

        resp = client.get(
            "/api/external/pool/stats",
            headers=self._auth_headers("multi-pool-deny"),
        )

        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertEqual(data.get("code"), "FORBIDDEN")

    def test_external_pool_claim_random_requires_pool_access_for_multi_key(self):
        client = self.app.test_client()
        self._create_external_api_key(
            "partner-a", "multi-pool-random-deny", pool_access=False
        )
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("pool_external_enabled", "true")
        self._insert_pool_account(provider="outlook")

        resp = client.post(
            "/api/external/pool/claim-random",
            headers=self._auth_headers("multi-pool-random-deny"),
            json={
                "caller_id": "ext-worker-01",
                "task_id": "task-ext-no-access",
                "provider": "outlook",
            },
        )

        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertEqual(data.get("code"), "FORBIDDEN")

    def test_external_pool_returns_api_key_not_configured(self):
        client = self.app.test_client()

        resp = client.get(
            "/api/external/pool/stats",
            headers=self._auth_headers("unconfigured-key"),
        )

        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertEqual(data.get("code"), "API_KEY_NOT_CONFIGURED")

    def test_external_pool_ip_not_allowed_in_public_mode(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("pool_external_enabled", "true")
        self._set_public_mode(True)
        self._set_ip_whitelist(["10.0.0.1"])

        resp = client.get("/api/external/pool/stats", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertEqual(data.get("code"), "IP_NOT_ALLOWED")

    def test_external_pool_allows_pool_access_for_multi_key(self):
        client = self.app.test_client()
        self._create_external_api_key("partner-a", "multi-pool-allow", pool_access=True)
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("pool_external_enabled", "true")
        self._insert_pool_account(provider="outlook")

        resp = client.get(
            "/api/external/pool/stats",
            headers=self._auth_headers("multi-pool-allow"),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
