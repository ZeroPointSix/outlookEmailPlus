from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from outlook_web.errors import build_error_payload
from outlook_web.services.http import get_response_details

# Token 端点
TOKEN_URL_GRAPH = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

# Graph API 返回 401 时的状态码（可能是 token 过期，也可能是权限不足，需进一步解析响应体区分）
GRAPH_AUTH_EXPIRED_STATUS = 401

# 表示 token 真正过期的 Graph API error code；权限不足（如 ErrorAccessDenied）不在此列
_GRAPH_TOKEN_EXPIRED_CODES = {
    "InvalidAuthenticationToken",
    "Authentication.TokenExpired",
    "TokenExpired",
}


def _is_graph_auth_expired(status_code: int, details: Any) -> bool:
    """判断 Graph API 401 是 token 真正过期，而非权限不足。

    - 权限不足（ErrorAccessDenied 等）→ False，IMAP 仍可回退
    - token 真正过期 → True
    - 无法解析响应体 → False（保守策略：不阻断 IMAP 回退）
    """
    if status_code != GRAPH_AUTH_EXPIRED_STATUS:
        return False
    if isinstance(details, dict):
        error_code = details.get("error", {}).get("code", "")
        return error_code in _GRAPH_TOKEN_EXPIRED_CODES
    return False


def build_proxies(proxy_url: str) -> Optional[Dict[str, str]]:
    """构建 requests 的 proxies 参数"""
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


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
                "scope": "https://graph.microsoft.com/.default",
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

        # 根据 Microsoft Learn 文档：refresh token 可能会在每次使用时“自我替换”，应保存新的 refresh_token（如有）。
        new_refresh_token = payload.get("refresh_token")

        # 检查返回的 scope 是否包含 Mail.Read 权限
        scope = payload.get("scope", "")
        has_mail_read = "Mail.Read" in scope or "Mail.ReadWrite" in scope

        return {
            "success": True,
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "scope": scope,
            "has_mail_read": has_mail_read,
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

    # 无 Mail.Read 权限时直接跳过，不浪费一次 Graph API 请求
    if not token_result.get("has_mail_read"):
        return {
            "success": False,
            "no_mail_permission": True,
            "error": build_error_payload(
                "GRAPH_NO_MAIL_PERMISSION",
                "Token 无 Mail.Read 权限，跳过 Graph API",
                "GraphPermissionError",
                403,
                token_result.get("scope", ""),
            ),
        }

    access_token = token_result.get("access_token")

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
                "auth_expired": _is_graph_auth_expired(res.status_code, details),
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
    client_id: str, refresh_token: str, proxy_url: str = None
) -> tuple[bool, str | None, str | None]:
    """测试 refresh token 是否有效；如服务端返回新的 refresh_token，则一并返回（用于滚动更新）。"""
    try:
        proxies = build_proxies(proxy_url)
        res = requests.post(
            TOKEN_URL_GRAPH,
            data={
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=30,
            proxies=proxies,
        )

        if res.status_code == 200:
            try:
                payload = res.json()
            except Exception:
                payload = {}
            new_refresh_token = payload.get("refresh_token")
            return True, None, new_refresh_token

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
        return False, str(error_msg), None
    except Exception as e:
        return False, f"请求异常: {str(e)}", None


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
