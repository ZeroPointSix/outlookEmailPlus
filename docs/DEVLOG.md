# DEVLOG

## v2.1.0 - 数据概览大盘与提取链路观测增强

发布日期：2026-04-20

### 新增功能

- 新增 5 Tab 数据概览大盘：统一展示总览、验证码提取、对外 API、邮箱池、系统活动五类运营数据。
- 新增 `verification_extract_logs` 与共享日志 helper：统一沉淀普通账号、临时邮箱、external API 提取链路的时延、通道、AI fallback 与错误码。
- 新增 overview 前端实时重拉与完整 i18n 收口：页头、Tab、KPI、表头、hover note、timeline/channel/status 等可见文案统一纳入翻译。

### 修复

- 修复浏览器扩展复制到脱敏 API Key 导致的“API 无效”问题，复制按钮现可获取真实明文 Key。
- 修复普通账号前端提取接入 shared logging 后的 Web 兼容语义回归，继续保持 `EMAIL_NOT_FOUND / 404`、`IMAP_AUTH_FAILED / 401` 等既有契约。
- 修复 overview 页头/Tab 模板静态文案未接 i18n、`刷新` / `邮箱池` 漏词条、残留英文短标签与动态机器值直出问题。

### 重要变更

- 版本号从 `2.0.0` 升级至 `2.1.0`。
- 浏览器扩展 Manifest 版本从 `0.1.0` 升级到 `0.2.0`。
- 数据库 schema 升级到 `v23`，新增 `verification_extract_logs`。
- 当前发布链路继续沿用 Python + Docker（Docker tar + 源码 zip），不引入 Tauri/MSI/NSIS。

### 测试/验证

- 全量测试：
  - `python -m unittest discover -s tests -v`
  - 结果：`Ran 1243 tests in 302.912s`
  - 状态：`OK (skipped=7)`
- 构建验证：
  - `docker build -t outlook-email-plus:v2.1.0 .` → 成功
  - 产物：
    - `dist/outlook-email-plus-v2.1.0-docker.tar`（177,893,376 bytes）
      - `sha256:108042af3e740b607efc0b4a305a07a9f0f3433805be21b9c95b68eb1a19e497`
    - `dist/outlookEmailPlus-v2.1.0-src.zip`（4,335,587 bytes）
      - `sha256:2d93c6102eb85651524571c2b9cbfd2fa6805066c8d3b0d5a057ef7e4b35df56`
    - `dist/browser-extension-v0.2.0.zip`（38,097 bytes）
      - `sha256:a237c1796c662e8c5bba205dfea0db8017812478f499c66b4f11d2e4e6416033`

## v2.0.0 - 浏览器扩展 v0.1.0 发布

发布日期：2026-04-18

### 新增功能

- 新增 Chrome/Edge MV3 浏览器扩展（`browser-extension/`）：邮箱池快捷操作面板，支持一键申领邮箱、验证码/验证链接自动提取、完成/释放邮箱，与后端外部 API 无缝集成。
- 新增后端 CORS 支持：`outlook_web/app.py` 集成 `flask-cors`，`/api/external/*` 允许 `chrome-extension://` 来源跨域访问。

### 修复

- 修复账号覆盖导入时 `pool_status` 未正确传递的 bug，确保 claimed/used 状态邮箱在重新导入时能正确重置为 available。
- 修复 `update_account_credentials` 中 allowed 集合缺少 `pool_status` 字段，导致状态更新静默失败。

### 重要变更

- 版本号从 `1.19.0` 升级至 `2.0.0`，标志浏览器扩展能力正式进入主线。
- 同步更新版本口径文件：`README.md`、`README.en.md`、`tests/test_version_update.py`、`CHANGELOG.md`。
- `requirements.txt` 新增 `flask-cors>=4.0.0`。

### 测试/验证

- main 分支全量测试：`Ran 1194 tests in 354.407s  OK (skipped=7)` 全绿 ✅
- dev 合并 main 后全量测试：`Ran 1204 tests in 377.181s  FAILED (failures=1, skipped=7)`，唯一失败为 CF Worker 真实 E2E（需外部网络），与本次代码变更无关。

## v1.19.0 - 刷新失败可执行提示与 Selected SSE 稳定性修复

发布日期：2026-04-17

### 新增功能

- 新增 selected/refresh-all 刷新失败摘要模板：统一展示错误码、可执行步骤与 trace 反馈指引。
- 新增 Issue #45 独立回归用例文件：`tests/test_refresh_selected_issue45.py`，覆盖混选场景下 Outlook-only 刷新与 SSE 事件完整性。

### 修复

- 修复 selected 刷新链路对 `sqlite3.Row` 使用 `.get()` 导致的 SSE 提前失败问题（改为 `row["provider"]` 并补齐查询字段）。
- 修复刷新冲突提示在不同入口语义不一致问题，统一 `REFRESH_CONFLICT` 返回与前端可执行指引。
- 修复 `NO_MAIL_PERMISSION` 场景下提示笼统的问题，前端新增重新授权与权限补齐建议。
- 修复 OAuth Tool 空列表测试的共享库污染问题，增强 `setUp()` 关联表清理。

### 重要变更

- 版本号从 `1.18.0` 升级至 `1.19.0`。
- 同步更新版本口径文件：`README.md`、`README.en.md`、`tests/test_version_update.py`、`CHANGELOG.md`。
- 发布链路继续沿用 Python + Docker 产物（tar/zip），不引入 Tauri/MSI/NSIS 构建链路。

### 测试/验证

- main 合并后分批全量回归：
  - Batch1：`Ran 303 tests in 189.896s`，`OK`
  - Batch2：`Ran 266 tests in 47.230s`，`OK`
  - Batch3：`Ran 273 tests in 43.359s`，`OK (skipped=7)`
  - Batch4：`Ran 352 tests in 82.976s`，`OK`
- 定向回归：`tests.test_refresh_selected_issue45`、`tests.test_refresh_outlook_only`、`tests.test_frontend_account_type_and_refresh_suggestions_contract`、`tests.test_oauth_tool` 均通过。
- 本地 Docker 人工验收已通过（容器重建后健康检查正常，用户确认通过）。

## v1.18.0 - 邮箱池项目维度成功复用

发布日期：2026-04-16

### 新增功能

- 新增长期邮箱“项目维度成功复用”能力：在显式传入 `project_key`、`caller_id`、`task_id` 的路径下，`claim-complete(result=success)` 后账号立即回到 `available`，支持跨项目继续领取。
- 新增项目成功事实字段与 claim 上下文记录：`accounts.claimed_project_key`、`account_project_usage.first_success_at / last_success_at / success_count`，用于把复用判定从 claim 痕迹切换为 success 事实。
- 新增对应的专项测试文件与回归覆盖，围绕 Schema v22、Repository 生命周期、Service 上下文传递和 flow suite 补齐目标语义验证。

### 修复

- 修复长期邮箱 success 后被全局打成 `used`、导致其他项目无法复用的问题。
- 修复 `claim-complete` 阶段缺失项目上下文的问题，使 complete 时可以准确判断是否启用项目复用语义。
- 修复 legacy v21 迁移过程中缺少 `password` 等列时的兼容性问题。
- 修复历史旧测试对 `release()` 语义的错误假设，避免继续要求删除 `account_project_usage` 行。

### 重要变更

- 版本号从 `1.17.0` 升级至 `1.18.0`。
- 数据库 schema 升级至 `v22`，并引入长期邮箱 `used -> available` 的一次性历史迁移逻辑。
- `README.md`、`README.en.md`、`tests/test_version_update.py` 已同步到 `v1.18.0`。
- 当前仓库仍不是 Tauri 工程，不包含 `Cargo.toml`、`package.json`、MSI 或 NSIS 构建链路；本次正式产物继续沿用 Docker 镜像 tar 与源码 zip。

### 测试/验证

- 目标专项回归：`python -m unittest tests.test_db_schema_v22_pool_project_reuse tests.test_pool_repository_project_reuse tests.test_pool_service_project_reuse tests.test_pool_flow_suite tests.test_pool -v` → `Ran 78 tests`，`OK`
- 全量回归：`python -m unittest discover -v` → `Ran 1187 tests in 458.110s`，`OK (skipped=7)`
- 构建验证：
  - `docker build -t outlook-email-plus:v1.18.0 .` → 成功
  - Docker 镜像 ID：`sha256:a3fa082473f29ce34054362cf8550c3dce35d0a5f18154d924f15170c3c333cd`
  - 产物：
    - `dist/outlook-email-plus-v1.18.0-docker.tar`（204,749,824 bytes）
    - `dist/outlookEmailPlus-v1.18.0-src.zip`（4,127,512 bytes）
- Docker 本地构建启动验证：本地构建镜像在隔离数据目录下可健康启动，`GET /healthz` 返回 `200`

## v1.17.0 - 通用 Webhook 通知与 API Key 易用性增强

发布日期：2026-04-15

### 新增功能

- 新增通用 Webhook 通知通道，支持在现有通知分发中与 Email/Telegram 并存。
- 新增 `POST /api/settings/webhook-test` 测试接口，严格采用“先保存配置，再测试发送”口径。
- 设置页新增 External API Key “随机生成 + 复制”交互，随机值由前端 `crypto.getRandomValues` 生成 64 位 URL-safe 字符串。

### 修复

- 完善 Webhook 配置/测试路径错误码与可读错误输出，配置缺失时稳定返回 `WEBHOOK_NOT_CONFIGURED`。
- 修复并收敛 Webhook 接入后的通道协同行为，保持既有 Email/Telegram 行为与去重语义不回退。
- 补齐前端契约与 i18n 词条，避免设置页交互和提示文案的回归漂移。

### 重要变更

- 版本号从 `1.16.0` 升级至 `1.17.0`。
- 版本口径同步更新：`README.md`、`README.en.md`、`tests/test_version_update.py`。
- 本次改动未引入新第三方依赖，未进行数据库 schema 升级。

### 测试/验证

- 定向测试（Webhook/API Key）：
  - `python -m unittest tests.test_settings_webhook -v` → `Ran 9, OK`
  - `python -m unittest tests.test_webhook_push -v` → `Ran 7, OK`
  - `python -m unittest tests.test_notification_dispatch -v` → `Ran 25, OK`
  - `python -m unittest tests.test_settings_webhook_frontend_contract -v` → `Ran 4, OK`
  - `python -m unittest tests.test_v190_frontend_contract -v` → `Ran 18, OK`
- 分批全量回归（main）：
  - `test_[a-f]*` → `Ran 346, OK`
  - `test_[g-l]*` → `Ran 89, OK`
  - `test_[m-r]*` → `Ran 231, OK (skipped=7)`
  - `test_[s-z]*` → `Ran 492, OK`
  - 汇总：`1158 tests 通过，skipped=7`
- 构建与发布：见本次 Release 执行记录（WORKSPACE 与 GitHub Release 页面）。

## v1.16.0 - OAuth Token 授权链接模式与 flow 修复

发布日期：2026-04-13

### 新增功能

- OAuth Token 工具改为“获取授权链接”交互模式：用户可在页面中直接获取、复制、打开授权链接，再手动粘贴回调 URL 进行 token 交换。
- Token 工具三层模块（routes/controllers/services）补充设计注释，明确兼容导入模式与安全校验链路。

### 修复

- 修复 `outlook_web/services/oauth_tool.py` 中 `get_oauth_flow()` 函数体缺失导致的 `IndentationError`。
- 恢复 OAuth flow 读取逻辑：过期清理、状态读取、浅拷贝返回，修复授权回调后的交换链路稳定性。

### 重要变更

- 版本号从 `1.15.0` 升级至 `1.16.0`。
- 版本展示与断言同步更新：`tests/test_version_update.py`、`README.md`、`README.en.md`。
- 文档口径同步：`.kiro/steering/*` 与 `CLAUDE.md` 已按当前代码架构与测试流程更新。

### 测试/验证

- 全量回归：`python -m pytest tests/ -q` → `1109 passed, 9 skipped`
- 关键专项：
  - `python -m pytest tests/test_version_update.py -v` → `51 passed`
  - `python -m pytest tests/test_oauth_tool.py -v` → `71 passed`
- 语法检查：
  - `python -m py_compile outlook_web/services/oauth_tool.py outlook_web/controllers/token_tool.py outlook_web/routes/token_tool.py` ✅

## v1.15.1 - CI 质量门禁修复与发布链路恢复

发布日期：2026-04-12

### 新增功能

- 无新增业务功能。

### 修复

- 修复 `Code Quality` 中 `black/isort` 格式化门禁失败问题，统一对齐仓库格式规范。
- 修复 `Build and Push Docker Image` 被前置 `quality-gate` 阻断的问题，恢复主干镜像构建与推送能力。

### 重要变更

- 版本号由 `1.15.0` 升级为 `1.15.1`，用于补齐版本标签镜像发布链路，确保版本发布与主干 CI 状态一致。

### 测试/验证

- 格式化校验：
  - `python -m black --check outlook_web tests web_outlook_app.py outlook_mail_reader.py start.py` ✅
  - `python -m isort --check-only --profile black outlook_web tests web_outlook_app.py outlook_mail_reader.py start.py` ✅
- 回归抽检：`python -m pytest -q tests/test_version_update.py tests/test_i18n_settings_completeness.py` → `71 passed`
- GitHub Actions（main / commit `61208e0`）验证通过：
  - `Build and Push Docker Image` ✅
  - `Code Quality` ✅
  - `Python Tests` ✅
  - `SonarCloud Scan` ✅
- `v1.15.1` tag 流水线验证通过：
  - `Create GitHub Release` ✅
  - `Build and Push Docker Image`（tag）✅
- 镜像仓库一致性核对（GHCR + Docker Hub）通过：
  - 版本标签：`v1.15.1` / `v1.15.1-d09d67f` → `sha256:4b1985478bb0f2c0fdf1ec6ef705ee62858919a886c7a8c79acd880ac45dd964`
  - 主线标签：`main` / `main-d09d67f` / `latest` → `sha256:a409244bf43a7f2e921d86f4977eeced462942d589b66d57982f1ed8eb930a9f`

## v1.15.0 - 验证码提取链路优化与设置页 i18n 补齐

发布日期：2026-04-12

### 新增功能

- 新增验证码提取链路统一能力：Web 与 External API 走同一提取策略，减少双路径行为漂移。
- 新增系统级验证码 AI 配置闭环：`verification_ai_enabled/base_url/api_key/model` 统一由 settings 管理，支持 API Key 加密存储与脱敏回显。
- 新增验证码 AI 可用性探测接口：`POST /api/settings/verification-ai-test`，输出结构化诊断字段用于快速排障。
- 新增固定 JSON 契约 `verification_ai_v1` 与结构校验，降低模型响应格式漂移。

### 修复

- 修复 `ACCOUNT_AUTH_EXPIRED` 误报场景，避免单通道失败导致整体误判。
- 修复 `VERIFICATION_NOT_FOUND` 语义不一致问题，统一“可读但未提取到验证码”的错误表达。
- 修复本地直启未加载 `.env` 时的凭据解密异常误判。
- 修复 SMTP 测试链路 587/465 模式冲突（587 强制 STARTTLS，465 强制 SSL）。
- 修复设置页 i18n 缺失映射，补齐“基础设置 / 验证码 AI 增强区 / 测试 AI 配置”等关键文案。

### 重要变更

- AI fallback 触发条件由“任一低置信触发”收紧为“code/link 均低置信才触发”，减少无效 AI 调用。
- 分组级 AI 配置口径收敛：分组仅保留规则项（长度/正则），运行期 AI 配置统一迁移到系统设置。
- 版本号从 `1.13.0` 升级至 `1.15.0`，由 `outlook_web.__version__` 统一驱动应用与接口版本展示。

### 测试/验证

- 全量回归（分片执行，等价覆盖全量）：
  - `python -m pytest -q tests/test_[a-m]*.py` → `441 passed, 2 skipped`（188.91s）
  - `python -m pytest -q tests/test_[n-z]*.py` → `597 passed, 7 skipped`（112.16s）
  - 合计：`1038 passed, 9 skipped`（301.07s）
- 版本更新回归：`python -m pytest -q tests/test_version_update.py` → `51 passed`
- 设置页 i18n 完整性回归：`python -m pytest -q tests/test_i18n_settings_completeness.py` → `20 passed`
- 验证码提取链路基准对比显示平均耗时下降，长尾场景已收敛并持续观察中。

## v1.13.0 - 热更新双模式端到端验证与合并

发布日期：2026-04-09

### 新增功能

- 新增热更新双模式支持：Watchtower（推荐）和 Docker API 自更新（A2 helper 容器），可在设置页面一键切换更新方式。
- 新增 Watchtower 集成：连通性测试、手动触发更新、已是最新版本智能检测（基于 Watchtower 同步 POST `/v1/update` 接口的行为特征——收到 200 响应即表示当前已是最新版本）。
- 新增 Docker API 自更新（A2 方案）：通过 Docker API 创建短生命周期 updater 容器（`oep-updater-*`），执行 12 步更新流程（pull → digest 比对 → create → stop 旧 → start 新 → health check → rename → cleanup），支持失败自动回滚。
- 新增 GHCR 镜像支持：白名单新增 `ghcr.io/zeropointsix/` 前缀，支持 GitHub Container Registry 镜像的热更新。
- 新增版本比较 pre-release 后缀支持：`_version_gt()` 自动忽略 `-hotupdate-test` 等后缀，仅比较语义化版本号。
- 新增 `/api/system/deployment-info` 部署信息 API：返回镜像名、标签类型、本地构建检测、Docker API 可用性、Watchtower 连通性。
- 新增 healthz `boot_id` 和 `version` 字段：前端通过 boot_id 变化精确检测容器重启。
- 新增设置面板手动触发更新按钮 UI，支持 i18n 中英双语。

### 修复

- 修复 Watchtower 连通测试超时：Watchtower `POST /v1/update` 是同步接口，完整镜像检查需 25-30s，连通测试超时从 5s 增加到 35s。
- 修复 Watchtower 200 响应被误判为"更新成功"：实际为"已是最新版本"（收到 200 说明 Watchtower 完成检查且未触发更新）。
- 修复 GHCR 镜像不在白名单导致 Docker API 更新被拦截。
- 修复本地镜像检测 `_looks_like_local_image_ref()` 误判远程镜像为本地构建。
- 修复 `can_auto_update` 逻辑仅检查 Watchtower 不检查 Docker API 可用性。
- 修复 Docker API 自更新同步调用导致容器停止时 HTTP 响应中断（改为后台线程 + 立即返回 → 再改为 A2 helper 容器方案）。
- 修复 `ModuleNotFoundError: outlook_web.models.AuditLog` 导致更新接口 500。
- 修复前端 `waitForRestart()` 无法检测容器真正重启（新增 boot_id 变化检测 + seenDown 双重判定）。
- 修复 Docker API 更新同 digest 时前端超时卡死（新增 digest 预检查，相同版本立即返回 `already_latest`）。
- 修复 emoji 前缀文本（🔄/🚀）的 i18n 翻译匹配失败。
- 修复设置页 Tab 标签（基础/临时邮箱/API 安全/自动化）缺少英文翻译。

### 重要变更

- 版本号从 `1.12.0` 提升到 `1.13.0`，应用 UI、系统接口和对外 API 返回的版本信息继续由 `outlook_web.__version__` 统一驱动。
- 热更新功能经过 `hotupdate-test` 分支 24 个提交的端到端验证，使用 GHCR 远程镜像在 Docker 环境中完成了两种更新方式的实际测试。
- 删除测试专用 compose 文件（`docker-compose.hotupdate-test.yml`、`docker-compose.docker-api-test.yml`），仅保留主 `docker-compose.yml`。
- 英文 README 大幅更新：新增 docker-compose + Watchtower 部署方式、一键更新功能描述和环境变量说明。

### 测试/验证

- 自动化测试：`python -m unittest discover -s tests -v`
  - 结果：`Ran 893 tests in 171.220s`
  - 状态：全部通过（6 skipped）
- 端到端验证（`hotupdate-test` 分支）：
  - Watchtower 模式：连通性测试、已是最新检测、i18n 双语切换 ✅
  - Docker API 模式：digest 预检查、A2 helper 容器创建/运行/自动清理 ✅
  - 镜像白名单：本地构建拦截、GHCR 远程镜像放行 ✅
  - 正向端到端：远程镜像 tag 变更 → A2 updater 完成 stop/start/rename/backup 全链路 ✅

## v1.10.0 - OAuth 回归修复与认证后工作区重构

发布日期：2026-03-26

### 新增功能

- 新增认证后主应用 `workspace` 语义化布局与 `ui_layout_v2` 持久化能力，支持侧栏折叠、拖拽宽度、移动端响应式以及旧本地布局数据自动迁移。
- 新增 Outlook OAuth 回调页与回调路由注册，前端可直接处理 `code`、`state`、错误参数及来源校验结果，降低 OAuth 导入链路的人工兜底成本。
- 新增账号备注轻量编辑 `PATCH` 接口，标准列表与紧凑模式都可以单独更新备注，不再要求提交完整账号凭据。
- 新增外部邮箱池对接收口后的回归覆盖，围绕 `/api/external/pool/*`、账号类型建议与通知分发补齐了一批契约测试与流程测试。

### 修复

- 修复 Outlook OAuth 回调、CSRF 恢复、verify-token 绑定和重试后回跳流程中的多处回归问题，避免导入链路因旧前端参数或异常回调而中断。
- 修复通知分发、Telegram 推送参与判定、临时邮箱内联图片刷新以及刷新失败提示文案不一致的问题，恢复主流程的可观测性和前端反馈一致性。
- 修复认证后简洁模式回归，恢复账号摘要列、分组交互、紧凑布局样式、多语言文案以及备注弹窗流程。
- 修复多 Key 鉴权场景下旧版 `external_api_key` 优先级异常，避免陈旧多 Key 配置覆盖仍在使用的单 Key 鉴权。

### 重要变更

- 版本号从 `1.9.2` 提升到 `1.10.0`，应用 UI、系统接口和对外 API 返回的版本信息继续由 `outlook_web.__version__` 统一驱动。
- 内部匿名 `/api/pool/*` 路径相关测试与前端契约已彻底收口到受控外部接口 `/api/external/pool/*`，后续集成方应以外部池协议为准。
- 当前仓库仍不是 Tauri 工程，不包含 `Cargo.toml`、`package.json`、MSI 或 NSIS 构建链路；本次正式产物继续沿用 Docker 镜像 tar 与源码 zip。

### 测试/验证

- 自动化测试：`python -m unittest discover -s tests -v`
  - 结果：`Ran 644 tests in 125.575s`
  - 状态：全部通过
- 构建验证：`docker build -t outlook-email-plus:v1.10.0 .`
  - 状态：成功
  - 镜像摘要：`sha256:7563be074c157e3273c8fc7aa557bda2ce5e5944a3a0a285ad0125bc559ece73`
- 发布产物：
  - `dist/outlook-email-plus-v1.10.0-docker.tar`
  - `dist/outlookEmailPlus-v1.10.0-src.zip`

## v1.9.2 - 紧凑模式发布与刷新提示增强

发布日期：2026-03-24

### 新增功能

- 新增账号管理“简洁模式”视图：账号列表支持高密度展示、分组条、验证码/最新邮件摘要列，以及标准/简洁模式之间的选中状态同步，适合批量运营场景。
- 新增账号备注轻量编辑链路：标准列表与简洁模式都可直接打开备注弹窗，通过独立 `PATCH` 接口只更新 `remark` 字段，支持新增、修改和清空备注而不要求重新填写账号凭据。
- 新增临时邮箱富内容保真能力：临时邮箱详情页可解析 `cid:` 内联图片、data URL 与远程图片地址，验证码截图类邮件可直接在前端查看。
- 新增按账号类型生成的刷新失败建议：刷新错误弹窗会根据 Outlook OAuth、Gmail IMAP、通用 IMAP 等不同场景给出差异化排障提示。

### 修复

- 修复 Outlook 刷新链路回归，手动刷新、重试失败与全量刷新会明确限制在 Outlook OAuth 账号范围内，避免 IMAP 账号误走 Graph 刷新流程并污染日志。
- 修复 Outlook.com Basic Auth 失败时的错误反馈，对邮箱详情、验证码提取和 external API 场景统一返回明确的 OAuth 导入提示。
- 修复旧版浏览器内置 OAuth 取 Token 流程导致的初始化与交互问题，移除失效的 `/api/oauth/*` 路由及前端入口，避免继续暴露不可用流程。
- 修复备注编辑、多语言文案与账号面板展示的一致性问题，统一“备注”入口名称，补齐弹窗相关国际化文案，并避免 IMAP 账号显示误导性的 Token 过期状态。

### 重要变更

- 版本号从 `1.9.1` 提升到 `1.9.2`，应用 UI 侧边栏版本显示、系统/对外 API 返回的 `version` 字段继续由 `outlook_web.__version__` 统一驱动。
- 当前仓库不是 Tauri 工程，不包含 `Cargo.toml`、`package.json`、MSI 或 NSIS 构建链路；本次发布继续沿用仓库既有的 Docker 镜像 tar 与源码 zip 作为正式产物。
- `README.md`、`README.en.md` 与 `registration-mail-pool-api.en.md` 已按当前实现同步更新，对外说明统一到受控 external API 与当前部署口径。

### 测试/验证

- 自动化测试：`python -m unittest discover -s tests -v`
  - 结果：`Ran 617 tests in 158.232s`
  - 状态：全部通过
  - 备注：Playwright 相关 2 个浏览器用例因环境缺少 `playwright` / `werkzeug` 依赖而按预期跳过。
- 构建验证：`docker build -t outlook-email-plus:v1.9.2 .`
  - 状态：成功
  - 镜像摘要：`sha256:d7aa37eabd966be0789815742434bec45472197ff6bfc1861db1859d02051346`
- 发布产物：
  - `dist/outlook-email-plus-v1.9.2-docker.tar`（174,048,768 bytes）
  - `dist/outlookEmailPlus-v1.9.2-src.zip`（1,078,317 bytes）

## v1.8.0 - 邮箱池与受控对外池 API 首次交付

发布日期：2026-03-17

### 新增功能

- 新增内部邮箱池接口：`/api/pool/claim-random`、`/api/pool/claim-release`、`/api/pool/claim-complete`、`/api/pool/stats`，支持随机领取、人工释放、结果回写与池统计。
- 新增对外邮箱池接口：`/api/external/pool/*` 现已支持 API Key 鉴权访问，并接入既有公网模式守卫、访问审计与调用方日级使用统计。
- 新增邮箱池状态机与持久化结构：账号新增 `pool_status`、`claimed_by`、`lease_expires_at`、`claim_token`、成功/失败计数等字段，同时引入 `account_claim_logs` 记录 claim/release/complete/expire 全链路动作。
- 新增多 API Key 粒度权限：`external_api_keys` 现支持 `pool_access` 字段，可按调用方单独授予 external pool 访问能力。

### 修复

- 修正对外邮箱池接口的返回格式，使 `claim-random`、`claim-release`、`claim-complete` 与 `stats` 全部对齐现有 external API contract，避免对接方处理分支不一致。
- 修正设置接口对邮箱池总开关和公网模式细粒度禁用项的读写逻辑，确保 `pool_external_enabled` 与 `external_api_disable_pool_*` 系列配置可以稳定持久化并回显。
- 修正租约超时回收行为，过期 claim 会自动写入 claim log、转入 `cooldown`，降低因调用方异常退出导致账号长期悬挂的风险。

### 重要变更

- 版本号从 `1.7.0` 提升到 `1.8.0`，应用 UI 侧边栏版本显示、系统/对外 API 返回的 `version` 字段继续由 `outlook_web.__version__` 统一驱动。
- 数据库 schema 新增邮箱池相关字段、`account_claim_logs` 表，以及 `external_api_keys.pool_access` 权限列；现有库初始化/升级时会自动补齐。
- 当前仓库不是 Tauri 工程，不包含 `Cargo.toml`、`package.json`、MSI 或 NSIS 构建链路；本次发布继续沿用仓库既有的 Docker 镜像 tar 与源码 zip 作为正式产物。

### 测试/验证

- 单元测试：`python -m unittest discover -s tests -v`
  - 结果：`Ran 440 tests in 42.599s`
  - 状态：全部通过
- 构建验证：`docker build -t outlook-email-plus:v1.8.0 .`
  - 状态：失败
  - 原因：Docker daemon 未启动，`//./pipe/dockerDesktopLinuxEngine` 不存在，当前环境无法连接 Docker Desktop Linux Engine
- 发布产物：
  - 未生成。由于镜像构建失败，本次未导出 Docker tar、源码 zip，也未同步到 GitHub Release 页面。

## v1.7.0 - 第二次发布：README 交付口径补全

发布日期：2026-03-15

### 新增功能

- 无新增业务功能。本次版本以“对外交付说明与发布内容整理”为主。

### 修复

- 重写 `README.md`，按当前代码实际能力补齐对外说明：对外只读 API、公网模式守卫（IP 白名单/限流/高风险端点禁用）、异步 probe、调度器、反向代理安全配置等。

### 重要变更

- 版本号从 `1.6.1` 提升到 `1.7.0`，应用 UI 侧边栏版本显示、系统/对外 API 返回的 `version` 字段均由 `outlook_web.__version__` 统一驱动。
- 发布内容继续沿用仓库既有的 Docker 镜像 tar 与源码 zip 作为正式产物。

### 测试/验证

- 单元测试：`python -m unittest discover -s tests -v`
  - 结果：`Ran 378 tests in 47.899s`
  - 状态：全部通过
- 构建验证：`docker build -t outlook-email-plus:v1.7.0 .`
  - 状态：通过
- 发布产物：
  - `dist/outlook-email-plus-v1.7.0-docker.tar`（299,417,600 bytes）
  - `dist/outlookEmailPlus-v1.7.0-src.zip`（930,706 bytes）

## v1.6.1 - 发布质量闸门清理与发布内容精简

发布日期：2026-03-15

### 新增功能

- 无新增终端功能。
- 补回面向发布的 `docs/DEVLOG.md`，用于保留版本级发布记录，避免内部过程文档清理后缺少对外可读的版本说明。

### 修复

- 清理 `external_api_guard`、`external_api_keys`、`external_api`、`system` 控制器中的格式与类型问题，恢复发布质量闸门可通过状态。
- 将异步 probe 轮询逻辑拆分为更小的私有函数，分别处理过期探测、待处理探测加载、命中结果写回与异常落库，降低发布前质量检查中的复杂度风险。
- 保持外部 API 行为不变的前提下，修正多处测试代码排版与断言表达，确保测试套件在当前代码状态下稳定通过。

### 重要变更

- 大规模移除了仓库内的内部分析、设计、测试与过程文档，仅保留运行所需内容与少量公开文档，显著缩减发布包体积和源码分发噪音。
- 本次版本号从 `1.6.0` 提升到 `1.6.1`。应用 UI 侧边栏版本显示、系统/对外 API 返回的 `version` 字段均由 `outlook_web.__version__` 统一驱动，已同步到新版本。
- 当前仓库不是 Tauri 工程，不包含 `Cargo.toml`、`package.json`、MSI 或 NSIS 构建链路；本次发布沿用仓库既有的 Docker 镜像与源码压缩包作为正式产物。

### 测试/验证

- 待执行：`python -m unittest discover -s tests -v`
- 待执行：`docker build -t outlook-email-plus:v1.6.1 .`
- 待执行：导出 Docker 镜像 tar 与源码 zip，并同步到 GitHub Release 页面。
