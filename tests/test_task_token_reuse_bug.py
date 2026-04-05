"""
BUG-002 复现测试：task_token UNIQUE 约束导致任务完成后无法复用

模拟场景：
  1. 任务A 申请临时邮箱 → 得到 task_token_A + email_A
  2. 任务A 完成 → email_A.status = 'finished'，但 task_token_A 仍在记录中
  3. 任务B 申请临时邮箱 → 系统生成新的 task_token_B（随机，不会冲突）
  4. 额外测试：手动用同一个 task_token 值再次 create → 应该失败（UNIQUE）
"""

from __future__ import annotations

import sqlite3
import unittest

from tests._import_app import clear_login_attempts, import_web_app_module


class TestTaskTokenReuseBug(unittest.TestCase):
    """复现 task_token 复用问题"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.db import get_db

            db = get_db()
            db.execute("DELETE FROM temp_email_messages")
            db.execute("DELETE FROM temp_emails")
            db.commit()

    # ─── 场景1：正常流程，task_token 每次随机生成不会冲突 ───

    def test_two_sequential_tasks_get_different_tokens(self):
        """两次 apply 应该各自得到不同的 task_token，互不影响"""
        from outlook_web.repositories import temp_emails as repo

        with self.app.app_context():
            ok1 = repo.create_temp_email(
                email_addr="task1@reuse-bug.test",
                mailbox_type="task",
                visible_in_ui=False,
                task_token="tmptask AAAA",
                caller_id="worker-1",
                task_id="job-001",
            )
            ok2 = repo.create_temp_email(
                email_addr="task2@reuse-bug.test",
                mailbox_type="task",
                visible_in_ui=False,
                task_token="tmptask BBBB",
                caller_id="worker-1",
                task_id="job-002",
            )

        self.assertTrue(ok1, "第一个任务邮箱创建应该成功")
        self.assertTrue(ok2, "第二个任务邮箱创建应该成功")

    # ─── 场景2：同一 task_token 值不能被第二次写入（UNIQUE 约束） ───

    def test_same_task_token_value_rejected_by_unique_constraint(self):
        """同一个 task_token 值写入第二条记录时，应该被 UNIQUE 约束拒绝"""
        from outlook_web.repositories import temp_emails as repo

        with self.app.app_context():
            ok1 = repo.create_temp_email(
                email_addr="first@reuse-bug.test",
                mailbox_type="task",
                visible_in_ui=False,
                task_token="tmptask_DUPLICATE",
                caller_id="worker-1",
                task_id="job-001",
            )

            # 尝试用完全相同的 task_token 再创建一条
            ok2 = repo.create_temp_email(
                email_addr="second@reuse-bug.test",
                mailbox_type="task",
                visible_in_ui=False,
                task_token="tmptask_DUPLICATE",  # 相同！
                caller_id="worker-1",
                task_id="job-002",
            )

        self.assertTrue(ok1)
        self.assertFalse(ok2, "相同 task_token 的第二条记录应该被 UNIQUE 约束拒绝")

    # ─── 场景3（核心BUG）：finish 后 task_token 仍占位，无法复用 ───

    def test_finished_task_token_still_blocks_new_insert(self):
        """
        这是 BUG-002 的核心复现场景：
        1. 创建邮箱，写入 task_token = "tmptask_REUSE"
        2. finish 后，task_token 没有被清空
        3. 再用同样的 task_token 创建新邮箱 → 失败
        """
        from outlook_web.repositories import temp_emails as repo

        with self.app.app_context():
            # 步骤1：任务A 创建邮箱
            ok = repo.create_temp_email(
                email_addr="reuse@reuse-bug.test",
                mailbox_type="task",
                visible_in_ui=False,
                task_token="tmptask_REUSE",
                caller_id="worker-1",
                task_id="job-001",
            )
            self.assertTrue(ok)

            # 步骤2：任务A 完成
            finished = repo.finish_task_temp_email("tmptask_REUSE")
            self.assertTrue(finished)

            # 验证：task_token 仍然留在记录中（没有被清空）
            record = repo.get_temp_email_by_task_token("tmptask_REUSE")
            self.assertIsNotNone(record)
            self.assertEqual(record["status"], "finished")
            self.assertEqual(record["task_token"], "tmptask_REUSE")  # ← BUG！仍然有值

            # 步骤3：尝试用同样的 task_token 创建新邮箱
            ok2 = repo.create_temp_email(
                email_addr="reuse2@reuse-bug.test",
                mailbox_type="task",
                visible_in_ui=False,
                task_token="tmptask_REUSE",  # 想复用同一个 token
                caller_id="worker-1",
                task_id="job-002",
            )
            self.assertFalse(ok2, "finish 后 task_token 没清空，UNIQUE 约束导致无法复用")

    # ─── 场景4：验证数据库层面的 UNIQUE INDEX ───

    def test_unique_index_exists_on_task_token(self):
        """确认 idx_temp_emails_task_token_unique 索引存在"""
        from outlook_web.db import get_db

        with self.app.app_context():
            db = get_db()
            indexes = db.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE '%task_token%'").fetchall()

        index_names = [row["name"] for row in indexes]
        self.assertIn(
            "idx_temp_emails_task_token_unique",
            index_names,
            f"缺少 task_token 唯一索引，当前索引: {index_names}",
        )

    # ─── 场景5：验证 finish 操作的字段变更（确认 task_token 未被清除） ───

    def test_finish_does_not_clear_task_token(self):
        """直接查数据库，确认 finish 只改了 status 和 finished_at，没清 task_token"""
        from outlook_web.db import get_db
        from outlook_web.repositories import temp_emails as repo

        with self.app.app_context():
            repo.create_temp_email(
                email_addr="verify@reuse-bug.test",
                mailbox_type="task",
                visible_in_ui=False,
                task_token="tmptask_VERIFY",
                caller_id="worker-1",
                task_id="job-001",
            )

            db = get_db()
            before = db.execute(
                "SELECT task_token, status, finished_at FROM temp_emails WHERE email = ?",
                ("verify@reuse-bug.test",),
            ).fetchone()

            repo.finish_task_temp_email("tmptask_VERIFY")

            after = db.execute(
                "SELECT task_token, status, finished_at FROM temp_emails WHERE email = ?",
                ("verify@reuse-bug.test",),
            ).fetchone()

        self.assertIsNotNone(before["task_token"])
        self.assertIsNone(before["finished_at"])
        self.assertEqual(before["status"], "active")

        self.assertIsNotNone(after["task_token"])  # ← BUG：finish 没有清空
        self.assertIsNotNone(after["finished_at"])
        self.assertEqual(after["status"], "finished")
        self.assertEqual(after["task_token"], before["task_token"])  # 完全没变


if __name__ == "__main__":
    unittest.main()
