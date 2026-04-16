from __future__ import annotations

import unittest

from tests._import_app import import_web_app_module


class PoolServiceProjectReuseTests(unittest.TestCase):
    """覆盖 docs/TDD/2026-04-16-邮箱池项目维度成功复用TDD.md 中的 Service 级核心用例。"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            account_columns = [row[1] for row in db.execute("PRAGMA table_info(accounts)").fetchall()]
            if "claimed_project_key" not in account_columns:
                db.execute("ALTER TABLE accounts ADD COLUMN claimed_project_key TEXT DEFAULT NULL")
            usage_columns = [row[1] for row in db.execute("PRAGMA table_info(account_project_usage)").fetchall()]
            if "first_success_at" not in usage_columns:
                db.execute("ALTER TABLE account_project_usage ADD COLUMN first_success_at TEXT DEFAULT NULL")
            if "last_success_at" not in usage_columns:
                db.execute("ALTER TABLE account_project_usage ADD COLUMN last_success_at TEXT DEFAULT NULL")
            if "success_count" not in usage_columns:
                db.execute("ALTER TABLE account_project_usage ADD COLUMN success_count INTEGER NOT NULL DEFAULT 0")
            db.execute("DELETE FROM account_claim_logs")
            db.execute("DELETE FROM account_project_usage")
            db.execute("DELETE FROM accounts")
            db.commit()

    def _insert_claimed_account(
        self,
        *,
        email: str,
        provider: str = "outlook",
        account_type: str = "outlook",
        claim_token: str,
        claimed_by: str,
        claimed_project_key: str | None,
    ) -> int:
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            db.execute(
                """
                INSERT INTO accounts (
                    email, client_id, refresh_token, status,
                    account_type, provider, group_id, pool_status,
                    claim_token, claimed_by, claimed_at, lease_expires_at,
                    claimed_project_key, email_domain
                )
                VALUES (?, 'cid', 'rt', 'active',
                        ?, ?, 1, 'claimed',
                        ?, ?, '2026-04-16T10:00:00Z', '2026-04-16T10:10:00Z',
                        ?, ?)
                """,
                (
                    email,
                    account_type,
                    provider,
                    claim_token,
                    claimed_by,
                    claimed_project_key,
                    email.rsplit("@", 1)[-1].lower(),
                ),
            )
            db.commit()
            row = db.execute("SELECT id FROM accounts WHERE email = ?", (email,)).fetchone()
            return int(row["id"])

    def test_complete_claim_uses_claimed_project_key_without_api_project_key(self):
        account_id = self._insert_claimed_account(
            email="svc-reuse@example.com",
            claim_token="clm_svc_reuse",
            claimed_by="svc_bot:task_1",
            claimed_project_key="project_alpha",
        )

        with self.app.app_context():
            from outlook_web.services import pool as pool_service

            new_status = pool_service.complete_claim(
                account_id=account_id,
                claim_token="clm_svc_reuse",
                caller_id="svc_bot",
                task_id="task_1",
                result="success",
            )

        self.assertEqual(new_status, "available")

    def test_complete_claim_without_claimed_project_key_falls_back_to_old_behavior(self):
        account_id = self._insert_claimed_account(
            email="svc-old@example.com",
            claim_token="clm_svc_old",
            claimed_by="svc_bot:task_2",
            claimed_project_key=None,
        )

        with self.app.app_context():
            from outlook_web.services import pool as pool_service

            new_status = pool_service.complete_claim(
                account_id=account_id,
                claim_token="clm_svc_old",
                caller_id="svc_bot",
                task_id="task_2",
                result="success",
            )

        self.assertEqual(new_status, "used")

    def test_complete_claim_cloudflare_temp_mail_stays_on_old_semantics(self):
        account_id = self._insert_claimed_account(
            email="svc-cf@example.com",
            provider="cloudflare_temp_mail",
            account_type="temp_mail",
            claim_token="clm_svc_cf",
            claimed_by="svc_bot:task_3",
            claimed_project_key="project_cf",
        )

        with self.app.app_context():
            from outlook_web.services import pool as pool_service

            new_status = pool_service.complete_claim(
                account_id=account_id,
                claim_token="clm_svc_cf",
                caller_id="svc_bot",
                task_id="task_3",
                result="success",
            )

        self.assertEqual(new_status, "used")

    def test_claim_random_blank_project_key_treated_as_old_behavior(self):
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.services import pool as pool_service
            from outlook_web.services.pool import PoolServiceError

            db = get_db()
            db.execute("""
                INSERT INTO accounts (
                    email, client_id, refresh_token, status,
                    account_type, provider, group_id, pool_status, email_domain
                )
                VALUES ('svc-blank@example.com', 'cid', 'rt', 'active', 'outlook', 'outlook', 1, 'available', 'example.com')
                """)
            db.commit()

            account = pool_service.claim_random(
                caller_id="svc_bot",
                task_id="blank_project_task",
                project_key="   ",
                email_domain="example.com",
            )
            self.assertEqual(account["email"], "svc-blank@example.com")

            with self.assertRaises(PoolServiceError) as ctx:
                pool_service.complete_claim(
                    account_id=account["id"],
                    claim_token="wrong_token",
                    caller_id="svc_bot",
                    task_id="blank_project_task",
                    result="success",
                )
            self.assertEqual(ctx.exception.error_code, "token_mismatch")

    def test_complete_claim_preserves_invalid_result_validation(self):
        account_id = self._insert_claimed_account(
            email="svc-invalid-result@example.com",
            claim_token="clm_invalid_result",
            claimed_by="svc_bot:task_4",
            claimed_project_key="project_invalid",
        )

        with self.app.app_context():
            from outlook_web.services import pool as pool_service
            from outlook_web.services.pool import PoolServiceError

            with self.assertRaises(PoolServiceError) as ctx:
                pool_service.complete_claim(
                    account_id=account_id,
                    claim_token="clm_invalid_result",
                    caller_id="svc_bot",
                    task_id="task_4",
                    result="not_supported",
                )
            self.assertEqual(ctx.exception.error_code, "invalid_result")

    def test_complete_claim_preserves_token_mismatch_validation(self):
        account_id = self._insert_claimed_account(
            email="svc-token-mismatch@example.com",
            claim_token="clm_token_mismatch",
            claimed_by="svc_bot:task_5",
            claimed_project_key="project_alpha",
        )

        with self.app.app_context():
            from outlook_web.services import pool as pool_service
            from outlook_web.services.pool import PoolServiceError

            with self.assertRaises(PoolServiceError) as ctx:
                pool_service.complete_claim(
                    account_id=account_id,
                    claim_token="wrong_token",
                    caller_id="svc_bot",
                    task_id="task_5",
                    result="success",
                )
            self.assertEqual(ctx.exception.error_code, "token_mismatch")


if __name__ == "__main__":
    unittest.main()
