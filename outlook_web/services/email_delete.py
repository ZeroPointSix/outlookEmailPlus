from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from outlook_web.errors import build_error_payload


def summarize_fallback_failures(method_errors: Dict[str, Any], labels: Dict[str, str]) -> str:
    """将多方式回退的失败原因聚合成“中文可理解”的摘要文本（用于 error.details 展示）。"""
    lines: List[str] = []

    for key, label in labels.items():
        if key not in method_errors:
            continue
        err = method_errors.get(key)
        if err is None:
            text = "未知错误"
        elif isinstance(err, dict):
            msg = (err.get("message") or err.get("error") or "").strip()
            code = (err.get("code") or "").strip()
            status = err.get("status")
            meta_parts: List[str] = []
            if code:
                meta_parts.append(f"code={code}")
            if status:
                meta_parts.append(f"status={status}")
            meta = f" ({', '.join(meta_parts)})" if meta_parts else ""
            if msg:
                text = f"{msg}{meta}"
            else:
                raw = json.dumps(err, ensure_ascii=False)
                text = raw[:400] + ("..." if len(raw) > 400 else "")
        elif isinstance(err, list):
            preview_items = [str(x) for x in err[:3]]
            preview = "; ".join(preview_items)
            if len(err) > 3:
                preview += f" ...(共 {len(err)} 条)"
            text = preview
        else:
            text = str(err)

        lines.append(f"{label}：{text}")

    return "\n".join(lines).strip()


def delete_emails_with_fallback(
    *,
    email_addr: str,
    client_id: str,
    refresh_token: str,
    message_ids: List[str],
    proxy_url: str,
    delete_emails_graph: Callable[[str, str, List[str], Optional[str]], Dict[str, Any]],
    delete_emails_imap: Callable[[str, str, str, List[str], str], Dict[str, Any]],
    imap_server_new: str,
    imap_server_old: str,
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    删除邮件（Graph 优先，IMAP 回退）并保持对外错误聚合结构一致。

    返回: (response_data, method)；method 为 'graph'/'imap_new'/'imap_old' 或 None。
    """
    graph_res = delete_emails_graph(client_id, refresh_token, message_ids, proxy_url)
    if graph_res.get("success"):
        return graph_res, "graph"

    graph_error = graph_res.get("error")
    graph_errors_list = graph_res.get("errors") or []
    # 无代理配置时，ConnectionError/ProxyError 不应阻断 IMAP 回退。
    is_proxy_error = bool(proxy_url) and (
        (isinstance(graph_error, dict) and graph_error.get("type") in ("ProxyError", "ConnectionError"))
        or (isinstance(graph_error, str) and "ProxyError" in graph_error)
        or any("ProxyError" in str(x) for x in graph_errors_list[:5])
    )
    if is_proxy_error:
        return graph_res, None

    method_errors: Dict[str, Any] = {
        "graph": graph_error or graph_errors_list or "Graph API 删除失败",
    }

    imap_res = delete_emails_imap(email_addr, client_id, refresh_token, message_ids, imap_server_new)
    if imap_res.get("success"):
        return imap_res, "imap_new"
    method_errors["imap_new"] = imap_res.get("error") or imap_res

    imap_old_res = delete_emails_imap(email_addr, client_id, refresh_token, message_ids, imap_server_old)
    if imap_old_res.get("success"):
        return imap_old_res, "imap_old"
    method_errors["imap_old"] = imap_old_res.get("error") or imap_old_res

    summary = summarize_fallback_failures(
        method_errors,
        {
            "graph": "Graph API",
            "imap_new": "IMAP（新服务器）",
            "imap_old": "IMAP（旧服务器）",
        },
    )
    error_payload = build_error_payload(
        "EMAIL_DELETE_ALL_METHODS_FAILED",
        "删除邮件失败，所有方式均失败",
        "FallbackError",
        502,
        summary,
    )

    response_data = dict(graph_res)
    response_data.setdefault("success_count", 0)
    response_data.setdefault("failed_count", len(message_ids))
    response_data.setdefault("errors", [])
    response_data.update(
        {
            "success": False,
            "error": error_payload,
            "details": method_errors,
        }
    )
    return response_data, None
