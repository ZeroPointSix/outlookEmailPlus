import json
import time
import unittest
import uuid
from unittest.mock import patch

from tests._import_app import clear_login_attempts, import_web_app_module


class ErrorAndTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        # 每个测试前清理登录限制记录，避免测试间互相影响
        with self.app.app_context():
            clear_login_attempts()

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        return resp

    def test_healthz(self):
        client = self.app.test_client()
        resp = client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("status"), "ok")
        # 新增字段：用于前端判断是否发生重启
        self.assertTrue(data.get("boot_id"))
        self.assertTrue(data.get("version"))

    def test_login_required_returns_structured_error(self):
        client = self.app.test_client()
        resp = client.get("/api/system/health")
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data.get("success"), False)
        self.assertEqual(data.get("need_login"), True)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "AUTH_REQUIRED")
        self.assertEqual(data["error"].get("status"), 401)
        self.assertTrue(data["error"].get("trace_id"))

    def test_api_404_has_structured_error_and_trace_id(self):
        client = self.app.test_client()
        resp = client.get("/api/__not_found__")
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertIsInstance(data, dict)
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "HTTP_ERROR")
        self.assertEqual(data["error"].get("status"), 404)
        self.assertTrue(data["error"].get("trace_id"))
        self.assertEqual(resp.headers.get("X-Trace-Id"), data["error"].get("trace_id"))
        self.assertEqual(data["error"].get("details"), "")

    def test_trace_id_can_be_propagated_from_request(self):
        client = self.app.test_client()
        resp = client.get("/api/__not_found__", headers={"X-Trace-Id": "trace_from_test"})
        data = resp.get_json()
        self.assertEqual(resp.headers.get("X-Trace-Id"), "trace_from_test")
        self.assertEqual(data["error"].get("trace_id"), "trace_from_test")

    def test_sanitize_error_details_masks_tokens(self):
        sanitized = self.module.sanitize_error_details('Bearer abcdefg refresh_token=xyz password: "123456"')
        self.assertIn("Bearer ***", sanitized)
        self.assertIn("refresh_token=***", sanitized)
        self.assertIn('"123456"', 'Bearer abcdefg refresh_token=xyz password: "123456"')  # sanity
        self.assertNotIn("123456", sanitized)

    def test_build_error_payload_sanitizes_message_and_details(self):
        payload = self.module.build_error_payload(
            "TEST",
            'Bearer abcdefg refresh_token=xyz password: "123456"',
            "TestError",
            400,
            'Bearer abcdefg refresh_token=xyz password: "123456"',
        )
        self.assertIn("Bearer ***", payload.get("message", ""))
        self.assertIn("refresh_token=***", payload.get("message", ""))
        self.assertNotIn("abcdefg", payload.get("message", ""))
        self.assertNotIn("123456", payload.get("message", ""))

        self.assertIn("Bearer ***", payload.get("details", ""))
        self.assertIn("refresh_token=***", payload.get("details", ""))
        self.assertNotIn("abcdefg", payload.get("details", ""))
        self.assertNotIn("123456", payload.get("details", ""))

    def test_delete_emails_all_methods_fail_returns_aggregated_error(self):
        client = self.app.test_client()
        login = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(login.status_code, 200)

        email_addr = "user@example.com"
        graph_error = {
            "code": "EMAIL_DELETE_FAILED",
            "message": "Graph 删除失败",
            "type": "GraphAPIError",
            "status": 502,
            "details": "graph_failed",
            "trace_id": "",
        }

        # 控制器现在使用 repositories 和 services，需要 mock 这些模块
        from outlook_web.repositories import accounts as accounts_repo
        from outlook_web.services import graph as graph_service
        from outlook_web.services import imap as imap_service

        with (
            patch.object(
                accounts_repo,
                "get_account_by_email",
                return_value={
                    "email": email_addr,
                    "client_id": "cid",
                    "refresh_token": "rt",
                    "group_id": None,
                },
            ),
            patch.object(
                graph_service,
                "delete_emails_graph",
                return_value={
                    "success": False,
                    "error": graph_error,
                    "success_count": 0,
                    "failed_count": 2,
                    "errors": ["e1"],
                },
            ),
            patch.object(
                imap_service,
                "delete_emails_imap",
                side_effect=[
                    {"success": False, "error": "imap_new_failed"},
                    {"success": False, "error": "imap_old_failed"},
                ],
            ),
        ):
            resp = client.post(
                "/api/emails/delete",
                json={"email": email_addr, "ids": ["m1", "m2"]},
            )

        self.assertEqual(resp.status_code, 502)
        data = resp.get_json()
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "EMAIL_DELETE_ALL_METHODS_FAILED")
        self.assertEqual(data["error"].get("status"), 502)
        self.assertTrue(data["error"].get("trace_id"))
        self.assertEqual(resp.headers.get("X-Trace-Id"), data["error"].get("trace_id"))

        details_text = data["error"].get("details") or ""
        self.assertIn("Graph API", details_text)
        self.assertIn("IMAP（新服务器）", details_text)
        self.assertIn("IMAP（旧服务器）", details_text)

    def test_delete_emails_proxy_error_does_not_fallback_to_imap(self):
        client = self.app.test_client()
        login = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(login.status_code, 200)

        email_addr = "user@example.com"
        graph_res = {
            "success": False,
            "error": {
                "code": "EMAIL_DELETE_FAILED",
                "message": "代理连接失败",
                "type": "ProxyError",
                "status": 502,
                "details": "proxy_failed",
                "trace_id": "",
            },
            "success_count": 0,
            "failed_count": 2,
            "errors": ["ProxyError: connect failed"],
        }

        # 控制器现在使用 repositories 和 services，需要 mock 这些模块
        from outlook_web.repositories import accounts as accounts_repo
        from outlook_web.repositories import groups as groups_repo
        from outlook_web.services import graph as graph_service
        from outlook_web.services import imap as imap_service

        with (
            patch.object(
                accounts_repo,
                "get_account_by_email",
                return_value={
                    "email": email_addr,
                    "client_id": "cid",
                    "refresh_token": "rt",
                    "group_id": 1,
                },
            ),
            patch.object(
                groups_repo,
                "get_group_by_id",
                return_value={"proxy_url": "http://proxy.test:8080"},
            ),
            patch.object(
                graph_service,
                "delete_emails_graph",
                return_value=graph_res,
            ),
            patch.object(
                imap_service,
                "delete_emails_imap",
            ) as imap_mock,
        ):
            resp = client.post(
                "/api/emails/delete",
                json={"email": email_addr, "ids": ["m1", "m2"]},
            )
            imap_mock.assert_not_called()

        self.assertEqual(resp.status_code, 502)
        data = resp.get_json()
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("type"), "ProxyError")
        self.assertTrue(data["error"].get("trace_id"))
        self.assertEqual(resp.headers.get("X-Trace-Id"), data["error"].get("trace_id"))

    def test_group_not_found_returns_structured_error_contract(self):
        client = self.app.test_client()

        # 登录
        login = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.get_json().get("success"), True)

        # 分组不存在应返回统一结构化错误，而不是裸字符串
        resp = client.get("/api/groups/999999")
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "GROUP_NOT_FOUND")
        self.assertEqual(data["error"].get("message"), "分组不存在")
        self.assertEqual(data["error"].get("message_en"), "Group not found")
        self.assertTrue(data["error"].get("trace_id"))

        # 响应体应是 JSON（确保 after_request 的 set_data 没破坏格式）
        json.loads(resp.get_data(as_text=True))

    def test_scheduler_status_endpoint_is_accessible_after_login(self):
        client = self.app.test_client()
        login = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(login.status_code, 200)

        resp = client.get("/api/scheduler/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("success"), True)
        self.assertIn("scheduler", data)
        self.assertIn("refresh", data)

    def test_system_health_and_scheduler_status_use_real_refresh_lock_name(self):
        client = self.app.test_client()
        login = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(login.status_code, 200)

        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.services.scheduler import REFRESH_LOCK_NAME

            db = get_db()
            db.execute("DELETE FROM distributed_locks WHERE name = ?", (REFRESH_LOCK_NAME,))
            db.execute(
                """
                INSERT INTO distributed_locks (name, owner_id, acquired_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (REFRESH_LOCK_NAME, "test-owner", time.time(), time.time() + 120),
            )
            db.commit()

        health_resp = client.get("/api/system/health")
        self.assertEqual(health_resp.status_code, 200)
        self.assertTrue(health_resp.get_json()["health"]["refresh"]["locked"])

        scheduler_resp = client.get("/api/scheduler/status")
        self.assertEqual(scheduler_resp.status_code, 200)
        self.assertTrue(scheduler_resp.get_json()["refresh"]["lock"]["locked"])

    def test_api_500_does_not_leak_exception_details(self):
        client = self.app.test_client()

        with self.app.test_request_context("/api/test"):
            from outlook_web.middleware.error_handler import handle_exception

            response, status_code = handle_exception(RuntimeError("database path C:/secret.db exploded"))

        self.assertEqual(status_code, 500)
        data = response.get_json()
        self.assertEqual(data["error"].get("details"), "")

    def test_validate_cron_endpoint(self):
        client = self.app.test_client()
        login = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(login.status_code, 200)

        resp = client.post("/api/settings/validate-cron", json={"cron_expression": "0 2 * * *"})
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data.get("success"), True)
        self.assertEqual(data.get("valid"), True)
        self.assertIsInstance(data.get("future_runs"), list)
        self.assertGreaterEqual(len(data.get("future_runs")), 1)

    def test_system_diagnostics_includes_schema(self):
        client = self.app.test_client()
        login = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(login.status_code, 200)

        resp = client.get("/api/system/diagnostics")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("success"), True)
        diagnostics = data.get("diagnostics") or {}
        self.assertIn("schema", diagnostics)
        self.assertIn("version", diagnostics["schema"])
        self.assertIn("target_version", diagnostics["schema"])
        self.assertIn("up_to_date", diagnostics["schema"])

    def test_system_upgrade_status_endpoint(self):
        client = self.app.test_client()
        login = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(login.status_code, 200)

        resp = client.get("/api/system/upgrade-status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("success"), True)
        upgrade = data.get("upgrade") or {}
        self.assertIn("schema_version", upgrade)
        self.assertIn("target_version", upgrade)
        self.assertIn("up_to_date", upgrade)
        self.assertIn("backup_hint", upgrade)

    def test_login_rate_limiting_locks_after_max_attempts(self):
        client = self.app.test_client()
        ip = "10.0.0.99"

        for _ in range(self.module.MAX_LOGIN_ATTEMPTS):
            resp = client.post(
                "/login",
                json={"password": "wrong_password"},
                headers={"X-Forwarded-For": ip},
            )
            self.assertEqual(resp.status_code, 401)
            data = resp.get_json()
            self.assertEqual(data.get("success"), False)
            self.assertIsInstance(data.get("error"), dict)
            self.assertEqual(data["error"].get("code"), "LOGIN_INVALID_PASSWORD")

        resp = client.post(
            "/login",
            json={"password": "wrong_password"},
            headers={"X-Forwarded-For": ip},
        )
        self.assertEqual(resp.status_code, 429)
        data = resp.get_json()
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "LOGIN_RATE_LIMITED")
        self.assertEqual(data["error"].get("status"), 429)
        self.assertTrue(data["error"].get("trace_id"))

    def test_export_requires_verify_token(self):
        client = self.app.test_client()
        login = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(login.status_code, 200)

        resp = client.post(
            "/api/accounts/export-selected",
            json={"group_ids": [1], "verify_token": "invalid_token"},
        )
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data.get("success"), False)
        self.assertEqual(data.get("need_verify"), True)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "EXPORT_VERIFY_REQUIRED")
        self.assertEqual(data["error"].get("message_en"), "Additional verification is required")
        self.assertEqual(data["error"].get("status"), 401)
        self.assertTrue(data["error"].get("trace_id"))

    def test_group_export_verify_failure_uses_detailed_error_contract(self):
        client = self.app.test_client()
        login = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(login.status_code, 200)

        with patch(
            "outlook_web.controllers.groups.consume_export_verify_token",
            return_value=(False, "验证失败：IP 不匹配"),
        ):
            resp = client.get("/api/groups/1/export")

        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data.get("success"), False)
        self.assertEqual(data.get("need_verify"), True)
        self.assertEqual(data["error"].get("code"), "EXPORT_VERIFY_IP_MISMATCH")
        self.assertEqual(
            data["error"].get("message_en"),
            "Verification failed because the client IP changed",
        )

    def test_import_failure_uses_structured_error_contract(self):
        client = self.app.test_client()
        login = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(login.status_code, 200)

        resp = client.post(
            "/api/accounts",
            json={"account_string": "bad-import-line", "group_id": 1},
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data.get("success"), False)
        self.assertEqual(data.get("code"), "ACCOUNT_IMPORT_FAILED")
        self.assertEqual(data.get("message_en"), "Account import failed")
        self.assertIsInstance(data.get("summary"), dict)
        self.assertIsInstance(data.get("errors"), list)
        self.assertTrue(data.get("trace_id"))

    def test_accounts_list_and_search_include_tags_and_last_refresh(self):
        client = self.app.test_client()
        login = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(login.status_code, 200)

        unique = uuid.uuid4().hex
        email_addr = f"test_{unique}@example.com"
        client_id = "client_id_" + unique
        refresh_token = "rt_" + unique
        tag_name = "tag_" + unique

        conn = self.module.create_sqlite_connection()
        try:
            # 插入账号
            cur = conn.execute(
                """
                INSERT INTO accounts (email, password, client_id, refresh_token, group_id, remark, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (email_addr, "", client_id, refresh_token, 1, "remark", "active"),
            )
            account_id = cur.lastrowid

            # 插入标签并关联
            cur = conn.execute(
                "INSERT INTO tags (name, color) VALUES (?, ?)",
                (tag_name, "#111111"),
            )
            tag_id = cur.lastrowid
            conn.execute(
                "INSERT OR IGNORE INTO account_tags (account_id, tag_id) VALUES (?, ?)",
                (account_id, tag_id),
            )

            # 插入刷新日志（用于 last_refresh_status/error）
            conn.execute(
                """
                INSERT INTO account_refresh_logs (account_id, account_email, refresh_type, status, error_message)
                VALUES (?, ?, ?, ?, ?)
                """,
                (account_id, email_addr, "manual", "failed", "network_error"),
            )

            conn.commit()
        finally:
            conn.close()

        # 列表接口：应返回 tags + last_refresh_*
        resp = client.get("/api/accounts")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("success"), True)

        accounts = data.get("accounts") or []
        target = next((a for a in accounts if a.get("email") == email_addr), None)
        self.assertIsNotNone(target)
        self.assertTrue(target.get("client_id", "").startswith(client_id[:8]))
        self.assertEqual(target.get("last_refresh_status"), "failed")
        self.assertEqual(target.get("last_refresh_error"), "network_error")
        self.assertIsInstance(target.get("tags"), list)
        self.assertIn(tag_name, [t.get("name") for t in target.get("tags")])

        # 搜索接口：按标签名应可搜索到
        resp = client.get(f"/api/accounts/search?q={tag_name}")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("success"), True)
        accounts = data.get("accounts") or []
        target = next((a for a in accounts if a.get("email") == email_addr), None)
        self.assertIsNotNone(target)
        self.assertEqual(target.get("last_refresh_status"), "failed")
        self.assertIn(tag_name, [t.get("name") for t in target.get("tags")])

    def test_system_group_cannot_be_deleted(self):
        client = self.app.test_client()
        login = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(login.status_code, 200)

        conn = self.module.create_sqlite_connection()
        try:
            row = conn.execute("SELECT id FROM groups WHERE is_system = 1 LIMIT 1").fetchone()
            self.assertIsNotNone(row)
            system_group_id = row["id"]
        finally:
            conn.close()

        resp = client.delete(f"/api/groups/{system_group_id}")
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "SYSTEM_GROUP_PROTECTED")
        self.assertEqual(data["error"].get("status"), 403)
        self.assertEqual(data["error"].get("message_en"), "System groups cannot be deleted")

    def test_account_cannot_be_moved_to_system_group_via_update(self):
        client = self.app.test_client()
        login = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(login.status_code, 200)

        unique = uuid.uuid4().hex
        email_addr = f"move_{unique}@example.com"

        conn = self.module.create_sqlite_connection()
        try:
            system_row = conn.execute("SELECT id FROM groups WHERE is_system = 1 LIMIT 1").fetchone()
            self.assertIsNotNone(system_row)
            system_group_id = system_row["id"]

            cur = conn.execute(
                """
                INSERT INTO accounts (email, password, client_id, refresh_token, group_id, remark, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (email_addr, "", "client", "rt", 1, "", "active"),
            )
            account_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()

        resp = client.put(
            f"/api/accounts/{account_id}",
            json={"email": email_addr, "group_id": system_group_id},
        )
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertEqual(data.get("success"), False)
        self.assertIsInstance(data.get("error"), dict)
        self.assertEqual(data["error"].get("code"), "SYSTEM_GROUP_PROTECTED")
        self.assertEqual(data["error"].get("status"), 403)
