from __future__ import annotations

import email
import hashlib
import imaplib
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.header import decode_header
from typing import Any, Dict, List, Optional

import requests

from outlook_web.errors import build_error_payload
from outlook_web.services.graph import get_access_token_graph
from outlook_web.services.http import get_response_details

_LOGGER = logging.getLogger(__name__)

# Token 端点
TOKEN_URL_IMAP = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"

# IMAP 服务器配置
IMAP_SERVER_NEW = "outlook.live.com"
IMAP_PORT = 993

_token_cache: Dict[str, tuple] = {}
_token_cache_lock = threading.Lock()


def decode_header_value(header_value: str) -> str:
    """解码邮件头字段"""
    if not header_value:
        return ""
    try:
        decoded_parts = decode_header(str(header_value))
        decoded_string = ""
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                try:
                    decoded_string += part.decode(
                        charset if charset else "utf-8", "replace"
                    )
                except (LookupError, UnicodeDecodeError):
                    decoded_string += part.decode("utf-8", "replace")
            else:
                decoded_string += str(part)
        return decoded_string
    except Exception:
        return str(header_value) if header_value else ""


def get_email_body(msg) -> str:
    """提取邮件正文"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                    break
                except Exception:
                    continue
            elif (
                content_type == "text/html"
                and "attachment" not in content_disposition
                and not body
            ):
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                except Exception:
                    continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")
        except Exception:
            body = str(msg.get_payload())

    return body


def _select_folder(connection, folder: str) -> Optional[str]:
    folder_map = {
        "inbox": ["INBOX"],
        "junk": ["Junk", "Junk Email", "Spam", "垃圾邮件"],
        "junkemail": ["Junk", "Junk Email", "Spam", "垃圾邮件"],
        "deleteditems": ["Deleted", "Deleted Items", "Trash", "已删除邮件"],
        "trash": ["Deleted", "Deleted Items", "Trash", "已删除邮件"],
    }
    candidates = folder_map.get((folder or "").lower(), [folder or "INBOX"])
    for candidate in candidates:
        for select_target in (f'"{candidate}"', candidate):
            try:
                status, _ = connection.select(select_target, readonly=True)
                if status == "OK":
                    return candidate
            except Exception:
                continue
    return None


def _get_html_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
    else:
        if msg.get_content_type() == "text/html":
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode(
                    msg.get_content_charset() or "utf-8", errors="replace"
                )
    return ""


def _parse_batch_fetch_response(all_data: list) -> List[tuple]:
    results = []
    for item in all_data:
        header = None
        raw_email = None

        if isinstance(item, tuple) and len(item) == 2:
            first, second = item
            if isinstance(first, (bytes, bytearray)) and isinstance(
                second, (bytes, bytearray)
            ):
                header = bytes(first)
                raw_email = bytes(second)
            elif isinstance(first, tuple) and len(first) == 2:
                nested_header, nested_raw = first
                if isinstance(nested_header, (bytes, bytearray)) and isinstance(
                    nested_raw, (bytes, bytearray)
                ):
                    header = bytes(nested_header)
                    raw_email = bytes(nested_raw)

        if not isinstance(header, (bytes, bytearray)) or not isinstance(
            raw_email, (bytes, bytearray)
        ):
            continue

        msg_id_str = header.split(b" ", 1)[0].decode("ascii", errors="ignore").strip()
        if not msg_id_str:
            continue
        results.append((msg_id_str, raw_email))
    return results


def _make_cache_key(client_id: str, refresh_token: str) -> str:
    rt_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()[:16]
    return f"{client_id}:{rt_hash}"


def clear_imap_token_cache(client_id: str = None) -> None:
    with _token_cache_lock:
        if client_id is None:
            _token_cache.clear()
        else:
            keys_to_remove = [k for k in _token_cache if k.startswith(f"{client_id}:")]
            for key in keys_to_remove:
                del _token_cache[key]


def get_access_token_imap_result(client_id: str, refresh_token: str) -> Dict[str, Any]:
    """获取 IMAP access_token（包含错误详情）"""
    cache_key = _make_cache_key(client_id, refresh_token)
    with _token_cache_lock:
        cached = _token_cache.get(cache_key)
        if cached:
            access_token, expires_at = cached
            if time.monotonic() < expires_at:
                return {"success": True, "access_token": access_token}

    try:
        res = requests.post(
            TOKEN_URL_IMAP,
            data={
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": "https://outlook.office.com/IMAP.AccessAsUser.All offline_access",
            },
            timeout=30,
        )

        if res.status_code != 200:
            details = get_response_details(res)
            return {
                "success": False,
                "error": build_error_payload(
                    "IMAP_TOKEN_FAILED",
                    "获取访问令牌失败",
                    "IMAPError",
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
                    "IMAP_TOKEN_MISSING",
                    "获取访问令牌失败",
                    "IMAPError",
                    res.status_code,
                    payload,
                ),
            }

        expires_in = int(payload.get("expires_in", 3599))
        ttl = max(0, expires_in - 60)
        with _token_cache_lock:
            _token_cache[cache_key] = (access_token, time.monotonic() + ttl)

        return {"success": True, "access_token": access_token}
    except Exception as exc:
        return {
            "success": False,
            "error": build_error_payload(
                "IMAP_TOKEN_EXCEPTION",
                "获取访问令牌失败",
                type(exc).__name__,
                500,
                str(exc),
            ),
        }


def get_access_token_imap(client_id: str, refresh_token: str) -> Optional[str]:
    """获取 IMAP access_token"""
    result = get_access_token_imap_result(client_id, refresh_token)
    if result.get("success"):
        return result.get("access_token")
    return None


def get_emails_imap(
    account: str,
    client_id: str,
    refresh_token: str,
    folder: str = "inbox",
    skip: int = 0,
    top: int = 20,
) -> Dict[str, Any]:
    """使用 IMAP 获取邮件列表（支持分页和文件夹选择）- 默认使用新版服务器"""
    return get_emails_imap_with_server(
        account, client_id, refresh_token, folder, skip, top, IMAP_SERVER_NEW
    )


def get_emails_imap_with_server(
    account: str,
    client_id: str,
    refresh_token: str,
    folder: str = "inbox",
    skip: int = 0,
    top: int = 20,
    server: str = IMAP_SERVER_NEW,
) -> Dict[str, Any]:
    """使用 IMAP 获取邮件列表（支持分页、文件夹选择和服务器选择）"""
    token_result = get_access_token_imap_result(client_id, refresh_token)
    if not token_result.get("success"):
        return {"success": False, "error": token_result.get("error")}

    access_token = token_result.get("access_token")

    connection = None
    try:
        connection = imaplib.IMAP4_SSL(server, IMAP_PORT)
        auth_string = f"user={account}\1auth=Bearer {access_token}\1\1".encode("utf-8")
        connection.authenticate("XOAUTH2", lambda x: auth_string)

        selected_folder = _select_folder(connection, folder)

        if not selected_folder:
            try:
                status, folder_list = connection.list()
                available_folders = []
                if status == "OK" and folder_list:
                    for folder_item in folder_list:
                        if isinstance(folder_item, bytes):
                            available_folders.append(
                                folder_item.decode("utf-8", errors="ignore")
                            )
                        else:
                            available_folders.append(str(folder_item))

                error_details = {
                    "last_error": "select folder failed",
                    "tried_folder": folder,
                    "available_folders": available_folders[:10],
                }
            except Exception:
                error_details = {
                    "last_error": "select folder failed",
                    "tried_folder": folder,
                }

            return {
                "success": False,
                "error": build_error_payload(
                    "EMAIL_FETCH_FAILED",
                    "无法访问文件夹，请检查账号配置",
                    "IMAPSelectError",
                    500,
                    error_details,
                ),
            }

        status, messages = connection.search(None, "ALL")
        if status != "OK":
            _LOGGER.debug(
                "[PERF] imap_search | account=%s | server=%s | folder=%s | status=%s (非OK)",
                account,
                server,
                selected_folder,
                status,
            )
            return {
                "success": False,
                "error": build_error_payload(
                    "EMAIL_FETCH_FAILED",
                    "获取邮件失败，请检查账号配置",
                    "IMAPSearchError",
                    500,
                    f"search status={status}",
                ),
            }
        if not messages or not messages[0]:
            _LOGGER.debug(
                "[PERF] imap_search | account=%s | server=%s | folder=%s | total=0 (空信箱)",
                account,
                server,
                selected_folder,
            )
            return {"success": True, "emails": []}

        message_ids = messages[0].split()
        total = len(message_ids)
        start_idx = max(0, total - skip - top)
        end_idx = total - skip

        _LOGGER.debug(
            "[PERF] imap_search | account=%s | server=%s | folder=%s | total=%d | skip=%d | top=%d | slice=[%d:%d]",
            account,
            server,
            selected_folder,
            total,
            skip,
            top,
            start_idx,
            end_idx,
        )

        if start_idx >= end_idx:
            return {"success": True, "emails": []}

        paged_ids = message_ids[start_idx:end_idx][::-1]
        emails_data = []

        ids_str = b",".join(paged_ids)
        status, all_data = connection.fetch(ids_str, "(RFC822)")
        if status != "OK":
            _LOGGER.debug(
                "[PERF] imap_fetch | account=%s | batch fetch失败 status=%s",
                account,
                status,
            )
            return {"success": True, "emails": emails_data}

        for msg_id_str, raw_email in _parse_batch_fetch_response(all_data or []):
            try:
                msg = email.message_from_bytes(raw_email)
                body_preview = get_email_body(msg)
                emails_data.append(
                    {
                        "id": msg_id_str,
                        "subject": decode_header_value(msg.get("Subject", "无主题")),
                        "from": decode_header_value(msg.get("From", "未知发件人")),
                        "date": msg.get("Date", "未知时间"),
                        "body_preview": (
                            body_preview[:200] + "..."
                            if len(body_preview) > 200
                            else body_preview
                        ),
                    }
                )
            except Exception as fetch_err:
                _LOGGER.debug(
                    "[PERF] imap_fetch | account=%s | msg_id=%s | 解析失败: %s",
                    account,
                    msg_id_str,
                    fetch_err,
                )
                continue

        _LOGGER.debug(
            "[PERF] imap_result | account=%s | server=%s | fetched=%d / requested=%d",
            account,
            server,
            len(emails_data),
            len(paged_ids),
        )
        return {"success": True, "emails": emails_data}
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
    finally:
        if connection:
            try:
                connection.logout()
            except Exception:
                pass


def fetch_and_detail_imap_with_server(
    account: str,
    client_id: str,
    refresh_token: str,
    folder: str = "inbox",
    skip: int = 0,
    top: int = 1,
    server: str = IMAP_SERVER_NEW,
) -> Dict[str, Any]:
    """一次 IMAP 连接完成邮件列表 + 最新一封详情。"""
    token_result = get_access_token_imap_result(client_id, refresh_token)
    if not token_result.get("success"):
        return {
            "success": False,
            "error": token_result.get("error"),
            "emails": [],
            "detail": None,
        }

    access_token = token_result["access_token"]
    connection = None

    try:
        connection = imaplib.IMAP4_SSL(server, IMAP_PORT)
        auth_string = f"user={account}\x01auth=Bearer {access_token}\x01\x01".encode(
            "utf-8"
        )
        connection.authenticate("XOAUTH2", lambda x: auth_string)

        selected = _select_folder(connection, folder)
        if not selected:
            return {
                "success": False,
                "error": build_error_payload(
                    "FOLDER_NOT_FOUND", "文件夹选择失败", "IMAPError", 500, ""
                ),
                "emails": [],
                "detail": None,
            }

        status, messages = connection.search(None, "ALL")
        if status != "OK" or not messages or not messages[0]:
            return {"success": True, "emails": [], "detail": None}

        message_ids = messages[0].split()
        total = len(message_ids)
        start_idx = max(0, total - skip - top)
        end_idx = total - skip
        if start_idx >= end_idx:
            return {"success": True, "emails": [], "detail": None}

        paged_ids = message_ids[start_idx:end_idx][::-1]
        emails_data: List[Dict[str, Any]] = []
        detail = None

        ids_str = b",".join(paged_ids)
        status, all_data = connection.fetch(ids_str, "(RFC822)")
        if status != "OK":
            return {"success": True, "emails": [], "detail": None}

        for i, (msg_id_str, raw_email) in enumerate(
            _parse_batch_fetch_response(all_data or [])
        ):
            msg = email.message_from_bytes(raw_email)
            body_preview = get_email_body(msg)
            email_item = {
                "id": msg_id_str,
                "subject": decode_header_value(msg.get("Subject", "无主题")),
                "from": decode_header_value(msg.get("From", "未知发件人")),
                "date": msg.get("Date", "未知时间"),
                "body_preview": body_preview[:200] + "..."
                if len(body_preview) > 200
                else body_preview,
            }
            emails_data.append(email_item)

            if i == 0:
                raw_text = (
                    raw_email.decode("utf-8", errors="replace")
                    if isinstance(raw_email, (bytes, bytearray))
                    else ""
                )
                detail = {
                    "id": email_item["id"],
                    "subject": email_item["subject"],
                    "from": email_item["from"],
                    "to": decode_header_value(msg.get("To", "")),
                    "cc": decode_header_value(msg.get("Cc", "")),
                    "date": email_item["date"],
                    "body": get_email_body(msg),
                    "body_html": _get_html_body(msg),
                    "raw_content": raw_text,
                }

        return {"success": True, "emails": emails_data, "detail": detail}
    except imaplib.IMAP4.error as exc:
        return {
            "success": False,
            "error": build_error_payload(
                "AUTH_FAILED", "IMAP认证失败", "IMAP4Error", 401, str(exc)
            ),
            "emails": [],
            "detail": None,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": build_error_payload(
                "EMAIL_FETCH_FAILED",
                "获取邮件失败",
                type(exc).__name__,
                500,
                str(exc),
            ),
            "emails": [],
            "detail": None,
        }
    finally:
        if connection:
            try:
                connection.logout()
            except Exception:
                pass


def get_emails_imap_concurrent(
    account: str,
    client_id: str,
    refresh_token: str,
    folder: str = "inbox",
    skip: int = 0,
    top: int = 20,
    servers: tuple = (IMAP_SERVER_NEW, "outlook.office365.com"),
) -> Dict[str, Any]:
    """并发连接多台 IMAP 服务器，返回第一个成功结果。"""
    if len(servers) <= 1:
        return get_emails_imap_with_server(
            account,
            client_id,
            refresh_token,
            folder,
            skip,
            top,
            servers[0] if servers else IMAP_SERVER_NEW,
        )

    last_error = None
    with ThreadPoolExecutor(max_workers=len(servers)) as executor:
        futures = {
            executor.submit(
                get_emails_imap_with_server,
                account,
                client_id,
                refresh_token,
                folder,
                skip,
                top,
                server,
            ): server
            for server in servers
        }
        for future in as_completed(futures):
            result = future.result()
            if result.get("success"):
                return result
            last_error = result

    return last_error or {
        "success": False,
        "error": {"code": "ALL_SERVERS_FAILED", "message": "所有服务器连接失败"},
    }


def get_email_detail_imap(
    account: str,
    client_id: str,
    refresh_token: str,
    message_id: str,
    folder: str = "inbox",
) -> Optional[Dict]:
    """使用 IMAP 获取邮件详情（默认使用新版服务器）。"""
    return get_email_detail_imap_with_server(
        account, client_id, refresh_token, message_id, folder, IMAP_SERVER_NEW
    )


def get_email_detail_imap_with_server(
    account: str,
    client_id: str,
    refresh_token: str,
    message_id: str,
    folder: str = "inbox",
    server: str = IMAP_SERVER_NEW,
) -> Optional[Dict]:
    """使用 IMAP 获取邮件详情（支持指定服务器）。"""
    access_token = get_access_token_imap(client_id, refresh_token)
    if not access_token:
        return None

    connection = None
    try:
        connection = imaplib.IMAP4_SSL(server, IMAP_PORT)
        auth_string = f"user={account}\1auth=Bearer {access_token}\1\1".encode("utf-8")
        connection.authenticate("XOAUTH2", lambda x: auth_string)

        folder_map = {
            "inbox": ['"INBOX"', "INBOX"],
            "junkemail": ['"Junk"', '"Junk Email"', "Junk", '"垃圾邮件"'],
            "deleteditems": [
                '"Deleted"',
                '"Deleted Items"',
                '"Trash"',
                "Deleted",
                '"已删除邮件"',
            ],
            "trash": [
                '"Deleted"',
                '"Deleted Items"',
                '"Trash"',
                "Deleted",
                '"已删除邮件"',
            ],
        }
        possible_folders = folder_map.get((folder or "").lower(), ['"INBOX"'])

        selected_folder = None
        for imap_folder in possible_folders:
            try:
                status, response = connection.select(imap_folder, readonly=True)
                if status == "OK":
                    selected_folder = imap_folder
                    break
            except Exception:
                continue

        if not selected_folder:
            return None

        fetch_id = message_id.encode() if isinstance(message_id, str) else message_id
        status, msg_data = connection.fetch(fetch_id, "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            return None

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        raw_text = ""
        try:
            raw_text = (
                raw_email.decode("utf-8", errors="replace")
                if isinstance(raw_email, (bytes, bytearray))
                else ""
            )
        except Exception:
            raw_text = ""

        return {
            "id": message_id,
            "subject": decode_header_value(msg.get("Subject", "无主题")),
            "from": decode_header_value(msg.get("From", "未知发件人")),
            "to": decode_header_value(msg.get("To", "")),
            "cc": decode_header_value(msg.get("Cc", "")),
            "date": msg.get("Date", "未知时间"),
            "body": get_email_body(msg),
            "raw_content": raw_text,
        }
    except Exception:
        return None
    finally:
        if connection:
            try:
                connection.logout()
            except Exception:
                pass


def delete_emails_imap(
    email_addr: str,
    client_id: str,
    refresh_token: str,
    message_ids: List[str],
    server: str,
) -> Dict[str, Any]:
    """通过 IMAP 删除邮件（永久删除）"""
    access_token = get_access_token_graph(client_id, refresh_token)
    if not access_token:
        return {"success": False, "error": "获取 Access Token 失败"}

    try:
        auth_string = "user=%s\x01auth=Bearer %s\x01\x01" % (email_addr, access_token)

        imap = imaplib.IMAP4_SSL(server, IMAP_PORT)
        imap.authenticate("XOAUTH2", lambda x: auth_string.encode("utf-8"))

        imap.select("INBOX")

        # Graph message id 与 IMAP UID 不兼容：保留原行为（暂不支持）
        return {"success": False, "error": "IMAP 删除暂不支持 (ID 格式不兼容)"}
    except Exception as e:
        return {"success": False, "error": str(e)}
