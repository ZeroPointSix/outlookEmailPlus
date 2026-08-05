from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from outlook_web.errors import build_error_payload
from outlook_web.services.http import get_response_details

# Token 端点
TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
TOKEN_URL_GRAPH = TOKEN_URL_TEMPLATE.format(tenant="common")
DEFAULT_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
DEFAULT_REFRESH_SCOPE = f"{DEFAULT_GRAPH_SCOPE} offline_access"
GRAPH_MAIL_READ_SCOPES = ("Mail.Read", "Mail.ReadWrite")

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


def get_access_token_graph_result(client_id: str, refresh_token: str, proxy_url: str = None) -> Dict[str, Any]:
    """获取 Graph API access_token（包含错误详情）"""
    try:
        proxies = build_proxies(proxy_url)
        res = requests.post(
            TOKEN_URL_GRAPH,
            data={
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": DEFAULT_GRAPH_SCOPE,
            },
            timeout=30,
            proxies=proxies,
        )

        if res.status_code != 200:
            details = get_response_details(res)
            return {
                "success": False,
                "error": build_error_payload(
                    "GRAPH_TOKEN_FAILED",
                    "获取访问令牌失败",
                    "GraphAPIError",
                    res.status_code,
                    details,
                ),
            }

        payload = res.json()
        access_token = payload.get("access_token")
        if not access_token:
            return {
                "success": False,
                "error": build_error_payload(
                    "GRAPH_TOKEN_MISSING",
                    "获取访问令牌失败",
                    "GraphAPIError",
                    res.status_code,
                    payload,
                ),
            }

        # 根据 Microsoft Learn 文档：refresh token 可能会在每次使用时"自我替换"，应保存新的 refresh_token（如有）。
        new_refresh_token = payload.get("refresh_token")
        return {
            "success": True,
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "new_refresh_token": new_refresh_token,
            "scope": payload.get("scope", ""),
        }
    except Exception as exc:
        return {
            "success": False,
            "error": build_error_payload(
                "GRAPH_TOKEN_EXCEPTION",
                "获取访问令牌失败",
                type(exc).__name__,
                500,
                str(exc),
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
    scope: str = DEFAULT_REFRESH_SCOPE,
    max_retries: int = 3,
) -> tuple[bool, str | None, str | None]:
    """测试 refresh token 是否有效；如服务端返回新的 refresh_token，则一并返回（用于滚动更新）。
    支持指数退避重试，遇到 429 时优先读取 Retry-After 头。"""
    import time

    proxies = build_proxies(proxy_url)
    resolved_scope = (scope or DEFAULT_REFRESH_SCOPE).strip() or DEFAULT_REFRESH_SCOPE
    url = build_token_url(tenant)
    data = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": resolved_scope,
    }

    last_error_msg = None
    for attempt in range(max_retries + 1):
        try:
            res = requests.post(url, data=data, timeout=15, proxies=proxies)

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
                last_error_msg = f"请求被限流 (429)，{wait}s 后重试"
                if attempt < max_retries:
                    time.sleep(wait)
                    continue

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
            last_error_msg = str(error_msg)
            # 非 429 的明确错误响应（如 400/401/403）不需要重试，直接返回
            return False, last_error_msg, None
        except Exception as e:
            last_error_msg = f"请求异常: {str(e)}"
            if attempt < max_retries:
                time.sleep(2**attempt)
                continue
            return False, last_error_msg, None

    return False, last_error_msg or "请求失败", None


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
