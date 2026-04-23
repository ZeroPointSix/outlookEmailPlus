from __future__ import annotations

from typing import Any

from outlook_web.errors import build_error_payload
from outlook_web.services.temp_mail_plugin_manager import (
    PluginManagerError,
    get_available_plugins,
    get_installed_plugins,
    get_plugin_config_schema,
    install_plugin,
    read_plugin_config,
    save_plugin_config,
    test_plugin_connection,
    uninstall_plugin,
)
from outlook_web.services.temp_mail_provider_factory import get_plugin_load_state


def _ok(data: Any | None = None, *, message: str = "success") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": True,
        "code": "OK",
        "message": message,
    }
    if data is not None:
        payload["data"] = data
    return payload


def _error(err: PluginManagerError) -> tuple[dict[str, Any], int]:
    payload = build_error_payload(
        err.code,
        err.message,
        status=err.status,
        details=err.data,
    )
    return {"success": False, "error": payload}, err.status


def api_get_plugins():
    installed = get_installed_plugins()
    available = get_available_plugins()
    load_state = get_plugin_load_state()
    installed_by_name = {str(item.get("name") or ""): item for item in installed if str(item.get("name") or "").strip()}
    available_by_name = {str(item.get("name") or ""): item for item in available if str(item.get("name") or "").strip()}
    all_names = sorted(set(available_by_name.keys()) | set(installed_by_name.keys()) | set(load_state.keys()))

    plugins: list[dict[str, Any]] = []
    for plugin_name in all_names:
        plugin = dict(available_by_name.get(plugin_name) or {})
        plugin.setdefault("name", plugin_name)
        plugin.setdefault("display_name", plugin_name)

        if plugin_name in load_state and load_state[plugin_name].get("status") == "failed":
            plugin["status"] = "load_failed"
            plugin["error"] = load_state[plugin_name].get("error")
        elif plugin_name in installed_by_name:
            plugin["status"] = "installed"
        else:
            plugin["status"] = "available"

        plugins.append(plugin)

    installed_count = sum(1 for plugin in plugins if plugin.get("status") == "installed")
    return _ok({"plugins": plugins, "installed_count": installed_count})


def api_install_plugin(body: dict[str, Any]):
    name = str((body or {}).get("name") or "").strip()
    url = str((body or {}).get("url") or "").strip() or None
    if not name:
        payload = build_error_payload("INVALID_PARAMS", "缺少插件名称", status=400)
        return {"success": False, "error": payload}, 400

    try:
        result = install_plugin(name, url=url)
        message = "插件安装成功，请点击「应用变更」使其生效"
        deps = result.get("dependencies") or []
        if isinstance(deps, list) and deps:
            message += f"。该插件需要额外依赖: {', '.join(str(item) for item in deps)}"
        return _ok(result, message=message)
    except PluginManagerError as err:
        return _error(err)


def api_uninstall_plugin(name: str, body: dict[str, Any]):
    clean_config = bool((body or {}).get("clean_config", False))
    try:
        result = uninstall_plugin(name, clean_config=clean_config)
        message = "插件已卸载"
        if result.get("had_active_emails"):
            message += "。关联邮箱记录已保留"
        if result.get("cleaned_keys"):
            message += "。已清理关联配置"
        return _ok(result, message=message)
    except PluginManagerError as err:
        return _error(err)


def api_get_plugin_config_schema(name: str):
    try:
        return _ok(get_plugin_config_schema(name))
    except PluginManagerError as err:
        return _error(err)


def api_get_plugin_config(name: str):
    try:
        return _ok(read_plugin_config(name))
    except PluginManagerError as err:
        return _error(err)


def api_save_plugin_config(name: str, body: dict[str, Any]):
    config = (body or {}).get("config", {})
    if not isinstance(config, dict):
        payload = build_error_payload("INVALID_PARAMS", "config 字段必须为对象", status=400)
        return {"success": False, "error": payload}, 400
    try:
        return _ok(save_plugin_config(name, config), message="配置已保存")
    except PluginManagerError as err:
        return _error(err)


def api_test_plugin_connection(name: str):
    result = test_plugin_connection(name)
    if result.get("success"):
        return _ok(result, message=str(result.get("message") or "连接成功"))

    payload = build_error_payload(
        "CONNECTION_FAILED",
        str(result.get("message") or "连接失败"),
        status=400,
        details=result,
    )
    return {"success": False, "error": payload}, 400
