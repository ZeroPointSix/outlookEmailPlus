from __future__ import annotations

import os
from typing import Optional

_APP_INSTANCE = None


def create_app(*, autostart_scheduler: Optional[bool] = None):
    """
    应用工厂（迁移期实现）：
    - 统一装配入口，便于测试与后续 Blueprint/分层拆分
    - 控制 import-time 副作用：初始化/调度器启动放到 create_app 中受控执行
    - routes 采用 Blueprint 模块化注册（URL 不变）
    """
    global _APP_INSTANCE

    if _APP_INSTANCE is None:
        from pathlib import Path

        from flask import Flask
        from werkzeug.exceptions import HTTPException
        from werkzeug.middleware.proxy_fix import ProxyFix

        from outlook_web import config
        from outlook_web import config as app_config
        from outlook_web.db import init_db, register_db
        from outlook_web.middleware import (
            attach_trace_id_and_normalize_errors,
            ensure_trace_id,
            handle_exception,
            handle_http_exception,
        )
        from outlook_web.routes import (
            accounts,
            audit,
            emails,
            external_pool,
            external_temp_emails,
            groups,
            pages,
            scheduler,
            settings,
            system,
            tags,
            temp_emails,
        )
        from outlook_web.security.csrf import init_csrf

        # 初始化（DB/目录等）
        repo_root = Path(__file__).resolve().parents[1]
        templates_dir = repo_root / "templates"
        static_dir = repo_root / "static"

        # 确保目录存在
        templates_dir.mkdir(parents=True, exist_ok=True)
        static_dir.mkdir(parents=True, exist_ok=True)

        # 确保数据目录存在
        data_dir = config.get_database_path()
        if data_dir:
            import os

            os.makedirs(
                os.path.dirname(data_dir) if os.path.dirname(data_dir) else ".",
                exist_ok=True,
            )

        # 初始化数据库
        init_db()

        app = Flask(
            __name__,
            template_folder=str(templates_dir),
            static_folder=str(static_dir),
            static_url_path="/static",
        )

        # 注入版本号到所有模板（用于 UI 显示）
        from outlook_web import __version__ as APP_VERSION

        @app.context_processor
        def inject_app_version():
            return {
                "APP_VERSION": APP_VERSION,
                "OAUTH_TOOL_ENABLED": app_config.get_oauth_tool_enabled(),
            }

        app.secret_key = config.require_secret_key()
        app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 7  # 7 天
        app.config["SESSION_COOKIE_HTTPONLY"] = True
        app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

        # ProxyFix 中间件（仅在配置启用时应用）
        # 注意：启用前必须配置 TRUSTED_PROXIES 环境变量
        if config.get_proxy_fix_enabled():
            app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

        # DB teardown（请求结束释放连接）
        register_db(app)

        # 配置日志（确保 outlook_web 命名空间的日志输出到 stderr）
        import logging
        import sys

        _log_handler = logging.StreamHandler(sys.stderr)
        _log_handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s", datefmt="%H:%M:%S"))
        _ow_logger = logging.getLogger("outlook_web")
        if not _ow_logger.handlers:
            _ow_logger.addHandler(_log_handler)
            # PERF_LOGGING=true 时输出 DEBUG 级别性能日志；默认 INFO（生产模式不输出）
            _perf_logging = os.getenv("PERF_LOGGING", "").strip().lower() == "true"
            _ow_logger.setLevel(logging.DEBUG if _perf_logging else logging.INFO)

        # CSRF（可选）
        _csrf, csrf_exempt, _generate_csrf = init_csrf(app)

        # trace_id + error 结构标准化（迁移到 middleware 模块）
        app.before_request(ensure_trace_id)
        app.after_request(attach_trace_id_and_normalize_errors)
        app.register_error_handler(HTTPException, handle_http_exception)
        app.register_error_handler(Exception, handle_exception)

        # 静态文件缓存控制（防止浏览器缓存旧版本 JS/CSS）
        @app.after_request
        def set_static_cache_control(response):
            """
            为静态文件设置合理的缓存策略：
            - 带版本号参数的静态文件可以长期缓存（1年）
            - 没有版本号的静态文件使用短期缓存（1小时）+ must-revalidate
            """
            from flask import request

            if request.path.startswith("/static/"):
                # 检查是否带版本号参数（?v=x.x.x）
                has_version_param = "v=" in (request.query_string or b"").decode("utf-8", errors="ignore")
                if has_version_param:
                    # 带版本号：可以长期缓存（immutable）
                    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
                else:
                    # 不带版本号：短期缓存 + 必须重新验证
                    response.headers["Cache-Control"] = "public, max-age=3600, must-revalidate"
            return response

        # Blueprint 路由注册（URL 不变）
        app.register_blueprint(pages.create_blueprint(csrf_exempt=csrf_exempt))
        app.register_blueprint(groups.create_blueprint())
        app.register_blueprint(tags.create_blueprint())
        app.register_blueprint(accounts.create_blueprint())
        app.register_blueprint(emails.create_blueprint())
        app.register_blueprint(temp_emails.create_blueprint(csrf_exempt=csrf_exempt))
        app.register_blueprint(settings.create_blueprint())
        app.register_blueprint(scheduler.create_blueprint())
        app.register_blueprint(system.create_blueprint())
        app.register_blueprint(audit.create_blueprint())
        app.register_blueprint(external_pool.create_blueprint(csrf_exempt=csrf_exempt))
        app.register_blueprint(external_temp_emails.create_blueprint(csrf_exempt=csrf_exempt))
        if app_config.get_oauth_tool_enabled():
            from outlook_web.routes import token_tool

            app.register_blueprint(token_tool.create_blueprint())

        # 浏览器扩展 CORS 支持（仅对 /api/external/* 路径）
        # chrome-extension:// 前缀不可被普通网页伪造，允许此来源不扩大安全边界
        import re as _re

        from flask_cors import CORS as _CORS

        _CORS(
            app,
            resources={
                r"/api/external/*": {
                    "origins": [_re.compile(r"^chrome-extension://.*$")],
                    "methods": ["GET", "POST", "OPTIONS"],
                    "allow_headers": ["Content-Type", "X-API-Key"],
                    "supports_credentials": False,
                }
            },
        )

        # 打印初始化信息
        print("=" * 60)
        print("Outlook 邮件 Web 应用已初始化")
        print(f"数据库文件: {config.get_database_path()}")
        print(f"Temp Mail API: {config.get_temp_mail_base_url()}")
        print("=" * 60)

        _APP_INSTANCE = app

    # 调度器启动控制
    if autostart_scheduler is None:
        from outlook_web.services import graph as graph_service
        from outlook_web.services import scheduler as scheduler_service

        if scheduler_service.should_autostart_scheduler():
            scheduler_service.init_scheduler(_APP_INSTANCE, graph_service.test_refresh_token_with_rotation)
    elif autostart_scheduler:
        from outlook_web.services import graph as graph_service
        from outlook_web.services import scheduler as scheduler_service

        scheduler_service.init_scheduler(_APP_INSTANCE, graph_service.test_refresh_token_with_rotation)

    return _APP_INSTANCE
