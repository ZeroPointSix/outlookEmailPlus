__version__ = "2.3.0"

# Python 3.13 兼容：Path.glob 返回可迭代对象（如 map），
# 这里统一转为 list，保证与项目内既有用法（可拼接、可重复遍历）一致。
from pathlib import Path

_old_path_glob = getattr(Path, "glob", None)
if callable(_old_path_glob):
    try:
        _probe = Path(".").glob("*")
        if not isinstance(_probe, list):

            def _glob_list(self: Path, pattern: str):  # type: ignore[override]
                return list(_old_path_glob(self, pattern))

            Path.glob = _glob_list  # type: ignore[assignment]
    except Exception:
        pass

from outlook_web.app import create_app

__all__ = ["create_app", "__version__"]
