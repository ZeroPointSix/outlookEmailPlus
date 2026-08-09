"""
验证码提取服务模块（兼容层）

核心提取逻辑已收敛至 verification_code_extraction；本模块保留：
- 向后兼容的函数签名
- AI 回退与探测能力
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from outlook_web.repositories import settings as settings_repo
from outlook_web.services import verification_code_extraction as vce

# 向后兼容：旧代码从此模块导入常量与工具
VERIFICATION_KEYWORDS = vce.VERIFICATION_KEYWORDS
VERIFICATION_PATTERN = vce.VERIFICATION_PATTERN
HYPHENATED_VERIFICATION_PATTERN = vce.HYPHENATED_VERIFICATION_PATTERN
CODE_CONTEXT_PHRASES = vce.CODE_CONTEXT_PHRASES
LINK_PATTERN = vce.LINK_PATTERN
DEFAULT_LINK_KEYWORDS = vce.DEFAULT_LINK_KEYWORDS
LINK_CONTEXT_PHRASES = vce.LINK_CONTEXT_PHRASES
HTMLTextExtractor = vce.HTMLTextExtractor

VERIFICATION_AI_SCHEMA_VERSION = "verification_ai_v1"
_LOGGER = logging.getLogger("outlook_web.services.verification_extractor")


def _is_valid_hyphenated_code(code: str) -> bool:
    return vce._is_valid_hyphenated_code(code)


def _has_code_context(email_content: str) -> bool:
    return vce._has_code_context(email_content)


def _find_hyphenated_code_in_text(text: str) -> Optional[str]:
    return vce._find_hyphenated_code_in_text(text)


def _smart_extract_hyphenated_verification_code(email_content: str) -> Optional[str]:
    return vce.smart_extract_hyphenated_verification_code(email_content)


def _fallback_extract_hyphenated_verification_code(email_content: str) -> Optional[str]:
    return vce.fallback_extract_hyphenated_verification_code(email_content)


def smart_extract_verification_code(email_content: str) -> Optional[str]:
    return vce.smart_extract_verification_code(email_content)


def fallback_extract_verification_code(email_content: str) -> Optional[str]:
    return vce.fallback_extract_verification_code(email_content)


def extract_links(email_content: str) -> List[str]:
    return vce.extract_links(email_content)


def extract_email_text(email: Dict[str, Any]) -> str:
    return vce.extract_email_text(email)


def extract_verification_info_from_text(email_content: str) -> Dict[str, Any]:
    verification_code = smart_extract_verification_code(email_content)
    if not verification_code:
        verification_code = fallback_extract_verification_code(email_content)

    links = extract_links(email_content)
    parts: List[str] = []
    if verification_code:
        parts.append(verification_code)
    parts.extend(links)

    return {
        "verification_code": verification_code,
        "links": links,
        "formatted": " ".join(parts) if parts else None,
    }


def extract_verification_info(email: Dict[str, Any]) -> Dict[str, Any]:
    email_content = extract_email_text(email)
    if not email_content:
        raise ValueError("邮件内容为空")

    result = extract_verification_info_from_text(email_content)
    if not result["formatted"]:
        raise ValueError("未找到验证信息")
    return result


def _extract_content_text_without_subject(email: Dict[str, Any]) -> str:
    return vce.extract_content_text_without_subject(vce.VerificationInput.from_email_dict(email))


def _parse_code_length(code_length: str) -> tuple[int, int]:
    return vce._parse_code_length(code_length)


def _build_code_regex(*, code_regex: str | None, code_length: str | None) -> re.Pattern[str]:
    return vce.build_code_regex(code_regex=code_regex, code_length=code_length)


def _smart_extract_code_by_keywords(email_content: str, code_re: re.Pattern[str]) -> Optional[str]:
    return vce.smart_extract_code_by_keywords(email_content, code_re)


def _fallback_extract_code(email_content: str, code_re: re.Pattern[str]) -> Optional[str]:
    return vce.fallback_extract_code(email_content, code_re)


def _pick_preferred_link(links: List[str], prefer_link_keywords: List[str]) -> Optional[str]:
    return vce.pick_preferred_link(links, prefer_link_keywords)


def extract_verification_info_with_options(
    email: Dict[str, Any],
    *,
    code_regex: str | None = None,
    code_length: str | None = None,
    code_source: str = "all",
    prefer_link_keywords: list[str] | None = None,
    enforce_mutual_exclusion: bool = True,
) -> Dict[str, Any]:
    return vce.extract_verification_from_email_dict(
        email,
        code_regex=code_regex,
        code_length=code_length,
        code_source=code_source,
        prefer_link_keywords=prefer_link_keywords,
        enforce_mutual_exclusion=enforce_mutual_exclusion,
        apply_confidence_gate_after=False,
    )


def apply_confidence_gate(extracted: Dict[str, Any], *, enforce_mutual_exclusion: bool = True) -> Dict[str, Any]:
    return vce.apply_confidence_gate(extracted, enforce_mutual_exclusion=enforce_mutual_exclusion)


def get_verification_ai_runtime_config() -> Dict[str, Any]:
    return {
        "enabled": settings_repo.get_verification_ai_enabled(),
        "base_url": settings_repo.get_verification_ai_base_url(),
        "api_key": settings_repo.get_verification_ai_api_key(),
        "model": settings_repo.get_verification_ai_model(),
    }


def is_verification_ai_config_complete(config: Dict[str, Any]) -> bool:
    return bool(
        (config or {}).get("enabled")
        and str((config or {}).get("base_url") or "").strip()
        and str((config or {}).get("api_key") or "").strip()
        and str((config or {}).get("model") or "").strip()
    )


def build_verification_ai_input_payload(
    email: Dict[str, Any],
    *,
    code_regex: str | None = None,
    code_length: str | None = None,
    code_source: str = "all",
) -> Dict[str, Any]:
    return {
        "schema_version": VERIFICATION_AI_SCHEMA_VERSION,
        "task": "extract_verification",
        "mail": {
            "subject": str(email.get("subject") or ""),
            "text": extract_email_text(email),
            "html": str(email.get("body_html") or email.get("html_content") or ""),
        },
        "rules": {
            "code_regex": str(code_regex or ""),
            "code_length": str(code_length or ""),
        },
        "hints": {
            "code_source": str(code_source or "all"),
        },
    }


def _normalize_verification_ai_endpoint(base_url: str) -> str:
    value = str(base_url or "").strip()
    if not value:
        return ""
    if value.lower().endswith("/chat/completions"):
        return value
    return value.rstrip("/") + "/chat/completions"


def _is_valid_verification_ai_endpoint(endpoint: str) -> bool:
    parsed = urlparse(str(endpoint or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _diagnose_verification_ai_http_status(status_code: int) -> tuple[str, str]:
    if status_code in {401, 403}:
        return "authentication", "请检查 API Key 是否有效，以及该 Key 是否有权访问所选模型。"
    if status_code == 404:
        return "endpoint", "请检查 Base URL。系统只会在末尾补充 /chat/completions。"
    if status_code in {408, 504}:
        return "network", "上游请求超时，请检查网络、代理或服务可用性。"
    if status_code == 429:
        return "rate_limit", "上游触发限流或额度不足，请稍后重试并检查账户额度。"
    if status_code >= 500:
        return "server", "上游服务返回错误，请稍后重试或查看服务端日志。"
    if status_code in {400, 409, 422}:
        return "configuration", "请求已到达服务，请检查模型 ID 和兼容接口参数。"
    return "server", "上游返回了未预期的 HTTP 状态，请检查服务端日志。"


def _diagnose_verification_ai_exception(exc: Exception) -> tuple[str, str, str]:
    if isinstance(exc, requests.Timeout):
        return "timeout", "network", "请求超时，请检查网络、代理或服务响应时间。"
    if isinstance(exc, (requests.exceptions.InvalidURL, requests.exceptions.MissingSchema)):
        return "invalid_base_url", "configuration", "Base URL 必须是完整的 http:// 或 https:// 地址。"
    if isinstance(exc, requests.ConnectionError):
        return "network_error", "network", "无法连接上游服务，请检查域名解析、网络和代理配置。"
    return "request_failed", "server", "请求未完成，请检查上游服务日志后重试。"


def _parse_verification_ai_content(raw_content: str) -> Optional[Dict[str, Any]]:
    text = str(raw_content or "").strip()
    if not text:
        return None

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()

    try:
        payload = json.loads(text)
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    def _coerce_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float, bool)):
            return str(value).strip()
        return ""

    def _normalize_confidence(value: Any) -> str:
        if isinstance(value, (int, float)):
            try:
                return "high" if float(value) >= 0.5 else "low"
            except Exception:
                return "low"
        if isinstance(value, bool):
            return "high" if value else "low"
        text_value = str(value or "").strip().lower()
        if text_value in {"high", "medium", "1", "true", "yes"}:
            return "high"
        return "low"

    verification_code = _coerce_text(payload.get("verification_code"))
    verification_link = _coerce_text(payload.get("verification_link"))
    if not verification_code and not verification_link:
        return None

    confidence = _normalize_confidence(payload.get("confidence"))
    reason_raw = payload.get("reason")
    reason = _coerce_text(reason_raw)
    if not reason and reason_raw not in (None, ""):
        try:
            reason = json.dumps(reason_raw, ensure_ascii=False)
        except Exception:
            reason = ""

    return {
        "schema_version": VERIFICATION_AI_SCHEMA_VERSION,
        "verification_code": verification_code,
        "verification_link": verification_link,
        "confidence": confidence,
        "reason": reason,
    }


def _call_verification_ai(ai_config: Dict[str, Any], ai_input: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    endpoint = _normalize_verification_ai_endpoint(str((ai_config or {}).get("base_url") or ""))
    api_key = str((ai_config or {}).get("api_key") or "").strip()
    model = str((ai_config or {}).get("model") or "").strip()
    if not endpoint or not api_key or not model:
        return None

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是验证码提取器。必须严格返回 JSON，且字段必须为："
                    "schema_version, verification_code, verification_link, confidence, reason。"
                    f"schema_version 固定为 {VERIFICATION_AI_SCHEMA_VERSION}。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(ai_input, ensure_ascii=False),
            },
        ],
    }

    try:
        response = requests.post(endpoint, headers=headers, json=body, timeout=6)
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices:
            return None
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            return None
        return _parse_verification_ai_content(content)
    except Exception as exc:
        _LOGGER.warning("verification_ai_call_failed: %s", exc)
        return None


def probe_verification_ai_runtime(
    *,
    ai_config: Dict[str, Any],
    sample_email: Optional[Dict[str, Any]] = None,
    code_regex: str | None = None,
    code_length: str | None = "6-6",
    code_source: str = "all",
    timeout_seconds: int = 8,
) -> Dict[str, Any]:
    endpoint = _normalize_verification_ai_endpoint(str((ai_config or {}).get("base_url") or ""))
    model = str((ai_config or {}).get("model") or "").strip()
    api_key = str((ai_config or {}).get("api_key") or "").strip()

    missing_fields: list[str] = []
    if not endpoint:
        missing_fields.append("verification_ai_base_url")
    if not api_key:
        missing_fields.append("verification_ai_api_key")
    if not model:
        missing_fields.append("verification_ai_model")
    if missing_fields:
        return {
            "ok": False,
            "error": "config_incomplete",
            "error_category": "configuration",
            "message": "验证码 AI 配置不完整",
            "hint": "请完整填写 Base URL、API Key 和模型 ID。",
            "missing_fields": missing_fields,
            "endpoint": endpoint,
            "model": model,
        }
    if not _is_valid_verification_ai_endpoint(endpoint):
        return {
            "ok": False,
            "error": "invalid_base_url",
            "error_category": "configuration",
            "message": "Base URL 格式无效",
            "hint": "请输入完整的 http:// 或 https:// 地址。",
            "endpoint": endpoint,
            "model": model,
        }

    email_obj = sample_email or {
        "subject": "Verification test",
        "body": "Your verification code is 123456",
        "body_html": "<p>Your verification code is <b>123456</b></p>",
    }
    ai_input = build_verification_ai_input_payload(
        email_obj,
        code_regex=code_regex,
        code_length=code_length,
        code_source=code_source,
    )

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是验证码提取器。必须严格返回 JSON，且字段必须为："
                    "schema_version, verification_code, verification_link, confidence, reason。"
                    f"schema_version 固定为 {VERIFICATION_AI_SCHEMA_VERSION}。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(ai_input, ensure_ascii=False),
            },
        ],
    }

    started = time.monotonic()
    try:
        response = requests.post(
            endpoint,
            headers=headers,
            json=body,
            timeout=max(1, int(timeout_seconds)),
        )
        latency_ms = int((time.monotonic() - started) * 1000)

        if response.status_code >= 400:
            response_preview = (response.text or "").strip()[:500]
            error_category, hint = _diagnose_verification_ai_http_status(response.status_code)
            return {
                "ok": False,
                "error": "http_error",
                "error_category": error_category,
                "message": f"AI 接口返回 HTTP {response.status_code}",
                "hint": hint,
                "endpoint": endpoint,
                "model": model,
                "http_status": response.status_code,
                "latency_ms": latency_ms,
                "response_preview": response_preview,
            }

        try:
            payload = response.json()
        except Exception:
            response_preview = (response.text or "").strip()[:500]
            return {
                "ok": False,
                "error": "invalid_response_format",
                "error_category": "protocol",
                "message": "AI 接口返回非 JSON 响应",
                "hint": "服务已连接，但响应不是 OpenAI Compatible JSON。请检查 API 类型或代理配置。",
                "endpoint": endpoint,
                "model": model,
                "http_status": response.status_code,
                "latency_ms": latency_ms,
                "response_preview": response_preview,
            }

        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices:
            return {
                "ok": False,
                "error": "invalid_response_format",
                "error_category": "protocol",
                "message": "AI 响应缺少 choices 字段",
                "hint": "服务已连接，但响应不符合 OpenAI chat/completions 契约。",
                "endpoint": endpoint,
                "model": model,
                "http_status": response.status_code,
                "latency_ms": latency_ms,
            }

        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            return {
                "ok": False,
                "error": "invalid_response_format",
                "error_category": "protocol",
                "message": "AI 响应缺少 message.content",
                "hint": "服务已连接，但响应不符合 OpenAI chat/completions 契约。",
                "endpoint": endpoint,
                "model": model,
                "http_status": response.status_code,
                "latency_ms": latency_ms,
            }

        parsed = _parse_verification_ai_content(content)
        if not parsed:
            return {
                "ok": False,
                "error": "invalid_ai_output",
                "error_category": "contract",
                "message": "AI 输出不符合固定 JSON 契约",
                "hint": "连通性正常，但模型未按验证码提取 JSON 契约返回。请更换模型或兼容服务。",
                "endpoint": endpoint,
                "model": model,
                "http_status": response.status_code,
                "latency_ms": latency_ms,
                "response_preview": content.strip()[:500],
            }

        actual_model = str(payload.get("model") or model).strip() if isinstance(payload, dict) else model
        return {
            "ok": True,
            "message": "AI 配置测试成功",
            "endpoint": endpoint,
            "model": actual_model,
            "requested_model": model,
            "http_status": response.status_code,
            "latency_ms": latency_ms,
            "parsed_output": parsed,
        }
    except Exception as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        error, error_category, hint = _diagnose_verification_ai_exception(exc)
        return {
            "ok": False,
            "error": error,
            "error_category": error_category,
            "message": f"AI 请求失败：{exc}",
            "hint": hint,
            "endpoint": endpoint,
            "model": model,
            "latency_ms": latency_ms,
        }


def enhance_verification_with_ai_fallback(
    *,
    email: Dict[str, Any],
    extracted: Dict[str, Any],
    code_regex: str | None = None,
    code_length: str | None = None,
    code_source: str = "all",
    enforce_mutual_exclusion: bool = True,
) -> Dict[str, Any]:
    def _apply_output_policy(payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(payload or {})

        if enforce_mutual_exclusion and normalized.get("verification_code"):
            normalized["verification_link"] = None
            normalized["link_confidence"] = "low"

        parts = []
        if normalized.get("verification_code"):
            parts.append(str(normalized.get("verification_code")))
        if normalized.get("verification_link"):
            parts.append(str(normalized.get("verification_link")))
        normalized["formatted"] = " ".join(parts) if parts else None
        normalized["confidence"] = (
            "high" if normalized.get("code_confidence") == "high" or normalized.get("link_confidence") == "high" else "low"
        )
        return normalized

    result = dict(extracted or {})

    code_confidence = str(result.get("code_confidence") or "low").lower()
    link_confidence = str(result.get("link_confidence") or "low").lower()
    if code_confidence == "high" or link_confidence == "high":
        return _apply_output_policy(result)

    ai_config = get_verification_ai_runtime_config()
    if not is_verification_ai_config_complete(ai_config):
        return _apply_output_policy(result)

    ai_input = build_verification_ai_input_payload(
        email,
        code_regex=code_regex,
        code_length=code_length,
        code_source=code_source,
    )
    ai_output = _call_verification_ai(ai_config, ai_input)
    if not ai_output:
        return _apply_output_policy(result)

    ai_code = str(ai_output.get("verification_code") or "").strip()
    ai_link = str(ai_output.get("verification_link") or "").strip()
    ai_confidence = str(ai_output.get("confidence") or "low").strip().lower()
    ai_reason = str(ai_output.get("reason") or "").strip()

    updated = False
    if ai_code:
        result["verification_code"] = ai_code
        result["code_confidence"] = "high" if ai_confidence == "high" else "low"
        updated = True
    if ai_link:
        result["verification_link"] = ai_link
        result["link_confidence"] = "high" if ai_confidence == "high" else "low"
        links = result.get("links")
        links_list = links if isinstance(links, list) else []
        if ai_link not in links_list:
            links_list = list(links_list)
            links_list.append(ai_link)
        result["links"] = links_list
        updated = True

    if not updated:
        return _apply_output_policy(result)

    result["ai_schema_version"] = VERIFICATION_AI_SCHEMA_VERSION
    result["ai_reason"] = ai_reason
    result["ai_used"] = True

    return _apply_output_policy(result)
