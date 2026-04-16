from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from tests._import_app import import_web_app_module


class DbSchemaV22PoolProjectReuseTests(unittest.TestCase):
    """覆盖 docs/TDD/2026-04-16-邮箱池项目维度成功复用TDD.md 中的迁移测试。"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()

    def _seed_legacy_v21_db(self, db_path: Path) -> None:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('db_schema_version', '21')")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    client_id TEXT NOT NULL,
                    refresh_token TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    account_type TEXT DEFAULT 'outlook',
                    provider TEXT DEFAULT 'outlook',
                    group_id INTEGER,
                    pool_status TEXT DEFAULT NULL,
                    email_domain TEXT DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS account_project_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    consumer_key TEXT NOT NULL,
                    project_key TEXT NOT NULL,
                    first_claimed_at TEXT NOT NULL,
                    last_claimed_at TEXT NOT NULL,
                    UNIQUE(account_id, consumer_key, project_key)
                )
                """)

            conn.execute("""
                INSERT INTO accounts (
                    email, client_id, refresh_token, status, account_type, provider, group_id, pool_status, email_domain
                ) VALUES
                    ('legacy_outlook@example.com', 'cid', 'rt', 'active', 'outlook', 'outlook', 1, 'used', 'example.com'),
                    ('legacy_cf@example.com', 'cid', 'rt', 'active', 'temp_mail', 'cloudflare_temp_mail', 1, 'used', 'example.com')
                """)
            conn.execute("""
                INSERT INTO account_project_usage (
                    account_id, consumer_key, project_key, first_claimed_at, last_claimed_at
                )
                VALUES (1, 'legacy_bot', 'legacy_project', '2026-04-15T10:00:00Z', '2026-04-15T10:05:00Z')
                """)
            conn.commit()
        finally:
            conn.close()

    def test_init_db_v22_adds_accounts_claimed_project_key_column(self):
        with tempfile.TemporaryDirectory(prefix="outlookEmail-v22-") as tmp:
            db_path = Path(tmp) / "legacy_v21.db"
            self._seed_legacy_v21_db(db_path)

            from outlook_web.db import init_db

            init_db(database_path=str(db_path))

            conn = sqlite3.connect(str(db_path))
            try:
                columns = [row[1] for row in conn.execute("PRAGMA table_info(accounts)").fetchall()]
                self.assertIn("claimed_project_key", columns)
            finally:
                conn.close()

    def test_init_db_v22_adds_account_project_usage_success_columns(self):
        with tempfile.TemporaryDirectory(prefix="outlookEmail-v22-") as tmp:
            db_path = Path(tmp) / "legacy_v21.db"
            self._seed_legacy_v21_db(db_path)

            from outlook_web.db import init_db

            init_db(database_path=str(db_path))

            conn = sqlite3.connect(str(db_path))
            try:
                columns = [row[1] for row in conn.execute("PRAGMA table_info(account_project_usage)").fetchall()]
                self.assertIn("first_success_at", columns)
                self.assertIn("last_success_at", columns)
                self.assertIn("success_count", columns)
            finally:
                conn.close()

    def test_init_db_v22_moves_historical_long_lived_used_accounts_back_to_available(self):
        with tempfile.TemporaryDirectory(prefix="outlookEmail-v22-") as tmp:
            db_path = Path(tmp) / "legacy_v21.db"
            self._seed_legacy_v21_db(db_path)

            from outlook_web.db import init_db

            init_db(database_path=str(db_path))

            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute("SELECT pool_status FROM accounts WHERE email = 'legacy_outlook@example.com'").fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], "available")
            finally:
                conn.close()

    def test_init_db_v22_keeps_cloudflare_temp_mail_out_of_long_lived_migration_scope(self):
        with tempfile.TemporaryDirectory(prefix="outlookEmail-v22-") as tmp:
            db_path = Path(tmp) / "legacy_v21.db"
            self._seed_legacy_v21_db(db_path)

            from outlook_web.db import init_db

            init_db(database_path=str(db_path))

            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute("SELECT pool_status FROM accounts WHERE email = 'legacy_cf@example.com'").fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], "used")
            finally:
                conn.close()

    def test_init_db_v22_does_not_backfill_success_count_from_legacy_claim_trace_rows(self):
        with tempfile.TemporaryDirectory(prefix="outlookEmail-v22-") as tmp:
            db_path = Path(tmp) / "legacy_v21.db"
            self._seed_legacy_v21_db(db_path)

            from outlook_web.db import init_db

            init_db(database_path=str(db_path))

            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute("""
                    SELECT first_success_at, last_success_at, success_count
                    FROM account_project_usage
                    WHERE consumer_key = 'legacy_bot' AND project_key = 'legacy_project'
                    """).fetchone()
                self.assertIsNotNone(row)
                self.assertIsNone(row[0])
                self.assertIsNone(row[1])
                self.assertEqual(row[2], 0)
            finally:
                conn.close()

    def test_init_db_v22_allows_claiming_migrated_long_lived_account(self):
        with tempfile.TemporaryDirectory(prefix="outlookEmail-v22-") as tmp:
            db_path = Path(tmp) / "legacy_v21.db"
            self._seed_legacy_v21_db(db_path)

            from outlook_web.db import create_sqlite_connection, init_db
            from outlook_web.repositories import pool as pool_repo

            init_db(database_path=str(db_path))

            conn = create_sqlite_connection(str(db_path))
            try:
                account = pool_repo.claim_atomic(
                    conn,
                    caller_id="migration_bot",
                    task_id="migration_task_1",
                    lease_seconds=600,
                    project_key="project_after_migration",
                    email_domain="example.com",
                )
                self.assertIsNotNone(account)
                self.assertEqual(account["email"], "legacy_outlook@example.com")
            finally:
                conn.close()

    def test_init_db_v22_allows_original_project_to_claim_migrated_account_once(self):
        with tempfile.TemporaryDirectory(prefix="outlookEmail-v22-") as tmp:
            db_path = Path(tmp) / "legacy_v21.db"
            self._seed_legacy_v21_db(db_path)

            from outlook_web.db import create_sqlite_connection, init_db
            from outlook_web.repositories import pool as pool_repo

            init_db(database_path=str(db_path))

            conn = create_sqlite_connection(str(db_path))
            try:
                account = pool_repo.claim_atomic(
                    conn,
                    caller_id="legacy_bot",
                    task_id="migration_task_2",
                    lease_seconds=600,
                    project_key="legacy_project",
                    email_domain="example.com",
                )
                self.assertIsNotNone(account)
                self.assertEqual(account["email"], "legacy_outlook@example.com")
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
