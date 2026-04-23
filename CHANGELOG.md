# Changelog

All notable changes to OutlookMail Plus are documented in this file.

## [Unreleased]

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
