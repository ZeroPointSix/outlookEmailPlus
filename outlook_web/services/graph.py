from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from outlook_web.errors import build_error_payload
from outlook_web.services.http import get_response_details

# Token 端点
TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
TOKEN_URL_GRAPH = TOKEN_URL_TEMPLATE.format(tenant="common")
DEFAULT_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
GRAPH_NAMED_MAIL_READ_SCOPE = "User.Read Mail.Read offline_access"
IMAP_ACCESS_SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
GRAPH_MAIL_READ_SCOPES = ("Mail.Read", "Mail.ReadWrite")

# Stable identifiers returned by token APIs. Keep human-facing labels separate so
# diagnostics and callers do not rely on localized presentation text.
TOKEN_MODE_REQUESTED_SCOPE = "requested_scope"
TOKEN_MODE_GRAPH_NAMED_CONSUMERS = "graph_named_consumers"
TOKEN_MODE_GRAPH_DEFAULT_CONSUMERS = "graph_default_consumers"
TOKEN_MODE_IMAP_CONSUMERS = "imap_consumers"
TOKEN_MODE_GRAPH_DEFAULT_COMMON = "graph_default_common"
TOKEN_MODE_GRAPH_NAMED_COMMON = "graph_named_common"
TOKEN_MODE_IMAP_COMMON = "imap_common"
TOKEN_MODE_GRAPH_DEFAULT_ORGANIZATIONS = "graph_default_organizations"
TOKEN_MODE_GRAPH_NAMED_ORGANIZATIONS = "graph_named_organizations"
TOKEN_MODE_IMAP_ORGANIZATIONS = "imap_organizations"

TOKEN_MODE_LABELS: Dict[str, str] = {
    TOKEN_MODE_REQUESTED_SCOPE: "指定 scope",
    TOKEN_MODE_GRAPH_NAMED_CONSUMERS: "新GR",
    TOKEN_MODE_GRAPH_DEFAULT_CONSUMERS: "老GR",
    TOKEN_MODE_IMAP_CONSUMERS: "IMAP",
    TOKEN_MODE_GRAPH_DEFAULT_COMMON: "老GR(common)",
    TOKEN_MODE_GRAPH_NAMED_COMMON: "新GR(common)",
    TOKEN_MODE_IMAP_COMMON: "IMAP(common)",
    TOKEN_MODE_GRAPH_DEFAULT_ORGANIZATIONS: "老GR(organizations)",
    TOKEN_MODE_GRAPH_NAMED_ORGANIZATIONS: "新GR(organizations)",
    TOKEN_MODE_IMAP_ORGANIZATIONS: "IMAP(organizations)",
}

TOKEN_REFRESH_COMPATIBILITY_MODES = (
    # 供应商新口径（个人号常见）
    {"mode": TOKEN_MODE_GRAPH_NAMED_CONSUMERS, "tenant": "consumers", "scope": GRAPH_NAMED_MAIL_READ_SCOPE},
    {"mode": TOKEN_MODE_GRAPH_DEFAULT_CONSUMERS, "tenant": "consumers", "scope": DEFAULT_GRAPH_SCOPE},
    {"mode": TOKEN_MODE_IMAP_CONSUMERS, "tenant": "consumers", "scope": IMAP_ACCESS_SCOPE},
    # 历史/跨 tenant 口径：部分 RT 在 /consumers 会报 AADSTS7000012（grant for different tenant）
    {"mode": TOKEN_MODE_GRAPH_DEFAULT_COMMON, "tenant": "common", "scope": DEFAULT_GRAPH_SCOPE},
    {"mode": TOKEN_MODE_GRAPH_NAMED_COMMON, "tenant": "common", "scope": GRAPH_NAMED_MAIL_READ_SCOPE},
    {"mode": TOKEN_MODE_IMAP_COMMON, "tenant": "common", "scope": IMAP_ACCESS_SCOPE},
    # 工作/学校账号或混合目录
    {
        "mode": TOKEN_MODE_GRAPH_DEFAULT_ORGANIZATIONS,
        "tenant": "organizations",
        "scope": DEFAULT_GRAPH_SCOPE,
    },
    {
        "mode": TOKEN_MODE_GRAPH_NAMED_ORGANIZATIONS,
        "tenant": "organizations",
        "scope": GRAPH_NAMED_MAIL_READ_SCOPE,
    },
    {"mode": TOKEN_MODE_IMAP_ORGANIZATIONS, "tenant": "organizations", "scope": IMAP_ACCESS_SCOPE},
)

GRAPH_ACCESS_TOKEN_COMPATIBILITY_MODES = (
    # 读信/删信先保留旧口径，避免 Mail.ReadWrite 账号被降到只读命名 scope。
    {"mode": TOKEN_MODE_GRAPH_DEFAULT_COMMON, "tenant": "common", "scope": DEFAULT_GRAPH_SCOPE},
    # 保持既有顺序：common 失败后先试 consumers 命名 scope（兼容既有单测与供应商新 GR）
    {"mode": TOKEN_MODE_GRAPH_NAMED_CONSUMERS, "tenant": "consumers", "scope": GRAPH_NAMED_MAIL_READ_SCOPE},
    {"mode": TOKEN_MODE_GRAPH_DEFAULT_CONSUMERS, "tenant": "consumers", "scope": DEFAULT_GRAPH_SCOPE},
    # 补 common 命名 scope：部分 RT 在 .default 报 9002313，命名 scope 可过
    {"mode": TOKEN_MODE_GRAPH_NAMED_COMMON, "tenant": "common", "scope": GRAPH_NAMED_MAIL_READ_SCOPE},
    # AADSTS7000012：grant 属于 organizations / 混合目录
    {
        "mode": TOKEN_MODE_GRAPH_DEFAULT_ORGANIZATIONS,
        "tenant": "organizations",
        "scope": DEFAULT_GRAPH_SCOPE,
    },
    {
        "mode": TOKEN_MODE_GRAPH_NAMED_ORGANIZATIONS,
        "tenant": "organizations",
        "scope": GRAPH_NAMED_MAIL_READ_SCOPE,
    },
)

# IMAP OAuth 取件：旧实现写死 /consumers，遇到非 consumers 签发的 RT 会全军覆没。
IMAP_ACCESS_TOKEN_COMPATIBILITY_MODES = (
    {"mode": TOKEN_MODE_IMAP_CONSUMERS, "tenant": "consumers", "scope": IMAP_ACCESS_SCOPE},
    {"mode": TOKEN_MODE_IMAP_COMMON, "tenant": "common", "scope": IMAP_ACCESS_SCOPE},
    {"mode": TOKEN_MODE_IMAP_ORGANIZATIONS, "tenant": "organizations", "scope": IMAP_ACCESS_SCOPE},
)

# Graph API 返回 401 时表示账号授权失效（与 token endpoint 失败不同）
GRAPH_AUTH_EXPIRED_STATUS = 401


def build_proxies(proxy_url: str) -> Optional[Dict[str, str]]:
    """构建 requests 的 proxies 参数"""
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def build_token_url(tenant: str | None = None) -> str:
    """按 tenant 生成 Microsoft OAuth token endpoint。"""
    normalized_tenant = (tenant or "common").strip() or "common"
    return TOKEN_URL_TEMPLATE.format(tenant=normalized_tenant)


def dedupe_token_modes(modes: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """按 tenant 与 scope 去重，并保留每种模式的稳定标识。"""
    seen = set()
    result: List[Dict[str, str]] = []
    for mode in modes:
        tenant = (mode.get("tenant") or "common").strip() or "common"
        scope = (mode.get("scope") or DEFAULT_GRAPH_SCOPE).strip() or DEFAULT_GRAPH_SCOPE
        key = (tenant, scope)
        if key in seen:
            continue
        seen.add(key)
        result.append({"mode": mode.get("mode") or scope, "tenant": tenant, "scope": scope})
    return result


def get_token_mode_label(mode: Dict[str, str]) -> str:
    """返回稳定 token mode 对应的诊断展示标签。"""
    mode_key = str(mode.get("mode") or "")
    return TOKEN_MODE_LABELS.get(mode_key, mode_key)


def parse_token_response_payload(res: requests.Response) -> Dict[str, Any]:
    """将 token endpoint 响应安全解析为字典。"""
    try:
        payload = res.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _build_refresh_mode_sequence(tenant: str, scope: str) -> List[Dict[str, str]]:
    requested = {
        "mode": TOKEN_MODE_REQUESTED_SCOPE,
        "tenant": (tenant or "common").strip() or "common",
        "scope": (scope or DEFAULT_GRAPH_SCOPE).strip() or DEFAULT_GRAPH_SCOPE,
    }
    modes: List[Dict[str, str]] = []
    # 显式指定非历史默认 scope 时先尊重调用方，其余场景按兼容模式优先。
    if requested["tenant"] != "common" or requested["scope"] != DEFAULT_GRAPH_SCOPE:
        modes.append(requested)
    modes.extend(TOKEN_REFRESH_COMPATIBILITY_MODES)
    if not modes:
        modes.append(requested)
    return dedupe_token_modes(modes)


def _request_token(
    *,
    client_id: str,
    refresh_token: str,
    proxy_url: str = None,
    tenant: str,
    scope: str,
    timeout: int,
) -> requests.Response:
    return requests.post(
        build_token_url(tenant),
        data={
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": scope,
        },
        timeout=timeout,
        proxies=build_proxies(proxy_url),
    )


def _extract_token_error_message(res: requests.Response) -> str:
    try:
        error_data = res.json()
    except Exception:
        error_data = {}
    error_msg = None
    if isinstance(error_data, dict):
        error_msg = error_data.get("error_description") or error_data.get("error")
    if not error_msg:
        details = get_response_details(res)
        error_msg = str(details)[:800] if details is not None else "未知错误"
    return str(error_msg)


def get_access_token_graph_result(client_id: str, refresh_token: str, proxy_url: str = None) -> Dict[str, Any]:
    """获取 Graph API access_token（包含错误详情）"""
    attempts: List[Dict[str, Any]] = []
    last_status = 400
    for mode in dedupe_token_modes(list(GRAPH_ACCESS_TOKEN_COMPATIBILITY_MODES)):
        try:
            res = _request_token(
                client_id=client_id,
                refresh_token=refresh_token,
                proxy_url=proxy_url,
                tenant=mode["tenant"],
                scope=mode["scope"],
                timeout=30,
            )
        except Exception as exc:
            last_status = 503
            attempts.append(
                {
                    "mode": mode["mode"],
                    "mode_label": get_token_mode_label(mode),
                    "tenant": mode["tenant"],
                    "scope": mode["scope"],
                    "status": last_status,
                    "details": {"exception": type(exc).__name__, "message": str(exc)},
                }
            )
            continue

        last_status = res.status_code
        if res.status_code != 200:
            attempts.append(
                {
                    "mode": mode["mode"],
                    "mode_label": get_token_mode_label(mode),
                    "tenant": mode["tenant"],
                    "scope": mode["scope"],
                    "status": res.status_code,
                    "details": get_response_details(res),
                }
            )
            continue

        payload = parse_token_response_payload(res)
        access_token = payload.get("access_token")
        if not access_token:
            attempts.append(
                {
                    "mode": mode["mode"],
                    "mode_label": get_token_mode_label(mode),
                    "tenant": mode["tenant"],
                    "scope": mode["scope"],
                    "status": res.status_code,
                    "details": payload,
                }
            )
            continue

        # refresh token 可能在换取 access token 时轮换，服务端返回新值时要写回。
        new_refresh_token = payload.get("refresh_token")
        return {
            "success": True,
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "new_refresh_token": new_refresh_token,
            "scope": payload.get("scope", ""),
            "token_mode": mode["mode"],
            "token_mode_label": get_token_mode_label(mode),
        }

    return {
        "success": False,
        "error": build_error_payload(
            "GRAPH_TOKEN_FAILED",
            "获取访问令牌失败",
            "GraphAPIError",
            last_status,
            {"attempts": attempts},
        ),
    }


def has_mail_read_permission(scope: Any) -> bool:
    scope_str = str(scope or "")
    return any(mail_scope in scope_str for mail_scope in GRAPH_MAIL_READ_SCOPES)


def get_access_token_graph(client_id: str, refresh_token: str, proxy_url: str = None) -> Optional[str]:
    """获取 Graph API access_token"""
    result = get_access_token_graph_result(client_id, refresh_token, proxy_url)
    if result.get("success"):
        return result.get("access_token")
    return None


def get_emails_graph(
    client_id: str,
    refresh_token: str,
    folder: str = "inbox",
    skip: int = 0,
    top: int = 20,
    proxy_url: str = None,
) -> Dict[str, Any]:
    """使用 Graph API 获取邮件列表（支持分页和文件夹选择）"""
    token_result = get_access_token_graph_result(client_id, refresh_token, proxy_url)
    if not token_result.get("success"):
        return {"success": False, "error": token_result.get("error")}

    access_token = token_result.get("access_token")
    scope = token_result.get("scope", "")
    if not has_mail_read_permission(scope):
        return {
            "success": False,
            "auth_expired": True,
            "no_mail_permission": True,
            "error": build_error_payload(
                "NO_MAIL_PERMISSION",
                "此账号未授予邮件读取权限 (scope 中不含 Mail.Read)",
                "PermissionError",
                403,
                f"scope={scope}",
            ),
        }

    try:
        folder_map = {
            "inbox": "inbox",
            "junkemail": "junkemail",
            "deleteditems": "deleteditems",
            "trash": "deleteditems",
        }
        folder_name = folder_map.get((folder or "").lower(), "inbox")

        url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder_name}/messages"
        params = {
            "$top": top,
            "$skip": skip,
            "$select": "id,subject,from,receivedDateTime,isRead,hasAttachments,bodyPreview",
            "$orderby": "receivedDateTime desc",
        }
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Prefer": "outlook.body-content-type='text'",
        }

        proxies = build_proxies(proxy_url)
        res = requests.get(url, headers=headers, params=params, timeout=30, proxies=proxies)

        if res.status_code != 200:
            details = get_response_details(res)
            return {
                "success": False,
                "auth_expired": res.status_code == GRAPH_AUTH_EXPIRED_STATUS,
                "error": build_error_payload(
                    "EMAIL_FETCH_FAILED",
                    "获取邮件失败，请检查账号配置",
                    "GraphAPIError",
                    res.status_code,
                    details,
                ),
            }

        return {
            "success": True,
            "emails": res.json().get("value", []),
            "new_refresh_token": token_result.get("refresh_token"),
        }
    except Exception as exc:
        return {
            "success": False,
            "error": build_error_payload(
                "EMAIL_FETCH_FAILED",
                "获取邮件失败，请检查账号配置",
                type(exc).__name__,
                500,
                str(exc),
            ),
        }


def get_email_detail_graph(
    client_id: str,
    refresh_token: str,
    message_id: str,
    proxy_url: str = None,
) -> Optional[Dict]:
    """使用 Graph API 获取邮件详情"""
    access_token = get_access_token_graph(client_id, refresh_token, proxy_url)
    if not access_token:
        return None

    try:
        url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}"
        params = {
            "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,isRead,hasAttachments,body,bodyPreview"
        }
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Prefer": "outlook.body-content-type='html'",
        }

        proxies = build_proxies(proxy_url)
        res = requests.get(url, headers=headers, params=params, timeout=30, proxies=proxies)

        if res.status_code != 200:
            return None

        return res.json()
    except Exception:
        return None


def get_email_raw_graph(
    client_id: str,
    refresh_token: str,
    message_id: str,
    proxy_url: str = None,
) -> Optional[str]:
    """使用 Graph API 获取邮件 MIME RAW 内容。"""
    access_token = get_access_token_graph(client_id, refresh_token, proxy_url)
    if not access_token:
        return None

    try:
        url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/$value"
        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        proxies = build_proxies(proxy_url)
        res = requests.get(url, headers=headers, timeout=30, proxies=proxies)

        if res.status_code != 200:
            return None

        res.encoding = res.encoding or "utf-8"
        return res.text
    except Exception:
        return None


def test_refresh_token(client_id: str, refresh_token: str, proxy_url: str = None) -> tuple[bool, str | None]:
    """测试 refresh token 是否有效，返回 (是否成功, 错误信息)"""
    ok, err, _new_refresh_token = test_refresh_token_with_rotation(client_id, refresh_token, proxy_url)
    return ok, err


def test_refresh_token_with_rotation(
    client_id: str,
    refresh_token: str,
    proxy_url: str = None,
    *,
    tenant: str = "common",
    scope: str = DEFAULT_GRAPH_SCOPE,
    max_retries: int = 3,
) -> tuple[bool, str | None, str | None]:
    """测试 refresh token 是否有效；如服务端返回新的 refresh_token，则一并返回（用于滚动更新）。
    支持新 GR / 老 GR / IMAP 三种取件 scope 兜底；遇到 429 时优先读取 Retry-After 头。"""
    import time

    resolved_scope = (scope or DEFAULT_GRAPH_SCOPE).strip() or DEFAULT_GRAPH_SCOPE
    modes = _build_refresh_mode_sequence(tenant, resolved_scope)

    errors: List[str] = []
    for mode in modes:
        last_error_msg = None
        for attempt in range(max_retries + 1):
            try:
                res = _request_token(
                    client_id=client_id,
                    refresh_token=refresh_token,
                    proxy_url=proxy_url,
                    tenant=mode["tenant"],
                    scope=mode["scope"],
                    timeout=15,
                )

                if res.status_code == 200:
                    try:
                        payload = res.json()
                    except Exception:
                        payload = {}
                    new_refresh_token = payload.get("refresh_token")
                    return True, None, new_refresh_token

                # 429 限流：读取 Retry-After 并退避
                if res.status_code == 429:
                    retry_after = None
                    try:
                        retry_after = int(res.headers.get("Retry-After", 0))
                    except Exception:
                        retry_after = None
                    wait = retry_after if retry_after else (2**attempt)
                    last_error_msg = f"{get_token_mode_label(mode)} 请求被限流 (429)，{wait}s 后重试"
                    if attempt < max_retries:
                        time.sleep(wait)
                        continue

                error_msg = _extract_token_error_message(res)
                last_error_msg = f"{get_token_mode_label(mode)}: {error_msg}"
                # 明确的 4xx 不在同一 scope 上重试，改试下一种取件权限。
                break
            except Exception as e:
                last_error_msg = f"{get_token_mode_label(mode)} 请求异常: {str(e)}"
                if attempt < max_retries:
                    time.sleep(2**attempt)
                    continue
                break

        if last_error_msg:
            errors.append(last_error_msg)

    return False, " | ".join(errors) if errors else "请求失败", None


def delete_emails_graph(
    client_id: str,
    refresh_token: str,
    message_ids: List[str],
    proxy_url: str = None,
) -> Dict[str, Any]:
    """通过 Graph API 批量删除邮件（永久删除）"""
    token_result = get_access_token_graph_result(client_id, refresh_token, proxy_url)
    if not token_result.get("success"):
        return {"success": False, "error": token_result.get("error")}

    access_token = token_result.get("access_token")
    if not access_token:
        return {
            "success": False,
            "error": build_error_payload(
                "GRAPH_TOKEN_FAILED",
                "获取访问令牌失败",
                "GraphAPIError",
                500,
                "empty_access_token",
            ),
        }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Graph API batch 请求每次最多 20
    batch_size = 20
    success_count = 0
    failed_count = 0
    errors: List[str] = []

    for i in range(0, len(message_ids), batch_size):
        batch = message_ids[i : i + batch_size]

        batch_requests = []
        for idx, msg_id in enumerate(batch):
            batch_requests.append({"id": str(idx), "method": "DELETE", "url": f"/me/messages/{msg_id}"})

        try:
            proxies = build_proxies(proxy_url)
            response = requests.post(
                "https://graph.microsoft.com/v1.0/$batch",
                headers=headers,
                json={"requests": batch_requests},
                timeout=30,
                proxies=proxies,
            )

            if response.status_code == 200:
                results = response.json().get("responses", [])
                for res in results:
                    if res.get("status") in [200, 204]:
                        success_count += 1
                    else:
                        failed_count += 1
                        try:
                            errors.append(f"Msg ID: {batch[int(res['id'])]}, Status: {res.get('status')}")
                        except Exception:
                            errors.append(f"Status: {res.get('status')}")
            else:
                failed_count += len(batch)
                errors.append(f"Batch request failed: {response.text}")
        except Exception as e:
            failed_count += len(batch)
            errors.append(f"Network error: {str(e)}")

    result: Dict[str, Any] = {
        "success": success_count > 0,
        "partial_success": success_count > 0 and failed_count > 0,
        "success_count": success_count,
        "failed_count": failed_count,
        "errors": errors,
    }

    if not result["success"]:
        result["error"] = build_error_payload(
            "EMAIL_DELETE_FAILED",
            "删除邮件失败",
            "GraphAPIError",
            502,
            {"failed_count": failed_count, "errors": errors[:10]},
        )

    return result
