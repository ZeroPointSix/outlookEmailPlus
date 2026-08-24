# Changelog

All notable changes to OutlookMail Plus are documented in this file.

## [v2.9.11] - 2026-08-24

### 修复 / Bug Fixes

- **ZER-575 Provider 插件边界收敛**：邮箱池从运行时注册表识别第三方 Provider，并统一支持按 Provider 领取、动态创建、持久化和写库失败回滚。
- **统一临时邮箱生命周期**：所有 Provider 均使用标准 `temp_mail` 状态机；插件不再引入专用数据库字段、关联表或成功后复用分支。

## [v2.9.10] - 2026-08-17

### 优化 / Improvements

- **ZER-657 新前端临时邮箱设置迁移补齐**：临时邮箱页的设置入口直达独立设置页签；恢复 Provider、API、域名、默认域名、前缀规则和 Cloudflare Worker 配置，并补充 JSON 结构校验、脱敏密钥保护与域名对象展示兼容。
- **ZER-582 纯白前端服务展示优化**：保持现有纯白主题、导航与全局色板不变；API Key 改为名称 / 状态 / 脱敏 Token / 操作的简洁列表，权限和邮箱范围固定在创建时选择并通过详情查看；Webhook 测试展示已保存配置的真实投递 URL、上游 HTTP 状态、耗时和尝试次数，Token 留空表示清空；AI 测试区分连通性与契约状态，并在请求失败时保留端点、模型和 HTTP 诊断。
- **版本号更新为 2.9.10**。
- **双镜像发布**：仓库提供两套 Dockerfile —— `Dockerfile`（默认，新前端 Ant Design Pro SPA）与 `Dockerfile.legacy`（旧前端）。Tag 发布时 CI 同时构建并推送两个镜像：`outlook-email-plus:v2.9.10`（SPA）与 `outlook-email-plus-legacy:v2.9.10-legacy`，部署时按前端模式选择镜像。

### 集成 / Integration

- **#109 新前端主线回收**：将 polish 分支与功能 PR（#130/#131/#132/#133/#134/#137）统一回收到 `feat/ant-design-pro-frontend-migration`（PR #109）。Railway 测试环境源分支改绑本分支。
- **/healthz 构建标识**：返回 `git_sha` / `git_branch` / `build_time`，便于确认 Railway 实际运行提交。

### 新增功能 / New Features

- **ZER-381 新前端自动轮询对齐旧前端**：开启「自动轮询」设置后，标准模式选中账号即自动开始监听新邮件（对齐旧前端 `accounts.js` 选中即监听）；复制邮箱地址成功后立即开始监听该账号（对齐旧前端 `email-copied` 事件），覆盖注册收验证码主流程，不再只能手动拉取。
- **ZER-381 顶栏 GitHub 链接**：头部操作区新增 GitHub 仓库入口（对齐旧前端抬头 `btn-github`），仓库地址逻辑抽取为 `utils/repoUrl.ts` 供顶栏与页脚复用。
- **

### 修复 / Bug Fixes

- **ZER-381 监听完成后状态丢失**：轮询引擎停止/发现后不再删除条目，改为保留最终快照（`active=false`），「检测到验证码」「监听超时」等结果持续展示在账号卡片与简洁表格中。
- **ZER-381 验证码提取后摘要不更新**：监听发现新邮件/验证码后自动刷新账号摘要与当前邮件列表；手动提取验证码成功后同步刷新，最新邮件摘要与摘要验证码即时更新。
- **ZER-381 页面整页滚动与底部空白**：改为固定视口布局（对齐旧前端 `body{overflow:hidden}`），页面本身不再滚动，仅内容区内部滚动，顶栏与侧边栏保持固定。
- **ZER-381 账号管理删除项字体不一致**：antd 主题 `fontFamily` 与全局 body 字体栈统一为同一 AlibabaSans 回退链，消除 AlibabaSans 加载失败时组件回退到不同默认字体造成的同页字体不一致。
- **ZER-381 部署环境 logo/favicon 404**：Docker 镜像按 `.dockerignore` 排除了仓库 `img/` 目录，而 Flask `/img/<path>` 与 `/favicon.ico` 路由只从该目录取文件，导致新前端 logo、头像与 favicon 在部署环境全部 404。现在仓库文件缺失时回退到 SPA 构建产物（`ant-design-pro/public/img/`），两种运行环境均可加载。
- **ZER-381 邮箱页账号栏信息不全且无法复制**：账号从截断的 Menu 项改为对齐旧前端的账号卡片——完整邮箱地址（截断改为完整展示，点击文本或复制图标即复制）、provider/状态/标签、备注、最近刷新时间，并恢复每账号快捷操作（验证码 / 复制 / 监听）。
- **ZER-381 简洁模式竖排错乱**：简洁模式账号列表从竖排 List 改为横向长条表格（选择 / 邮箱(点击复制) / 验证码 / 最新邮件 / 分组标签 / 操作），对齐旧前端 `mail-row` 六列栅格；验证码按钮优先复用账号摘要码，无摘要码时兜底实时提取。
- **ZER-381 邮件详情验证码区布局**：工具栏顺序对齐旧前端（提取并复制验证码主按钮 → 再次复制 → 信任原始 HTML），不再把信任开关放在最前。

## [v2.9.7] - 2026-08-09

### 修复 / Bug Fixes

- **

## [v2.9.6] - 2026-08-08

### 优化 / Improvements

- **

## [v2.9.5] - 2026-08-05

### 修复 / Bug Fixes

- **ZER-381 无代理场景错误误分类**：仅在分组明确配置 `proxy_url` 时，才将 Graph 的 `ProxyError`/`ConnectionError` 判定为 `EMAIL_PROXY_CONNECTION_FAILED` / `PROXY_ERROR` 并跳过 IMAP 回退；无代理时继续 Graph → IMAP 回退。覆盖 `/api/emails`、external messages 与删除邮件回退路径。
- **主题抽屉开关语义**：修正 Ant Design Pro `SettingDrawer` 的 `collapse` 开合状态接线。

## [v2.8.0] - 2026-07-26

旧前端紧急版本（Issue #115）。在 SPA 新前端迁移（#109）之前，先发布一个范围受控、可回滚的稳定旧前端版本，合入近期关键缺陷修复与验证码能力增强。

### 新增功能 / New Features

- **ZER-90 统一验证码提取模块（#119）**：将规则提取、选项化提取、置信度门控与对外 API 契约收口到统一模块；前端 `extract-verification` 与观测链路共用同一套提取路径，减少“页面可用但 API 行为不一致”的漂移。
- **临时邮箱接入邮箱池（#85）**：Cloudflare 等临时邮箱可被 `claim-random` 领取并纳入邮箱池调度，扩展自动化注册场景的邮箱来源。
- **Gunicorn 并发启动配置（#84）**：修正多 worker/线程场景下的启动与调度行为，降低高并发下整站被同步长任务拖死的概率。

### 修复 / Bug Fixes

- **IMAP 验证码详情错配（#67）**：修复提取结果与邮件详情展示不一致的问题，避免用户看到 A 邮件内容却拿到 B 邮件验证码。
- **验证码大小写被篡改（#103）**：规则分支与 AI 回退路径不再强制 `.upper()`，`verification_code` / `formatted` 保持邮件原文大小写（如 `ab12cd` 不再变成 `AB12CD`）。
- **OAuth Token scope 校验（#108 / #107）**：修复 Token 工具写入账号时使用默认 scope 校验导致 `AADSTS70000` 的问题；授权与验证阶段 scope 保持一致。
- **x.ai 连字符验证码识别（#114 / ZER-57）**：支持 `84A-KMN`、`NJF-KUU` 等带连字符验证码；修复 HTML 粘连（如 `84A-KMNIf`）与 CSS 色值 `#333333` 误识别为验证码的问题。
- **跨文件夹选取最新验证邮件**：在多个文件夹存在验证邮件时，优先选择时间上最新的一封，降低“拿到旧验证码”的概率。
- **验证码回退链路收敛**：减少不必要的 fallback 调用，并修复 stale-code fallback 可能返回过期验证码的问题。
- **Watchtower 镜像版本固定（#65）**：`docker-compose.yml` 固定 `containrrr/watchtower:1.7.1`，避免旧版内嵌 Docker API 1.25 连接新版 Engine（要求 API 1.44+）失败；README 补充故障排查说明。

### 重要变更 / Important Changes

- **发版边界**：本版本为旧前端紧急线（#115），**不包含** SPA 新前端迁移（#109/#110/#111/#112）；性能大改（#36）与 domain claim（#105）继续延期。
- **版本号**：`outlook_web.__version__`、健康检查 `/healthz`、系统设置与对外 API 返回的 `version` 字段统一升级为 `2.8.0`。
- **发布门禁**：打 `v2.8.0` tag 时 CI 强制校验 `__version__` 与 `CHANGELOG.md` 段落一致（`scripts/check_release_version.py`）。

### 测试/验证 / Testing & Verification

- 全量回归：`python -m unittest discover -s tests -v` → **1592 passed**，skipped 9（约 146s）。
- 发版聚焦套件：验证码提取 / OAuth / 冒烟契约等 **173 passed**。
- 代码质量：`black --check`、`isort --check-only`、`flake8 --select=E9,F63,F7,F82`、`compileall` 全部通过。
- 本地服务冒烟：`/healthz`、`/login`、登录后首页与静态资源、`/api/bootstrap`、`/api/settings`、`/api/accounts`、`/api/overview/summary` 均 200；x.ai 连字符样本（`84A-KMN`、粘连 `84A-KMNIf`）提取通过。
- 合并后 CI：`Code Quality`、`Python Tests`、`Build and Push Docker Image` 在 `main@ee8d769` 均已通过。

## [v2.7.0] - 2026-05-29

### 新增功能 / New Features

- **Issue #69 性能优化 — Phase 1 首屏降载**：
  - 新增 `/api/bootstrap` 轻量端点，替代首页阶段对 `/api/settings` 的重复重查询
  - `checkVersionUpdate()` 延迟 5 秒执行，避免首屏阶段外网请求抢占 sync worker
  - `load_groups_with_account_count()` 聚合查询，替代 N+1 循环查询
- **Issue #69 性能优化 — Phase 2 接口缓存与查询收敛**：
  - `api_get_overview_summary()` 新增 30 秒 TTL 进程级缓存
  - `api_version_check()` 支持 `enable_version_check` 设置开关

### 修复 / Bug Fixes

- **Issue #70 Figma 邮件展示修复**：修复 Figma 验证邮件在前端的展示问题。
- **Issue #71 版本号与发版一致性**：`outlook_web.__version__` 与 Git tag / GitHub Release 对齐为 `2.7.0`；CI tag 构建新增 `scripts/check_release_version.py` 门禁（校验 `__version__` + `CHANGELOG.md`）。

### 重要变更 / Important Changes

- 版本号从 `2.6.0` 升级至 `2.7.0`（`outlook_web.__version__`）。
- Docker 发版：`docker-build-push.yml` 在 push `v*.*.*` tag 时强制版本与 CHANGELOG 一致。

## [v2.6.0] - 2026-05-19

### 新增功能 / New Features

- **Issue #60 号池管理 UI 与状态维护 MVP**：
  - 新增 `GET /api/pool-admin/accounts`（池内/池外/分组/状态/provider/搜索筛选 + 分页）
  - 新增 `POST /api/pool-admin/accounts/<id>/action`（移入/移出号池、冻结/恢复/退休/强制释放）
  - claimed 状态保护：占用中的账号仅允许 `force_release`
  - 前端号池管理页：筛选、分页、批量操作、行内动作

### 修复 / Bug Fixes

- **号池管理 i18n**：补全英文模式翻译（29 条精确词条 + 6 条 regex 规则）。

### 重要变更 / Important Changes

- 版本号从 `2.5.0` 升级至 `2.6.0`。
- 新增 Pool Admin 四层模块（routes/controllers/services/repositories）。

## [v2.5.0] - 2026-05-07

### 新增功能 / New Features

- **Issue #58 Cloudflare Temp Mail 导入功能**：临时邮箱页面新增「导入」按钮（模态框交互），支持批量粘贴 `邮箱地址----JWT` 格式导入已有 CF Worker 邮箱。后端新增 `POST /api/temp-emails/import` API，支持 JWT 直传落库和指定 provider_name，取件时通过 `meta_json.provider_name` 自动区分 CF/GPTMail provider。

### 修复 / Bug Fixes

- **Issue #57 批量刷新卡 12/50**：`outlook_web/services/graph.py` 刷新链路增加指数退避 + 抖动 + 超时组合策略，避免大批量刷新时因个别账号超时导致整体卡住。
- CI 环境自动跳过 `test_pool_cf_real_e2e` 外部 E2E 测试（`@unittest.skipIf(os.environ.get("CI") == "true")`），解除 Docker 构建阻塞。

### 重要变更 / Important Changes

- 版本号从 `2.4.0` 升级至 `2.5.0`。
- `temp_mail_service.py` 新增 `import_user_mailbox_with_jwt()` 方法，支持 JWT 直传导入。
- `import_user_mailbox()` 新增 `provider_name` 参数，不再依赖全局 provider 设置。

### 测试/验证 / Testing & Verification

- 全量回归：`Ran 1410 tests in 326.482s`，`FAILED (failures=4, skipped=7)`。唯一失败为 `test_pool_cf_real_e2e.py`（CF Worker 上游异常），与本次变更无关。
- 临时邮箱专项测试：34 tests 全通过。
- 本地服务人工验收通过（模态框 + 导入按钮 + provider 切换）。

## [v2.4.0] - 2026-05-02

### 新增功能 / New Features

- **Issue #55 批量拉取与验收修复**：后端 Controller/Repository 扩展批量拉取能力；前端 groups.js / main.js 新增批量操作 UI 与交互。新增 `test_batch_fetch_email_api_contract.py`、`test_batch_fetch_frontend_contract.py` 及 Jest 前端测试。
- **Issue #56 账号列表分页**：`GET /api/accounts` 升级为服务端分页（`page` / `page_size` / `search` / `tag_ids` / `sort_by` / `sort_order`），Repository 层新增 `get_accounts_page()`，避免万级账号全量加载崩溃。新增 `test_issue56_accounts_pagination.py` 专项测试。

### 修复 / Bug Fixes

- 浏览器扩展 `popup.html` / `popup.js` 体验微调。
- `mailbox_compact.js` 紧凑模式体验优化；`i18n.js` 补充缺失词条。

### 重要变更 / Important Changes

- 版本号从 `2.3.0` 升级至 `2.4.0`。
- 发布链路继续沿用 Python + Docker（Docker tar + 源码 zip）。

### 测试/验证 / Testing & Verification

- 全量回归：`Ran 1410 tests in 476.370s`，`FAILED (failures=4, skipped=7)`。唯一失败为 `test_pool_cf_real_e2e.py`（CF Worker 上游异常），与本次变更无关。
- 布局系统 Jest 测试：15 suites / 138 tests 全通过。

## [v2.3.0] - 2026-04-23

### 新增功能 / New Features

- **Issue #49 失效账号检测与治理闭环**：
  - 后端：刷新链路新增 `_classify_refresh_failure()` 统一判定 `invalid_grant / AADSTS70000` 错误；全量/定时/选中/重试四条刷新链路均扩展返回 `invalid_token_failed_count` 和 `invalid_token_failed_list`。
  - 新增独立治理接口：`GET /api/accounts/invalid-token-candidates` 查询失效候选，`POST /api/accounts/batch-update-status` 批量更新状态（默认 `inactive`），含去重、存在性校验与审计日志。
  - 前端：刷新模态框新增"失效 Token 治理面板"，支持检测摘要展示、候选列表、一键批量置 inactive、二次确认批量删除；"🔍 失效治理"手动入口按钮。
  - 测试：新增 `tests/test_invalid_token_governance.py`（12 个用例），覆盖判定 helper、候选接口、批量状态接口、端到端闭环。
- **浏览器扩展档案字段只读化 + 点击复制反馈**：Profile 生成器字段改为 `readonly`，点击后触发顶部消息栏"已复制"提示，避免误编辑；新增字段级复制 helper 与集成测试。

### 修复 / Bug Fixes

- **Issue #52 前端邮件列表排序与滚动位置**：`renderEmailList()` 新增 `scrollToTop` 参数（默认 `true`），在切换账号、切换文件夹、首次加载时自动回到列表顶部；补全所有缓存命中路径的 `sortEmailsByNewestFirst` 排序兜底；新增 `tests/test_v190_frontend_contract.py` 前端排序契约测试。
- **浏览器扩展 UX 修复**：消息栏从 `display:none/block` 改为 `opacity` 过渡，彻底消除点击复制时的页面跳动；移除字段点击后的绿色背景/边框/文字色反馈，仅保留顶部消息栏提示。

### 重要变更 / Important Changes

- `dev` 分支（含 PR #48 + Issue #49 + UX 修复）已合并到 `main`。
- 版本号从 `2.2.2` 升级至 `2.3.0`。

## [v2.2.2] - 2026-04-22

### 修复 / Bug Fixes

- **CI 质量门禁彻底修复**：
  - `isort` 排序失败：修复 `tests/test_settings_dynamic_provider_names.py` 内部 import 顺序，通过 `isort --check-only`。
  - `coverage` 报告失败：在 `pyproject.toml` 中配置 `[tool.coverage.run]`，omit 测试期间动态创建的临时插件文件（`*/outlookEmail-tests-*/plugins/temp_mail_providers/*.py`），解决 `No source for code` 错误。
  - 插件测试文件泄漏：将 `test_temp_mail_plugin_manager.py` 与 `test_temp_mail_plugin_api.py` 的 `tearDown` 中文件清理模式从 `mock_*.py` 放宽为 `*.py`，防止 `custom_one.py` 等临时文件残留。

### 重要变更 / Important Changes

- **版本升级**：`outlook_web.__version__` 从 `2.2.1` 升级为 `2.2.2`。

## [v2.2.1] - 2026-04-22

### 修复 / Bug Fixes

- **CI 测试环境兼容性修复**：将 `tests/test_settings_dynamic_provider_names.py` 从 pytest 语法迁移至标准库 `unittest`，消除 CI 环境中因缺少 `pytest` 导致的 `ModuleNotFoundError`，修复 `Python Tests` 与 `Build and Push Docker Image` 质量门禁失败。

### 重要变更 / Important Changes

- **版本升级**：`outlook_web.__version__` 从 `2.2.0` 升级为 `2.2.1`。

## [v2.2.0] - 2026-04-22

### 新增功能 / New Features

- **临时邮箱 Provider 插件化架构**：全新插件系统支持第三方临时邮箱 Provider 动态安装、卸载、配置与热加载。
  - 核心模块：`temp_mail_registry`（全局注册表）、`temp_mail_plugin_manager`（生命周期管理）、`temp_mail_plugin_cli`（CLI 工具）、`plugins/registry.json`（源索引）。
  - 内置 Provider：Cloudflare Workers（多域 + Admin Key 加密）、Custom API、GPTMail、Moemail。
  - Web 管理 API：`/api/plugins`（列表/安装/卸载/配置/连接测试）。
  - 设置页新增插件管理卡片，支持自定义安装模态框与 Provider 注入逻辑。
  - Provider 设置与域名选择解耦：设置页不再硬编码 Provider 名称，改为动态从注册表获取。
- **浏览器扩展 v0.3.0 增强**：
  - 新增本地个人信息生成器（`profile-generator.js` + `profile-data-us.js`），支持一键生成姓名/地址/电话等注册所需字段。
  - 新增完整 Jest 测试覆盖（popup、storage、profile-generator 的单元与集成测试）。
- **登录鉴权增强**：`login_required` 装饰器现同时支持 `session["logged_in"]` 与 `session["user_id"]`，提升多场景兼容性与安全性。

### 修复 / Bug Fixes

- **发布质量门禁修复**：对新增插件化模块及既有文件执行 `black` / `isort` 对齐，修复 `Code Quality` / `Build and Push Docker Image` 链路被质量门禁阻断的问题；本地复测确认 `Code Quality` 等效命令已全部通过。
- **版本测试动态化**：`tests/test_version_update.py` 改为跟随 `outlook_web.__version__` 动态断言，避免仅因版本号 bump 导致全量回归误报。

### 重要变更 / Important Changes

- **版本升级**：`outlook_web.__version__` 从 `2.1.0` 升级为 `2.2.0`。
- **扩展版本同步**：`browser-extension/manifest.json` 从 `0.2.0` 升级为 `0.3.0`，与扩展新增能力一并发布。
- **发布口径保持不变**：当前仓库继续采用 **Python + Docker** 发布链路，正式产物以 Docker 镜像 tar 与源码 zip 为主，不引入 Tauri / Cargo / MSI / NSIS 构建链路。

### 测试/验证 / Testing & Verification

- 全量回归：
  - `python -m unittest discover -s tests -v`（CI 等效）
  - 结果：`1,369 passed, 9 skipped, 0 failed`
  - 状态：全绿 ✅
- 构建验证：
  - `docker build -t outlook-email-plus:v2.2.0 .` → 待执行
  - 产物：
    - `dist/outlook-email-plus-v2.2.0-docker.tar`
    - `dist/outlookEmailPlus-v2.2.0-src.zip`
    - `dist/browser-extension-v0.3.0.zip`

## [v2.1.0] - 2026-04-20

### 新增功能 / New Features

- **数据概览大盘正式上线**：新增 5 Tab 统一运营看板，覆盖总览、验证码提取、对外 API、邮箱池、系统活动，并用纯 CSS 图表/进度块/时间线替换旧 dashboard。
- **验证码提取日志统一观测**：新增 `verification_extract_logs` 表与共享写库 helper，普通账号、临时邮箱、external API、邮箱池相关提取链路统一落日志，支持时延、通道、AI fallback、错误码等维度分析。
- **Overview 前端实时联动与多语言补齐**：提取成功后会主动失效 overview 缓存并重拉相关 Tab；overview 页头、Tab、KPI、表头、hover note、timeline/channel/status 等可见文案已全部纳入 i18n。

### 修复 / Bug Fixes

- **浏览器扩展“API 无效”修复**：主应用设置页复制 External API Key 时，已从“复制脱敏值”改为登录态拉取真实明文后再复制，避免扩展天然拿到错误 Key。
- **浏览器扩展前置条件口径澄清**：补齐 `external pool` / `pool_access` 真实依赖，避免把所有“API 无效”都误判成同一个 API Key 问题。
- **内部 Web 提取兼容回归修复**：普通账号前端提取接入 shared logging 后，重新补齐 IMAP generic patch 点与旧错误语义，继续保持 `EMAIL_NOT_FOUND / 404` 与 `IMAP_AUTH_FAILED / 401` 兼容口径。
- **Overview 页面细节修复**：修复页头/Tab 模板静态文本未走 i18n、`刷新` / `邮箱池` 漏词条、残留英文短标签与动态机器值直出等问题。

### 重要变更 / Important Changes

- **版本升级**：`outlook_web.__version__` 从 `2.0.0` 升级为 `2.1.0`。
- **扩展版本同步**：`browser-extension/manifest.json` 从 `0.1.0` 升级为 `0.2.0`，与本次扩展可用性修复一并发布。
- **数据库升级**：schema 升级到 `v23`，新增 `verification_extract_logs` 表；其中 `account_id > 0` 表示 `accounts.id`，`account_id < 0` 表示负数编码后的 `temp_emails.id`。
- **发布口径保持不变**：当前仓库继续采用 **Python + Docker** 发布链路，正式产物仍以 Docker 镜像 tar 与源码 zip 为主，不引入 Tauri / Cargo / MSI / NSIS 构建链路。

### 测试/验证 / Testing & Verification

- 全量回归：
  - `python -m unittest discover -s tests -v`
  - 结果：`Ran 1243 tests in 302.912s`
  - 状态：`OK (skipped=7)`
- 构建验证：
  - `docker build -t outlook-email-plus:v2.1.0 .` → 成功
  - `dist/outlook-email-plus-v2.1.0-docker.tar`（177,893,376 bytes）
  - `dist/outlookEmailPlus-v2.1.0-src.zip`（4,335,587 bytes）
  - `dist/browser-extension-v0.2.0.zip`（38,097 bytes）
- GitHub Actions 实际结果：
  - `Create GitHub Release`（tag `v2.1.0`）✅ 成功
  - `Python Tests`（release commit `7cf7557`）✅ 成功
  - `SonarCloud Scan`（post-release docs commit `5b65a70`）✅ 成功
  - `Code Quality`（release commit `7cf7557`）❌ 失败：`black --check` 报告 10 个文件需格式化
  - `Build and Push Docker Image`（tag `v2.1.0`）❌ 失败：`quality-gate` 卡在 formatter checks，`build-and-push` job 未执行，因此镜像仓库发布未完成

## [v2.0.0] - 2026-04-18

### 新增功能 / New Features

- **浏览器扩展（Chrome/Edge MV3）v0.1.0**：全新 `browser-extension/` 子目录，提供邮箱池快捷操作面板，支持一键申领邮箱、自动提取验证码/验证链接、完成/释放邮箱，与 OutlookMail Plus 外部 API 无缝集成。
- **后端 CORS 支持**：`/api/external/*` 接口支持 `chrome-extension://` 来源跨域访问，扩展可直接调用后端。

### 修复 / Bug Fixes

- 修复账号覆盖导入（overwrite 模式）时 `pool_status` 未正确更新的 bug（`_overwrite_account` 参数透传遗漏）。
- 修复 `update_account_credentials` 不允许更新 `pool_status` 字段导致导入后邮箱池状态异常的问题。

### 重要变更 / Breaking Changes

- 版本号从 `1.19.0` 升级至 `2.0.0`（浏览器扩展为项目重大里程碑）。
- `requirements.txt` 新增 `flask-cors>=4.0.0`。

## [v1.19.0] - 2026-04-17

### 新增功能 / New Features

- **刷新失败提示模板化增强**：前端新增 selected/refresh-all 的失败摘要构造函数，统一输出错误码、可执行步骤与 trace 反馈指引，减少“仅显示刷新失败”不可操作提示。
- **Selected 刷新回归补强**：新增 `tests/test_refresh_selected_issue45.py`，覆盖 Outlook+IMAP 混选下仅刷新 Outlook、跳过 IMAP 且 SSE `start/progress/complete` 完整返回。

### 修复 / Bug Fixes

- **Issue #45 根因修复**：`stream_refresh_selected_accounts` 中 selected 查询补齐 `provider` 字段，`sqlite3.Row` 访问从 `row.get(...)` 改为 `row[...]`，修复 selected SSE 过滤阶段提前异常。
- **冲突提示语义统一**：scheduled / selected / retry_failed 三条刷新入口统一 `REFRESH_CONFLICT` 语义，明确“当前已有刷新任务执行中，请等待完成后再试”。
- **权限失败可执行提示**：`NO_MAIL_PERMISSION` 场景下前端改为给出重新授权与补齐 `Mail.Read / Mail.ReadWrite` 的明确操作建议。
- **OAuth Tool 空列表隔离修复**：`tests/test_oauth_tool.py` 的测试初始化补充清理关联表，消除共享测试库残留导致的 `test_accounts_list_empty` 间歇性失败。

### 重要变更 / Important Changes

- **版本升级**：`outlook_web.__version__` 从 `1.18.0` 升级为 `1.19.0`。
- **版本口径同步**：`README.md`、`README.en.md`、`tests/test_version_update.py`、`docs/DEVLOG.md` 同步更新到 `v1.19.0`。
- **发布口径说明**：当前仓库继续采用 Python + Docker 发布链路，不含 Tauri/Cargo/NPM/MSI/NSIS 构建链路；本次发布产物继续使用 Docker 镜像 tar 与源码 zip。

### 测试/验证 / Testing & Verification

- main 合并后分批全量回归（单命令 300000ms 约束下）：
  - Batch1：`Ran 303 tests in 189.896s`，`OK`
  - Batch2：`Ran 266 tests in 47.230s`，`OK`
  - Batch3：`Ran 273 tests in 43.359s`，`OK (skipped=7)`
  - Batch4：`Ran 352 tests in 82.976s`，`OK`
- 定向回归：
  - `tests.test_refresh_selected_issue45` / `tests.test_refresh_outlook_only` / `tests.test_frontend_account_type_and_refresh_suggestions_contract` / `tests.test_oauth_tool` 均通过。
- 本地 Docker 人工验收：
  - 构建镜像 `ghcr.io/zeropointsix/outlook-email-plus:local-main-20260417` 成功；
  - 容器 `outlook-email-plus-local-main` 在 `5002->5000` healthy；
  - `GET /healthz` 返回 `status=ok, version=1.18.0`（构建时点）；
  - 用户确认“验收通过”。

## [v1.18.0] - 2026-04-16

### 新增功能 / New Features

- **邮箱池项目维度成功复用**：长期邮箱在显式携带 `project_key`、`caller_id`、`task_id` 的路径下，完成 `claim-complete(result=success)` 后不再全局退出候选池，而是支持跨项目立即复用。
- **项目成功事实沉淀**：新增 claim 上下文与项目成功记录字段，成功复用的判断从“claim 痕迹”升级为“项目 success 事实”，同项目成功后阻断、跨项目成功后立即可复用。
- **测试覆盖扩展**：新增 Schema / Repository / Service 三层专项测试，并补强 flow suite 与旧骨架回归，覆盖迁移、成功计数、同项目/跨项目语义与 token 校验。

### 修复 / Bug Fixes

- **success 生命周期修复**：修复长期邮箱在 success 后被直接打成全局 `used`、导致其他项目无法继续领取的问题。
- **claim 上下文缺失修复**：修复 `claim-complete` 阶段无法得知 claim 所属项目、从而无法判断是否应进入项目复用语义的问题。
- **遗留迁移兼容修复**：修复 legacy v21 测试库缺列时 `migrate_sensitive_data()` 直接读取失败的问题，迁移阶段现可按实际列集合兼容处理。
- **旧回归口径修复**：收口历史测试中“release 必须删除 `account_project_usage` 行”的旧假设，改为与当前 success 语义一致。

### 重要变更 / Important Changes

- **版本升级**：`outlook_web.__version__` 从 `1.17.0` 升级为 `1.18.0`。
- **数据库升级**：数据库 schema 升级到 `v22`，新增 `accounts.claimed_project_key` 与 `account_project_usage.first_success_at / last_success_at / success_count`。
- **迁移边界**：历史长期邮箱 `used -> available` 只在升级到 `v22` 时执行；`cloudflare_temp_mail` / `temp_mail` 不进入该迁移语义，也不伪造历史 success 数据。
- **发布产物口径**：当前仓库仍不是 Tauri 工程，不包含 `Cargo.toml`、`package.json`、MSI 或 NSIS 构建链路；本次发布继续沿用 Docker 镜像 tar 与源码 zip 作为正式产物。

### 测试/验证 / Testing & Verification

- 目标专项回归：
  - `python -m unittest tests.test_db_schema_v22_pool_project_reuse tests.test_pool_repository_project_reuse tests.test_pool_service_project_reuse tests.test_pool_flow_suite tests.test_pool -v`
  - 结果：`Ran 78 tests`，`OK`
- 全量回归（本地 `main`）：
  - `python -m unittest discover -v`
  - 结果：`Ran 1187 tests in 458.110s`，`OK (skipped=7)`
- 构建验证：
  - `docker build -t outlook-email-plus:v1.18.0 .` → 成功
  - `dist/outlook-email-plus-v1.18.0-docker.tar`
  - `dist/outlookEmailPlus-v1.18.0-src.zip`
- Docker 运行态验证：
  - 默认 Compose 路径因挂载损坏的本地数据库而启动失败，根因已确认
  - 本地构建镜像使用隔离数据目录启动后，`GET /healthz` 返回 `200`

## [v1.17.0] - 2026-04-15

### 新功能 / New Features

- **通用 Webhook 通知通道**：在现有通知分发体系中新增 `webhook` 通道，支持全局单 URL 配置，与 Email/Telegram 并存；发送协议为 `POST text/plain; charset=utf-8`。
- **Webhook 测试链路**：新增 `/api/settings/webhook-test`，按“先保存，再测试”口径，仅使用已保存配置进行测试发送。
- **External API Key 易用性增强**：设置页新增“随机生成 + 复制”交互，随机值为前端 `crypto.getRandomValues` 生成的 64 位 URL-safe 字符串。

### 修复 / Bug Fixes

- **设置链路校验修复**：补齐 Webhook 配置保存与测试路径中的错误码映射与可读错误返回，配置缺失时稳定返回 `WEBHOOK_NOT_CONFIGURED`。
- **通知分发兼容修复**：Webhook 接入后继续保持 Email/Telegram 既有行为与游标/去重语义，不引入跨通道互斥副作用。
- **前端契约修复**：补齐自动化 Tab 与 API 安全 Tab 的文案和交互契约（Webhook 字段、测试按钮、API Key 生成与复制函数）以消除回归风险。

### 重要变更 / Important Changes

- **版本升级**：`outlook_web.__version__` 从 `1.16.0` 升级为 `1.17.0`。
- **版本口径同步**：`README.md`、`README.en.md`、`tests/test_version_update.py` 同步更新到 `v1.17.0`。
- Webhook Token 作为可选头处理：仅在 token 非空时发送 `X-Webhook-Token`。
- Webhook 投递策略固定：10 秒超时、失败立即重试 1 次、2xx 视为成功。
- 本次能力扩展未引入新第三方依赖，未进行数据库 schema 变更。

### 测试/验证 / Testing & Verification

- 定向测试：
  - `python -m unittest tests.test_settings_webhook -v` → 9 passed
  - `python -m unittest tests.test_webhook_push -v` → 7 passed
  - `python -m unittest tests.test_notification_dispatch -v` → 25 passed
  - `python -m unittest tests.test_settings_webhook_frontend_contract -v` → 4 passed
  - `python -m unittest tests.test_v190_frontend_contract -v` → 18 passed
  - `python -m unittest tests.test_settings_tab_refactor_backend -v` → 14 passed
  - `python -m unittest tests.test_settings_tab_refactor_frontend -v` → 12 passed
- 分批回归（单命令超时约束下）：
  - `test_[a-f]*` → Ran 346, OK
  - `test_[g-l]*` → Ran 89, OK
  - `test_[m-r]*` → Ran 231, OK (skipped=7)
  - `test_[s-z]*` → Ran 492, OK
  - 汇总：**1158 tests 通过，skipped=7**。
- main 分支复核：
  - 在 main 再次执行分批全量回归，结果与上次一致（**1158 通过，skipped=7**）。
- 构建验证：
  - `docker build -t outlook-email-plus:v1.17.0 .`（本次发布执行）
  - 产物预期：Docker 镜像 tar + 源码 zip

### 已知风险 / Known Risks

- Webhook 当前固定发送纯文本（`text/plain`）；若下游仅接受 JSON，需要由接入方在网关/中间层做文本转 JSON 适配。
- UI 人工冒烟（Webhook 卡片实操、API Key 随机/复制体验）仍建议在发布前补齐。

## [v1.16.0] - 2026-04-13

### 新功能 / New Features

- **OAuth Token 工具交互升级**：Token 工具前端从自动弹窗改为“获取授权链接”模式，支持在页面内直接展示 `authorize_url`，并提供复制/打开链接操作，提升跨环境授权稳定性。
- **Token 工具文档化增强**：为 `routes/token_tool.py`、`controllers/token_tool.py`、`services/oauth_tool.py` 增补模块级设计说明，明确兼容账号导入模式（`tenant=consumers`、`client_secret` 为空）与授权流关键约束。

### 修复 / Bug Fixes

- **OAuth flow 状态读取修复**：修复 `services/oauth_tool.py:get_oauth_flow()` 函数体缺失导致的 `IndentationError` 与 flow 状态读取异常；恢复过期清理与浅拷贝返回逻辑。
- **回调交换链路稳定性**：修复后 `state -> verifier -> code exchange` 链路恢复正常，避免授权成功后在服务端交换阶段失败。

### 重要变更 / Important Changes

- **版本升级**：`outlook_web.__version__` 从 `1.15.0` 升级到 `1.16.0`。
- **版本显示同步**：同步更新 `tests/test_version_update.py`、`README.md`、`README.en.md` 中的版本展示与断言口径。
- **文档现状同步**：同步更新 `.kiro/steering/*` 与 `CLAUDE.md` 的架构/测试口径描述（授权链接模式、本地 pytest 与 CI unittest 双口径）。

### 测试/验证 / Testing & Verification

- 全量回归：`python -m pytest tests/ -q` → **1109 passed, 9 skipped**。
- 关键回归：
  - `python -m pytest tests/test_version_update.py -v` → 51 passed
  - `python -m pytest tests/test_oauth_tool.py -v` → 71 passed
- 语法校验：`python -m py_compile outlook_web/services/oauth_tool.py outlook_web/controllers/token_tool.py outlook_web/routes/token_tool.py` 通过。

## [v1.15.0] - 2026-04-12

### 新功能 / New Features

- **OAuth Token 获取工具**：新增独立 Token 工具窗口，支持 Authorization Code + PKCE、手动粘贴回调 URL、Scope 校验、JWT 诊断信息展示
- **兼容账号导入模式**：OAuth Token 工具现固定面向个人 Microsoft 账号导入，要求 Public Client、`tenant=consumers`、`client_secret` 为空
- **账号一键写回**：获取到的 refresh token 可直接更新已有 Outlook 账号或创建新账号，并在写入前执行 token 有效性校验与轮换处理
- **配置持久化与环境变量开关**：支持 `oauth_tool_*` Settings 持久化、`OAUTH_TOOL_ENABLED` 总开关，以及 Client ID / Redirect URI / Scope / Tenant 的环境变量默认值
- **邮箱别名（+ 子地址）自动识别与回溯**：新增 `normalize_alias_email()`，统一将 `user+tag@domain` 规范化为 `user@domain`；在 `resolve_mailbox()`、external API 通用参数解析、内部邮件列表/邮件详情入口接入，保证别名地址可回溯到主账号且不改变无别名地址行为

- **分层口径收敛（why）**：分组策略仅保留规则项（`verification_code_length`、`verification_code_regex`），运行期 AI 配置统一迁移到系统设置（settings Basic Tab），避免“分组配置与系统配置双口径”导致的运维混乱。
- **系统级 AI 配置闭环（why）**：`GET/PUT /api/settings` 新增并承载 `verification_ai_enabled/base_url/api_key/model`；API Key 加密存储、脱敏回显；开启 AI 时执行保存期完整性校验。
- **提取链路提速与稳定性（why）**：保持规则快路径优先，仅在低置信度场景触发 AI fallback；AI 输出异常/无效时快速回退规则结果，不阻塞主流程。
- **AI fallback 触发条件收紧（方案 A）**：`enhance_verification_with_ai_fallback()` 由"code/link 任一低置信即触发 AI"调整为"code/link 任一高置信即跳过 AI"；仅在两者均为 low 时才调用 AI，避免"验证码已高置信命中却因链接低置信而白白调用 AI"的浪费。对外仍保留 `verification_code`/`verification_link` 双字段结构不变。
- **固定 JSON 契约（why）**：新增 AI 输入/输出固定 JSON 契约（`verification_ai_v1`），并在服务端进行结构与类型校验，降低模型返回漂移风险。
- **前端迁移策略（why）**：分组弹窗移除 AI 字段，历史 group AI payload 软兼容（忽略旧字段，不硬失败），实现平滑内部切换。

- 修复 Microsoft token 端点仅返回 `error_description` 时无法命中错误引导的问题，现会同时保留 `error` 码用于稳定映射
- 修复工具关闭场景下 Blueprint 已注册但测试期望动态 404 的问题，Controller 层现统一执行开关检查
- 加固 Token 工具的 Scope Chip 渲染逻辑，改为 DOM 创建 + 事件委托，避免将动态 scope 值拼进内联 `onclick`
- 明确 `oauth_tool_client_secret` 的兼容读取策略：历史明文配置继续可读，不可解密的 `enc:` 值保持隐藏为空字符串
- 修复 Token 工具“写入账号”弹窗在校验失败或接口返回 400 时提示被主状态栏遮住、表现为“确认写入没反应”的问题，错误现已直接显示在弹窗内
- 收敛 Token 工具为兼容账号导入模式：前端禁用 `client_secret`、Tenant 固定 `consumers`、默认 Scope 切换到 IMAP 兼容预设，`prepare/config/save` 接口统一拒绝不兼容配置，避免“保存成功但运行态刷新失败”的模型错位
- 新增邮箱别名能力对应测试覆盖：`tests/test_email_alias_normalize.py`、`tests/test_email_alias_flow.py`、`tests/test_email_alias_migration_compat.py`，并补充 `tests/test_mailbox_resolver.py` 的别名回溯用例

- 新增 `POST /api/settings/verification-ai-test`：基于**已保存**的系统级 AI 配置执行连通性与契约探测，返回结构化诊断结果（`ok/error/message/latency_ms/http_status/parsed_output`）。
- 探测口径调整为“连通性优先”：上游返回 HTTP 2xx 即判定 `ok=true`；同时暴露 `connectivity_ok` 与 `contract_ok` 区分“可连通”与“契约完全通过”。
- 前端“基础 -> 验证码 AI 增强”新增“🤖 测试 AI 配置”按钮与结果提示区，支持在页面内快速判断配置是否真正可用。
- 探测逻辑复用 `probe_verification_ai_runtime(...)`，重点覆盖：配置缺项、HTTP 错误、响应格式错误、AI 输出不符合固定 JSON 契约、探测成功。

## [v1.13.0] - 2026-04-09

### 新功能 / New Features

- **热更新双模式支持**：新增 Watchtower 和 Docker API（A2 helper 容器）两种一键更新方式，支持在设置页面切换
- **Watchtower 集成**：连通性测试、手动触发更新、已是最新版本智能检测（基于 Watchtower 同步行为）
- **Docker API 自更新**：digest 预检查避免无效更新、辅助容器（oep-updater）执行 12 步更新流程、失败自动回滚
- **GHCR 镜像支持**：白名单新增 `ghcr.io/zeropointsix/` 前缀，支持 GitHub Container Registry 镜像
- **版本检测增强**：`_version_gt()` 支持 pre-release 后缀（如 `-hotupdate-test`），自动忽略后缀仅比较语义版本号
- **部署信息 API**：`/api/system/deployment-info` 返回镜像名、标签、本地构建检测、Docker API 可用性
- **healthz 增强**：新增 `boot_id`（进程指纹）和 `version` 字段，支持前端精确检测容器重启

### 修复 / Bug Fixes

- 修复 Watchtower 连通测试 5s 超时（Watchtower 同步检查需 25-30s），增加到 35s
- 修复 Watchtower 200 响应被误判为"更新成功"（实际为"已是最新"）
- 修复 GHCR 镜像不在白名单导致 Docker API 更新被拦截
- 修复本地镜像检测 `_looks_like_local_image_ref()` 误判远程镜像
- 修复 `docker_api_available` 仅检查 Watchtower 不检查 Docker API
- 修复 Docker API 自更新同步调用导致容器停止时响应中断（改为后台线程 + 立即返回）
- 修复 `ModuleNotFoundError: outlook_web.models.AuditLog` 导致更新接口 500
- 修复前端 `waitForRestart()` 无法检测容器真正重启（新增 boot_id 变化检测）

### i18n

- 新增 emoji 前缀 i18n 变体：`🔄 一键更新配置`、`🚀 触发容器更新`
- 新增设置页 Tab 翻译：基础 / 临时邮箱 / API 安全 / 自动化
- 新增连通性/更新状态翻译：连通正常 / 检查完毕 / 测试中 / 更新失败
- `testWatchtower()` 结果文本经过 `translateAppTextLocal()` 翻译
- `manualTriggerUpdate()` 使用 `pickApiMessage()` 实现双语消息

### 安全

- 镜像白名单校验 + RepoDigests 检测双重防护，禁止本地构建镜像触发更新
- Docker API 自更新默认关闭，需显式设置 `DOCKER_SELF_UPDATE_ALLOW=true`
- 更新操作记录审计日志

---

## [v1.11.0] - 2026-04-03

### 新功能 / New Features

- **邮箱池项目隔离（PR#27）**：在 `claim-random` 时支持传入 `project_key`，同一 `caller_id + project_key` 下已使用的账号不会被重复领取（DB 迁移 v17）
- **CF Worker 临时邮箱多域支持**：可在设置页配置多个 CF Worker 域名；新增"同步域名"按钮，支持前端一键刷新域名列表
- **CF Worker Admin Key 加密存储**：`cf_worker_admin_key` 现在以 `enc:` 前缀加密写入数据库，不再以明文存储（DB 迁移 v18）
- **账号列表前端分页**：每页展示 50 条账号，大量账号时滚动加载更流畅
- **统一轮询引擎**：将标准模式与简洁模式的双轮询系统合并为单一 `poll-engine`（4 阶段重构），消除轮询竞争与状态积压

### 修复 / Bug Fixes

- **BUG-06**：生成或删除临时邮箱后，列表中已选中的邮箱状态得到正确保留，不再因刷新而丢失选中高亮
- **BUG-07**：临时邮箱面板在刷新邮件列表后，域名下拉选择不再被意外重置回默认值
- **Issue #24**：修复邮件展开/激活状态在列表重渲染后丢失、i18n 语言切换后账号列表不刷新、视口高度链路断裂、缺失翻译词条等问题
- **轮询 BUG**：修复页面初始加载时触发的批量邮件拉取、分组切换重复启动轮询、跨视图切换时轮询状态积压等问题
- **Graph API 401 静默回退**：修复 token 轮换时 Graph API 401 被静默吞掉导致的 token 丢失问题

### i18n

- 临时邮箱面板域名提示文字（`domain_hint_xxx`）新增中英双语翻译
- CF Worker 域名同步按钮 (`sync_cf_domains`)、提示文字 (`cf_domain_hint`) 新增双语支持
- 补充设置页与轮询指示器等处的缺失翻译词条

### CI / 代码质量修复

- 修复 `pool.py` 中存在的重复函数定义（`release`、`complete`、`expire_stale_claims`、`recover_cooldown`、`get_stats`）
- 修复 `pool.py` `get_stats()` 后的死代码（`return` 之后的不可达 `claim` 函数体）
- 修复 `RESULT_TO_POOL_STATUS` 中 `"success"` 映射：由旧的 `"cooldown"` 改为正确的 `"used"`
- 修复 `get_stats()` 的 `pool_counts` 字典，补充缺失的 `"used": 0` 键
- 修复 `pool.py` `claim_atomic()` 中 black 格式化问题（`cutoff`、`lease_expires_at_str` 多行表达式）
- 在 `external_api.py` 中添加 `# noqa: E203`、`# noqa: C901` 压制 flake8 误报
- 对齐 `test_pool.py` 和 `test_pool_flow_suite.py` 中的测试断言，统一期望 `success` 完成后状态为 `"used"`
- 全量 `black --line-length 127` 与 `isort --profile black` 格式化

---

## [v1.10.0] - 2026-03-26

- OAuth 回归修复与认证后工作区重构

## [v1.9.2] - 2026-03-24

- 小版本修复

## [v1.9.0] - 2026-03-20

- 双语界面、统一通知分发与演示站点保护

## [v1.7.0] - 2026-03-15

- 第二次发布：README 交付口径补全

## [v1.6.1] - 2026-03-15

- 发布质量闸门清理与发布内容精简
