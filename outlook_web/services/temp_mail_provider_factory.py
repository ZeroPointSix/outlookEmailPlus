from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from outlook_web.repositories import settings as settings_repo
from outlook_web.services.temp_mail_provider_base import TempMailProviderBase

logger = logging.getLogger(__name__)

# 失败插件节流：同一文件未变更时跳过重复加载，避免日志噪音
_FAILED_PLUGIN_MTIMES: dict[str, int] = {}
_PLUGIN_LOAD_STATE: dict[str, dict[str, Any]] = {}

# 热刷新保护：内置 provider 不清空
_BUILTIN_PROVIDERS = {
    settings_repo.CLOUDFLARE_TEMP_MAIL_PROVIDER,
    settings_repo.DEFAULT_TEMP_MAIL_PROVIDER,
    settings_repo.LEGACY_TEMP_MAIL_PROVIDER,
}

# 触发内置 provider 装饰器注册
import outlook_web.services.temp_mail_provider_cf  # noqa: F401,E402
import outlook_web.services.temp_mail_provider_custom  # noqa: F401,E402


class TempMailProviderFactoryError(Exception):
    def __init__(self, code: str, message: str, *, status: int = 503, data: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.data = data


def _get_plugin_dir() -> Path:
    """获取插件目录（默认以 DATABASE_PATH 同级目录为根）。"""
    from outlook_web import config

    db_path = Path(config.get_database_path()).resolve()
    return db_path.parent / "plugins" / "temp_mail_providers"


def _get_registry() -> dict[str, type[TempMailProviderBase]]:
    from outlook_web.temp_mail_registry import _REGISTRY

    return _REGISTRY


def get_plugin_load_state() -> dict[str, dict[str, Any]]:
    return {name: dict(item) for name, item in _PLUGIN_LOAD_STATE.items()}


def load_plugins() -> list[dict[str, Any]]:
    """扫描并加载插件目录中的 provider 文件。"""
    plugin_dir = _get_plugin_dir()
    if not plugin_dir.is_dir():
        _PLUGIN_LOAD_STATE.clear()
        return []

    discovered_names = {py_file.stem for py_file in plugin_dir.glob("*.py") if not py_file.name.startswith("_")}
    for cached_name in list(_PLUGIN_LOAD_STATE.keys()):
        if cached_name not in discovered_names:
            _PLUGIN_LOAD_STATE.pop(cached_name, None)

    results: list[dict[str, Any]] = []
    for py_file in sorted(plugin_dir.glob("*.py"), key=lambda p: p.name):
        if py_file.name.startswith("_"):
            continue

        name = py_file.stem
        module_name = f"_plugin_{name}"
        file_key = str(py_file)
        try:
            mtime_ns = py_file.stat().st_mtime_ns
        except OSError:
            continue

        # 文件未变化且上次失败：跳过重复尝试（测试/生产都可降低噪音）
        if _FAILED_PLUGIN_MTIMES.get(file_key) == mtime_ns:
            cached = _PLUGIN_LOAD_STATE.get(name)
            if cached is not None and cached.get("status") == "failed":
                results.append(dict(cached))
            continue

        try:
            importlib.invalidate_caches()

            # 强制删除对应 pyc，避免同秒覆盖导致旧字节码复用
            try:
                cache_path = Path(importlib.util.cache_from_source(str(py_file)))
                cache_path.unlink(missing_ok=True)
            except Exception:
                pass

            # 同名模块热替换前先移除缓存
            sys.modules.pop(module_name, None)

            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                failure = {"name": name, "status": "failed", "error": "ImportError: 无法创建模块规格"}
                results.append(failure)
                _PLUGIN_LOAD_STATE[name] = dict(failure)
                _FAILED_PLUGIN_MTIMES[file_key] = mtime_ns
                continue

            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
            loaded = {"name": name, "status": "loaded"}
            results.append(loaded)
            _PLUGIN_LOAD_STATE[name] = dict(loaded)
            _FAILED_PLUGIN_MTIMES.pop(file_key, None)
        except Exception as exc:
            # 失败项 error 需要可检索到异常类型（如 SyntaxError / ModuleNotFoundError）
            failure = {"name": name, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            results.append(failure)
            _PLUGIN_LOAD_STATE[name] = dict(failure)
            _FAILED_PLUGIN_MTIMES[file_key] = mtime_ns
            logger.error("[plugin] 加载失败 %s: %s", name, exc)

    return results


def reload_plugins() -> dict[str, Any]:
    """热刷新插件：清空第三方注册 + 清理模块缓存 + 重新扫描加载。"""
    registry = _get_registry()

    # 1) 清空非内置 provider
    for name in list(registry.keys()):
        if name not in _BUILTIN_PROVIDERS:
            registry.pop(name, None)

    # 2) 清理 sys.modules 中插件模块
    for key in list(sys.modules.keys()):
        if key.startswith("_plugin_"):
            sys.modules.pop(key, None)

    # 3) 重新加载
    results = load_plugins()
    loaded = [item["name"] for item in results if item.get("status") == "loaded"]
    failed = [item for item in results if item.get("status") == "failed"]

    return {
        "loaded": loaded,
        "failed": failed,
        "total_available": len(registry),
    }


def get_temp_mail_provider(provider_name: str | None = None) -> TempMailProviderBase:
    registry = _get_registry()
    resolved_provider_name = settings_repo.get_temp_mail_runtime_provider_name(provider_name)
    if not resolved_provider_name:
        raise TempMailProviderFactoryError(
            "TEMP_MAIL_PROVIDER_NOT_CONFIGURED",
            "未配置临时邮箱 Provider",
        )

    provider_cls = registry.get(resolved_provider_name)
    if provider_cls is not None:
        return provider_cls(provider_name=resolved_provider_name)

    raise TempMailProviderFactoryError(
        "TEMP_MAIL_PROVIDER_INVALID",
        f"未知的临时邮箱 Provider: {resolved_provider_name}",
        data={"provider_name": resolved_provider_name},
    )


def get_available_providers() -> list[dict[str, Any]]:
    """返回已注册 provider 列表（含元信息）。"""
    registry = _get_registry()
    providers: list[dict[str, Any]] = []
    for name, cls in sorted(registry.items(), key=lambda item: item[0]):
        providers.append(
            {
                "name": name,
                "label": getattr(cls, "provider_label", "") or name,
                "version": getattr(cls, "provider_version", "0.0.0"),
                "author": getattr(cls, "provider_author", ""),
            }
        )
    return providers
