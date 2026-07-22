"""
A 层：IMAP OAuth Token 短期缓存测试

验证 imap.py 模块级 token 缓存的命中/未命中/过期/key 隔离行为。
对应 TDD 矩阵 T-01 ~ T-08。

注意：缓存功能尚未实现，本测试先行编写（TDD 红灯阶段）。
实现时需在 imap.py 新增 _token_cache / _token_cache_lock / clear_imap_token_cache。
"""

import hashlib
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# 辅助常量
# ---------------------------------------------------------------------------
_CLIENT_ID_A = "client-id-aaa"
_CLIENT_ID_B = "client-id-bbb"
_REFRESH_TOKEN_A = "rt-aaa-111"
_REFRESH_TOKEN_B = "rt-bbb-222"
_ACCESS_TOKEN_1 = "access-token-first"
_ACCESS_TOKEN_2 = "access-token-second"


def _make_token_response(access_token: str, expires_in: int = 3599):
    """构造 MS token endpoint 的 mock Response"""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "access_token": access_token,
        "expires_in": expires_in,
        "token_type": "Bearer",
    }
    return resp


def _make_error_response(status: int = 400):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = {"error": "invalid_grant"}
    resp.text = '{"error":"invalid_grant"}'
    resp.headers = {}
    return resp


class TestImapTokenCache(unittest.TestCase):
    """IMAP OAuth Token 缓存测试"""

    def setUp(self):
        """每个测试前清空缓存"""
        try:
            from outlook_web.services.imap import clear_imap_token_cache

            clear_imap_token_cache()
        except ImportError:
            pass

    def tearDown(self):
        try:
            from outlook_web.services.imap import clear_imap_token_cache

            clear_imap_token_cache()
        except ImportError:
            pass

    # T-01: 首次调用 → 请求 MS endpoint
    @patch("outlook_web.services.imap.requests.post")
    def test_first_call_fetches_from_endpoint(self, mock_post):
        from outlook_web.services.imap import get_access_token_imap_result

        mock_post.return_value = _make_token_response(_ACCESS_TOKEN_1)

        result = get_access_token_imap_result(_CLIENT_ID_A, _REFRESH_TOKEN_A)

        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("access_token"), _ACCESS_TOKEN_1)
        self.assertEqual(mock_post.call_count, 1)

    # T-02: 二次调用 → 命中缓存，不再请求
    @patch("outlook_web.services.imap.requests.post")
    def test_second_call_returns_cached_token(self, mock_post):
        from outlook_web.services.imap import get_access_token_imap_result

        mock_post.return_value = _make_token_response(_ACCESS_TOKEN_1)

        result1 = get_access_token_imap_result(_CLIENT_ID_A, _REFRESH_TOKEN_A)
        result2 = get_access_token_imap_result(_CLIENT_ID_A, _REFRESH_TOKEN_A)

        self.assertTrue(result2.get("success"))
        self.assertEqual(result2.get("access_token"), _ACCESS_TOKEN_1)
        # 第二次不应请求 endpoint
        self.assertEqual(mock_post.call_count, 1)

    # T-03: 过期后调用 → 重新请求
    @patch("outlook_web.services.imap.requests.post")
    @patch("outlook_web.services.imap.time.monotonic")
    def test_expired_token_refetches(self, mock_time, mock_post):
        from outlook_web.services.imap import get_access_token_imap_result

        # 第一次调用时间 = 0
        mock_time.return_value = 0.0
        mock_post.return_value = _make_token_response(_ACCESS_TOKEN_1, expires_in=60)

        result1 = get_access_token_imap_result(_CLIENT_ID_A, _REFRESH_TOKEN_A)
        self.assertTrue(result1.get("success"))

        # 时间推进到过期之后（60 - 60 buffer = 0 → 任何正数都过期）
        mock_time.return_value = 61.0
        mock_post.return_value = _make_token_response(_ACCESS_TOKEN_2, expires_in=3599)

        result2 = get_access_token_imap_result(_CLIENT_ID_A, _REFRESH_TOKEN_A)
        self.assertTrue(result2.get("success"))
        self.assertEqual(result2.get("access_token"), _ACCESS_TOKEN_2)
        self.assertEqual(mock_post.call_count, 2)

    # T-04: 不同 refresh_token → 各自独立缓存
    @patch("outlook_web.services.imap.requests.post")
    def test_different_refresh_token_separate_cache(self, mock_post):
        from outlook_web.services.imap import get_access_token_imap_result

        mock_post.side_effect = [
            _make_token_response(_ACCESS_TOKEN_1),
            _make_token_response(_ACCESS_TOKEN_2),
        ]

        r1 = get_access_token_imap_result(_CLIENT_ID_A, _REFRESH_TOKEN_A)
        r2 = get_access_token_imap_result(_CLIENT_ID_A, _REFRESH_TOKEN_B)

        self.assertEqual(r1.get("access_token"), _ACCESS_TOKEN_1)
        self.assertEqual(r2.get("access_token"), _ACCESS_TOKEN_2)
        self.assertEqual(mock_post.call_count, 2)

    # T-05: 不同 client_id → 各自独立缓存
    @patch("outlook_web.services.imap.requests.post")
    def test_different_client_id_separate_cache(self, mock_post):
        from outlook_web.services.imap import get_access_token_imap_result

        mock_post.side_effect = [
            _make_token_response(_ACCESS_TOKEN_1),
            _make_token_response(_ACCESS_TOKEN_2),
        ]

        r1 = get_access_token_imap_result(_CLIENT_ID_A, _REFRESH_TOKEN_A)
        r2 = get_access_token_imap_result(_CLIENT_ID_B, _REFRESH_TOKEN_A)

        self.assertEqual(r1.get("access_token"), _ACCESS_TOKEN_1)
        self.assertEqual(r2.get("access_token"), _ACCESS_TOKEN_2)
        self.assertEqual(mock_post.call_count, 2)

    # T-06: 手动清除后重新请求
    @patch("outlook_web.services.imap.requests.post")
    def test_clear_cache_forces_refetch(self, mock_post):
        from outlook_web.services.imap import (
            clear_imap_token_cache,
            get_access_token_imap_result,
        )

        mock_post.return_value = _make_token_response(_ACCESS_TOKEN_1)

        get_access_token_imap_result(_CLIENT_ID_A, _REFRESH_TOKEN_A)
        clear_imap_token_cache()

        mock_post.return_value = _make_token_response(_ACCESS_TOKEN_2)
        r2 = get_access_token_imap_result(_CLIENT_ID_A, _REFRESH_TOKEN_A)

        self.assertEqual(r2.get("access_token"), _ACCESS_TOKEN_2)
        self.assertEqual(mock_post.call_count, 2)

    # T-07: refresh_token 轮换 → 旧缓存不命中
    @patch("outlook_web.services.imap.requests.post")
    def test_rotated_refresh_token_misses_cache(self, mock_post):
        from outlook_web.services.imap import get_access_token_imap_result

        mock_post.return_value = _make_token_response(_ACCESS_TOKEN_1)

        get_access_token_imap_result(_CLIENT_ID_A, _REFRESH_TOKEN_A)
        # 使用新 refresh_token（模拟轮换）
        new_rt = "rt-aaa-rotated-999"
        mock_post.return_value = _make_token_response(_ACCESS_TOKEN_2)

        r = get_access_token_imap_result(_CLIENT_ID_A, new_rt)
        self.assertEqual(r.get("access_token"), _ACCESS_TOKEN_2)
        self.assertEqual(mock_post.call_count, 2)

    # T-08b: consumers 失败时回退到 common tenant
    @patch("outlook_web.services.imap.requests.post")
    def test_imap_token_falls_back_to_common_tenant(self, mock_post):
        from outlook_web.services.graph import TOKEN_MODE_IMAP_COMMON
        from outlook_web.services.imap import get_access_token_imap_result

        mock_post.side_effect = [
            _make_error_response(400),
            _make_token_response(_ACCESS_TOKEN_2),
        ]

        result = get_access_token_imap_result(_CLIENT_ID_A, _REFRESH_TOKEN_A)

        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("access_token"), _ACCESS_TOKEN_2)
        self.assertEqual(result.get("token_mode"), TOKEN_MODE_IMAP_COMMON)
        self.assertEqual(mock_post.call_count, 2)
        self.assertIn("/consumers/", mock_post.call_args_list[0].args[0])
        self.assertIn("/common/", mock_post.call_args_list[1].args[0])

    @patch("outlook_web.services.imap.requests.post")
    def test_imap_token_continues_after_network_error(self, mock_post):
        """首个 endpoint 网络异常时，应继续尝试后续 tenant。"""
        import requests

        from outlook_web.services.graph import TOKEN_MODE_IMAP_COMMON
        from outlook_web.services.imap import get_access_token_imap_result

        mock_post.side_effect = [
            requests.ConnectionError("temporary network error"),
            _make_token_response(_ACCESS_TOKEN_2),
        ]

        result = get_access_token_imap_result(_CLIENT_ID_A, _REFRESH_TOKEN_A)

        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("token_mode"), TOKEN_MODE_IMAP_COMMON)
        self.assertEqual(mock_post.call_count, 2)

    # T-08: endpoint 返回失败 → 不写入缓存
    @patch("outlook_web.services.imap.requests.post")
    def test_endpoint_failure_not_cached(self, mock_post):
        from outlook_web.services.imap import get_access_token_imap_result

        mock_post.return_value = _make_error_response(400)

        r1 = get_access_token_imap_result(_CLIENT_ID_A, _REFRESH_TOKEN_A)
        self.assertFalse(r1.get("success"))
        # multi-tenant 兜底：consumers/common/organizations 各试一次
        failed_calls = mock_post.call_count
        self.assertGreaterEqual(failed_calls, 1)

        # 修正后再调用应该重新请求（而不是返回缓存的失败）
        mock_post.return_value = _make_token_response(_ACCESS_TOKEN_1)
        r2 = get_access_token_imap_result(_CLIENT_ID_A, _REFRESH_TOKEN_A)
        self.assertTrue(r2.get("success"))
        self.assertEqual(mock_post.call_count, failed_calls + 1)


if __name__ == "__main__":
    unittest.main()
