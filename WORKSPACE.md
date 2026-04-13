# WORKSPACE — 工作区操作记录

> 本文档记录项目开发过程中的操作日志，按日期倒序排列。

---

## 2026-04-13

### 操作记录

#### 44. main 对齐 alias 合并结果并完成分批全量 unittest 验证

**时间**：2026-04-13

**本次操作**：

1. 分支与合并状态对齐
   - 在 `main` 先执行本地文档改动暂存：`git stash push -u -m "pre-alias-merge-main-docs"`
   - `git pull --ff-only origin main` 后，`main` 快进到 `67f3ea4`，该提交已包含 PR #41（`alias-email-merge`）的 merge commit
   - 结论：邮箱别名功能代码已在 `main` 分支可见并可测试

2. 全量测试执行（受 300000ms 单命令上限，改为分批）
   - `python -m unittest discover -s tests -v -p "test_[a-f]*.py"` → `Ran 346 tests in 178.563s`，`OK`
   - `python -m unittest discover -s tests -v -p "test_[g-l]*.py"` → `Ran 89 tests in 11.477s`，`OK`
   - `python -m unittest discover -s tests -v -p "test_[m-r]*.py"` → `Ran 226 tests in 36.681s`，`OK (skipped=7)`
   - `python -m unittest discover -s tests -v -p "test_[s-z]*.py"` → `Ran 472 tests in 83.833s`，`OK`
   - 汇总：`Ran 1133 tests`，`OK`，`skipped=7`

3. 文档恢复与冲突处理
   - 按用户确认的方案 B 恢复 `main` 的 3 个无关文档改动（`README.md`、`README.en.md`、`WORKSPACE.md`）
   - `git stash pop` 时 `WORKSPACE.md` 发生冲突，已改为手工合并，保留：
     - ClawCloud 排障记录（43/42）
     - 邮箱别名实现记录（41）
     - 本次 main 合并与测试记录（44）

4. 当前结论
   - 邮箱别名能力已在 `main`；全量 unittest 分批回归通过
   - 当前工作区仅剩文档变更，待统一提交与推送

---

#### 43. 联网比对公开案例并收敛平台侧共性

**时间**：2026-04-13

**本次操作**：

1. 联网检索方向
   - 检索 `KillPodSandbox` / `FailedKillPod` / `DeadlineExceeded`
   - 检索 Caddy / 反向代理健康检查与 upstream 全部 unhealthy 的公开案例

2. 命中案例
   - Kubernetes issue `kubernetes/kubernetes#126681`
   - Caddy issue `caddyserver/caddy#7544`
   - Caddy issue `caddyserver/caddy#7524`

3. 共性结论
   - `Stopping container` + `KillPodSandbox DeadlineExceeded` 在公网案例中常与 Pod 终止异常、容器运行时状态不一致、探针持续失败同时出现
   - 即使健康端点人工访问正常，反向代理的 active health check 仍可能把所有 upstream 长时间判为 unhealthy
   - 因此本次 `no healthy upstream` 不能简单理解为应用代码崩溃，更符合“平台侧容器生命周期异常 + 健康实例判定失败”的组合问题

4. 对当前案例的影响
   - 继续优先从 ClawCloud 平台事件、实例切换、健康检查路径与策略入手
   - 不把临时邮箱上游 502 作为入口层故障的直接根因

---

#### 42. 收敛 ClawCloud 故障处理方向并补记执行约束

**时间**：2026-04-13

**本次操作**：

1. 新增平台侧证据
   - 用户补充 ClawCloud / 容器事件：`Successfully assigned ...`
   - 用户补充容器停止事件：`Stopping container mail`
   - 用户补充回收异常：`FailedKillPod`、`KillPodSandbox DeadlineExceeded`

2. 解决方向收敛
   - 当前优先判断为平台侧容器生命周期 / 健康实例切换问题
   - 后续解决重点放在健康检查路径、单实例更新策略、以及新实例启动日志
   - 不再把 `TEMP_EMAIL_UPSTREAM_READ_FAILED` 作为 `no healthy upstream` 的直接根因

3. 执行约束补记
   - 后续如需启动长时间命令，仅使用新进程后台启动（如 `Start-Process` / 独立进程）
   - 不再使用前台长命令占住执行链路
   - 继续通过 MCP `寸止` 输出会话信息，不在终端直接对话

---

#### 41. 邮箱别名（+ 子地址）自动识别与无缝迁移测试补齐

**时间**：2026-04-13

**本次操作**：

1. 在干净分支上实现邮箱别名回溯能力
   - 新增 `normalize_alias_email(email_addr)`：将 `user+tag@domain` 规范化为 `user@domain`
   - 在 `resolve_mailbox()` 入口统一接入 normalize
   - 在 `controllers/emails.py` 入口补齐 normalize：
     - `_parse_external_common_args()`
     - `api_get_emails()`
     - `api_get_email_detail()`

2. 测试补齐（专属迁移场景）
   - 新增 `tests/test_email_alias_normalize.py`
   - 新增 `tests/test_email_alias_flow.py`
   - 新增 `tests/test_email_alias_migration_compat.py`
   - 补充 `tests/test_mailbox_resolver.py`：`test_resolve_mailbox_supports_plus_alias_lookup`

3. 回归结果
   - `python -m unittest tests.test_email_alias_normalize tests.test_mailbox_resolver tests.test_email_alias_flow tests.test_email_alias_migration_compat -v`
   - 结果：`Ran 20 tests in 7.103s`，`OK`

4. 文档同步
   - `CHANGELOG.md`（v1.15.0）补充邮箱别名能力与测试覆盖说明

---

#### 40. 统一同步其他分支到 main（本地 + 远端）

**时间**：2026-04-13

**本次操作**：

1. 同步目标
   - 将以下分支与 `main` 保持一致：
     - `Buggithubissue`
     - `dev`
     - `dev-5.3Codex`
     - `feature`

2. 执行方式（强一致）
   - 本地分支指针强制对齐到 `main`
   - 远端分支通过强制推送对齐到 `main`

3. 同步结果
   - 本地与远端对应分支均已对齐 `main`
   - 分支历史已收敛到同一主线提交

4. 风险说明
   - 该操作会覆盖上述分支原有分叉历史（按用户要求执行）
   - 未对 `main` 执行 force push

---

#### 39. 补齐 v1.16.0 标签镜像（重打 tag 到 CI 全绿提交）

**时间**：2026-04-13

**本次操作**：

1. 处理策略
   - 采用“重打同名 tag”的方式补齐 `v1.16.0` 版本镜像
   - 将 `v1.16.0` 从旧目标提交（`a7d1fb1`）迁移到 CI 全绿提交（`5d1f424`）

2. 执行步骤
   - 本地重置 tag：`git tag -fa v1.16.0 5d1f424 -m "v1.16.0 (retag for CI-green image publish)"`
   - 删除远端旧 tag：`git push origin :refs/tags/v1.16.0`
   - 推送新 tag：`git push origin v1.16.0`

3. 流水线结果
   - `Create GitHub Release`（run `24334384448`）✅ success
   - `Build and Push Docker Image`（run `24334384479`）✅ success
   - 产物镜像 digest（workflow 输出）：
     - `sha256:12e1fb01bf8d20e6c5aae4f3e89a0c34b335759d971f9e06363882b971c027d5`

4. digest 核对
   - GHCR `v1.16.0` / `v1.16.0-5d1f424` digest：
     - `sha256:12e1fb01bf8d20e6c5aae4f3e89a0c34b335759d971f9e06363882b971c027d5`
   - DockerHub `v1.16.0` / `v1.16.0-5d1f424` digest：
     - `sha256:12e1fb01bf8d20e6c5aae4f3e89a0c34b335759d971f9e06363882b971c027d5`

5. 结论
   - `v1.16.0` 标签镜像已补齐且 GHCR / DockerHub digest 一致 ✅

---

#### 38. 核对 GHCR / DockerHub 镜像 digest 一致性

**时间**：2026-04-13

**本次操作**：

1. 核对镜像标签可用性
   - `v1.16.0` 标签当前在 GHCR / DockerHub 均不存在（原因：该次 tag workflow 曾被 quality-gate 阻断）

2. 核对已成功推送的 main 链路镜像
   - 参考成功 workflow：`Build and Push Docker Image`（run `24333634813`）
   - 对比标签：`main`、`latest`、`main-5d1f424`

3. digest 对比结果
   - GHCR `main` digest：`sha256:1593096c384fc8b5dbec68045e18aebea0ec243893bb3cb398fb98b17429ad1c`
   - GHCR `latest` digest：`sha256:1593096c384fc8b5dbec68045e18aebea0ec243893bb3cb398fb98b17429ad1c`
   - GHCR `main-5d1f424` digest：`sha256:1593096c384fc8b5dbec68045e18aebea0ec243893bb3cb398fb98b17429ad1c`
   - DockerHub `main` digest：`sha256:1593096c384fc8b5dbec68045e18aebea0ec243893bb3cb398fb98b17429ad1c`
   - DockerHub `latest` digest：`sha256:1593096c384fc8b5dbec68045e18aebea0ec243893bb3cb398fb98b17429ad1c`
   - DockerHub `main-5d1f424` digest：`sha256:1593096c384fc8b5dbec68045e18aebea0ec243893bb3cb398fb98b17429ad1c`

4. 结论
   - GHCR 与 DockerHub 的 main 系列镜像 digest 完全一致 ✅
   - 如需补齐 `v1.16.0` 版本镜像标签，需要在质量门禁通过后重新触发 tag 构建链路。

---

#### 37. 修正 v1.16.0 Release 文案口径（产物状态）

**时间**：2026-04-13

**本次操作**：

1. 核对 Release 页面当前文案
   - 发现 `v1.16.0` Release 中仍保留“源码 zip 失败”旧描述

2. 更新 Release 正文
   - 使用 `gh release edit v1.16.0 --notes-file ...` 覆盖发布日志
   - 将“`outlookEmailPlus-v1.16.0-src.zip` 失败”修正为“成功”

3. 结果确认
   - Release 页面已更新：
     - `https://github.com/ZeroPointSix/outlookEmailPlus/releases/tag/v1.16.0`
   - 当前发布日志中的产物口径已与实际一致：Docker tar 与源码 zip 均为成功

---

#### 36. CI 修复结果复核（四项主工作流恢复全绿）

**时间**：2026-04-13

**本次操作**：

1. 推送格式化修复提交
   - commit: `5d1f424 chore(format): align release branch with black/isort quality gate`

2. 核对 main 最新 CI 运行结果
   - `Code Quality` ✅ success（run `24333634815`）
   - `Python Tests` ✅ success（run `24333634834`）
   - `Build and Push Docker Image` ✅ success（run `24333634813`）
   - `SonarCloud Scan` ✅ success（run `24333634798`）

3. 结论
   - v1.16.0 发布后因格式化导致的 quality-gate 阻断已解除
   - main 分支 CI/CD 主链路已恢复全绿

---

#### 35. 修复 v1.16.0 发布后的 CI 格式化门禁

**时间**：2026-04-13

**本次操作**：

1. 按 CI 失败日志执行格式化修复
   - 运行：`python -m black outlook_web tests web_outlook_app.py outlook_mail_reader.py start.py`
   - 结果：8 个文件被格式化（与 GitHub Actions 报告一致）
   - 运行：`python -m isort --profile black outlook_web tests web_outlook_app.py outlook_mail_reader.py start.py`

2. 本地质量门禁复核
   - `python -m black --check ...` ✅
   - `python -m isort --check-only --profile black ...` ✅

3. 回归测试
   - `python -m pytest tests/ -q` → `1109 passed, 9 skipped` ✅

4. 处理目标
   - 消除 `Code Quality` 的 `black --check` 失败根因
   - 解除 `Build and Push Docker Image` 因 quality-gate 阻断的问题

---

#### 34. v1.16.0 发布后 CI/CD 状态核对

**时间**：2026-04-13

**本次操作**：

1. 使用 GitHub CLI 核对最新工作流状态
   - 命令：`gh run list --limit 30`、`gh run view <run_id> --log-failed`

2. v1.16.0 对应流水线结论
   - `Create GitHub Release`（tag `v1.16.0`）✅ success
   - `Python Tests`（main）✅ success
   - `SonarCloud Scan`（main）✅ success
   - `Code Quality`（main）❌ failure
   - `Build and Push Docker Image`（main/tag）❌ failure（由 quality-gate 阻断）

3. 失败根因
   - `Code Quality` 中 `black --check` 未通过
   - 日志显示 8 个文件需格式化（含 `outlook_web/controllers/token_tool.py`、`outlook_web/services/oauth_tool.py`、`tests/test_version_update.py` 等）
   - `docker-build-push` 工作流前置 `quality-gate` 失败，因此镜像推送流程被阻断

4. 状态说明
   - 本地发布与 GitHub Release 已成功（tag、Release 文案、产物上传均完成）
   - 但 CI 质量门禁未全绿，需后续补格式化并再次推送以恢复 main/tag 镜像流水线

---

#### 33. v1.16.0 正式发布（GitHub Release + 产物上传）

**时间**：2026-04-13

**本次操作**：

1. 按发布流程执行版本发布
   - 创建并推送版本提交：`a7d1fb1 docs(release): prepare v1.16.0 version, changelog, and devlog`
   - 创建并推送 tag：`v1.16.0`
   - 推送分支：`git push origin main`（`8ae283f..a7d1fb1`）
   - 推送标签：`git push origin v1.16.0`

2. 发布门禁验证（测试）
   - `python -m pytest tests/test_version_update.py -q` → `51 passed`
   - `python -m pytest tests/test_oauth_tool.py -q` → `71 passed`
   - `python -m pytest tests/ -q` → `1109 passed, 9 skipped`

3. 发布产物构建
   - Docker 镜像构建：
     - `docker build -t outlook-email-plus:v1.16.0 .` ✅
     - image id: `sha256:b53839622bf256e3d6d8bd06ad06372e39b253a5e0555288780b0a6845aaf00c`
   - 产物导出：
     - `dist/outlook-email-plus-v1.16.0-docker.tar` ✅
     - `dist/outlookEmailPlus-v1.16.0-src.zip` ✅（最终通过 `git archive` 生成）
   - 说明：首次 `Compress-Archive` 方案因运行中数据库文件占用失败，已改用 `git archive` 稳定导出源码包。

4. GitHub Release 发布
   - 发现 `v1.16.0` Release 已存在（tag push 后自动创建）
   - 采用 `gh release edit` 更新完整发布日志
   - 采用 `gh release upload --clobber` 上传产物
   - 发布地址：
     - `https://github.com/ZeroPointSix/outlookEmailPlus/releases/tag/v1.16.0`

5. 发布内容结构
   - 已同步四段式发布说明：
     - 新增功能
     - 修复
     - 重要变更
     - 测试/验证

---

#### 32. v1.16.0 发布准备（版本更新 + 日志同步）

**时间**：2026-04-13

**本次操作**：

1. 读取发布规范与版本记录
   - 读取 `RELEASE.md`（确认本仓库发布产物为 Docker tar + 源码 zip，非 Tauri MSI/NSIS）
   - 读取 `docs/DEVLOG.md`（确认当前最新记录 `v1.15.1`）

2. 按发布流程更新版本号与版本展示
   - `outlook_web/__init__.py`：`1.15.0` → `1.16.0`
   - `tests/test_version_update.py`：版本断言 `1.16.0`
   - `README.md` / `README.en.md`：当前稳定版本更新为 `v1.16.0`

3. 同步发布记录
   - `CHANGELOG.md`：新增 `## [v1.16.0] - 2026-04-13`
     - 结构包含：新增功能 / 修复 / 重要变更 / 测试验证
   - `docs/DEVLOG.md`：新增 `v1.16.0` 版本记录

4. 工作区记录
   - 同步将本次发布准备步骤写入 `WORKSPACE.md`

---

#### 31. 更新 steering 文档与 CLAUDE.md（按当前代码架构同步）

**时间**：2026-04-13

**本次操作**：

1. 按“仅基于当前代码现状”重新核对项目架构信息
   - 核查入口与装配：`outlook_web/app.py`、`outlook_web/__init__.py`
   - 核查 DB 与 schema：`outlook_web/db.py`（`DB_SCHEMA_VERSION=21`）、实际库表清单（24 张）
   - 核查 OAuth 工具现状：
     - `outlook_web/routes/token_tool.py`
     - `outlook_web/controllers/token_tool.py`
     - `outlook_web/services/oauth_tool.py`
     - `templates/token_tool.html`
     - `static/js/features/token_tool.js`
   - 核查 CI/测试口径：
     - `.github/workflows/python-tests.yml`（CI 使用 unittest）
     - 本地全量实测命令：`python -m pytest tests/ -q`

2. 更新 `.kiro/steering`（仅改项目现状相关内容）
   - `project-overview.md`
     - 修正目录树中的 `config.py` 重复项
     - 更新测试文件数量口径（`test_*.py` 约 97，tests 下 Python 文件约 105）
     - 增补 OAuth 工具“获取授权链接”交互模式（替代自动弹窗）
     - 更新测试命令口径（本地 pytest、CI unittest）
   - `architecture.md`
     - OAuth Token 工具流程补充“前端展示授权链接 -> 用户手动打开/复制”
     - 架构结论补充“授权链接模式”的现状描述
   - `tech-stack.md`
     - 前端实现补充 Token 工具授权链接模式
     - 测试章节补充“本地 pytest / CI unittest”双口径

3. 更新项目根 `CLAUDE.md`
   - 常用命令区新增“本地全量回归（pytest）”
   - 保留“CI 同款 unittest”命令
   - OAuth 工具章节补充“获取授权链接 -> 手动粘贴回调 URL”流程

4. 执行边界
   - 本次仅更新：`.kiro/steering/*` + `CLAUDE.md` + `WORKSPACE.md`
   - 未改动其他业务代码与非目标文档

---

#### 30. OAuth Token 服务层修复 + main 全量回归验证

**时间**：2026-04-13

**本次操作**：

1. 检查 main 分支待提交内容
   - 发现 3 个业务文件改动：
     - `outlook_web/controllers/token_tool.py`
     - `outlook_web/routes/token_tool.py`
     - `outlook_web/services/oauth_tool.py`

2. 修复 `oauth_tool.py` 的语法问题
   - 问题：`get_oauth_flow()` 在 `with OAUTH_FLOW_LOCK:` 后缺少函数体，触发 `IndentationError`
   - 修复：补回逻辑：
     - `_prune_expired()`
     - `data = OAUTH_FLOW_STORE.get(state)`
     - `return dict(data) if data else None`
   - `py_compile` 语法检查通过：
     - `outlook_web/services/oauth_tool.py`
     - `outlook_web/controllers/token_tool.py`
     - `outlook_web/routes/token_tool.py`

3. main 分支全量回归测试（后台独立进程）
   - 启动方式：`Start-Process`（非前台阻塞）
   - 命令：`python -m pytest tests/ -q`
   - 结果：**1109 passed, 9 skipped** ✅
   - 耗时：327.27s
   - 备注：外层工具 300s 超时中断，但后台 pytest 实际已完成；以日志最终结果为准

4. 提交策略
   - 按用户确认：3 个业务文件采用**单个本地提交**
   - 同步更新 WORKSPACE 记录本次操作

---

#### 29. dev → main 合并 + 全量测试验证

**时间**：2026-04-13

**本次操作**：

1. dev 分支推送到远程
   - `git push origin dev` → `f4c16e9..7e93193`（8 commits）
   - 清理 dev 工作区临时诊断脚本（`_check_india*.py`、`_check_pwd.py` 等）

2. dev 合并到 main（仅本地，未推送远程）
   - 合并提交：`396e52d Merge branch 'dev' into main`
   - 解决 7 个冲突文件：
     - `outlook_web/__init__.py`：版本号 → `1.15.0`
     - `outlook_web/services/graph.py`：保留 `build_token_url()` + dev 格式化签名
     - `tests/test_version_update.py`：版本引用全部 → `1.15.0`
     - `CHANGELOG.md`、`README.md`、`README.en.md`、`WORKSPACE.md`：取 dev 版本

3. main 分支全量测试
   - `python -m pytest tests/ -q` → **1109 passed, 9 skipped** ✅
   - `python -m pytest tests/test_version_update.py -v` → 51 passed ✅
   - `python -m pytest tests/test_oauth_tool.py -v` → 71 passed ✅

4. 印度邮箱问题最终调查结论
   - 扫描所有数据库文件（12 个 `.db`），**无任何 `@outlook.in` 账户**
   - 主部署 DB 包含：`outlook.com`(20)、`qq.com`(1)、`gmail.com`(1)、`163.com`(1)、`126.com`(1)
   - 之前的 `ACCOUNT_CREDENTIAL_DECRYPT_FAILED` 确认是 **环境变量配错**（SECRET_KEY 不匹配），非区域问题
   - Git 历史中无 "India" / "outlook.in" 相关提交

**分支状态**：
- `main`：领先 origin/main 4 commits（未推送）
- `dev`：已推送到 origin ✅
- `Buggithubissue`：领先 origin 1 commit

**本地服务**：
- main 分支 PID 52780，`http://127.0.0.1:5000/login` HTTP 200 ✅（用户已测试确认正常）

---

#### 28. OAuth Token 工具 UI 简化 + 获取授权链接 + i18n 翻译

**时间**：2026-04-13

**本次操作**：

1. UI 简化
   - 删除整个「Azure 配置指引」折叠卡片（含 4 步配置说明 + 故障排查长文）
   - 删除 Client Secret 输入框（之前已 disabled）
   - 删除 Tenant 下拉框（之前固定 `consumers`）
   - 标题从「兼容账号 Token 导入工具」→「OAuth Token 工具」
   - 副标题改为简洁说明
   - CSS 清理不再使用的样式

2. 获取授权链接功能（替代自动弹窗）
   - 按钮从「登录 Microsoft」→「获取授权链接」
   - 新增 ② 授权链接展示区：readonly input + 「复制链接」「打开链接」按钮
   - `startOAuth()` 不再自动 `window.open()` 弹窗，改为展示链接供用户复制
   - 步骤编号更新：② 授权链接 → ③ 换取 Token → ④ 结果

3. i18n 翻译支持
   - `token_tool.html` 引入 `i18n.js`
   - `i18n.js` exactMap 新增约 50 条 token tool 中英翻译
   - `token_tool.js` 所有动态中文提示用 `t()` / `translateAppText()` 包装
   - 用户切换中/英后，页面静态文本自动翻译，动态提示也跟随

**修改文件**：
- `templates/token_tool.html`
- `static/js/features/token_tool.js`
- `static/css/token_tool.css`
- `static/js/i18n.js`
- `tests/test_oauth_tool.py`

**测试结果**：
- `python -m pytest tests/test_oauth_tool.py -v` → 71 passed
- `python -m pytest tests/ -q` → 1109 passed, 9 skipped

**本地服务**：
- PID 11436，`http://127.0.0.1:5000/login` HTTP 200

---

## 2026-04-12

### 操作记录

#### 27. 输出“微软云配置自动化提示词”文件，供其他 AI 直接执行云端配置

**时间**：2026-04-12

**本次操作**：
- 在项目目录新增：
  - `docs\\微软云配置自动化提示词.md`

**文件用途**：
- 让其他 AI 只处理微软云端配置
- 自动完成：
  - audience
  - public client
  - redirect URI
  - API permissions
- 明确声明：
  - personal account 的最终登录 / consent / refresh_token 获取仍需人工交互

**联动更新**：
- 已在 `docs\\OAuth-Token工具兼容导入踩坑总结.md` 中补上对这份提示词文件的引用
- 已同步更新会话 `plan.md` 与 `WORKSPACE.md`

#### 26. 评估“微软 CLI / API + AI 自动完成配置”的可行边界

**时间**：2026-04-12

**调研结论**：
- 可以自动化的部分：
  - App Registration 创建 / 更新
  - `signInAudience`
  - public redirect / public client 开关
  - API permissions 增删
  - 组织租户下的 admin consent（如适用）
- 不能完全自动化的部分：
  - personal Microsoft account 的首次交互式登录
  - delegated 权限的首次 consent
  - 最终 refresh_token 的实际颁发

**更现实的方案**：
- AI 负责 Azure 配置与差异检查
- 用户只做一次浏览器登录授权
- AI 再接管本地 token 校验、写入账号、错误诊断

**本次同步动作**：
- 已将这部分内容补入 `docs\\OAuth-Token工具兼容导入踩坑总结.md`
- 已同步更新会话 `plan.md` 与 `WORKSPACE.md`

#### 25. 输出会话专用踩坑总结文件，供后续写教程使用

**时间**：2026-04-12

**本次操作**：
- 按用户要求，最终将专用总结文件写入项目目录而非用户目录：
  - `E:\\hushaokang\\Data-code\\EnsoAi\\outlookEmail\\Buggithubissue\\docs\\OAuth-Token工具兼容导入踩坑总结.md`

**文件内容**：
- 最终跑通时的微软侧配置
- 当前项目兼容导入模式的真实约束
- 本次所有关键错误码与根因映射
- 已在项目中完成的收口
- 最终验证结果
- 后续写教程时建议强调的顺序

#### 24. 权限放开后，邮件拉取已成功；日志确认此前是“受众 + Scope + API permissions”三重叠加

**时间**：2026-04-12

**本次结果**：
- 用户确认已经在微软侧放开邮箱权限，并成功拉取邮件
- 日志显示：
  - `/api/token-tool/exchange` → `200`
  - `/api/token-tool/save` → `200`
  - `/api/emails/zerodotsix@outlook.com?...` → `200`

**从失败到成功的完整结论**：
- Graph 侧曾出现 `AADSTS9002331`：说明 Supported account types 不能收窄到 `PersonalMicrosoftAccount`
- IMAP 侧曾出现 `AADSTS70000`：说明旧 Graph 默认 Scope 残留或 IMAP 权限未放开
- Graph 侧还出现过 `ErrorAccessDenied`：说明邮箱读取权限本身也未完全放开

**最终踩坑总结**：
- 受众要用 `AzureADandPersonalMicrosoftAccount`
- 平台要走 Public Client / Mobile and desktop applications
- Scope 要切到 IMAP 预设并重新授权
- Azure API permissions 至少要补：
  - `Office 365 Exchange Online → IMAP.AccessAsUser.All`
- 如果还希望 Graph 链路也可用，再补：
  - `Microsoft Graph → Mail.Read`

**附带发现**：
- 日志里仍有一个独立问题：`/api/emails/.../extract-verification` 触发了 `AttributeError: 'str' object has no attribute 'get'`
- 这个 500 不影响本次邮件列表拉取成功，但属于后续可单独修复的旁路问题

#### 23. 按最新运行时诊断再次重启本地服务

**时间**：2026-04-12

**原因**：
- 在读取运行日志、修正保存失败引导与旧 Scope 兼容映射后，原服务进程仍停留在旧代码

**本次操作**：
- 停止了当前占用 5000 端口的旧进程
- 重新启动本地服务，新 PID `44800`
- 验证：`http://127.0.0.1:5000/login` 返回 `HTTP 200`

#### 22. 运行日志确认当前保存的 Scope 仍是旧 Graph 默认值

**时间**：2026-04-12

**日志与配置结论**：
- 运行日志显示：
  - Graph：`AADSTS9002331`（受众过窄，仍与 `/common` 冲突）
  - IMAP：`AADSTS70000`（scope 未授权 / 过期）
- 进一步读取当前工具配置后确认：
  - `oauth_tool_scope = offline_access https://graph.microsoft.com/.default`

**确认结论**：
- 当前 IMAP 失败不是“refresh_token 本身坏了”
- 更直接的原因是：用户这次授权仍在沿用旧的 Graph 默认 Scope，没有切回 IMAP 兼容预设
- 因此兼容导入模式下，需要：
  - 将受众切到 `AzureADandPersonalMicrosoftAccount`
  - 将 Scope 切回 IMAP 预设
  - 重新授权后再写入账号

**本次同步动作**：
- `get_config()` 现在会把历史遗留的 Graph 默认 Scope 自动映射回 IMAP 默认值，降低旧配置残留导致的重复踩坑概率
- 新增自动化用例覆盖这条“旧 Graph 默认 Scope → IMAP 默认值”的兼容映射
- 更新页面说明、README、会话 plan 和 `WORKSPACE.md`

**针对性回归**：
- `python -m pytest tests/test_oauth_tool.py -v -k "legacy_graph_scope or common_endpoint_guidance"` → `2 passed`

#### 21. `AADSTS9002331` 证明受众不能收窄到 PersonalMicrosoftAccount

**时间**：2026-04-12

**实际现象**：
- 授权已成功，用户进入“写入账号”弹窗
- 保存前 token 验证失败，错误为：
  - `AADSTS9002331`
  - `Application ... is configured for use by Microsoft Account users only. Please use the /consumers endpoint to serve this request.`

**确认结论**：
- 这说明兼容导入模式不能把应用受众收窄到 **PersonalMicrosoftAccount**
- 因为系统当前写入前验证与部分运行链路仍依赖 `/common`
- 因此与现有模型兼容的正确受众，应是：
  - **Accounts in any identity provider or organizational directory and personal Microsoft accounts**
  - 即 `AzureADandPersonalMicrosoftAccount`

**本次同步动作**：
- 更新 `save_to_account()` 的失败引导：遇到 `AADSTS9002331` 时，明确提示把 Supported account types 改为 `AzureADandPersonalMicrosoftAccount`
- 新增自动化用例覆盖该引导分支
- 更新页面说明、README、会话 plan 和 `WORKSPACE.md`，撤回此前“PersonalMicrosoftAccount 也可作为推荐选项”的过宽口径

**针对性回归**：
- `python -m pytest tests/test_oauth_tool.py -v -k "common_endpoint_guidance or invalid_client or unauthorized_client"` → `3 passed`

#### 20. 用户最新 manifest 已修正一半，剩余卡点集中在 Web 回调平台

**时间**：2026-04-12

**用户反馈的最新 manifest**：
- `allowPublicClient = true` ✅
- `signInAudience = "PersonalMicrosoftAccount"` ✅
- `accessTokenAcceptedVersion = 2` ✅
- 但 `replyUrlsWithType` 仍然只有：
  - `http://localhost:5000/token-tool/callback`（`type = "Web"`）

**字段级结论**：
- 这说明 audience / public-client 开关已经改对了一半
- 当前仍然不符合兼容导入模式的关键点，是**回调平台仍停留在 Web**
- 在这种情况下，Azure 继续把当前链路视为机密 Web 客户端、继续要求 `client_secret` 是符合现象的

**下一步建议**：
- 不再继续围绕 Web 回调调整
- 改用 **Mobile and desktop applications** 的 public redirect
- 若 Azure 门户允许，优先直接登记 `http://localhost:5000/token-tool/callback` 这类本地 callback URI；`http://localhost` 作为后备 public redirect
- 在工具里把 Redirect URI 改成相同值，并使用**手动粘贴回调 URL**完成 exchange

#### 19. `invalid_client` + “必须提供 client_secret” 反映的是平台类型错位

**时间**：2026-04-12

**实际现象**：
- 用户重新测试后收到：
  - `invalid_client`
  - `AADSTS70002: The provided request must include a 'client_secret' input parameter`

**当前判断**：
- 这不应再解读成“Client ID 无效或应用被删除”
- 更符合当前上下文的解释是：Azure 仍把当前 redirect/platform 视为**机密 Web 客户端**
- 也就是说，即使 audience、public client 开关已经调整过，只要还在走 Web 平台回调，Azure 仍可能继续要求 `client_secret`

**本次同步动作**：
- 更新 `oauth_tool.py` 的 `invalid_client` 引导文案，改成 public client / redirect 平台错位说明
- 更新 `templates/token_tool.html` 与 README：若仍被要求 `client_secret`，改用 **Mobile and desktop applications** 平台的 public redirect（如 `http://localhost`），并在工具里走手动粘贴回调 URL
- 将该结论写入会话 plan 与 `WORKSPACE.md`，作为后续人工测试的主诊断方向

**针对性回归**：
- `python -m pytest tests/test_oauth_tool.py -v -k "invalid_client or unauthorized_client"` → `2 passed`

#### 18. `ms-sso.copilot.microsoft.com/processcookie` 跳转属于浏览器侧干扰

**时间**：2026-04-12

**实际现象**：
- 用户登录 Microsoft 账号后，没有直接回到 Azure / 本地回调
- 浏览器跳到：
  - `ms-sso.copilot.microsoft.com/processcookie?...`
- 页面报错：
  - `ERR_CONNECTION_CLOSED`

**当前判断**：
- 这个域名不在我们应用的 OAuth 回调链路中
- 它更像是浏览器 / Copilot / Microsoft SSO 的 cookie 处理辅助跳转
- 因此这一步优先按**浏览器环境问题**处理，而不是继续修改本地代码或 Azure App Registration

**建议排查方向**：
- 使用无插件的隐身窗口 / Guest Profile / 另一浏览器重试
- 清理 `live.com`、`microsoftonline.com`、`copilot.microsoft.com` 相关 cookie
- 暂时关闭代理、VPN、杀软 HTTPS 检查、浏览器扩展后再试
- 若在新浏览器或新网络下恢复正常，可基本确认是本机浏览器环境干扰

#### 17. 基于用户提供的 Azure manifest 样本做字段级诊断

**时间**：2026-04-12

**用户提供的 manifest 关键信息**：
- `signInAudience = "PersonalMicrosoftAccount"` → 这一项已经对了
- `accessTokenAcceptedVersion = 2` → token 版本前置约束已经满足
- `allowPublicClient = null` → 兼容导入模式下应显式开启为 public client
- `replyUrlsWithType` 当前只有 `http://localhost:5000/token-tool/callback`

**字段级结论**：
- 需要重点改的是 **`allowPublicClient`**：应设为启用（Portal 中对应 `Allow public client flows = Yes`）
- Redirect URI 最好同时注册：
  - `http://127.0.0.1:5000/token-tool/callback`
  - `http://localhost:5000/token-tool/callback`
- `passwordCredentials` 可以保留，但当前兼容导入模式不会使用它
- IMAP 兼容链路建议通过 Portal 的 **API permissions** 补充 Exchange Online 的委托权限，而不是直接手改 manifest GUID

**本次同步动作**：
- 更新页面配置指引，明确本地建议同时注册 `127.0.0.1` 与 `localhost` 两个 Redirect URI
- 将 manifest 样本分析结果写入会话 plan 与 WORKSPACE，便于后续继续排查

#### 16. Azure 门户切换 consumers 时的 manifest 前置约束补充

**时间**：2026-04-12

**实际现象**：
- 用户在把应用切换为支持个人 Microsoft 账号时，Azure 门户报错：
  - `Property api.requestedAccessTokenVersion is invalid`

**确认结论**：
- 这是 Azure App Registration 的 manifest 约束，不是本地代码问题
- 当应用要支持个人 Microsoft 账号（`PersonalMicrosoftAccount` / `AzureADandPersonalMicrosoftAccount`）时，`api.requestedAccessTokenVersion` 必须为 `2`
- 正确处理顺序是：先到 **Manifest** 把 `api.requestedAccessTokenVersion` 改成 `2`，保存后再去切换 Supported account types

**本次同步动作**：
- 更新页面内 Azure 配置提示，补上 `requestedAccessTokenVersion=2` 的前置说明
- 更新 README / OAuth Tool 相关 PRD / FD / TD / TDD / TODO / 会话 plan，保证文档与当前实际限制一致

#### 15. 根据实际 `unauthorized_client` 结果补齐微软侧配置口径

**时间**：2026-04-12

**实际现象**：
- 在兼容账号导入模式下继续人工测试时，Microsoft 返回：
  - `unauthorized_client`
  - `The client does not exist or is not enabled for consumers`

**确认结论**：
- 当前模式不仅要求 `tenant=consumers`、Public Client、无 `client_secret`
- 还要求 Azure App Registration 的 **Supported account types 必须包含个人 Microsoft 账号**
- 如果应用只面向组织目录 / 单租户组织账号，即使前端和后端配置都改成兼容模式，授权前也会直接失败

**本次同步动作**：
- 更新 `oauth_tool.py` 的 `unauthorized_client` 引导文案：明确提示“支持个人 Microsoft 账号 + 开启公共客户端流”
- 更新 `templates/token_tool.html` 的 Azure 配置指引：显式写出 Supported account types 的可选项与禁区
- 更新 README / README.en 与 OAuth Tool 相关 PRD / FD / TD / TDD / TODO 顶部说明，使文档与这次真实报错保持一致

**针对性回归**：
- `python -m pytest tests/test_oauth_tool.py -v -k unauthorized_client` → `1 passed`

#### 14. OAuth Token 工具收口到兼容账号导入模式（专项 + 全量回归通过）

**时间**：2026-04-12

**本轮实现**：
- 前端页面与侧边栏入口统一改为“兼容账号 Token 导入”口径，Client Secret 改为禁用提示，Tenant 固定为 `consumers`
- `token_tool.js` 统一按兼容模式收集表单：`client_secret` 强制空字符串，`tenant` 强制 `consumers`，默认 Scope 切换到 IMAP 兼容预设
- `token_tool.py` 在 `prepare_oauth()`、`save_config()`、`save_to_account()` 增加兼容模式硬校验，直接拒绝非空 `client_secret` 与非 `consumers` tenant
- `graph.py` 与 `oauth_tool.py` 清理上一轮 tenant/client_secret-aware 临时链路，回到现有账号运行模型
- `tests/test_oauth_tool.py` 同步改为兼容模式口径：新增 prepare/config/save 的拒绝分支断言，配置返回固定空 `client_secret` 与 `consumers` tenant，并补充 IMAP 默认 Scope 断言

**当前判断**：
- Token 工具不再承诺“任意 Azure 应用上下文导入”，而是收敛为与现有购买账号同模型的导入入口
- 这轮改动用于在工具阶段就拦截不兼容账号，避免保存成功后才在运行态 `GRAPH_TOKEN_FAILED` / `IMAP_TOKEN_FAILED`

**专项回归**：
- `python -m pytest tests/test_oauth_tool.py -v` → `64 passed`

**全量回归**：
- `python -m pytest tests/ -v` → `994 passed, 10 skipped, 2 warnings`

**服务同步**：
- 已停止旧服务 PID `12592`
- 已按当前代码重启本地服务，新 PID `31192`
- `http://127.0.0.1:5000/login` 返回 `HTTP 200`

#### 15. OAuth Token 获取工具审查提示词（v1.0）

**时间**：2026-04-12

**问题背景**：
- 基于两轮代码审查经验，为 OAuth Token 获取工具编写专项审查提示词
- 目标：可交给其他 AI 对该功能实现进行独立审查

**产出**：
- `docs/DEV/oauth-token-review-prompt.md` — OAuth Token 功能专项审查提示词 v1.0
- 包含：全部 TD 函数签名/路由/配置表、6 项关键技术约束、八维度检查清单、TDD 13 类 59 用例映射
- 审查重点：功能实现正确性（TD 逐函数比对）+ 回归安全性（测试覆盖有效性）

---

#### 14. OAuth Token 获取工具第二轮代码审查（v1.15.0）

**时间**：2026-04-12

**问题背景**：
- 第一轮审查发现 3 条 Watch Items（均 LOW）
- 另一 AI 完成保守加固（Scope Chip DOM 创建 + client_secret 兼容策略）后进行第二轮审查

**审查范围**：
- 核心后端 6 + 前端 5 + 测试 1 + 发布/文档 7 = 19 个文件
- 八维度深度审查：TD/TDD 一致性、OAuth 安全链路、配置安全、账号写入链路、前后端契约、XSS/注入/泄露、测试覆盖、发布文档一致性

**审查结论**：
- **Must-Fix: 0 条**
- **Watch Items: 1 条（LOW）**：`exchange_token` 中 state 不匹配分支缺少直接单元测试
- **结论: Merge-Ready**

**验收数据**：
- `python -m pytest tests/test_oauth_tool.py -v` → `59 passed`
- `python -m pytest tests/ -v` → `989 passed, 10 skipped, 2 warnings`

**加固确认**：
- ✅ Scope Chip: `document.createElement()` + `data-scope` + 事件委托
- ✅ client_secret: 明文→直接返回 / `enc:` 正常→解密 / `enc:` 损坏→返回空串
- ✅ 新增 2 个专项测试覆盖上述加固

---

#### 13. OAuth Token 工具方向收敛：改为兼容账号导入模式（规划阶段）

**时间**：2026-04-12

**背景判断**：
- 通过人工测试确认：Token 工具虽然已能完成授权、换 token、保存前验证与账号写入，但“购买账号”运行模型与“用户自备 Azure 应用导入账号”并不是同一类型
- 现有运行态默认只表达 `client_id + refresh_token`，而用户自备 Azure 应用可能还要求 tenant / client_secret / 单租户上下文
- 继续在运行时对单租户 / 机密客户端逐点打补丁，会持续扩大复杂度并破坏旧模型稳定性

**本次规划结论**：
- 不再以“支持任意 Azure 应用导入”为目标
- 改为“**兼容账号导入模式**”：只允许导入与现有购买账号运行模型一致的账号
- 兼容模式口径暂定为：`tenant=consumers`、public client、无需 client_secret、不依赖账号级 tenant/secret 运行态上下文

**规划动作**：
- 已创建会话级 `plan.md`
- 已拆分后续收敛任务：前端收敛、后端硬校验、测试口径调整、文档统一、临时兼容逻辑清理
- 当前阶段仅完成方案收敛与计划编写，尚未开始按兼容模式改代码

**结论**：
- 后续实现方向从“扩运行态支持更多 OAuth 模型”转为“收缩 Token 工具输入边界，使导入账号与购买账号模型一致”
- 该方向更符合当前项目既有运行模型，也更利于控制复杂度

#### 12. OAuth Token 工具写入前 client_secret 校验链路修复

**时间**：2026-04-12

**问题背景**：
- 在 tenant-aware 修复之后，保存前 refresh token 校验继续报 `AADSTS7000218`
- 排查确认：保存接口虽然已经带上了 `tenant`，但验证请求仍然没有带 `client_secret`
- 对于机密客户端（confidential client），这会导致保存前验证阶段直接要求 `client_secret` / `client_assertion`

**本次修复**：

1. client_secret 贯通保存链路
   - `static/js/features/token_tool.js` 在保存 payload 中补充提交 `client_secret`
   - `outlook_web/controllers/token_tool.py` 在 `save_to_account()` 中接收 `client_secret`
   - 仅当实际有值时，才向底层验证函数传递 `client_secret`

2. 保存前验证支持机密客户端
   - `outlook_web/services/graph.py` 的 `test_refresh_token_with_rotation()` 增加可选 `client_secret`
   - 当页面已配置 secret 时，保存前 refresh token 校验将一并携带该 secret

3. 回归与运行态同步
   - `tests/test_oauth_tool.py` 新增 client-secret-aware 保存验证测试
   - `python -m pytest tests/test_oauth_tool.py -v` → `62 passed`
   - 本地服务已重启并确认 `http://127.0.0.1:5000/login` 返回 `HTTP 200`

**结论**：
- 机密客户端现在不会再因为保存前验证缺少 `client_secret` 而卡在 `AADSTS7000218`
- 当前人工测试环境已更新到最新代码，可继续刷新页面验证完整“获取 token → 写入账号”链路

#### 11. OAuth Token 工具写入前 tenant-aware 验证修复

**时间**：2026-04-12

**问题背景**：
- 人工测试中，Token 获取已经成功，但写入账号前的 refresh_token 验证报错：应用在目录 `Microsoft Accounts` 中不存在
- 排查确认：OAuth Tool 前面的授权链路按当前表单 Tenant 成功获取了 token，但保存前验证复用了 `graph.py` 里写死 `common` 的旧校验端点
- 对于单租户 Azure 应用，这会把本应在指定租户里验证的 token 错误地拿去 `common / Microsoft Accounts` 上验证，从而导致保存失败

**本次修复**：

1. tenant 贯通保存链路
   - `outlook_web/services/oauth_tool.py` 的 token 结果中补充返回 `tenant`
   - `static/js/features/token_tool.js` 在保存 payload 中补充提交 `tenant`
   - `outlook_web/controllers/token_tool.py` 在 `save_to_account()` 中接收 `tenant`

2. 保存前验证 tenant-aware
   - `outlook_web/services/graph.py` 新增按 tenant 生成 token 端点的能力
   - `test_refresh_token_with_rotation()` 增加可选 `tenant` 参数
   - 保存前验证不再固定走 `common`，而是按当前 OAuth 实际 tenant 发起 refresh token 校验

3. 回归与运行态同步
   - `tests/test_oauth_tool.py` 新增 tenant-aware 保存验证测试
   - `python -m pytest tests/test_oauth_tool.py -v` → `61 passed`
   - 本地服务已重启并加载最新代码，`http://127.0.0.1:5000/login` 返回 `HTTP 200`

**结论**：
- 单租户 Azure 应用现在不会再因为保存前验证错误落到 `Microsoft Accounts/common` 而写入失败
- 当前人工测试环境已切到最新代码，可继续刷新页面验证“获取 token → 写入账号”完整链路

#### 10. OAuth Token 工具写入账号弹窗错误可视化修复

**时间**：2026-04-12

**问题背景**：
- 人工测试中，OAuth Token 已成功获取，但点击“写入到账号 → 确认写入”后，界面看起来像“按钮没有反应”
- 通过运行中的服务日志确认，前端实际上已经多次请求 `POST /api/token-tool/save`，且后端返回 `400`
- 根因不是按钮失效，而是前端把错误提示输出到了弹窗外的主状态栏，用户在 modal 打开状态下看不到

**本次修复**：

1. 弹窗内错误反馈
   - 在 `templates/token_tool.html` 的保存弹窗中新增独立状态区
   - `static/js/features/token_tool.js` 新增弹窗级 `showSaveDialogStatus()` / `clearSaveDialogStatus()`
   - 保存校验失败、账号列表加载失败、保存接口返回错误时，统一在弹窗内直接展示提示

2. 样式与运行态同步
   - `static/css/token_tool.css` 增加弹窗状态区样式
   - 本地服务重启后再次确认 `http://127.0.0.1:5000/login` 返回 `HTTP 200`

**验收结果**：
- `python -m pytest tests/test_oauth_tool.py -v` → `60 passed`
- 本地服务已重启并加载最新前端代码

**结论**：
- 当前“确认写入像没反应”的表现已被修正为“错误直接在弹窗内可见”
- 后续若再出现写入失败，用户将能直接看到真实后端返回信息，方便继续定位业务原因

#### 9. OAuth Token 工具人工测试前回归与服务拉起

**时间**：2026-04-12

**本次操作**：

1. 全量回归确认
   - 再次执行 `python -m pytest tests/ -v`
   - 结果为 `990 passed, 10 skipped, 2 warnings`
   - warnings 仍是 `tests/test_live_credentials.py` 里既有的 `return bool` 提示，非本轮引入

2. 本地服务启动
   - 使用项目默认入口 `python start.py` 启动 Flask 服务
   - 通过 PowerShell `Start-Process` 挂起进程并保留 stdout/stderr 日志
   - 启动后确认服务监听 `127.0.0.1:5000`

3. 连通性检查
   - 对 `http://127.0.0.1:5000/login` 发起本地请求
   - 返回 `HTTP 200`，登录页 HTML 正常返回

**结论**：
- 当前代码已完成最新一轮全量回归
- 本地人工测试服务已成功拉起，可直接基于 `http://127.0.0.1:5000` 继续手工验证

#### 8. OAuth Token 获取工具审查后保守加固与二次回归（v1.15.0）

**时间**：2026-04-12

**问题背景**：
- 在 OAuth Token 工具主功能落地并通过初轮回归后，针对审查结果继续做一轮保守优化
- 本轮明确不改动 `save_to_account()` 的 TD 主路径，只处理不影响既有设计链路的安全性与兼容性项

**本次处理内容**：

1. 前端安全加固
   - `static/js/features/token_tool.js` 中的 Scope Chip 改为 `document.createElement()` 构建
   - 删除动态 scope 值拼接到 `onclick` 的做法，改为 `data-scope` + 容器事件委托

2. 配置兼容性明确化
   - `outlook_web/repositories/settings.py` 中的 `get_oauth_tool_client_secret()` 显式区分明文与 `enc:` 值
   - 历史明文配置直接返回；不可解密的加密值继续隐藏为空字符串，避免把损坏密文回显到页面

3. 测试与文档同步
   - `tests/test_oauth_tool.py` 新增 3 个回归用例（2 个配置读取 + 1 个 state mismatch 直接覆盖）
   - `CHANGELOG.md` 与 `WORKSPACE.md` 同步补充本轮审查后加固记录

**验收结果**：
- `python -m pytest tests/test_oauth_tool.py -v` → `60 passed`
- `python -m pytest tests/ -v` → `990 passed, 10 skipped, 2 warnings`
- warnings 仍来自 `tests/test_live_credentials.py` 中已有的 `return bool` 写法，非本轮引入

**结论**：
- OAuth Token 工具在不偏离 TD 主路径的前提下完成了一轮审查后保守加固
- 前端动态事件拼接风险已收敛，`client_secret` 配置读取策略也与当前实际行为保持一致

#### 1. OAuth Token 获取工具 PRD 编写（Issue #38, #34）

**时间**：2026-04-12

**问题背景**：
- Issue #38、#34 多位用户反馈需要内置 refresh_token 获取功能
- 旧版本该功能因设计复杂被废弃,但社区需求持续存在
- 旧版本内置 client_id 导致 unauthorized_client 报错（Issue #26, #20）

**讨论与决策**：

1. 方案评估
   - 方案 A: 深度集成 OAuth 页面 — 耦合度高,维护成本大
   - **方案 B: 松耦合集成**（✅ 采纳）— 独立 Blueprint 模块,可启用/禁用
   - 方案 C: 不内置,仅对接外部工具 — 体验割裂

2. 参考分析
   - 分析了博客文章「Python实现Microsoft邮件自动化：OAuth2.0认证与邮件处理详细指引」
   - 分析了 QuickMSToken 项目（somnifex/QuickMSToken）源码实现
   - 分析了现有代码库 token 刷新架构（graph.py、refresh.py）

3. 核心设计决策
   - 用户自备 client_id,不内置默认值
   - 支持 Authorization Code + PKCE 流程
   - 支持手动回调 URL 粘贴（兼容 Docker/反代部署）
   - 获取 token 后可一键写入系统账号

**产出文档**：
- `docs/PRD/2026-04-12-OAuth-Token获取工具PRD.md`

**补充内容（v1.1）**：
- 新增 2.6 节: Token 工具与现有导入功能的定位区分
- 新增 2.7 节: 8 种常见 OAuth 错误的中文提示与解决引导
- 扩展 7.2 节: Azure 应用注册指引改为分步骤详细说明（含直达链接）
- 新增 Tenant 租户选择器需求（consumers/common/organizations + 自定义）
- 更新 UI 布局图增加快速指引卡片和 Tenant 下拉
- 补充验收标准 A-07（Azure 指引）、A-08（多租户）

**结论**：
- PRD 已完成 v1.1 版,涵盖产品背景、核心需求、用例、错误引导、安全、部署兼容性等完整内容
- PRD 已在 FD 讨论后更新为 v1.2，补充页面形态决策和配置持久化策略

#### 2. OAuth Token 获取工具 FD 编写

**时间**：2026-04-12

**讨论与决策**：

1. 分析现有代码架构
   - Flask Blueprint 工厂模式（`create_blueprint()` + `add_url_rule()`）
   - 原生 JS SPA 前端（`navigate()` 页面切换）
   - `@login_required` Session 认证 + Flask-WTF CSRF
   - MVC 分层: routes → controllers → services → repositories

2. 分析 QuickMSToken 源码（app.py 731 行）
   - PKCE 生成: `secrets.token_urlsafe(64)` + SHA256
   - 内存 OAUTH_FLOW_STORE + 线程锁 + 20 分钟 TTL
   - 双模式: page 模式自动回调 + popup 模式手动粘贴
   - Scope 校验: 单资源限制、`.default` 混用检测
   - JWT 不验签解码（仅展示 audience/scope）

3. FD 关键设计决策
   - **页面形态**: 浏览器新窗口 `window.open()`（D1 方案）
   - **回调处理**: 智能回调,优先自动降级手动（Q2-A）
   - **结果传递**: 用户手动复制回调 URL 到主页面（Q3-A，QuickMSToken 方式）
   - **配置持久化**: 服务端 Settings 表,key 前缀 `oauth_tool_`（Q4-B）

4. 前后端模块设计
   - 后端: 新增 Blueprint `token_tool`（8 个路由）+ Controller + Service（`oauth_tool.py`）
   - 前端: 独立模板 `token_tool.html` + `token_tool.js` + `token_tool.css`
   - 回调页: `popup_result.html`（极简,仅显示复制提示或错误引导）

**产出文档**：
- `docs/FD/2026-04-12-OAuth-Token获取工具FD.md`
- `docs/PRD/2026-04-12-OAuth-Token获取工具PRD.md`（v1.2 更新）

**结论**：
- FD 已完成 v1.0,涵盖系统架构、数据流、接口设计、前端设计、安全设计、环境变量等完整内容
- 可直接进入开发阶段

#### 3. OAuth Token 获取工具 TD 编写

**时间**：2026-04-12

**代码库深度分析**：

1. 应用工厂与 Blueprint 注册
   - `app.py`: 12 个 Blueprint 无条件注册（lines 138-150），本期首例条件注册
   - Context Processor `inject_app_version()` 注入 `APP_VERSION`（lines 80-82）
   - CSRF 全局保护 `CSRFProtect`（line 109），部分 Blueprint 传入 `csrf_exempt`

2. 现有 Token 操作体系
   - `graph.py`: `TOKEN_URL_GRAPH` 使用 `/common/` 硬编码 tenant（line 11）
   - `get_access_token_graph_result()` 使用 `grant_type=refresh_token`（lines 46-106）
   - `test_refresh_token_with_rotation()` 返回 `(success, error, new_refresh_token)` 三元组（lines 255-293）
   - Token 工具将使用 `grant_type=authorization_code`，复用验证函数

3. 加密/配置/Settings 现状
   - `crypto.py`: `encrypt_data()` 使用 `enc:` 前缀标识 + Fernet 加密（lines 66-80）
   - `config.py`: `_getenv()` + `env_true()` 模式（lines 6-55）
   - `settings.py`: `get_setting()` / `set_setting()` + typed getter 模式（已有 CF Worker 先例）
   - `errors.py`: 已有 8 个 OAuth 相关错误码（lines 49-56, 95-102）

4. 账号管理
   - `accounts_repo.add_account()`: 自动 `encrypt_data(refresh_token)`（lines 157-236）
   - `accounts_repo.update_account()`: None 参数不覆盖现有值（lines 239-339）
   - DB Schema v19，本期无需升级

**核心技术决策**:

| 编号 | 决策 | 选定方案 | 理由 |
|------|------|---------|------|
| TD-01 | Schema 变更 | 无需升级（保持 v19） | Settings 表 INSERT OR REPLACE 自动处理，accounts 字段够用 |
| TD-02 | 配置读取 | settings.py 新增 getter 函数 | 与 CF Worker getter 模式一致，封装优先级链 |
| TD-03 | CSRF 策略 | 标准流程，不 exempt | 独立模板 Jinja2 注入 csrf_token，GET 请求天然不受 CSRF 保护 |
| TD-04 | FLOW_STORE 位置 | services/oauth_tool.py 内部 | 紧耦合于 OAuth 流程，Service 自包含模式 |
| TD-05 | Blueprint 注册 | 条件注册（env_true 模式） | 默认 OAUTH_TOOL_ENABLED=true，遵循 PRD 开箱即用要求 |

**产出文档**：
- `docs/TD/2026-04-12-OAuth-Token获取工具TD.md`

**结论**：
- TD 已完成 v1.0，涵盖代码级实现细节：config/settings/service/controller/routes/templates/JS 完整伪代码
- 11 个章节：文档目标、技术现状、核心决策、后端实现（7 个文件）、前端实现（4 个文件）、安全设计、错误处理、测试策略、实施计划（4 里程碑）、风险缓解、未来优化
- 与 FD 的区别：TD 精确到行号级代码引用、函数签名、变量命名、参数约束，可直接指导开发

#### 4. PRD/FD/TD 文档联调

**时间**：2026-04-12

**发现的问题与修复**：

1. **PRD 版本号不一致**（严重度: 中）
   - 问题: PRD 头部标记为 `v1.0`，但实际已经过两次更新（v1.1 补充, v1.2 FD 联动更新）
   - 修复: 更新为 `v1.3`（含本次联调修正）
   - 新增 FD/TD 关联文档引用

2. **PRD §4.4 与 FD/TD 的 client_secret 存储策略矛盾**（严重度: 高）
   - 问题: PRD 明确写 "❌ 不存储 client_secret 到数据库或文件"，但 FD §8.1 和 TD §3.1 设计为 Settings 表加密存储
   - 原因: FD 讨论阶段（Q4-B 决策）选定了服务端 Settings 表持久化方案，PRD 未同步更新
   - 修复: 删除 PRD §4.4 中该条约束，补充 v1.2 更新说明；同步更新 §5.1 安全表述

3. **TD save_to_account() 使用了错误的 update_account() 调用方式**（严重度: 高）
   - 问题: TD 伪代码传入 `email_addr=None, group_id=None, remark=None`，但 `update_account()` 要求这三个参数为必填（`str`/`int`/`str`），传 None 会触发 `if not email_addr → return False`
   - 修复: 改为先通过 `get_account_by_id()` 获取现有数据，将原字段回传，仅替换 `client_id`/`refresh_token`/`status`
   - 更新 Q1 说明，纠正 "None 值不覆盖" 的错误描述

4. **TD get_account_list() 调用了不存在的函数**（严重度: 高）
   - 问题: TD 使用 `accounts_repo.get_all_accounts()`，但 accounts.py 中该函数不存在
   - 实际函数: `accounts_repo.load_accounts()`（line 47，返回全部账号含解密字段）
   - 修复: 替换为 `load_accounts()`，补充安全说明（仅提取 4 个非敏感字段返回前端）

5. **FD §7.2/§7.3 与 TD 的配置引用方式不一致**（严重度: 中）
   - 问题: FD 使用 `from outlook_web.config import OAUTH_TOOL_ENABLED`（常量导入），TD 使用 `app_config.get_oauth_tool_enabled()`（函数调用）
   - 修复: FD 统一改为函数调用方式（因 config.py 定义的是函数而非常量）

6. **FD 缺少 TD 关联引用**（严重度: 低）
   - 修复: FD 头部新增 `关联 TD` 字段

**产出变更**：
- `docs/PRD/2026-04-12-OAuth-Token获取工具PRD.md` → v1.3（修复 #1, #2）
- `docs/FD/2026-04-12-OAuth-Token获取工具FD.md` → v1.0（修复 #5, #6，内容更新但版本号保持）
- `docs/TD/2026-04-12-OAuth-Token获取工具TD.md` → v1.1（修复 #3, #4）

**结论**：
- 三份文档间的术语、API 函数签名、配置引用方式已对齐
- 2 个高严重度 Bug（会导致运行时失败的伪代码错误）已修复
- PRD 中被 FD 设计阶段覆盖的约束已标注更新说明

#### 5. TDD 测试设计文档编写

**时间**：2026-04-12

**问题背景**：
- PRD/FD/TD 已完成并联调通过，需编写独立的 TDD（测试设计文档）指导实现阶段的测试编写
- TD §8 仅提供测试策略概要（单元 11 + 集成 9 = 20 个用例），需扩展为完整的测试设计

**讨论与决策**：

1. 文件组织方式
   - 方案 A: 两个文件（与 TD §8 原设计一致）
   - **方案 B: 一个文件**（✅ 采纳）— `tests/test_oauth_tool.py`，多 TestCase 分组
   - 方案 C: 三个文件（最细粒度）

2. 测试基础设施分析
   - 分析了 7 个现有测试文件的 fixture/mock/断言/命名模式
   - 分析了 errors.py、auth.py、graph.py、accounts.py 的完整函数签名
   - 确认项目使用 `unittest.TestCase` + `_import_app.py` 模式

**产出变更**：
- `docs/TDD/2026-04-12-OAuth-Token获取工具TDD.md` → v1.0（新建）
  - 11 个章节：文档目标、测试目标、测试原则、测试分层设计（13 个 TestCase 分组）、Mock 策略、测试数据、测试难点、前端手动验收、用例总表、执行命令、与 TD 差异说明
  - 自动化 47 个用例 + 手动验收 8 个场景 = 55 个测试点
  - 每个用例含用例 ID、场景描述、关键断言、伪代码
- `docs/TD/2026-04-12-OAuth-Token获取工具TD.md` → v1.2（更新 §8 测试策略）
  - 测试文件名由两个合并为一个（`test_oauth_tool.py`）
  - §8 增加 TDD 交叉引用
  - 头部新增关联 TDD 字段

**结论**：
- TDD 覆盖了 TD §8 的全部用例并扩展至 47 个自动化用例（原 20 个），增加了 PKCE 字符集、Scope 更多边界、FLOW_STORE 更细粒度、认证拦截、敏感数据过滤等边界场景
- 识别了 4 个测试难点并提供应对方案：FLOW_STORE 模块级变量隔离、Blueprint 条件注册时机、update_account 必填参数、requests.post Mock 路径

---

#### 6. TODO 任务拆分文档编写

**时间**：2026-04-12

**问题背景**：
- PRD/FD/TD/TDD 四份文档均已完成并联调通过
- 需编写 TODO 任务拆分文档，将 TD §9 的 4 个里程碑细化为可执行的开发任务

**讨论与决策**：

1. 分阶段结构（8 个 Phase）
   - Phase 0: 文档对齐收尾（修复 TDD URL 路径不一致问题）
   - Phase 1~2: 后端基础层 + Service 核心
   - Phase 3: Service 层 TDD 测试（先行）
   - Phase 4~5: 路由层 + API 集成测试
   - Phase 6: 前端实现
   - Phase 7: 联调与发布

2. TDD URL 路径修正
   - 发现 TDD 中所有 API 路径使用了 `/token-tool/api/*` 格式
   - TD 定义的路由为 `/api/token-tool/*` 格式
   - 已在编写 TODO 前统一修正 TDD 中约 20 处 URL 路径

**产出变更**：
- `docs/TODO/2026-04-12-OAuth-Token获取工具TODO.md` → v1.0（新建）

#### 7. OAuth Token 获取工具实现落地（v1.15.0）

**时间**：2026-04-12

**本次实现内容**：

1. 后端基础层
   - `outlook_web/config.py` 新增 6 个 OAuth Token 工具环境变量 getter
   - `outlook_web/repositories/settings.py` 新增 6 个 `oauth_tool_*` typed getter

2. OAuth Service 核心
   - 新增 `outlook_web/services/oauth_tool.py`
   - 完成 PKCE、Scope 校验、OAUTH_FLOW_STORE、错误引导、JWT payload 解码、authorization_code 换 token
   - 修正 Microsoft 错误解析：同时保留 `error` 与 `error_description`，保证引导映射稳定

3. 路由与控制器
   - 新增 `outlook_web/routes/token_tool.py` 与 `outlook_web/controllers/token_tool.py`
   - `app.py` 条件注册 Blueprint，并注入 `OAUTH_TOOL_ENABLED`
   - 按实现阶段确认结果，Controller 层统一增加动态开关检查，满足工具关闭时页面/API 一并返回 404

4. 测试
   - 新增 `tests/test_oauth_tool.py`
   - 覆盖 Service 29 个用例 + API 33 个用例，共 62 个自动化用例

5. 前端与发布信息
   - 新增独立页面 `token_tool.html`、回调页 `popup_result.html`
   - 新增 `static/js/features/token_tool.js`、`static/css/token_tool.css`
   - `templates/index.html` 侧边栏增加 Token 工具入口
   - 更新 `CHANGELOG.md`、`README.md`、`README.en.md`、`.env.example`、`docker-compose.yml`
   - 版本号提升到 `v1.15.0`
  - 8 个 Phase、43 个 Task
  - 每个 Task 含文件路径、位置、检查项
  - 包含依赖关系图、风险提醒表
  - 映射 TD §4/§5 完整伪代码和 TDD 55 个测试点
- `docs/TDD/2026-04-12-OAuth-Token获取工具TDD.md`（修正）
  - 约 20 处 API URL 路径从 `/token-tool/api/*` 修正为 `/api/token-tool/*`，与 TD §4.4 路由定义保持一致

**结论**：
- 所有开发文档（PRD/FD/TD/TDD/TODO）编写完成，形成完整的文档链路
- Issue #38 功能从需求分析到任务拆分的文档阶段全部完成
- 后续进入实现阶段时，按 TODO Phase 0~7 顺序执行

#### 7. 第二次文档联调（TODO 交叉审查）

**时间**：2026-04-12

**问题背景**：
- TODO v1.0 完成后，需要与 PRD/FD/TD/TDD 全部文档进行交叉一致性校验
- 确保 TODO 中所有函数名、返回类型、字段名、测试数量与权威文档（TD）完全一致

**审查发现（8 个不一致）**：

| 级别 | 编号 | 问题 | 影响文件 |
|------|------|------|---------|
| HIGH | H1 | TODO Phase 2 使用 6 个错误的 Service 函数名（如 `store_flow()` → `store_oauth_flow()`） | TODO |
| HIGH | H2 | `validate_scope()` 返回类型 `Optional[str]` → `Tuple[str, Optional[str]]` | TODO |
| HIGH | H3 | TDD §9 用例总数 24+23=47 → 实际 29+28=57（预存 bug） | TDD, TODO |
| MED | M4 | `get_account_list()` 返回字段 `email_addr, client_id` → `email, account_type` | TODO, TDD |
| MED | M5 | 删除不存在的 `save_oauth_tool_config()` 函数 | TODO |
| MED | M6 | 补充缺失的 `get_oauth_tool_prompt_consent()` getter | TODO |
| LOW | L7 | getter 命名 `get_oauth_tool_tenant_id()` → `get_oauth_tool_tenant()` | TODO |
| LOW | L8 | `render_page()` 动态开关检查描述修正（与 Task 4.6 统一） | TODO |

**产出变更**：
- `docs/TODO/2026-04-12-OAuth-Token获取工具TODO.md` → v1.1
  - 修复全部 8 个不一致问题
  - 更新版本头部引用 TDD v1.1
- `docs/TDD/2026-04-12-OAuth-Token获取工具TDD.md` → v1.1
  - §9 用例总数修正：24→29, 23→28, 47→57, 55→65
  - A-LIST-01 返回字段修正：`email_addr, client_id` → `email, account_type`
  - A-LIST-01 伪代码断言对齐 TD §4.5

**结论**：
- 五份文档（PRD/FD/TD/TDD/TODO）全部完成交叉一致性校验
- 所有函数名、返回类型、字段名与 TD（权威源）完全对齐
- 文档链路完整，可进入实现阶段

#### 8. 实现提示词编写 + 文档最终同步

**时间**：2026-04-12

**问题背景**：
- 用户需要一份自包含的实现提示词，供其他 AI 按文档严格执行开发
- 第二次联调修正后 TD §8 的测试计数仍沿用旧值，需同步

**操作内容**：

1. TD §8 测试计数同步
   - §8.1 标题 24 → 29、§8.2 标题 23 → 28、总计 47+8=55 → 57+8=65
   - TD 版本升级 v1.2 → v1.3
   - TODO 引用更新为 TD v1.3

2. 编写实现提示词（直接输出，不落地为文件）
   - 涵盖项目上下文、5 份文档精华、逐 Phase 实现指令
   - 包含关键陷阱警告和验收标准

**产出变更**：
- `docs/TD/2026-04-12-OAuth-Token获取工具TD.md` → v1.3（§8 计数同步）
- `docs/TODO/2026-04-12-OAuth-Token获取工具TODO.md` → v1.1（引用更新 TD v1.3）

**文档最终版本**：

| 文档 | 版本 | 状态 |
|------|------|------|
| PRD | v1.3 | ✅ 完成 |
| FD | v1.0 | ✅ 完成 |
| TD | v1.3 | ✅ 完成 |
| TDD | v1.1 | ✅ 完成 |
| TODO | v1.1 | ✅ 完成 |

---

## 2026-04-09

### 操作记录

**操作内容**：
- PRD：6 处修改
  - `§2.4.1` 标题和所有 `/claim` 引用 → `claim-random`
  - "加密存储" → "明文 JSON 存储"（JWT 已签名，本期不额外加密）
- FD：3 处修改
  - 数据流图和参考资料中 `/claim` → `claim-random`
- TD：4 处修改
  - `Schema v18` → `Schema v19`
  - 所有 `/claim` 引用 → `claim-random`
- TODO：Phase 0 任务全部标记为 `[x]`

#### 7c. Phase 4 读信链路适配 + 真实 E2E 测试

**时间**：2026-04-09

**操作内容**：

1. **mailbox_resolver.py 适配**：
   - CF pool 账号（`provider='cloudflare_temp_mail'`）→ 返回 `kind='temp'`
   - meta 从 `accounts.temp_mail_meta` 解析，包含 `provider_jwt`
   - 外部读信链路自动走 `TempMailService → CF Provider → 真实 CF Worker API`

2. **真实 CF Worker E2E 测试**（`tests/test_pool_cf_real_e2e.py`）：
   - CF Worker: `https://temp.zerodotsix.top` + 真实 admin key
   - E2E-01: claim-random → 真实创建 CF 邮箱 ✅
   - E2E-02: 读取邮件列表（新邮箱为空，正确返回 404）✅
   - E2E-03: complete(success) → 远程 CF 邮箱已删除 ✅
   - E2E-04: complete(verification_timeout) → 远程邮箱保留 ✅
   - 4/4 全部通过（11.961s）

3. **测试结果汇总**：
   - Pool 相关 70 测试（含 TDD 骨架）：0 failures, 1 skipped
   - 真实 E2E 4 测试：0 failures
   - 模块边界测试 3/3 通过

**修改文件**：
- `outlook_web/services/mailbox_resolver.py` — 新增 CF pool 账号 → `kind='temp'` 逻辑
- `outlook_web/services/refresh.py` — 排除 CF pool 账号进入 OAuth 刷新链路（`provider='cloudflare_temp_mail'`）
- `tests/test_pool_cf_real_e2e.py` — **新增** 真实 CF Worker E2E 测试（4 个用例）
- `tests/test_pool_cf_integration_tdd_skeleton.py` — E2E mock 测试 skip（已由真实 E2E 替代）

#### 7d. Phase 6 风险修复 + 联调验收

**时间**：2026-04-09

**发现并修复的风险**：
- CF pool 账号（account_type='outlook'）会被 `refresh.py` 误选入 OAuth token 刷新链路
- 修复：`is_refreshable_outlook_account()` 新增 `provider` 参数，排除 `cloudflare_temp_mail`
- 修复：`build_refreshable_outlook_account_where()` SQL 新增 `provider != 'cloudflare_temp_mail'` 条件
- 验证：refresh 测试 7/7 通过

**Phase 6 进度**：
- ✅ Task 6.1: 本地联调脚本（已被真实 E2E 覆盖）
- ✅ Task 6.3: 日志与审计（claim/complete audit 有 provider、account_id、result）
- ✅ Task 6.4: 风险清单复核（refresh 排除 + 缓存依赖已通过 E2E 验证）
- ✅ Task 6.5: 验收清单（claim → read → complete 全链路真实验证通过）

#### 7e. Phase 6.2 前端 UI 保护 + 后端删除/编辑守卫

**时间**：2026-04-09

**操作内容**：

1. **前端 UI 保护**（`static/js/features/groups.js`）：
   - `getProviderLabel()` 新增 `cloudflare_temp_mail: 'CF 临时邮箱'` 标签
   - 新增 `isCfPoolAccount` 变量，识别 CF pool 账号
   - CF pool 账号的编辑和删除按钮设为 `disabled` + `opacity:0.3` + 提示文案

2. **后端删除保护**（`outlook_web/controllers/accounts.py`）：
   - `api_delete_account()` 新增 CF pool 检查，返回 403
   - `api_delete_account_by_email()` 新增 CF pool 检查，返回 403
   - `api_batch_delete_accounts()` 新增 CF pool 跳过逻辑
   - `api_update_account()` 新增 CF pool 检查，返回 403

3. **全量测试**：917 测试通过，0 failures

**修改文件**：
- `static/js/features/groups.js` — CF provider 标签 + 编辑/删除按钮禁用
- `outlook_web/controllers/accounts.py` — 删除/编辑 CF pool 账号保护（4 处）

#### 7f. 临时邮箱页面 CF 域名下拉不显示：BUG 确认 + 方案 A 选定 + 文档对齐更新

**时间**：2026-04-09

**背景**：在验收 CF Worker 临时邮箱/邮箱池接入时发现一个前端体验 BUG —— 设置页已同步的 CF 域名在「⚡ 临时邮箱」页选择 `cloudflare_temp_mail` provider 后，域名下拉不展示。

**根因结论**（已记录到 BUG 文档）：
- `/api/temp-emails/options` 当前不支持按 provider 返回（始终按全局 runtime provider 返回 options）
- `CloudflareTempMailProvider.get_options()` 读取的是 `temp_mail_*` key，但设置页同步写入的是 `cf_worker_*` key，导致 domains 为空

**本次决策**：确认采用 **修复方案 A（推荐）**
- options API 支持 `provider_name` 参数（后端按 provider 返回 options）
- CF provider 的 options 读取口径切换为 `cf_worker_*`
- 前端请求 options 时携带当前选择的 provider

**本次实际操作**（按“以代码为准”修正文档）：
- 更新/对齐文档：
  - `docs/FD/2026-04-09-CF临时邮箱接入邮箱池FD.md`（修正“读信无需改动/解析返回 kind=account/account_type=temp_mail”等不准确描述；强调 resolver 返回 `kind='temp'`）
  - `docs/TD/2026-04-09-CF临时邮箱接入邮箱池TD.md`（修正“Repository 层进行网络调用”的伪代码与函数命名；对齐实际实现：网络调用在 Service，Repository 仅 DB 写入）
  - `docs/TODO/2026-04-09-CF临时邮箱接入邮箱池TODO.md`（补齐 Phase 4/6 的已完成勾选，保持与 WORKSPACE 的真实进度一致）
  - `docs/BUG/2026-04-09-临时邮箱-CF域名配置不生效-Options口径不一致BUG.md`（状态更新为“已确认方案 A，待实施”）

#### 7g. BUG 修复实施完成 + 人工验收通过（含一次配置值误报排查）

**时间**：2026-04-09

**实施内容**：

1. **方案 A 落地**：
   - `/api/temp-emails/options` 支持 `provider_name` 参数（后端按 provider 返回 options）
   - `TempMailService.get_options(provider_name=...)` 支持按 provider 取配置
   - 前端 `loadTempEmailOptions()` 带 provider 查询参数

2. **v0.3.1 快速修复**：
   - `CloudflareTempMailProvider.get_options()` 增加自动同步逻辑：
     - 当 `cf_worker_domains` 为空且 `cf_worker_base_url` 已配置时，自动请求 `GET {base_url}/open_api/settings`
     - 成功后写回 `cf_worker_domains` / `cf_worker_default_domain`
     - 失败非阻塞（warning）

3. **人工验收（真实环境）**：
   - provider=CF 后域名下拉可见（`zerodotsix.top`, `outlookmailplus.tech`）
   - 指定域名创建邮箱成功

4. **现场故障排查记录**：
   - 现象：创建时报 `UNAUTHORIZED` / 502
   - 根因：`cf_worker_admin_key` 配置值错误（写入了 `admin123`，实际应为 `1234567890-=`）
   - 结论：非代码保存链路缺陷，修正配置值后恢复

#### 7h. 文档二次对齐收尾（按“代码与测试结果为准”）

**时间**：2026-04-09

**目标**：将 `FD/TD/TODO/BUG` 与当前实现、真实人工验收、全量测试结果一致化，清理历史“计划态/样例态”描述。

**本次对齐动作**：

1. `docs/TODO/2026-04-09-CF临时邮箱接入邮箱池TODO.md`
   - 将全量测试从 `917/917` 更新为 `919/919`
   - 明确 claim/complete audit 当前字段覆盖现状（claim-complete 额外 provider 标为后续增强）
   - 明确 `mailbox_resolver` + external read 最小链路已由真实 E2E 覆盖
   - 文末声明更新为“已持续回填，默认以代码和测试为准”

2. `docs/FD/2026-04-09-CF临时邮箱接入邮箱池FD.md`
   - 修正测试文件引用：去除不存在的 `test_pool_cf_integration.py / test_external_pool_cf_e2e.py / test_pool_cf_contract.py`
   - 对齐当前实际测试文件：`test_pool_cf_integration_tdd_skeleton.py`、`test_pool_cf_real_e2e.py`、`test_temp_emails_api_regression.py`、`test_temp_mail_provider_cf.py`
   - 调整“文档更新”章节为当前仓库状态描述（CHANGELOG/API 文档按可选同步）

3. `docs/TD/2026-04-09-CF临时邮箱接入邮箱池TD.md`
   - 将“动态创建在 claim_atomic 中调用 `_create_cf_temp_email_for_pool()`”改为真实实现：Service 层 `_create_cf_mailbox_for_pool()` + Repository `insert_claimed_account()`
   - 将 external claim-random 示例对齐为当前 controller 结构（返回字段以当前实现为准）
   - 修正里程碑与验收项：标注已完成项、待发布项、测试结果（919/919）
   - 将不存在测试文件替换为当前真实文件

4. `docs/BUG/2026-04-09-临时邮箱-CF域名配置不生效-Options口径不一致BUG.md`
   - 状态改为“已修复”
   - 补充 v0.3.1 自动同步实现与人工验收结论
   - 补充“UNAUTHORIZED 为配置值错误而非保存链路缺陷”的排查记录

**验证**：
- 重点回归：`tests.test_temp_mail_provider_cf` + `tests.test_temp_emails_api_regression` 通过
- 全量测试：`python -m unittest discover -s tests -v` → `Ran 919 tests ... OK (skipped=7)`

#### 7i. README 与对外接口文档同步更新（面向接入方）

**时间**：2026-04-09

**背景**：在完成 CF 临时邮箱接入池能力与人工验收后，补齐对外可见文档，避免接入方沿用旧字段/旧错误码。

**本次更新文件**：

1. `README.md`
   - 补充 CF 临时邮箱最近更新：
     - options 支持 `provider_name`（前端切换 provider 时域名下拉正确联动）
     - v0.3.1 自动同步 domains（`cf_worker_domains` 为空时自动回源）
     - `cf_worker_admin_key` 配置不一致会导致 `UNAUTHORIZED` 的注意事项
   - 在核心能力中补充 `provider=cloudflare_temp_mail` 且池空动态创建
   - 在环境变量说明中补充 CF Worker 对应项（并注明设置页 key 名）

2. `注册与邮箱池接口文档.md`
   - `claim-random` 的 `provider` 可选值补全：`outlook/imap/custom/cloudflare_temp_mail`
   - 明确 `provider=cloudflare_temp_mail` 且池空时会动态创建
   - 成功返回字段补全：`email_domain`、`claimed_at`
   - 错误码对齐：`NO_AVAILABLE_ACCOUNT` → `no_available_account`
   - 补充 `claim-complete` 下 CF 删除策略（success/credential_invalid 删除，失败非阻塞）

3. `registration-mail-pool-api.en.md`
   - 与中文接口文档做同口径同步（provider 枚举、动态创建行为、返回字段、错误码大小写、CF 删除策略）

**结果**：
- 接入方文档与当前实现保持一致，减少对接歧义和现场排障成本。

#### 7j. 对外接口文档补充“可复制接入示例”（中英）

**时间**：2026-04-09

**背景**：为降低接入成本，按当前真实接口契约补充可直接复制的 curl 与响应示例。

**更新文件**：

1. `注册与邮箱池接口文档.md`
   - 新增：
     - CF 池 `claim-random` 可复制请求示例
     - `claim-random` 成功/无可用账号响应示例
     - `claim-complete` 可复制请求与成功响应示例
     - `claim-release` 可复制请求示例

2. `registration-mail-pool-api.en.md`
   - 同步新增英文版可复制示例（claim-random / claim-complete / claim-release）

**文档口径**：
- provider 明确支持 `cloudflare_temp_mail`
- no-available 错误码统一为 `no_available_account`
- claim-random 成功字段示例包含 `email_domain`、`claimed_at`

---

#### 4. CF临时邮箱接入邮箱池：文档补齐 + TDD 编写

**时间**：2026-04-09

**目标**：按“文档先行”流程补齐该功能的文档链路，并在进入实现前完成 TDD（测试设计文档）。

**本次实际操作**：

- 确认 PRD 已存在：`docs/PRD/2026-04-09-CF临时邮箱接入邮箱池PRD.md`
- 编写/补齐（当前工作区内为未提交状态）：
  - `docs/FD/2026-04-09-CF临时邮箱接入邮箱池FD.md`
  - `docs/TD/2026-04-09-CF临时邮箱接入邮箱池TD.md`
  - `docs/TDD/2026-04-09-CF临时邮箱接入邮箱池-TDD.md`

**关键内容**：

- 明确测试目标：动态创建、智能删除、兼容不破坏、外部 API 契约稳定
- 明确测试分层：Repository → Service → Controller →（可选）external 读信链路
- 明确 Mock 策略：禁止真实网络，统一 patch `CloudflareTempMailProvider.*`

**对话规范**：后续需求确认/方案选择/完成前反馈，统一通过“寸止 MCP”进行。

#### 5. 文档与代码现状对齐：schema 版本与项目地图修正

**时间**：2026-04-09

**目标**：在“充分阅读源代码”后，将仓库内关键说明文档与代码现状对齐，并记录本次操作。

**本次实际操作**：

- 对照源码确认：
  - `outlook_web/__init__.py` 版本号为 `1.13.0`
  - `outlook_web/db.py` 当前 `DB_SCHEMA_VERSION = 19`（含 v18: accounts 新增 `temp_mail_meta`）
- 修正文档不一致处：
  - `CLAUDE.md`：
    - `outlook_web/__init__.py` 版本号注释 `v1.12.0` → `v1.13.0`
    - `db.py` schema 注释 `v18` → `v19`
    - Database 章节 `schema v18` → `schema v19`
  - `docs/项目地图.md`：
    - “凭据加密（schema v18）” → “（schema v19）”
    - “数据库迁移框架（v18）” → “（v19）”

**说明**：本次仅做“事实对齐”的最小改动，不调整原有结构与叙事。

#### 6. 深读主链路源码并对齐 CF 邮箱池文档（external_pool 路由实际为 claim-random/claim-complete）

**时间**：2026-04-09

**目标**：按“以源码为准”的原则深读邮箱池/CF Provider/外部 API 安全链路，并将 FD/TD 文档中的接口路径与行为描述对齐到当前实现。

**本次实际操作（可核对点）**：

- 深读源码文件（节选）：
  - `outlook_web/routes/external_pool.py`：外部邮箱池路由实际为
    - `POST /api/external/pool/claim-random`
    - `POST /api/external/pool/claim-release`
    - `POST /api/external/pool/claim-complete`
    - `GET  /api/external/pool/stats`
  - `outlook_web/controllers/external_pool.py`：claim-random/complete/release 的参数透传与 audit 逻辑
  - `outlook_web/security/external_api_guard.py`：公网模式下的 IP 白名单、限流、功能开关（feature 禁用）
  - `outlook_web/repositories/pool.py`：provider=cloudflare_temp_mail 时无可用邮箱会动态创建；complete 后按结果非阻塞删除远程 CF 邮箱
  - `outlook_web/services/temp_mail_provider_cf.py`：CF Worker API 适配（x-admin-auth / Bearer jwt），meta 标准化（provider_jwt/provider_mailbox_id/provider_capabilities）

- 文档对齐改动：
  - `docs/FD/2026-04-09-CF临时邮箱接入邮箱池FD.md`
    - 将 `/api/external/pool/claim` 对齐为实际路由 `/api/external/pool/claim-random`
    - 将 `/api/external/pool/complete` 对齐为实际路由 `/api/external/pool/claim-complete`
    - 修正“邮件读取已支持无需改动”的表述，避免与当前 resolver 行为产生误导
  - `docs/TD/2026-04-09-CF临时邮箱接入邮箱池TD.md`
    - 将 external pool 章节中的 `/claim`、`/complete` 路由对齐为 `/claim-random`、`/claim-complete`
    - 将 complete 响应示例调整为“以 controller 实现为准”的兼容表述

**说明**：本次仍坚持“最小必要改动”，只修正与源码不一致的接口路径与高风险误导点。

#### 3. 分支同步与联系方式添加

**时间**：2026-04-09

**分支同步**：
- `Buggithubissue`、`dev`、`feature` 三个分支均已落后 main，无独立提交
- 使用 `git branch -f` + `git push --force` 将所有分支 fast-forward 到 main（`7952820`）
- 注意：三个分支被 worktree 占用（`E:/hushaokang/Data-code/EnsoAi/outlookEmail/` 下），无法 checkout，改用 `git branch -f` 直接重置
- `feature` 无远程分支，仅本地同步

**联系方式**：
- `README.md`：新增"联系方式"章节 → `outlookmailplus@163.com`
- `README.en.md`：新增"Contact"章节 → `outlookmailplus@163.com`

**修改文件**：
- `README.md`：末尾新增联系方式
- `README.en.md`：末尾新增 Contact 章节

**Commits**：
- `301b122`：fix: 移除 sonar-project.properties 中已删除的 fix_format.py 引用
- `7952820`：docs: 添加联系邮箱，同步所有分支到 main

---

#### 2. v1.13.0 发布与 SonarCloud 修复

**时间**：2026-04-09

**版本发布**：
- 版本号：`1.12.0` → `1.13.0`（`outlook_web/__init__.py`）
- 更新 CHANGELOG.md、DEVLOG.md、README.md、README.en.md 版本引用
- 更新 `tests/test_version_update.py` 中所有版本断言和 mock 数据
- 本地 893 测试全部通过（0 failures, 6 skipped）
- CI 全量通过（Python Tests / Code Quality / Docker Build）
- Git Tag `v1.13.0` → 触发 `create-github-release.yml` 自动创建 GitHub Release
- Docker 镜像双仓库推送成功：
  - GHCR: `ghcr.io/zeropointsix/outlook-email-plus:v1.13.0` / `:latest`
  - Docker Hub: `guangshanshui/outlook-email-plus:v1.13.0` / `:latest`
  - Digest: `sha256:8909cf0300c956d2db803157dfdeced2a24e6b6c09c149509f87ae6025ff086d`
  - 架构: `linux/amd64` + `linux/arm64`

**SonarCloud 失败修复**：
- 根因：`sonar-project.properties` 中 `sonar.sources` / `sonar.inclusions` / `sonar.coverage.exclusions` 引用了已删除的 `fix_format.py`
- 该文件在 commit `04824bc` 已删除，但 SonarCloud 配置未同步清理
- 修复：从 3 处配置项中移除 `fix_format.py` 引用
- 同步清理：`docs/项目地图.md` 中可清理项目列表移除 `fix_format.py`

**修改文件**：
- `outlook_web/__init__.py`：版本号 → `1.13.0`
- `tests/test_version_update.py`：版本断言 + mock tag_name
- `CHANGELOG.md`：新增 `[v1.13.0]` 段落
- `docs/DEVLOG.md`：新增 `v1.13.0` 段落
- `README.md` / `README.en.md`：版本引用更新
- `sonar-project.properties`：移除 `fix_format.py` 引用（3 处）
- `docs/项目地图.md`：移除已删除文件记录

---

#### 1. hotupdate-test 分支端到端测试与合并

**时间**：2026-04-09

**背景**：`hotupdate-test` 分支在 `main` 基础上新增 24 个提交，用于热更新功能的端到端验证（Watchtower + Docker API 双模式）。分支使用 GHCR 远程镜像（`ghcr.io/zeropointsix/outlook-email-plus:hotupdate-test`）进行了完整的两种更新方式的实际测试。

**测试环境**：
- 端口 5002：Watchtower 模式（`docker-compose.hotupdate-test.yml`，含 Watchtower sidecar）
- 端口 5003：Docker API 模式（`docker-compose.docker-api-test.yml`，挂载 docker.sock）
- 镜像：`ghcr.io/zeropointsix/outlook-email-plus:hotupdate-test`

**发现并修复的问题**：

| # | 问题 | 修复 | Commit |
|---|------|------|--------|
| 1 | GHCR 镜像不在白名单 | 添加 `ghcr.io/zeropointsix/` 到 ALLOWED_IMAGE_PREFIXES | 早期提交 |
| 2 | 本地镜像检测误判 | 重写 `_looks_like_local_image_ref()` 为 namespace 白名单 | 早期提交 |
| 3 | 版本比较 pre-release 后缀问题 | `_version_gt()` 忽略 `-hotupdate-test` 等后缀 | 早期提交 |
| 4 | Watchtower 连通测试超时 (5s) | 增加到 35s，添加详细注释说明 Watchtower 同步行为 | `6441de2` |
| 5 | Emoji 前缀 i18n 翻译匹配失败 | 在 exactMap 中添加 `🔄`/`🚀` 前缀变体 | `6441de2` |
| 6 | 设置页 Tab 标签缺少翻译 | 添加 基础/临时邮箱/API 安全/自动化 翻译 | `6441de2` |
| 7 | Watchtower 200 响应误判为"更新成功" | 改为 `already_latest: true`（Watchtower 同步完成 → 未更新我们） | `2b49547` |
| 8 | 连通性/更新结果 i18n 缺失 | 添加 连通正常/检查完毕/测试中/更新失败 等翻译 | `2b49547` |
| 9 | 测试断言不匹配 | 更新 `test_watchtower_success` 断言 `already_latest` + `"检查完毕"` | `3672888` |

**合并过程**：

1. 版本号从 `1.12.8-hotupdate-test` 回退至 `1.12.0`（与 main 一致）
2. 删除测试专用 compose 文件（`docker-compose.hotupdate-test.yml`、`docker-compose.docker-api-test.yml`）
3. 移除 CI docker-build-push 中 `hotupdate-test` 分支触发
4. 清理 `start.py` 测试注释、恢复 `WORKSPACE.md`
5. Fast-forward 合并到 main（`6f5c707`）
6. 推送 main、删除远程和本地 `hotupdate-test` 分支
7. 停止并删除所有测试容器和 volume

**Watchtower 同步行为关键发现**：

Watchtower `POST /v1/update` 是**同步接口**——完整执行镜像拉取和 digest 比对后才返回 200。如果我们的容器需要更新，Watchtower 会在返回前 kill 旧容器并启动新容器，因此**我们永远收不到 200 响应**。反过来，如果收到了 200 响应，说明 Watchtower 判定当前已是最新版本，无需更新。

**Watchtower DNS 问题**：

测试环境中 Watchtower 将 `ghcr.io` 解析为 `198.18.2.198`（VPN/代理干扰），导致 HEAD 请求失败，fallback 到完整 pull（需 25-30s），这是连通测试超时需要从 5s 增加到 35s 的根本原因。

---

## 2026-04-07

### 操作记录

#### 7. Docker API 自更新安全策略强化（策略A）

**时间**：2026-04-07 下午

**背景**：原有 Docker API 自更新功能存在安全隐患——本地构建镜像可能误触发更新，导致不可预期的行为。

**目标**：实施策略A（彻底禁止本地构建镜像触发 Docker API 更新），确保只有官方远程镜像才能触发更新。

**实施内容**：

1. **镜像白名单收紧**：
   - 移除 `outlook-email-plus`（无 namespace）白名单项
   - 仅保留 `guangshanshui/outlook-email-plus`官方镜像前缀
   
2. **新增本地构建检测**：
   - `validate_image_for_update()`：镜像白名单 + RepoDigests 检测双重校验
   - `_looks_like_local_image_ref()`：基于 namespace 的启发式本地镜像检测（修复 bug：改为 namespace 白名单判断）
   - `_has_repo_digests()`：通过 Docker API 检查镜像 RepoDigests（本地 build 镜像为空）
   
3. **API 层前置校验**：
   - `_trigger_docker_api_update()` 在触发阶段就获取容器镜像并校验
   - 校验失败返回 403/500，避免等到 spawn updater 内部才失败
   
4. **部署信息展示优化**：
   - `api_deployment_info()` 不再依赖 `DOCKER_SELF_UPDATE_ALLOW` 环境变量
   - 只要 docker.sock 可用就通过 Docker API 获取真实镜像名（更准确）
   
5. **测试用例调整**：
   - `docker-compose.docker-api-test.yml` 镜像改为 `guangshanshui/outlook-email-plus:latest`（形成负向用例：本地 build 但伪装官方名也会被 RepoDigests 检测拦截）

**修改文件**：
- `outlook_web/services/docker_update.py`：
  - 白名单收紧
  - 新增 `validate_image_for_update()`, `_looks_like_local_image_ref()`, `_has_repo_digests()`
  - `get_container_info()` 通过 `client.images.get()` 获取 RepoDigests
  - `spawn_update_helper_container()` 和 `self_update()` 调用新校验函数
  - Bug修复：`_looks_like_local_image_ref()` 改为 namespace 白名单判断（`guangshanshui`, `docker.io/guangshanshui`, `ghcr.io/guangshanshui`）
- `outlook_web/controllers/system.py`：
  - `_trigger_docker_api_update()` API 层镜像校验
  - `api_deployment_info()` 获取镜像名逻辑优化
- `docker-compose.docker-api-test.yml`：测试镜像名调整

**代码逻辑测试结果**（PowerShell环境）：
```
=== 白名单校验 ===
guangshanshui/outlook-email-plus:latest  → ✅ 通过
guangshanshui/outlook-email-plus:test    → ✅ 通过
outlook-email-plus:latest                → ❌ 拦截（无 namespace）
myregistry/outlook-email-plus:latest     → ❌ 拦截（非官方 namespace）

=== 启发式检测 ===
guangshanshui/outlook-email-plus:*       → False（正确识别为官方）
outlook-email-plus:*                     → True（正确识别为本地）
其他namespace/*                          → True（正确识别为非官方）
```

**文档产出**：
- `docs/DEV/manual-acceptance-checklist.md`：人工验收清单（4 个测试用例 + 验收标准 + 快速测试脚本）

**待验收项（当时）**：
- [ ] 负向用例1：本地构建镜像触发更新被拦截
- [ ] 负向用例2：本地构建伪装官方名触发更新被拦截
- [ ] 正向用例3：官方远程镜像成功触发更新流程
- [ ] 部署信息准确性验证

**端到端实际测试记录（Docker Desktop / Windows）**：

环境：
- Docker Desktop 4.43.2（Engine 28.3.2，Context: desktop-linux）
- Docker Compose v2.38.2

执行：
1) 启动负向用例（本地 build + 伪装官方镜像名）：
   - 命令：`docker compose -f docker-compose.docker-api-test.yml up -d --build`
   - 容器：`outlook-dockerapi-test`（端口 5003→5000）
   - 镜像：`guangshanshui/outlook-email-plus:latest`（本地 build）
   - 镜像 RepoDigests：`[]`（确认本地 build 特征）

2) 通过脚本模拟前端触发更新（含 CSRF）：
   - `POST /login` → ✅ success
   - `GET /api/csrf-token` → ✅ 返回 csrf_token
   - `POST /api/system/trigger-update?method=docker_api` + `X-CSRFToken` → ✅ 返回 403
     - message：`检测到本地构建镜像（RepoDigests 为空），已按安全策略禁止 Docker API 一键更新...`
   - 结论：策略A拦截生效；未创建 updater 容器；旧容器未被 stop

3) 正向用例尝试（远程拉取官方镜像）被环境网络阻塞：
   - `docker pull guangshanshui/outlook-email-plus:v1.11.0` → ❌ 超时
   - 错误：`Client.Timeout exceeded while awaiting headers`（auth.docker.io token 请求超时）
   - 影响：无法在当前环境完成“远程镜像 RepoDigests 非空 → 允许触发 updater → self_update 跑完”的正向验收

**结论（阶段性）**：负向端到端已通过；正向端到端当时受 DockerHub 网络访问影响未完成。

---

#### 13. 策略A 正向端到端验收补全：真实“热更新切换”演示（A2 + 远程镜像 tag 变更）

**时间**：2026-04-07 晚

**目标**：补齐策略A的正向端到端验收，验证当远程镜像 tag 指向新 digest 时，A2 updater 能完成完整切换流程：

- pull 最新镜像
- digest 不同 → create 新容器
- stop 旧容器释放端口
- start 新容器 + health
- rename（新容器接管原名称）
- 旧容器保留为 backup（remove_old=false）

**验收环境/对象**：

- 镜像 tag：`guangshanshui/outlook-email-plus:a2-strategyA-canary`
- 初始运行容器：`outlook-canary`（端口 `5005 -> 5000`，挂载 `/var/run/docker.sock`）
- 触发更新方式：应用内接口 `POST /api/system/trigger-update?method=docker_api`（登录 + CSRF）

**关键证据（更新前）**：

- 运行中容器：`outlook-canary`
- 容器使用的 image id（旧）：`sha256:056f69613d8dac7a486ed77a32c8041fb522c4f63d0fad8f6d0149078190e84e`
- 容器镜像引用仍为 tag：`guangshanshui/outlook-email-plus:a2-strategyA-canary`
- 本地同 tag 已被重新打到新镜像（新 image id）：`sha256:21aba8bda26d893f59af319eaeb5a72d06eedfd3b4f521a0d004e2bd9503b2fb`

说明：容器创建时记录的是当时 tag 对应的镜像 ID；后续重新 push 同 tag 后，容器仍显示原 tag，但 image id 不会自动变化，因此能触发“digest 不同 → 更新”。

**触发更新（PowerShell / Invoke-RestMethod，带 session cookie 与 CSRF）**：

```powershell
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession

# 1) 登录（写入 session cookie）
$loginBody = @{ password = 'admin123' } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://localhost:5005/login' -Method Post -ContentType 'application/json' -Body $loginBody -WebSession $session

# 2) 获取 CSRF token
$csrf = (Invoke-RestMethod -Uri 'http://localhost:5005/api/csrf-token' -Method Get -WebSession $session).csrf_token

# 3) 触发 Docker API 更新（A2 helper）
Invoke-RestMethod -Uri 'http://localhost:5005/api/system/trigger-update?method=docker_api' -Method Post -Headers @{ 'X-CSRFToken' = $csrf } -WebSession $session
```

接口返回（关键字段）：

```json
{"success": true, "message": "更新任务已启动: oep-updater-1775571256 (e21bf4afbbdb)"}
```

**关键证据（更新后）**：

1) `outlook-canary` 名称仍存在，且重新变为运行态并健康：

- 新容器 ID（short）：`e0ba3c44dcc9`
- 新容器 image id：`sha256:21aba8bda26d893f59af319eaeb5a72d06eedfd3b4f521a0d004e2bd9503b2fb`
- 端口仍为：`0.0.0.0:5005->5000/tcp`

2) 旧容器被 rename 为 backup 并退出（符合 A2 设计：保留旧容器便于回滚）：

- 旧容器名称：`outlook-canary_backup_1775571270`
- 旧容器 image id：`sha256:056f69613d8dac7a486ed77a32c8041fb522c4f63d0fad8f6d0149078190e84e`
- 状态：Exited(0)

3) `/healthz` 访问正常（证明新容器已接管服务）：

```json
{"status":"ok","version":"1.12.0","boot_id":"1775571264516-7"}
```

**结论**：策略A + A2 helper 的“正向端到端热更新切换”已完成，验证了 digest 变化场景下的 stop/start/rename/backup 全链路行为。

**关联 Issue/PR**：待 Docker 容器内实际验收通过后提交

---

#### 1. mystatus 插件状态确认

**背景**：尝试使用 `mystatus` 工具查询 AI 账户配额使用情况。

**实际情况**：

| 项目 | 状态 |
|------|------|
| 插件安装 | `opencode-mystatus@1.2.4` 已安装于全局 `~/.config/opencode/node_modules/` |
| 全局配置 | `~/.config/opencode/opencode.json` 已注册 `plugin` 和 `command` |
| 项目配置 | 项目级 `opencode.json` 未单独配置 mystatus 插件（使用全局配置） |
| 工具可用性 | 当前会话工具列表中**未注册** `mystatus` 工具，无法直接调用 |

**配置位置**：

- 全局插件配置：`C:\Users\PLA30\.config\opencode\opencode.json`
  ```json
  "plugin": ["opencode-mystatus"],
  "command": {
    "mystatus": {
      "description": "Query quota usage for all AI accounts",
      "template": "Use the mystatus tool to query quota usage. Return the result as-is without modification."
    }
  }
  ```
- 插件源码位置：`C:\Users\PLA30\.config\opencode\node_modules\opencode-mystatus\`

**支持平台**：

| Platform | Account Type |
|----------|-------------|
| OpenAI | Plus / Team / Pro |
| Zhipu AI | Coding Plan |
| Z.ai | Coding Plan |
| GitHub Copilot | Individual / Business |
| Google Cloud | Antigravity |

**结论**：`mystatus` 作为 opencode 插件需要在 opencode 运行时环境中通过 `/mystatus` 命令或自然语言触发，当前通过外部 Agent 调用时无法直接使用该工具。

#### 2. 热更新功能开发状态确认

**关联文档**：
- AI 提示词：`docs/DEV/hot-update-ai-prompt.md`
- 基线记录：`docs/DEV/hot-update-baseline.md`

**功能概述**：为 Outlook Email Plus 实现 Docker 部署环境下的一键更新功能，支持 Watchtower 和 Docker API 两种更新方式。

**实施进度（全部已完成）**：

| 阶段 | 内容 | 状态 | Commit |
|------|------|------|--------|
| Phase 1 | BUG 修复（Token 为空启动失败、浏览器缓存旧 JS） | ✅ | 91a8f35 |
| Phase 2 | UI 提示优化（镜像标签/构建模式检测） | ✅ | 91a8f35 |
| Phase 3 | 内置 Docker API 自更新 | ✅ | 91a8f35 |
| P0 | BUG-006 GitHub 仓库地址修复 | ✅ | e6d27b6 |

**核心产出**：
- 新增：`outlook_web/services/docker_update.py`（591 行，经代码验证 2026-04-07，原文档记录 839 行已修正）
- 新增 API：`/api/system/version-check`、`/api/system/trigger-update`、`/api/system/test-watchtower`、`/api/system/deployment-info`
- 新增设置项：`watchtower_url`、`watchtower_token`（加密存储）、`update_method`
- 前端：版本更新 Banner、Watchtower 配置 UI、Docker API 更新方式选择
- 前端补齐：设置页一键更新区域的部署信息警告（`/api/system/deployment-info` → `#deploymentWarnings`）
- 安全：默认关闭 Docker API 自更新、镜像白名单校验、审计日志

**当前版本**：v1.12.0，热更新验证已通过（v1.12.0 → v1.12.1）

#### 3. 文档更新

- 创建 `WORKSPACE.md` 工作区操作记录文档
- 确认项目结构：项目级 `opencode.json` 仅配置了子代理（context-retriever, small-task-executor），mystatus 依赖全局配置
- 记录热更新功能完整实施状态

#### 4. 热更新文档代码验证与清理

**操作内容**：

1. **代码验证**：逐一对比 `hot-update-ai-prompt.md` 中的描述与实际代码
   - ✅ 4 个 API 端点全部存在且已注册路由
   - ✅ `update_method` 设置项 GET/PUT 支持
   - ✅ 静态文件缓存控制 `set_static_cache_control()` 
   - ✅ GitHub 仓库地址 `ZeroPointSix/outlookEmailPlus`
   - ✅ `docker-compose.yml` 配置完整（Token 默认值、docker.sock 注释、DOCKER_SELF_UPDATE_ALLOW）
   - ✅ `.env.example` 模板完整
   - ⚠️ **发现差异**：`docker_update.py` 实际 591 行，文档记录为 839 行 → **已修正**

2. **文档清理**：清理 `hot-update-ai-prompt.md`
   - 删除"待实施任务 (可选扩展)"部分（第 154-318 行），该部分重复了已完成的 Phase 1-3 任务描述
   - 新增"代码验证记录"表格，记录 13 项验证结果
   - 修正 `docker_update.py` 行数为实际值 591
   - 保留"参考文件清单"和"注意事项"部分

**已修改文件**：
- `docs/DEV/hot-update-ai-prompt.md` — 删除冗余内容，新增验证记录，修正数据

#### 5. README 生产配置更新

**操作内容**：
- 更新 `README.md` 中 docker-compose 生产配置示例，同步 Phase 3 新功能
  - 新增 `DOCKER_SELF_UPDATE_ALLOW` 环境变量（注释状态）
  - 新增 docker.sock 挂载选项（注释状态）
  - 新增"更新方式"说明段落，指导用户如何切换 Watchtower/Docker API 模式
- 修正 README "最近更新"版本号：v1.11.0 → v1.12.0
- 新增"一键更新"功能说明段落

**已修改文件**：
- `README.md` — 版本号更新、docker-compose 示例更新、功能说明补充

#### 6. 热更新功能完整性详细分析

**结论：功能已完整实现**，所有文档描述的功能点均在代码中找到对应实现。

**后端功能验证（全部 ✅）**：

| 功能 | 位置 | 状态 |
|------|------|------|
| 版本检测 API（10 分钟缓存） | system.py:353 | ✅ |
| 更新触发 API（双模式） | system.py:402 | ✅ |
| Watchtower 更新（DB→env fallback + 加密 Token） | system.py:438 | ✅ |
| Docker API 更新（安全检查→socket→白名单→12 步流程） | system.py:500 + docker_update.py | ✅ |
| 部署信息检测（镜像/标签/本地构建/Watchtower 连通性） | system.py:561 | ✅ |
| Watchtower 连通性测试 | system.py:732 | ✅ |
| 设置项 update_method（GET/PUT） | settings.py:351/1013 | ✅ |
| 静态文件缓存控制 | app.py:124 | ✅ |

**前端功能验证（全部 ✅）**：

| 功能 | 位置 | 状态 |
|------|------|------|
| 页面加载版本检查 | main.js:3763 `checkVersionUpdate()` | ✅ |
| 双模式触发更新 + 差异化超时 | main.js:3790 `triggerUpdate()` (120s/10s) | ✅ |
| 重启轮询等待 | main.js:3880 `waitForRestart()` | ✅ |
| 部署信息警告渲染（设置页） | main.js: `loadDeploymentInfo()` / `renderDeploymentWarnings()` | ✅ |
| Watchtower 连通性测试 | main.js:2169 `testWatchtower()` | ✅ |
| 设置加载/保存 update_method | main.js:1743/2100 | ✅ |

**Docker API 自更新 12 步流程（docker_update.py）**：

| 步骤 | 函数 | 状态 |
|------|------|------|
| 1. 启用开关检查 | `is_docker_api_enabled()` | ✅ |
| 2. Socket 可访问性 | `check_docker_socket()` | ✅ |
| 3. 获取当前容器信息 | `get_current_container_info()` | ✅ |
| 4. 镜像名白名单校验 | `validate_image_name()` | ✅ |
| 5. 拉取最新镜像 | `pull_latest_image()` | ✅ |
| 6. Digest 比较 | `compare_image_digest()` | ✅ |
| 7. 创建新容器（复制配置） | `create_new_container()` + `_parse_volumes()` + `_parse_ports()` | ✅ |
| 8. 启动新容器 | `start_new_container()` | ✅ |
| 9. 健康检查 | `health_check_new_container()` | ✅ |
| 10. 停止旧容器 | `stop_old_container()` | ✅ |
| 11. 重命名容器 | `rename_containers()` | ✅ |
| 12. 清理/保留旧容器 | `cleanup_old_container()` | ✅ |

**发现的问题（非阻塞）**：

| # | 问题 | 严重度 | 说明 |
|---|------|--------|------|
| 1 | `can_auto_update` 未考虑 Docker API 模式 | 低 | `api_deployment_info()` 中 `can_auto_update` 仅检查 Watchtower 连通性，用户选 Docker API 模式且无 Watchtower 时会误报为不可更新 |
| 2 | `self_update()` 同步调用风险 | 低 | system.py:531 注释说明同步调用可能中断响应，但 Docker API 模式下前端有 120s 超时 + `waitForRestart()` 轮询兜底 |
| 3 | `docker-compose.hotupdate-test.yml` 含硬编码密钥 | 低 | 测试专用文件，不影响生产安全 |

#### 7. 热更新功能非阻塞问题修复

**修复 #1：`can_auto_update` 逻辑支持 Docker API 模式**

- **文件**：`outlook_web/controllers/system.py`
- **问题**：`api_deployment_info()` 中 `can_auto_update` 仅检查 Watchtower 连通性
- **修复**：新增 `docker_api_available` 检测（检查 `DOCKER_SELF_UPDATE_ALLOW` + socket 可用性），`can_auto_update` 逻辑改为 `watchtower_reachable or docker_api_available`
- **新增返回字段**：`deployment.docker_api_available`（布尔值）

**修复 #2：`self_update()` 同步→异步**

- **文件**：`outlook_web/controllers/system.py`
- **问题**：`_trigger_docker_api_update()` 同步调用 `self_update()`，旧容器被停止时响应无法到达客户端
- **修复**：使用 `threading.Thread(daemon=True)` 在后台线程执行自更新，主线程立即返回 `{"success": True, "message": "Docker API 自更新已启动，容器即将重启"}`
- **审计日志**：移入后台线程，确保更新结果被记录
- **前端兼容**：前端已有 `waitForRestart()` 轮询 `/healthz` 等待新容器启动，无需修改

**修复 #3：清理测试配置硬编码密钥**

- **文件**：`docker-compose.hotupdate-test.yml`
- **问题**：SECRET_KEY 和 WATCHTOWER_HTTP_API_TOKEN 为硬编码明文值
- **修复**：改为 `${SECRET_KEY:-please-change-this-secret-key-for-testing}` 和 `${WATCHTOWER_HTTP_API_TOKEN:-test-hotupdate-token}` 格式，支持 `.env` 文件注入
- **附加**：更新文件头注释（移除版本号引用，添加使用方式说明）

**已修改文件汇总**：
- `outlook_web/controllers/system.py` — can_auto_update 逻辑 + self_update 异步化
- `docker-compose.hotupdate-test.yml` — 密钥环境变量化

#### 8. README 环境变量补充

**操作内容**：
- 在 `README.md` 的"常用环境变量"部分新增"一键更新相关"小节
- 补充环境变量说明：
  - `WATCHTOWER_HTTP_API_TOKEN` — Watchtower API 鉴权令牌
  - `WATCHTOWER_API_URL` — Watchtower API 地址
  - `DOCKER_SELF_UPDATE_ALLOW` — 是否启用 Docker API 自更新
  - `DOCKER_IMAGE` — 当前容器镜像名（可选）
- 添加安全提示说明 Docker API 自更新的风险

**已修改文件**：
- `README.md` — 新增一键更新相关环境变量说明

#### 9. 一键更新功能人工验收 BUG 分析

**分析范围**：dev 分支相对于 main 分支新增的一键更新功能

**功能概述**：
- 版本检测：GET `/api/system/version-check`，对比 GitHub 最新 release 与本地版本
- 触发更新：POST `/api/system/trigger-update?method=watchtower|docker_api`
- Watchtower 配置：设置页可配置 URL + Token（加密存储）
- Docker API 自更新：12 步流程（拉取镜像→创建容器→健康检查→切换）

**潜在 BUG 分析**：

| # | 问题描述 | 严重度 | 复现条件 | 影响 | 建议处理 |
|---|---------|--------|----------|------|----------|
| 1 | **镜像名检测依赖 DOCKER_IMAGE 环境变量** | 低 | 未设置 DOCKER_IMAGE 时 | `api_deployment_info()` 无法准确获取镜像名，可能显示 `unknown` | 可接受，用户可手动设置 |
| 2 | **容器名冲突风险** | 低 | Docker API 自更新失败后重试 | 新容器使用 `{name}_new` 临时名称，若上次失败未清理可能冲突 | 代码中已有 force 删除逻辑，风险较低 |
| 3 | **审计日志在后台线程中记录** | 低 | Docker API 自更新 | 若新容器启动后旧容器被停止，审计日志写入数据库时机可能不稳定 | 非阻塞，日志可能丢失但不影响功能 |
| 4 | **前端超时固定 120s** | 信息 | Docker API 大镜像拉取 | 若镜像很大，拉取时间超过 120s，前端可能误报超时（但后台仍在执行） | 可接受，前端会继续轮询 `/healthz` |

**健康检查说明**：
- `docker_update.py` 中的 `health_check_new_container()` 检查的是 Docker 容器状态和 Docker 原生 healthcheck
- 前端 `waitForRestart()` 轮询的 `/healthz` 端点是应用级健康检查（已存在于 `system.py:39`）
- 两者是独立的：容器启动后，后端健康检查通过 → 前端轮询 `/healthz` 确认应用可用

**验收建议**：

1. **Watchtower 模式验收**：
   - [ ] 部署 docker-compose（含 watchtower 服务）
   - [ ] 在设置页配置 Watchtower URL + Token
   - [ ] 点击"测试连通性"按钮，确认返回成功
   - [ ] 触发版本检测，确认 Banner 显示
   - [ ] 点击"立即更新"，确认容器重启

2. **Docker API 模式验收**：
   - [ ] 修改 docker-compose 启用 `DOCKER_SELF_UPDATE_ALLOW=true`
   - [ ] 挂载 `/var/run/docker.sock`
   - [ ] 在设置页切换"更新方式"为 Docker API
   - [ ] 确认部署信息显示 `docker_api_available: true`
   - [ ] 触发更新，确认 12 步流程正常执行

3. **边界条件验收**：
   - [ ] 使用固定版本标签（如 `:v1.12.0`），确认 UI 警告正确
   - [ ] 本地构建镜像，确认 UI 警告正确
   - [ ] 未配置 Watchtower Token，确认错误提示

**结论**：一键更新功能已基本完整，无阻塞性 BUG。建议按上述验收清单进行人工测试。

#### 10. Docker API 自更新实测发现阻塞 BUG 并修复（dev 分支）

**实测背景**：尝试在 Docker 容器中调用 `/api/system/trigger-update?method=docker_api` 做完整 12 步自更新模拟。

**实际问题**：接口直接返回 500。

- 容器日志报错：`ModuleNotFoundError: No module named 'outlook_web.models'`
- 根因：`outlook_web/controllers/system.py::_trigger_docker_api_update()` 中错误引用 `from outlook_web.models import AuditLog`，但项目不存在 `outlook_web/models.py` 以及 `AuditLog` 类

**修复策略（方案 A）**：移除 `AuditLog` 依赖。

- 主线程：使用现有 `outlook_web.audit.log_audit()` 记录一次 `trigger_docker_api_update_start`（含 method/remove_old/username）
- 后台线程：仅执行 `docker_update.self_update()` 并写入应用日志（logger），避免后台线程依赖 Flask request context / DB 连接

**修改文件**：
- `outlook_web/controllers/system.py` — 移除 `outlook_web.models.AuditLog` 引用，改用 `log_audit`

---

#### 11. A2 方案实现：按需 helper job 容器（避免"自杀"问题）

**背景问题**：Docker API 模式实测发现核心阻塞——容器无法在内部 stop 自己后继续执行后续步骤（进程被杀死）。原始方案使用 daemon 线程在后台执行 self_update()，但旧容器被 stop 的瞬间后台线程也会被杀死，导致"create 新容器→stop 旧→rename→cleanup"流程中断。

**方案选型**：

| 方案 | 描述 | 优势 | 劣势 |
|------|------|------|------|
| A1: 两阶段脚本 | app 容器内写脚本→nohup 后台执行→exit | 最简单 | 可靠性差，进程管理困难 |
| **A2: 按需 helper job 容器** | app 通过 Docker API 临时创建 updater 容器 | 可靠、隔离、auto_remove 自动清理 | 短暂 2 容器并存 |
| A3: 外部 updater 服务 | 额外部署常驻 updater 容器 | 最稳 | 增加部署复杂度 |

**选定方案**：A2（按需 helper job 容器）

**架构设计**：

```
┌─────────────────────────────┐
│  App 容器（用户请求）          │
│                             │
│  1. 鉴权 + 安全校验            │
│  2. 记录审计日志（主线程）       │
│  3. Docker API 创建 updater 容器│
│  4. 立即返回 HTTP 响应          │
└─────────────┬───────────────┘
              │ docker.sock
              ▼
┌─────────────────────────────┐
│  Updater 容器（短生命周期）     │
│                             │
│  1. sleep(2) 等 HTTP 响应     │
│  2. pull 最新镜像              │
│  3. create 新容器（复制配置）   │
│  4. stop 旧容器（释放端口）     │
│  5. start 新容器               │
│  6. healthcheck 新容器         │
│  7. rename 容器                │
│  8. cleanup 旧容器             │
│  9. 退出 → auto_remove 自动清理 │
└─────────────────────────────┘
```

**关键设计决策**：

1. **start_delay_seconds=2**：updater 容器启动后延迟 2 秒再执行更新操作，给 app 容器的 HTTP 响应留出到达客户端的时间
2. **先 stop 旧容器再 start 新容器**：解决 host port 映射场景下端口冲突问题（docker-compose 常见 5000:5000 映射）
3. **auto_remove=True**：updater 容器退出后自动删除，保持"单容器部署体验"
4. **失败回滚**：新容器启动失败或健康检查失败时，尝试恢复旧容器
5. **透传 Docker 凭证**：支持 DOCKER_AUTH_CONFIG / DOCKER_CONFIG 环境变量，确保 updater 可拉取私有镜像
6. **Watchtower 排除**：updater 容器添加 `com.centurylinklabs.watchtower.enable=false` 标签

**新增/修改文件清单**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `outlook_web/services/docker_update_helper.py` | **新增**（69 行） | updater 容器入口模块，读取环境变量调用 `self_update()` |
| `outlook_web/services/docker_update.py` | 修改 | 新增 `get_container_info()`、`spawn_update_helper_container()`；增强 `validate_image_name()` 支持 digest 和 registry port；增强 volumes 解析支持 named volume；`self_update()` 新增 `target_container_id` 参数；调整步骤顺序（先 stop 旧再 start 新）；失败时尝试恢复旧容器 |
| `outlook_web/controllers/system.py` | 修改 | `healthz()` 新增 `boot_id` 和 `version` 字段；`_trigger_docker_api_update()` 改为调用 `spawn_update_helper_container()`；`api_deployment_info()` 增强 Docker API 检测和上下文感知警告 |
| `static/js/main.js` | 修改 | `waitForRestart()` 增加 boot_id 变化检测；Docker API 模式超时放宽到 180s；`triggerUpdate()` 统一走 waitForRestart 逻辑；`loadSettings()` 触发部署信息加载；新增 `loadDeploymentInfo()` / `renderDeploymentWarnings()`；语言切换时重渲染部署警告 |
| `templates/index.html` | 修改 | 新增 `#deploymentWarnings` 容器；微调缩进格式 |
| `tests/test_error_and_trace.py` | 修改 | 适配 healthz 新增 `boot_id` / `version` 字段 |
| `tests/test_smoke_contract.py` | 修改 | 适配 healthz 新增字段 |
| `docker-compose.docker-api-test.yml` | **新增**（45 行） | Docker API 模式专用测试 compose 配置 |
| `docker-compose.hotupdate-test.yml` | 修改 | 新增 DOCKER_IMAGE 环境变量 |

**self_update() 步骤顺序调整**：

原方案（先 start 新再 stop 旧）在 host port 映射场景下会产生端口冲突：

```
原: pull → compare → get_info → validate → pull_image → compare_digest → create → start_new → health_check → stop_old → rename → cleanup
新: pull → compare → get_info → validate → pull_image → compare_digest → create → stop_old → start_new → health_check → rename → cleanup
```

**前端轮询优化**：

通过 `boot_id`（`{timestamp}-{pid}`）判断容器是否发生了真正的进程重启：
- 首次轮询前记录 `initialBootId`
- 后续轮询中检测 `boot_id` 是否变化
- `boot_id` 变化 或 `seenDown`（曾看到服务不可用）时判定为重启完成

#### 12. A2 方案本地 Docker 验证（dev 分支）

**验证环境**：
- Docker Desktop 4.43.2 (Engine 28.3.2)
- 本地构建镜像 `outlook-email-a2-test:latest`（基于 dev 分支源码）
- 容器名 `outlook-dockerapi-test`，端口映射 5003:5000
- 挂载 docker.sock，DOCKER_SELF_UPDATE_ALLOW=true

**验证步骤与结果**：

| # | 测试项 | 结果 | 说明 |
|---|--------|------|------|
| 1 | `healthz` 返回 `boot_id` + `version` | ✅ | `{"status":"ok","boot_id":"1775563642828-8","version":"1.12.0"}` — A2 代码已生效 |
| 2 | 登录 + CSRF token 获取 | ✅ | Cookie-based session + X-CSRFToken |
| 3 | 部署信息 API | ✅ | `docker_api_available:true`，`is_local_build:true`，警告正确 |
| 4 | 触发更新 API（白名单校验） | ✅ | 返回 `"镜像名不在白名单内: outlook-email-a2-test:latest"` — 正确拦截 |
| 5 | Docker socket 连通性 | ✅ | `check_docker_socket()` 返回可用 |
| 6 | 容器内省 `get_container_info()` | ✅ | 返回完整容器信息（name/image/volumes/networks/restart_policy） |
| 7 | updater 容器创建 + 运行 + auto_remove | ✅ | 容器创建成功 → 正常运行 → 退出后自动删除 |
| 8 | 完整 helper 流程 (`python -m docker_update_helper`) | ✅ | 步骤 1-3 通过（权限/socket/容器信息），步骤 4 白名单拦截（本地构建镜像），原容器完好 |

**关键发现**：

1. **A2 核心逻辑完全通过**：updater 容器可以由 app 容器通过 docker.sock 创建、运行、自动清理
2. **白名单机制正常**：本地构建镜像被正确拦截，不会误更新
3. **auto_remove 有效**：updater 容器退出后自动删除，保持"单容器体验"
4. **原容器保护有效**：即使更新流程被拦截，原容器状态不受影响（status=running）
5. **无法端到端验证 pull→create→stop→start→rename**：因为本地构建镜像无法从远程 registry pull；完整流程需在真实远程镜像环境下验证

**清理**：
- 停止并删除测试容器和 volume
- 删除临时测试脚本 `test_a2_spawn.py` / `test_a2_helper.py`
- 删除本地测试镜像 `outlook-email-a2-test:latest`

**结论**：A2 方案的核心逻辑（updater 容器创建、运行、自动清理、白名单保护）已全部验证通过。完整端到端测试（含 pull→create→stop→start→rename）需在远程镜像环境下进行。

---

### 待办：本地端到端测试指南

> 以下是用户自行在本地进行端到端测试的完整步骤，覆盖 Watchtower 模式和 Docker API 模式。

#### 前提条件

1. Docker Desktop 运行中（Engine 28.x+）
2. dev 分支最新代码
3. 端口 5002、5003 未被占用

#### 方式一：Docker API 模式测试（A2 方案核心验证）

```bash
# 1. 构建本地镜像（含 A2 代码改动）
docker compose -f docker-compose.docker-api-test.yml up -d --build

# 2. 等待容器启动（约 20 秒）
# 查看健康状态
docker ps --filter "name=outlook-dockerapi-test"

# 3. 浏览器访问
# 打开 http://localhost:5003
# 使用密码 admin123 登录

# 4. 测试验证项
# 4a. 访问 /healthz 确认 boot_id 和 version 字段
#     浏览器直接访问 http://localhost:5003/healthz
#     期望: {"status":"ok","boot_id":"...","version":"1.12.0"}

# 4b. 进入"设置"→"自动化"→"一键更新"
#     - 切换更新方式为"Docker API"
#     - 确认看到部署信息警告（本地构建提示/Docker API 可用提示）
#     - 点击"立即更新"按钮
#     期望: 弹出"镜像名不在白名单内"错误（本地构建镜像无法自动更新，这是正确行为）

# 5. 测试完毕后清理
docker compose -f docker-compose.docker-api-test.yml down -v
docker rmi outlook-email-a2-test:latest  # 清理本地测试镜像
```

**注意**：本地构建镜像无法完成完整 pull→create→stop→start→rename 流程，因为远程 registry 没有 `outlook-email-a2-test` 镜像。白名单校验会正确拦截。

#### 方式二：Watchtower 模式测试（原有功能回归验证）

```bash
# 1. 启动 app + watchtower 双容器
docker compose -f docker-compose.hotupdate-test.yml up -d

# 2. 等待容器启动（约 20 秒）
docker ps --filter "name=outlook-hotupdate-test"

# 3. 浏览器访问 http://localhost:5002
# 使用密码 admin123 登录

# 4. 测试验证项
# 4a. 进入"设置"→"自动化"→"一键更新"
#     - 确认 Watchtower 配置显示
#     - 点击"测试连通性"
#     期望: 返回"连接成功"

# 4b. 点击"检查更新"（页面顶部或设置页）
#     期望: 显示当前版本和最新版本信息

# 4c. 点击"立即更新"
#     期望: 按钮变为"等待容器重启..."，前端轮询 /healthz
#     注意: 如果已是最新版本，Watchtower 不会触发容器重建

# 5. 测试完毕后清理
docker compose -f docker-compose.hotupdate-test.yml down -v
```

#### 方式三：远程镜像 + Docker API 端到端测试（最完整，需发布新版本）

```bash
# 1. 先提交 A2 代码到 dev 分支
# 2. 合并到 main 并发布新版本（如 v1.13.0）
# 3. 等待 Docker Hub 镜像发布
# 4. 使用远程镜像启动容器

docker run -d \
  --name oep-e2e-test \
  -p 5004:5000 \
  -e SECRET_KEY=test-secret-key \
  -e LOGIN_PASSWORD=admin123 \
  -e DOCKER_SELF_UPDATE_ALLOW=true \
  -e SCHEDULER_AUTOSTART=true \
  -v /var/run/docker.sock:/var/run/docker.sock \
  guangshanshui/outlook-email-plus:v1.13.0

# 5. 浏览器访问 http://localhost:5004，登录
# 6. 设置 → 自动化 → 一键更新 → 切换到 Docker API 模式
# 7. 点击"立即更新"
#    期望:
#    - 后端创建 updater 容器 (oep-updater-xxxxx)
#    - updater 容器 pull 最新镜像
#    - 如果有新版本：stop 旧容器 → create/start 新容器 → rename → cleanup
#    - 如果已是最新：返回"镜像已是最新，无需更新"
#    - 前端检测到 boot_id 变化 → 刷新页面

# 8. 清理
docker rm -f oep-e2e-test
```

#### 关键验证检查清单

- [ ] `GET /healthz` 返回 `boot_id` + `version`
- [ ] `GET /api/system/deployment-info` 返回正确的部署信息
- [ ] `docker_api_available` 在挂载 docker.sock 时为 true
- [ ] 更新方式切换 UI 正常（Watchtower ↔ Docker API）
- [ ] 部署警告根据更新方式动态变化（Watchtower 不可达时 info vs error）
- [ ] 触发更新时 CSRF 保护正常
- [ ] 白名单校验正确拦截非白名单镜像
- [ ] updater 容器创建成功并正确退出
- [ ] 前端 waitForRestart 轮询正常（boot_id 变化检测）
- [ ] 语言切换时部署警告重渲染

#### 13. 生成功能验证提示词（给其他 AI 审查用）

**操作内容**：
- 创建 `VERIFICATION_PROMPT.md`，包含 A2 方案的完整功能验证提示词
- 覆盖 5 大类验证点（后端 API / Docker 服务 / 前端 / 安全 / 边界条件），共 30+ 个具体检查项
- 附带改动文件清单和已知限制说明
- 用于交给其他 AI 审查代码变更的完整性和正确性

**已新增文件**：
- `VERIFICATION_PROMPT.md` — 功能验证提示词

---

### 待办：项目文件归类清理（暂缓，提交后执行）

> 以下为扫描项目结构后的清理建议，待 dev 分支提交后再执行。

#### 需删除的文件

| 文件 | 原因 |
|------|------|
| `fix_format.py` | 一次性格式修复脚本，已完成使命 |
| `NUL` | Windows 空文件，已在 .gitignore |
| `EhushaokangData-codeoutlookEmailserver.log` | 日志文件（文件名异常），已在 .gitignore |
| `-p/` 空目录 | 空目录，无内容 |
| `.ruff_cache/` | Linter 缓存目录 |

#### 需移动归类的文件

| 文件 | 目标位置 |
|------|---------|
| `注册与邮箱池接口文档.md` | → `docs/API/注册与邮箱池接口文档.md` |
| `registration-mail-pool-api.en.md` | → `docs/API/registration-mail-pool-api.en.md` |
| `VERIFICATION_PROMPT.md` | → `docs/DEV/VERIFICATION_PROMPT.md` |
| `docs/2026-04-05-设置页面重构-AI执行提示词.md` | → `docs/DEV/` 或删除 |

#### .gitignore 需补充

```
.ruff_cache/
-p/
```

**执行结果**（Commit: `04824bc`）：
- ✅ 删除 `fix_format.py`
- ✅ 移动 `注册与邮箱池接口文档.md` → `docs/API/`
- ✅ 移动 `registration-mail-pool-api.en.md` → `docs/API/`
- ✅ 移动 `VERIFICATION_PROMPT.md` → `docs/DEV/`
- ✅ 移动 `设置页面重构-AI执行提示词.md` → `docs/DEV/`
- ✅ `.gitignore` 补充 `.ruff_cache/` 和 `-p/`
- 注：`NUL`、`-p/`、`.ruff_cache/`、`Ehushaokang...server.log` 已在 .gitignore 中，物理文件已被清理

---

### 历史记录：A2 方案开发期间的修改清单（已合并至 main）

> 以下修改已通过 `hotupdate-test` 分支合并到 main（2026-04-09），此处仅作历史参考。

| 文件 | 修改类型 | 说明 |
|------|---------|------|
| `outlook_web/services/docker_update_helper.py` | **新增** | updater 容器入口模块 |
| `outlook_web/services/docker_update.py` | Modified | helper 容器创建、步骤顺序调整、失败回滚 |
| `outlook_web/controllers/system.py` | Modified | A2 触发逻辑、healthz 增强、部署信息增强 |
| `static/js/main.js` | Modified | boot_id 检测、部署警告渲染、超时优化 |
| `templates/index.html` | Modified | deploymentWarnings 容器 |
| `tests/test_error_and_trace.py` | Modified | 适配 healthz 新字段 |
| `tests/test_smoke_contract.py` | Modified | 适配 healthz 新字段 |
| `docs/DEV/hot-update-ai-prompt.md` | Modified | 文档清理 + 补充 |
| `docs/DEV/hot-update-baseline.md` | Modified | 文档补充 |
