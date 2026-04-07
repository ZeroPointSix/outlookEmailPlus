# 一键更新功能 — BUG/现象记录与解决方案

> 版本: v1.0 | 日期: 2026-04-07
> 状态: 待实施

---

## 前后端架构变化

### 新增 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/system/version-check` | GET | 检查 GitHub 最新版本 |
| `/api/system/trigger-update` | POST | 触发一键更新（Watchtower/Docker API） |
| `/api/system/test-watchtower` | POST | 测试 Watchtower 连通性 |

### 新增设置项

| 设置键 | 说明 | 存储方式 |
|--------|------|----------|
| `watchtower_url` | Watchtower API 地址 | 明文 |
| `watchtower_token` | Watchtower API Token | 加密存储 |

### 前端新增函数

| 函数 | 说明 |
|------|------|
| `checkVersionUpdate()` | 页面加载时检查版本更新 |
| `triggerUpdate()` | 触发一键更新 |
| `waitForRestart()` | 轮询等待容器重启 |
| `testWatchtower()` | 测试 Watchtower 连通性 |
| `dismissVersionBanner()` | 关闭更新提示横幅 |

### 数据流

```
版本检测:
  页面加载 → GET /api/system/version-check → 对比本地 vs GitHub
  → has_update=true → 显示橙色 Banner

一键更新:
  用户点击"立即更新" → POST /api/system/trigger-update
  → 后端读取 watchtower_url/token（数据库优先，环境变量回退）
  → POST {watchtower_url}/v1/update → Watchtower 拉取镜像+重建容器
  → 前端轮询 /healthz (3s间隔，最多90s) → 页面刷新

设置保存:
  PUT /api/settings → watchtower_url 明文存储
  PUT /api/settings → watchtower_token 加密存储（encrypt_data）
  GET /api/settings → watchtower_token 脱敏返回（****xxxx）

配置优先级:
  watchtower_url: 数据库 > 环境变量 WATCHTOWER_API_URL > 默认 http://watchtower:8080
  watchtower_token: 数据库 > 环境变量 WATCHTOWER_HTTP_API_TOKEN
```

### UI 变化

设置 → 自动化 Tab 新增：
- 📬 Telegram 通知（已有）
- 🔄 一键更新 (Watchtower)（新增）
  - Watchtower API 地址输入框
  - Watchtower API Token 输入框
  - 测试连通性按钮

顶部更新 Banner（已有，修复 GitHub 地址后生效）：
- 发现新版本时显示橙色横幅
- 包含版本号、更新日志链接、立即更新按钮、忽略按钮

---

## BUG-001: 固定版本标签时 Watchtower 不会更新

### 现象
当 docker-compose.yml 中使用固定版本标签（如 `image: xxx:v1.12.0`）时，Watchtower 只检查该标签的 digest。新版本使用不同标签推送时不会触发更新。

### 影响
用户使用固定版本标签部署时，一键更新功能失效。

### 解决方案
- 设置页面自动检测当前容器的镜像标签
- 如果是固定版本标签（非 latest），在 UI 上提示建议使用 latest 标签
- README 和 docker-compose 示例中默认使用 latest 标签

### 涉及文件
- `static/js/main.js` — 添加镜像标签检测逻辑
- `templates/index.html` — 更新方式提示 UI

---

## BUG-002: 固定 digest 时 Watchtower 不会更新

### 现象
当使用 `image: xxx@sha256:xxx` 方式指定镜像时，Watchtower 对比 digest 永远相同，不会触发更新。

### 影响
用户通过 digest 锁定镜像时，一键更新功能完全失效。

### 解决方案
- 与 BUG-001 合并处理，在 UI 上统一提示
- 如果检测到 digest 模式，提示改为标签模式

---

## BUG-003: Watchtower Token 为空时启动即退出

### 现象
环境变量 WATCHTOWER_HTTP_API_TOKEN 未设置时，Watchtower 容器启动后立即 fatal 退出。

Watchtower 日志:
```
level=fatal msg="api token is empty or has not been set. exiting"
```

### 影响
用户忘记配置 Token 时，Watchtower 无法运行，一键更新不可用。

### 解决方案
- .env.example 中提供 WATCHTOWER_HTTP_API_TOKEN 模板和说明
- docker-compose.yml 中提供 Token 默认值
- 设置页面 Watchtower 配置区域增加首次配置引导
- 应用启动时检测 Watchtower 是否在线，如果不可达则在 UI 上显示配置引导

### 涉及文件
- `.env.example` — 添加 Token 模板
- `docker-compose.yml` — Token 默认值
- `templates/index.html` — 配置引导提示

---

## BUG-004: 本地构建镜像无法被 Watchtower 更新

### 现象
使用 `build: .` + `image: outlook-email-dev:latest` 本地构建时，镜像不存在于 Docker Hub，Watchtower 无法拉取更新。

### 影响
开发环境无法使用一键更新功能。

### 解决方案
- docker-compose.yml 注释中已有说明
- 设置页面检测是否为本地构建镜像，如果是则提示需要使用远程镜像部署

### 涉及文件
- `templates/index.html` — 检测提示

---

## BUG-005: Docker 内部网络地址用户难以理解

### 现象
应用通过 `http://watchtower:8080` 访问 Watchtower。这是 Docker 内部网络地址，用户可能不理解。

### 影响
用户配置时可能填错地址，导致连接失败。

### 解决方案
- Watchtower URL 输入框默认值设为 `http://watchtower:8080`
- placeholder 和 help 文本说明这是 Docker 内部地址
- 测试连通性失败时，提示检查两个容器是否在同一 Docker 网络中

### 涉及文件
- `templates/index.html` — 默认值和帮助文本
- `outlook_web/controllers/system.py` — 改善错误提示

---

## BUG-006: GitHub 仓库地址曾配置错误（已修复）

### 现象
版本检测 API 中的 GitHub 仓库地址为 `hshaokang/outlookemail-plus`（不存在），导致 API 返回 404 后降级为"无更新"。

### 解决方案（已实施）
改为 `ZeroPointSix/outlookEmailPlus`，已提交 `e6d27b6`。

---

## BUG-007: 版本更新后浏览器缓存旧 JS 文件

### 现象
容器更新后，浏览器可能使用缓存的旧 JS 文件，导致 UI 行为异常。

### 解决方案
- 静态文件 URL 添加版本号参数（如 `main.js?v=1.12.0`）
- 在 HTML 模板中使用版本号变量
- 设置 Cache-Control 头部

### 涉及文件
- `templates/index.html` — 添加版本号参数
- `outlook_web/app.py` — Cache-Control 头部

---

## 改进-001: 内置 Docker API 自更新（方案 A）

### 背景
当前一键更新依赖 Watchtower 外部容器，用户需要额外部署。增加内置 Docker API 自更新可简化部署。

### 解决方案
- 新增 `outlook_web/services/docker_update.py` 封装 Docker API 操作
- 扩展 `api_trigger_update()` 支持 method 参数（watchtower / docker_api）
- 设置页面添加"更新方式"选择
- docker-compose.yml 添加 docker.sock 挂载（可选，需用户显式启用）
- 安全考虑: 默认关闭，需 DOCKER_SELF_UPDATE_ALLOW=true 启用

### 涉及文件
- `outlook_web/services/docker_update.py` — 新建
- `outlook_web/controllers/system.py` — 扩展
- `outlook_web/controllers/settings.py` — 新增配置
- `static/js/main.js` — 前端逻辑
- `templates/index.html` — UI
- `docker-compose.yml` — docker.sock
- `requirements.txt` — docker SDK

### 实施优先级
Phase 3（在 BUG 修复和设置页面完善之后）

---

## 实施顺序

| 优先级 | 编号 | 内容 | 状态 |
|--------|------|------|------|
| P0 | BUG-006 | GitHub 仓库地址修复 | 已修复 |
| P1 | BUG-003 | Watchtower Token 为空启动失败 | 待实施 |
| P1 | BUG-007 | 浏览器缓存旧 JS | 待实施 |
| P2 | BUG-001/002/004/005 | UI 提示优化 | 待实施 |
| P3 | 改进-001 | Docker API 自更新 | 待实施 |
