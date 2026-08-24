import json
import secrets
import unittest
from unittest.mock import Mock, patch

from tests._import_app import import_web_app_module


class TempMailboxPoolTests(unittest.TestCase):
    """临时邮箱（temp_emails 表）接入邮箱池的领取/释放/完成链路测试（Issue #85）。"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        from outlook_web.db import create_sqlite_connection
        from outlook_web.repositories import pool as pool_repo
        from outlook_web.services import pool as pool_service

        cls.pool_repo = pool_repo
        cls.pool_service = pool_service
        cls.create_conn = staticmethod(lambda: create_sqlite_connection())

    def setUp(self):
        # 与共享临时 DB 的其它用例隔离：清理 accounts + temp_emails 池状态
        conn = self.create_conn()
        try:
            conn.execute("DELETE FROM account_project_usage")
            conn.execute("DELETE FROM account_claim_logs")
            conn.execute("DELETE FROM accounts")
            conn.execute("DELETE FROM temp_emails")
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        conn = self.create_conn()
        try:
            conn.execute("DELETE FROM temp_emails")
            conn.commit()
        finally:
            conn.close()

    def _make_temp_email(self, source="custom_domain_temp_mail", domain=None):
        # 每个邮箱使用唯一 domain，便于用 email_domain 过滤确定性领取
        if domain is None:
            domain = f"d{secrets.token_hex(4)}.test"
        conn = self.create_conn()
        try:
            local = f"u{secrets.token_hex(4)}"
            email = f"{local}@{domain}"
            conn.execute(
                """
                INSERT INTO temp_emails (email, status, mailbox_type, source, prefix, domain)
                VALUES (?, 'active', 'user', ?, ?, ?)
                """,
                (email, source, local, domain),
            )
            conn.commit()
            row = conn.execute("SELECT id FROM temp_emails WHERE email = ?", (email,)).fetchone()
            return row["id"], email, domain
        finally:
            conn.close()

    def _make_plugin_email(self, provider_name="plugin_provider", domain="plugin.test"):
        temp_id, email, _ = self._make_temp_email(domain=domain)
        conn = self.create_conn()
        try:
            conn.execute(
                "UPDATE temp_emails SET meta_json = ? WHERE id = ?",
                (json.dumps({"provider_name": provider_name}), temp_id),
            )
            conn.commit()
        finally:
            conn.close()
        return temp_id, email, domain

    @staticmethod
    def _fake_plugin_result(email, provider_name="plugin_provider"):
        return {
            "success": True,
            "email": email,
            "meta": {
                "provider_name": provider_name,
                "provider_mailbox_id": f"mailbox-{email.split('@', 1)[0]}",
            },
        }

    def _make_legacy_null_domain_email(self, domain):
        # 模拟老库：active 临时邮箱但 domain/prefix 为 NULL（v24 之前入库）
        conn = self.create_conn()
        try:
            local = f"legacy{secrets.token_hex(4)}"
            email = f"{local}@{domain}"
            conn.execute(
                """
                INSERT INTO temp_emails (email, status, mailbox_type, source, prefix, domain)
                VALUES (?, 'active', 'user', 'custom_domain_temp_mail', NULL, NULL)
                """,
                (email,),
            )
            conn.commit()
            row = conn.execute("SELECT id FROM temp_emails WHERE email = ?", (email,)).fetchone()
            return row["id"], email
        finally:
            conn.close()

    def test_claim_random_domain_filter_matches_null_domain_row(self):
        # 回归 (Issue #85 审查)：domain 为 NULL 的历史行按 email_domain 领取时不应漏掉
        domain = f"legacy{secrets.token_hex(4)}.test"
        temp_id, email = self._make_legacy_null_domain_email(domain)
        result = self.pool_service.claim_random(
            caller_id="reg_bot", task_id="t_null_dom", provider="custom", email_domain=domain
        )
        self.assertEqual(result["email"], email)
        self.assertEqual(result["id"], temp_id + self.pool_repo.TEMP_POOL_ID_OFFSET)

    def test_claim_random_custom_claims_temp_mailbox(self):
        temp_id, email, domain = self._make_temp_email()
        result = self.pool_service.claim_random(caller_id="reg_bot", task_id="t_claim", provider="custom", email_domain=domain)
        self.assertEqual(result["email"], email)
        self.assertEqual(result["id"], temp_id + self.pool_repo.TEMP_POOL_ID_OFFSET)
        self.assertTrue(result["claim_token"].startswith("clm_"))

        conn = self.create_conn()
        try:
            row = conn.execute("SELECT pool_status, claim_token FROM temp_emails WHERE id = ?", (temp_id,)).fetchone()
            self.assertEqual(row["pool_status"], "claimed")
            self.assertEqual(row["claim_token"], result["claim_token"])
        finally:
            conn.close()

    def test_claim_random_provider_none_claims_temp_mailbox(self):
        temp_id, email, domain = self._make_temp_email()
        result = self.pool_service.claim_random(caller_id="reg_bot", task_id="t_none", email_domain=domain)
        self.assertTrue(self.pool_repo.is_temp_pool_account_id(result["id"]))

    def test_claim_random_outlook_does_not_touch_temp(self):
        # 制造一个可用临时邮箱（唯一 domain），provider=outlook 不应回退到临时邮箱池
        _, _, domain = self._make_temp_email()
        with self.assertRaises(self.pool_service.PoolServiceError) as ctx:
            self.pool_service.claim_random(caller_id="reg_bot", task_id="t_outlook", provider="outlook", email_domain=domain)
        self.assertEqual(ctx.exception.error_code, "no_available_account")

    def test_claim_random_unspecified_provider_can_claim_plugin_mailbox(self):
        temp_id, email, domain = self._make_plugin_email()
        result = self.pool_service.claim_random(
            caller_id="reg_bot",
            task_id="t_unspecified_plugin",
            email_domain=domain,
        )
        self.assertEqual(result["id"], temp_id + self.pool_repo.TEMP_POOL_ID_OFFSET)
        self.assertEqual(result["email"], email)
        self.assertEqual(result["provider"], "plugin_provider")
        self.assertEqual(result["account_type"], "temp_mail")

    def test_claim_registered_plugin_uses_bounded_sql_query(self):
        temp_id, email, _ = self._make_plugin_email()
        conn = self.create_conn()
        statements: list[str] = []
        try:
            conn.set_trace_callback(statements.append)
            claimed = self.pool_repo.claim_temp_mailbox_atomic(
                conn,
                caller_id="reg_bot",
                task_id="t_bounded_query",
                lease_seconds=600,
                provider="plugin_provider",
            )
        finally:
            conn.set_trace_callback(None)
            conn.close()

        self.assertEqual(claimed["id"], temp_id + self.pool_repo.TEMP_POOL_ID_OFFSET)
        self.assertEqual(claimed["email"], email)
        claim_sql = next(statement for statement in statements if "SELECT * FROM temp_emails" in statement)
        self.assertIn("json_valid", claim_sql)
        self.assertIn("LIMIT 1", claim_sql)

    def test_claim_random_registered_plugin_selects_existing_mailbox(self):
        temp_id, email, _ = self._make_plugin_email()
        with patch(
            "outlook_web.services.temp_mail_provider_factory.get_available_providers",
            return_value=[{"name": "plugin_provider"}],
        ):
            result = self.pool_service.claim_random(
                caller_id="reg_bot",
                task_id="t_existing_plugin",
                provider="plugin_provider",
            )

        self.assertEqual(result["id"], temp_id + self.pool_repo.TEMP_POOL_ID_OFFSET)
        self.assertEqual(result["email"], email)
        self.assertEqual(result["provider"], "plugin_provider")
        self.assertEqual(result["account_type"], "temp_mail")

    def test_claim_random_registered_plugin_creates_generic_temp_mailbox(self):
        provider = Mock()
        provider.provider_capabilities = {"delete_mailbox": True}
        provider.create_mailbox.return_value = self._fake_plugin_result("new-mailbox@plugin.test")
        with (
            patch(
                "outlook_web.services.temp_mail_provider_factory.get_available_providers",
                return_value=[{"name": "plugin_provider"}],
            ),
            patch(
                "outlook_web.services.temp_mail_provider_factory.get_temp_mail_provider",
                return_value=provider,
            ),
        ):
            result = self.pool_service.claim_random(
                caller_id="reg_bot",
                task_id="t_plugin_create",
                provider="plugin_provider",
                project_key="project-a",
            )

        self.assertEqual(result["provider"], "plugin_provider")
        self.assertEqual(result["account_type"], "temp_mail")
        self.assertEqual(result["email"], "new-mailbox@plugin.test")

        conn = self.create_conn()
        try:
            row = conn.execute(
                "SELECT source, meta_json, pool_status FROM temp_emails WHERE email = ?",
                ("new-mailbox@plugin.test",),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["source"], "custom_domain_temp_mail")
        self.assertEqual(json.loads(row["meta_json"])["provider_name"], "plugin_provider")
        self.assertEqual(row["pool_status"], "claimed")

        self.assertEqual(
            self.pool_service.complete_claim(
                account_id=result["id"],
                claim_token=result["claim_token"],
                caller_id="reg_bot",
                task_id="t_plugin_create",
                result="success",
            ),
            "used",
        )

    def test_registered_plugin_insert_failure_rolls_back_remote_mailbox(self):
        provider = Mock()
        provider.provider_capabilities = {"delete_mailbox": True}
        provider.create_mailbox.return_value = self._fake_plugin_result("rollback@plugin.test")
        with (
            patch(
                "outlook_web.services.temp_mail_provider_factory.get_available_providers",
                return_value=[{"name": "plugin_provider"}],
            ),
            patch(
                "outlook_web.services.temp_mail_provider_factory.get_temp_mail_provider",
                return_value=provider,
            ),
            patch.object(
                self.pool_repo,
                "insert_claimed_temp_mailbox",
                side_effect=self.pool_repo.PoolRepositoryError("write failed", "db_error"),
            ),
        ):
            with self.assertRaises(self.pool_service.PoolServiceError) as ctx:
                self.pool_service.claim_random(
                    caller_id="reg_bot",
                    task_id="t_plugin_rollback",
                    provider="plugin_provider",
                )

        self.assertEqual(ctx.exception.error_code, "db_error")
        provider.delete_mailbox.assert_called_once()

    def test_registered_plugin_without_delete_capability_skips_rollback(self):
        provider = Mock()
        provider.provider_capabilities = {"delete_mailbox": False}
        provider.create_mailbox.return_value = self._fake_plugin_result("keep@plugin.test")
        with (
            patch(
                "outlook_web.services.temp_mail_provider_factory.get_available_providers",
                return_value=[{"name": "plugin_provider"}],
            ),
            patch(
                "outlook_web.services.temp_mail_provider_factory.get_temp_mail_provider",
                return_value=provider,
            ),
            patch.object(
                self.pool_repo,
                "insert_claimed_temp_mailbox",
                side_effect=self.pool_repo.PoolRepositoryError("write failed", "db_error"),
            ),
        ):
            with self.assertRaises(self.pool_service.PoolServiceError):
                self.pool_service.claim_random(
                    caller_id="reg_bot",
                    task_id="t_plugin_no_delete",
                    provider="plugin_provider",
                )

        provider.delete_mailbox.assert_not_called()

    def test_release_temp_mailbox(self):
        _, _, domain = self._make_temp_email()
        claimed = self.pool_service.claim_random(caller_id="reg_bot", task_id="t_rel", provider="custom", email_domain=domain)
        self.pool_service.release_claim(
            account_id=claimed["id"],
            claim_token=claimed["claim_token"],
            caller_id="reg_bot",
            task_id="t_rel",
        )
        temp_id = self.pool_repo.temp_id_from_account_id(claimed["id"])
        conn = self.create_conn()
        try:
            row = conn.execute("SELECT pool_status, claim_token FROM temp_emails WHERE id = ?", (temp_id,)).fetchone()
            self.assertEqual(row["pool_status"], "available")
            self.assertIsNone(row["claim_token"])
        finally:
            conn.close()

    def test_complete_temp_mailbox_success(self):
        _, _, domain = self._make_temp_email()
        claimed = self.pool_service.claim_random(caller_id="reg_bot", task_id="t_done", provider="custom", email_domain=domain)
        new_status = self.pool_service.complete_claim(
            account_id=claimed["id"],
            claim_token=claimed["claim_token"],
            caller_id="reg_bot",
            task_id="t_done",
            result="success",
        )
        self.assertEqual(new_status, "used")
        temp_id = self.pool_repo.temp_id_from_account_id(claimed["id"])
        conn = self.create_conn()
        try:
            row = conn.execute("SELECT pool_status, last_result FROM temp_emails WHERE id = ?", (temp_id,)).fetchone()
            self.assertEqual(row["pool_status"], "used")
            self.assertEqual(row["last_result"], "success")
        finally:
            conn.close()

    def test_complete_temp_mailbox_token_mismatch(self):
        _, _, domain = self._make_temp_email()
        claimed = self.pool_service.claim_random(caller_id="reg_bot", task_id="t_mm", provider="custom", email_domain=domain)
        with self.assertRaises(self.pool_service.PoolServiceError) as ctx:
            self.pool_service.complete_claim(
                account_id=claimed["id"],
                claim_token="clm_wrong",
                caller_id="reg_bot",
                task_id="t_mm",
                result="success",
            )
        self.assertEqual(ctx.exception.error_code, "token_mismatch")

    def test_get_claim_context_resolves_temp(self):
        _, _, domain = self._make_temp_email()
        claimed = self.pool_service.claim_random(caller_id="reg_bot", task_id="t_ctx", provider="custom", email_domain=domain)
        conn = self.create_conn()
        try:
            ctx = self.pool_repo.get_claim_context(conn, claimed["claim_token"])
        finally:
            conn.close()
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx["account_id"], claimed["id"])
        self.assertEqual(ctx["email"], claimed["email"])

    def test_expire_and_recover_temp(self):
        _, _, domain = self._make_temp_email()
        # 领取并将租约设为已过期
        claimed = self.pool_service.claim_random(caller_id="reg_bot", task_id="t_exp", provider="custom", email_domain=domain)
        temp_id = self.pool_repo.temp_id_from_account_id(claimed["id"])
        conn = self.create_conn()
        try:
            conn.execute(
                "UPDATE temp_emails SET lease_expires_at = '2000-01-01T00:00:00Z' WHERE id = ?",
                (temp_id,),
            )
            conn.commit()
            expired = self.pool_repo.expire_stale_temp_claims(conn)
            self.assertGreaterEqual(expired, 1)
            row = conn.execute("SELECT pool_status, updated_at FROM temp_emails WHERE id = ?", (temp_id,)).fetchone()
            self.assertEqual(row["pool_status"], "cooldown")
            # 冷却结束后恢复
            conn.execute(
                "UPDATE temp_emails SET updated_at = '2000-01-01T00:00:00Z' WHERE id = ?",
                (temp_id,),
            )
            conn.commit()
            recovered = self.pool_repo.recover_cooldown_temp(conn, cooldown_seconds=60)
            self.assertGreaterEqual(recovered, 1)
            row2 = conn.execute("SELECT pool_status FROM temp_emails WHERE id = ?", (temp_id,)).fetchone()
            self.assertEqual(row2["pool_status"], "available")
        finally:
            conn.close()

    def test_stats_includes_temp(self):
        self._make_temp_email()
        stats = self.pool_service.get_pool_stats()
        self.assertGreaterEqual(stats["pool_counts"]["available"], 1)


if __name__ == "__main__":
    unittest.main()
