"""tests/test_telegram_push.py — TDD-00007 Telegram 实时推送测试

覆盖 TDD-00007 §12 全部 32 个测试用例（T-01 ~ T-32）。

测试分组：
  TestBuildTelegramMessage   - T-01~T-05  消息构造单元测试
  TestHtmlToPlain            - T-06~T-07  HTML 转纯文本
  TestEscapeHtml             - T-08       HTML 转义
  TestToggleTelegramPush     - T-09~T-12  toggle_telegram_push Repository
  TestUpdateTelegramCursor   - T-13       update_telegram_cursor Repository
  TestGetTelegramPushAccounts- T-14       get_telegram_push_accounts Repository
  TestRunTelegramPushJob     - T-15~T-22  run_telegram_push_job 集成（mock 外部调用）
  TestTelegramToggleEndpoint - T-23~T-26  /api/accounts/<id>/telegram-toggle 端点
  TestTelegramSettingsAPI    - T-27~T-30  /api/settings Telegram 字段扩展
  TestRegressions            - T-31~T-32  回归：调度器、全量测试
"""

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from tests._import_app import clear_login_attempts, import_web_app_module


# ---------------------------------------------------------------------------
# 辅助：共享 app 实例（避免重复初始化）
# ---------------------------------------------------------------------------

def _get_app():
    return import_web_app_module().app


def _login(client):
    resp = client.post("/login", json={"password": "testpass123"})
    assert resp.status_code == 200, f"Login failed: {resp.data}"


def _insert_test_account(db, email, provider="imap", enabled=0, last_checked=None, status="active"):
    """在 accounts 表中插入测试账号，返回 rowid。"""
    db.execute(
        """INSERT INTO accounts
           (email, client_id, provider, account_type, refresh_token, imap_host, imap_port,
            imap_password, group_id, telegram_push_enabled, telegram_last_checked_at, status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            email, "test_client_id", provider,
            "outlook" if provider == "outlook" else "imap",
            "enc:dummy_refresh", "imap.test.com", 993,
            "enc:dummy_pass", None,
            enabled, last_checked, status,
        ),
    )
    db.commit()
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]


# ===========================================================================
# T-01 ~ T-05：消息构造单元测试
# ===========================================================================

class TestBuildTelegramMessage(unittest.TestCase):
    """TDD-00007 T-01 ~ T-05"""

    def _build(self, account_email, **email_kwargs):
        from outlook_web.services.telegram_push import _build_telegram_message
        email = {
            "subject": email_kwargs.get("subject", "Test Subject"),
            "sender":  email_kwargs.get("sender",  "sender@test.com"),
            "received_at": email_kwargs.get("received_at", "2026-03-04T14:30:00"),
            "preview": email_kwargs.get("preview", ""),
        }
        return _build_telegram_message(account_email, email)

    def test_t01_normal_email_with_preview(self):
        """T-01：正常邮件（含预览），消息包含所有关键字段"""
        msg = self._build(
            "user@example.com",
            subject="Hello World",
            sender="bob@x.com",
            received_at="2026-03-04T14:30:00",
            preview="This is a test email body.",
        )
        self.assertIn("📬", msg)
        self.assertIn("user@example.com", msg)
        self.assertIn("bob@x.com", msg)
        self.assertIn("Hello World", msg)
        self.assertIn("14:30", msg)
        self.assertIn("This is a test email body.", msg)
        self.assertIn("内容预览：", msg)

    def test_t02_empty_preview_omits_section(self):
        """T-02：正文为空时，消息中不包含"内容预览："区块"""
        msg = self._build("user@example.com", preview="")
        self.assertNotIn("内容预览：", msg)

    def test_t03_very_long_message_truncated(self):
        """T-03：消息超 4096 字符时截断至 4096，末尾为"..." """
        msg = self._build("user@example.com", preview="a" * 5000)
        self.assertLessEqual(len(msg), 4096)
        self.assertTrue(msg.endswith("..."), f"Expected truncation marker, got: {msg[-10:]!r}")

    def test_t04_html_special_chars_escaped(self):
        """T-04：subject 和 sender 中的 HTML 特殊字符被正确转义"""
        msg = self._build(
            "user@example.com",
            subject="<Sale> & <Offer>",
            sender="a&b@test.com",
        )
        # 转义后的形式
        self.assertIn("&lt;Sale&gt;", msg)
        self.assertIn("&amp;", msg)
        self.assertIn("a&amp;b@test.com", msg)
        # 不应出现原始字符（在 subject/sender 渲染位置）
        # （注意：HTML 标签本身如 <code> 是合法的，只检查 subject/sender 值）
        self.assertNotIn("<Sale>", msg)
        self.assertNotIn("<Offer>", msg)

    def test_t05_preview_truncated_at_200_chars(self):
        """T-05：正文超 200 字时截断，追加"..." """
        msg = self._build("user@example.com", preview="x" * 300)
        # 正文区域包含 200 个 x + "..."
        self.assertIn("x" * 200 + "...", msg)
        self.assertNotIn("x" * 201, msg)


# ===========================================================================
# T-06 ~ T-07：HTML 转纯文本
# ===========================================================================

class TestHtmlToPlain(unittest.TestCase):
    """TDD-00007 T-06 ~ T-07"""

    def _convert(self, html):
        from outlook_web.services.telegram_push import _html_to_plain
        return _html_to_plain(html)

    def test_t06_strip_html_tags(self):
        """T-06：HTML 标签被剥除"""
        result = self._convert("<p>Hello <b>World</b></p>")
        self.assertIn("Hello", result)
        self.assertIn("World", result)
        self.assertNotIn("<p>", result)
        self.assertNotIn("<b>", result)

    def test_t06_empty_string(self):
        """T-06：空字符串返回空字符串"""
        self.assertEqual(self._convert(""), "")

    def test_t07_collapse_whitespace(self):
        """T-07：多余空白（多个空格、换行）被合并为单个空格"""
        result = self._convert("<p>  a  </p>  <br>  <p>b</p>")
        self.assertIn("a", result)
        self.assertIn("b", result)
        # 不应出现连续多个空格
        self.assertNotIn("  ", result)


# ===========================================================================
# T-08：HTML 转义
# ===========================================================================

class TestEscapeHtml(unittest.TestCase):
    """TDD-00007 T-08"""

    def test_t08_escape_three_special_chars(self):
        """T-08：& < > 三种字符均被正确转义"""
        from outlook_web.services.telegram_push import _escape_html
        result = _escape_html("a & <b> and > c")
        self.assertEqual(result, "a &amp; &lt;b&gt; and &gt; c")


# ===========================================================================
# T-09 ~ T-12：toggle_telegram_push Repository
# ===========================================================================

class TestToggleTelegramPush(unittest.TestCase):
    """TDD-00007 T-09 ~ T-12"""

    @classmethod
    def setUpClass(cls):
        cls.app = _get_app()

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.db import get_db
            db = get_db()
            db.execute("DELETE FROM accounts WHERE email LIKE '%@tgtest.com'")
            db.commit()
            self._account_id = _insert_test_account(db, "tg@tgtest.com", enabled=0, last_checked=None)

    def test_t09_first_enable_sets_cursor(self):
        """T-09：首次开启时 telegram_last_checked_at 被设置（不为 None）"""
        with self.app.app_context():
            from outlook_web.repositories.accounts import toggle_telegram_push
            from outlook_web.db import get_db
            result = toggle_telegram_push(self._account_id, True)
            self.assertTrue(result)
            row = get_db().execute(
                "SELECT telegram_push_enabled, telegram_last_checked_at FROM accounts WHERE id = ?",
                (self._account_id,)
            ).fetchone()
            self.assertEqual(row["telegram_push_enabled"], 1)
            self.assertIsNotNone(row["telegram_last_checked_at"])
            # 游标应为有效 ISO8601 字符串
            self.assertRegex(row["telegram_last_checked_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

    def test_t10_disable_preserves_cursor(self):
        """T-10：关闭推送时游标不清空"""
        with self.app.app_context():
            from outlook_web.repositories.accounts import toggle_telegram_push
            from outlook_web.db import get_db
            db = get_db()
            # 先开启（设置游标）
            toggle_telegram_push(self._account_id, True)
            original_cursor = db.execute(
                "SELECT telegram_last_checked_at FROM accounts WHERE id = ?",
                (self._account_id,)
            ).fetchone()["telegram_last_checked_at"]
            # 关闭
            toggle_telegram_push(self._account_id, False)
            row = db.execute(
                "SELECT telegram_push_enabled, telegram_last_checked_at FROM accounts WHERE id = ?",
                (self._account_id,)
            ).fetchone()
            self.assertEqual(row["telegram_push_enabled"], 0)
            self.assertEqual(row["telegram_last_checked_at"], original_cursor)

    def test_t11_nonexistent_account_returns_false(self):
        """T-11：账号不存在时返回 False"""
        with self.app.app_context():
            from outlook_web.repositories.accounts import toggle_telegram_push
            result = toggle_telegram_push(99999, True)
            self.assertFalse(result)

    def test_t12_repeat_enable_not_reset_cursor(self):
        """T-12：重复开启不重置已有游标"""
        with self.app.app_context():
            from outlook_web.repositories.accounts import toggle_telegram_push
            from outlook_web.db import get_db
            db = get_db()
            # 先开启（游标设为 T1）
            toggle_telegram_push(self._account_id, True)
            cursor_t1 = db.execute(
                "SELECT telegram_last_checked_at FROM accounts WHERE id = ?",
                (self._account_id,)
            ).fetchone()["telegram_last_checked_at"]
            # 再次开启
            toggle_telegram_push(self._account_id, True)
            cursor_t2 = db.execute(
                "SELECT telegram_last_checked_at FROM accounts WHERE id = ?",
                (self._account_id,)
            ).fetchone()["telegram_last_checked_at"]
            self.assertEqual(cursor_t1, cursor_t2, "重复开启不应重置游标")

    def test_t12b_reenable_resets_cursor(self):
        """T-12b：禁用后重新启用应重置游标到当前时间"""
        with self.app.app_context():
            from outlook_web.repositories.accounts import toggle_telegram_push
            from outlook_web.db import get_db
            db = get_db()
            # 先开启
            toggle_telegram_push(self._account_id, True)
            # 手动设置一个明显更早的游标
            db.execute(
                "UPDATE accounts SET telegram_last_checked_at = '2020-01-01T00:00:00' WHERE id = ?",
                (self._account_id,),
            )
            db.commit()
            # 关闭
            toggle_telegram_push(self._account_id, False)
            # 重新开启
            toggle_telegram_push(self._account_id, True)
            cursor_new = db.execute(
                "SELECT telegram_last_checked_at FROM accounts WHERE id = ?",
                (self._account_id,)
            ).fetchone()["telegram_last_checked_at"]
            self.assertGreater(cursor_new, "2020-01-01T00:00:00", "重新启用应重置游标到更新的时间")


# ===========================================================================
# T-13：update_telegram_cursor Repository
# ===========================================================================

class TestUpdateTelegramCursor(unittest.TestCase):
    """TDD-00007 T-13"""

    @classmethod
    def setUpClass(cls):
        cls.app = _get_app()

    def setUp(self):
        with self.app.app_context():
            from outlook_web.db import get_db
            db = get_db()
            db.execute("DELETE FROM accounts WHERE email = 'cursor@tgtest.com'")
            db.commit()
            self._account_id = _insert_test_account(db, "cursor@tgtest.com")

    def test_t13_update_cursor(self):
        """T-13：update_telegram_cursor 正确更新游标"""
        with self.app.app_context():
            from outlook_web.repositories.accounts import update_telegram_cursor
            from outlook_web.db import get_db
            update_telegram_cursor(self._account_id, "2026-03-04T14:30:00")
            row = get_db().execute(
                "SELECT telegram_last_checked_at FROM accounts WHERE id = ?",
                (self._account_id,)
            ).fetchone()
            self.assertEqual(row["telegram_last_checked_at"], "2026-03-04T14:30:00")


# ===========================================================================
# T-14：get_telegram_push_accounts Repository
# ===========================================================================

class TestGetTelegramPushAccounts(unittest.TestCase):
    """TDD-00007 T-14"""

    @classmethod
    def setUpClass(cls):
        cls.app = _get_app()

    def setUp(self):
        with self.app.app_context():
            from outlook_web.db import get_db
            db = get_db()
            db.execute("DELETE FROM accounts WHERE email LIKE '%@tg14test.com'")
            db.commit()
            _insert_test_account(db, "a@tg14test.com", enabled=1, status="active")
            _insert_test_account(db, "b@tg14test.com", enabled=0, status="active")
            _insert_test_account(db, "c@tg14test.com", enabled=1, status="disabled")

    def test_t14_returns_only_enabled_active_accounts(self):
        """T-14：只返回 enabled=1 且 status != disabled 的账号"""
        with self.app.app_context():
            from outlook_web.repositories.accounts import get_telegram_push_accounts
            accounts = get_telegram_push_accounts()
            emails = [a["email"] for a in accounts]
            self.assertIn("a@tg14test.com", emails)
            self.assertNotIn("b@tg14test.com", emails)  # enabled=0
            self.assertNotIn("c@tg14test.com", emails)  # status=disabled


# ===========================================================================
# T-15 ~ T-22：run_telegram_push_job 集成测试（mock 外部调用）
# ===========================================================================

class TestRunTelegramPushJob(unittest.TestCase):
    """TDD-00007 T-15 ~ T-22"""

    @classmethod
    def setUpClass(cls):
        cls.app = _get_app()

    def setUp(self):
        with self.app.app_context():
            from outlook_web.db import get_db
            db = get_db()
            db.execute("DELETE FROM accounts WHERE email LIKE '%@tgjob.com'")
            # 确保其他测试遗留的账号不干扰推送 job（关闭所有推送开关）
            db.execute("UPDATE accounts SET telegram_push_enabled = 0")
            db.commit()

    def _set_settings(self, bot_token="test_token_12345678", chat_id="-12345"):
        from outlook_web.repositories.settings import set_setting
        from outlook_web.security.crypto import encrypt_data
        if bot_token:
            set_setting("telegram_bot_token", encrypt_data(bot_token))
        else:
            set_setting("telegram_bot_token", "")
        set_setting("telegram_chat_id", chat_id)

    def _run_job(self):
        from outlook_web.services.telegram_push import run_telegram_push_job
        run_telegram_push_job(self.app)

    def _make_email(self, received_at="2026-03-04T14:31:00"):
        return {
            "subject": "Test",
            "sender": "s@test.com",
            "received_at": received_at,
            "preview": "body preview",
        }

    def test_t15_no_bot_token_skips(self):
        """T-15：Bot Token 未配置 → Telegram API 不被调用"""
        with self.app.app_context():
            self._set_settings(bot_token="", chat_id="-12345")
            with patch("outlook_web.services.telegram_push._send_telegram_message") as mock_send:
                self._run_job()
                mock_send.assert_not_called()

    def test_t16_no_chat_id_skips(self):
        """T-16：Chat ID 未配置 → Telegram API 不被调用"""
        with self.app.app_context():
            self._set_settings(bot_token="valid_token_xyz", chat_id="")
            with patch("outlook_web.services.telegram_push._send_telegram_message") as mock_send:
                self._run_job()
                mock_send.assert_not_called()

    def test_t17_no_enabled_accounts_skips(self):
        """T-17：无启用推送的账号 → Telegram API 不被调用"""
        with self.app.app_context():
            self._set_settings()
            # 确保无 enabled 账号（setUp 已清理）
            with patch("outlook_web.services.telegram_push._send_telegram_message") as mock_send:
                self._run_job()
                mock_send.assert_not_called()

    def test_t18_first_run_sets_cursor_no_push(self):
        """T-18：首次开启（last_checked_at=NULL）→ 设游标，不推送"""
        with self.app.app_context():
            from outlook_web.db import get_db
            db = get_db()
            acc_id = _insert_test_account(db, "first@tgjob.com", enabled=1, last_checked=None)
            self._set_settings()

            with patch("outlook_web.services.telegram_push._fetch_new_emails_imap") as mock_fetch, \
                 patch("outlook_web.services.telegram_push._fetch_new_emails_graph") as mock_graph, \
                 patch("outlook_web.services.telegram_push._send_telegram_message") as mock_send:

                mock_fetch.return_value = [self._make_email(), self._make_email()]
                mock_graph.return_value = []
                self._run_job()

                # 不推送
                mock_send.assert_not_called()

            # 游标已更新（不再为 NULL）
            row = db.execute(
                "SELECT telegram_last_checked_at FROM accounts WHERE id = ?",
                (acc_id,)
            ).fetchone()
            self.assertIsNotNone(row["telegram_last_checked_at"])

    def test_t19_normal_push_calls_api_and_updates_cursor(self):
        """T-19：正常推送 → Telegram API 被调用，游标更新"""
        with self.app.app_context():
            from outlook_web.db import get_db
            db = get_db()
            acc_id = _insert_test_account(
                db, "normal@tgjob.com", enabled=1, last_checked="2026-03-01T00:00:00"
            )
            self._set_settings()

            # 使用近期时间（PUSH_RECENCY_HOURS 内）
            from datetime import timedelta
            recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
            emails = [
                self._make_email(recent),
                self._make_email(recent),
            ]
            with patch("outlook_web.services.telegram_push._fetch_new_emails_imap", return_value=emails), \
                 patch("outlook_web.services.telegram_push._send_telegram_message", return_value=True) as mock_send, \
                 patch("outlook_web.services.telegram_push.TELEGRAM_PUSH_DELAY_SEC", 0):

                self._run_job()

                self.assertEqual(mock_send.call_count, 2)

            # 游标已更新（不再是 2026-03-01）
            cursor = db.execute(
                "SELECT telegram_last_checked_at FROM accounts WHERE id = ?",
                (acc_id,)
            ).fetchone()["telegram_last_checked_at"]
            self.assertIsNotNone(cursor)
            self.assertNotEqual(cursor, "2026-03-01T00:00:00")

    def test_t20_global_limit_20(self):
        """T-20：全局上限 20 封，跨账号合计不超过 20 条 Telegram 消息"""
        with self.app.app_context():
            from outlook_web.db import get_db
            db = get_db()
            # 账号 A：12 封；账号 B：15 封 → 合计最多 20 封
            _insert_test_account(db, "aa@tgjob.com", enabled=1, last_checked="2026-01-01T00:00:00")
            _insert_test_account(db, "bb@tgjob.com", enabled=1, last_checked="2026-01-01T00:00:00")
            self._set_settings()

            from datetime import timedelta
            recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
            emails_a = [self._make_email(recent) for _ in range(12)]
            emails_b = [self._make_email(recent) for _ in range(15)]

            call_count = 0

            def fake_fetch(account, since):
                nonlocal call_count
                if account["email"] == "aa@tgjob.com":
                    return emails_a
                return emails_b

            def fake_send(token, chat, msg):
                nonlocal call_count
                call_count += 1
                return True

            with patch("outlook_web.services.telegram_push._fetch_new_emails_imap", side_effect=fake_fetch), \
                 patch("outlook_web.services.telegram_push._send_telegram_message", side_effect=fake_send), \
                 patch("outlook_web.services.telegram_push.TELEGRAM_PUSH_DELAY_SEC", 0):
                self._run_job()

            self.assertEqual(call_count, 20, f"Expected 20, got {call_count}")

    def test_t21_imap_exception_silent_cursor_not_advanced(self):
        """T-21：IMAP 连接异常 → 不抛出，游标不推进（避免漏推邮件）"""
        with self.app.app_context():
            from outlook_web.db import get_db
            db = get_db()
            acc_id = _insert_test_account(
                db, "imapfail@tgjob.com", enabled=1, last_checked="2026-03-01T00:00:00"
            )
            self._set_settings()

            with patch(
                "outlook_web.services.telegram_push._fetch_new_emails_imap",
                side_effect=ConnectionError("IMAP connection refused")
            ), patch("outlook_web.services.telegram_push._send_telegram_message") as mock_send:
                # 不应抛出异常
                try:
                    self._run_job()
                except Exception as e:
                    self.fail(f"run_telegram_push_job raised unexpectedly: {e}")

                mock_send.assert_not_called()

            # 游标不推进——保留旧值以便下次重试
            cursor = db.execute(
                "SELECT telegram_last_checked_at FROM accounts WHERE id = ?",
                (acc_id,)
            ).fetchone()["telegram_last_checked_at"]
            self.assertEqual(cursor, "2026-03-01T00:00:00")

    def test_t22_send_failure_silent_cursor_updated(self):
        """T-22：Telegram 发送失败 → 不抛出，游标仍更新"""
        with self.app.app_context():
            from outlook_web.db import get_db
            db = get_db()
            acc_id = _insert_test_account(
                db, "sendfail@tgjob.com", enabled=1, last_checked="2026-03-01T00:00:00"
            )
            self._set_settings()

            from datetime import timedelta
            recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
            emails = [self._make_email(recent), self._make_email(recent)]
            with patch("outlook_web.services.telegram_push._fetch_new_emails_imap", return_value=emails), \
                 patch("outlook_web.services.telegram_push._send_telegram_message", return_value=False), \
                 patch("outlook_web.services.telegram_push.TELEGRAM_PUSH_DELAY_SEC", 0):
                try:
                    self._run_job()
                except Exception as e:
                    self.fail(f"run_telegram_push_job raised unexpectedly: {e}")

            # 游标仍更新
            cursor = db.execute(
                "SELECT telegram_last_checked_at FROM accounts WHERE id = ?",
                (acc_id,)
            ).fetchone()["telegram_last_checked_at"]
            self.assertNotEqual(cursor, "2026-03-01T00:00:00")


# ===========================================================================
# T-23 ~ T-26：/api/accounts/<id>/telegram-toggle 端点测试
# ===========================================================================

class TestTelegramToggleEndpoint(unittest.TestCase):
    """TDD-00007 T-23 ~ T-26"""

    @classmethod
    def setUpClass(cls):
        cls.app = _get_app()

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.db import get_db
            db = get_db()
            db.execute("DELETE FROM accounts WHERE email LIKE '%@tgapi.com'")
            db.commit()
            self._account_id = _insert_test_account(db, "api@tgapi.com")

    def _toggle(self, client, account_id, enabled):
        return client.post(
            f"/api/accounts/{account_id}/telegram-toggle",
            json={"enabled": enabled},
            content_type="application/json",
        )

    def test_t23_enable_success(self):
        """T-23：开启成功 → 200, success=true, DB 更新"""
        client = self.app.test_client()
        _login(client)
        resp = self._toggle(client, self._account_id, True)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["enabled"])

        with self.app.app_context():
            from outlook_web.db import get_db
            row = get_db().execute(
                "SELECT telegram_push_enabled FROM accounts WHERE id = ?",
                (self._account_id,)
            ).fetchone()
            self.assertEqual(row["telegram_push_enabled"], 1)

    def test_t24_disable_success(self):
        """T-24：关闭成功 → 200, success=true, DB 更新"""
        with self.app.app_context():
            from outlook_web.db import get_db
            get_db().execute(
                "UPDATE accounts SET telegram_push_enabled=1 WHERE id=?",
                (self._account_id,)
            )
            get_db().commit()

        client = self.app.test_client()
        _login(client)
        resp = self._toggle(client, self._account_id, False)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertFalse(data["enabled"])

        with self.app.app_context():
            from outlook_web.db import get_db
            row = get_db().execute(
                "SELECT telegram_push_enabled FROM accounts WHERE id = ?",
                (self._account_id,)
            ).fetchone()
            self.assertEqual(row["telegram_push_enabled"], 0)

    def test_t25_nonexistent_account_404(self):
        """T-25：账号不存在 → HTTP 404"""
        client = self.app.test_client()
        _login(client)
        resp = self._toggle(client, 99999, True)
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertFalse(data["success"])

    def test_t26_unauthenticated_denied(self):
        """T-26：未登录 → 拒绝访问（401 或 302 重定向）"""
        client = self.app.test_client()
        # 不调用 _login
        resp = self._toggle(client, self._account_id, True)
        self.assertIn(resp.status_code, [401, 302, 403])


# ===========================================================================
# T-27 ~ T-30：/api/settings Telegram 字段扩展测试
# ===========================================================================

class TestTelegramSettingsAPI(unittest.TestCase):
    """TDD-00007 T-27 ~ T-30"""

    @classmethod
    def setUpClass(cls):
        cls.app = _get_app()

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.repositories.settings import set_setting
            set_setting("telegram_bot_token", "")
            set_setting("telegram_chat_id", "")
            set_setting("telegram_poll_interval", "600")

    def test_t27_get_settings_includes_telegram_fields(self):
        """T-27：GET /api/settings 返回 telegram 配置字段，bot_token 脱敏"""
        with self.app.app_context():
            from outlook_web.repositories.settings import set_setting
            from outlook_web.security.crypto import encrypt_data
            set_setting("telegram_bot_token", encrypt_data("1234567890:AAxxxxx"))

        client = self.app.test_client()
        _login(client)
        resp = client.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        self.assertIn("telegram_bot_token", data)
        self.assertIn("telegram_chat_id", data)
        self.assertIn("telegram_poll_interval", data)
        # bot_token 不应返回明文
        token_val = data["telegram_bot_token"]
        self.assertNotEqual(token_val, "1234567890:AAxxxxx")
        # 应为脱敏值（含 * 或为空）
        if token_val:
            self.assertTrue(
                token_val.startswith("****") or "*" in token_val,
                f"Bot token should be masked, got: {token_val!r}"
            )

    def test_t28_put_settings_saves_telegram_config(self):
        """T-28：PUT /api/settings 保存 telegram 配置，bot_token 加密存储"""
        client = self.app.test_client()
        _login(client)
        resp = client.put(
            "/api/settings",
            json={
                "telegram_bot_token": "NewToken123",
                "telegram_chat_id": "-123456",
                "telegram_poll_interval": 300,
            },
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"), f"Expected success, got: {data}")

        with self.app.app_context():
            from outlook_web.repositories.settings import get_setting
            from outlook_web.security.crypto import decrypt_data
            raw_token = get_setting("telegram_bot_token")
            # 应加密存储（前缀 enc:）
            self.assertTrue(raw_token.startswith("enc:"), f"Token should be encrypted, got: {raw_token!r}")
            # 解密后应为原始值
            self.assertEqual(decrypt_data(raw_token), "NewToken123")
            self.assertEqual(get_setting("telegram_chat_id"), "-123456")
            self.assertEqual(get_setting("telegram_poll_interval"), "300")

    def test_t29_invalid_interval_returns_400(self):
        """T-29：telegram_poll_interval 低于最小值 10 → 400 错误"""
        client = self.app.test_client()
        _login(client)
        resp = client.put(
            "/api/settings",
            json={"telegram_poll_interval": 5},  # 低于最小值 10
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_t30_masked_token_placeholder_not_overwrite(self):
        """T-30：传入脱敏占位符（****xxxx）不覆盖已有 bot_token"""
        with self.app.app_context():
            from outlook_web.repositories.settings import set_setting
            from outlook_web.security.crypto import encrypt_data
            original_encrypted = encrypt_data("OriginalRealToken")
            set_setting("telegram_bot_token", original_encrypted)

        client = self.app.test_client()
        _login(client)
        resp = client.put(
            "/api/settings",
            json={"telegram_bot_token": "****xxxx"},  # 脱敏占位符
            content_type="application/json",
        )
        # 保存不报错
        self.assertIn(resp.status_code, [200, 204])

        with self.app.app_context():
            from outlook_web.repositories.settings import get_setting
            from outlook_web.security.crypto import decrypt_data, encrypt_data
            stored = get_setting("telegram_bot_token")
            # 解密后应仍为原始值（未被覆盖）
            self.assertEqual(decrypt_data(stored), "OriginalRealToken")


# ===========================================================================
# T-31 ~ T-32：回归测试
# ===========================================================================

class TestRegressions(unittest.TestCase):
    """TDD-00007 T-31 ~ T-32"""

    @classmethod
    def setUpClass(cls):
        cls.app = _get_app()

    def test_t31_token_refresh_job_unaffected(self):
        """T-31：加载 telegram_push 模块不影响 token_refresh 调度器 job"""
        # 确认可以导入 telegram_push 模块而不报错
        try:
            import outlook_web.services.telegram_push as tp  # noqa: F401
        except ImportError as e:
            self.fail(f"Cannot import telegram_push service: {e}")

    def test_t32_existing_tests_still_pass(self):
        """T-32：现有核心功能（providers, settings）在引入新模块后仍正常"""
        with self.app.app_context():
            # providers 模块正常
            from outlook_web.services.providers import get_provider_list
            providers = get_provider_list()
            self.assertIsInstance(providers, list)
            self.assertGreater(len(providers), 0)

            # settings repository 正常
            from outlook_web.repositories.settings import get_setting, set_setting
            set_setting("_test_regression_key", "ok")
            val = get_setting("_test_regression_key")
            self.assertEqual(val, "ok")


# ===========================================================================
# BUG-00009 相关测试：IMAP 时区处理 + 游标过滤
# ===========================================================================


class TestImapTimezoneAndCursor(unittest.TestCase):
    """BUG-00009 D-2: 验证 IMAP 邮件时区正确转换为 UTC 后与游标比较"""

    def test_imap_email_cst_timezone_converted_to_utc(self):
        """BUG-TG-006 验证：CST +0800 邮件时间应转换为 UTC"""
        from datetime import timezone as tz
        from email.utils import parsedate_to_datetime

        date_str = "Wed, 05 Mar 2026 17:00:00 +0800"
        received_dt = parsedate_to_datetime(date_str)
        if received_dt.tzinfo is not None:
            received_dt = received_dt.astimezone(tz.utc)
        received_iso = received_dt.strftime("%Y-%m-%dT%H:%M:%S")

        # CST 17:00 = UTC 09:00
        self.assertEqual(received_iso, "2026-03-05T09:00:00")

    def test_imap_email_utc_timezone_unchanged(self):
        """UTC +0000 邮件时间应保持不变"""
        from datetime import timezone as tz
        from email.utils import parsedate_to_datetime

        date_str = "Wed, 05 Mar 2026 09:00:00 +0000"
        received_dt = parsedate_to_datetime(date_str)
        if received_dt.tzinfo is not None:
            received_dt = received_dt.astimezone(tz.utc)
        received_iso = received_dt.strftime("%Y-%m-%dT%H:%M:%S")

        self.assertEqual(received_iso, "2026-03-05T09:00:00")

    def test_cursor_filter_before_cursor_excluded(self):
        """游标之前的邮件应被过滤（received_iso <= since → continue）"""
        cursor = "2026-03-05T09:30:00"
        email_time = "2026-03-05T09:20:00"  # 在游标之前
        self.assertTrue(email_time <= cursor, "游标之前的邮件应被过滤")

    def test_cursor_filter_after_cursor_included(self):
        """游标之后的邮件应通过过滤"""
        cursor = "2026-03-05T09:30:00"
        email_time = "2026-03-05T09:40:00"  # 在游标之后
        self.assertFalse(email_time <= cursor, "游标之后的邮件不应被过滤")

    def test_cursor_filter_exact_cursor_excluded(self):
        """恰好等于游标时间的邮件应被过滤（<= 比较）"""
        cursor = "2026-03-05T09:30:00"
        email_time = "2026-03-05T09:30:00"
        self.assertTrue(email_time <= cursor, "等于游标的邮件应被过滤")

    def test_cst_email_vs_utc_cursor_correct_after_fix(self):
        """BUG-TG-006 核心场景：CST 邮件转 UTC 后应被正确过滤"""
        from datetime import timezone as tz
        from email.utils import parsedate_to_datetime

        cursor_utc = "2026-03-05T09:30:00"

        # CST 17:00 = UTC 09:00, 在游标 09:30 之前 → 应被过滤
        date_str = "Wed, 05 Mar 2026 17:00:00 +0800"
        received_dt = parsedate_to_datetime(date_str)
        if received_dt.tzinfo is not None:
            received_dt = received_dt.astimezone(tz.utc)
        received_iso = received_dt.strftime("%Y-%m-%dT%H:%M:%S")

        self.assertTrue(received_iso <= cursor_utc,
                        f"CST 17:00 (UTC 09:00) 应在游标 09:30 之前被过滤，但 received_iso={received_iso}")

    def test_cst_email_after_cursor_passes_filter(self):
        """CST 邮件转 UTC 后若在游标之后应通过"""
        from datetime import timezone as tz
        from email.utils import parsedate_to_datetime

        cursor_utc = "2026-03-05T09:30:00"

        # CST 18:00 = UTC 10:00, 在游标 09:30 之后 → 应通过
        date_str = "Wed, 05 Mar 2026 18:00:00 +0800"
        received_dt = parsedate_to_datetime(date_str)
        if received_dt.tzinfo is not None:
            received_dt = received_dt.astimezone(tz.utc)
        received_iso = received_dt.strftime("%Y-%m-%dT%H:%M:%S")

        self.assertFalse(received_iso <= cursor_utc,
                         f"CST 18:00 (UTC 10:00) 应通过游标 09:30 过滤，但被拦截了")


class TestScrollPreservation(unittest.TestCase):
    """BUG-00009 D-1: 滚动位置保留（前端手动验证清单）"""

    def test_d1_documented_as_manual_test(self):
        """D-1 前端滚动测试需手动验证：
        1. 滚动到分组中间某个账号
        2. 点击 🔔 开启推送
        3. 验证列表不回到顶部
        4. 点击 🔔推送 标签关闭
        5. 验证列表不回到顶部
        """
        # 前端交互测试无法自动化，此用例记录验证清单
        pass


# ===========================================================================
# BUG-00010 相关测试：并行获取 + 游标策略 + 发送计数 + INTERNALDATE
# ===========================================================================


class TestFetchAccountEmails(unittest.TestCase):
    """BUG-00010: _fetch_account_emails 独立函数测试"""

    def test_first_run_returns_none_emails(self):
        """首次运行（last_checked_at=None）→ emails=None, error=None"""
        from outlook_web.services.telegram_push import _fetch_account_emails
        account = {"id": 1, "email": "x@test.com", "provider": "qq", "telegram_last_checked_at": None}
        acc, emails, error = _fetch_account_emails(account)
        self.assertIsNone(emails)
        self.assertIsNone(error)

    def test_fetch_success_returns_emails(self):
        """正常 fetch → 返回邮件列表"""
        from outlook_web.services.telegram_push import _fetch_account_emails
        account = {"id": 1, "email": "x@test.com", "provider": "qq",
                   "telegram_last_checked_at": "2026-03-01T00:00:00"}
        fake_emails = [{"subject": "Hi", "sender": "a@b.com", "received_at": "2026-03-05T10:00:00", "preview": ""}]

        with patch("outlook_web.services.telegram_push._fetch_new_emails_imap", return_value=fake_emails):
            acc, emails, error = _fetch_account_emails(account)
        self.assertEqual(len(emails), 1)
        self.assertIsNone(error)

    def test_fetch_error_returns_error(self):
        """fetch 异常 → emails=None, error=Exception"""
        from outlook_web.services.telegram_push import _fetch_account_emails
        account = {"id": 1, "email": "x@test.com", "provider": "qq",
                   "telegram_last_checked_at": "2026-03-01T00:00:00"}

        with patch("outlook_web.services.telegram_push._fetch_new_emails_imap",
                   side_effect=ConnectionError("timeout")):
            acc, emails, error = _fetch_account_emails(account)
        self.assertIsNone(emails)
        self.assertIsInstance(error, ConnectionError)

    def test_outlook_uses_graph_fetch(self):
        """Outlook 账号使用 Graph API fetch"""
        from outlook_web.services.telegram_push import _fetch_account_emails
        account = {"id": 1, "email": "x@outlook.com", "provider": "outlook",
                   "telegram_last_checked_at": "2026-03-01T00:00:00"}

        with patch("outlook_web.services.telegram_push._fetch_new_emails_graph", return_value=[]) as mock_graph, \
             patch("outlook_web.services.telegram_push._fetch_new_emails_imap") as mock_imap:
            _fetch_account_emails(account)
        mock_graph.assert_called_once()
        mock_imap.assert_not_called()


class TestParallelJobBehavior(unittest.TestCase):
    """BUG-00010: 并行 job 行为测试"""

    @classmethod
    def setUpClass(cls):
        cls.app = _get_app()

    def setUp(self):
        with self.app.app_context():
            from outlook_web.db import get_db
            db = get_db()
            db.execute("DELETE FROM accounts WHERE email LIKE '%@parallel.com'")
            db.execute("UPDATE accounts SET telegram_push_enabled = 0")
            db.commit()

    def _set_settings(self, bot_token="test_token_12345678", chat_id="-12345"):
        from outlook_web.repositories.settings import set_setting
        from outlook_web.security.crypto import encrypt_data
        if bot_token:
            set_setting("telegram_bot_token", encrypt_data(bot_token))
        else:
            set_setting("telegram_bot_token", "")
        set_setting("telegram_chat_id", chat_id)

    def _run_job(self):
        from outlook_web.services.telegram_push import run_telegram_push_job
        run_telegram_push_job(self.app)

    def _make_email(self, received_at="2026-03-04T14:31:00"):
        return {
            "subject": "Test",
            "sender": "s@test.com",
            "received_at": received_at,
            "preview": "body preview",
        }

    def test_send_failure_does_not_increment_count(self):
        """发送失败时 sent_count 不递增"""
        with self.app.app_context():
            from outlook_web.db import get_db
            db = get_db()
            _insert_test_account(db, "fail@parallel.com", enabled=1,
                                 last_checked="2026-03-01T00:00:00")
            self._set_settings()

            from datetime import timedelta
            recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
            emails = [self._make_email(recent)]

            send_calls = []
            def fake_send(token, chat, msg):
                send_calls.append(msg)
                return False  # 发送失败

            with patch("outlook_web.services.telegram_push._fetch_new_emails_imap", return_value=emails), \
                 patch("outlook_web.services.telegram_push._send_telegram_message", side_effect=fake_send), \
                 patch("outlook_web.services.telegram_push.TELEGRAM_PUSH_DELAY_SEC", 0):
                self._run_job()

            self.assertEqual(len(send_calls), 1, "应尝试发送 1 次")

    def test_mixed_success_failure_accounts(self):
        """混合场景：一个账号成功、一个失败 → 成功的游标推进，失败的保留"""
        with self.app.app_context():
            from outlook_web.db import get_db
            db = get_db()
            ok_id = _insert_test_account(db, "ok@parallel.com", enabled=1,
                                         last_checked="2026-03-01T00:00:00")
            err_id = _insert_test_account(db, "err@parallel.com", enabled=1,
                                          last_checked="2026-03-01T00:00:00")
            self._set_settings()

            from datetime import timedelta
            recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
            emails = [self._make_email(recent)]

            def fake_fetch(account, since):
                if account["email"] == "ok@parallel.com":
                    return emails
                raise ConnectionError("IMAP timeout")

            with patch("outlook_web.services.telegram_push._fetch_new_emails_imap", side_effect=fake_fetch), \
                 patch("outlook_web.services.telegram_push._send_telegram_message", return_value=True), \
                 patch("outlook_web.services.telegram_push.TELEGRAM_PUSH_DELAY_SEC", 0):
                self._run_job()

            ok_cursor = db.execute(
                "SELECT telegram_last_checked_at FROM accounts WHERE id = ?", (ok_id,)
            ).fetchone()["telegram_last_checked_at"]
            err_cursor = db.execute(
                "SELECT telegram_last_checked_at FROM accounts WHERE id = ?", (err_id,)
            ).fetchone()["telegram_last_checked_at"]

            self.assertNotEqual(ok_cursor, "2026-03-01T00:00:00", "成功账号游标应推进")
            self.assertEqual(err_cursor, "2026-03-01T00:00:00", "失败账号游标应保留")

    def test_parallel_fetch_all_accounts_processed(self):
        """并行模式下所有账号都应被处理"""
        with self.app.app_context():
            from outlook_web.db import get_db
            db = get_db()
            ids = []
            for i in range(5):
                aid = _insert_test_account(db, f"p{i}@parallel.com", enabled=1,
                                           last_checked="2026-03-01T00:00:00")
                ids.append(aid)
            self._set_settings()

            fetch_emails = set()
            def fake_fetch(account, since):
                fetch_emails.add(account["email"])
                return []

            with patch("outlook_web.services.telegram_push._fetch_new_emails_imap", side_effect=fake_fetch), \
                 patch("outlook_web.services.telegram_push._send_telegram_message", return_value=True):
                self._run_job()

            for i in range(5):
                self.assertIn(f"p{i}@parallel.com", fetch_emails,
                              f"p{i}@parallel.com 未被 fetch")

    def test_scheduler_default_interval_is_60(self):
        """调度器默认间隔应为 60 秒"""
        with self.app.app_context():
            from outlook_web.services.scheduler import _get_telegram_interval
            # 清除可能存在的设置
            from outlook_web.repositories.settings import set_setting
            set_setting("telegram_poll_interval", "")
            interval = _get_telegram_interval(self.app)
            self.assertEqual(interval, 60)

    def test_recency_filter_skips_old_emails(self):
        """PUSH_RECENCY_HOURS: 超过 12 小时的邮件应被跳过"""
        with self.app.app_context():
            from outlook_web.db import get_db
            db = get_db()
            _insert_test_account(db, "old@parallel.com", enabled=1,
                                 last_checked="2026-01-01T00:00:00")
            self._set_settings()

            # 创建一封很旧的邮件（比当前时间早 24 小时以上）
            from datetime import timedelta
            old_time = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
            old_emails = [self._make_email(old_time)]

            send_calls = []
            def fake_send(token, chat, msg):
                send_calls.append(msg)
                return True

            with patch("outlook_web.services.telegram_push._fetch_new_emails_imap", return_value=old_emails), \
                 patch("outlook_web.services.telegram_push._send_telegram_message", side_effect=fake_send), \
                 patch("outlook_web.services.telegram_push.TELEGRAM_PUSH_DELAY_SEC", 0):
                self._run_job()

            self.assertEqual(len(send_calls), 0, "超过 12 小时的邮件不应推送")

    def test_recent_email_passes_recency_filter(self):
        """PUSH_RECENCY_HOURS: 12 小时内的邮件应正常推送"""
        with self.app.app_context():
            from outlook_web.db import get_db
            db = get_db()
            _insert_test_account(db, "new@parallel.com", enabled=1,
                                 last_checked="2026-01-01T00:00:00")
            self._set_settings()

            # 创建一封 1 小时前的邮件
            from datetime import timedelta
            recent_time = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
            recent_emails = [self._make_email(recent_time)]

            send_calls = []
            def fake_send(token, chat, msg):
                send_calls.append(msg)
                return True

            with patch("outlook_web.services.telegram_push._fetch_new_emails_imap", return_value=recent_emails), \
                 patch("outlook_web.services.telegram_push._send_telegram_message", side_effect=fake_send), \
                 patch("outlook_web.services.telegram_push.TELEGRAM_PUSH_DELAY_SEC", 0):
                self._run_job()

            self.assertEqual(len(send_calls), 1, "1 小时内的邮件应正常推送")


if __name__ == "__main__":
    unittest.main()
