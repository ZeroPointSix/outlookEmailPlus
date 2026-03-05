"""outlook_web/services/telegram_push.py — Telegram 实时推送核心服务

轮询 IMAP/Graph 读取新邮件 → 构造消息 → 调用 Telegram Bot API → 丢弃内容，仅更新游标。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import List

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 文本工具
# ---------------------------------------------------------------------------

MAX_TELEGRAM_LENGTH = 4096
MAX_PREVIEW_LENGTH = 200
MAX_EMAILS_PER_FETCH = 50
MAX_SENT_PER_JOB = 20
PUSH_RECENCY_HOURS = 12  # 超过此小时数的邮件不推送（防止首次启用时轰炸）
TELEGRAM_PUSH_DELAY_SEC = 1.5  # 连续发送 Telegram 消息的间隔（防限流）


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
    """调用 Telegram sendMessage API。超时 10 秒，失败返回 False。"""
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


def _fetch_new_emails_imap(account: dict, since: str) -> List[dict]:
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
        conn.login(user, password)
        conn.select("INBOX", readonly=True)

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
                from imaplib import Internaldate2tuple
                import calendar
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
                    part.decode(charset or "utf-8") if isinstance(part, bytes) else part
                    for part, charset in subject_parts
                )

                sender = msg.get("From", "")
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
                                body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                            break
                        elif ct == "text/html" and not body:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = _html_to_plain(
                                    payload.decode(part.get_content_charset() or "utf-8", errors="replace")
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
                        "subject": subject,
                        "sender": sender,
                        "received_at": received_iso,
                        "preview": preview,
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


def _fetch_new_emails_graph(account: dict, since: str) -> List[dict]:
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
    url = "https://graph.microsoft.com/v1.0/me/messages"
    params = {
        "$filter": f"receivedDateTime gt {since_z}",
        "$top": MAX_EMAILS_PER_FETCH,
        "$select": "subject,from,receivedDateTime,bodyPreview",
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
            results.append(
                {
                    "subject": item.get("subject", ""),
                    "sender": sender,
                    "received_at": received_iso,
                    "preview": preview,
                }
            )
    except Exception as e:
        logger.warning("[telegram_push] Graph fetch error for %s: %s", account.get("email"), e)
        raise

    return results


# ---------------------------------------------------------------------------
# 主入口（调度器调用）
# ---------------------------------------------------------------------------


def _fetch_account_emails(account: dict) -> tuple:
    """并行获取单个账号新邮件，返回 (account, emails_list, error)。"""
    last_checked = account.get("telegram_last_checked_at")
    if last_checked is None:
        return (account, None, None)  # 首次运行，仅设置游标

    try:
        if account.get("provider") == "outlook":
            emails = _fetch_new_emails_graph(account, last_checked)
        else:
            emails = _fetch_new_emails_imap(account, last_checked)

        logger.info(
            "[telegram_push] account=%s provider=%s since=%s found=%d",
            account.get("email"), account.get("provider"), last_checked, len(emails),
        )
        return (account, emails, None)
    except Exception as e:
        logger.warning("[telegram_push] account=%s error: %s", account.get("email"), e)
        return (account, None, e)


def run_telegram_push_job(app) -> None:
    """主入口：并行轮询 → 推送 → 更新游标。由调度器调用。"""
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    t0 = time.monotonic()
    logger.info("[telegram_push] job started")

    with app.app_context():
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

        job_start_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        # 计算 recency 截止时间（超过此时间的邮件不推送）
        from datetime import timedelta
        recency_cutoff = (datetime.now(timezone.utc) - timedelta(hours=PUSH_RECENCY_HOURS)).strftime("%Y-%m-%dT%H:%M:%S")
        sent_count = 0

        # 并行获取所有账号邮件
        fetch_results = []
        with ThreadPoolExecutor(max_workers=min(len(accounts), 10)) as executor:
            futures = {executor.submit(_fetch_account_emails, acc): acc for acc in accounts}
            for future in as_completed(futures):
                fetch_results.append(future.result())

        # 顺序推送 + 更新游标
        for account, emails, error in fetch_results:
            if emails is None and error is None:
                # 首次运行，仅设置游标
                update_telegram_cursor(account["id"], job_start_time)
                continue

            if error is not None:
                # fetch 失败，不推进游标
                continue

            if sent_count >= MAX_SENT_PER_JOB:
                update_telegram_cursor(account["id"], job_start_time)
                continue

            for em in sorted(emails, key=lambda e: e.get("received_at", "")):
                if sent_count >= MAX_SENT_PER_JOB:
                    break
                # 跳过超过 PUSH_RECENCY_HOURS 的旧邮件
                if em.get("received_at", "") < recency_cutoff:
                    continue
                msg = _build_telegram_message(account["email"], em)
                if _send_telegram_message(bot_token, chat_id, msg):
                    sent_count += 1
                    # 消息间延迟，防止 Telegram API 限流
                    if TELEGRAM_PUSH_DELAY_SEC > 0:
                        time.sleep(TELEGRAM_PUSH_DELAY_SEC)

            update_telegram_cursor(account["id"], job_start_time)

    elapsed = time.monotonic() - t0
    logger.info("[telegram_push] job finished: sent=%d elapsed=%.1fs", sent_count, elapsed)
