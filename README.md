# Outlook Email Plus

[English](./README.en.md) · [发布流程](./RELEASE.md)

OutlookMail Plus 是一款面向个人与团队的注册邮箱管理器。

与市面上通用型邮箱客户端不同，它更聚焦在**注册与验证**场景，并围绕注册流程做了深度优化。

### 为什么是 OutlookMail Plus

- **专为注册而生**：尽量减少注册流程中不必要的操作。你可以一键复制邮箱地址；在注册页发送验证邮件后，回到管理器点击“验证码”，即可自动拉取最新验证邮件，并用正则快速提取验证码或验证链接，尽量减少等待。
- **更轻、更专注**：舍弃发件等非核心能力，界面更清爽，所有设计都围绕“把注册跑通”。
- **导入兼容更广**：支持主流邮箱导入（Gmail、QQ、163 等），也支持自定义 IMAP 服务器。即使是自建邮箱也能使用；内置 CF Worker 临时邮箱，支持多域配置与 Admin Key 加密，大幅降低注册场景的隐私泄露风险。
- **支持自动化**：对外提供接口，支持批量自动化注册流程；邮箱池支持 `project_key` 项目隔离领取。对于长期邮箱，在领取阶段显式传入 `project_key + caller_id + task_id` 时，同项目成功账号不会被重复分配，`claim-complete(result=success)` 后会直接回到 `available`，并可被其他项目立即复用；临时邮箱 / `cloudflare_temp_mail` 继续沿用旧语义。获取接码与释放邮箱等能力一应俱全。
- **第三方通知**：支持第三方渠道通知，当前已接入 Telegram；重点邮箱收到邮件可自动推送提醒。

简而言之，OutlookMail Plus 是一款为“注册流程”打造的邮箱管理器。

## 演示站点

演示站点：https://demo.outlookmailplus.tech/
登录密码：`12345678`

站点内置 10 个邮箱账号用于演示，数据会定期重置。请勿删除演示账号或将其用于个人用途。

演示涵盖本项目的主要功能（Telegram 推送因需要额外配置，演示站未启用）。




## 界面预览

当前仓库已包含部分截图，后续将继续补充更多演示图片。

![仪表盘](img/仪表盘.png)
![邮箱界面](img/邮箱界面.png)
![提取验证码](img/提取验证码.png)
![设置界面](img/设置界面.png)


## 版本亮点

当前稳定版本：`v2.2.2`

### 近期版本速览

| 版本 | 日期 | 核心新功能 |
|------|------|-----------|
| **v2.2.0** | 2026-04 | 🔌 **临时邮箱 Provider 插件化**：支持第三方插件动态安装/卸载/配置，内置 Cloudflare / Custom / GPTMail / Moemail，Provider 设置与域名选择解耦；浏览器扩展新增本地个人信息生成器与完整 Jest 测试覆盖 |
| **v2.1.0** | 2026-04 | 📊 **数据概览大盘**：5 Tab 统一看板（总览 / 验证码提取 / 对外 API / 邮箱池 / 系统活动），新增 `verification_extract_logs` 统一观测链路，并修复浏览器扩展 API Key 复制与 overview i18n/实时刷新问题 |
| **v2.0.0** | 2026-04 | 🌐 **浏览器扩展**（Chrome/Edge MV3）：一键申领邮箱 → 自动提取验证码/链接 → 完成/释放，无需切换标签页；后端新增 `chrome-extension://` CORS 跨域支持 |
| **v1.19.0** | 2026-04 | 🔧 刷新失败提示结构化增强（错误码 + 可执行步骤 + trace 反馈指引）；Selected 账号刷新提前失败修复（Issue #45） |
| **v1.18.0** | 2026-04 | 🔄 邮箱池**项目成功复用**：显式携带 `project_key + caller_id + task_id` 时，success 后直接回到 `available`，支持跨项目立即复用（DB v22）|
| **v1.17.0** | 2026-04 | 🪝 **Webhook 通知通道**：全局单 URL 配置，与 Email/Telegram 并存；X-API-Key 随机生成快捷入口 |
| **v1.16.0** | 2026-04 | 🔑 OAuth Token 工具升级：新增"获取授权链接"模式，稳定支持跨环境授权 |
| **v1.15.0** | 2026-04 | 🤖 **AI 验证码增强**：系统级 AI fallback（双低置信才触发），固定 JSON 契约；**邮箱别名**（`+tag`）自动识别与回溯 |
| **v1.13.0** | 2026-04 | ⚡ **一键热更新**：Watchtower（推荐）和 Docker API 双模式，自动检测新版本弹出提示 |
| **v1.11.0** | 2026-04 | 🏊 **邮箱池项目隔离**（`project_key`）；CF Worker 多域 + Admin Key 加密；前端账号列表分页；统一轮询引擎 |
| **v1.9.0** | 2026-03 | 🌐 **双语界面**（中/英）；统一通知分发（Email + Telegram）；演示站点登录密码保护 |

---

### v2.1.0 — 数据概览大盘与观测增强

- 新增 5 Tab 数据概览大盘，替换旧 dashboard
- 新增 `verification_extract_logs`，统一观测普通账号 / 临时邮箱 / external API 提取链路
- 修复浏览器扩展“API 无效”的真实根因：复制脱敏 API Key 与 external pool / pool_access 前置条件认知偏差
- overview 前端补齐实时重拉与完整 i18n，页头 / Tab / hover note / timeline 现与主体卡片保持一致

### v2.0.0 — 浏览器扩展（新）

`browser-extension/` 目录包含 Chrome/Edge Manifest V3 扩展，详见 [浏览器扩展](#浏览器扩展) 章节。

### v1.15.0–v1.16.0 — OAuth Token 获取工具

- 新增独立 Token 工具窗口，以**兼容账号导入模式**获取 Microsoft refresh token
- 当前模式固定面向个人 Microsoft 账号：Public Client、`tenant=consumers`、不支持 `client_secret`
- Azure 应用注册的 **Supported account types** 应选择 **Accounts in any identity provider or organizational directory and personal Microsoft accounts**；仅组织目录会报 `unauthorized_client`，而 **Personal Microsoft accounts only** 会在写入前 `/common` 验证阶段报 `AADSTS9002331`
- 如果 Azure 门户在切换 Supported account types 时提示 `Property api.requestedAccessTokenVersion is invalid`，请到 **Manifest** 中把 `api.requestedAccessTokenVersion` 改为 `2`
- 如果已经开启 Public Client 仍然报"必须包含 `client_secret`"，说明当前回调仍被 Azure 视为机密 Web 客户端；此时应改用 **Mobile and desktop applications** 平台的 public redirect（如 `http://localhost`），并在工具里走手动粘贴回调 URL
- 如果遇到 `AADSTS70000`（scope 未授权/失效），优先检查"授权时 scope"和"验证时 scope"是否一致，并重新执行一次 **强制 Consent** 授权
- Graph 场景建议最小权限：**offline_access + Mail.Read + User.Read**；如需 IMAP 再额外补 **Office 365 Exchange Online → IMAP.AccessAsUser.All**
- 支持 Graph / IMAP Scope 预设、错误引导、JWT audience/scope 诊断；前端默认推荐 **Graph 邮件预设**（后端环境变量 fallback 保持 IMAP 兼容 Scope）
- 页面内置 Azure 应用注册快速指引折叠卡片（5 步）与教程入口：<https://real-caption-6d1.notion.site/OutlooKMailplus-token-344463aed7e680099380dc324ecdf1c9?source=copy_link>
- 支持一键写入已有 Outlook 账号或创建新账号，写入前自动验证 refresh token，并拒绝不兼容配置

### v1.13.0 — 一键更新

- 支持两种更新方式：Watchtower（推荐）和 Docker API 自更新（高级）
- 自动检测 GitHub 最新版本，界面弹出更新提示
- 完整的部署信息检测：镜像标签、本地构建、Watchtower 连通性等
- Watchtower 已是最新版本智能检测（基于 Watchtower 同步行为）
- Docker API 模式 digest 预检查，相同版本不触发无效更新

### v1.11.0 — 邮箱池 & 前端增强

- **邮箱池项目隔离**：`project_key` 防止同项目重复领取（DB v17）
- **CF Worker 临时邮箱多域支持**：设置页配置多个域名，"同步域名"按钮一键刷新
- **Admin Key 加密存储**：`cf_worker_admin_key` 以 `enc:` 前缀加密写入数据库（DB v18）
- **账号列表前端分页**：每页 50 条，大量账号时列表加载更流畅
- **统一轮询引擎**：标准模式与简洁模式合并为单一 `poll-engine`，修复竞态与状态积压

## 核心能力

- 多邮箱账号管理
  支持 Outlook OAuth、普通 IMAP 邮箱和 CF Worker 临时邮箱（多域配置，Admin Key 加密存储）
- 批量导入与分组整理
  支持批量导入、标签、搜索、分组、导出
- 邮件读取与提取
  支持验证码、链接、原文内容读取
- 邮箱池调度
  支持可领取、释放、完成、冷却恢复、过期回收等状态流转；长期邮箱支持 `project_key` 项目维度成功复用：同项目按 success 记录防重复领取，`success` 后回到 `available`，跨项目可立即复用；未传 `project_key` 与 `provider=cloudflare_temp_mail` / 临时邮箱继续保持旧语义；`claim-random` 仍支持池空时动态创建 CF 邮箱
- 受控对外接口
  支持 `X-API-Key` 鉴权、多调用方 Key 管理、邮箱范围授权、IP 白名单和速率限制
- 通知能力
  支持业务邮件通知、Telegram 推送和测试发送
- 演示站点保护
  可通过环境变量锁定登录密码修改入口，避免访客在设置页改后台密码

## 项目结构

```text
outlook_web/          Flask 应用主体（controllers / routes / services / repositories）
templates/            页面模板
static/               前端脚本与样式
data/                 SQLite 数据与运行时文件
tests/                自动化测试
web_outlook_app.py    兼容入口
```

## 快速开始

### Docker 部署

**方式一：docker run（快速体验）**

```bash
docker run -d \
  --name outlook-email-plus \
  -p 5000:5000 \
  -v $(pwd)/data:/app/data \
  -e SECRET_KEY=your-secret-key-here \
  -e LOGIN_PASSWORD=your-login-password \
  -e ALLOW_LOGIN_PASSWORD_CHANGE=false \
  guangshanshui/outlook-email-plus:latest
```

**方式二：docker-compose（推荐，含一键更新）**

保存以下内容为 `docker-compose.yml`，然后运行 `docker-compose up -d`：

```yaml
services:
  app:
    image: ghcr.io/zeropointsix/outlook-email-plus:latest   # 推荐（国内网络稳定）
    # image: guangshanshui/outlook-email-plus:latest         # Docker Hub 备选
    container_name: outlook-email-plus
    restart: unless-stopped
    ports:
      - "5001:5000"           # 可改为 5000:5000 或其他端口
    env_file:
      - .env
    environment:
      SECRET_KEY: "${SECRET_KEY:?请在 .env 中设置 SECRET_KEY}"
      # 一键更新 Token：留空即可直接使用内置默认值；生产环境建议设为随机强密码
      WATCHTOWER_HTTP_API_TOKEN: "${WATCHTOWER_HTTP_API_TOKEN:-outlook-mail-plus-watchtower-default}"
      # Docker API 自更新（可选，高级功能）
      # ⚠️ 启用后容器可通过 Docker API 控制宿主机其他容器，存在安全风险
      # DOCKER_SELF_UPDATE_ALLOW: "false"
    volumes:
      - ./data:/app/data
      # Docker socket 挂载（可选，仅用于 Docker API 自更新功能）
      # ⚠️ 挂载 docker.sock 会授予容器完全的 Docker API 访问权限，请谨慎使用
      # - /var/run/docker.sock:/var/run/docker.sock
    labels:
      - "com.centurylinklabs.watchtower.enable=true"
    networks:
      - outlook-net

  watchtower:
    image: containrrr/watchtower
    container_name: watchtower
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      # 与上方 app 服务保持一致；留空时两边同步使用内置默认值，无需手动对齐
      - WATCHTOWER_HTTP_API_TOKEN=${WATCHTOWER_HTTP_API_TOKEN:-outlook-mail-plus-watchtower-default}
      - WATCHTOWER_HTTP_API_UPDATE=true
      - WATCHTOWER_CLEANUP=true
      - WATCHTOWER_HTTP_API_PERIODIC_POLLS=false
    command: --http-api-update --label-enable
    labels:
      - "com.centurylinklabs.watchtower.enable=false"
    networks:
      - outlook-net

networks:
  outlook-net:
    driver: bridge
```

说明：

- 建议始终挂载 `data/`，避免数据库与运行数据丢失
- `SECRET_KEY` 必须稳定且足够强，建议随机64位：`python -c "import secrets; print(secrets.token_hex(32))"`
- `WATCHTOWER_HTTP_API_TOKEN` **可留空**，留空时 app 和 watchtower 自动使用同一内置默认值，部署后一键更新即可使用
- 配置好后，当有新版本时系统界面会自动弹出更新提示，点击"立即更新"即可完成升级
- 一键更新功能**仅在 docker-compose 部署方式下有效**；`docker run` 单容器模式不支持

**更新方式**：默认使用 Watchtower（推荐）。如需使用 Docker API 自更新（无需 Watchtower），需在 `docker-compose.yml` 中：
1. 取消 `DOCKER_SELF_UPDATE_ALLOW` 注释并设为 `"true"`
2. 取消 docker.sock 挂载注释
3. 在设置页选择"更新方式"为"Docker API"
4. ⚠️ 请充分了解安全风险后再启用

#### ClawCloud / 反向代理部署注意事项

- 健康检查请显式使用 `GET /healthz`，不要依赖 `/`、`/login` 或 302 跳转链路；本项目首页 `/` 受登录保护，会重定向到 `/login`
- `no healthy upstream` 表示反向代理当前没有健康后端，不等于应用一定是“代码崩溃”；更新后若持续出现，优先查看**新容器启动日志**与平台事件
- 若平台事件出现 `Stopping container`、`FailedKillPod`、`KillPodSandbox DeadlineExceeded`，说明故障至少包含平台侧 Pod 停止/回收异常，不能只根据应用日志下结论
- 本项目默认使用 SQLite + 持久卷，更新时建议保持**单实例**；若新旧实例短时并发访问同一数据库文件，启动阶段的迁移或文件锁等待可能导致健康检查超时
- `TEMP_EMAIL_UPSTREAM_READ_FAILED` 与 `no healthy upstream` 需要分开理解：前者是临时邮箱上游读取失败，后者是入口层前面没有健康应用实例

### 本地运行

```bash
python -m venv .venv
pip install -r requirements.txt
python web_outlook_app.py
```

### 运行测试

```bash
python -m unittest discover -s tests -v
```

## 常用环境变量

- `SECRET_KEY`
  会话与敏感字段加密密钥，必须配置
- `LOGIN_PASSWORD`
  初始后台登录密码，首次启动后会写入数据库并哈希存储
- `ALLOW_LOGIN_PASSWORD_CHANGE`
  是否允许在设置页修改登录密码。演示站点建议设为 `false`
- `DATABASE_PATH`
  SQLite 数据库路径，默认 `data/outlook_accounts.db`
- `PORT` / `HOST`
  Web 服务监听地址
- `SCHEDULER_AUTOSTART`
  是否自动启动后台调度器
- `OAUTH_TOOL_ENABLED`
  是否启用 OAuth Token 获取工具入口与相关 API，默认 `true`
- `OAUTH_CLIENT_ID`
  Outlook OAuth 应用 ID
- `OAUTH_CLIENT_SECRET`
  兼容导入模式下应保持为空；如 Azure 应用依赖 `client_secret`，则不属于当前支持范围
- `OAUTH_REDIRECT_URI`
  Outlook OAuth 回调地址
- `OAUTH_SCOPE`
  后端环境变量默认 Scope（fallback），默认 `offline_access https://outlook.office.com/IMAP.AccessAsUser.All`；前端首次展示默认 Graph 预设
- `OAUTH_TENANT`
  Token 工具默认 Tenant，固定兼容模式 `consumers`
- `GPTMAIL_BASE_URL`
  GPTMail 服务地址
- `GPTMAIL_API_KEY`
  GPTMail API Key，用于临时邮箱能力
- `CF_WORKER_BASE_URL`（设置页对应 `cf_worker_base_url`）
  Cloudflare Temp Email Worker 地址
- `CF_WORKER_ADMIN_KEY`（设置页对应 `cf_worker_admin_key`）
  Cloudflare Worker Admin 密码；建议仅通过设置页保存，系统会加密存储

### 一键更新相关

- `WATCHTOWER_HTTP_API_TOKEN`
  Watchtower API 鉴权令牌。**可留空**，留空时 app 和 watchtower 两边自动使用同一内置默认值，开箱即用；生产环境建议设置随机强密码
- `WATCHTOWER_API_URL`
  Watchtower API 地址，默认 `http://watchtower:8080`（Docker 内部网络，通常无需修改）
- `DOCKER_SELF_UPDATE_ALLOW`
  是否启用 Docker API 自更新功能，默认 `false`。⚠️ 启用后容器可访问 Docker API，存在安全风险
- `DOCKER_IMAGE`
  当前容器镜像名（可选，用于部署信息检测）

> **安全提示**：Docker API 自更新需要挂载 `/var/run/docker.sock`，这会授予容器完全的 Docker API 访问权限。生产环境建议使用 Watchtower 方式。

## 通知能力说明

### 邮件通知

如果你准备启用“邮件通知”，需要额外配置 SMTP。邮件通知与 Telegram、GPTMail 是独立链路，不能互相替代。

最少需要配置：

- `EMAIL_NOTIFICATION_SMTP_HOST`
- `EMAIL_NOTIFICATION_FROM`

常见可选配置：

- `EMAIL_NOTIFICATION_SMTP_PORT`
- `EMAIL_NOTIFICATION_SMTP_USERNAME`
- `EMAIL_NOTIFICATION_SMTP_PASSWORD`
- `EMAIL_NOTIFICATION_SMTP_USE_TLS`
- `EMAIL_NOTIFICATION_SMTP_USE_SSL`
- `EMAIL_NOTIFICATION_SMTP_TIMEOUT`

示例：

```env
EMAIL_NOTIFICATION_SMTP_HOST=smtp.qq.com
EMAIL_NOTIFICATION_SMTP_PORT=465
EMAIL_NOTIFICATION_FROM=your_account@qq.com
EMAIL_NOTIFICATION_SMTP_USERNAME=your_account@qq.com
EMAIL_NOTIFICATION_SMTP_PASSWORD=your_smtp_auth_code
EMAIL_NOTIFICATION_SMTP_USE_SSL=true
EMAIL_NOTIFICATION_SMTP_USE_TLS=false
EMAIL_NOTIFICATION_SMTP_TIMEOUT=15
```

注意：

- 设置页中的测试邮件遵循“先保存，再测试”
- 测试接口不会直接读取输入框临时值
- 系统只会读取已保存的 `email_notification_recipient`

### Telegram 推送

项目支持在设置页配置：

- `telegram_bot_token`
- `telegram_chat_id`
- `telegram_poll_interval`

当前版本中，Telegram 推送与业务邮件通知已经统一接入通知分发链路。

## 外部接口与邮箱池集成

如果你要把本项目接入注册机、脚本平台或其他自动化系统，当前推荐方式是受控外部接口：

- 路径前缀：`/api/external/*`
- 鉴权头：`X-API-Key`
- 邮箱池接口：`/api/external/pool/*`

当前外部接口支持：

- 单 Key 鉴权
- 多 Key 配置
- 按调用方限制邮箱范围
- 公网模式白名单与速率限制
- 可禁用原文读取、长轮询等高风险端点

注意：

- 旧匿名 `/api/pool/*` 已移除
- 生产环境建议开启受控公网模式并配置白名单

## 浏览器扩展

`browser-extension/` 目录包含配套的 Chrome / Edge 扩展（Manifest V3），提供「申领邮箱 → 获取验证码/链接 → 完成/释放」一站式快捷面板，无需切换标签页。

详细说明见 [browser-extension/README.md](./browser-extension/README.md)。

### 项目 Key（Project Key）

项目 Key 用于**邮箱池的多租户隔离**：不同业务/项目的申领互不干扰，配合 `caller_id + task_id` 还能在同项目内防止重复分配。

- **不填**：从公共邮箱池随机申领
- **填写**：只在该项目的邮箱中申领；`success` 完成后邮箱立即回到 `available`，可被其他项目复用

### 完成 vs 释放

完成和释放都会结束当前任务，区别在于邮箱的后续状态：

| 操作 | 邮箱状态 | 适用场景 |
|------|---------|---------|
| **释放（Release）** | → `available`（立即可再申领） | 注册失败、误领、测试归还 |
| **完成（Complete）** | → `used`（已用，默认不再分配） | 注册成功、验证码已使用 |

> 启用项目复用时，`complete(result=success)` + 显式 `project_key` 路径会直接回到 `available`，支持跨项目立即复用。

## 演示站点建议

如果你要公开一个演示站点给其他人访问，建议至少这样配置：

```env
LOGIN_PASSWORD=your-strong-password
ALLOW_LOGIN_PASSWORD_CHANGE=false
```

- 站点仍然可以登录
- 访客无法在“系统设置”里改掉后台登录密码



## 项目文档

- [注册与邮箱池接口文档](./注册与邮箱池接口文档.md)
- [Registration Worker and Mail Pool API](./registration-mail-pool-api.en.md)
- [临时邮箱 Provider 插件接入说明](./临时邮箱Provider插件接入说明.md)
- [临时邮箱 Provider 插件接入提示词](./临时邮箱Provider插件接入提示词.md)

如果你要对接注册机或批量工作流，优先看邮箱池和外部接口文档。

如果你要新增一个临时邮箱 Provider 插件，优先看上面的「插件接入说明」与「插件接入提示词」。

## 致谢

本项目基于以下技术与服务能力构建：

- Flask
- SQLite
- Microsoft Graph API
- IMAP
- APScheduler

  
 外部友链：https://linux.do/


也参考了以下项目的思路：

- [assast/outlookEmail](https://github.com/assast/outlookEmail)
- [gblaowang-i/MailAggregator_Pro](https://github.com/gblaowang-i/MailAggregator_Pro)

## 许可证

Apache License 2.0

## 联系方式

如果你在使用过程中遇到问题，或有合作意向，欢迎通过邮件联系：[outlookmailplus@163.com](mailto:outlookmailplus@163.com)

