# DEVLOG

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
