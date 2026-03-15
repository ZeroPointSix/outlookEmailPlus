from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any, Iterable

from outlook_web.db import get_db
from outlook_web.security.crypto import decrypt_data, encrypt_data


def _mask_secret_value(value: str, head: int = 4, tail: int = 4) -> str:
    if not value:
        return ""
    safe_value = str(value)
    if len(safe_value) <= head + tail:
        return "*" * len(safe_value)
    return safe_value[:head] + ("*" * (len(safe_value) - head - tail)) + safe_value[-tail:]


def _parse_allowed_emails(raw: Any) -> list[str]:
    if raw in (None, "", []):
        return []
    values = raw
    if isinstance(raw, str):
        try:
            values = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            values = [item.strip() for item in raw.replace("\r", "\n").replace(",", "\n").split("\n")]

    if not isinstance(values, list):
        return []

    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        email_addr = str(item or "").strip().lower()
        if not email_addr or "@" not in email_addr or email_addr in seen:
            continue
        seen.add(email_addr)
        result.append(email_addr)
    return result


def _allowed_emails_json(allowed_emails: Iterable[str] | None) -> str:
    return json.dumps(_parse_allowed_emails(list(allowed_emails or [])), ensure_ascii=False)


def _coerce_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return default


def _build_consumer_key(key_id: int | str) -> str:
    return f"key:{key_id}"


def _decrypt_api_key(value: str) -> str:
    if not value:
        return ""
    try:
        return decrypt_data(value)
    except Exception:
        return ""


def _serialize_row(row: Any) -> dict[str, Any]:
    api_key_plain = _decrypt_api_key(row["api_key_encrypted"] or "")
    allowed_emails = _parse_allowed_emails(row["allowed_emails_json"] or "[]")
    return {
        "id": row["id"],
        "consumer_key": _build_consumer_key(row["id"]),
        "name": row["name"] or "",
        "enabled": bool(row["enabled"]),
        "allowed_emails": allowed_emails,
        "api_key_masked": _mask_secret_value(api_key_plain) if api_key_plain else "",
        "last_used_at": row["last_used_at"] or "",
        "created_at": row["created_at"] or "",
        "updated_at": row["updated_at"] or "",
    }


def list_external_api_keys(*, include_disabled: bool = True) -> list[dict[str, Any]]:
    db = get_db()
    sql = """
        SELECT id, name, api_key_encrypted, allowed_emails_json, enabled, last_used_at, created_at, updated_at
        FROM external_api_keys
    """
    params: list[Any] = []
    if not include_disabled:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY id ASC"
    rows = db.execute(sql, params).fetchall()
    return [_serialize_row(row) for row in rows]


def get_external_api_key_by_id(key_id: int) -> dict[str, Any] | None:
    db = get_db()
    row = db.execute(
        """
        SELECT id, name, api_key_encrypted, allowed_emails_json, enabled, last_used_at, created_at, updated_at
        FROM external_api_keys
        WHERE id = ?
        """,
        (int(key_id),),
    ).fetchone()
    return _serialize_row(row) if row else None


def create_external_api_key(
    *,
    name: str,
    api_key: str,
    allowed_emails: Iterable[str] | None = None,
    enabled: bool = True,
    commit: bool = True,
) -> dict[str, Any]:
    db = get_db()
    db.execute(
        """
        INSERT INTO external_api_keys (name, api_key_encrypted, allowed_emails_json, enabled, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            str(name or "").strip(),
            encrypt_data(str(api_key or "").strip()),
            _allowed_emails_json(allowed_emails),
            1 if _coerce_bool(enabled, True) else 0,
        ),
    )
    if commit:
        db.commit()
    row_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    return get_external_api_key_by_id(row_id) or {}


def update_external_api_key(
    key_id: int,
    *,
    name: str | None = None,
    api_key: str | None = None,
    allowed_emails: Iterable[str] | None = None,
    enabled: bool | None = None,
    commit: bool = True,
) -> dict[str, Any] | None:
    existing = get_external_api_key_by_id(int(key_id))
    if not existing:
        return None

    db = get_db()
    db.execute(
        """
        UPDATE external_api_keys
        SET name = ?,
            api_key_encrypted = ?,
            allowed_emails_json = ?,
            enabled = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            str(existing["name"] if name is None else name).strip(),
            (
                encrypt_data(str(api_key).strip())
                if api_key is not None
                else db.execute(
                    "SELECT api_key_encrypted FROM external_api_keys WHERE id = ?",
                    (int(key_id),),
                ).fetchone()["api_key_encrypted"]
            ),
            _allowed_emails_json(existing["allowed_emails"] if allowed_emails is None else allowed_emails),
            int(_coerce_bool(existing["enabled"] if enabled is None else enabled, bool(existing["enabled"]))),
            int(key_id),
        ),
    )
    if commit:
        db.commit()
    return get_external_api_key_by_id(int(key_id))


def delete_external_api_key(key_id: int, *, commit: bool = True) -> bool:
    db = get_db()
    cursor = db.execute("DELETE FROM external_api_keys WHERE id = ?", (int(key_id),))
    if commit:
        db.commit()
    return cursor.rowcount > 0


def replace_external_api_keys(items: list[dict[str, Any]], *, commit: bool = True) -> list[dict[str, Any]]:
    existing_rows = list_external_api_keys(include_disabled=True)
    existing_ids = {int(item["id"]): item for item in existing_rows}
    seen_ids: set[int] = set()

    for raw_item in items:
        item_id = raw_item.get("id")
        name = str(raw_item.get("name") or "").strip()
        api_key = raw_item.get("api_key")
        allowed_emails = raw_item.get("allowed_emails")
        enabled = _coerce_bool(raw_item.get("enabled", True), True)

        if item_id in (None, ""):
            create_external_api_key(
                name=name,
                api_key=str(api_key or "").strip(),
                allowed_emails=_parse_allowed_emails(allowed_emails),
                enabled=enabled,
                commit=False,
            )
            continue

        key_id = int(item_id)
        existing = existing_ids.get(key_id)
        if not existing:
            continue
        seen_ids.add(key_id)
        if api_key == existing.get("api_key_masked"):
            api_key = None
        update_external_api_key(
            key_id,
            name=name,
            api_key=None if api_key in (None, "") and existing.get("api_key_masked") else api_key,
            allowed_emails=_parse_allowed_emails(allowed_emails) if allowed_emails is not None else existing["allowed_emails"],
            enabled=enabled,
            commit=False,
        )

    for key_id in existing_ids:
        if key_id not in seen_ids:
            delete_external_api_key(key_id, commit=False)

    if commit:
        get_db().commit()

    return list_external_api_keys(include_disabled=True)


def has_any_external_api_key_configured(*, enabled_only: bool = False) -> bool:
    db = get_db()
    sql = "SELECT COUNT(*) AS c FROM external_api_keys"
    params: list[Any] = []
    if enabled_only:
        sql += " WHERE enabled = 1"
    row = db.execute(sql, params).fetchone()
    return bool(row and int(row["c"] or 0) > 0)


def find_external_api_key_by_plaintext(provided_key: str) -> dict[str, Any] | None:
    provided = str(provided_key or "").strip()
    if not provided:
        return None

    db = get_db()
    rows = db.execute("""
        SELECT id, name, api_key_encrypted, allowed_emails_json, enabled, last_used_at, created_at, updated_at
        FROM external_api_keys
        WHERE enabled = 1
        ORDER BY id ASC
        """).fetchall()

    for row in rows:
        plain = _decrypt_api_key(row["api_key_encrypted"] or "")
        if plain and secrets.compare_digest(plain, provided):
            return _serialize_row(row)
    return None


def mark_external_api_key_used(key_id: int) -> None:
    db = get_db()
    used_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    db.execute(
        """
        UPDATE external_api_keys
        SET last_used_at = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (used_at, int(key_id)),
    )
    db.commit()


def record_external_api_consumer_usage(
    *,
    consumer_key: str,
    consumer_name: str,
    endpoint: str,
    status: str,
) -> None:
    if not consumer_key or not endpoint:
        return
    db = get_db()
    usage_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    last_used_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    success_inc = 1 if str(status or "").lower() == "ok" else 0
    error_inc = 0 if success_inc else 1
    db.execute(
        """
        INSERT INTO external_api_consumer_usage_daily (
            consumer_key, consumer_name, usage_date, endpoint,
            total_count, success_count, error_count, last_status, last_used_at, updated_at
        )
        VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(consumer_key, usage_date, endpoint)
        DO UPDATE SET
            consumer_name = excluded.consumer_name,
            total_count = external_api_consumer_usage_daily.total_count + 1,
            success_count = external_api_consumer_usage_daily.success_count + excluded.success_count,
            error_count = external_api_consumer_usage_daily.error_count + excluded.error_count,
            last_status = excluded.last_status,
            last_used_at = excluded.last_used_at,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            consumer_key,
            str(consumer_name or "")[:120],
            usage_date,
            str(endpoint or "")[:200],
            success_inc,
            error_inc,
            str(status or "")[:40],
            last_used_at,
        ),
    )
    db.commit()


def get_external_api_usage_summary(consumer_keys: list[str]) -> dict[str, dict[str, Any]]:
    clean_keys = [str(item or "").strip() for item in consumer_keys if str(item or "").strip()]
    if not clean_keys:
        return {}

    db = get_db()
    usage_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    placeholders = ", ".join(["?"] * len(clean_keys))
    rows = db.execute(
        f"""
        SELECT consumer_key,
               SUM(total_count) AS total_count,
               SUM(success_count) AS success_count,
               SUM(error_count) AS error_count,
               MAX(last_used_at) AS last_used_at
        FROM external_api_consumer_usage_daily
        WHERE usage_date = ? AND consumer_key IN ({placeholders})
        GROUP BY consumer_key
        """,
        [usage_date] + clean_keys,
    ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        result[row["consumer_key"]] = {
            "today_total_count": int(row["total_count"] or 0),
            "today_success_count": int(row["success_count"] or 0),
            "today_error_count": int(row["error_count"] or 0),
            "today_last_used_at": row["last_used_at"] or "",
        }
    return result
