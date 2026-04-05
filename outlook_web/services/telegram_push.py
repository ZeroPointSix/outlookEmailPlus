"""outlook_web/services/telegram_push.py — Telegram 实时推送核心服务

轮询 IMAP/Graph 读取新邮件 → 构造消息 → 调用 Telegram Bot API → 丢弃内容，仅更新游标。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import List

import requests

from outlook_web.repositories import notification_state as notification_state_repo
from outlook_web.services import notification_dispatch
from outlook_web.services.providers import (
    get_imap_folder_candidates,
    infer_provider_from_email,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 文本工具
# ---------------------------------------------------------------------------

MAX_TELEGRAM_LENGTH = 4096
MAX_PREVIEW_LENGTH = 200
MAX_EMAILS_PER_FETCH = 50
MAX_SENT_PER_JOB = 20
TELEGRAM_PUSH_DELAY_SEC = 1.5  # 连续发送 Telegram 消息的间隔（防限流）


def _quote_imap_folder_name(folder_name: str) -> list[str]:
    name = (folder_name or "").strip()
    if not name:
        return []
    if name.startswith('"') and name.endswith('"'):
        return [name]
    if " " in name:
        return [name, f'"{name}"']
    return [name]


def _escape_html(text: str) -> str:
    """转义 Telegram HTML 模式必须转义的三种字符：& < >"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _html_to_plain(html_str: str) -> str:
    """将 HTML 正文提取为纯文本（strip tags），合并多余空白。"""
    if not html_str:
        return ""
    text = re.sub(r"<[^>]+>", " ", html_str)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _build_telegram_message(account_email: str, email: dict) -> str:
    """构造 Telegram HTML 消息文本（PRD §3.4 格式）。"""
    subject = _escape_html(email.get("subject", ""))
    sender = _escape_html(email.get("sender", ""))
    received_at = email.get("received_at", "")
    preview = email.get("preview", "")

    lines = [
        "📬 新邮件通知",
        "",
        f"账户：{_escape_html(account_email)}",
        f"发件人：{sender}",
        f"主题：{subject}",
        f"时间：{received_at}",
    ]

    if preview:
        truncated = preview[:MAX_PREVIEW_LENGTH]
        if len(preview) > MAX_PREVIEW_LENGTH:
            truncated += "..."
        lines.append("")
        lines.append(f"内容预览：\n{_escape_html(truncated)}")

    msg = "\n".join(lines)

    if len(msg) > MAX_TELEGRAM_LENGTH:
        msg = msg[: MAX_TELEGRAM_LENGTH - 3] + "..."

    return msg


# ---------------------------------------------------------------------------
# Telegram API
# ---------------------------------------------------------------------------


def _send_telegram_message(bot_token: str, chat_id: str, text: str) -> bool:
    """调用 Telegram sendMessage API。超时 10 秒，失败返回 False。
    自动读取系统 telegram_proxy_url 设置并透传给 requests。
    """
    from outlook_web.repositories import settings as settings_repo
    from outlook_web.services.graph import build_proxies

    proxy_url = settings_repo.get_telegram_proxy_url()
    proxies = build_proxies(proxy_url) if proxy_url else None

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
            proxies=proxies,
        )
        if not resp.ok:
            logger.warning("[telegram_push] send HTTP %s: %s", resp.status_code, resp.text[:200])
        return resp.ok
    except Exception as e:
        logger.warning("[telegram_push] send failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# 邮件拉取（IMAP / Graph）
# ---------------------------------------------------------------------------


def _resolve_imap_folder(account: dict, folder: str) -> list[str]:
    provider = str(account.get("provider") or "").strip().lower()
    if provider in {"", "imap"}:
        provider = infer_provider_from_email(str(account.get("email") or "")) or provider
    candidates = get_imap_folder_candidates(provider, folder)
    resolved: list[str] = []
    for candidate in candidates:
        resolved.extend(_quote_imap_folder_name(candidate))
    return resolved or ["INBOX"]


def _should_fetch_account_via_graph(account: dict) -> bool:
    account_type = str(account.get("account_type") or "").strip().lower()
    if account_type:
        return account_type == "outlook"
    return str(account.get("provider") or "").strip().lower() == "outlook"


def _call_fetcher_with_folder(fetcher, account: dict, since: str, folder: str) -> List[dict]:
    try:
        return fetcher(account, since, folder=folder)
    except TypeError as exc:
        if "unexpected keyword argument 'folder'" not in str(exc):
            raise
        return fetcher(account, since)


def _deduplicate_emails_for_source(account: dict, emails: List[dict]) -> List[dict]:
    source = {
        "source_type": notification_dispatch.SOURCE_ACCOUNT,
        "source_key": notification_dispatch.build_source_key(notification_dispatch.SOURCE_ACCOUNT, account.get("email", "")),
    }
    deduped: list[dict] = []
    seen: set[str] = set()
    for email_item in sorted(emails, key=lambda item: item.get("received_at", "")):
        message_key = notification_dispatch.build_message_key(source, email_item)
        if message_key in seen:
            continue
        seen.add(message_key)
        deduped.append(email_item)
    return deduped


def _should_fetch_account_via_graph(account: dict) -> bool:
    account_type = str(account.get("account_type") or "").strip().lower()
    if account_type:
        return account_type == "outlook"
    return str(account.get("provider") or "").strip().lower() == "outlook"


def _fetch_new_emails_imap(account: dict, since: str, folder: str = "inbox") -> List[dict]:
    """通过 IMAP 获取 received_at > since 的邮件，最多返回 50 封。

    两步策略：先用 INTERNALDATE 快速过滤，再对命中的邮件下载正文。
    """
    import email as email_lib
    import email.header
    import imaplib
    from datetime import datetime as dt

    from outlook_web.security.crypto import decrypt_data

    host = account.get("imap_host", "")
    port = int(account.get("imap_port", 993))
    password_raw = account.get("imap_password", "")
    password = decrypt_data(password_raw) if password_raw else ""
    user = account.get("email", "")

    since_dt = dt.fromisoformat(since)
    since_date_str = since_dt.strftime("%d-%b-%Y")

    results: List[dict] = []
    conn = None
    try:
        conn = imaplib.IMAP4_SSL(host, port, timeout=15)
        try:
            conn.login(user, password)
        except imaplib.IMAP4.error as exc:
            raw_message = str(exc or "")
            lowered = raw_message.lower()
            if (account.get("provider") or "").strip().lower() == "outlook" and "basicauthblocked" in lowered:
                raise RuntimeError("Outlook.com 已阻止 Basic Auth（账号密码直连）；请将该账号改为 Outlook OAuth 导入") from exc
            raise
        selected = False
        last_select_error = None
        for folder_name in _resolve_imap_folder(account, folder):
            try:
                status, _ = conn.select(folder_name, readonly=True)
                if status == "OK":
                    selected = True
                    break
                last_select_error = f"select {folder_name} status={status}"
            except Exception as exc:
                last_select_error = str(exc)
                continue
        if not selected:
            logger.warning(
                "[telegram_push] folder select failed email=%s provider=%s folder=%s err=%s",
                user,
                account.get("provider"),
                folder,
                last_select_error or "unknown",
            )
            return results

        _, data = conn.search(None, f'(SINCE "{since_date_str}")')
        msg_ids = data[0].split() if data[0] else []

        if not msg_ids:
            return results

        # 第一步：批量获取 INTERNALDATE 快速过滤
        candidate_ids = msg_ids[-MAX_EMAILS_PER_FETCH:]
        id_range = b",".join(candidate_ids)
        _, date_data = conn.fetch(id_range, "(INTERNALDATE)")

        import re

        date_pattern = re.compile(rb'INTERNALDATE "([^"]+)"')
        new_msg_ids = []

        for item in date_data:
            if not isinstance(item, tuple):
                continue
            header_line = item[0] if isinstance(item[0], bytes) else b""
            mid_match = re.match(rb"(\d+)", header_line)
            date_match = date_pattern.search(header_line)
            if not mid_match or not date_match:
                continue

            mid = mid_match.group(1)
            idate_str = date_match.group(1).decode("ascii", errors="replace")
            try:
                import calendar
                from imaplib import Internaldate2tuple

                tt = Internaldate2tuple(b'"' + date_match.group(1) + b'"')
                if tt:
                    ts = calendar.timegm(tt)
                    idate_iso = dt.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S")
                    if idate_iso <= since:
                        continue
            except Exception:
                pass  # 解析失败时保留，由后续 RFC822 过滤
            new_msg_ids.append(mid)

        # 第二步：仅对候选邮件下载 RFC822
        for mid in new_msg_ids[-MAX_EMAILS_PER_FETCH:]:
            try:
                _, msg_data = conn.fetch(mid, "(RFC822)")
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)

                subject_parts = email.header.decode_header(msg.get("Subject", ""))
                subject = "".join(
                    part.decode(charset or "utf-8") if isinstance(part, bytes) else part for part, charset in subject_parts
                )

                sender = msg.get("From", "")
                # 提取 Message-ID（BUG-00011 P2 去重用）
                raw_message_id = msg.get("Message-ID", "") or msg.get("Message-Id", "")
                if not raw_message_id:
                    raw_message_id = f"imap:{account.get('email', '')}:{mid.decode() if isinstance(mid, bytes) else mid}"
                date_str = msg.get("Date", "")
                try:
                    from email.utils import parsedate_to_datetime

                    received_dt = parsedate_to_datetime(date_str)
                    if received_dt.tzinfo is not None:
                        received_dt = received_dt.astimezone(timezone.utc)
                    received_iso = received_dt.strftime("%Y-%m-%dT%H:%M:%S")
                except Exception:
                    received_iso = date_str

                if received_iso <= since:
                    continue

                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        ct = part.get_content_type()
                        if ct == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode(
                                    part.get_content_charset() or "utf-8",
                                    errors="replace",
                                )
                            break
                        elif ct == "text/html" and not body:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = _html_to_plain(
                                    payload.decode(
                                        part.get_content_charset() or "utf-8",
                                        errors="replace",
                                    )
                                )
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        charset = msg.get_content_charset() or "utf-8"
                        raw_body = payload.decode(charset, errors="replace")
                        if msg.get_content_type() == "text/html":
                            body = _html_to_plain(raw_body)
                        else:
                            body = raw_body

                preview = body[:MAX_PREVIEW_LENGTH] if body else ""

                results.append(
                    {
                        "message_id": raw_message_id.strip(),
                        "subject": subject,
                        "sender": sender,
                        "received_at": received_iso,
                        "preview": preview,
                        "content": body,
                        "folder": folder,
                    }
                )
            except Exception:
                continue

    except Exception as e:
        logger.warning("[telegram_push] IMAP fetch error for %s: %s", account.get("email"), e)
        raise
    finally:
        if conn:
            try:
                conn.logout()
            except Exception:
                pass

    return results[:MAX_EMAILS_PER_FETCH]


def _fetch_new_emails_graph(account: dict, since: str, folder: str = "inbox") -> List[dict]:
    """通过 Microsoft Graph API 获取 received_at > since 的邮件，最多返回 50 封。"""
    from outlook_web.security.crypto import decrypt_data
    from outlook_web.services.graph import build_proxies, get_access_token_graph

    client_id = account.get("client_id", "")
    refresh_token_raw = account.get("refresh_token", "")
    refresh_token = decrypt_data(refresh_token_raw) if refresh_token_raw else ""
    proxy_url = account.get("proxy_url", "") or ""

    access_token = get_access_token_graph(client_id, refresh_token, proxy_url)
    if not access_token:
        return []

    since_z = since if since.endswith("Z") else since + "Z"
    folder_name = (folder or "inbox").strip().lower()
    url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder_name}/messages"
    params = {
        "$filter": f"receivedDateTime gt {since_z}",
        "$top": MAX_EMAILS_PER_FETCH,
        "$select": "id,subject,from,receivedDateTime,bodyPreview,internetMessageId,body",
        "$orderby": "receivedDateTime asc",
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    proxies = build_proxies(proxy_url)

    results: List[dict] = []
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15, proxies=proxies)
        if not resp.ok:
            return []
        data = resp.json()
        for item in data.get("value", []):
            sender_info = item.get("from", {}).get("emailAddress", {})
            sender = sender_info.get("address", sender_info.get("name", ""))
            received_raw = item.get("receivedDateTime", "")
            received_iso = received_raw.replace("Z", "").split(".")[0] if received_raw else ""
            preview = (item.get("bodyPreview", "") or "")[:MAX_PREVIEW_LENGTH]
            body = ""
            body_info = item.get("body") or {}
            if body_info.get("contentType") == "html":
                body = _html_to_plain(body_info.get("content", "") or "")
            else:
                body = body_info.get("content", "") or ""
            # BUG-00011 P2: 提取 Message-ID（优先 internetMessageId，回退 Graph id）
            msg_id = item.get("internetMessageId", "") or item.get("id", "")
            results.append(
                {
                    "message_id": msg_id,
                    "subject": item.get("subject", ""),
                    "sender": sender,
                    "received_at": received_iso,
                    "preview": preview,
                    "content": body,
                    "folder": folder_name,
                }
            )
    except Exception as e:
        logger.warning("[telegram_push] Graph fetch error for %s: %s", account.get("email"), e)
        raise

    return results


# ---------------------------------------------------------------------------
# Message-ID 去重（BUG-00011 P2）
# ---------------------------------------------------------------------------

PUSH_LOG_RETENTION_DAYS = 7  # 去重记录保留天数


def _is_message_pushed(db, account_id: int, message_id: str) -> bool:
    """检查该邮件是否已推送过。"""
    row = db.execute(
        "SELECT 1 FROM telegram_push_log WHERE account_id = ? AND message_id = ?",
        (account_id, message_id),
    ).fetchone()
    return row is not None


def _record_pushed_message(db, account_id: int, message_id: str) -> None:
    """记录已推送的邮件 Message-ID。"""
    try:
        db.execute(
            "INSERT OR IGNORE INTO telegram_push_log (account_id, message_id, pushed_at) VALUES (?, ?, ?)",
            (
                account_id,
                message_id,
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            ),
        )
        db.commit()
    except Exception:
        pass  # 去重失败不影响推送流程


def _cleanup_push_log(db) -> None:
    """清理超过 PUSH_LOG_RETENTION_DAYS 天的去重记录。"""
    try:
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=PUSH_LOG_RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
        db.execute("DELETE FROM telegram_push_log WHERE pushed_at < ?", (cutoff,))
        db.commit()
    except Exception:
        pass


def _has_message_been_sent(source: dict, message_key: str) -> bool:
    if notification_state_repo.was_delivered(
        notification_dispatch.CHANNEL_TELEGRAM,
        source["source_type"],
        source["source_key"],
        message_key,
    ):
        return True

    legacy_row = None
    try:
        from outlook_web.db import get_db

        db = get_db()
        legacy_row = db.execute(
            "SELECT 1 FROM telegram_push_log WHERE account_id = ? AND message_id = ?",
            (source.get("account_id"), message_key),
        ).fetchone()
    except Exception:
        legacy_row = None
    return legacy_row is not None


def _record_sent_message(source: dict, message_key: str) -> None:
    from outlook_web.db import get_db

    notification_state_repo.complete_delivery_attempt(
        notification_dispatch.CHANNEL_TELEGRAM,
        source["source_type"],
        source["source_key"],
        message_key,
        status="sent",
    )
    if source.get("account_id"):
        _record_pushed_message(get_db(), int(source["account_id"]), message_key)


def _record_failed_message(source: dict, message_key: str, error: Exception | str) -> None:
    notification_state_repo.complete_delivery_attempt(
        notification_dispatch.CHANNEL_TELEGRAM,
        source["source_type"],
        source["source_key"],
        message_key,
        status="failed",
        error_code=getattr(error, "code", "TELEGRAM_SEND_FAILED"),
        error_message=str(error),
    )


# ---------------------------------------------------------------------------
# 主入口（调度器调用）
# ---------------------------------------------------------------------------


def _fetch_account_emails(account: dict) -> tuple:
    """并行获取单个账号新邮件，返回 (account, emails_list, error)。"""
    last_checked = account.get("notification_cursor") or account.get("telegram_last_checked_at")
    if last_checked is None:
        return (account, None, None)  # 首次运行，仅设置游标

    try:
        if _should_fetch_account_via_graph(account):
            emails: List[dict] = []
            for folder in notification_dispatch.ACCOUNT_INCLUDED_FOLDERS:
                emails.extend(_call_fetcher_with_folder(_fetch_new_emails_graph, account, last_checked, folder))
        else:
            emails = []
            for folder in notification_dispatch.ACCOUNT_INCLUDED_FOLDERS:
                emails.extend(_call_fetcher_with_folder(_fetch_new_emails_imap, account, last_checked, folder))

        emails = _deduplicate_emails_for_source(account, emails)

        logger.info(
            "[telegram_push] account=%s provider=%s since=%s found=%d",
            account.get("email"),
            account.get("provider"),
            last_checked,
            len(emails),
        )
        return (account, emails, None)
    except Exception as e:
        logger.warning("[telegram_push] account=%s error: %s", account.get("email"), e)
        return (account, None, e)


def run_telegram_push_job(app) -> None:
    """主入口：并行轮询 → 去重 → 推送 → 更新游标。由调度器调用。"""
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    t0 = time.monotonic()
    logger.info("[telegram_push] job started")

    with app.app_context():
        from outlook_web.db import get_db
        from outlook_web.repositories.accounts import (
            get_telegram_push_accounts,
            update_telegram_cursor,
        )
        from outlook_web.repositories.settings import get_setting
        from outlook_web.security.crypto import decrypt_data, is_encrypted

        bot_token_raw = get_setting("telegram_bot_token", "")
        bot_token = decrypt_data(bot_token_raw) if bot_token_raw and is_encrypted(bot_token_raw) else bot_token_raw
        chat_id = get_setting("telegram_chat_id", "")

        if not bot_token or not chat_id:
            logger.info("[telegram_push] job skipped: no bot_token or chat_id")
            return

        accounts = get_telegram_push_accounts()
        if not accounts:
            logger.info("[telegram_push] job skipped: no push-enabled accounts")
            return

        normalized_accounts = []
        for account in accounts:
            source_key = notification_dispatch.build_source_key(notification_dispatch.SOURCE_ACCOUNT, account.get("email", ""))
            notification_cursor = notification_state_repo.get_cursor(
                notification_dispatch.CHANNEL_TELEGRAM,
                notification_dispatch.SOURCE_ACCOUNT,
                source_key,
            )
            account_copy = dict(account)
            account_copy["source_type"] = notification_dispatch.SOURCE_ACCOUNT
            account_copy["source_key"] = source_key
            account_copy["account_id"] = account.get("id")
            account_copy["notification_cursor"] = notification_cursor
            normalized_accounts.append(account_copy)

        job_start_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        sent_count = 0
        dedup_skipped = 0

        db = get_db()

        # 并行获取所有账号邮件
        fetch_results = []
        with ThreadPoolExecutor(max_workers=min(len(normalized_accounts), 10)) as executor:
            futures = {executor.submit(_fetch_account_emails, acc): acc for acc in normalized_accounts}
            for future in as_completed(futures):
                fetch_results.append(future.result())

        # 顺序推送 + 更新游标
        for account, emails, error in fetch_results:
            current_cursor = account.get("notification_cursor") or account.get("telegram_last_checked_at") or ""
            if emails is None and error is None:
                # 首次运行，仅设置游标
                update_telegram_cursor(account["id"], job_start_time)
                notification_state_repo.upsert_cursor(
                    notification_dispatch.CHANNEL_TELEGRAM,
                    account["source_type"],
                    account["source_key"],
                    job_start_time,
                )
                continue

            if error is not None:
                # fetch 失败，不推进游标
                continue

            safe_cursor = current_cursor

            if sent_count >= MAX_SENT_PER_JOB:
                continue

            account_id = account["id"]
            for em in sorted(emails, key=lambda e: e.get("received_at", "")):
                if sent_count >= MAX_SENT_PER_JOB:
                    break
                message_received_at = str(em.get("received_at", "") or "")
                message_key = notification_dispatch.build_message_key(
                    {
                        "source_type": account["source_type"],
                        "source_key": account["source_key"],
                    },
                    em,
                )
                claim_result = notification_state_repo.claim_delivery_attempt(
                    notification_dispatch.CHANNEL_TELEGRAM,
                    account["source_type"],
                    account["source_key"],
                    message_key,
                )
                source_meta = {
                    "source_type": account["source_type"],
                    "source_key": account["source_key"],
                    "account_id": account_id,
                }
                if claim_result == "sent":
                    dedup_skipped += 1
                    if message_received_at:
                        safe_cursor = notification_dispatch._max_cursor_value(safe_cursor, message_received_at)
                    continue
                if _has_message_been_sent(source_meta, message_key):
                    notification_state_repo.complete_delivery_attempt(
                        notification_dispatch.CHANNEL_TELEGRAM,
                        account["source_type"],
                        account["source_key"],
                        message_key,
                        status="sent",
                    )
                    dedup_skipped += 1
                    if message_received_at:
                        safe_cursor = notification_dispatch._max_cursor_value(safe_cursor, message_received_at)
                    continue
                if claim_result != "acquired":
                    logger.info(
                        "[telegram_push] skip delivery without lock account=%s message=%s state=%s",
                        account.get("email"),
                        message_key,
                        claim_result,
                    )
                    continue

                msg = _build_telegram_message(account["email"], em)
                if _send_telegram_message(bot_token, chat_id, msg):
                    sent_count += 1
                    _record_sent_message(
                        {
                            "source_type": account["source_type"],
                            "source_key": account["source_key"],
                            "account_id": account_id,
                        },
                        message_key,
                    )
                    if message_received_at:
                        safe_cursor = notification_dispatch._max_cursor_value(safe_cursor, message_received_at)
                    # 消息间延迟，防止 Telegram API 限流
                    if TELEGRAM_PUSH_DELAY_SEC > 0:
                        time.sleep(TELEGRAM_PUSH_DELAY_SEC)
                else:
                    _record_failed_message(
                        {
                            "source_type": account["source_type"],
                            "source_key": account["source_key"],
                            "account_id": account_id,
                        },
                        message_key,
                        "telegram_send_failed",
                    )
                    break

            update_telegram_cursor(account["id"], safe_cursor)
            notification_state_repo.upsert_cursor(
                notification_dispatch.CHANNEL_TELEGRAM,
                account["source_type"],
                account["source_key"],
                safe_cursor,
            )

        # 定期清理过期去重记录（>7 天）
        _cleanup_push_log(db)

    elapsed = time.monotonic() - t0
    logger.info(
        "[telegram_push] job finished: sent=%d dedup_skipped=%d elapsed=%.1fs",
        sent_count,
        dedup_skipped,
        elapsed,
    )
