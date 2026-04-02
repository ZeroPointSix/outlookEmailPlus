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
from typing import Any, Dict, List, Optional

# 验证码关键词列表（支持中英文）
VERIFICATION_KEYWORDS = [
    "验证码",
    "code",
    "验证",
    "verification",
    "OTP",
    "动态码",
    "校验码",
    "verify code",
    "confirmation code",
    "security code",
    "验证码是",
    "your code",
    "code is",
    "激活码",
    "短信验证码",
]

# 验证码模式（4-8位数字或字母，必须包含至少一个数字）
VERIFICATION_PATTERN = r"\b[A-Z0-9]{4,8}\b"

# 链接正则表达式
LINK_PATTERN = r'https?://[^\s<>"{}|\\^`\[\]]+'

# 对外/参数化提取：验证链接优先关键词
DEFAULT_LINK_KEYWORDS = [
    "verify",
    "confirmation",
    "confirm",
    "activate",
    "validation",
]

# 链接语境提权：仅与"验证/激活账户/确认邮箱"强相关的完整短语
# 必须带对象名词（email/account/邮箱/账户），避免 "confirm your order" 等交易邮件误触
LINK_CONTEXT_PHRASES = [
    "verify your email",
    "verify your account",
    "verify your address",
    "confirm your email",
    "confirm your account",
    "confirm your address",
    "activate your email",
    "activate your account",
    "email verification",
    "account verification",
    "验证您的邮箱",
    "验证你的邮箱",
    "验证您的账户",
    "验证你的账户",
    "验证您的账号",
    "验证你的账号",
    "确认您的邮箱",
    "确认你的邮箱",
    "确认您的账户",
    "确认你的账户",
    "激活您的账户",
    "激活你的账户",
    "激活您的邮箱",
    "激活你的邮箱",
    "邮箱验证",
    "账号验证",
    "账户验证",
]


class HTMLTextExtractor(HTMLParser):
    """HTML 转纯文本提取器"""

    def __init__(self):
        super().__init__()
        self.text_parts = []
        self._skip_tags = {"style", "script", "head", "meta", "link"}
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
        cleaned = link.rstrip(".,;:!?)>'\"")
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
        "formatted": formatted,
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


def _extract_content_text_without_subject(email: Dict[str, Any]) -> str:
    """
    仅提取邮件正文/预览（不回退到 subject）。

    注意：extract_email_text() 会在末尾回退 subject；该函数用于 code_source=content 时严格遵循语义。
    """
    # 优先使用纯文本
    if email.get("body") and str(email["body"]).strip():
        return str(email["body"]).strip()

    # 其次使用 HTML 转纯文本
    if email.get("body_html") and str(email["body_html"]).strip():
        parser = HTMLTextExtractor()
        try:
            parser.feed(str(email["body_html"]))
            text = html.unescape(parser.get_text() or "")
            return text.strip()
        except Exception:
            return ""

    # Graph API 格式 bodyContent/bodyContentType
    if email.get("bodyContent") and str(email["bodyContent"]).strip():
        content = str(email["bodyContent"])
        if str(email.get("bodyContentType") or "").lower() == "html":
            parser = HTMLTextExtractor()
            try:
                parser.feed(content)
                text = html.unescape(parser.get_text() or "")
                return text.strip()
            except Exception:
                return ""
        return content.strip()

    if email.get("body_preview") and str(email["body_preview"]).strip():
        return str(email["body_preview"]).strip()

    return ""


def _parse_code_length(code_length: str) -> tuple[int, int]:
    m = re.match(r"^(\d+)-(\d+)$", str(code_length or "").strip())
    if not m:
        raise ValueError("code_length 参数无效")
    min_len = int(m.group(1))
    max_len = int(m.group(2))
    if min_len <= 0 or max_len <= 0 or min_len > max_len:
        raise ValueError("code_length 参数无效")
    return min_len, max_len


def _build_code_regex(*, code_regex: str | None, code_length: str | None) -> re.Pattern:
    if code_regex:
        try:
            return re.compile(code_regex)
        except re.error as exc:
            raise ValueError("code_regex 参数无效") from exc

    if code_length:
        min_len, max_len = _parse_code_length(code_length)
        return re.compile(rf"\b\d{{{min_len},{max_len}}}\b")

    # 默认：4-8 位数字验证码（更贴近“验证码”场景）
    return re.compile(r"\b\d{4,8}\b")


def _smart_extract_code_by_keywords(
    email_content: str, code_re: re.Pattern
) -> Optional[str]:
    if not email_content:
        return None

    content_lower = email_content.lower()

    for keyword in VERIFICATION_KEYWORDS:
        keyword_lower = keyword.lower()
        pos = content_lower.find(keyword_lower)
        if pos == -1:
            continue

        start = max(0, pos - 50)
        end = min(len(email_content), pos + len(keyword) + 50)
        context = email_content[start:end]

        for m in code_re.finditer(context):
            value = m.group(0)
            if value and any(c.isdigit() for c in value):
                return value.upper()

    return None


def _fallback_extract_code(email_content: str, code_re: re.Pattern) -> Optional[str]:
    if not email_content:
        return None

    candidates: List[str] = []
    for m in code_re.finditer(email_content):
        value = m.group(0) or ""
        if not value:
            continue

        # 与现有提取器保持一致：必须包含至少一个数字
        if not any(c.isdigit() for c in value):
            continue

        # 过滤常见误判（仅对纯数字候选生效）
        if value.isdigit() and len(value) == 4:
            year = int(value)
            if 1900 <= year <= 2100:
                continue
            hour = int(value[:2])
            minute = int(value[2:])
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                continue
            num = int(value)
            if 2020 <= num <= 2030:
                continue

        candidates.append(value.upper())

    return candidates[0] if candidates else None


def _pick_preferred_link(
    links: List[str], prefer_link_keywords: List[str]
) -> Optional[str]:
    if not links:
        return None

    keywords = [k.lower() for k in (prefer_link_keywords or []) if k]
    if keywords:
        for keyword in keywords:
            for link in links:
                if keyword in (link or "").lower():
                    return link

    return links[0]


def extract_verification_info_with_options(
    email: Dict[str, Any],
    *,
    code_regex: str | None = None,
    code_length: str | None = None,
    code_source: str = "all",
    prefer_link_keywords: list[str] | None = None,
) -> Dict[str, Any]:
    """
    在现有提取器基础上支持：
    - 自定义验证码正则（code_regex）
    - 自定义验证码长度范围（code_length，如 4-8 / 6-6）
    - 提取来源限定（subject/content/html/all）
    - 验证链接关键词优先级（prefer_link_keywords）

    返回结构为兼容扩展字典：
    - verification_code
    - verification_link
    - links
    - formatted
    - match_source
    - confidence          (向后兼容：code/link 中较高者)
    - code_confidence      (high=关键词命中或调用方指定code_regex命中, low=仅 fallback 或未命中)
    - link_confidence      (high=链接含验证关键词或邮件正文含强验证语境短语, low=任意首链接且无验证语境)

    注意：该函数主要服务外部 API，不主动抛“未找到验证码/链接”的异常，方便上层按需映射错误码。
    """
    subject = str(email.get("subject") or "").strip()
    content = _extract_content_text_without_subject(email)
    html_content = str(
        email.get("body_html") or email.get("html_content") or ""
    ).strip()

    source = str(code_source or "all").strip().lower()
    if source == "subject":
        source_text = subject
        match_source = "subject"
    elif source == "content":
        source_text = content
        match_source = "content"
    elif source == "html":
        source_text = html_content
        match_source = "html"
    else:
        source_text = f"{subject} {content} {html_content}".strip()
        match_source = "all"

    code_re = _build_code_regex(code_regex=code_regex, code_length=code_length)
    # 仅 code_regex 具有判别力，code_length 只是宽度约束，不自动提权
    caller_directed_code = bool(code_regex)

    # ── 验证码提取 & 置信度 ──
    verification_code = _smart_extract_code_by_keywords(source_text, code_re)
    code_confidence: str = "high" if verification_code else "low"
    if not verification_code:
        verification_code = _fallback_extract_code(source_text, code_re)
        # 调用方显式指定了 code_regex（强判别力正则）→ 提取命中即视为可信
        if verification_code and caller_directed_code:
            code_confidence = "high"

    # ── 链接提取 & 置信度 ──
    links = extract_links(f"{subject} {content} {html_content}".strip())
    prefer_keywords = prefer_link_keywords or DEFAULT_LINK_KEYWORDS
    verification_link = _pick_preferred_link(links, prefer_keywords)

    link_confidence: str = "low"
    if verification_link:
        # 优先检查 URL 本身是否含验证关键词
        for kw in prefer_keywords:
            if kw and kw.lower() in verification_link.lower():
                link_confidence = "high"
                break
        # URL 不含关键词时，检查邮件正文/主题是否有强验证语境短语
        if link_confidence != "high":
            full_text_lower = f"{subject} {content}".lower()
            for phrase in LINK_CONTEXT_PHRASES:
                if phrase.lower() in full_text_lower:
                    link_confidence = "high"
                    break

    # 总 confidence 向后兼容：取 code / link 中较高者
    confidence = (
        "high" if code_confidence == "high" or link_confidence == "high" else "low"
    )

    parts: List[str] = []
    if verification_code:
        parts.append(verification_code)
    if verification_link:
        parts.append(verification_link)
    formatted = " ".join(parts) if parts else None

    return {
        "verification_code": verification_code,
        "verification_link": verification_link,
        "links": links,
        "formatted": formatted,
        "match_source": match_source,
        "confidence": confidence,
        "code_confidence": code_confidence,
        "link_confidence": link_confidence,
    }


def apply_confidence_gate(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """
    对 extract_verification_info_with_options() 的返回结果应用置信度门控。

    规则：
    - code_confidence != "high"  → verification_code 置 None
    - link_confidence != "high"  → verification_link 置 None
    - 重算 formatted 与 confidence 以保持一致

    用途：外部 API 和临时邮箱验证码提取均应调用此函数，
    确保两条路径使用完全相同的门控标准，避免逻辑漂移。

    Args:
        extracted: extract_verification_info_with_options() 的返回值（原地修改一份拷贝）

    Returns:
        门控后的字典（不修改原始 extracted，返回新字典）
    """
    result = dict(extracted)

    if result.get("code_confidence") != "high":
        result["verification_code"] = None
    if result.get("link_confidence") != "high":
        result["verification_link"] = None

    parts = [
        v
        for v in (result.get("verification_code"), result.get("verification_link"))
        if v
    ]
    result["formatted"] = " ".join(parts) if parts else None
    result["confidence"] = (
        "high"
        if result.get("code_confidence") == "high"
        or result.get("link_confidence") == "high"
        else "low"
    )
    return result
