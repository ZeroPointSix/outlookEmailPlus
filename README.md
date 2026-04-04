# Outlook Email Plus


[English](./README.en.md)

OutlookMail Plus 是一款面向个人与团队的注册邮箱管理器。

与市面上通用型邮箱客户端不同，它更聚焦在**注册与验证**场景，并围绕注册流程做了深度优化。

### 为什么是 OutlookMail Plus

- **专为注册而生**：尽量减少注册流程中不必要的操作。你可以一键复制邮箱地址；在注册页发送验证邮件后，回到管理器点击“验证码”，即可自动拉取最新验证邮件，并用正则快速提取验证码或验证链接，尽量减少等待。
- **更轻、更专注**：舍弃发件等非核心能力，界面更清爽，所有设计都围绕“把注册跑通”。
- **导入兼容更广**：支持主流邮箱导入（Gmail、QQ、163 等），也支持自定义 IMAP 服务器。即使是自建邮箱也能使用；内置 CF Worker 临时邮箱，支持多域配置与 Admin Key 加密，大幅降低注册场景的隐私泄露风险。
- **支持自动化**：对外提供接口，支持批量自动化注册流程；邮箱池支持项目隔离策略，同一项目内已使用的邮箱不会被重复分配，获取接码与释放邮箱等能力一应俱全。
- **第三方通知**：支持第三方渠道通知，当前已接入 Telegram；重点邮箱收到邮件可自动推送提醒。

简而言之，OutlookMail Plus 是一款为“注册流程”打造的邮箱管理器。

## 演示站点
演示站点：https://gbcoinystsyz.ap-southeast-1.clawcloudrun.com
登录密码：12345678

实际上我提供了10个邮箱账号作为演示使用，不建议某些人单独尝试删除，我会定时把这个账号的内容信息上传，不建议自己使用，除非你想要让它对你造成不良影响

基本都涵盖了本项目的所有功能（除了邮件推送，纸飞机推送需要具体的配置没有添加）




## 界面预览

当前仓库已包含部分截图，后续将继续补充更多演示图片。

![仪表盘](img/仪表盘.png)
![邮箱界面](img/邮箱界面.png)
![提取验证码](img/提取验证码.png)
![设置界面](img/设置界面.png)


## 最近更新

重点包括：

- 当前稳定版本：`v1.11.0`

**邮箱池增强**
- 项目隔离领取策略（PR#27）：`claim-random` 支持传入 `project_key`，同一 `caller_id + project_key` 下已使用的账号不重复领取（DB v17）

**CF Worker 临时邮箱**
- 多域支持：可在设置页配置多个 CF Worker 域名，新增"同步域名"按钮一键刷新域名列表
- Admin Key 加密存储：`cf_worker_admin_key` 以 `enc:` 前缀加密写入数据库，不再明文存储（DB v18）

**前端体验修复**
- BUG-06：生成或删除临时邮箱后，列表中已选中邮箱的高亮状态得到正确保留
- BUG-07：临时邮箱面板刷新邮件列表后，域名下拉选择不再被重置
- Issue #24：修复邮件展开/激活状态在重渲染后丢失、i18n 语言切换后账号列表不刷新、视口高度链路断裂等问题

**轮询引擎重构**
- 将标准模式和简洁模式的双轮询系统合并为统一的 `poll-engine`（4 阶段重构）
- 修复初始加载时批量邮件请求、分组切换重复启动轮询、跨视图轮询状态积压等问题

**账号列表**
- 新增前端分页（每页 50 条），大量账号时列表加载更流畅

**i18n**
- 临时邮箱面板域名提示文字、CF Worker 域名同步按钮新增中英双语翻译

## 核心能力

- 多邮箱账号管理
  支持 Outlook OAuth、普通 IMAP 邮箱和 CF Worker 临时邮箱（多域配置，Admin Key 加密存储）
- 批量导入与分组整理
  支持批量导入、标签、搜索、分组、导出
- 邮件读取与提取
  支持验证码、链接、原文内容读取
- 邮箱池调度
  支持可领取、释放、完成、冷却恢复、过期回收等状态流转；支持 `project_key` 项目隔离，同项目内已用邮箱不重复分配
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

```bash
docker pull guangshanshui/outlook-email-plus:v1.11.0
docker pull guangshanshui/outlook-email-plus:latest

docker run -d \
  --name outlook-email-plus \
  -p 5000:5000 \
  -v $(pwd)/data:/app/data \
  -e SECRET_KEY=your-secret-key-here \
  -e LOGIN_PASSWORD=your-login-password \
  -e ALLOW_LOGIN_PASSWORD_CHANGE=false \
  guangshanshui/outlook-email-plus:v1.11.0
```

说明：

- 建议始终挂载 `data/`，避免数据库与运行数据丢失
- `SECRET_KEY` 必须稳定且足够强，建议随机64位
- 生产环境建议优先固定到明确版本标签，例如 `v1.11.0`；`latest` 更适合快速体验

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
- `OAUTH_CLIENT_ID`
  Outlook OAuth 应用 ID
- `OAUTH_REDIRECT_URI`
  Outlook OAuth 回调地址
- `GPTMAIL_BASE_URL`
  GPTMail 服务地址
- `GPTMAIL_API_KEY`
  GPTMail API Key，用于临时邮箱能力

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

如果你要对接注册机或批量工作流，优先看邮箱池和外部接口文档。

## 致谢

本项目基于以下技术与服务能力构建：

- Flask
- SQLite
- Microsoft Graph API
- IMAP
- APScheduler

也参考了以下项目的思路：

- [assast/outlookEmail](https://github.com/assast/outlookEmail)
- [gblaowang-i/MailAggregator_Pro](https://github.com/gblaowang-i/MailAggregator_Pro)

## 许可证

Apache License 2.0
