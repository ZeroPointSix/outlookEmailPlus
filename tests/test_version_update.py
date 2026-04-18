"""
版本更新检测与一键更新 — 后端单元测试

覆盖范围：
- _version_gt 版本比较工具函数
- api_version_check: 正常更新/无更新/GitHub 不可达降级/缓存 TTL/字段名校验
- api_trigger_update: 未配置 token/Watchtower 成功/Watchtower 非200/连接失败/异常兜底
- 路由注册: GET /api/system/version-check, POST /api/system/trigger-update
- 鉴权: 未登录时两个接口均拦截
- HTML 模板: Banner 在 body 顶部，包含正确 id
- CSS: version-update-banner 样式存在
- .env.example: 环境变量名正确
"""

import json
import os
import re
import time
import unittest
from unittest.mock import MagicMock, patch

from tests._import_app import clear_login_attempts, import_web_app_module

# urllib 在被测函数内部 import，需要 patch 标准库路径
URLOPEN_PATH = "urllib.request.urlopen"


def _mock_github_response(tag_name="v2.0.0", html_url="https://github.com/test"):
    """构造 mock urlopen 返回值"""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(
        {
            "tag_name": tag_name,
            "html_url": html_url,
        }
    ).encode()
    mock_resp.__enter__ = lambda s: mock_resp
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _mock_watchtower_response(status=200):
    """构造 mock urlopen 返回值（Watchtower）"""
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.__enter__ = lambda s: mock_resp
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class VersionGtTests(unittest.TestCase):
    """_version_gt 版本比较"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def _import_fn(self):
        from outlook_web.controllers.system import _version_gt

        return _version_gt

    def test_major_greater(self):
        gt = self._import_fn()
        self.assertTrue(gt("2.0.0", "1.9.9"))

    def test_minor_greater(self):
        gt = self._import_fn()
        self.assertTrue(gt("1.10.0", "1.9.9"))

    def test_patch_greater(self):
        gt = self._import_fn()
        self.assertTrue(gt("1.0.2", "1.0.1"))

    def test_equal_returns_false(self):
        gt = self._import_fn()
        self.assertFalse(gt("1.0.0", "1.0.0"))

    def test_less_returns_false(self):
        gt = self._import_fn()
        self.assertFalse(gt("1.0.0", "1.0.1"))

    def test_invalid_version_returns_false(self):
        gt = self._import_fn()
        self.assertFalse(gt("abc", "1.0.0"))

    def test_none_safe(self):
        gt = self._import_fn()
        self.assertFalse(gt("1.0.0", "not-a-version"))

    def test_two_segment(self):
        gt = self._import_fn()
        self.assertTrue(gt("1.10", "1.9"))


class VersionCheckAPITests(unittest.TestCase):
    """api_version_check 接口"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
        # 每次测试前清除模块级缓存
        import outlook_web.controllers.system as sc

        sc._version_cache = None
        sc._version_cache_at = 0.0

    def _login(self, client):
        resp = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(resp.status_code, 200)

    def test_route_get_version_check(self):
        """路由: GET /api/system/version-check 注册存在"""
        client = self.app.test_client()
        self._login(client)
        with patch(URLOPEN_PATH) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(
                {
                    "tag_name": "v0.0.1",
                    "html_url": "https://github.com/test",
                }
            ).encode()
            mock_resp.__enter__ = lambda s: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            resp = client.get("/api/system/version-check")
        self.assertEqual(resp.status_code, 200)

    def test_has_update_true_when_newer(self):
        """GitHub 有更高版本时 has_update=True"""
        client = self.app.test_client()
        self._login(client)
        with patch(URLOPEN_PATH) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(
                {
                    "tag_name": "v99.0.0",
                    "html_url": "https://github.com/hshaokang/outlookemail-plus/releases/tag/v99.0.0",
                }
            ).encode()
            mock_resp.__enter__ = lambda s: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            resp = client.get("/api/system/version-check")
        data = resp.get_json()
        self.assertTrue(data["has_update"])
        self.assertEqual(data["latest_version"], "99.0.0")
        self.assertEqual(data["current_version"], "2.0.0")
        self.assertTrue(data["success"])

    def test_has_update_false_when_same(self):
        """GitHub 版本相同时 has_update=False"""
        client = self.app.test_client()
        self._login(client)
        with patch(URLOPEN_PATH) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(
                {
                    "tag_name": "v2.0.0",
                    "html_url": "https://github.com/test",
                }
            ).encode()
            mock_resp.__enter__ = lambda s: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            resp = client.get("/api/system/version-check")
        data = resp.get_json()
        self.assertFalse(data["has_update"])
        self.assertEqual(data["latest_version"], "2.0.0")

    def test_has_update_false_when_older(self):
        """GitHub 版本更低时 has_update=False"""
        client = self.app.test_client()
        self._login(client)
        with patch(URLOPEN_PATH) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(
                {
                    "tag_name": "v0.1.0",
                    "html_url": "https://github.com/test",
                }
            ).encode()
            mock_resp.__enter__ = lambda s: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            resp = client.get("/api/system/version-check")
        data = resp.get_json()
        self.assertFalse(data["has_update"])

    def test_degradation_when_github_unreachable(self):
        """GitHub API 不可达时静默降级，返回 has_update=False"""
        client = self.app.test_client()
        self._login(client)
        with patch(
            URLOPEN_PATH,
            side_effect=Exception("network error"),
        ):
            resp = client.get("/api/system/version-check")
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertFalse(data["has_update"])
        self.assertEqual(data["current_version"], "2.0.0")
        self.assertEqual(data["latest_version"], "2.0.0")
        self.assertEqual(data["release_url"], "")

    def test_response_field_names(self):
        """响应字段名必须是 current_version/latest_version，不含旧字段"""
        client = self.app.test_client()
        self._login(client)
        with patch(URLOPEN_PATH) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(
                {
                    "tag_name": "v2.0.0",
                    "html_url": "https://github.com/test",
                }
            ).encode()
            mock_resp.__enter__ = lambda s: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            resp = client.get("/api/system/version-check")
        data = resp.get_json()
        # 必须存在
        self.assertIn("current_version", data)
        self.assertIn("latest_version", data)
        self.assertIn("has_update", data)
        self.assertIn("success", data)
        self.assertIn("release_url", data)
        # 禁止旧字段（精确匹配，不含 current_version/latest_version）
        for key in data:
            self.assertNotEqual(key, "current", "不应有 current 字段（应为 current_version）")
            self.assertNotEqual(key, "latest", "不应有 latest 字段（应为 latest_version）")

    def test_cache_ttl(self):
        """缓存 TTL=600s：第二次请求不调 GitHub API"""
        client = self.app.test_client()
        self._login(client)

        call_count = 0

        def fake_urlopen(*a, **kw):
            nonlocal call_count
            call_count += 1
            return _mock_github_response("v2.0.0")

        with patch(URLOPEN_PATH, side_effect=fake_urlopen):
            resp1 = client.get("/api/system/version-check")
            data1 = resp1.get_json()
            self.assertEqual(call_count, 1)

            resp2 = client.get("/api/system/version-check")
            data2 = resp2.get_json()
            self.assertEqual(call_count, 1, "第二次应命中缓存，不再调 GitHub")

            self.assertEqual(data1, data2)

    def test_cache_expires_after_ttl(self):
        """缓存过期后重新调 GitHub API"""
        import outlook_web.controllers.system as sc

        original_ttl = sc._VERSION_CACHE_TTL
        try:
            sc._VERSION_CACHE_TTL = 0  # 立即过期

            client = self.app.test_client()
            self._login(client)

            call_count = 0

            def fake_urlopen(*a, **kw):
                nonlocal call_count
                call_count += 1
                return _mock_github_response("v2.0.0")

            with patch(URLOPEN_PATH, side_effect=fake_urlopen):
                client.get("/api/system/version-check")
                client.get("/api/system/version-check")
                self.assertEqual(call_count, 2, "TTL=0 时每次都应调 GitHub")
        finally:
            sc._VERSION_CACHE_TTL = original_ttl

    def test_github_api_url_correct(self):
        """GitHub API URL 使用 ZeroPointSix/outlookEmailPlus"""
        client = self.app.test_client()
        self._login(client)
        with patch(URLOPEN_PATH) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(
                {
                    "tag_name": "v1.0.0",
                    "html_url": "",
                }
            ).encode()
            mock_resp.__enter__ = lambda s: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            client.get("/api/system/version-check")

            # 验证请求 URL
            args = mock_urlopen.call_args
            req_obj = args[0][0]
            self.assertIn("ZeroPointSix/outlookEmailPlus", req_obj.full_url)

    def test_github_user_agent_header(self):
        """GitHub API 请求包含 User-Agent"""
        client = self.app.test_client()
        self._login(client)
        with patch(URLOPEN_PATH) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(
                {
                    "tag_name": "v1.0.0",
                    "html_url": "",
                }
            ).encode()
            mock_resp.__enter__ = lambda s: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            client.get("/api/system/version-check")

            req_obj = mock_urlopen.call_args[0][0]
            self.assertEqual(req_obj.get_header("User-agent"), "outlook-email-plus")


class TriggerUpdateAPITests(unittest.TestCase):
    """api_trigger_update 接口"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()

    def _login(self, client):
        resp = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(resp.status_code, 200)

    def test_route_post_trigger_update(self):
        """路由: POST /api/system/trigger-update 注册存在"""
        client = self.app.test_client()
        self._login(client)
        resp = client.post("/api/system/trigger-update")
        # 至少不是 404/405
        self.assertIn(resp.status_code, (200, 500, 502, 503))

    def test_no_token_returns_500(self):
        """未配置 WATCHTOWER_HTTP_API_TOKEN 时返回 500"""
        client = self.app.test_client()
        self._login(client)
        with patch.dict(os.environ, {"WATCHTOWER_HTTP_API_TOKEN": ""}, clear=False):
            resp = client.post("/api/system/trigger-update")
        self.assertEqual(resp.status_code, 500)
        data = resp.get_json()
        self.assertFalse(data["success"])
        self.assertIn("Token 未配置", data["message"])

    def test_watchtower_success(self):
        """Watchtower 返回 200 时成功"""
        client = self.app.test_client()
        self._login(client)
        with patch.dict(
            os.environ,
            {
                "WATCHTOWER_HTTP_API_TOKEN": "test-token",
                "WATCHTOWER_API_URL": "http://watchtower:8080",
            },
        ):
            with patch(URLOPEN_PATH) as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.status = 200
                mock_resp.read.return_value = b""
                mock_resp.__enter__ = lambda s: mock_resp
                mock_resp.__exit__ = MagicMock(return_value=False)
                mock_urlopen.return_value = mock_resp

                resp = client.post("/api/system/trigger-update")

        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data["success"])
        self.assertTrue(data.get("already_latest"))
        self.assertIn("检查完毕", data["message"])
        # 验证 message_en 字段存在（供前端 pickApiMessage 使用）
        self.assertEqual(data.get("message_en"), "Watchtower check complete, already up to date")

    def test_watchtower_non_200(self):
        """Watchtower 返回非 200 时返回 502"""
        client = self.app.test_client()
        self._login(client)
        with patch.dict(os.environ, {"WATCHTOWER_HTTP_API_TOKEN": "test-token"}):
            with patch(URLOPEN_PATH) as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.status = 403
                mock_resp.read.return_value = b"Forbidden"
                mock_resp.__enter__ = lambda s: mock_resp
                mock_resp.__exit__ = MagicMock(return_value=False)
                mock_urlopen.return_value = mock_resp

                resp = client.post("/api/system/trigger-update")

        self.assertEqual(resp.status_code, 502)
        data = resp.get_json()
        self.assertFalse(data["success"])

    def test_watchtower_connection_refused(self):
        """Watchtower 连接失败时返回 503"""
        import urllib.error

        client = self.app.test_client()
        self._login(client)
        with patch.dict(os.environ, {"WATCHTOWER_HTTP_API_TOKEN": "test-token"}):
            with patch(
                URLOPEN_PATH,
                side_effect=urllib.error.URLError("Connection refused"),
            ):
                resp = client.post("/api/system/trigger-update")

        self.assertEqual(resp.status_code, 503)
        data = resp.get_json()
        self.assertFalse(data["success"])
        self.assertIn("无法连接 Watchtower", data["message"])

    def test_watchtower_generic_exception(self):
        """Watchtower 其他异常时返回 500"""
        client = self.app.test_client()
        self._login(client)
        with patch.dict(os.environ, {"WATCHTOWER_HTTP_API_TOKEN": "test-token"}):
            with patch(
                URLOPEN_PATH,
                side_effect=RuntimeError("unexpected"),
            ):
                resp = client.post("/api/system/trigger-update")

        self.assertEqual(resp.status_code, 500)
        data = resp.get_json()
        self.assertFalse(data["success"])

    def test_authorization_header_bearer_token(self):
        """请求 Watchtower 时 Authorization 头格式正确"""
        client = self.app.test_client()
        self._login(client)
        with patch.dict(
            os.environ,
            {
                "WATCHTOWER_HTTP_API_TOKEN": "my-secret-token",
                "WATCHTOWER_API_URL": "http://wt:8080",
            },
        ):
            with patch(URLOPEN_PATH) as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.status = 200
                mock_resp.read.return_value = b""
                mock_resp.__enter__ = lambda s: mock_resp
                mock_resp.__exit__ = MagicMock(return_value=False)
                mock_urlopen.return_value = mock_resp

                client.post("/api/system/trigger-update")

                req_obj = mock_urlopen.call_args[0][0]
                self.assertEqual(req_obj.get_header("Authorization"), "Bearer my-secret-token")
                self.assertIn("wt:8080/v1/update", req_obj.full_url)

    def test_env_var_names(self):
        """使用正确的环境变量名 WATCHTOWER_API_URL + WATCHTOWER_HTTP_API_TOKEN"""
        client = self.app.test_client()
        self._login(client)
        with patch.dict(
            os.environ,
            {
                "WATCHTOWER_HTTP_API_TOKEN": "tok",
                "WATCHTOWER_API_URL": "http://custom:9999",
            },
        ):
            with patch(URLOPEN_PATH) as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.status = 200
                mock_resp.read.return_value = b""
                mock_resp.__enter__ = lambda s: mock_resp
                mock_resp.__exit__ = MagicMock(return_value=False)
                mock_urlopen.return_value = mock_resp

                client.post("/api/system/trigger-update")

                req_obj = mock_urlopen.call_args[0][0]
                self.assertIn("custom:9999/v1/update", req_obj.full_url)


class AuthProtectionTests(unittest.TestCase):
    """未登录时接口鉴权拦截"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()

    def test_version_check_requires_login(self):
        """未登录 GET /api/system/version-check 返回 401"""
        client = self.app.test_client()
        resp = client.get("/api/system/version-check")
        self.assertEqual(resp.status_code, 401)

    def test_trigger_update_requires_login(self):
        """未登录 POST /api/system/trigger-update 返回 401"""
        client = self.app.test_client()
        resp = client.post("/api/system/trigger-update")
        self.assertEqual(resp.status_code, 401)


class HTMLTemplateTests(unittest.TestCase):
    """HTML 模板中 Banner 结构校验"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()

    def _login(self, client):
        resp = client.post("/login", json={"password": "testpass123"})
        self.assertEqual(resp.status_code, 200)

    def test_banner_in_body_before_app(self):
        """Banner div 在 body 顶部、#app 之前"""
        client = self.app.test_client()
        self._login(client)
        resp = client.get("/")
        html = resp.get_data(as_text=True)
        body_start = html.index("<body>")
        banner_pos = html.index('id="versionUpdateBanner"')
        app_pos = html.index('id="app"')
        self.assertGreater(banner_pos, body_start, "Banner 应在 body 内")
        self.assertLess(banner_pos, app_pos, "Banner 应在 #app 之前")

    def test_banner_default_hidden(self):
        """Banner 默认有 d-none class"""
        client = self.app.test_client()
        self._login(client)
        resp = client.get("/")
        html = resp.get_data(as_text=True)
        self.assertIn('class="version-update-banner d-none"', html)

    def test_banner_has_correct_ids(self):
        """Banner 包含正确的 id"""
        client = self.app.test_client()
        self._login(client)
        resp = client.get("/")
        html = resp.get_data(as_text=True)
        self.assertIn('id="versionUpdateBanner"', html)
        self.assertIn('id="versionUpdateMsg"', html)
        self.assertIn('id="btnTriggerUpdate"', html)

    def test_banner_has_trigger_and_dismiss_buttons(self):
        """Banner 包含"立即更新"和"忽略"按钮"""
        client = self.app.test_client()
        self._login(client)
        resp = client.get("/")
        html = resp.get_data(as_text=True)
        self.assertIn("triggerUpdate()", html)
        self.assertIn("dismissVersionBanner()", html)
        self.assertIn("立即更新", html)
        self.assertIn("忽略", html)

    def test_sidebar_has_version_number(self):
        """侧边栏显示版本号"""
        client = self.app.test_client()
        self._login(client)
        resp = client.get("/")
        html = resp.get_data(as_text=True)
        self.assertIn("v2.0.0", html)


class CSSStyleTests(unittest.TestCase):
    """CSS 样式校验"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def test_banner_style_exists(self):
        """version-update-banner 样式存在"""
        client = self.app.test_client()
        resp = client.get("/static/css/main.css")
        css = resp.get_data(as_text=True)
        self.assertIn(".version-update-banner", css)

    def test_banner_fixed_position(self):
        """Banner 使用 position: fixed"""
        client = self.app.test_client()
        resp = client.get("/static/css/main.css")
        css = resp.get_data(as_text=True)
        self.assertIn("position: fixed", css)

    def test_banner_top_zero(self):
        """Banner top: 0"""
        client = self.app.test_client()
        resp = client.get("/static/css/main.css")
        css = resp.get_data(as_text=True)
        # 在 .version-update-banner 块内找 top: 0
        idx = css.index(".version-update-banner")
        block_end = css.index("}", idx)
        block = css[idx:block_end]
        self.assertIn("top: 0", block)

    def test_banner_zindex_high(self):
        """Banner z-index 足够高"""
        client = self.app.test_client()
        resp = client.get("/static/css/main.css")
        css = resp.get_data(as_text=True)
        idx = css.index(".version-update-banner")
        block_end = css.index("}", idx)
        block = css[idx:block_end]
        self.assertIn("z-index: 9999", block)

    def test_dnone_display_none(self):
        """.version-update-banner.d-none 使用 display: none"""
        client = self.app.test_client()
        resp = client.get("/static/css/main.css")
        css = resp.get_data(as_text=True)
        self.assertIn(".version-update-banner.d-none", css)
        self.assertIn("display: none", css)


class JSContractTests(unittest.TestCase):
    """JS 前端代码契约校验"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def _get_js(self):
        client = self.app.test_client()
        resp = client.get("/static/js/main.js")
        return resp.get_data(as_text=True)

    def test_check_version_update_function(self):
        """checkVersionUpdate 函数存在"""
        js = self._get_js()
        self.assertIn("async function checkVersionUpdate()", js)

    def test_trigger_update_function(self):
        """triggerUpdate 函数存在"""
        js = self._get_js()
        self.assertIn("async function triggerUpdate()", js)

    def test_dismiss_version_banner_function(self):
        """dismissVersionBanner 函数存在"""
        js = self._get_js()
        self.assertIn("function dismissVersionBanner()", js)

    def test_get_csrf_token_function(self):
        """getCSRFToken 函数存在"""
        js = self._get_js()
        self.assertIn("function getCSRFToken()", js)

    def test_wait_for_restart_function(self):
        """waitForRestart 函数存在"""
        js = self._get_js()
        self.assertIn("async function waitForRestart()", js)

    def test_uses_current_version_not_current(self):
        """JS 中版本检测使用 data.current_version 而非 data.current"""
        js = self._get_js()
        # 精确定位 checkVersionUpdate 函数体
        idx = js.index("async function checkVersionUpdate()")
        block_end = js.index("\n        function dismissVersionBanner()", idx)
        block = js[idx:block_end]
        self.assertIn("data.current_version", block)
        self.assertIn("data.latest_version", block)
        # 禁止出现 data.current（不后跟 _version）和 data.latest（不后跟 _version）
        bare_current = re.findall(r"data\.current(?!_version)", block)
        bare_latest = re.findall(r"data\.latest(?!_version)", block)
        self.assertEqual(
            bare_current,
            [],
            f"不应有 data.current（应为 data.current_version）: {bare_current}",
        )
        self.assertEqual(
            bare_latest,
            [],
            f"不应有 data.latest（应为 data.latest_version）: {bare_latest}",
        )

    def test_trigger_uses_csrf_token(self):
        """triggerUpdate 请求包含 CSRFToken"""
        js = self._get_js()
        idx = js.index("async function triggerUpdate()")
        block_end = js.index("async function waitForRestart()", idx)
        block = js[idx:block_end]
        self.assertIn("X-CSRFToken", block)
        self.assertIn("getCSRFToken()", block)

    def test_wait_for_restart_polls_healthz(self):
        """waitForRestart 轮询 /healthz"""
        js = self._get_js()
        idx = js.index("async function waitForRestart()")
        block_end = len(js)
        block = js[idx:block_end]
        self.assertIn("/healthz", block)
        self.assertIn("90000", block)  # MAX_WAIT_MS
        self.assertIn("3000", block)  # POLL_INTERVAL_MS

    def test_no_show_update_guide(self):
        """不包含旧的 showUpdateGuide 函数"""
        js = self._get_js()
        self.assertNotIn("showUpdateGuide", js)

    def test_no_auto_update_enabled(self):
        """不包含旧的 auto_update_enabled"""
        js = self._get_js()
        self.assertNotIn("auto_update_enabled", js)

    def test_banner_padding_top_on_show(self):
        """显示 Banner 时设置 #app padding-top"""
        js = self._get_js()
        idx = js.index("async function checkVersionUpdate()")
        block_end = js.index("function dismissVersionBanner()", idx)
        block = js[idx:block_end]
        self.assertIn("paddingTop", block)

    def test_banner_padding_clear_on_dismiss(self):
        """忽略 Banner 时清除 #app padding-top"""
        js = self._get_js()
        idx = js.index("function dismissVersionBanner()")
        block_end = js.index("async function triggerUpdate()", idx)
        block = js[idx:block_end]
        self.assertIn("paddingTop = ''", block)


class EnvExampleTests(unittest.TestCase):
    """.env.example 环境变量名校验"""

    def test_watchtower_env_vars(self):
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env.example")
        if not os.path.exists(env_path):
            self.skipTest(".env.example not found")
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("WATCHTOWER_API_URL", content)
        self.assertIn("WATCHTOWER_HTTP_API_TOKEN", content)
        # 旧变量名不应存在
        self.assertNotIn("WATCHTOWER_BASE_URL", content)
        # WATCHTOWER_API_TOKEN（不含 HTTP）不应出现
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertFalse(
                re.match(r"^WATCHTOWER_API_TOKEN\s*=", stripped),
                f"不应有 WATCHTOWER_API_TOKEN（应为 WATCHTOWER_HTTP_API_TOKEN）: {stripped}",
            )


if __name__ == "__main__":
    unittest.main()
