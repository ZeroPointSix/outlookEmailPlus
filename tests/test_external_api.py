import json
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from tests._import_app import clear_login_attempts, import_web_app_module


class ExternalApiBaseTest(unittest.TestCase):
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
            db.execute("DELETE FROM accounts WHERE email LIKE '%@extapi.test'")
            db.execute("DELETE FROM external_api_keys")
            db.execute("DELETE FROM external_api_consumer_usage_daily")
            db.execute("DELETE FROM external_upstream_probes")
            db.execute("DELETE FROM external_probe_cache")
            db.commit()
            settings_repo.set_setting("external_api_key", "")

    def _set_external_api_key(self, value: str):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("external_api_key", value)

    def _create_external_api_key(
        self,
        name: str,
        api_key: str,
        *,
        allowed_emails: list[str] | None = None,
        enabled: bool = True,
    ):
        with self.app.app_context():
            from outlook_web.repositories import external_api_keys as external_api_keys_repo

            return external_api_keys_repo.create_external_api_key(
                name=name,
                api_key=api_key,
                allowed_emails=allowed_emails or [],
                enabled=enabled,
            )

    def _insert_outlook_account(self, email_addr: str | None = None) -> str:
        email_addr = email_addr or f"{uuid.uuid4().hex}@extapi.test"
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            db.execute(
                """
                INSERT INTO accounts (email, password, client_id, refresh_token, group_id, status, account_type, provider)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (email_addr, "pw", "cid-test", "rt-test", 1, "active", "outlook", "outlook"),
            )
            db.commit()
        return email_addr

    def _insert_claimed_pool_account(
        self,
        *,
        email_addr: str | None = None,
        project_key: str = "register",
        consumer_key: str = "legacy:settings.external_api_key",
        caller_id: str = "pool-worker",
        task_id: str = "pool-task",
        claim_token: str = "clm_test_token",
        claimed_at: str | None = None,
    ) -> str:
        email_addr = email_addr or f"{uuid.uuid4().hex}@extapi.test"
        claimed_at = claimed_at or self._utc_iso()
        claimed_by = f"{consumer_key}||{project_key}||{caller_id}||{task_id}"
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            db.execute(
                """
                INSERT INTO accounts (
                    email, email_domain, password, client_id, refresh_token, group_id,
                    status, account_type, provider, pool_status, claimed_by, claimed_at,
                    lease_expires_at, claim_token
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'claimed', ?, ?, ?, ?)
                """,
                (
                    email_addr,
                    email_addr.rsplit("@", 1)[-1].lower(),
                    "pw",
                    "cid-test",
                    "rt-test",
                    1,
                    "active",
                    "outlook",
                    "outlook",
                    claimed_by,
                    claimed_at,
                    self._utc_iso(minutes_delta=10),
                    claim_token,
                ),
            )
            db.commit()
        return email_addr

    def _insert_imap_account(self, email_addr: str | None = None) -> str:
        email_addr = email_addr or f"{uuid.uuid4().hex}@extapi.test"
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            db.execute(
                """
                INSERT INTO accounts (
                    email, password, client_id, refresh_token, group_id, status,
                    account_type, provider, imap_host, imap_port, imap_password
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (email_addr, "pw", "cid-test", "rt-test", 1, "active", "imap", "custom", "imap.test.com", 993, "imap-pass"),
            )
            db.commit()
        return email_addr

    def _set_account_status(self, email_addr: str, status: str):
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            db.execute("UPDATE accounts SET status = ? WHERE email = ?", (status, email_addr))
            db.commit()

    @staticmethod
    def _auth_headers(value: str = "abc123"):
        return {"X-API-Key": value}

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    @staticmethod
    def _utc_iso(minutes_delta: int = 0) -> str:
        dt = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(minutes=minutes_delta)
        return dt.isoformat().replace("+00:00", "Z")

    @classmethod
    def _graph_email(
        cls,
        message_id: str = "msg-1",
        subject: str = "Your verification code",
        sender: str = "noreply@example.com",
        received_at: str | None = None,
    ):
        return {
            "id": message_id,
            "subject": subject,
            "from": {"emailAddress": {"address": sender}},
            "receivedDateTime": received_at or cls._utc_iso(),
            "isRead": False,
            "hasAttachments": False,
            "bodyPreview": "Your code is 123456",
        }

    @classmethod
    def _graph_detail(
        cls,
        message_id: str = "msg-1",
        body_text: str = "Your code is 123456",
        html_text: str = "<p>Your code is 123456</p>",
        received_at: str | None = None,
    ):
        return {
            "id": message_id,
            "subject": "Your verification code",
            "from": {"emailAddress": {"address": "noreply@example.com"}},
            "toRecipients": [{"emailAddress": {"address": "user@outlook.com"}}],
            "receivedDateTime": received_at or cls._utc_iso(),
            "body": {"content": body_text if body_text else html_text, "contentType": "text" if body_text else "html"},
        }

    def _external_audit_logs(self):
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            rows = db.execute("""
                SELECT action, resource_id, details
                FROM audit_logs
                WHERE resource_type = 'external_api'
                ORDER BY id ASC
                """).fetchall()
        return [dict(row) for row in rows]

    def _external_consumer_usage_rows(self):
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            rows = db.execute("""
                SELECT consumer_key, consumer_name, endpoint, total_count, success_count, error_count
                FROM external_api_consumer_usage_daily
                ORDER BY id ASC
                """).fetchall()
        return [dict(row) for row in rows]


class ExternalApiAuthTests(ExternalApiBaseTest):
    def test_external_health_requires_api_key(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")

        resp = client.get("/api/external/health")

        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data.get("code"), "UNAUTHORIZED")

    def test_external_health_returns_403_when_api_key_not_configured(self):
        client = self.app.test_client()

        resp = client.get("/api/external/health", headers=self._auth_headers("abc123"))

        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertEqual(data.get("code"), "API_KEY_NOT_CONFIGURED")

    def test_external_health_accepts_valid_api_key(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")

        resp = client.get("/api/external/health", headers=self._auth_headers("abc123"))

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("code"), "OK")

    def test_external_health_accepts_valid_multi_api_key(self):
        client = self.app.test_client()
        self._create_external_api_key("partner-a", "multi-123")

        resp = client.get("/api/external/health", headers=self._auth_headers("multi-123"))

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    def test_disabled_multi_api_key_rejected(self):
        client = self.app.test_client()
        self._create_external_api_key("partner-a", "multi-123", enabled=False)

        resp = client.get("/api/external/health", headers=self._auth_headers("multi-123"))

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json().get("code"), "API_KEY_NOT_CONFIGURED")

    def test_disabled_multi_api_key_returns_401_when_other_enabled_key_exists(self):
        client = self.app.test_client()
        self._create_external_api_key("partner-a", "multi-123", enabled=False)
        self._create_external_api_key("partner-b", "multi-456", enabled=True)

        resp = client.get("/api/external/health", headers=self._auth_headers("multi-123"))

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.get_json().get("code"), "UNAUTHORIZED")

    def test_legacy_external_api_key_still_works_when_multi_keys_exist(self):
        client = self.app.test_client()
        self._create_external_api_key("partner-a", "multi-123")
        self._set_external_api_key("legacy-123")

        resp = client.get("/api/external/health", headers=self._auth_headers("legacy-123"))

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))


class ExternalApiMessageTests(ExternalApiBaseTest):
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_latest_message_returns_filtered_latest_email(self, mock_get_emails_graph):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        newer = self._graph_email(message_id="msg-new", subject="Target mail", received_at=self._utc_iso())
        older = self._graph_email(message_id="msg-old", subject="Ignore mail", received_at=self._utc_iso(minutes_delta=-2))
        mock_get_emails_graph.return_value = {"success": True, "emails": [older, newer]}

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages/latest?email={email_addr}&subject_contains=Target",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("data", {}).get("id"), "msg-new")

    def test_external_messages_returns_account_not_found(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")

        resp = client.get(
            "/api/external/messages?email=missing@extapi.test",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json().get("code"), "ACCOUNT_NOT_FOUND")

    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_messages_returns_list_when_graph_succeeds(self, mock_get_emails_graph):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {"success": True, "emails": [self._graph_email()]}

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("code"), "OK")
        self.assertEqual(len(data.get("data", {}).get("emails", [])), 1)


class ExternalApiKeyScopeTests(ExternalApiBaseTest):
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_messages_allows_email_within_key_scope(self, mock_get_emails_graph):
        email_addr = self._insert_outlook_account()
        self._create_external_api_key("partner-a", "scope-123", allowed_emails=[email_addr])
        mock_get_emails_graph.return_value = {"success": True, "emails": [self._graph_email()]}

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages?email={email_addr}",
            headers=self._auth_headers("scope-123"),
        )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    def test_external_messages_reject_email_outside_key_scope(self):
        allowed_email = self._insert_outlook_account()
        denied_email = self._insert_outlook_account()
        self._create_external_api_key("partner-a", "scope-123", allowed_emails=[allowed_email])

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages?email={denied_email}",
            headers=self._auth_headers("scope-123"),
        )

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json().get("code"), "EMAIL_SCOPE_FORBIDDEN")

    def test_external_account_status_reject_email_outside_key_scope(self):
        allowed_email = self._insert_outlook_account()
        denied_email = self._insert_outlook_account()
        self._create_external_api_key("partner-a", "scope-123", allowed_emails=[allowed_email])

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/account-status?email={denied_email}",
            headers=self._auth_headers("scope-123"),
        )

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json().get("code"), "EMAIL_SCOPE_FORBIDDEN")

    def test_probe_status_rejects_email_outside_key_scope(self):
        allowed_email = self._insert_outlook_account()
        denied_email = self._insert_outlook_account()
        self._create_external_api_key("partner-a", "scope-123", allowed_emails=[allowed_email])

        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            now = datetime.now(timezone.utc).isoformat()
            future = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
            db.execute(
                """
                INSERT INTO external_probe_cache
                    (id, email_addr, status, timeout_seconds, poll_interval, expires_at, created_at, updated_at)
                VALUES (?, ?, 'pending', 30, 5, ?, ?, ?)
                """,
                ("scope-probe-1", denied_email, future, now, now),
            )
            db.commit()

        client = self.app.test_client()
        resp = client.get("/api/external/probe/scope-probe-1", headers=self._auth_headers("scope-123"))

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json().get("code"), "EMAIL_SCOPE_FORBIDDEN")


class ExternalApiConsumerAuditTests(ExternalApiBaseTest):
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_multi_key_request_records_consumer_metadata_and_usage(self, mock_get_emails_graph):
        email_addr = self._insert_outlook_account()
        created = self._create_external_api_key("partner-a", "audit-123", allowed_emails=[email_addr])
        mock_get_emails_graph.return_value = {"success": True, "emails": [self._graph_email()]}

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages?email={email_addr}",
            headers=self._auth_headers("audit-123"),
        )

        self.assertEqual(resp.status_code, 200)
        audit_logs = self._external_audit_logs()
        self.assertEqual(len(audit_logs), 1)
        self.assertIn('"consumer_name": "partner-a"', audit_logs[0]["details"])
        self.assertIn(f'"consumer_id": {created["id"]}', audit_logs[0]["details"])

        usage_rows = self._external_consumer_usage_rows()
        self.assertEqual(len(usage_rows), 1)
        self.assertEqual(usage_rows[0]["consumer_key"], created["consumer_key"])
        self.assertEqual(usage_rows[0]["consumer_name"], "partner-a")
        self.assertEqual(usage_rows[0]["endpoint"], "/api/external/messages")
        self.assertEqual(usage_rows[0]["total_count"], 1)
        self.assertEqual(usage_rows[0]["success_count"], 1)

    @patch("outlook_web.services.imap.get_emails_imap_with_server")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_messages_falls_back_to_imap_when_graph_fails(self, mock_get_emails_graph, mock_get_emails_imap):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {"success": False, "error": "graph failed"}
        mock_get_emails_imap.return_value = {
            "success": True,
            "emails": [
                {
                    "id": "imap-1",
                    "subject": "IMAP Subject",
                    "from": "imap@example.com",
                    "date": "2026-03-08T12:00:00Z",
                    "is_read": False,
                    "has_attachments": False,
                    "body_preview": "preview",
                }
            ],
        }

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(len(data.get("data", {}).get("emails", [])), 1)

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    def test_external_message_detail_returns_message_content(self, mock_get_email_detail_graph, mock_get_email_raw_graph):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_email_detail_graph.return_value = self._graph_detail()
        mock_get_email_raw_graph.return_value = "RAW MIME CONTENT"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages/msg-1?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("content", data.get("data", {}))
        self.assertIn("raw_content", data.get("data", {}))
        self.assertEqual(data.get("data", {}).get("raw_content"), "RAW MIME CONTENT")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    def test_external_message_raw_returns_raw_content_and_audits(self, mock_get_email_detail_graph, mock_get_email_raw_graph):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_email_detail_graph.return_value = self._graph_detail(body_text="raw test")
        mock_get_email_raw_graph.return_value = "MIME-Version: 1.0\r\nraw test"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages/msg-1/raw?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("data", {}).get("raw_content"), "MIME-Version: 1.0\r\nraw test")

        audit_logs = self._external_audit_logs()
        self.assertEqual(len(audit_logs), 1)
        self.assertIn("/api/external/messages/{message_id}/raw", audit_logs[0]["details"])


class ExternalApiVerificationTests(ExternalApiBaseTest):
    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_verification_code_returns_code(
        self,
        mock_get_emails_graph,
        mock_get_email_detail_graph,
        mock_get_email_raw_graph,
    ):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {"success": True, "emails": [self._graph_email()]}
        mock_get_email_detail_graph.return_value = self._graph_detail(body_text="Your code is 123456")
        mock_get_email_raw_graph.return_value = "RAW MIME CONTENT"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-code?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("data", {}).get("verification_code"), "123456")

    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_verification_code_defaults_to_recent_10_minutes(self, mock_get_emails_graph):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {
            "success": True,
            "emails": [self._graph_email(received_at=self._utc_iso(minutes_delta=-20))],
        }

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-code?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json().get("code"), "MAIL_NOT_FOUND")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_verification_link_returns_preferred_link(
        self,
        mock_get_emails_graph,
        mock_get_email_detail_graph,
        mock_get_email_raw_graph,
    ):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {
            "success": True,
            "emails": [self._graph_email(subject="Please verify your email")],
        }
        mock_get_email_detail_graph.return_value = self._graph_detail(
            body_text="Click https://example.com/verify?token=abc to continue",
        )
        mock_get_email_raw_graph.return_value = "RAW MIME CONTENT"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-link?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("verify", data.get("data", {}).get("verification_link", ""))

    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_verification_link_defaults_to_recent_10_minutes(self, mock_get_emails_graph):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {
            "success": True,
            "emails": [self._graph_email(subject="Please verify your email", received_at=self._utc_iso(minutes_delta=-30))],
        }

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-link?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json().get("code"), "MAIL_NOT_FOUND")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_verification_code_supports_claim_token_baseline(
        self,
        mock_get_emails_graph,
        mock_get_email_detail_graph,
        mock_get_email_raw_graph,
    ):
        claimed_at = "2026-03-08T12:00:00Z"
        claim_email = self._insert_claimed_pool_account(
            email_addr=f"{uuid.uuid4().hex}@extapi.test",
            claim_token="clm_claim_read_001",
            claimed_at=claimed_at,
        )
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {
            "success": True,
            "emails": [
                self._graph_email(message_id="old-msg", received_at="2026-03-08T11:59:00Z"),
                self._graph_email(message_id="new-msg", received_at="2026-03-08T12:01:00Z"),
            ],
        }
        mock_get_email_detail_graph.return_value = self._graph_detail(
            message_id="new-msg",
            body_text="Your code is 123456",
            received_at="2026-03-08T12:01:00Z",
        )
        mock_get_email_raw_graph.return_value = "RAW MIME CONTENT"

        client = self.app.test_client()
        resp = client.get(
            "/api/external/verification-code?claim_token=clm_claim_read_001",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("data", {}).get("email"), claim_email)
        self.assertEqual(data.get("data", {}).get("matched_email_id"), "new-msg")
        self.assertEqual(data.get("data", {}).get("claim_token"), "clm_claim_read_001")

    def test_external_verification_code_rejects_claim_email_mismatch(self):
        self._insert_claimed_pool_account(
            email_addr=f"{uuid.uuid4().hex}@extapi.test",
            claim_token="clm_claim_mismatch_001",
        )
        self._set_external_api_key("abc123")
        client = self.app.test_client()

        resp = client.get(
            "/api/external/verification-code?claim_token=clm_claim_mismatch_001&email=other@extapi.test",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json().get("code"), "CLAIM_CONTEXT_MISMATCH")

    @patch("outlook_web.services.external_api.time.sleep")
    @patch("outlook_web.services.external_api.time.time")
    @patch("outlook_web.services.external_api.get_latest_message_for_external")
    def test_wait_for_message_only_returns_new_messages(self, mock_get_latest_message, mock_time, mock_sleep):
        from outlook_web.services import external_api as external_api_service

        mock_time.side_effect = [100, 100, 100]
        mock_get_latest_message.side_effect = [
            {"id": "old", "timestamp": 99, "method": "Graph API"},
            {"id": "new", "timestamp": 101, "method": "Graph API"},
        ]

        result = external_api_service.wait_for_message(email_addr="user@example.com", timeout_seconds=30, poll_interval=5)

        self.assertEqual(result.get("id"), "new")
        mock_sleep.assert_called_once_with(5)

    def test_external_wait_message_rejects_too_large_timeout(self):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        client = self.app.test_client()

        resp = client.get(
            f"/api/external/wait-message?email={email_addr}&timeout_seconds=999",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json().get("code"), "INVALID_PARAM")


class ExternalApiSystemTests(ExternalApiBaseTest):
    def test_external_capabilities_returns_feature_list_and_audits(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")

        resp = client.get("/api/external/capabilities", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("service", data.get("data", {}))
        self.assertIn("version", data.get("data", {}))
        self.assertIn("features", data.get("data", {}))

        audit_logs = self._external_audit_logs()
        self.assertEqual(len(audit_logs), 1)
        self.assertIn("/api/external/capabilities", audit_logs[0]["details"])

    def test_external_health_audits_access(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")
        with self.app.app_context():
            from outlook_web.services import external_api as external_api_service

            external_api_service.record_upstream_probe_summary(
                scope_type="instance",
                scope_key="__instance__",
                email_addr="probe@extapi.test",
                probe_ok=True,
                probe_method="Graph API",
                last_probe_error="",
                last_probe_at=self._utc_iso(),
            )

        resp = client.get("/api/external/health", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json().get("data", {})
        self.assertTrue(data.get("upstream_probe_ok"))
        self.assertTrue(data.get("last_probe_at"))
        audit_logs = self._external_audit_logs()
        self.assertEqual(len(audit_logs), 1)
        self.assertIn("/api/external/health", audit_logs[0]["details"])

    @patch("outlook_web.controllers.system.external_api_service.probe_instance_upstream")
    def test_external_health_uses_probe_instance_upstream(self, mock_probe_instance_upstream):
        client = self.app.test_client()
        self._set_external_api_key("abc123")
        mock_probe_instance_upstream.return_value = {
            "upstream_probe_ok": True,
            "last_probe_at": self._utc_iso(),
            "last_probe_error": "",
            "probe_method": "Graph API",
        }

        resp = client.get("/api/external/health", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("data", {}).get("upstream_probe_ok"))
        mock_probe_instance_upstream.assert_called_once()

    @patch("outlook_web.services.external_api.graph_service.get_emails_graph")
    def test_external_account_status_returns_account_data_and_audits(self, mock_get_emails_graph):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {"success": True, "emails": [self._graph_email()]}
        client = self.app.test_client()

        resp = client.get(
            f"/api/external/account-status?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("data", {}).get("email"), email_addr)
        self.assertTrue(data.get("data", {}).get("exists"))
        self.assertEqual(data.get("data", {}).get("account_type"), "outlook")
        self.assertEqual(data.get("data", {}).get("provider"), "outlook")
        self.assertIn("preferred_method", data.get("data", {}))
        self.assertIn("last_refresh_at", data.get("data", {}))
        self.assertTrue(data.get("data", {}).get("can_read"))
        self.assertTrue(data.get("data", {}).get("upstream_probe_ok"))
        self.assertTrue(data.get("data", {}).get("last_probe_at"))
        self.assertEqual(data.get("data", {}).get("probe_method"), "Graph API")
        self.assertEqual(data.get("data", {}).get("last_probe_error"), "")

        audit_logs = self._external_audit_logs()
        self.assertEqual(len(audit_logs), 1)
        self.assertIn("/api/external/account-status", audit_logs[0]["details"])

    @patch("outlook_web.services.external_api.imap_service.get_emails_imap_with_server")
    @patch("outlook_web.services.external_api.graph_service.get_emails_graph")
    def test_external_account_status_probe_failure_returns_probe_summary(self, mock_get_emails_graph, mock_get_emails_imap):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {"success": False, "error": {"message": "token invalid"}}
        mock_get_emails_imap.return_value = {"success": False, "error": {"message": "imap fallback failed"}}
        client = self.app.test_client()

        resp = client.get(
            f"/api/external/account-status?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json().get("data", {})
        self.assertFalse(data.get("upstream_probe_ok"))
        self.assertEqual(data.get("probe_method"), "graph")
        self.assertTrue(data.get("last_probe_at"))
        self.assertTrue(data.get("last_probe_error"))


class ExternalApiRegressionTests(ExternalApiBaseTest):
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_internal_email_list_api_still_works(self, mock_get_emails_graph):
        email_addr = self._insert_outlook_account()
        mock_get_emails_graph.return_value = {"success": True, "emails": [self._graph_email()]}

        client = self.app.test_client()
        self._login(client)
        resp = client.get(f"/api/emails/{email_addr}")

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("emails", data)

    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_internal_extract_verification_api_still_works(self, mock_get_emails_graph, mock_get_email_detail_graph):
        email_addr = self._insert_outlook_account()
        mock_get_emails_graph.return_value = {"success": True, "emails": [self._graph_email()]}
        mock_get_email_detail_graph.return_value = self._graph_detail(body_text="Your code is 123456")

        client = self.app.test_client()
        self._login(client)
        resp = client.get(f"/api/emails/{email_addr}/extract-verification")

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("data", {}).get("verification_code"), "123456")

    def test_internal_settings_api_still_returns_existing_fields(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.get("/api/settings")

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("refresh_interval_days", data.get("settings", {}))
        self.assertIn("gptmail_api_key_set", data.get("settings", {}))


class ExternalApiSchemaValidationTests(ExternalApiBaseTest):
    """OpenAPI 返回字段抽样校验：确认核心接口的返回字段覆盖 OpenAPI schema required 字段"""

    @patch("outlook_web.services.graph.get_emails_graph")
    def test_messages_response_schema_has_required_fields(self, mock_get_emails_graph):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {"success": True, "emails": [self._graph_email()]}

        client = self.app.test_client()
        resp = client.get(f"/api/external/messages?email={email_addr}", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        # 顶层统一响应结构
        for key in ("success", "code", "message", "data"):
            self.assertIn(key, body, f"顶层缺少字段: {key}")
        data = body["data"]
        self.assertIn("emails", data)
        self.assertIn("count", data)
        # MessageSummary required 字段
        if data["emails"]:
            msg = data["emails"][0]
            for key in ("id", "email_address", "from_address", "subject", "has_html", "timestamp", "created_at", "is_read"):
                self.assertIn(key, msg, f"MessageSummary 缺少字段: {key}")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    def test_message_detail_response_schema_has_required_fields(self, mock_detail, mock_raw):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_detail.return_value = self._graph_detail()
        mock_raw.return_value = "RAW"

        client = self.app.test_client()
        resp = client.get(f"/api/external/messages/msg-1?email={email_addr}", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json().get("data", {})
        for key in (
            "id",
            "email_address",
            "from_address",
            "subject",
            "content",
            "html_content",
            "raw_content",
            "timestamp",
            "created_at",
            "has_html",
        ):
            self.assertIn(key, data, f"MessageDetail 缺少字段: {key}")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_verification_code_response_schema_has_required_fields(self, mock_list, mock_detail, mock_raw):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_list.return_value = {"success": True, "emails": [self._graph_email()]}
        mock_detail.return_value = self._graph_detail(body_text="Your code is 123456")
        mock_raw.return_value = "RAW"

        client = self.app.test_client()
        resp = client.get(f"/api/external/verification-code?email={email_addr}", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json().get("data", {})
        for key in ("email", "verification_code", "matched_email_id", "from", "subject", "received_at"):
            self.assertIn(key, data, f"VerificationCodeData 缺少字段: {key}")
        # confidence 枚举校验
        self.assertIn(data.get("confidence"), ("high", "low"), "confidence 应为 high 或 low")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_verification_link_response_schema_has_required_fields(self, mock_list, mock_detail, mock_raw):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_list.return_value = {
            "success": True,
            "emails": [self._graph_email(subject="Please verify")],
        }
        mock_detail.return_value = self._graph_detail(
            body_text="Click https://example.com/verify?token=abc to verify",
        )
        mock_raw.return_value = "RAW"

        client = self.app.test_client()
        resp = client.get(f"/api/external/verification-link?email={email_addr}", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json().get("data", {})
        for key in ("email", "verification_link", "matched_email_id", "from", "subject", "received_at"):
            self.assertIn(key, data, f"VerificationLinkData 缺少字段: {key}")

    def test_health_response_schema_has_required_fields(self):
        self._set_external_api_key("abc123")
        client = self.app.test_client()
        resp = client.get("/api/external/health", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json().get("data", {})
        for key in (
            "status",
            "service",
            "version",
            "server_time_utc",
            "database",
            "upstream_probe_ok",
            "last_probe_at",
            "last_probe_error",
        ):
            self.assertIn(key, data, f"HealthData 缺少字段: {key}")

    def test_capabilities_response_schema_has_required_fields(self):
        self._set_external_api_key("abc123")
        client = self.app.test_client()
        resp = client.get("/api/external/capabilities", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json().get("data", {})
        for key in ("service", "version", "features"):
            self.assertIn(key, data, f"CapabilitiesData 缺少字段: {key}")
        self.assertIsInstance(data["features"], list)

    @patch("outlook_web.services.external_api.graph_service.get_emails_graph")
    def test_account_status_response_schema_has_required_fields(self, mock_get_emails_graph):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {"success": True, "emails": [self._graph_email()]}
        client = self.app.test_client()
        resp = client.get(f"/api/external/account-status?email={email_addr}", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json().get("data", {})
        for key in ("email", "exists", "upstream_probe_ok", "probe_method", "last_probe_at", "last_probe_error"):
            self.assertIn(key, data, f"AccountStatusData 缺少字段: {key}")
        self.assertIn("status", data, "AccountStatusData 应返回 status 字段")

    @patch("outlook_web.services.external_api.graph_service.get_emails_graph")
    def test_account_status_marks_inactive_account_as_not_readable(self, mock_get_emails_graph):
        email_addr = self._insert_outlook_account()
        self._set_account_status(email_addr, "inactive")
        self._set_external_api_key("abc123")
        client = self.app.test_client()

        resp = client.get(f"/api/external/account-status?email={email_addr}", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json().get("data", {})
        self.assertFalse(data.get("can_read"))
        self.assertIsNone(data.get("upstream_probe_ok"))
        mock_get_emails_graph.assert_not_called()


class ExternalApiRawFieldTrimTests(ExternalApiBaseTest):
    """验证 /messages/{id}/raw 仅返回裁剪后的字段"""

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    def test_raw_endpoint_only_returns_trimmed_fields(self, mock_detail, mock_raw):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_detail.return_value = self._graph_detail(body_text="body text here")
        mock_raw.return_value = "MIME-Version: 1.0\r\nraw content"

        client = self.app.test_client()
        resp = client.get(f"/api/external/messages/msg-1/raw?email={email_addr}", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json().get("data", {})
        allowed_keys = {"id", "email_address", "raw_content", "method"}
        actual_keys = set(data.keys())
        self.assertEqual(actual_keys, allowed_keys, f"raw 接口应仅返回 {allowed_keys}，实际返回 {actual_keys}")
        self.assertEqual(data["raw_content"], "MIME-Version: 1.0\r\nraw content")
        # 不应包含详情字段
        self.assertNotIn("content", data)
        self.assertNotIn("html_content", data)
        self.assertNotIn("subject", data)


class ExternalApiWaitMessageHttpTests(ExternalApiBaseTest):
    """wait-message HTTP 层集成测试"""

    @patch("outlook_web.services.external_api.time.sleep")
    @patch("outlook_web.services.external_api.time.time")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_wait_message_http_only_returns_new_message(self, mock_get_emails_graph, mock_time, mock_sleep):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")

        # baseline_timestamp = int(time.time()) = 2000000000
        # old email timestamp (~1767225600) < baseline → 不匹配
        # new email timestamp (~2019686400) >= baseline → 命中
        mock_time.side_effect = [2000000000, 2000000000, 2000000000, 2000000000, 2000000000]
        old_email = self._graph_email(message_id="old-msg", received_at="2026-01-01T00:00:00Z")
        new_email = self._graph_email(message_id="new-msg", received_at="2034-01-01T00:00:00Z")
        mock_get_emails_graph.side_effect = [
            {"success": True, "emails": [old_email]},
            {"success": True, "emails": [new_email]},
        ]

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/wait-message?email={email_addr}&timeout_seconds=30&poll_interval=5",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("data", {}).get("id"), "new-msg")

    def test_wait_message_http_returns_400_for_invalid_timeout(self):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        client = self.app.test_client()

        resp = client.get(
            f"/api/external/wait-message?email={email_addr}&timeout_seconds=0",
            headers=self._auth_headers(),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json().get("code"), "INVALID_PARAM")

    def test_wait_message_http_returns_400_for_missing_email(self):
        self._set_external_api_key("abc123")
        client = self.app.test_client()

        resp = client.get(
            "/api/external/wait-message?timeout_seconds=10",
            headers=self._auth_headers(),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json().get("code"), "INVALID_PARAM")

    @patch("outlook_web.services.external_api.time.sleep")
    @patch("outlook_web.services.external_api.time.time")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_wait_message_http_supports_claim_token_baseline(self, mock_get_emails_graph, mock_time, mock_sleep):
        self._insert_claimed_pool_account(
            email_addr=f"{uuid.uuid4().hex}@extapi.test",
            claim_token="clm_wait_claim_001",
            claimed_at="2026-03-08T12:00:00Z",
        )
        self._set_external_api_key("abc123")
        mock_time.side_effect = [2000000000, 2000000000, 2000000000]
        mock_get_emails_graph.side_effect = [
            {"success": True, "emails": [self._graph_email(message_id="old-msg", received_at="2026-03-08T11:59:00Z")]},
            {"success": True, "emails": [self._graph_email(message_id="new-msg", received_at="2026-03-08T12:01:00Z")]},
        ]

        client = self.app.test_client()
        resp = client.get(
            "/api/external/wait-message?claim_token=clm_wait_claim_001&timeout_seconds=30&poll_interval=5",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("data", {}).get("id"), "new-msg")
        self.assertEqual(data.get("data", {}).get("claim_token"), "clm_wait_claim_001")

    @patch("outlook_web.services.external_api.wait_for_message")
    def test_wait_message_http_unexpected_error_logs_audit(self, mock_wait_for_message):
        """wait-message 未预期异常也应写 external_api 审计日志"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_wait_for_message.side_effect = RuntimeError("boom")

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/wait-message?email={email_addr}&timeout_seconds=10&poll_interval=5",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.get_json().get("code"), "INTERNAL_ERROR")

        audit_logs = self._external_audit_logs()
        self.assertGreaterEqual(len(audit_logs), 1)
        last_log = audit_logs[-1]
        details = json.loads(last_log["details"]) if isinstance(last_log["details"], str) else last_log["details"]
        self.assertEqual(details.get("code"), "INTERNAL_ERROR")
        self.assertEqual(details.get("err"), "RuntimeError")


# ---------------------------------------------------------------------------
# TC-AUTH-03: 错误 API Key → 401 UNAUTHORIZED
# ---------------------------------------------------------------------------
class ExternalApiWrongKeyTests(ExternalApiBaseTest):
    """TC-AUTH-03"""

    def test_wrong_api_key_returns_401(self):
        self._set_external_api_key("correct-key-123")
        client = self.app.test_client()

        resp = client.get("/api/external/health", headers=self._auth_headers("wrong-key-456"))

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.get_json().get("code"), "UNAUTHORIZED")


# ---------------------------------------------------------------------------
# TC-MSG-04 ~ TC-MSG-15: 消息接口参数校验、过滤、回退、错误路径
# ---------------------------------------------------------------------------
class ExternalApiMessageParamTests(ExternalApiBaseTest):
    """TC-MSG-04, TC-MSG-05, TC-MSG-06, TC-MSG-07, TC-MSG-08"""

    def test_invalid_folder_returns_400(self):
        """TC-MSG-04: folder 参数非法 → 400"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        client = self.app.test_client()

        resp = client.get(
            f"/api/external/messages?email={email_addr}&folder=spam",
            headers=self._auth_headers(),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json().get("code"), "INVALID_PARAM")

    def test_top_param_zero_returns_400(self):
        """TC-MSG-05: top=0 越界"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        client = self.app.test_client()

        resp = client.get(
            f"/api/external/messages?email={email_addr}&top=0",
            headers=self._auth_headers(),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json().get("code"), "INVALID_PARAM")

    def test_top_param_too_large_returns_400(self):
        """TC-MSG-05: top=999 越界"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        client = self.app.test_client()

        resp = client.get(
            f"/api/external/messages?email={email_addr}&top=999",
            headers=self._auth_headers(),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json().get("code"), "INVALID_PARAM")

    @patch("outlook_web.services.graph.get_emails_graph")
    def test_from_contains_filter(self, mock_get_emails_graph):
        """TC-MSG-06: from_contains 过滤"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {
            "success": True,
            "emails": [
                self._graph_email(message_id="m1", sender="openai@example.com", subject="OpenAI Code"),
                self._graph_email(message_id="m2", sender="google@example.com", subject="Google Code"),
            ],
        }

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages?email={email_addr}&from_contains=openai",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        emails = resp.get_json().get("data", {}).get("emails", [])
        self.assertEqual(len(emails), 1)
        self.assertIn("openai", emails[0].get("from_address", "").lower())

    @patch("outlook_web.services.graph.get_emails_graph")
    def test_since_minutes_filter(self, mock_get_emails_graph):
        """TC-MSG-08: since_minutes 过滤"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {
            "success": True,
            "emails": [
                self._graph_email(message_id="new", received_at=self._utc_iso(minutes_delta=-2)),
                self._graph_email(message_id="old", received_at=self._utc_iso(minutes_delta=-60)),
            ],
        }

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages?email={email_addr}&since_minutes=10",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        emails = resp.get_json().get("data", {}).get("emails", [])
        self.assertEqual(len(emails), 1)
        self.assertEqual(emails[0].get("id"), "new")


class ExternalApiMessageErrorTests(ExternalApiBaseTest):
    """TC-MSG-10, TC-MSG-13, TC-MSG-14, TC-MSG-15"""

    @patch("outlook_web.services.graph.get_emails_graph")
    def test_latest_message_not_found(self, mock_get_emails_graph):
        """TC-MSG-10: 最新邮件不存在 → 404"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {"success": True, "emails": []}

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages/latest?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json().get("code"), "MAIL_NOT_FOUND")

    @patch("outlook_web.services.imap.get_email_detail_imap_with_server")
    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    def test_detail_graph_fail_imap_fallback(self, mock_detail_graph, mock_raw_graph, mock_detail_imap):
        """TC-MSG-13: 详情 Graph 失败后 IMAP 回退成功"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_detail_graph.return_value = None
        mock_raw_graph.return_value = None
        mock_detail_imap.return_value = {
            "id": "msg-1",
            "subject": "IMAP Detail Subject",
            "from": "sender@test.com",
            "date": self._utc_iso(),
            "body": "IMAP body content",
            "html": "<p>IMAP body content</p>",
        }

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages/msg-1?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json().get("data", {})
        self.assertIn("content", data)
        self.assertIn("IMAP", data.get("method", ""))

    @patch("outlook_web.services.imap.get_emails_imap_with_server")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_all_upstream_fail_returns_502(self, mock_graph, mock_imap):
        """TC-MSG-14: Graph + IMAP 全部失败 → 502 UPSTREAM_READ_FAILED"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_graph.return_value = {"success": False, "error": "graph error"}
        mock_imap.return_value = {"success": False, "error": "imap error"}

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 502)
        self.assertEqual(resp.get_json().get("code"), "UPSTREAM_READ_FAILED")

    @patch("outlook_web.services.graph.get_emails_graph")
    def test_proxy_error_returns_502(self, mock_graph):
        """TC-MSG-15: Graph 代理错误 → 502 PROXY_ERROR"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_graph.return_value = {
            "success": False,
            "error": {"type": "ProxyError", "message": "Proxy connection failed"},
        }

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 502)
        self.assertEqual(resp.get_json().get("code"), "PROXY_ERROR")

    @patch("outlook_web.services.graph.get_emails_graph")
    def test_proxy_error_with_nested_payload_still_returns_502_proxy_error(self, mock_graph):
        """TC-MSG-15 扩展：Graph 返回结构化错误 payload 时仍应保持 502 PROXY_ERROR"""
        from outlook_web.errors import build_error_payload

        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_graph.return_value = {
            "success": False,
            "error": build_error_payload(
                "GRAPH_TOKEN_EXCEPTION",
                "Proxy tunnel failed",
                err_type="ProxyError",
                status=500,
                details="proxy-down",
                trace_id="test-trace",
            ),
        }

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 502)
        self.assertEqual(resp.get_json().get("code"), "PROXY_ERROR")
        audit_logs = self._external_audit_logs()
        self.assertTrue(audit_logs)
        details = (
            json.loads(audit_logs[-1]["details"]) if isinstance(audit_logs[-1]["details"], str) else audit_logs[-1]["details"]
        )
        self.assertEqual(details.get("code"), "PROXY_ERROR")

    @patch("outlook_web.services.external_api.get_email_detail_imap_generic_result")
    def test_imap_detail_nested_error_uses_final_public_code_in_response_and_audit(self, mock_detail_result):
        email_addr = self._insert_imap_account()
        self._set_external_api_key("abc123")
        mock_detail_result.return_value = {
            "success": False,
            "error": {
                "code": "IMAP_AUTH_FAILED",
                "message": "IMAP 认证失败：Outlook.com 已阻止 Basic Auth（账号密码直连），请改用 Outlook OAuth 导入（client_id + refresh_token）",
                "message_en": "IMAP authentication failed: Outlook.com blocked Basic Auth. Use Outlook OAuth import instead.",
                "type": "IMAPAuthError",
                "status": 401,
                "details": "",
                "trace_id": "test-trace",
            },
            "error_code": "IMAP_AUTH_FAILED",
        }

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages/msg-1?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.get_json().get("code"), "IMAP_AUTH_FAILED")
        audit_logs = self._external_audit_logs()
        self.assertTrue(audit_logs)
        details = (
            json.loads(audit_logs[-1]["details"]) if isinstance(audit_logs[-1]["details"], str) else audit_logs[-1]["details"]
        )
        self.assertEqual(details.get("code"), "IMAP_AUTH_FAILED")

    def test_messages_for_inactive_account_returns_403(self):
        email_addr = self._insert_outlook_account()
        self._set_account_status(email_addr, "inactive")
        self._set_external_api_key("abc123")

        client = self.app.test_client()
        resp = client.get(f"/api/external/messages?email={email_addr}", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json().get("code"), "ACCOUNT_ACCESS_FORBIDDEN")

    def test_wait_message_for_disabled_account_returns_403(self):
        email_addr = self._insert_outlook_account()
        self._set_account_status(email_addr, "disabled")
        self._set_external_api_key("abc123")

        client = self.app.test_client()
        resp = client.get(f"/api/external/wait-message?email={email_addr}", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json().get("code"), "ACCOUNT_ACCESS_FORBIDDEN")


# ---------------------------------------------------------------------------
# TC-VER-04, TC-VER-06, TC-VER-09, TC-VER-12: 验证码/链接错误路径
# ---------------------------------------------------------------------------
class ExternalApiVerificationErrorTests(ExternalApiBaseTest):
    """TC-VER-04, TC-VER-06, TC-VER-09, TC-VER-12"""

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_invalid_code_regex_returns_400(self, mock_list, mock_detail, mock_raw):
        """TC-VER-04: 非法正则 → 400 INVALID_PARAM"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_list.return_value = {"success": True, "emails": [self._graph_email()]}
        mock_detail.return_value = self._graph_detail(body_text="Code is 123456")
        mock_raw.return_value = "RAW"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-code?email={email_addr}&code_regex=[invalid",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json().get("code"), "INVALID_PARAM")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_no_verification_code_returns_404(self, mock_list, mock_detail, mock_raw):
        """TC-VER-06: 邮件存在但无验证码 → 404 VERIFICATION_CODE_NOT_FOUND"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_list.return_value = {"success": True, "emails": [self._graph_email()]}
        mock_detail.return_value = self._graph_detail(body_text="Hello, this is a normal email with no code.")
        mock_raw.return_value = "RAW"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-code?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json().get("code"), "VERIFICATION_CODE_NOT_FOUND")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_no_verification_link_returns_404(self, mock_list, mock_detail, mock_raw):
        """TC-VER-09: 邮件存在但无验证链接 → 404 VERIFICATION_LINK_NOT_FOUND"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_list.return_value = {"success": True, "emails": [self._graph_email()]}
        mock_detail.return_value = self._graph_detail(body_text="No links here at all.")
        mock_raw.return_value = "RAW"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-link?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json().get("code"), "VERIFICATION_LINK_NOT_FOUND")

    @patch("outlook_web.services.external_api.time.sleep")
    @patch("outlook_web.services.external_api.time.time")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_wait_message_timeout_returns_404(self, mock_graph, mock_time, mock_sleep):
        """TC-VER-12: 等待超时 → 404 MAIL_NOT_FOUND"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        # time.time() 模拟: baseline=100, start=100, 第1次循环检查=100, 第2次=200(超时)
        mock_time.side_effect = [100, 100, 100, 200]
        mock_graph.return_value = {"success": True, "emails": []}

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/wait-message?email={email_addr}&timeout_seconds=10&poll_interval=5",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json().get("code"), "MAIL_NOT_FOUND")


# ---------------------------------------------------------------------------
# TC-SYS-04: account-status 账号不存在
# ---------------------------------------------------------------------------
class ExternalApiSystemErrorTests(ExternalApiBaseTest):
    """TC-SYS-04"""

    def test_account_status_not_found(self):
        """TC-SYS-04: account-status 账号不存在 → 404 ACCOUNT_NOT_FOUND"""
        self._set_external_api_key("abc123")
        client = self.app.test_client()

        resp = client.get(
            "/api/external/account-status?email=nonexist@nowhere.test",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json().get("code"), "ACCOUNT_NOT_FOUND")


# ---------------------------------------------------------------------------
# BUG-00017 止血：营销邮件误命中 & 低置信度拦截
# ---------------------------------------------------------------------------
class ExternalApiVerificationConfidenceTests(ExternalApiBaseTest):
    """BUG-00017: 低置信度结果不再返回 200 OK"""

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_marketing_email_code_returns_404(self, mock_list, mock_detail, mock_raw):
        """营销邮件中的普通数字不应被当作成功验证码返回"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_list.return_value = {
            "success": True,
            "emails": [
                self._graph_email(
                    subject="Runpod - 50% OFF GPU Instances",
                    sender="marketing@runpod.io",
                )
            ],
        }
        # 关键：detail 的 subject 也要与 email 列表一致（营销主题）
        marketing_detail = {
            "id": "msg-1",
            "subject": "Runpod - 50% OFF GPU Instances",
            "from": {"emailAddress": {"address": "marketing@runpod.io"}},
            "toRecipients": [{"emailAddress": {"address": "user@outlook.com"}}],
            "receivedDateTime": self._utc_iso(),
            "body": {"content": "Save big on 1181 new GPU instances! Order now for $2999/month.", "contentType": "text"},
        }
        mock_detail.return_value = marketing_detail
        mock_raw.return_value = "RAW"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-code?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 404, "营销邮件数字不应返回 200 成功")
        self.assertEqual(resp.get_json().get("code"), "VERIFICATION_CODE_NOT_FOUND")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_marketing_email_link_returns_404(self, mock_list, mock_detail, mock_raw):
        """营销邮件中的普通链接不应被当作成功验证链接返回"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_list.return_value = {
            "success": True,
            "emails": [
                self._graph_email(
                    subject="Weekly Newsletter - Check out new features",
                    sender="news@example.com",
                )
            ],
        }
        mock_detail.return_value = {
            "id": "msg-1",
            "subject": "Weekly Newsletter - Check out new features",
            "from": {"emailAddress": {"address": "news@example.com"}},
            "toRecipients": [{"emailAddress": {"address": "user@outlook.com"}}],
            "receivedDateTime": self._utc_iso(),
            "body": {
                "content": "Read more at https://blog.example.com/latest-news and https://shop.example.com/deals",
                "contentType": "text",
            },
        }
        mock_raw.return_value = "RAW"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-link?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 404, "营销链接不应返回 200 成功")
        self.assertEqual(resp.get_json().get("code"), "VERIFICATION_LINK_NOT_FOUND")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_legit_verification_code_still_succeeds(self, mock_list, mock_detail, mock_raw):
        """标准验证码邮件仍可正常成功提取（高置信度 → 200 OK）"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_list.return_value = {
            "success": True,
            "emails": [self._graph_email(subject="Your verification code")],
        }
        mock_detail.return_value = self._graph_detail(
            body_text="Your verification code is 987654. Do not share this code.",
        )
        mock_raw.return_value = "RAW"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-code?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data["data"]["verification_code"], "987654")
        self.assertEqual(data["data"]["code_confidence"], "high")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_legit_verification_link_still_succeeds(self, mock_list, mock_detail, mock_raw):
        """标准验证链接邮件仍可正常成功提取（高置信度 → 200 OK）"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_list.return_value = {
            "success": True,
            "emails": [self._graph_email(subject="Confirm your email address")],
        }
        mock_detail.return_value = self._graph_detail(
            body_text="Click https://auth.example.com/verify?token=abc to confirm your email.",
        )
        mock_raw.return_value = "RAW"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-link?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("verify", data["data"]["verification_link"])
        self.assertEqual(data["data"]["link_confidence"], "high")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_low_confidence_code_response_includes_confidence_metadata(self, mock_list, mock_detail, mock_raw):
        """低置信度返回 404 时，仍可从错误中辨别原因（非邮件不存在，而是无可信结果）"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_list.return_value = {
            "success": True,
            "emails": [self._graph_email(subject="System Report")],
        }
        # 关键：detail 的 subject 也要是非验证码主题
        report_detail = {
            "id": "msg-1",
            "subject": "System Report",
            "from": {"emailAddress": {"address": "noreply@example.com"}},
            "toRecipients": [{"emailAddress": {"address": "user@outlook.com"}}],
            "receivedDateTime": self._utc_iso(),
            "body": {"content": "There are 445566 active users this quarter.", "contentType": "text"},
        }
        mock_detail.return_value = report_detail
        mock_raw.return_value = "RAW"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-code?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json().get("code"), "VERIFICATION_CODE_NOT_FOUND")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_code_with_custom_regex_still_returns_high_confidence(self, mock_list, mock_detail, mock_raw):
        """调用方传入 code_regex 精确匹配时，关键词命中仍返回 high confidence"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_list.return_value = {
            "success": True,
            "emails": [self._graph_email(subject="Your OTP code")],
        }
        mock_detail.return_value = self._graph_detail(
            body_text="Your OTP code is AB1234. Enter it within 5 minutes.",
        )
        mock_raw.return_value = "RAW"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-code?email={email_addr}&code_regex=%5Cb%5BA-Z0-9%5D%7B6%7D%5Cb",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["data"]["verification_code"], "AB1234")
        self.assertEqual(data["data"]["code_confidence"], "high")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_code_regex_without_keyword_context_still_succeeds(self, mock_list, mock_detail, mock_raw):
        """code_regex 精确匹配，邮件无验证码关键词 → 仍应返回 200"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_list.return_value = {
            "success": True,
            "emails": [self._graph_email(subject="Account notice")],
        }
        detail = {
            "id": "msg-1",
            "subject": "Account notice",
            "from": {"emailAddress": {"address": "noreply@example.com"}},
            "toRecipients": [{"emailAddress": {"address": "user@outlook.com"}}],
            "receivedDateTime": self._utc_iso(),
            "body": {"content": "Use AB1234 within 5 minutes to proceed.", "contentType": "text"},
        }
        mock_detail.return_value = detail
        mock_raw.return_value = "RAW"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-code?email={email_addr}&code_regex=%5Cb%5BA-Z%5D%7B2%7D%5Cd%7B4%7D%5Cb",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200, "code_regex 精确匹配不应被拦截")
        data = resp.get_json()
        self.assertEqual(data["data"]["verification_code"], "AB1234")
        self.assertEqual(data["data"]["code_confidence"], "high")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_opaque_verify_link_with_email_context_succeeds(self, mock_list, mock_detail, mock_raw):
        """URL 不含验证关键词但邮件正文有验证语境 → 应返回 200"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_list.return_value = {
            "success": True,
            "emails": [self._graph_email(subject="Please verify your account")],
        }
        detail = {
            "id": "msg-1",
            "subject": "Please verify your account",
            "from": {"emailAddress": {"address": "noreply@example.com"}},
            "toRecipients": [{"emailAddress": {"address": "user@outlook.com"}}],
            "receivedDateTime": self._utc_iso(),
            "body": {"content": "Click to verify your email: https://auth.example.com/t/abc123", "contentType": "text"},
        }
        mock_detail.return_value = detail
        mock_raw.return_value = "RAW"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-link?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200, "邮件正文有验证语境时不应拦截链接")
        data = resp.get_json()
        self.assertIn("auth.example.com", data["data"]["verification_link"])
        self.assertEqual(data["data"]["link_confidence"], "high")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_discount_code_email_link_returns_404(self, mock_list, mock_detail, mock_raw):
        """营销邮件正文含 'discount code' + 普通链接 → 不应被提权，应返回 404"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_list.return_value = {"success": True, "emails": [self._graph_email()]}
        detail = {
            "id": "msg-1",
            "subject": "Your exclusive discount code inside!",
            "from_address": "deals@shop.example.com",
            "content": "Use discount code SAVE20 at https://shop.example.com/checkout",
            "html_content": "",
            "received_at": "2026-03-08T12:00:00Z",
        }
        mock_detail.return_value = detail
        mock_raw.return_value = "RAW"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-link?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 404, "'discount code' 语境不应让普通链接通过门控")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_confirm_your_order_link_returns_404(self, mock_list, mock_detail, mock_raw):
        """'confirm your order' 不是验证语境 → 普通链接应返回 404"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_list.return_value = {"success": True, "emails": [self._graph_email()]}
        detail = {
            "id": "msg-1",
            "subject": "Please confirm your order",
            "from_address": "orders@shop.example.com",
            "content": "Click here to confirm your order: https://shop.example.com/orders/status/789",
            "html_content": "",
            "received_at": "2026-03-08T12:00:00Z",
        }
        mock_detail.return_value = detail
        mock_raw.return_value = "RAW"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-link?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 404, "'confirm your order' 不应让普通链接通过门控")


# ---------------------------------------------------------------------------
class ExternalApiRegressionExtendedTests(ExternalApiBaseTest):
    """TC-REG-02, TC-REG-05"""

    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_internal_email_detail_still_works(self, mock_list, mock_detail):
        """TC-REG-02: 旧邮件详情接口仍可用"""
        email_addr = self._insert_outlook_account()
        mock_list.return_value = {"success": True, "emails": [self._graph_email()]}
        mock_detail.return_value = self._graph_detail(body_text="detail body")

        client = self.app.test_client()
        self._login(client)

        resp = client.get(f"/api/email/{email_addr}/msg-1")

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))

    def test_settings_put_old_fields_only(self):
        """TC-REG-05: PUT /api/settings 只修改旧字段不影响 external_api_key"""
        self._set_external_api_key("my-secret-key")
        client = self.app.test_client()
        self._login(client)

        resp = client.put("/api/settings", json={"refresh_interval_days": 7})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

        # external_api_key 不应被清空
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            key = settings_repo.get_external_api_key()
            self.assertTrue(key, "external_api_key 不应被清空")


# ---------------------------------------------------------------------------
# TC-AUD-02, TC-AUD-03: 审计日志错误路径与敏感信息脱敏
# ---------------------------------------------------------------------------
class ExternalApiAuditTests(ExternalApiBaseTest):
    """TC-AUD-02, TC-AUD-03"""

    @patch("outlook_web.services.graph.get_emails_graph")
    def test_failed_api_call_also_logs_audit(self, mock_graph):
        """TC-AUD-02: 失败调用也写审计日志"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_graph.return_value = {"success": True, "emails": []}

        client = self.app.test_client()
        # 触发 MAIL_NOT_FOUND
        resp = client.get(
            f"/api/external/messages/latest?email={email_addr}",
            headers=self._auth_headers(),
        )
        self.assertEqual(resp.status_code, 404)

        audit_logs = self._external_audit_logs()
        self.assertGreaterEqual(len(audit_logs), 1)
        last_log = audit_logs[-1]
        details = json.loads(last_log["details"]) if isinstance(last_log["details"], str) else last_log["details"]
        self.assertEqual(details.get("code"), "MAIL_NOT_FOUND")

    def test_audit_logs_do_not_contain_api_key(self):
        """TC-AUD-03: 审计日志不包含明文 API Key"""
        self._set_external_api_key("super-secret-api-key-12345")
        client = self.app.test_client()

        resp = client.get("/api/external/health", headers=self._auth_headers("super-secret-api-key-12345"))
        self.assertEqual(resp.status_code, 200)

        audit_logs = self._external_audit_logs()
        for log in audit_logs:
            details_str = json.dumps(log) if isinstance(log, dict) else str(log)
            self.assertNotIn("super-secret-api-key-12345", details_str, "审计日志不应包含明文 API Key")


if __name__ == "__main__":
    unittest.main()


# ══════════════════════════════════════════════════════════════════════
# P1 安全守卫测试
# ══════════════════════════════════════════════════════════════════════


class ExternalApiGuardBaseTest(ExternalApiBaseTest):
    """P1 守卫测试基类：提供公网模式配置 helper。"""

    def setUp(self):
        super().setUp()
        # 确保默认关闭公网模式
        self._set_public_mode(False)
        self._set_ip_whitelist([])
        self._set_rate_limit(60)
        self._set_disable_feature("raw_content", False)
        self._set_disable_feature("wait_message", False)

    # ── helper ──

    def _set_public_mode(self, enabled: bool):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("external_api_public_mode", "true" if enabled else "false")

    def _set_ip_whitelist(self, ips: list):
        import json as _json

        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("external_api_ip_whitelist", _json.dumps(ips))

    def _set_rate_limit(self, limit: int):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("external_api_rate_limit_per_minute", str(limit))

    def _set_disable_feature(self, feature: str, disabled: bool):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting(f"external_api_disable_{feature}", "true" if disabled else "false")

    def _clear_rate_limits(self):
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            db.execute("DELETE FROM external_api_rate_limits")
            db.commit()


class GuardPublicModeOffTests(ExternalApiGuardBaseTest):
    """TC-GUARD-01~03: public_mode=false 时守卫完全透传。"""

    def test_guard_noop_when_private(self):
        """TC-GUARD-01: 私有模式下守卫不生效，请求正常通过"""
        self._set_external_api_key("abc123")
        self._set_public_mode(False)
        self._set_ip_whitelist(["10.0.0.1"])  # 故意设白名单，但私有模式不应检查
        client = self.app.test_client()
        resp = client.get("/api/external/health", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)

    def test_rate_limit_noop_when_private(self):
        """TC-GUARD-02: 私有模式下限流不生效"""
        self._set_external_api_key("abc123")
        self._set_public_mode(False)
        self._set_rate_limit(1)
        client = self.app.test_client()
        for _ in range(5):
            resp = client.get("/api/external/health", headers=self._auth_headers())
            self.assertEqual(resp.status_code, 200)

    def test_feature_disable_noop_when_private(self):
        """TC-GUARD-03: 私有模式下功能禁用不生效"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        self._set_public_mode(False)
        self._set_disable_feature("raw_content", True)
        self._set_disable_feature("wait_message", True)
        client = self.app.test_client()
        # raw 端点 → 应正常进入 controller（可能 404 找不到邮件，但不是 403）
        resp = client.get(
            f"/api/external/messages/fake-id/raw",
            headers=self._auth_headers(),
        )
        self.assertNotEqual(resp.status_code, 403)


class GuardIpWhitelistTests(ExternalApiGuardBaseTest):
    """TC-GUARD-04~07: IP 白名单功能。"""

    def test_ip_rejected_when_not_in_whitelist(self):
        """TC-GUARD-04: 公网模式 + IP 不在白名单 → 403 IP_NOT_ALLOWED"""
        self._set_external_api_key("abc123")
        self._set_public_mode(True)
        self._set_ip_whitelist(["10.0.0.1"])
        client = self.app.test_client()
        resp = client.get("/api/external/health", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertEqual(data["code"], "IP_NOT_ALLOWED")

    def test_ip_allowed_when_in_whitelist(self):
        """TC-GUARD-05: 公网模式 + IP 在白名单 → 正常通过"""
        self._set_external_api_key("abc123")
        self._set_public_mode(True)
        self._set_ip_whitelist(["127.0.0.1"])
        client = self.app.test_client()
        resp = client.get("/api/external/health", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)

    def test_empty_whitelist_allows_all(self):
        """TC-GUARD-06: 公网模式 + 白名单为空 → 不限制"""
        self._set_external_api_key("abc123")
        self._set_public_mode(True)
        self._set_ip_whitelist([])
        client = self.app.test_client()
        resp = client.get("/api/external/health", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)

    def test_cidr_whitelist(self):
        """TC-GUARD-07: CIDR 白名单匹配"""
        self._set_external_api_key("abc123")
        self._set_public_mode(True)
        self._set_ip_whitelist(["127.0.0.0/8"])
        client = self.app.test_client()
        resp = client.get("/api/external/health", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)

    def test_xff_ignored_when_proxy_not_trusted(self):
        """公网模式下：不信任代理时忽略 XFF，防止伪造绕过白名单"""
        import os

        old = os.environ.pop("TRUSTED_PROXIES", None)
        try:
            self._set_external_api_key("abc123")
            self._set_public_mode(True)
            # 只允许伪造的 XFF，但不允许真实 remote_addr(127.0.0.1)
            self._set_ip_whitelist(["10.0.0.1"])
            client = self.app.test_client()
            resp = client.get(
                "/api/external/health",
                headers={**self._auth_headers(), "X-Forwarded-For": "10.0.0.1"},
            )
            self.assertEqual(resp.status_code, 403)
            data = resp.get_json()
            self.assertEqual(data["code"], "IP_NOT_ALLOWED")
        finally:
            if old is not None:
                os.environ["TRUSTED_PROXIES"] = old

    def test_xff_honored_when_proxy_trusted(self):
        """公网模式下：来自受信任代理时可使用 XFF 进行白名单判断"""
        import os

        old = os.environ.get("TRUSTED_PROXIES")
        os.environ["TRUSTED_PROXIES"] = "127.0.0.1"
        try:
            self._set_external_api_key("abc123")
            self._set_public_mode(True)
            self._set_ip_whitelist(["10.0.0.1"])
            client = self.app.test_client()
            resp = client.get(
                "/api/external/health",
                headers={**self._auth_headers(), "X-Forwarded-For": "10.0.0.1"},
            )
            self.assertEqual(resp.status_code, 200)
        finally:
            if old is None:
                os.environ.pop("TRUSTED_PROXIES", None)
            else:
                os.environ["TRUSTED_PROXIES"] = old


class GuardFeatureDisableTests(ExternalApiGuardBaseTest):
    """TC-GUARD-08~11: 高风险接口禁用。"""

    def test_raw_disabled(self):
        """TC-GUARD-08: 公网模式 + raw 禁用 → 403 FEATURE_DISABLED"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        self._set_public_mode(True)
        self._set_ip_whitelist(["127.0.0.1"])
        self._set_disable_feature("raw_content", True)
        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages/fake-id/raw",
            headers=self._auth_headers(),
        )
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertEqual(data["code"], "FEATURE_DISABLED")
        self.assertIn("raw_content", data.get("data", {}).get("feature", ""))

    def test_wait_message_disabled(self):
        """TC-GUARD-09: 公网模式 + wait-message 禁用 → 403"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        self._set_public_mode(True)
        self._set_ip_whitelist(["127.0.0.1"])
        self._set_disable_feature("wait_message", True)
        client = self.app.test_client()
        resp = client.get(
            f"/api/external/wait-message?email={email_addr}",
            headers=self._auth_headers(),
        )
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertEqual(data["code"], "FEATURE_DISABLED")

    def test_raw_allowed_when_not_disabled(self):
        """TC-GUARD-10: 公网模式 + raw 未禁用 → 正常进入 controller"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        self._set_public_mode(True)
        self._set_ip_whitelist(["127.0.0.1"])
        self._set_disable_feature("raw_content", False)
        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages/fake-id/raw",
            headers=self._auth_headers(),
        )
        # 不是 403 FEATURE_DISABLED（可能是 404/500 等取决于后续逻辑）
        self.assertNotEqual(resp.status_code, 403)

    def test_wait_message_allowed_when_not_disabled(self):
        """TC-GUARD-11: 公网模式 + wait-message 未禁用 → 正常进入"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        self._set_public_mode(True)
        self._set_ip_whitelist(["127.0.0.1"])
        self._set_disable_feature("wait_message", False)
        client = self.app.test_client()
        resp = client.get(
            f"/api/external/wait-message?email={email_addr}",
            headers=self._auth_headers(),
        )
        self.assertNotEqual(resp.status_code, 403)


class GuardRateLimitTests(ExternalApiGuardBaseTest):
    """TC-GUARD-12~14: 限流功能。"""

    def test_rate_limit_exceeded(self):
        """TC-GUARD-12: 公网模式 + 超限 → 429 RATE_LIMIT_EXCEEDED"""
        self._set_external_api_key("abc123")
        self._set_public_mode(True)
        self._set_ip_whitelist(["127.0.0.1"])
        self._set_rate_limit(3)
        self._clear_rate_limits()
        client = self.app.test_client()
        results = []
        for _ in range(5):
            resp = client.get("/api/external/health", headers=self._auth_headers())
            results.append(resp.status_code)
        # 前 3 次应该通过（200），之后应该是 429
        self.assertTrue(any(s == 429 for s in results), f"预期至少一个 429，实际: {results}")
        # 检查 429 响应内容
        last_429 = [r for r in range(5) if results[r] == 429]
        if last_429:
            resp = client.get("/api/external/health", headers=self._auth_headers())
            if resp.status_code == 429:
                data = resp.get_json()
                self.assertEqual(data["code"], "RATE_LIMIT_EXCEEDED")

    def test_rate_limit_not_exceeded(self):
        """TC-GUARD-13: 公网模式 + 未超限 → 正常通过"""
        self._set_external_api_key("abc123")
        self._set_public_mode(True)
        self._set_ip_whitelist(["127.0.0.1"])
        self._set_rate_limit(100)
        self._clear_rate_limits()
        client = self.app.test_client()
        for _ in range(5):
            resp = client.get("/api/external/health", headers=self._auth_headers())
            self.assertEqual(resp.status_code, 200)

    def test_rate_limit_response_structure(self):
        """TC-GUARD-14: 429 响应包含 limit/current/ip"""
        self._set_external_api_key("abc123")
        self._set_public_mode(True)
        self._set_ip_whitelist(["127.0.0.1"])
        self._set_rate_limit(1)
        self._clear_rate_limits()
        client = self.app.test_client()
        client.get("/api/external/health", headers=self._auth_headers())
        resp = client.get("/api/external/health", headers=self._auth_headers())
        if resp.status_code == 429:
            data = resp.get_json()
            err_data = data.get("data", {})
            self.assertIn("limit", err_data)
            self.assertIn("current", err_data)
            self.assertIn("ip", err_data)


class GuardCapabilitiesTests(ExternalApiGuardBaseTest):
    """TC-GUARD-15~16: capabilities 端点 P1 增强。"""

    def test_capabilities_private_mode(self):
        """TC-GUARD-15: 私有模式 capabilities 不含 restricted_features"""
        self._set_external_api_key("abc123")
        self._set_public_mode(False)
        client = self.app.test_client()
        resp = client.get("/api/external/capabilities", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertFalse(data.get("public_mode", False))

    def test_capabilities_public_mode_with_disabled(self):
        """TC-GUARD-16: 公网模式 + 功能禁用 → restricted_features 列出禁用项"""
        self._set_external_api_key("abc123")
        self._set_public_mode(True)
        self._set_ip_whitelist(["127.0.0.1"])
        self._set_disable_feature("raw_content", True)
        self._set_disable_feature("wait_message", True)
        client = self.app.test_client()
        resp = client.get("/api/external/capabilities", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertTrue(data.get("public_mode"))
        restricted = data.get("restricted_features", [])
        self.assertIn("raw_content", restricted)
        self.assertIn("wait_message", restricted)


class GuardSettingsApiTests(ExternalApiGuardBaseTest):
    """TC-GUARD-17~18: P1 设置读写。"""

    def test_get_settings_contains_p1_fields(self):
        """TC-GUARD-17: GET /api/settings 包含 P1 字段"""
        with self.app.test_client() as client:
            self._login(client)
            resp = client.get("/api/settings")
            self.assertEqual(resp.status_code, 200)
            s = resp.get_json()["settings"]
            self.assertIn("external_api_public_mode", s)
            self.assertIn("external_api_ip_whitelist", s)
            self.assertIn("external_api_rate_limit_per_minute", s)
            self.assertIn("external_api_disable_raw_content", s)
            self.assertIn("external_api_disable_wait_message", s)

    def test_update_p1_settings(self):
        """TC-GUARD-18: PUT /api/settings 可更新 P1 字段"""
        with self.app.test_client() as client:
            self._login(client)
            # 获取 CSRF token
            csrf_resp = client.get("/api/csrf-token")
            csrf_token = csrf_resp.get_json().get("csrf_token", "")
            resp = client.put(
                "/api/settings",
                json={
                    "external_api_public_mode": True,
                    "external_api_ip_whitelist": ["10.0.0.1", "192.168.0.0/16"],
                    "external_api_rate_limit_per_minute": 30,
                    "external_api_disable_raw_content": True,
                    "external_api_disable_wait_message": True,
                },
                headers={"X-CSRFToken": csrf_token},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["success"])
            # 验证设置已保存
            resp2 = client.get("/api/settings")
            s = resp2.get_json()["settings"]
            self.assertTrue(s["external_api_public_mode"])
            self.assertEqual(s["external_api_ip_whitelist"], ["10.0.0.1", "192.168.0.0/16"])
            self.assertEqual(s["external_api_rate_limit_per_minute"], 30)
            self.assertTrue(s["external_api_disable_raw_content"])
            self.assertTrue(s["external_api_disable_wait_message"])


# ======================================================================
# P2 异步探测 (probe) 测试
# ======================================================================


class ExternalApiProbeBaseTest(ExternalApiBaseTest):
    """P2 探测测试基类。"""

    def setUp(self):
        super().setUp()
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.repositories import settings as settings_repo

            db = get_db()
            db.execute("DELETE FROM external_probe_cache")
            db.commit()
            # 确保公网模式关闭，避免 P1 守卫干扰
            settings_repo.set_setting("external_api_public_mode", "false")
            settings_repo.set_setting("external_api_disable_wait_message", "false")
            settings_repo.set_setting("external_api_disable_raw_content", "false")


class ProbeCreateTests(ExternalApiProbeBaseTest):
    """TC-PROBE-01~04: 创建异步探测。"""

    def test_create_probe_async(self):
        """TC-PROBE-01: mode=async 创建探测返回 202 + probe_id"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        client = self.app.test_client()
        resp = client.get(
            f"/api/external/wait-message?email={email_addr}&mode=async&timeout_seconds=30",
            headers=self._auth_headers(),
        )
        self.assertEqual(resp.status_code, 202)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("probe_id", data["data"])
        self.assertEqual(data["data"]["status"], "pending")
        self.assertIn("poll_url", data["data"])

    def test_create_probe_invalid_email(self):
        """TC-PROBE-02: 不存在的邮箱 → 404"""
        self._set_external_api_key("abc123")
        client = self.app.test_client()
        resp = client.get(
            "/api/external/wait-message?email=nonexist@test.com&mode=async",
            headers=self._auth_headers(),
        )
        self.assertEqual(resp.status_code, 404)

    def test_create_probe_invalid_timeout(self):
        """TC-PROBE-03: 无效 timeout → 400"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        client = self.app.test_client()
        resp = client.get(
            f"/api/external/wait-message?email={email_addr}&mode=async&timeout_seconds=999",
            headers=self._auth_headers(),
        )
        self.assertEqual(resp.status_code, 400)

    def test_sync_mode_still_works(self):
        """TC-PROBE-04: mode=sync（默认）保持阻塞等待行为"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        client = self.app.test_client()
        # sync 模式超时会返回 404 MAIL_NOT_FOUND
        resp = client.get(
            f"/api/external/wait-message?email={email_addr}&timeout_seconds=1&poll_interval=1",
            headers=self._auth_headers(),
        )
        self.assertIn(resp.status_code, [404, 502])  # MAIL_NOT_FOUND or upstream error


class ProbeStatusTests(ExternalApiProbeBaseTest):
    """TC-PROBE-05~08: 查询探测状态。"""

    def test_get_probe_status_pending(self):
        """TC-PROBE-05: 新建探测状态为 pending"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        client = self.app.test_client()
        # 创建
        resp = client.get(
            f"/api/external/wait-message?email={email_addr}&mode=async&timeout_seconds=60",
            headers=self._auth_headers(),
        )
        probe_id = resp.get_json()["data"]["probe_id"]
        # 查询
        resp2 = client.get(
            f"/api/external/probe/{probe_id}",
            headers=self._auth_headers(),
        )
        self.assertEqual(resp2.status_code, 200)
        data = resp2.get_json()["data"]
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["probe_id"], probe_id)

    def test_get_probe_status_not_found(self):
        """TC-PROBE-06: 不存在的 probe_id → 404"""
        self._set_external_api_key("abc123")
        client = self.app.test_client()
        resp = client.get(
            "/api/external/probe/nonexist123",
            headers=self._auth_headers(),
        )
        self.assertEqual(resp.status_code, 404)

    def test_probe_requires_auth(self):
        """TC-PROBE-07: 查询探测需要 API Key"""
        self._set_external_api_key("abc123")
        client = self.app.test_client()
        resp = client.get("/api/external/probe/some-id")
        self.assertEqual(resp.status_code, 401)

    def test_probe_status_contains_email(self):
        """TC-PROBE-08: 探测状态包含邮箱地址"""
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        client = self.app.test_client()
        resp = client.get(
            f"/api/external/wait-message?email={email_addr}&mode=async&timeout_seconds=60",
            headers=self._auth_headers(),
        )
        probe_id = resp.get_json()["data"]["probe_id"]
        resp2 = client.get(f"/api/external/probe/{probe_id}", headers=self._auth_headers())
        data = resp2.get_json()["data"]
        self.assertEqual(data["email"], email_addr)


class ProbePollTests(ExternalApiProbeBaseTest):
    """TC-PROBE-09~12: 后台探测轮询逻辑。"""

    def test_poll_marks_expired_as_timeout(self):
        """TC-PROBE-09: 过期的 pending 探测被标记为 timeout"""
        from datetime import datetime, timedelta, timezone

        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            past = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
            db.execute(
                """INSERT INTO external_probe_cache
                   (id, email_addr, status, timeout_seconds, poll_interval, expires_at, created_at, updated_at)
                   VALUES (?, ?, 'pending', 30, 5, ?, ?, ?)""",
                ("expired-probe-1", email_addr, past, past, past),
            )
            db.commit()

        with self.app.app_context():
            from outlook_web.services.external_api import poll_pending_probes

            poll_pending_probes()

        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            row = db.execute("SELECT status FROM external_probe_cache WHERE id = ?", ("expired-probe-1",)).fetchone()
            self.assertEqual(row["status"], "timeout")

    def test_poll_matches_new_email(self):
        """TC-PROBE-10: 后台轮询命中新邮件时标记为 matched"""
        from datetime import datetime, timedelta, timezone
        from unittest.mock import patch

        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")

        now = datetime.now(timezone.utc)
        future = (now + timedelta(seconds=120)).isoformat()
        now_iso = now.isoformat()

        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            db.execute(
                """INSERT INTO external_probe_cache
                   (id, email_addr, status, timeout_seconds, poll_interval, expires_at, created_at, updated_at)
                   VALUES (?, ?, 'pending', 60, 5, ?, ?, ?)""",
                ("match-probe-1", email_addr, future, now_iso, now_iso),
            )
            db.commit()

        mock_msg = {
            "id": "msg-new",
            "subject": "Code 123456",
            "timestamp": int(now.timestamp()) + 1,
            "method": "graph",
        }
        with self.app.app_context():
            with patch("outlook_web.services.external_api.get_latest_message_for_external", return_value=mock_msg):
                from outlook_web.services.external_api import poll_pending_probes

                poll_pending_probes()

        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            row = db.execute("SELECT * FROM external_probe_cache WHERE id = ?", ("match-probe-1",)).fetchone()
            self.assertEqual(row["status"], "matched")
            self.assertIn("msg-new", row["result_json"])

    def test_cleanup_old_probes(self):
        """TC-PROBE-11: cleanup 清理过期已完成探测"""
        from datetime import datetime, timedelta, timezone

        email_addr = self._insert_outlook_account()
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            old = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
            db.execute(
                """INSERT INTO external_probe_cache
                   (id, email_addr, status, timeout_seconds, poll_interval, expires_at, created_at, updated_at)
                   VALUES (?, ?, 'timeout', 30, 5, ?, ?, ?)""",
                ("old-probe-1", email_addr, old, old, old),
            )
            db.commit()

        with self.app.app_context():
            from outlook_web.services.external_api import cleanup_expired_probes

            deleted = cleanup_expired_probes(max_age_minutes=30)
            self.assertGreaterEqual(deleted, 1)

        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            row = db.execute("SELECT * FROM external_probe_cache WHERE id = ?", ("old-probe-1",)).fetchone()
            self.assertIsNone(row)

    def test_poll_handles_upstream_error(self):
        """TC-PROBE-12: 轮询中上游错误标记为 error"""
        from datetime import datetime, timedelta, timezone
        from unittest.mock import patch

        email_addr = self._insert_outlook_account()

        now = datetime.now(timezone.utc)
        future = (now + timedelta(seconds=120)).isoformat()
        now_iso = now.isoformat()

        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            db.execute(
                """INSERT INTO external_probe_cache
                   (id, email_addr, status, timeout_seconds, poll_interval, expires_at, created_at, updated_at)
                   VALUES (?, ?, 'pending', 60, 5, ?, ?, ?)""",
                ("error-probe-1", email_addr, future, now_iso, now_iso),
            )
            db.commit()

        with self.app.app_context():
            with patch(
                "outlook_web.services.external_api.get_latest_message_for_external", side_effect=RuntimeError("Network down")
            ):
                from outlook_web.services.external_api import poll_pending_probes

                poll_pending_probes()

        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            row = db.execute("SELECT * FROM external_probe_cache WHERE id = ?", ("error-probe-1",)).fetchone()
            self.assertEqual(row["status"], "error")
            self.assertIn("Network down", row["error_message"])
