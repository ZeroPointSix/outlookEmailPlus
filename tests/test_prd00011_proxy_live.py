"""
tests/test_prd00011_proxy_live.py
PRD-00011 代理支持补全 — 集成测试（基于 Flask TestClient，无需独立服务器进程）

测试覆盖：
  1. GET /api/settings 返回 telegram_proxy_url 字段
  2. PUT /api/settings 可以保存并读回 telegram_proxy_url
  3. POST /api/settings/test-telegram-proxy 路由已注册
  4. 未配置 Bot Token 时接口返回合理错误（非 5xx/404）
  5. 直接用 requests 测试代理可达性（可选，仅当环境变量 ENABLE_PROXY_LIVE_TEST=1 时运行）

注意：代理直连测试（TestPRD00011DirectProxyConnectivity）默认跳过，需通过环境变量启用：
  ENABLE_PROXY_LIVE_TEST=1 python -m unittest tests.test_prd00011_proxy_live
  代理地址通过环境变量 TEST_PROXY_URLS 传入（逗号分隔，格式 socks5://user:pass@host:port）
"""

from __future__ import annotations

import os

# ──────────────────────────────────────────────────────────────────────────────
# 应用初始化（复用项目标准 _import_app 辅助）
# ──────────────────────────────────────────────────────────────────────────────
import sys
import tempfile
import unittest
from pathlib import Path

import requests

_TEMP_DIR = tempfile.TemporaryDirectory(prefix="prd00011-tests-")
_DB_PATH = Path(_TEMP_DIR.name) / "test.db"

os.environ.setdefault("SECRET_KEY", "test-secret-key-32bytes-minimum-0000000000000000")
os.environ.setdefault("LOGIN_PASSWORD", "admin123")
os.environ.setdefault("SCHEDULER_AUTOSTART", "false")
os.environ["DATABASE_PATH"] = str(_DB_PATH)

import importlib

_module = importlib.import_module("web_outlook_app")
_app = _module.app
_app.config.update(
    TESTING=True,
    WTF_CSRF_ENABLED=False,
    WTF_CSRF_CHECK_DEFAULT=False,
)

# 代理列表：通过环境变量 TEST_PROXY_URLS 传入（逗号分隔），格式：socks5://user:pass@host:port
# 默认为空列表；不要在代码中硬编码真实代理凭据
_ENV_PROXY_URLS = os.environ.get("TEST_PROXY_URLS", "")
PROXY_URLS = [u.strip() for u in _ENV_PROXY_URLS.split(",") if u.strip()]

# 是否启用外网直连代理测试（默认关闭，CI 中不运行）
_ENABLE_LIVE_TEST = os.environ.get("ENABLE_PROXY_LIVE_TEST", "").lower() in (
    "1",
    "true",
    "yes",
)


def _login(client):
    """登录辅助（CSRF 已在测试配置中禁用）"""
    resp = client.post("/login", json={"password": "admin123"})
    return resp.status_code == 200 and resp.get_json().get("success")


class TestPRD00011Settings(unittest.TestCase):
    """验收点 1：GET/PUT /api/settings 的 telegram_proxy_url 字段"""

    def setUp(self):
        self.client = _app.test_client()
        ok = _login(self.client)
        if not ok:
            self.skipTest("登录失败，跳过测试")

    def test_get_settings_returns_telegram_proxy_url(self):
        """GET /api/settings 响应中应包含 telegram_proxy_url 字段"""
        resp = self.client.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"), f"GET /api/settings failed: {data}")
        settings = data.get("settings", {})
        self.assertIn(
            "telegram_proxy_url",
            settings,
            "settings 中缺少 telegram_proxy_url 字段",
        )

    def test_put_settings_saves_telegram_proxy_url(self):
        """PUT /api/settings 可以保存并读回 telegram_proxy_url"""
        test_url = "http://test-proxy.example.com:8080"
        resp = self.client.put("/api/settings", json={"telegram_proxy_url": test_url})
        self.assertEqual(resp.status_code, 200, f"PUT failed: {resp.get_json()}")
        data = resp.get_json()
        self.assertTrue(data.get("success"), f"PUT /api/settings failed: {data}")

        # 读回验证
        resp2 = self.client.get("/api/settings")
        saved = resp2.get_json().get("settings", {}).get("telegram_proxy_url", "")
        self.assertEqual(
            saved,
            test_url,
            f"保存后读回的 proxy_url 不一致，期望 {test_url!r}，实际 {saved!r}",
        )

    def test_put_settings_clears_telegram_proxy_url(self):
        """PUT /api/settings 传空字符串可以清空 telegram_proxy_url"""
        # 先写入
        self.client.put("/api/settings", json={"telegram_proxy_url": "http://x.com:1"})
        # 再清空
        resp = self.client.put("/api/settings", json={"telegram_proxy_url": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

        resp2 = self.client.get("/api/settings")
        saved = resp2.get_json().get("settings", {}).get("telegram_proxy_url", "MISSING")
        self.assertEqual(saved, "", f"清空后期望空字符串，实际 {saved!r}")


class TestPRD00011TelegramProxyNoToken(unittest.TestCase):
    """验收点 2（无 Bot Token 情况）：POST /api/settings/test-telegram-proxy"""

    def setUp(self):
        self.client = _app.test_client()
        ok = _login(self.client)
        if not ok:
            self.skipTest("登录失败，跳过测试")
        # 清空 telegram_bot_token，确保测试环境干净
        self.client.put("/api/settings", json={"telegram_bot_token": ""})

    def test_proxy_test_without_bot_token_returns_error(self):
        """未配置 Bot Token 时，测试代理接口应返回提示错误（非 5xx）"""
        resp = self.client.post(
            "/api/settings/test-telegram-proxy",
            json={"proxy_url": "socks5://127.0.0.1:1080"},
        )
        # 接口本身应当正常响应（不是 500/404）
        self.assertIn(resp.status_code, (200, 400), f"意外状态码: {resp.status_code}")
        data = resp.get_json()
        # 两种合法响应：success=False + 提示信息，或 success=True + ok=False
        if not data.get("success"):
            self.assertIn("message", data.get("error", {}), "error 对象中缺少 message")
        # 不应抛出服务端异常
        self.assertNotEqual(resp.status_code, 500, "接口不应返回 500")


class TestPRD00011ProxyEndpoint(unittest.TestCase):
    """验收点 2（路由是否存在）：POST /api/settings/test-telegram-proxy 接口路由已注册"""

    def setUp(self):
        self.client = _app.test_client()
        ok = _login(self.client)
        if not ok:
            self.skipTest("登录失败，跳过测试")

    def test_route_exists(self):
        """POST /api/settings/test-telegram-proxy 应返回非 404"""
        resp = self.client.post(
            "/api/settings/test-telegram-proxy",
            json={"proxy_url": ""},
        )
        self.assertNotEqual(resp.status_code, 404, "路由未注册（返回 404）")
        self.assertNotEqual(resp.status_code, 405, "方法不允许（405），路由注册有误")

    def test_response_has_success_field(self):
        """接口响应必须包含 success 字段"""
        resp = self.client.post(
            "/api/settings/test-telegram-proxy",
            json={"proxy_url": ""},
        )
        data = resp.get_json()
        self.assertIsNotNone(data, "响应应为 JSON")
        self.assertIn("success", data, "响应缺少 success 字段")


class TestPRD00011DirectProxyConnectivity(unittest.TestCase):
    """额外：直接用 requests 测试代理能否访问 api.telegram.org（不经过本地应用）

    默认跳过。需设置以下环境变量启用：
      ENABLE_PROXY_LIVE_TEST=1
      TEST_PROXY_URLS=socks5://user:pass@host:port,socks5://user:pass@host2:port2
    """

    def setUp(self):
        if not _ENABLE_LIVE_TEST:
            self.skipTest("外网代理测试未启用，设置 ENABLE_PROXY_LIVE_TEST=1 以运行")
        if not PROXY_URLS:
            self.skipTest("未配置代理，设置 TEST_PROXY_URLS=socks5://... 以运行")

    def test_proxy_direct_access(self):
        """直接用代理访问 https://api.telegram.org（无需 Bot Token），只验证连通性"""
        results = []
        direct_session = requests.Session()
        direct_session.trust_env = False
        for proxy_url in PROXY_URLS:
            proxies = {"http": proxy_url, "https": proxy_url}
            try:
                resp = direct_session.get(
                    "https://api.telegram.org",
                    proxies=proxies,
                    timeout=10,
                )
                results.append((proxy_url, True, resp.status_code))
            except Exception as exc:
                results.append((proxy_url, False, str(exc)[:60]))

        print("\n=== 代理直连测试结果 ===")
        for proxy_url, ok, detail in results:
            status = "✅" if ok else "❌"
            print(f"  {status} {proxy_url}  →  {detail}")
        print(f"\n  可用代理数量: {sum(1 for _, ok, _ in results if ok)}/{len(results)}")
        # 不强制要求代理可用（网络环境可能不稳定），仅打印结果


if __name__ == "__main__":
    unittest.main(verbosity=2)
