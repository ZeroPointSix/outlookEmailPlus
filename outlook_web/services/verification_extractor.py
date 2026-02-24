"""
验证码提取服务模块

提供从邮件内容中提取验证码和链接的功能，包括：
- 智能验证码识别（基于关键词）
- 保底验证码提取（正则匹配 + 过滤）
- 链接提取（HTTP/HTTPS）
- 邮件内容提取（HTML转纯文本）
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import List, Optional, Dict, Any


# 验证码关键词列表（支持中英文）
VERIFICATION_KEYWORDS = [
    "验证码", "code", "验证", "verification",
    "OTP", "动态码", "校验码", "verify code",
    "confirmation code", "security code", "验证码是",
    "your code", "code is", "激活码", "短信验证码"
]

# 验证码模式（4-8位数字或字母，必须包含至少一个数字）
VERIFICATION_PATTERN = r'\b[A-Z0-9]{4,8}\b'

# 链接正则表达式
LINK_PATTERN = r'https?://[^\s<>"{}|\\^`\[\]]+'


class HTMLTextExtractor(HTMLParser):
    """HTML 转纯文本提取器"""

    def __init__(self):
        super().__init__()
        self.text_parts = []
        self._skip_tags = {'style', 'script', 'head', 'meta', 'link'}
        self._current_skip = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._skip_tags:
            self._current_skip = True

    def handle_endtag(self, tag):
        if tag.lower() in self._skip_tags:
            self._current_skip = False

    def handle_data(self, data):
        if not self._current_skip and data.strip():
            self.text_parts.append(data.strip())

    def get_text(self) -> str:
        return " ".join(self.text_parts)


def smart_extract_verification_code(email_content: str) -> Optional[str]:
    """
    智能提取验证码（基于关键词）

    算法：
    1. 遍历关键词列表
    2. 在邮件内容中查找关键词位置
    3. 在关键词前后 50 个字符范围内搜索验证码模式
    4. 返回第一个匹配的验证码（必须包含数字）

    Args:
        email_content: 邮件文本内容

    Returns:
        验证码字符串，未找到返回 None
    """
    if not email_content:
        return None

    content_lower = email_content.lower()

    for keyword in VERIFICATION_KEYWORDS:
        keyword_lower = keyword.lower()
        pos = content_lower.find(keyword_lower)

        if pos != -1:
            # 提取关键词前后 50 个字符的上下文
            start = max(0, pos - 50)
            end = min(len(email_content), pos + len(keyword) + 50)
            context = email_content[start:end]

            # 在上下文中搜索验证码
            matches = re.findall(VERIFICATION_PATTERN, context, re.IGNORECASE)
            if matches:
                # 过滤掉纯字母的匹配（验证码通常包含数字）
                for match in matches:
                    if any(c.isdigit() for c in match):
                        return match.upper()

    return None


def fallback_extract_verification_code(email_content: str) -> Optional[str]:
    """
    保底提取验证码（正则匹配 + 过滤）

    算法：
    1. 提取所有 4-8 位的数字/字母组合
    2. 过滤掉常见的非验证码模式（日期、时间等）
    3. 返回第一个匹配项

    Args:
        email_content: 邮件文本内容

    Returns:
        验证码字符串，未找到返回 None
    """
    if not email_content:
        return None

    # 提取所有可能的验证码
    matches = re.findall(VERIFICATION_PATTERN, email_content, re.IGNORECASE)

    # 过滤规则
    filtered = []
    for match in matches:
        match_upper = match.upper()

        # 必须包含至少一个数字
        if not any(c.isdigit() for c in match):
            continue

        # 排除纯数字且长度为 4 的（可能是年份）
        if match.isdigit() and len(match) == 4:
            year = int(match)
            if 1900 <= year <= 2100:
                continue

        # 排除常见的时间格式（如 1234 可能是 12:34）
        if match.isdigit() and len(match) == 4:
            hour = int(match[:2])
            minute = int(match[2:])
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                continue

        # 排除常见的 4 位数字编号（如 2024、2025 等年份）
        if match.isdigit() and len(match) == 4:
            # 年份范围检查
            num = int(match)
            if 2020 <= num <= 2030:
                continue

        filtered.append(match_upper)

    return filtered[0] if filtered else None


def extract_links(email_content: str) -> List[str]:
    """
    提取所有 HTTP/HTTPS 链接

    算法：
    1. 使用正则表达式提取所有链接
    2. 去重并保持顺序
    3. 清理链接末尾的标点符号

    Args:
        email_content: 邮件文本内容

    Returns:
        去重后的链接列表
    """
    if not email_content:
        return []

    matches = re.findall(LINK_PATTERN, email_content, re.IGNORECASE)

    # 清理链接（移除末尾的标点符号）
    cleaned_links = []
    for link in matches:
        # 移除末尾的标点符号
        cleaned = link.rstrip('.,;:!?)>\'"')
        cleaned_links.append(cleaned)

    # 去重并保持顺序
    seen = set()
    unique_links = []
    for link in cleaned_links:
        if link not in seen:
            seen.add(link)
            unique_links.append(link)

    return unique_links


def extract_email_text(email: Dict[str, Any]) -> str:
    """
    从邮件对象提取纯文本内容

    优先级：
    1. body（纯文本）
    2. body_html（HTML 转纯文本）
    3. body_preview（预览文本）

    Args:
        email: 邮件对象字典

    Returns:
        提取的纯文本内容

    Raises:
        ValueError: 邮件内容为空
    """
    # 优先使用纯文本
    if email.get("body") and email["body"].strip():
        return email["body"].strip()

    # 其次使用 HTML 转纯文本
    if email.get("body_html") and email["body_html"].strip():
        parser = HTMLTextExtractor()
        try:
            parser.feed(email["body_html"])
            text = parser.get_text()
            # 解码 HTML 实体
            text = html.unescape(text)
            if text.strip():
                return text.strip()
        except Exception:
            pass

    # 再次尝试使用 bodyContent（Graph API 格式）
    if email.get("bodyContent") and email["bodyContent"].strip():
        content = email["bodyContent"]
        # 如果是 HTML，需要转换
        if email.get("bodyContentType") == "html":
            parser = HTMLTextExtractor()
            try:
                parser.feed(content)
                text = parser.get_text()
                text = html.unescape(text)
                if text.strip():
                    return text.strip()
            except Exception:
                pass
        else:
            return content.strip()

    # 最后使用预览文本
    if email.get("body_preview") and email["body_preview"].strip():
        return email["body_preview"].strip()

    # 使用 subject 作为补充
    if email.get("subject") and email["subject"].strip():
        return email["subject"].strip()

    return ""


def extract_verification_info_from_text(email_content: str) -> Dict[str, Any]:
    """
    从文本内容提取验证信息

    Args:
        email_content: 邮件文本内容

    Returns:
        包含验证码、链接和格式化输出的字典
    """
    # 提取验证码（智能识别 + 保底）
    verification_code = smart_extract_verification_code(email_content)
    if not verification_code:
        verification_code = fallback_extract_verification_code(email_content)

    # 提取链接
    links = extract_links(email_content)

    # 格式化输出
    parts = []
    if verification_code:
        parts.append(verification_code)
    parts.extend(links)

    formatted = " ".join(parts) if parts else None

    return {
        "verification_code": verification_code,
        "links": links,
        "formatted": formatted
    }


def extract_verification_info(email: Dict[str, Any]) -> Dict[str, Any]:
    """
    从邮件对象提取验证信息的完整流程

    Args:
        email: 邮件对象字典

    Returns:
        包含验证码、链接和格式化输出的字典

    Raises:
        ValueError: 未找到验证信息
    """
    # 提取邮件文本内容
    email_content = extract_email_text(email)

    if not email_content:
        raise ValueError("邮件内容为空")

    # 提取验证信息
    result = extract_verification_info_from_text(email_content)

    if not result["formatted"]:
        raise ValueError("未找到验证信息")

    return result
