"""
邮箱通道缓存：记住每个邮箱可用的读取方式（graph / imap），避免重复尝试必然失败的通道。

- graph: 有 Mail.Read 权限，直接走 Graph API
- imap: 无 Mail.Read 权限或 Graph API 持续失败，跳过 Graph 直走 IMAP
- TTL 1 小时后过期重新探测
"""

from __future__ import annotations

import threading
import time
from typing import Optional

_channel_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 3600  # 1 hour


def get_cached_channel(email: str) -> Optional[str]:
    """获取缓存的可用通道，过期返回 None。"""
    with _cache_lock:
        entry = _channel_cache.get(email)
        if entry and entry["expires_at"] > time.time():
            return entry["method"]
        if entry:
            del _channel_cache[email]
        return None


def set_cached_channel(email: str, method: str) -> None:
    """缓存某邮箱的可用通道。"""
    with _cache_lock:
        _channel_cache[email] = {
            "method": method,
            "expires_at": time.time() + _CACHE_TTL,
        }


def invalidate_channel(email: str) -> None:
    """失效某邮箱的通道缓存。"""
    with _cache_lock:
        _channel_cache.pop(email, None)
