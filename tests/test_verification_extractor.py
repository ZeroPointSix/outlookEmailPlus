"""
验证码提取服务单元测试

测试验证码提取算法的正确性，包括：
- 智能识别算法（中英文关键词）
- 保底提取算法（正则匹配 + 过滤）
- 链接提取算法
- 边界情况处理
"""

import unittest
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from outlook_web.services.verification_extractor import (
    smart_extract_verification_code,
    fallback_extract_verification_code,
    extract_links,
    extract_email_text,
    extract_verification_info,
    extract_verification_info_from_text
)


class TestVerificationExtractor(unittest.TestCase):
    """验证码提取服务测试类"""

    # ==================== 智能识别算法测试 ====================

    def test_smart_extract_chinese_keyword_pure_number(self):
        """
        测试用例 UT-001：智能识别 - 中文关键词 + 纯数字验证码

        测试目的：验证智能识别算法能正确识别中文关键词附近的纯数字验证码
        """
        content = "您的验证码是 123456，请在10分钟内完成验证。"
        result = smart_extract_verification_code(content)
        self.assertEqual(result, "123456")

    def test_smart_extract_english_keyword_pure_number(self):
        """
        测试用例 UT-002：智能识别 - 英文关键词 + 纯数字验证码

        测试目的：验证智能识别算法能正确识别英文关键词附近的纯数字验证码
        """
        content = "Your verification code is 654321. Please verify within 10 minutes."
        result = smart_extract_verification_code(content)
        self.assertEqual(result, "654321")

    def test_smart_extract_otp_keyword_alphanumeric(self):
        """
        测试用例 UT-003：智能识别 - OTP 关键词 + 数字字母混合

        测试目的：验证智能识别算法能正确识别 OTP 关键词附近的数字字母混合验证码
        """
        content = "Your OTP is ABC123. This code will expire in 5 minutes."
        result = smart_extract_verification_code(content)
        self.assertEqual(result, "ABC123")

    def test_smart_extract_code_before_keyword(self):
        """
        测试用例 UT-004：智能识别 - 验证码在关键词前面

        测试目的：验证智能识别算法能识别验证码在关键词前面的情况
        """
        content = "888999 is your verification code."
        result = smart_extract_verification_code(content)
        self.assertEqual(result, "888999")

    def test_smart_extract_multiple_keywords(self):
        """
        测试用例：智能识别 - 多种关键词

        测试目的：验证智能识别算法能正确处理多种关键词
        """
        # 测试 "code is"
        content1 = "The code is 111222 for your account."
        result1 = smart_extract_verification_code(content1)
        self.assertEqual(result1, "111222")

        # 测试 "激活码"
        content2 = "您的激活码为 ABC123，请尽快使用。"
        result2 = smart_extract_verification_code(content2)
        self.assertEqual(result2, "ABC123")

    # ==================== 保底提取算法测试 ====================

    def test_fallback_extract_without_keyword(self):
        """
        测试用例 UT-005：保底提取 - 无关键词的验证码

        测试目的：验证保底提取算法能在没有关键词的情况下提取验证码
        """
        content = "Please use code XYZ789 to complete your registration."
        result = fallback_extract_verification_code(content)
        self.assertEqual(result, "XYZ789")

    def test_fallback_extract_filter_date(self):
        """
        测试用例 UT-006：保底提取 - 过滤日期格式

        测试目的：验证保底提取算法能正确过滤日期格式（避免误判）
        """
        content = "Meeting scheduled for 2024-01-15 at 14:30."
        result = fallback_extract_verification_code(content)
        # 2024 应该被过滤掉（年份）
        self.assertNotEqual(result, "2024")

    def test_fallback_extract_filter_time(self):
        """
        测试用例 UT-007：保底提取 - 过滤时间格式

        测试目的：验证保底提取算法能正确过滤时间格式（避免误判）
        """
        content = "Meeting at 1430 hours."
        result = fallback_extract_verification_code(content)
        # 1430 应该被过滤掉（14:30）
        self.assertNotEqual(result, "1430")

    def test_fallback_extract_filter_year_range(self):
        """
        测试用例：保底提取 - 过滤 2020-2030 年份

        测试目的：验证保底提取算法能正确过滤近期年份
        """
        content = "Welcome to 2025! Your code is 888999."
        result = fallback_extract_verification_code(content)
        # 2025 应该被过滤掉，888999 应该被提取
        self.assertEqual(result, "888999")

    def test_fallback_extract_pure_letter_filtered(self):
        """
        测试用例：保底提取 - 过滤纯字母组合

        测试目的：验证保底提取算法能正确过滤纯字母组合
        """
        content = "Your code is ABCD. It contains no numbers."
        result = fallback_extract_verification_code(content)
        # ABCD 是纯字母，应该被过滤
        self.assertIsNone(result)

    # ==================== 链接提取算法测试 ====================

    def test_extract_single_link(self):
        """
        测试用例 UT-008：链接提取 - 单个链接

        测试目的：验证链接提取算法能正确提取单个 HTTP/HTTPS 链接
        """
        content = "Please click: https://example.com/verify?token=abc123def456"
        result = extract_links(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], "https://example.com/verify?token=abc123def456")

    def test_extract_multiple_links(self):
        """
        测试用例 UT-009：链接提取 - 多个链接

        测试目的：验证链接提取算法能正确提取多个链接并去重
        """
        content = """
        Activate: https://example.com/activate
        Visit: https://example.com
        Terms: https://example.com/terms
        """
        result = extract_links(content)
        self.assertEqual(len(result), 3)
        self.assertIn("https://example.com/activate", result)
        self.assertIn("https://example.com", result)
        self.assertIn("https://example.com/terms", result)

    def test_extract_links_deduplication(self):
        """
        测试用例 UT-010：链接提取 - 链接去重

        测试目的：验证链接提取算法能正确去重重复的链接
        """
        content = """
        Link1: https://example.com/verify
        Link2: https://example.com/verify
        Link3: https://example.com/help
        """
        result = extract_links(content)
        self.assertEqual(len(result), 2)  # 去重后只有 2 个

    def test_extract_links_clean_trailing_punctuation(self):
        """
        测试用例：链接提取 - 清理末尾标点

        测试目的：验证链接提取算法能正确清理链接末尾的标点符号
        """
        content = "Click here: https://example.com/verify."
        result = extract_links(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], "https://example.com/verify")

    def test_extract_http_link(self):
        """
        测试用例：链接提取 - HTTP 链接

        测试目的：验证链接提取算法能正确提取 HTTP 链接
        """
        content = "Visit: http://example.com/page"
        result = extract_links(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], "http://example.com/page")

    # ==================== 边界情况测试 ====================

    def test_extract_empty_email(self):
        """
        测试用例 UT-011：空邮件内容

        测试目的：验证算法能正确处理空邮件内容
        """
        email = {"body": "", "body_html": "", "body_preview": ""}
        text = extract_email_text(email)
        self.assertEqual(text, "")

    def test_extract_no_verification_info(self):
        """
        测试用例 UT-012：未找到验证码和链接

        测试目的：验证算法能正确处理不包含验证码和链接的邮件
        """
        content = "Welcome to our newsletter! This is a regular email."

        code = smart_extract_verification_code(content)
        self.assertIsNone(code)

        code = fallback_extract_verification_code(content)
        self.assertIsNone(code)

        links = extract_links(content)
        self.assertEqual(len(links), 0)

    def test_extract_html_email(self):
        """
        测试用例 UT-013：HTML 邮件内容提取

        测试目的：验证 HTML 转纯文本功能正确
        """
        email = {
            "body_html": "<html><body><p>Your code is <strong>777666</strong></p></body></html>"
        }

        text = extract_email_text(email)
        self.assertIn("777666", text)
        self.assertNotIn("<strong>", text)  # HTML 标签应该被移除

    def test_extract_multiple_codes_first(self):
        """
        测试用例 UT-014：多个验证码（取第一个）

        测试目的：验证算法在多个验证码时取第一个
        """
        content = "Your code is 111222. Previous code 333444 has expired."
        result = smart_extract_verification_code(content)
        self.assertEqual(result, "111222")

    def test_extract_code_length_boundary(self):
        """
        测试用例 UT-015：验证码长度边界（4位和8位）

        测试目的：验证算法能正确识别 4-8 位验证码
        """
        # 4 位
        content1 = "Your code is A1B2"
        result1 = fallback_extract_verification_code(content1)
        self.assertEqual(result1, "A1B2")

        # 8 位
        content2 = "Your code is 12345678"
        result2 = fallback_extract_verification_code(content2)
        self.assertEqual(result2, "12345678")

        # 3 位（应该被忽略）
        content3 = "Your code is A1B"
        result3 = fallback_extract_verification_code(content3)
        self.assertIsNone(result3)

        # 9 位（应该被忽略）
        content4 = "Your code is 123456789"
        result4 = fallback_extract_verification_code(content4)
        self.assertIsNone(result4)

    # ==================== 完整流程测试 ====================

    def test_extract_full_process_code_and_link(self):
        """
        测试用例 UT-016：完整提取流程 - 同时包含验证码和链接

        测试目的：验证完整提取流程能正确提取验证码和链接并格式化
        """
        email_body = "Your verification code is 999888. Or click: https://example.com/activate?code=999888"

        code = smart_extract_verification_code(email_body)
        self.assertEqual(code, "999888")

        links = extract_links(email_body)
        self.assertEqual(len(links), 1)
        self.assertIn("https://example.com/activate?code=999888", links)

        formatted = f"{code} {' '.join(links)}"
        self.assertEqual(formatted, "999888 https://example.com/activate?code=999888")

    def test_extract_full_process_code_only(self):
        """
        测试用例 UT-017：完整提取流程 - 只有验证码

        测试目的：验证完整提取流程能正确处理只有验证码的情况
        """
        email_body = "您的验证码是 123456，请在10分钟内完成验证。"

        code = smart_extract_verification_code(email_body)
        self.assertEqual(code, "123456")

        links = extract_links(email_body)
        self.assertEqual(len(links), 0)

        formatted = code
        self.assertEqual(formatted, "123456")

    def test_extract_full_process_link_only(self):
        """
        测试用例 UT-018：完整提取流程 - 只有链接

        测试目的：验证完整提取流程能正确处理只有链接的情况
        """
        email_body = "Please click: https://example.com/verify?token=abc123def456"

        code = smart_extract_verification_code(email_body)
        self.assertIsNone(code)

        links = extract_links(email_body)
        self.assertEqual(len(links), 1)

        formatted = ' '.join(links)
        self.assertEqual(formatted, "https://example.com/verify?token=abc123def456")

    # ==================== extract_verification_info 函数测试 ====================

    def test_extract_verification_info_success(self):
        """
        测试用例：完整提取函数 - 成功提取
        """
        email = {
            "body": "您的验证码是 123456，点击 https://example.com/verify 激活。"
        }

        result = extract_verification_info(email)
        self.assertEqual(result["verification_code"], "123456")
        self.assertEqual(len(result["links"]), 1)
        self.assertEqual(result["formatted"], "123456 https://example.com/verify")

    def test_extract_verification_info_empty_content(self):
        """
        测试用例：完整提取函数 - 空内容
        """
        email = {"body": "", "body_html": "", "body_preview": ""}

        with self.assertRaises(ValueError) as context:
            extract_verification_info(email)
        self.assertIn("邮件内容为空", str(context.exception))

    def test_extract_verification_info_not_found(self):
        """
        测试用例：完整提取函数 - 未找到验证信息
        """
        email = {"body": "This is a regular email without any codes or links."}

        with self.assertRaises(ValueError) as context:
            extract_verification_info(email)
        self.assertIn("未找到验证信息", str(context.exception))

    # ==================== 空内容边界测试 ====================

    def test_smart_extract_empty_content(self):
        """
        测试用例：智能识别 - 空内容
        """
        result = smart_extract_verification_code("")
        self.assertIsNone(result)

        result = smart_extract_verification_code(None)
        self.assertIsNone(result)

    def test_fallback_extract_empty_content(self):
        """
        测试用例：保底提取 - 空内容
        """
        result = fallback_extract_verification_code("")
        self.assertIsNone(result)

        result = fallback_extract_verification_code(None)
        self.assertIsNone(result)

    def test_extract_links_empty_content(self):
        """
        测试用例：链接提取 - 空内容
        """
        result = extract_links("")
        self.assertEqual(result, [])

        result = extract_links(None)
        self.assertEqual(result, [])

    def test_extract_email_text_body_content_type(self):
        """
        测试用例：邮件文本提取 - bodyContent 格式
        """
        email = {
            "bodyContent": "<p>Your code is 555666</p>",
            "bodyContentType": "html"
        }

        text = extract_email_text(email)
        self.assertIn("555666", text)


if __name__ == '__main__':
    unittest.main()
