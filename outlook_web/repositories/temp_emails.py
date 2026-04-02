from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from outlook_web.db import get_db

_TEMP_EMAIL_RICH_KEYS = (
    "attachments",
    "inline_attachments",
    "inlineAttachments",
    "inline_images",
    "inlineImages",
    "resources",
    "images",
    "cid_map",
    "cidMap",
)

TEMP_MAIL_KIND = "temp"
TEMP_MAIL_READ_CAPABILITY = "temp_provider"
DEFAULT_TEMP_MAIL_SOURCE = "custom_domain_temp_mail"
LEGACY_TEMP_MAIL_SOURCE = "legacy_gptmail"
DEFAULT_TEMP_MAIL_PROVIDER_NAME = "custom_domain_temp_mail"
LEGACY_TEMP_MAIL_PROVIDER_NAME = "legacy_bridge"

DEFAULT_PROVIDER_CAPABILITIES = {
    "delete_mailbox": False,
    "delete_message": True,
    "clear_messages": True,
}


def _serialize_temp_email_payload(message: Dict[str, Any]) -> str:
    try:
        return json.dumps(message or {}, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return str(message or "")


def _load_temp_email_payload(raw_content: Any) -> Dict[str, Any]:
    if isinstance(raw_content, dict):
        return raw_content
    if not isinstance(raw_content, str) or not raw_content.strip():
        return {}
    try:
        payload = json.loads(raw_content)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _score_temp_email_payload(payload: Any) -> int:
    payload_dict = _load_temp_email_payload(payload)
    if not payload_dict:
        return 0

    score = 0
    if str(
        payload_dict.get("html_content") or payload_dict.get("body_html") or ""
    ).strip():
        score += 20
    for key in _TEMP_EMAIL_RICH_KEYS:
        value = payload_dict.get(key)
        if isinstance(value, dict) and value:
            score += 30
        elif isinstance(value, list) and value:
            score += 30
    score += min(len(payload_dict), 20)
    return score


def _choose_richer_temp_email_payload(
    existing_payload: Any, incoming_payload: Any
) -> str:
    existing_score = _score_temp_email_payload(existing_payload)
    incoming_score = _score_temp_email_payload(incoming_payload)
    if incoming_score >= existing_score:
        normalized = _load_temp_email_payload(incoming_payload) or incoming_payload
        return _serialize_temp_email_payload(normalized)
    normalized = _load_temp_email_payload(existing_payload) or existing_payload
    return _serialize_temp_email_payload(normalized)


def _default_provider_name_for_source(source: str | None) -> str:
    normalized_source = str(source or "").strip().lower()
    if normalized_source == LEGACY_TEMP_MAIL_SOURCE:
        return LEGACY_TEMP_MAIL_PROVIDER_NAME
    return DEFAULT_TEMP_MAIL_PROVIDER_NAME


def deserialize_temp_email_meta(
    raw_meta: Any, *, source: str | None = None
) -> Dict[str, Any]:
    if isinstance(raw_meta, dict):
        meta = dict(raw_meta)
    elif isinstance(raw_meta, str) and raw_meta.strip():
        try:
            parsed = json.loads(raw_meta)
            meta = parsed if isinstance(parsed, dict) else {}
        except Exception:
            meta = {}
    else:
        meta = {}

    provider_capabilities = meta.get("provider_capabilities")
    if not isinstance(provider_capabilities, dict):
        provider_capabilities = {}

    provider_debug = meta.get("provider_debug")
    if not isinstance(provider_debug, dict):
        provider_debug = {}

    if str(
        source or ""
    ).strip().lower() == LEGACY_TEMP_MAIL_SOURCE and not provider_debug.get("bridge"):
        provider_debug["bridge"] = "gptmail"

    provider_labels = meta.get("provider_labels")
    if not isinstance(provider_labels, list):
        provider_labels = []

    normalized = {
        "provider_name": str(
            meta.get("provider_name") or _default_provider_name_for_source(source)
        ).strip()
        or _default_provider_name_for_source(source),
        "provider_mailbox_id": str(meta.get("provider_mailbox_id") or "").strip(),
        "provider_jwt": str(meta.get("provider_jwt") or "").strip(),
        "provider_cursor": str(meta.get("provider_cursor") or "").strip(),
        "provider_labels": [
            str(item).strip() for item in provider_labels if str(item or "").strip()
        ],
        "provider_capabilities": {
            "delete_mailbox": bool(
                provider_capabilities.get(
                    "delete_mailbox", DEFAULT_PROVIDER_CAPABILITIES["delete_mailbox"]
                )
            ),
            "delete_message": bool(
                provider_capabilities.get(
                    "delete_message", DEFAULT_PROVIDER_CAPABILITIES["delete_message"]
                )
            ),
            "clear_messages": bool(
                provider_capabilities.get(
                    "clear_messages", DEFAULT_PROVIDER_CAPABILITIES["clear_messages"]
                )
            ),
        },
        "provider_debug": provider_debug,
    }
    return normalized


def serialize_temp_email_meta(meta: Any, *, source: str | None = None) -> str:
    normalized = deserialize_temp_email_meta(meta, source=source)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def get_temp_email_group_id() -> int:
    """获取临时邮箱分组的 ID"""
    db = get_db()
    cursor = db.execute("SELECT id FROM groups WHERE name = '临时邮箱'")
    row = cursor.fetchone()
    return row["id"] if row else 2


def _serialize_temp_email_row(row: Any) -> Dict[str, Any]:
    if not row:
        return {}
    item = dict(row)
    item["visible_in_ui"] = bool(item.get("visible_in_ui", 0))
    item["created_by"] = (
        "task"
        if str(item.get("mailbox_type") or "").strip().lower() == "task"
        else "user"
    )
    item["meta_json"] = deserialize_temp_email_meta(
        item.get("meta_json"), source=item.get("source")
    )
    item["provider_name"] = str(
        item["meta_json"].get("provider_name")
        or _default_provider_name_for_source(item.get("source"))
    )
    return item


def build_temp_mailbox_descriptor(record: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _serialize_temp_email_row(record)
    email_addr = str(normalized.get("email") or "").strip()
    prefix = str(
        normalized.get("prefix")
        or (email_addr.split("@", 1)[0] if "@" in email_addr else "")
    ).strip()
    domain = str(
        normalized.get("domain")
        or (email_addr.split("@", 1)[1] if "@" in email_addr else "")
    ).strip()
    return {
        "kind": TEMP_MAIL_KIND,
        "email": email_addr,
        "source": str(normalized.get("source") or DEFAULT_TEMP_MAIL_SOURCE),
        "provider_name": str(
            normalized.get("provider_name")
            or _default_provider_name_for_source(normalized.get("source"))
        ),
        "mailbox_type": str(normalized.get("mailbox_type") or "user").strip().lower()
        or "user",
        "visible_in_ui": bool(normalized.get("visible_in_ui")),
        "status": str(normalized.get("status") or "active").strip().lower() or "active",
        "prefix": prefix,
        "domain": domain,
        "task_token": str(normalized.get("task_token") or "").strip(),
        "consumer_key": str(normalized.get("consumer_key") or "").strip(),
        "caller_id": str(normalized.get("caller_id") or "").strip(),
        "task_id": str(normalized.get("task_id") or "").strip(),
        "created_at": str(normalized.get("created_at") or ""),
        "updated_at": str(normalized.get("updated_at") or ""),
        "finished_at": str(normalized.get("finished_at") or ""),
        "read_capability": TEMP_MAIL_READ_CAPABILITY,
        "meta": dict(normalized.get("meta_json") or {}),
        "record": normalized,
    }


def build_temp_mailbox_public_dto(record: Dict[str, Any]) -> Dict[str, Any]:
    descriptor = build_temp_mailbox_descriptor(record)
    return {
        "email": descriptor["email"],
        "prefix": descriptor["prefix"],
        "domain": descriptor["domain"],
        "source": descriptor["source"],
        "mailbox_type": descriptor["mailbox_type"],
        "visible_in_ui": descriptor["visible_in_ui"],
        "status": descriptor["status"],
        "created_at": descriptor["created_at"],
        "task_token": descriptor["task_token"],
    }


def load_temp_emails(
    *,
    visible_only: bool = False,
    mailbox_type: Optional[str] = None,
    status: Optional[str] = None,
    consumer_key: Optional[str] = None,
    view: str = "record",
) -> List[Dict]:
    """加载临时邮箱，支持按可见性/类型/状态/调用方归属筛选。"""
    db = get_db()
    clauses: list[str] = []
    params: list[Any] = []
    if visible_only:
        clauses.append("visible_in_ui = 1")
    if mailbox_type:
        clauses.append("mailbox_type = ?")
        params.append(str(mailbox_type).strip())
    if status:
        clauses.append("status = ?")
        params.append(str(status).strip())
    if consumer_key:
        clauses.append("consumer_key = ?")
        params.append(str(consumer_key).strip())
    sql = "SELECT * FROM temp_emails"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC"
    cursor = db.execute(sql, params)
    rows = cursor.fetchall()
    serialized = [_serialize_temp_email_row(row) for row in rows]
    if view == "descriptor":
        return [build_temp_mailbox_descriptor(row) for row in serialized]
    if view == "public":
        return [build_temp_mailbox_public_dto(row) for row in serialized]
    return serialized


def get_temp_email_by_address(
    email_addr: str, *, view: str = "record"
) -> Optional[Dict]:
    """根据邮箱地址获取临时邮箱"""
    db = get_db()
    cursor = db.execute("SELECT * FROM temp_emails WHERE email = ?", (email_addr,))
    row = cursor.fetchone()
    if not row:
        return None
    serialized = _serialize_temp_email_row(row)
    if view == "descriptor":
        return build_temp_mailbox_descriptor(serialized)
    if view == "public":
        return build_temp_mailbox_public_dto(serialized)
    return serialized


def get_temp_email_by_task_token(
    task_token: str, *, view: str = "record"
) -> Optional[Dict]:
    db = get_db()
    cursor = db.execute("SELECT * FROM temp_emails WHERE task_token = ?", (task_token,))
    row = cursor.fetchone()
    if not row:
        return None
    serialized = _serialize_temp_email_row(row)
    if view == "descriptor":
        return build_temp_mailbox_descriptor(serialized)
    if view == "public":
        return build_temp_mailbox_public_dto(serialized)
    return serialized


def create_temp_email(
    *,
    email_addr: str,
    mailbox_type: str = "user",
    visible_in_ui: bool = True,
    source: str = "custom_domain_temp_mail",
    prefix: Optional[str] = None,
    domain: Optional[str] = None,
    task_token: Optional[str] = None,
    consumer_key: Optional[str] = None,
    caller_id: Optional[str] = None,
    task_id: Optional[str] = None,
    meta_json: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    provider_name: Optional[str] = None,
    status: str = "active",
) -> bool:
    """创建临时邮箱记录。"""
    db = get_db()
    normalized_email = str(email_addr or "").strip()
    normalized_prefix = (
        prefix
        if prefix is not None
        else (normalized_email.split("@", 1)[0] if "@" in normalized_email else None)
    )
    normalized_domain = (
        domain
        if domain is not None
        else (normalized_email.split("@", 1)[1] if "@" in normalized_email else None)
    )
    normalized_source = (
        str(source or DEFAULT_TEMP_MAIL_SOURCE).strip() or DEFAULT_TEMP_MAIL_SOURCE
    )
    normalized_meta_source = meta if meta is not None else meta_json
    normalized_meta_json = serialize_temp_email_meta(
        normalized_meta_source,
        source=normalized_source,
    )
    if provider_name:
        normalized_meta = deserialize_temp_email_meta(
            normalized_meta_json, source=normalized_source
        )
        normalized_meta["provider_name"] = str(
            provider_name
        ).strip() or _default_provider_name_for_source(normalized_source)
        normalized_meta_json = serialize_temp_email_meta(
            normalized_meta, source=normalized_source
        )
    try:
        db.execute(
            """
            INSERT INTO temp_emails (
                email, status, mailbox_type, visible_in_ui, source, prefix, domain,
                task_token, consumer_key, caller_id, task_id, meta_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_email,
                str(status or "active").strip() or "active",
                str(mailbox_type or "user").strip() or "user",
                1 if visible_in_ui else 0,
                normalized_source,
                normalized_prefix,
                normalized_domain,
                str(task_token or "").strip() or None,
                str(consumer_key or "").strip() or None,
                str(caller_id or "").strip() or None,
                str(task_id or "").strip() or None,
                normalized_meta_json,
            ),
        )
        db.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def add_temp_email(email_addr: str) -> bool:
    """兼容旧调用：添加用户可见临时邮箱。"""
    return create_temp_email(email_addr=email_addr)


def finish_task_temp_email(task_token: str, *, result_status: str = "finished") -> bool:
    db = get_db()
    cursor = db.execute(
        """
        UPDATE temp_emails
        SET status = ?, finished_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE task_token = ? AND mailbox_type = 'task'
        """,
        (str(result_status or "finished").strip() or "finished", task_token),
    )
    db.commit()
    return cursor.rowcount > 0


def delete_temp_email(email_addr: str) -> bool:
    """删除临时邮箱及其所有邮件"""
    db = get_db()
    try:
        db.execute(
            "DELETE FROM temp_email_messages WHERE email_address = ?", (email_addr,)
        )
        db.execute("DELETE FROM temp_emails WHERE email = ?", (email_addr,))
        db.commit()
        return True
    except Exception:
        return False


def save_temp_email_messages(email_addr: str, messages: List[Dict]) -> int:
    """保存临时邮件到数据库"""
    db = get_db()
    saved = 0
    for msg in messages:
        try:
            message_id = str(msg.get("id") or "").strip()
            if not message_id:
                continue

            existing = get_temp_email_message_by_id(message_id, email_addr=email_addr)
            content = str(msg.get("content") or msg.get("body_text") or "")
            html_content = str(msg.get("html_content") or msg.get("body_html") or "")
            from_address = str(
                msg.get("from_address")
                or msg.get("source")  # CF Worker 字段名
                or msg.get("from")  # Graph API 风格
                or msg.get("sender")  # 其他常见格式
                or ""
            )
            subject = str(msg.get("subject") or "")
            _ts_raw = msg.get("timestamp") or msg.get("created_at")
            if isinstance(_ts_raw, str):
                from datetime import datetime as _dt

                try:
                    _ts_clean = _ts_raw.replace("Z", "+00:00").replace(".000", "")
                    timestamp = int(_dt.fromisoformat(_ts_clean).timestamp())
                except (ValueError, AttributeError):
                    timestamp = 0
            else:
                timestamp = int(_ts_raw or 0)
            raw_content = _serialize_temp_email_payload(msg)

            if existing:
                if not content:
                    content = str(existing.get("content") or "")
                if not html_content:
                    html_content = str(existing.get("html_content") or "")
                if not from_address:
                    from_address = str(existing.get("from_address") or "")
                if not subject:
                    subject = str(existing.get("subject") or "")
                if not timestamp:
                    timestamp = existing.get("timestamp", 0)
                raw_content = _choose_richer_temp_email_payload(
                    existing.get("raw_content"), msg
                )

            has_html = bool(
                msg.get("has_html")
                or html_content
                or (existing and existing.get("has_html"))
            )
            db.execute(
                """
                INSERT OR REPLACE INTO temp_email_messages
                (message_id, email_address, from_address, subject, content, html_content, has_html, timestamp, raw_content)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    email_addr,
                    from_address,
                    subject,
                    content,
                    html_content,
                    1 if has_html else 0,
                    timestamp,
                    raw_content,
                ),
            )
            saved += 1
        except Exception:
            continue
    db.commit()
    return saved


def get_temp_email_messages(email_addr: str) -> List[Dict]:
    """获取临时邮箱的所有邮件（从数据库）"""
    db = get_db()
    cursor = db.execute(
        """
        SELECT * FROM temp_email_messages
        WHERE email_address = ?
        ORDER BY timestamp DESC
        """,
        (email_addr,),
    )
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


def get_temp_email_message_by_id(
    message_id: str, *, email_addr: Optional[str] = None
) -> Optional[Dict]:
    """根据消息 ID 获取临时邮件，优先按邮箱地址定位。"""
    db = get_db()
    if email_addr:
        cursor = db.execute(
            """
            SELECT * FROM temp_email_messages
            WHERE email_address = ? AND message_id = ?
            LIMIT 1
            """,
            (email_addr, message_id),
        )
    else:
        cursor = db.execute(
            """
            SELECT * FROM temp_email_messages
            WHERE message_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (message_id,),
        )
    row = cursor.fetchone()
    return dict(row) if row else None


def delete_temp_email_message(
    message_id: str, *, email_addr: Optional[str] = None
) -> bool:
    """删除临时邮件，提供邮箱地址时仅删除目标邮箱下的消息。"""
    db = get_db()
    try:
        if email_addr:
            db.execute(
                "DELETE FROM temp_email_messages WHERE email_address = ? AND message_id = ?",
                (email_addr, message_id),
            )
        else:
            db.execute(
                "DELETE FROM temp_email_messages WHERE message_id = ?", (message_id,)
            )
        db.commit()
        return True
    except Exception:
        return False


def get_temp_email_count(*, visible_only: bool = False) -> int:
    """获取临时邮箱数量。"""
    db = get_db()
    if visible_only:
        cursor = db.execute(
            "SELECT COUNT(*) as count FROM temp_emails WHERE visible_in_ui = 1"
        )
    else:
        cursor = db.execute("SELECT COUNT(*) as count FROM temp_emails")
    row = cursor.fetchone()
    return row["count"] if row else 0
