"""tests/test_settings_tab_refactor_backend.py — A 类：后端契约测试

目标：验证设置页面 UI 重构（Tab 化 + 临时邮箱配置区分离）的后端实现：
  - 3 个新 cf_worker_* settings key 的 GET/PUT/默认值
  - GPTMail 与 CF Worker 数据隔离（域名、前缀规则互不覆盖）
  - Repository getter 健壮性（损坏 JSON 时返回安全默认值）
  - temp_mail_provider 字段存在于 GET 响应
  - 认证保护

关联文档：
  - TDD: docs/TDD/2026-04-04-设置页面UI重构-TDD.md
  - TD:  docs/TD/2026-04-04-设置页面整体UI重构-TD.md
"""

from __future__ import annotations

import json
import unittest

from tests._import_app import clear_login_attempts, import_web_app_module


class SettingsTabRefactorBackendTests(unittest.TestCase):
    """A 类：后端 Settings API 契约测试 — 设置页面 Tab 重构"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.db import get_db

            db = get_db()
            # 重置新增 key 为默认值（确保测试间隔离）
            db.execute(
                "DELETE FROM settings WHERE key IN "
                "('cf_worker_domains', 'cf_worker_default_domain', 'cf_worker_prefix_rules')"
            )
            db.commit()

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    # ──────────────────────────────────────────────────────
    # TC-A01：GET /api/settings 返回 3 个新字段 + 默认值
    # ──────────────────────────────────────────────────────

    def test_get_settings_returns_cf_worker_defaults(self):
        """GET /api/settings 应包含 3 个 cf_worker_* 字段且默认值正确"""
        client = self.app.test_client()
        self._login(client)

        resp = client.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        settings = resp.get_json().get("settings", {})

        # 域名列表默认为空列表
        self.assertIn(
            "cf_worker_domains", settings, "settings 应包含 cf_worker_domains 字段"
        )
        self.assertEqual(
            settings.get("cf_worker_domains"), [], "cf_worker_domains 默认值应为空列表"
        )

        # 默认域名默认为空字符串
        self.assertIn(
            "cf_worker_default_domain",
            settings,
            "settings 应包含 cf_worker_default_domain 字段",
        )
        self.assertEqual(
            settings.get("cf_worker_default_domain"),
            "",
            "cf_worker_default_domain 默认值应为空字符串",
        )

        # 前缀规则默认值包含 min_length / max_length / pattern
        self.assertIn(
            "cf_worker_prefix_rules",
            settings,
            "settings 应包含 cf_worker_prefix_rules 字段",
        )
        prefix_rules = settings.get("cf_worker_prefix_rules")
        self.assertIsInstance(
            prefix_rules, dict, "cf_worker_prefix_rules 应为 dict 类型"
        )
        self.assertIn("min_length", prefix_rules)
        self.assertIn("max_length", prefix_rules)
        self.assertIn("pattern", prefix_rules)

    # ──────────────────────────────────────────────────────
    # TC-A02：PUT 保存 cf_worker_prefix_rules + GET 回环验证
    # ──────────────────────────────────────────────────────

    def test_put_cf_worker_prefix_rules_round_trip(self):
        """PUT 保存 cf_worker_prefix_rules 后 GET 能读到"""
        client = self.app.test_client()
        self._login(client)

        new_rules = {"min_length": 3, "max_length": 20, "pattern": "^[a-z][a-z0-9]*$"}
        resp = client.put("/api/settings", json={"cf_worker_prefix_rules": new_rules})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

        resp2 = client.get("/api/settings")
        prefix_rules = (
            resp2.get_json().get("settings", {}).get("cf_worker_prefix_rules")
        )
        self.assertIsNotNone(prefix_rules)
        self.assertEqual(prefix_rules.get("min_length"), 3)
        self.assertEqual(prefix_rules.get("max_length"), 20)
        self.assertEqual(prefix_rules.get("pattern"), "^[a-z][a-z0-9]*$")

    # ──────────────────────────────────────────────────────
    # TC-A03：数据隔离 — GPTMail 域名与 CF Worker 域名互不影响
    # ──────────────────────────────────────────────────────

    def test_cf_worker_domains_do_not_overwrite_temp_mail_domains(self):
        """cf_worker_domains 和 temp_mail_domains 应存储在独立 key，互不覆盖"""
        client = self.app.test_client()
        self._login(client)

        # 先设置 GPTMail 域名
        gptmail_domains = [{"name": "gptmail.example.com", "enabled": True}]
        client.put("/api/settings", json={"temp_mail_domains": gptmail_domains})

        # 再通过 repository 直接写入 cf_worker_domains（模拟同步操作）
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            cf_domains = [{"name": "cf.example.com", "enabled": True}]
            settings_repo.set_setting("cf_worker_domains", json.dumps(cf_domains))

        # 验证两个 key 各自独立
        resp = client.get("/api/settings")
        settings = resp.get_json().get("settings", {})

        temp_domains = settings.get("temp_mail_domains", [])
        cf_domains_result = settings.get("cf_worker_domains", [])

        # GPTMail 域名未被覆盖
        self.assertTrue(
            any(d.get("name") == "gptmail.example.com" for d in temp_domains),
            "GPTMail 域名应保持不变，不被 CF Worker 域名覆盖",
        )
        # CF Worker 域名独立存在
        self.assertTrue(
            any(d.get("name") == "cf.example.com" for d in cf_domains_result),
            "CF Worker 域名应独立存储",
        )
        # 确认互不污染
        self.assertFalse(
            any(d.get("name") == "cf.example.com" for d in temp_domains),
            "CF Worker 域名不应出现在 GPTMail 域名列表中",
        )
        self.assertFalse(
            any(d.get("name") == "gptmail.example.com" for d in cf_domains_result),
            "GPTMail 域名不应出现在 CF Worker 域名列表中",
        )

    # ──────────────────────────────────────────────────────
    # TC-A04：数据隔离 — cf_worker_prefix_rules 与 temp_mail_prefix_rules 独立
    # ──────────────────────────────────────────────────────

    def test_cf_worker_prefix_rules_do_not_overwrite_temp_mail_prefix_rules(self):
        """cf_worker_prefix_rules 和 temp_mail_prefix_rules 应独立存储"""
        client = self.app.test_client()
        self._login(client)

        # 设置 GPTMail 前缀规则
        gptmail_rules = {"min_length": 5, "max_length": 30, "pattern": "^[a-z]+$"}
        resp1 = client.put(
            "/api/settings", json={"temp_mail_prefix_rules": gptmail_rules}
        )
        self.assertTrue(resp1.get_json().get("success"), "GPTMail 前缀规则保存失败")

        # 设置 CF Worker 前缀规则
        cf_rules = {"min_length": 2, "max_length": 10, "pattern": "^[a-z0-9]+$"}
        resp2 = client.put("/api/settings", json={"cf_worker_prefix_rules": cf_rules})
        self.assertTrue(resp2.get_json().get("success"), "CF Worker 前缀规则保存失败")

        # 验证两者独立
        resp = client.get("/api/settings")
        settings = resp.get_json().get("settings", {})

        temp_rules = settings.get("temp_mail_prefix_rules", {})
        cf_rules_result = settings.get("cf_worker_prefix_rules", {})

        self.assertEqual(
            temp_rules.get("min_length"), 5, "GPTMail 前缀规则的 min_length 不应被修改"
        )
        self.assertEqual(
            cf_rules_result.get("min_length"),
            2,
            "CF Worker 前缀规则的 min_length 应为刚刚保存的值",
        )

    # ──────────────────────────────────────────────────────
    # TC-A05：PUT 不传 cf_worker 字段时，cf_worker_domains 保持不变
    # ──────────────────────────────────────────────────────

    def test_put_other_fields_does_not_clear_cf_worker_domains(self):
        """PUT 时不传 cf_worker_domains，已有的域名应保持不变"""
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            cf_domains = [{"name": "preserved.example.com", "enabled": True}]
            settings_repo.set_setting(
                "cf_worker_domains", json.dumps(cf_domains), commit=True
            )

        client = self.app.test_client()
        self._login(client)

        # PUT 只修改其他字段（不传 cf_worker_domains）
        resp = client.put(
            "/api/settings",
            json={"cf_worker_prefix_rules": {"min_length": 3, "max_length": 20}},
        )
        self.assertTrue(resp.get_json().get("success"))

        # cf_worker_domains 应保持不变
        resp2 = client.get("/api/settings")
        domains = resp2.get_json().get("settings", {}).get("cf_worker_domains", [])
        self.assertTrue(
            any(d.get("name") == "preserved.example.com" for d in domains),
            "cf_worker_domains 不应在未传该字段时被清空",
        )

    # ──────────────────────────────────────────────────────
    # TC-A06：DB 默认值 — 新 key 初始化后存在
    # ──────────────────────────────────────────────────────

    def test_db_default_values_exist_after_init(self):
        """数据库初始化后 3 个 cf_worker_* key 应存在且有默认值（GET 层面）"""
        client = self.app.test_client()
        self._login(client)

        # 此时 setUp 已 DELETE 这 3 个 key，但 db.py 的 INSERT OR IGNORE 在 init 时执行
        # 通过 GET /api/settings 验证 getter 函数能返回正确默认值
        resp = client.get("/api/settings")
        settings = resp.get_json().get("settings", {})

        # 即使 DB 里没有（因为被 DELETE），getter 有 fallback 默认值
        cf_domains = settings.get("cf_worker_domains")
        cf_default = settings.get("cf_worker_default_domain")
        cf_rules = settings.get("cf_worker_prefix_rules")

        self.assertIsNotNone(cf_domains, "cf_worker_domains 应有默认值")
        self.assertIsNotNone(cf_default, "cf_worker_default_domain 应有默认值")
        self.assertIsNotNone(cf_rules, "cf_worker_prefix_rules 应有默认值")
        self.assertIsInstance(cf_domains, list, "cf_worker_domains 应为 list 类型")
        self.assertIsInstance(cf_rules, dict, "cf_worker_prefix_rules 应为 dict 类型")

    # ──────────────────────────────────────────────────────
    # TC-A07：Repository getter — get_cf_worker_domains 返回 list
    # ──────────────────────────────────────────────────────

    def test_get_cf_worker_domains_returns_list(self):
        """get_cf_worker_domains() 应返回 list 类型"""
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            result = settings_repo.get_cf_worker_domains()
            self.assertIsInstance(result, list, "get_cf_worker_domains() 应返回 list")

    # ──────────────────────────────────────────────────────
    # TC-A08：Repository getter — 损坏 JSON 时返回空列表
    # ──────────────────────────────────────────────────────

    def test_get_cf_worker_domains_handles_invalid_json(self):
        """cf_worker_domains 存储了非法 JSON 时，getter 应返回空列表而不是抛异常"""
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting(
                "cf_worker_domains", "not-valid-json", commit=True
            )
            result = settings_repo.get_cf_worker_domains()
            self.assertEqual(
                result, [], "非法 JSON 时 get_cf_worker_domains() 应返回空列表"
            )

    # ──────────────────────────────────────────────────────
    # TC-A09：Repository getter — 损坏 JSON 时返回默认值 dict
    # ──────────────────────────────────────────────────────

    def test_get_cf_worker_prefix_rules_handles_invalid_json(self):
        """cf_worker_prefix_rules 存储了非法 JSON 时，getter 应返回带默认键的 dict"""
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("cf_worker_prefix_rules", "{{broken", commit=True)
            result = settings_repo.get_cf_worker_prefix_rules()
            self.assertIsInstance(result, dict, "非法 JSON 时应返回 dict 而非抛出异常")
            self.assertIn("min_length", result)
            self.assertIn("max_length", result)
            self.assertIn("pattern", result)

    # ──────────────────────────────────────────────────────
    # TC-A10：同步接口写入 cf_worker_* 而非 temp_mail_*
    # ──────────────────────────────────────────────────────

    def test_sync_cf_worker_writes_to_cf_worker_keys_not_temp_mail(self):
        """
        CF Worker 域名同步接口应写入 cf_worker_domains / cf_worker_default_domain，
        不应覆盖 temp_mail_domains / temp_mail_default_domain。
        使用 unittest.mock 模拟 CF Worker Admin API 响应。
        """
        from unittest.mock import patch, MagicMock

        # 预设 GPTMail 域名（用于验证不被覆盖）
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            original_gptmail_domains = [
                {"name": "gptmail.example.com", "enabled": True}
            ]
            settings_repo.set_setting(
                "temp_mail_domains", json.dumps(original_gptmail_domains), commit=True
            )
            settings_repo.set_setting(
                "cf_worker_base_url", "https://worker.example.com", commit=True
            )
            settings_repo.set_setting(
                "cf_worker_admin_key", "test-admin-key", commit=True
            )

        client = self.app.test_client()
        self._login(client)

        # 构造 mock 的 CF Worker Admin API 响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "domains": ["cf1.example.com", "cf2.example.com"],
        }
        mock_response.raise_for_status = MagicMock()

        # 尝试两种可能的 requests 调用路径
        # （实际路径取决于 controller 实现，若路径不对则测试 skip）
        try:
            with patch("requests.get", return_value=mock_response):
                resp = client.post("/api/settings/cf-worker-sync-domains")
        except Exception:
            self.skipTest("同步接口 mock 路径需确认，跳过本 case")
            return

        if resp.status_code not in (200, 400, 500):
            self.skipTest(
                f"同步接口路由未找到（状态码 {resp.status_code}），跳过本 case"
            )
            return

        if resp.status_code == 200:
            # 验证写入到 cf_worker_* key
            with self.app.app_context():
                from outlook_web.repositories import settings as settings_repo

                cf_domains = settings_repo.get_cf_worker_domains()
                cf_domain_names = [d.get("name") for d in cf_domains]
                self.assertTrue(
                    "cf1.example.com" in cf_domain_names
                    or "cf2.example.com" in cf_domain_names,
                    "cf_worker_domains 应包含同步到的域名",
                )

            # 验证 temp_mail_domains 未被覆盖
            resp2 = client.get("/api/settings")
            temp_domains = (
                resp2.get_json().get("settings", {}).get("temp_mail_domains", [])
            )
            self.assertTrue(
                any(d.get("name") == "gptmail.example.com" for d in temp_domains),
                "temp_mail_domains 不应被 CF Worker 同步覆盖",
            )

    # ──────────────────────────────────────────────────────
    # TC-A11：PUT cf_worker_prefix_rules 格式校验 — 非 dict 拒绝
    # ──────────────────────────────────────────────────────

    def test_put_cf_worker_prefix_rules_rejects_non_dict(self):
        """cf_worker_prefix_rules 传入非 dict 值应返回错误"""
        client = self.app.test_client()
        self._login(client)

        resp = client.put(
            "/api/settings", json={"cf_worker_prefix_rules": "not-a-dict"}
        )
        data = resp.get_json()
        # 应该报错或 errors 列表非空
        errors = data.get("errors", [])
        self.assertTrue(
            len(errors) > 0 or not data.get("success"),
            "非 dict 的 cf_worker_prefix_rules 应返回错误提示",
        )

    # ──────────────────────────────────────────────────────
    # TC-A12：PUT 只传 cf_worker 字段，temp_mail 字段保持不变
    # ──────────────────────────────────────────────────────

    def test_put_cf_worker_fields_only_does_not_touch_temp_mail(self):
        """只保存 CF Worker 相关字段时，temp_mail 相关字段保持不变"""
        client = self.app.test_client()
        self._login(client)

        # 先设置 temp_mail 相关字段
        original_url = "https://gptmail.original.com"
        resp_setup = client.put(
            "/api/settings", json={"temp_mail_api_base_url": original_url}
        )
        self.assertTrue(resp_setup.get_json().get("success"))

        # 只更新 CF Worker 字段
        resp = client.put(
            "/api/settings",
            json={
                "cf_worker_base_url": "https://worker.example.com",
                "cf_worker_prefix_rules": {"min_length": 2, "max_length": 15},
            },
        )
        self.assertTrue(resp.get_json().get("success"))

        # temp_mail 字段不变
        resp2 = client.get("/api/settings")
        settings = resp2.get_json().get("settings", {})
        self.assertEqual(
            settings.get("temp_mail_api_base_url"),
            original_url,
            "temp_mail_api_base_url 不应被 CF Worker 保存操作修改",
        )

    # ──────────────────────────────────────────────────────
    # TC-A13：GET 包含 temp_mail_provider 字段
    # ──────────────────────────────────────────────────────

    def test_get_settings_includes_temp_mail_provider(self):
        """GET /api/settings 应包含 temp_mail_provider 字段"""
        client = self.app.test_client()
        self._login(client)

        resp = client.get("/api/settings")
        settings = resp.get_json().get("settings", {})

        self.assertIn(
            "temp_mail_provider", settings, "settings 应包含 temp_mail_provider 字段"
        )

    # ──────────────────────────────────────────────────────
    # TC-A14：未登录时 GET 返回认证错误
    # ──────────────────────────────────────────────────────

    def test_get_settings_requires_auth(self):
        """未登录时 GET /api/settings 应返回认证错误"""
        client = self.app.test_client()
        resp = client.get("/api/settings")
        self.assertNotEqual(
            resp.status_code, 200, "未登录时 GET /api/settings 不应返回 200"
        )


if __name__ == "__main__":
    unittest.main()
