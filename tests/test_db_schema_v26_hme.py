import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tests._import_app import import_web_app_module


class DbSchemaV26HmeTests(unittest.TestCase):
    """验证旧临时邮箱记录升级到 HME Provider schema。"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()

    def test_v26_adds_hme_columns_and_backfills_provider_name(self):
        with tempfile.TemporaryDirectory(prefix="outlookEmail-v26-hme-") as tmp:
            db_path = Path(tmp) / "legacy_v25.db"
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute("""
                    CREATE TABLE settings (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """)
                conn.execute("INSERT INTO settings (key, value) VALUES ('db_schema_version', '25')")
                conn.execute("""
                    CREATE TABLE temp_emails (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        email TEXT UNIQUE NOT NULL,
                        status TEXT DEFAULT 'active',
                        mailbox_type TEXT NOT NULL DEFAULT 'user',
                        visible_in_ui INTEGER NOT NULL DEFAULT 1,
                        source TEXT NOT NULL DEFAULT 'custom_domain_temp_mail',
                        prefix TEXT,
                        domain TEXT,
                        meta_json TEXT
                    )
                    """)
                conn.execute(
                    """
                    INSERT INTO temp_emails (email, source, meta_json)
                    VALUES (?, ?, ?)
                    """,
                    (
                        "legacy-alias@icloud.com",
                        "custom_domain_temp_mail",
                        json.dumps({"provider_name": "icloud_hme"}),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            from outlook_web.db import init_db

            init_db(database_path=str(db_path))

            conn = sqlite3.connect(str(db_path))
            try:
                columns = [row[1] for row in conn.execute("PRAGMA table_info(temp_emails)").fetchall()]
                self.assertIn("provider_name", columns)
                self.assertIn("claimed_project_key", columns)
                self.assertIn("success_count", columns)
                self.assertIn("fail_count", columns)
                provider_row = conn.execute(
                    "SELECT provider_name FROM temp_emails WHERE email = ?",
                    ("legacy-alias@icloud.com",),
                ).fetchone()
                self.assertEqual(provider_row[0], "icloud_hme")
                usage_table = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'temp_email_project_usage'"
                ).fetchone()
                self.assertIsNotNone(usage_table)
                schema_version = conn.execute("SELECT value FROM settings WHERE key = 'db_schema_version'").fetchone()
                self.assertEqual(schema_version[0], "26")
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
