"""
邮件列表缓存：避免 2h 内重复拉取同一邮箱的同一文件夹。

- key: (email, folder)
- value: {emails, method, has_more, cached_at}
- TTL: 2 小时
- 线程安全
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

_email_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 7200  # 2 hours


def _make_key(email: str, folder: str) -> str:
    return f"{email}|{folder}"


def get_cached_emails(email: str, folder: str) -> Optional[Dict[str, Any]]:
    """命中缓存返回 {emails, method, has_more}，未命中或过期返回 None。"""
    key = _make_key(email, folder)
    with _cache_lock:
        entry = _email_cache.get(key)
        if entry and entry["expires_at"] > time.time():
            return {
                "emails": entry["emails"],
                "method": entry["method"],
                "has_more": entry["has_more"],
            }
        if entry:
            del _email_cache[key]
        return None


def set_cached_emails(
    email: str,
    folder: str,
    emails: List[Dict],
    method: str,
    has_more: bool = False,
) -> None:
    """写入缓存。"""
    key = _make_key(email, folder)
    with _cache_lock:
        _email_cache[key] = {
            "emails": emails,
            "method": method,
            "has_more": has_more,
            "expires_at": time.time() + _CACHE_TTL,
        }


def invalidate_email_cache(email: str, folder: Optional[str] = None) -> None:
    """失效缓存。folder=None 时清除该邮箱所有文件夹。"""
    with _cache_lock:
        if folder:
            _email_cache.pop(_make_key(email, folder), None)
        else:
            keys_to_remove = [k for k in _email_cache if k.startswith(f"{email}|")]
            for k in keys_to_remove:
                del _email_cache[k]
