"""
login_required 装饰器补充测试

背景：login_required 从仅检查 session["logged_in"] 改为同时接受 session["user_id"]：
    is_logged_in = bool(session.get("logged_in") or session.get("user_id"))

本文件验证五种 session 状态下装饰器的认证行为。
"""

import unittest

from tests._import_app import clear_login_attempts, import_web_app_module


class TestLoginRequiredUserIdScenarios(unittest.TestCase):
    """login_required 装饰器对 logged_in / user_id session 键的组合验证"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()

    def _set_session(self, client, logged_in=None, user_id=None):
        """在 Flask test client 的 session 中设置指定的键值"""
        with client.session_transaction() as sess:
            if logged_in is not None:
                sess["logged_in"] = logged_in
            if user_id is not None:
                sess["user_id"] = user_id

    def test_only_logged_in_true_should_pass(self):
        """session 中仅有 logged_in=True（无 user_id）时，应通过认证"""
        client = self.app.test_client()
        self._set_session(client, logged_in=True)

        resp = client.get("/api/system/health")
        self.assertEqual(resp.status_code, 200, "logged_in=True 应通过认证")

    def test_only_user_id_should_pass(self):
        """session 中仅有 user_id=1（无 logged_in）时，应通过认证（新增场景）"""
        client = self.app.test_client()
        self._set_session(client, user_id=1)

        resp = client.get("/api/system/health")
        self.assertEqual(resp.status_code, 200, "仅有 user_id=1 应通过认证")

    def test_both_logged_in_and_user_id_should_pass(self):
        """session 中同时有 logged_in=True 和 user_id=1 时，应通过认证"""
        client = self.app.test_client()
        self._set_session(client, logged_in=True, user_id=1)

        resp = client.get("/api/system/health")
        self.assertEqual(resp.status_code, 200, "同时存在 logged_in 和 user_id 应通过认证")

    def test_neither_logged_in_nor_user_id_should_reject(self):
        """session 中既无 logged_in 也无 user_id 时，应拒绝认证（返回 401）"""
        client = self.app.test_client()

        resp = client.get("/api/system/health")
        self.assertEqual(resp.status_code, 401, "缺少 logged_in 和 user_id 应返回 401")
        data = resp.get_json()
        self.assertFalse(data.get("success"))
        self.assertTrue(data.get("need_login"))
        self.assertEqual(data["error"]["code"], "AUTH_REQUIRED")

    def test_logged_in_false_with_user_id_should_pass(self):
        """session 中 logged_in=False 但 user_id=1 时，应通过认证"""
        client = self.app.test_client()
        self._set_session(client, logged_in=False, user_id=1)

        resp = client.get("/api/system/health")
        self.assertEqual(resp.status_code, 200, "logged_in=False 但 user_id=1 应通过认证")


if __name__ == "__main__":
    unittest.main()
