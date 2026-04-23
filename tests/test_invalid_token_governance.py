"""Issue #49: 失效 Token 治理端点与判定逻辑的集成测试。

覆盖:
  - _classify_refresh_failure helper 分类逻辑
  - GET /api/accounts/invalid-token-candidates 候选查询
  - POST /api/accounts/batch-update-status 批量状态更新
  - 两者闭环联动（候选 → 批量停用）
"""

import json
import unittest
import uuid

from tests._import_app import clear_login_attempts, import_web_app_module


class InvalidTokenGovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()

    # ---------- helpers ----------

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        return resp

    def _insert_account_direct(self, email=None):
        """直接向 DB 插入一个 Outlook 账号，返回 (account_id, email)。"""
        from outlook_web.db import get_db
        from outlook_web.security.crypto import encrypt_data

        suffix = uuid.uuid4().hex[:8]
        email = email or f"govtest_{suffix}@outlook.com"
        db = get_db()
        cursor = db.execute(
            """
            INSERT INTO accounts (email, password, refresh_token, client_id, account_type, provider, status)
            VALUES (?, ?, ?, ?, 'outlook', 'outlook', 'active')
            """,
            (email, "unused", encrypt_data(f"rt_{suffix}"), "test-client-id"),
        )
        db.commit()
        return cursor.lastrowid, email

    def _insert_refresh_log(self, account_id, account_email, status, error_message, refresh_type="manual"):
        """直接向 account_refresh_logs 插入一条记录。"""
        from outlook_web.db import get_db

        db = get_db()
        db.execute(
            """
            INSERT INTO account_refresh_logs
                (account_id, account_email, refresh_type, status, error_message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (account_id, account_email, refresh_type, status, error_message),
        )
        db.commit()

    # ---------- _classify_refresh_failure unit tests ----------

    def test_classify_invalid_grant_error(self):
        """invalid_grant 错误应被分类为 invalid_token。"""
        from outlook_web.services.refresh import _classify_refresh_failure

        result = _classify_refresh_failure("AADSTS70000: invalid_grant - token expired")
        self.assertTrue(result.get("is_invalid_token"))
        self.assertEqual(result.get("reason_code"), "INVALID_GRANT_OR_AADSTS70000")

    def test_classify_aadsts70000_error(self):
        """AADSTS70000 错误应被分类为 invalid_token。"""
        from outlook_web.services.refresh import _classify_refresh_failure

        result = _classify_refresh_failure("AADSTS70000: The token has been revoked")
        self.assertTrue(result.get("is_invalid_token"))
        self.assertEqual(result.get("reason_code"), "INVALID_GRANT_OR_AADSTS70000")

    def test_classify_normal_error_not_invalid_token(self):
        """普通网络错误不应被分类为 invalid_token。"""
        from outlook_web.services.refresh import _classify_refresh_failure

        result = _classify_refresh_failure("ConnectionTimeout: failed to connect to graph.microsoft.com")
        self.assertFalse(result.get("is_invalid_token"))

    def test_classify_none_error(self):
        """None error_message 应返回非 invalid_token。"""
        from outlook_web.services.refresh import _classify_refresh_failure

        result = _classify_refresh_failure(None)
        self.assertFalse(result.get("is_invalid_token"))

    def test_classify_empty_error(self):
        """空字符串应返回非 invalid_token。"""
        from outlook_web.services.refresh import _classify_refresh_failure

        result = _classify_refresh_failure("")
        self.assertFalse(result.get("is_invalid_token"))

    # ---------- invalid-token-candidates endpoint ----------

    def test_get_invalid_token_candidates_returns_empty_when_no_logs(self):
        """没有 invalid_grant 日志时应返回空的候选项（结构正确）。"""
        client = self.app.test_client()
        self._login(client)

        resp = client.get("/api/accounts/invalid-token-candidates")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIsInstance(data.get("candidates"), list)
        # 注：测试间共享 DB，可能有前序测试残留的候选，
        # 此处只检验结构完整性，不严格断言数量为 0
        self.assertIn("total", data)

    def test_get_invalid_token_candidates_returns_classified_account(self):
        """有 invalid_grant 日志时应返回对应候选。"""
        client = self.app.test_client()
        self._login(client)

        with self.app.app_context():
            account_id, email = self._insert_account_direct()
            self._insert_refresh_log(account_id, email, "failed", "AADSTS70000: invalid_grant - token expired")

        resp = client.get("/api/accounts/invalid-token-candidates")
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        candidates = data.get("candidates", [])
        found = [c for c in candidates if c["account_id"] == account_id]
        self.assertTrue(
            len(found) > 0, f"应至少有1条候选包含 account_id={account_id}，实际: {[c['account_id'] for c in candidates]}"
        )
        self.assertTrue(found[0].get("is_invalid_token"))
        self.assertEqual(found[0].get("reason_code"), "INVALID_GRANT_OR_AADSTS70000")

    def test_get_invalid_token_candidates_excludes_normal_error(self):
        """普通失败的账号不应出现在候选列表。"""
        client = self.app.test_client()
        self._login(client)

        with self.app.app_context():
            account_id, email = self._insert_account_direct()
            self._insert_refresh_log(account_id, email, "failed", "NetworkError: timeout")

        resp = client.get("/api/accounts/invalid-token-candidates")
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        candidates = data.get("candidates", [])
        found = [c for c in candidates if c["account_id"] == account_id]
        self.assertEqual(len(found), 0, "普通网络错误不应出现在 invalid token 候选中")

    # ---------- batch-update-status endpoint ----------

    def test_batch_update_status_to_inactive(self):
        """批量将账号状态置为 inactive。"""
        client = self.app.test_client()
        self._login(client)

        with self.app.app_context():
            account_id_1, _ = self._insert_account_direct()
            account_id_2, _ = self._insert_account_direct()

        resp = client.post(
            "/api/accounts/batch-update-status",
            json={"account_ids": [account_id_1, account_id_2], "status": "inactive"},
        )
        data = resp.get_json()
        self.assertTrue(data.get("success"), f"批量停用应成功: {data}")
        self.assertEqual(data.get("updated_count"), 2)

        # 验证状态确实变了
        for aid in [account_id_1, account_id_2]:
            detail_resp = client.get(f"/api/accounts/{aid}")
            detail = detail_resp.get_json()
            self.assertEqual(detail["account"]["status"], "inactive")

    def test_batch_update_status_rejects_empty_ids(self):
        """空 account_ids 应被拒绝。"""
        client = self.app.test_client()
        self._login(client)

        resp = client.post(
            "/api/accounts/batch-update-status",
            json={"account_ids": [], "status": "inactive"},
        )
        data = resp.get_json()
        self.assertFalse(data.get("success"))
        self.assertIn("ACCOUNT_IDS_REQUIRED", data.get("error", {}).get("code", ""))

    def test_batch_update_status_rejects_invalid_status(self):
        """无效的 status 值应被拒绝。"""
        client = self.app.test_client()
        self._login(client)

        with self.app.app_context():
            account_id, _ = self._insert_account_direct()

        resp = client.post(
            "/api/accounts/batch-update-status",
            json={"account_ids": [account_id], "status": "bogus_status"},
        )
        data = resp.get_json()
        self.assertFalse(data.get("success"))

    # ---------- governance loop: candidates → batch inactive ----------

    def test_governance_loop_candidates_then_batch_inactive(self):
        """端到端闭环：插入 invalid_grant 日志 → 查到候选 → 批量停用。"""
        client = self.app.test_client()
        self._login(client)

        # 1) 创建账号
        with self.app.app_context():
            account_id, email = self._insert_account_direct()
            self._insert_refresh_log(account_id, email, "failed", "AADSTS70000: The token has expired due to inactivity")

        # 2) 查询候选
        resp = client.get("/api/accounts/invalid-token-candidates")
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        candidates = data.get("candidates", [])
        found = [c for c in candidates if c["account_id"] == account_id]
        self.assertTrue(len(found) > 0, f"应能查到候选 account_id={account_id}")
        self.assertTrue(found[0].get("is_invalid_token"))

        # 3) 批量停用
        resp = client.post(
            "/api/accounts/batch-update-status",
            json={"account_ids": [account_id], "status": "inactive"},
        )
        data = resp.get_json()
        self.assertTrue(data.get("success"), f"批量停用应成功: {data}")

        # 4) 验证状态
        detail_resp = client.get(f"/api/accounts/{account_id}")
        detail = detail_resp.get_json()
        self.assertEqual(detail["account"]["status"], "inactive")


if __name__ == "__main__":
    unittest.main()
