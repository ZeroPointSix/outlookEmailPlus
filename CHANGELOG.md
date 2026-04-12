# Changelog

All notable changes to OutlookMail Plus are documented in this file.

## [Unreleased]

（暂无）

## [v1.15.1] - 2026-04-12

### 新增功能

- 无新增业务功能。

### 修复

- 修复 CI 格式化门禁失败：对仓库代码执行 `black` / `isort` 全量对齐，消除 `Code Quality` 与 `docker-build-push` 前置 `quality-gate` 阻断。
- 恢复主干构建发布链路：`Build and Push Docker Image` 在 `main` 分支重新通过，镜像推送流程恢复稳定。

### 重要变更

- 版本号由 `1.15.0` 升级至 `1.15.1`，用于补齐“版本标签镜像”发布链路，与已修复的主干 CI 状态保持一致。

### 测试/验证

- 本地格式化校验：
  - `python -m black --check outlook_web tests web_outlook_app.py outlook_mail_reader.py start.py` ✅
  - `python -m isort --check-only --profile black outlook_web tests web_outlook_app.py outlook_mail_reader.py start.py` ✅
- 本地回归抽检：
  - `python -m pytest -q tests/test_version_update.py tests/test_i18n_settings_completeness.py` → `71 passed`
- 远端 CI（`main` / commit `61208e0`）全绿：
  - `Build and Push Docker Image` ✅
  - `Code Quality` ✅
  - `Python Tests` ✅
  - `SonarCloud Scan` ✅
- `v1.15.1` tag 发布链路验证：
  - `Create GitHub Release` ✅
  - `Build and Push Docker Image`（tag）✅
- 仓库镜像一致性核对（GHCR / Docker Hub）：
  - `v1.15.1` 与 `v1.15.1-d09d67f` digest 一致：`sha256:4b1985478bb0f2c0fdf1ec6ef705ee62858919a886c7a8c79acd880ac45dd964`
  - `main` / `main-d09d67f` / `latest` digest 一致：`sha256:a409244bf43a7f2e921d86f4977eeced462942d589b66d57982f1ed8eb930a9f`

## [v1.15.0] - 2026-04-12

### 新增功能

- **验证码提取链路重构（Web + External）**：统一验证码提取路径，补齐 repository 层 token 持久化职责边界，减少渠道切换下的状态漂移。
- **系统级验证码 AI 配置闭环**：`GET/PUT /api/settings` 承载 `verification_ai_enabled/base_url/api_key/model`，支持 API Key 加密存储与脱敏回显。
- **验证码 AI 可用性探测接口**：新增 `POST /api/settings/verification-ai-test`，基于已保存配置返回结构化探测结果（`ok/error/message/latency_ms/http_status/parsed_output`）。
- **固定 JSON 契约**：引入 `verification_ai_v1` 输入/输出契约与服务端结构校验，降低模型返回漂移风险。

### 修复

- 修复 `ACCOUNT_AUTH_EXPIRED` 误报：仅在所有可用通道都无法认证/读取时返回该错误。
- 修复验证码提取未命中语义：当有通道读取成功但未提取到验证码时统一返回 `VERIFICATION_NOT_FOUND`。
- 修复本地直启环境一致性：`web_outlook_app.py` 自动加载 `.env`，避免 `SECRET_KEY` 缺失导致的凭据解密失败。
- 修复邮件通知测试链路 587/465 传输模式冲突：端口驱动规范化（587 强制 STARTTLS、465 强制 SSL）。
- 修复设置页 i18n 缺失映射：补齐“基础设置 / 验证码 AI 增强区 / 测试 AI 配置”等多处中英映射并新增回归测试。

### 重要变更

- **AI fallback 触发条件收紧（方案 A）**：由“code/link 任一低置信即触发 AI”调整为“仅当 code 与 link 均 low 时触发 AI”，减少不必要 AI 调用。
- **分层配置口径收敛**：分组策略仅保留规则项（`verification_code_length`、`verification_code_regex`），运行期 AI 配置统一收敛到系统设置。
- **版本升级**：应用版本由 `1.13.0` 升级为 `1.15.0`（由 `outlook_web.__version__` 统一驱动 UI 与 API 版本展示）。

### 测试/验证

- 全量回归（分片执行，等价覆盖全量）：
  - `python -m pytest -q tests/test_[a-m]*.py` → `441 passed, 2 skipped`（188.91s）
  - `python -m pytest -q tests/test_[n-z]*.py` → `597 passed, 7 skipped`（112.16s）
  - 合计：`1038 passed, 9 skipped`（301.07s）
- 版本更新回归：`python -m pytest -q tests/test_version_update.py` → `51 passed`
- 设置页 i18n 完整性回归：`python -m pytest -q tests/test_i18n_settings_completeness.py` → `20 passed`
- 验证码提取链路优化基准：对比历史基线平均耗时有稳定下降，长尾场景已收敛但仍持续观察。

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
