from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from outlook_web.temp_mail_registry import _REGISTRY, get_registry_snapshot


def register_provider(cls: type["TempMailProviderBase"]) -> type["TempMailProviderBase"]:
    """类装饰器：将 Provider 注册到全局注册表。"""
    raw_name = getattr(cls, "provider_name", None)
    resolved_name = ""

    # 常规路径：显式声明 provider_name
    if isinstance(raw_name, str):
        resolved_name = raw_name.strip()
        # 显式给了空字符串，视为无效，不做回退
        if not resolved_name and "provider_name" in getattr(cls, "__dict__", {}):
            return cls
    elif raw_name is not None:
        # 非字符串显式值（如 int）直接忽略
        return cls

    # 兼容路径：未声明 provider_name 时，用类名自动派生
    if not resolved_name and "provider_name" not in getattr(cls, "__dict__", {}):
        class_name = getattr(cls, "__name__", "")
        if class_name:
            resolved_name = re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).lower().strip("_")

    if resolved_name:
        _REGISTRY[resolved_name] = cls
    return cls


def get_registry() -> dict[str, type["TempMailProviderBase"]]:
    """返回注册表快照（只读副本）。"""
    return get_registry_snapshot()


class TempMailProviderBase(ABC):
    provider_name: str = ""
    provider_label: str = ""
    provider_version: str = "0.0.0"
    provider_author: str = ""
    config_schema: dict[str, Any] = {}

    @abstractmethod
    def get_options(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def create_mailbox(self, *, prefix: str | None = None, domain: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def generate_mailbox(self, *, prefix: str | None = None, domain: str | None = None) -> dict[str, Any]:
        return self.create_mailbox(prefix=prefix, domain=domain)

    @abstractmethod
    def delete_mailbox(self, mailbox: dict[str, Any]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_messages(self, mailbox: dict[str, Any]) -> list[dict[str, Any]] | None:
        raise NotImplementedError

    @abstractmethod
    def get_message_detail(self, mailbox: dict[str, Any], message_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def delete_message(self, mailbox: dict[str, Any], message_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def clear_messages(self, mailbox: dict[str, Any]) -> bool:
        raise NotImplementedError


def _ensure_builtin_providers_loaded() -> None:
    """确保内置 Provider 在基类模块导入后完成注册。"""
    try:
        import outlook_web.services.temp_mail_provider_cf  # noqa: F401
        import outlook_web.services.temp_mail_provider_custom  # noqa: F401
    except Exception:
        # 基类模块不能因为内置 provider 导入失败而不可用
        return


_ensure_builtin_providers_loaded()
