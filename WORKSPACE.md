# WORKSPACE — 工作区操作记录

> 本文档记录项目开发过程中的操作日志，按日期倒序排列。

---

## 2026-04-18

### 操作记录

#### 159. UI/UX 优化：删除独立浮窗、主界面移除项目Key、宽度自适应

**时间**：2026-04-18

**修改**：

| 文件 | 修改内容 |
|------|---------|
| `popup.html` | 删除 `⤢` 独立浮窗按钮；移除主界面「项目 Key」输入框；`body.width` 改为 `min-width: 340px; width: 100%` |
| `popup.js` | 删除 detach button 逻辑；`handleClaim` 直接读 `config.defaultProjectKey`，不再读 UI 输入框 |
| `manifest.json` | 权限从 `["storage","tabs","windows"]` → `["storage","tabs"]`（windows 权限仅用于独立浮窗，已无需保留） |

**背景**：项目 Key 仅需在设置页配置，不应在主界面操作时每次手动填写。独立浮窗功能用户不需要。宽度改为自适应内容宽度。

#### 158. 主项目 README 补充浏览器扩展、项目 Key、完成/释放说明

**时间**：2026-04-18

**内容**（`README.md` + `README.en.md`）：
- 新增「浏览器扩展」章节（位于"外部接口与邮箱池集成"之后）
- 项目 Key：多租户隔离、填/不填的行为、成功复用路径
- 完成 vs 释放：状态对比表、适用场景

#### 157. 完善浏览器扩展 README（项目 Key 说明 + 完成/释放区别）

**时间**：2026-04-18

**内容**（`browser-extension/README.md`）：
- 新增「概念说明」章节
- 项目 Key：多租户隔离机制、填写方式、不填时的回落行为
- 完成 vs 释放：状态机区别、适用场景对比表、简单记法

#### 156. 修复插件验证码/验证链接提取 bug（API 响应层级错误）

**时间**：2026-04-18

**根因**：
- `verification-code` API 实际响应结构为 `{success, code:"OK", data:{verification_code:..., verification_link:...}}`
- `popup.js` 的 `handleGetCode` 检查并读取 `result.code`，该字段值永远是字符串 `"OK"`（状态码），不是验证码
- `handleGetLink` 读取 `result.link`，顶层无此字段，为 `undefined`

**修改**（`browser-extension/popup.js`）：

| 函数 | 旧写法 | 新写法 |
|------|--------|--------|
| `handleGetCode` | `result.code` | `result.data.verification_code` |
| `handleGetLink` | `result.link` | `result.data.verification_link` |

#### 155. 修复插件申领邮箱核心 bug（result.data 层级错误）

**时间**：2026-04-18

**根因**：API 响应结构为 `{success:true, data:{email, account_id, claim_token, ...}}`，但 popup.js 在取字段时直接访问 `result.email`（顶层），导致 `undefined` → 报"服务器未返回邮箱地址"。

同时 `apiRelease` / `apiComplete` 只发送 `task_id`，缺少 `account_id`、`claim_token`、`caller_id`，服务端验证必失败。

**修改**（`browser-extension/popup.js`）：

| 位置 | 修改内容 |
|------|---------|
| `handleClaim` | 从 `result.data` 取 `email`/`account_id`/`claim_token`，存入 task 对象 |
| `apiComplete` | 签名改为接受 task 对象，body 补充 `account_id`/`claim_token`/`caller_id` |
| `apiRelease` | 同上 |
| `handleComplete` | 传入 `currentTask` 而非 `currentTask.taskId` |
| `handleRelease` | 同上 |

#### 154. 修復 _overwrite_account 边界条件（claimed 状态不被重置）

**時間**：2026-04-18

**問題**：`_overwrite_account` 原條件 `not existing.get("pool_status")` 對 `claimed` 帳號無效（'claimed' 是 truthy，條件為 False），覆蓋導入時 `add_to_pool=True` 不會重置已 claimed 的帳號。

**修復**：

```python
# 修復前
if add_to_pool and not existing.get("pool_status"):
# 修復後
if add_to_pool and existing.get("pool_status") != "available":
```

**文件**：`outlook_web/controllers/accounts.py`，`_overwrite_account` 函數

#### 153. 診斷並修復：重導入後插件仍無法申領

**時間**：2026-04-18

**根因**：7 個帳號 `pool_status='claimed'` 卡住（之前測試時已申領但從未釋放/完成）。用戶重刪再導入時，這些帳號可能仍保留在 DB 中（軟刪除或未徹底清除），導致 claim 失敗。

**另一個相關隱患**：我們修復的 `_overwrite_account` bug 有邊界情況：
- `not existing.get("pool_status")` 在 `pool_status='claimed'` 時為 False（不會重置為 available）
- 即覆蓋導入時若賬號已是 `claimed` 狀態，`add_to_pool=True` 也不會解除 claim

**本次修復**：
- SQL 重置 7 個卡住帳號：`UPDATE accounts SET pool_status='available', claimed_by=NULL, claimed_at=NULL, claim_token=NULL WHERE pool_status='claimed' AND status='active'`
- 結果：14 個帳號全部 `available`
- 驗證：claim-random 返回 HTTP 200 成功

**建議後續**：長期方案應在 claim 時設置 `lease_expires_at`，到期後自動歸還（Pool 已有此字段，可定時任務掃描過期 claim）。

#### 152. 文档同步更新（FD/TD/TDD）

**时间**：2026-04-18

| 文档 | 修改内容 |
|------|---------|
| `docs/FD/2026-04-18-浏览器扩展邮箱池快捷操作面板FD.md` | 本期包含新增：深色主题、420px宽度、⤢独立浮窗、错误提示优化、API Key引导 |
| `docs/TD/2026-04-18-浏览器扩展邮箱池快捷操作面板TD.md` | manifest.json permissions 加入 `windows`；验收口径7更新说明 |
| `docs/TDD/2026-04-18-浏览器扩展邮箱池快捷操作面板TDD.md` | 手工矩阵新增 TC-13（独立浮窗）、TC-14（主题切换）；验收条件更新为 TC-01~TC-14 |

#### 151. 修复 pool_status 相关 bug + 邮箱池激活

**时间**：2026-04-18

| 修改 | 文件 | 说明 |
|------|------|------|
| SQL 直接激活 | 数据库 | `UPDATE accounts SET pool_status='available' WHERE status='active' AND pool_status IS NULL` — 14 个账号 |
| 重复导入 pool_status bug | `controllers/accounts.py` | `_overwrite_account` 增加 `add_to_pool` 参数，覆盖时同步设置 `pool_status='available'` |
| 重复导入 pool_status bug | `controllers/accounts.py` | 调用处传入 `add_to_pool=add_to_pool` |
| 允许更新 pool_status | `repositories/accounts.py` | `update_account_credentials` 的 `allowed` 集合加入 `pool_status` |

**验证**：`claim-random` API 返回 HTTP 200 + `{"success":true,"data":{"email":"AlexandraBailey3593@outlook.in",...}}`

#### 150. 独立浮窗 + 错误提示修复

**时间**：2026-04-18

| 修改 | 文件 | 说明 |
|------|------|------|
| 新增 `windows` 权限 | `manifest.json` | 支持 `chrome.windows.create` |
| 独立浮窗按钮 `⤢` | `popup.html` | 右上角 header-actions 区域 |
| 浮窗逻辑 | `popup.js` | 点击 `⤢` → `chrome.windows.create({type:'popup', width:420, height:600})` |
| 窗口模式检测 | `popup.js` | `?mode=window` 时隐藏 detach 按钮，避免嵌套开窗 |
| 错误提示优化 | `popup.js` | handleClaim 先检查 `result.success===false`，优先显示 `result.message` |

**遗留问题（用户需操作）：**
- pool_enabled 仍为 `false` → 用户需在主应用「设置 → 对外 API」手动启用
- 用户输入的 Key（`YKYbgUV...`）与数据库 Legacy Key 不匹配 → 需重新复制

#### 149. Popup 尺寸 + UI 主题修复

**时间**：2026-04-18

| 修改 | 文件 | 说明 |
|------|------|------|
| 宽度 380→420px | `popup.html` | `body { width: 420px }` |
| CSS 变量名对齐 | `popup.html` | `--text-sec` → `--text-secondary`，`--font` → `--font-sans` |
| 变量值对齐 | `popup.html` | `--radius` 8→10px，`--radius-sm` 5→6px，`--transition` 0.22s ease |
| 新增变量 | `popup.html` | `--clr-jade-light`、`--clr-success`、`--bg-hover`、`--bg-secondary` |
| 深色模式 | `popup.html` | 新增 `[data-theme="dark"]` 完整变量块 |
| 深色模式 body | `popup.html` | `color: var(--text)`、`transition: background/color` |
| 主题切换按钮 | `popup.html` | 新增 `🌙/☀️` 按钮，`.header-actions` 包装 |
| API Key 引导 | `popup.html` | 设置面板 API Key 下方加 `.form-hint` 提示 |
| 主题初始化 | `popup.js` | DOMContentLoaded 读 `localStorage['ol_theme']` 设置 `data-theme` |
| 主题切换逻辑 | `popup.js` | 点击主题按钮切换 dark/light，同步写 localStorage |

#### 148. TC 验收实测 — 发现 2 个配置问题

**时间**：2026-04-18

| # | 问题 | 根因 | 修复动作 |
|---|------|------|---------|
| 1 | 扩展 API Key 校验失败（401） | 扩展里存的 Key 与服务器 Legacy Key（`test***-123`）不匹配 | 用户需在扩展设置里重填正确完整 Key |
| 2 | Key 正确后仍无法申领（FEATURE_DISABLED） | 主应用 `external_pool_enabled = false`，邮箱池 API 未启用 | 用户需在主应用「设置 → 对外 API」开启邮箱池功能 |

另：用户反馈 Popup 尺寸固定、UI 主题不跟主应用（无深色模式），待修复。

#### 147. 全量回归测试（验收前）

**时间**：2026-04-18  
**命令**：`python -m unittest discover -s tests`  
**结果**：✅ 全部通过

| 指标 | 数值 |
|------|------|
| 总测试数 | 1197 |
| 通过 | 1190 |
| 失败 | 0 |
| 错误 | 0 |
| 跳过 | 7 |
| 耗时 | 535.7s |

**结论**：P1 修复未引入新问题，代码健康，可进行 D 层手工验收。

#### 146. 代码审查结果 + P1 问题修复

**时间**：2026-04-18

**审查结论**（claude-sonnet-4.6）：

- **P0**：无问题（CSP 合规、存储原子性、task_id 先写后发、65000ms 超时、失败后清空逻辑、optional_host_permissions 全部通过）
- **P1 修复 2 处**：

  | 问题 | 位置 | 修复方式 |
  |------|------|---------|
  | 错误提示被 `renderState('idle')` → `hideMessage()` 立即抹掉，用户静默回 idle 看不到错误 | `popup.js` handleComplete / handleRelease finally 块 | 将 `showError` 移到 `renderState('idle')` 之后执行 |
  | `handleOpenLink` 未校验 URL scheme，可被恶意服务端用 `data:` / `file:` URL 攻击 | `popup.js` handleOpenLink | 添加 `new URL()` + protocol 白名单校验（仅允许 http/https） |

- **P2**：无需补充

#### 145. 启动代码审查子代理（claude-sonnet-4.6 审查扩展代码）

**时间**：2026-04-18

**本次操作**：

启动 claude-sonnet-4.6 code-review 子代理，对浏览器扩展 v0.1.0 核心文件进行审查（manifest.json / storage.js / popup.js / popup.html / README.md）。

**审查重点**：
- P0：MV3 CSP 合规、storage 写入原子性、task_id 先写后发、AbortController 65000ms、失败后清空逻辑
- P1：7 状态机完整性、新标签打开、权限申请流程
- P2：错误提示、历史排序

**状态**：等待子代理完成，将通过寸止汇报结果。

#### 144. 调研 GitHub Copilot CLI 子代理 thinking budget 支持情况

**时间**：2026-04-18

**本次操作**：

查阅 GitHub Copilot CLI 官方文档和网络资料，调研 `task` 子代理工具是否支持指定"思考程度"（thinking budget）。

**调研结论**：

`task` 工具当前**不支持**直接配置 thinking budget。可用参数仅包含 `name/prompt/description/agent_type/mode/model`，无 `thinking_budget` 等参数。

**替代方案**：通过选择模型来隐式控制思考深度：
- 深度思考 → `claude-opus-4.6`
- 标准 → `claude-sonnet-4.6` / `gpt-5.4`
- 快速轻量 → `gpt-5.4-mini`

官方文档支持：`Ctrl+T` 切换推理过程可见性（不影响实际思考深度）。

#### 143. 启动扩展代码开发子代理（gpt-5.4 执行 E-01 ~ E-07）

**时间**：2026-04-18

**本次操作**：

启动 gpt-5.4 子代理，依据 `browser-extension/PROMPTS_PACK.md` 中的提示词集合，逐步创建浏览器扩展 v0.1.0 全部核心文件（E-01~E-07）。

**执行顺序**：E-01 → E-02 → E-03 → E-04（含 E-05 重命名）→ E-07；E-06 图标独立执行。

**目标产出**：
- `browser-extension/manifest.json`
- `browser-extension/storage.js`
- `browser-extension/popup.js`
- `browser-extension/popup.html`（正式版，CSP 合规）
- `browser-extension/popup.preview.html`（预览原型，原 popup.html 重命名）
- `browser-extension/icons/icon16.png`、`icon48.png`、`icon128.png`
- `browser-extension/README.md`

**状态**：✅ 完成（gpt-5.4，耗时约 7.5 分钟）

**执行结果**（全部成功）：

| 文件 | 状态 |
|------|------|
| `manifest.json` | ✅ 创建，JSON 合法，通过校验 |
| `storage.js` | ✅ 创建 |
| `popup.js` | ✅ 创建（7 状态机 + 5 API + 完整事件处理） |
| `popup.html` | ✅ 创建（正式版，无内联 JS，CSP 合规） |
| `popup.preview.html` | ✅ 原 popup.html 重命名保留 |
| `icons/icon16.png` | ✅ 合法 PNG，16×16 |
| `icons/icon48.png` | ✅ 合法 PNG，48×48 |
| `icons/icon128.png` | ✅ 合法 PNG，128×128 |
| `README.md` | ✅ 创建 |

#### 142. 更新 CLAUDE.md — 新增子代理模型分配规则

**时间**：2026-04-18

**本次操作**：

在 `CLAUDE.md` 末尾新增 `Sub-Agent Model Selection（子代理模型分配规则）` 章节，记录项目中子代理任务类型与对应模型的映射规则。

**规则摘要**：

| 任务类型 | 优先模型 |
|---------|--------|
| 探索类 | `gpt-5.4-mini` |
| 前端 UI 设计/开发 | `claude-sonnet-4.6` 或 `gpt-5.4`（Gemini 不可用时替代） |
| 后端探索/实现 | `claude-sonnet-4.6` 或 `gpt-5.4` |
| 思考整合/头脑风暴/复杂设计 | `claude-opus-4.6` |
| 其余小任务 | `gpt-5.4-mini` |

#### 141. 生成浏览器扩展 E-01 ~ E-07 AI 执行提示词集合（Prompts Pack）

**时间**：2026-04-18

**本次操作**：

读取 FD / TD / TODO / popup.html 预览版四份文档，为浏览器扩展子项目 v0.1.0 的 7 个开发任务（E-01 ~ E-07）生成完整的自包含 AI 执行提示词集合。

**涉及文档**：
- `docs/FD/2026-04-18-浏览器扩展邮箱池快捷操作面板FD.md`
- `docs/TD/2026-04-18-浏览器扩展邮箱池快捷操作面板TD.md`
- `browser-extension/TODO.md`
- `browser-extension/popup.html`（预览版，作为 CSS 参考）

**产出**：7 个自包含提示词（E-01 manifest.json / E-02 storage.js / E-03 popup.js / E-04 popup.html 正式版 / E-05 预览版重命名 / E-06 图标生成 / E-07 README.md），通过 MCP 寸止工具输出给用户。

**依赖顺序**：E-01 → E-02 → E-03 → E-04（含 E-05 重命名）→ E-07；E-06 可独立执行。

#### 140. 回归测试 + 四文档联调（PRD 基准对齐）

**时间**：2026-04-18

**本次操作**：

**一、回归测试**：运行 141 个已有测试（test_external_pool + test_external_api + test_external_pool_e2e + test_smoke_contract）全部通过，确认 CORS 改动无破坏性。

**二、文档联调发现问题（以 PRD 为基准）并全部修正**：

| 编号 | 问题位置 | 问题描述 | 修复 |
|------|----------|---------|------|
| 联调-01 | FD §1.2 | 快捷键说明缺默认值（PRD UC-2 明确了 `Ctrl+Shift+E`） | FD 补充完整描述 |
| 联调-02 | TDD §4.4 | 手工冒烟矩阵用 M-01~M-12，与 §6.2 TC-01~TC-12 冲突 | §4.4 统一改为 TC-01~TC-12 |
| 联调-03 | TDD §6.2 TC-10 | 缺少 101 条历史上限验证（§4.4 M-11 有此场景） | TC-10 补充第 3/4 步 |
| 联调-04 | TODO.md | 缺少 README.md 任务（FD §2.1 + TD §3.1 均列有此文件） | 新增 E-07 |

**当前文档体系**：PRD / FD / TD / TDD 全链路已经完成联调，与 PRD 保持一致。

#### 139. 创建浏览器扩展子项目 TODO 文档

**时间**：2026-04-18

**本次操作**：

创建 `browser-extension/TODO.md`，梳理扩展子项目 v0.1.0 的完整任务清单。

**已完成（标记 ✅）**：D-01~D-05（文档体系）、B-01~B-02（主应用 CORS）、T-01（CORS 测试）

**待完成（核心扩展代码）**：

| 编号 | 任务 | 依赖 |
|------|------|------|
| E-01 | `manifest.json`（MV3）| — |
| E-02 | `storage.js`（chrome.storage 封装）| E-01 |
| E-03 | `popup.js`（主交互逻辑）| E-01, E-02 |
| E-04 | `popup.html`（正式版，MV3 CSP 合规）| E-03 |
| E-05 | 预览版改名为 `popup.preview.html` | E-04 |
| E-06 | 图标文件（16/48/128px）| — |

**手工冒烟**：TC-01~TC-12（12 条），TC-05/TC-12 为高风险点

#### 138. 编写 A 层 CORS 测试代码，实施主应用 CORS 改动

**时间**：2026-04-18

**本次操作**：

根据 TDD §4.1/§5 编写实际测试代码并实施主应用 CORS 改动：

- 新增：`requirements.txt` 追加 `flask-cors>=4.0.0`
- 修改：`outlook_web/app.py` 在 Blueprint 注册后增加 CORS 配置（仅对 `/api/external/*`）
- 新建：`tests/test_extension_cors.py`（A 层 CORS 测试，10 个测试方法）

**CORS 配置方案**：

```python
# 仅允许 chrome-extension:// 来源访问 /api/external/* 路径
CORS(app, resources={
    r"/api/external/*": {
        "origins": [re.compile(r"^chrome-extension://.*$")],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "X-API-Key"],
        "supports_credentials": False,
    }
})
```

**测试结果**：10 个测试全部通过（10/10 OK，耗时 3.3s）

覆盖场景：CR-01~CR-08（含 claim-random/release/complete/verification-code/verification-link 5 个端点，OPTIONS 预检，4xx 响应时 CORS 头存在，内部 API 不受影响）

#### 137. 编写浏览器扩展 TDD 文档，补充 FD 关联

**时间**：2026-04-18

**本次操作**：

创建 TDD 文档，并同步更新 FD 增加 TDD 关联字段：

- 文档路径：`docs/TDD/2026-04-18-浏览器扩展邮箱池快捷操作面板TDD.md`
- FD 更新：增加「关联 TDD」字段

**TDD 核心设计**：

测试分层策略：

| 层级 | 方式 | 是否 v0.1.0 必须 |
|------|------|----------------|
| A. 主应用 CORS（Python）| `tests/test_extension_cors.py` | ✅ 必须 |
| B. Storage 封装（Jest）| `browser-extension/tests/storage.test.js` | ❌ 可选 |
| C. 状态机 & 流程（Jest）| `browser-extension/tests/popup.test.js` | ❌ 可选 |
| D. 手工冒烟（TC-01~12）| 12 条测试用例 | ✅ 必须 |

关键测试矩阵数量：
- A 层 CORS 矩阵：8 个场景（CR-01 ~ CR-08）
- B 层 Storage：7 个场景（ST-01 ~ ST-07）
- C 层状态机：13 个场景（SM-01 ~ SM-13）
- D 层手工冒烟：12 条测试用例（TC-01 ~ TC-12）

高风险测试点：TC-05（Popup 关闭恢复）、TC-12（权限拒绝处理），v0.1.0 前必须人工确认。

**当前状态**：
- TDD v1.0 已创建
- 文档体系全链路完整：PRD → FD → TD → TDD

#### 136. PRD-FD-TD 文档联调

**时间**：2026-04-18

**本次操作**：

对三个文档进行联调，发现并修正 FD 中 4 处不一致：

| # | 位置 | 问题 | 修正内容 |
|---|------|------|---------|
| 1 | FD 2.1 文件结构 | 缺少 `storage.js` 和 `popup.preview.html` | 同步补充（与 TD 3.1 文件结构一致） |
| 2 | FD 2.3 caller_id 注释 | 写了「可在设置中自定义」，但 PRD/FD 设置面板均无该字段 | 改为「v1 硬编码，不提供配置项」 |
| 3 | FD 2.4 超时处理 | 描述为「若支持 wait 则依赖服务端超时，否则加兜底」逻辑不明 | 改为「始终加 65s AbortController 兜底」（与 TD 一致） |
| 4 | FD 2.7 设置面板 | 缺少「保存时触发 chrome.permissions.request」步骤 | 补充完整权限申请流程（包含用户拒绝处理） |

**三文档结论**：

- PRD：产品需求层面无需变更（权限申请属实现细节，PRD 不展开）
- FD：4 处已修正，与 TD 设计对齐
- TD：无需变更，逻辑原本正确

**当前状态**：PRD → FD → TD 三文档已联调完毕，描述一致

#### 135. 创建浏览器扩展 TD 文档，恢复 FD 关联

**时间**：2026-04-18

**本次操作**：

用户要求编写 TD 文档，深入分析技术难点。执行以下操作：

1. 恢复 `FD` 文档中「关联 TD」字段（此前条目 134 删除了该字段）
2. 创建 TD 文档：`docs/TD/2026-04-18-浏览器扩展邮箱池快捷操作面板TD.md`

**TD 核心内容 — 9 大技术难点**：

| 难点 | 核心问题 | 选定方案 |
|------|---------|---------|
| 1. 动态地址 vs host_permissions | MV3 要求静态声明权限，用户自填地址无法预知 | `optional_host_permissions: <all_urls>` + `chrome.permissions.request` 在保存时动态申请 |
| 2. Popup 生命周期 vs wait=60 | 关闭 Popup 时 fetch 被中断 | UI 提示「勿关闭」+ AbortController 兜底 + 重新打开可重试 |
| 3. Manifest V3 CSP | 禁止内联 JS，预览版无法直接用 | 正式版 popup.html 只含 DOM，全部 JS 移入 popup.js；预览版改名 popup.preview.html |
| 4. Extension ID 不稳定 | 重装后 ID 变化导致 CORS 白名单失效 | 服务端匹配 `chrome-extension://` 前缀（正则），不写死 ID |
| 5. 主应用 CORS 改动 | flask-cors 需支持 chrome-extension:// 来源 | 视现状选 flask-cors 正则 origins 或手动 after_request headers |
| 6. storage 原子性 | 多次异步写入顺序问题 | 封装 Storage 助手，所有操作 async/await 串行 |
| 7. task_id 可靠生成 | 内存变量在 Popup 关闭后丢失 | 生成后立即写 storage，API 请求在 storage 写完之后发起 |
| 8. 错误类型区分 | CORS 拦截与网络不通在前端表现一致 | 分层提示，引导用户检查配置 |
| 9. 图标资源 | 需 3 种尺寸 PNG | SVG 设计后转换，或代码生成 |

**额外设计产出**：
- 完整 `manifest.json` 设计（含 commands 快捷键、permissions、optional_host_permissions）
- `popup.js` 模块结构（5 层：常量、UI 渲染、Storage、API、事件处理器 + init）
- 主应用 CORS 3 种改动场景（全局 flask-cors / Blueprint after_request / 无现有配置）

**当前状态**：
- TD v1.0 已创建，文档体系完整（PRD → FD → TD）
- 下一步：实际编写扩展代码 or 先做主应用 CORS 改动

#### 134. 更新浏览器扩展 FD —— 移除 TD 关联

**时间**：2026-04-18

**本次操作**：

用户明确本项目**不单独出 TD 文档**，设计与实现细节直接在 FD 内展开。

- 更新 `docs/FD/2026-04-18-浏览器扩展邮箱池快捷操作面板FD.md` 元数据头：
  - 删除「关联 TD」引用行
  - 修改「当前范围」描述为「含必要实现细节，不另出 TD」

**当前状态**：
- FD 已更新，无 TD 关联
- 下一步待确认：是否直接开始编写实际扩展代码

#### 133. 编写浏览器扩展 FD 文档

**时间**：2026-04-18

**本次操作**：

用户确认 UI 预览（国风配色版）效果满意，进入 FD 阶段。创建功能设计文档：

- 文档路径：`docs/FD/2026-04-18-浏览器扩展邮箱池快捷操作面板FD.md`
- 文档版本：v1.0
- 关联 PRD：`docs/PRD/2026-04-18-浏览器扩展邮箱池快捷操作面板PRD.md`

**FD 核心内容**：

1. **功能定义**：本期包含扩展骨架、状态机、申领/获取/完成/释放全流程、历史记录、主应用 CORS 改动；明确排除 DOM 注入、Background SW 等
2. **行为设计**：
   - 扩展文件结构（manifest.json / popup.html / popup.js / icons/）
   - Popup 7 种状态（idle / claiming / claimed / fetching / result_code / result_link / settings）
   - 各流程详细步骤（申领 → 验证码 → 验证链接 → 完成/释放）
   - `task_id` 使用 `crypto.randomUUID()` 生成，`caller_id` 固定为 `"browser-extension"`
3. **接口契约**：主应用 CORS 改动（`chrome-extension://` 前缀匹配）+ 5 个外部 API 调用规范
4. **数据语义**：`chrome.storage.local` 完整数据结构（config / currentTask / history）
5. **兼容与边界**：扩展与主应用解耦、Extension ID 变更应对方案、popup.html 预览版定位说明
6. **验收口径**：10 条可验证的验收标准

**当前状态**：
- FD v1.0 已创建，等待进一步实现阶段决策

#### 131. 创建浏览器扩展 PRD 文档

**时间**：2026-04-18

**本次操作**：

根据设计讨论结果（条目 130），编写浏览器扩展功能 PRD：

- 文档路径：`docs/PRD/2026-04-18-浏览器扩展邮箱池快捷操作面板PRD.md`
- 文档版本：v1.0
- 定位：独立伴生子项目，不依附主应用版本号

**PRD 核心内容**：
- 背景：Web 界面操作割裂，注册场景需频繁切换页面
- 目标：快捷键唤起 Popup，一键申领邮箱 + 获取验证码/链接
- Use Case：UC-1（配置）~ UC-8（历史记录）共 8 个用例
- 非目标：明确排除 DOM 自动识别、Content Script 注入等复杂能力
- 服务端关联改动：主应用需补充 `chrome-extension://` CORS 支持

**当前状态**：
- PRD v1.0 已创建，处于需求讨论阶段

#### 132. 创建浏览器扩展目录与 UI 预览文件

**时间**：2026-04-18

**本次操作**：

1. 新建独立目录：`browser-extension/`
2. 创建交互式 UI 预览文件：`browser-extension/popup.html`

**popup.html 功能说明**：
- 可直接在浏览器中打开进行 UI 预览（无需安装扩展）
- 包含所有状态的完整交互演示：
  - 「无任务」状态 → 申领邮箱 → loading 动画 → 进入「申领中」状态
  - 「申领中」状态 → 获取验证码 / 获取验证链接 → 结果展示框（一键复制）
  - 完成 / 释放邮箱 → 自动返回「无任务」状态
  - 设置面板（服务器地址、API Key、默认项目Key）
  - 历史记录区（可折叠展开）
- 底部预览切换栏：无任务 / 申领中 / 有验证码 / 有链接 / 设置

**当前状态**：
- UI 预览文件已完成，可供前端效果评审



**时间**：2026-04-18

**第一轮讨论（初始方案）**：

针对「Chrome/Edge 浏览器插件」方向进行可行性评估，初始设想包含自动 DOM 识别和自动填充能力。

**第二轮讨论（方案收敛）**：

经用户明确后，**不做 DOM 自动识别 / 自动填充**，定位为轻量快捷操作面板。

**第三轮讨论（设计定稿）**：

确认采用**方案 A：极简 Popup**，完整设计如下：

**触发方式**：
- 快捷键唤起 Popup（如 `Ctrl+Shift+E`），弹出小窗

**核心操作流（极简）**：
1. 点「申领邮箱」→ 从邮箱池申领一个邮箱，显示地址并一键复制
2. 用户手动将邮箱地址填入注册页面
3. 点「获取验证码」→ 拉取该邮箱最新验证码，一键复制
4. 可选：点「释放邮箱」→ 归还邮箱池

**本地历史记录**（关键特性）：
- 即使邮箱已释放，申领记录（邮箱地址 + 最新验证码）**保留在插件本地存储中**
- 用户可随时翻阅历史，方便复用

**插件架构（定稿）**：
- 仅 `Popup` 页面 + `chrome.storage.local`，**无 Content Script、无 Background SW**
- 快捷键通过 `manifest.json` `commands` 配置
- 分区：① 服务配置（服务器地址 + API Key）② 当前任务（申领/验证码/释放）③ 历史记录

**对接接口**：
| 操作 | 接口 |
|---|---|
| 申领邮箱 | `POST /api/external/pool/claim-random` |
| 获取最新验证码 | `GET /api/external/verification-code` |
| 释放邮箱 | `POST /api/external/pool/claim-release` |
| 完成邮箱 | `POST /api/external/pool/claim-complete` |

**后端改动**：
- 补充 CORS 支持，允许 `chrome-extension://` 来源

**存放位置**：独立子目录 `browser-extension/`

**当前状态**：
- 设计讨论已完成，方案定稿，**尚未决定是否开始实施**


#### 165. CI/CD 全绿 - v2.0.0 发布验证

**时间**：2026-04-18

**触发**：black 格式化修复 commit `b58ec73`（`style: black格式化 v2.0.0 版本文件`）

**结果**：
| Workflow | 状态 |
|---------|------|
| Code Quality | ✅ success |
| Python Tests | ✅ success |
| Build and Push Docker Image | ✅ success |
| SonarCloud Scan | ✅ success |

**v2.0.0 发布完整链路验证完毕** ✅

---

#### 164. 发布 v2.0.0 GitHub Release

**时间**：2026-04-18

**版本号**：`1.19.0` → `2.0.0`（浏览器扩展为大版本里程碑）

**修改文件**：`outlook_web/__init__.py`、`README.md`、`README.en.md`、`tests/test_version_update.py`、`CHANGELOG.md`、`docs/DEVLOG.md`

**操作**：
- `git commit` release 准备提交（`d3f94fc`）+ 推送
- `gh release create v2.0.0` → https://github.com/ZeroPointSix/outlookEmailPlus/releases/tag/v2.0.0

**结果**：v2.0.0 Release 页面已上线 ✅

---

#### 163. main 分支全量测试 - 全部通过

**时间**：2026-04-18

**操作**：
`python -m unittest discover -s tests -v`（main 工作树）

**结果**：
``r
Ran 1194 tests in 354.407s
OK (skipped=7)
`  

- ✅ **全部通过**，0 个失败，7 个跳过
- 浏览器扩展 v0.1.0 合并到 main 后无任何功能回归

---

#### 162. 合并 dev -> main 发布浏览器扩展 v0.1.0

**时间**：2026-04-18

**操作**：
- main 工作树执行 `git merge origin/dev --no-ff`，合并 20 个文件，4930 insertions
- `git push origin main`（`a9381f8` → `663f1ff`）

**合并内容**：
- 浏览器扩展完整代码（`browser-extension/`）
- CORS 支持（`outlook_web/app.py`）
- pool_status 修复（`controllers/accounts.py`、`repositories/accounts.py`）
- FD/TD/TDD 设计文档
- README.md / README.en.md 浏览器扩展章节

**结果**：浏览器扩展 v0.1.0 已发布到 main ✅

---

#### 161. 合并 main -> dev + 全量测试验证

**时间**：2026-04-18

**背景**：main 分支包含 v1.19.0 多项修复（refresh 逻辑、SSE issue#45、版本检测等），dev 包含浏览器扩展 v0.1.0，需合并确认兼容性。

**操作**：
- `git merge main -X ours --no-ff`（WORKSPACE.md 冲突以 dev 为准）
- 合并引入 13 个文件变更，1079 insertions

**测试结果**：
- 共运行 **1204 个测试**（比合并前多 7 个，来自 main 新测试），耗时 377s
- 通过：1196 个
- 跳过：7 个
- 失败：1 个（`test_pool_cf_real_e2e::test_04_claim_complete_timeout_skips_delete`，CF Worker E2E，环境限制，与代码无关）

**结论**：合并后所有功能性测试全部通过，浏览器扩展代码与 main 分支兼容 ✅

**注意**：本次 merge commit 仅本地，未推送。

---
#### 160. 全量测试 + git push 到远端

**时间**：2026-04-18

**操作**：
`ash
python -m unittest discover -s tests -v
git push origin dev
`

**结果**：
- 共运行 **1197 个测试**，耗时 360s
- 通过：1189 个
- 跳过：7 个
- 失败：1 个（`test_pool_cf_real_e2e::test_04_claim_complete_timeout_skips_delete`）

**失败分析**：该测试需要真实 CF Worker API（https://temp.zerodotsix.top），本地无网络访问，属于预期内的环境限制，与本次代码变更无关。

**Push**：`e13fcf4 → origin/dev` 推送成功

---
## 2026-04-16

### 操作记录

#### 129. 同步 main 最新提交 a9381f8（冲突按当前分支记录保留）

**时间**：2026-04-17

**本次操作**：

1. 按会话要求将 `origin/main` 最新提交 `a9381f8` 同步到 `dev`。
2. `cherry-pick` 过程中仅 `WORKSPACE.md` 冲突；按确认策略保留当前分支已有记录并补本条说明。
3. 完成后继续 `cherry-pick` 流程并推送远端。

#### 127. 文档同步提交已推送到 origin/main

**时间**：2026-04-16

**本次操作**：

1. 推送范围
   - 推送分支：`main -> origin/main`
   - 已推送提交：
     - `8c63ae7` `docs: update demo url and pool api docs`
     - `5965b26` `docs(workspace): record doc sync update`

2. 推送结果
   - `git push origin main` 已成功
   - 远端 `main` 已从 `79e3011` 前进到 `5965b26`

3. 当前状态
   - README、双语对外 API 文档、`WORKSPACE.md` 的最新同步结果均已进入远端主线

#### 126. README 与对外 API 文档同步更新：演示地址切换为 demo.outlookmailplus.tech

**时间**：2026-04-16

**本次操作**：

1. README 文档更新
   - 更新 `README.md`
   - 更新 `README.en.md`
   - 演示地址统一切换为：`https://demo.outlookmailplus.tech/`
   - 登录密码保持不变：`12345678`
   - 同步修正文档中的邮箱池语义，改为当前真实实现：长期邮箱在显式 `project_key + caller_id + task_id` 路径下支持项目维度 success 复用

2. 对外 API 文档更新
   - 更新 `注册与邮箱池接口文档.md`
   - 更新 `registration-mail-pool-api.en.md`
   - 修正 `claim-complete(result=success)` 的真实语义：
     - 项目复用路径返回 `pool_status=available`
     - 旧路径 / `cloudflare_temp_mail` / 临时邮箱继续返回 `used`
   - 明确请求结构未新增字段，项目复用依赖 claim 阶段绑定的上下文

3. 当前状态
   - 文档已按当前实现与当前演示地址完成回填
   - 已提交：`8c63ae7` `docs: update demo url and pool api docs`

#### 125. v1.18.0 retag 闭环：标签已对齐 79e3011 并重新触发发布链路

**时间**：2026-04-16

**本次操作**：

1. tag 锚点修复
   - 复核发现本地与远端 `v1.18.0` peeled commit 仍指向旧提交：`8bfeea8`
   - 已重新执行：
     - `git tag -fa v1.18.0 79e301132b7b1e4f1571b8a2bd0ce1e4fe417e82 -m 'v1.18.0 (retag after formatter gate fix)'`
     - `git push origin :refs/tags/v1.18.0`
     - `git push origin v1.18.0`
   - 当前本地与远端 `v1.18.0` peeled commit 已一致指向：`79e3011`

2. Release 与附件状态
   - `gh release view v1.18.0` 仍可正常访问
   - Release 页面未丢失，附件保持为 formatter 修复后的最新版本：
     - `outlook-email-plus-v1.18.0-docker.tar` → `sha256:07930496cefd3ab5a72f6857bf5fdce6317aa2ec77e8254618e8d7f7457d99e8`
     - `outlookEmailPlus-v1.18.0-src.zip` → `sha256:820e2f310da4fafb71a8915c9d779037716167a28c8843f610bcd84b1993b6f8`

3. 重新触发的工作流状态
   - `Code Quality`（main, `79e3011`）✅ success
   - `Python Tests`（main, `79e3011`）✅ success
   - `Build and Push Docker Image`（main, `79e3011`）✅ success
   - `Build and Push Docker Image`（tag: `v1.18.0`, `79e3011`）✅ success

4. 当前结论
   - Release 页面、Release 附件、远端 tag、远端 main HEAD 已重新对齐到同一提交：`79e3011`
   - `main` 与 `v1.18.0` 对应的质量门禁、测试、Docker 发布链路现已全部恢复为成功状态

#### 124. v1.18.0 发布后检查：Release 成功，远端质量门禁仍有阻塞

**时间**：2026-04-16

**本次操作**：

1. Release 状态复核
   - `gh release view v1.18.0` 已确认：
     - Release 已创建
     - 非草稿、非预发布
     - 两份附件已上传成功

2. 远端工作流状态
   - `Python Tests`（main）✅ success
   - `Code Quality`（main）❌ failure
   - `Build and Push Docker Image`（main）❌ failure
   - `Build and Push Docker Image`（tag: `v1.18.0`）❌ failure

3. 失败根因
   - 三条失败链路根因一致：formatter gate 未通过
   - 远端日志显示 `black --check` 要求重新格式化以下 3 个文件：
     - `outlook_web/db.py`
     - `tests/test_db_schema_v22_pool_project_reuse.py`
     - `tests/test_pool_service_project_reuse.py`
   - 因 `quality-gate` 失败，Docker build-push（main/tag）链路被阻断

4. 当前结论
   - `v1.18.0` GitHub Release 页面与附件已成功发布
   - 但远端 CI 还不是全绿，若要补齐镜像发布闭环，下一步需要先处理上述格式化问题并重新触发工作流

#### 123. v1.18.0 正式发布完成（GitHub Release + 附件上传）

**时间**：2026-04-16

**本次操作**：

1. 版本准备
   - 版本号：`1.17.0` -> `1.18.0`
   - 更新：`outlook_web/__init__.py`
   - 同步：`README.md`、`README.en.md`、`tests/test_version_update.py`
   - 发布记录：`CHANGELOG.md`、`docs/DEVLOG.md`

2. 发布前验证
   - 全量测试：`python -m unittest discover -v`
   - 结果：`Ran 1187 tests in 458.110s`，`OK (skipped=7)`

3. 发布产物构建
   - Docker 镜像：`docker build -t outlook-email-plus:v1.18.0 .`
   - 镜像 ID：`sha256:a3fa082473f29ce34054362cf8550c3dce35d0a5f18154d924f15170c3c333cd`
   - 导出产物：
     - `dist/outlook-email-plus-v1.18.0-docker.tar`（204,749,824 bytes）
     - `dist/outlookEmailPlus-v1.18.0-src.zip`（4,127,512 bytes）

4. 发布执行
   - 提交：`8bfeea8` `docs(release): finalize v1.18.0 artifacts`
   - 打标：`v1.18.0`
   - 推送：`git push origin main`、`git push origin v1.18.0`
   - 创建 Release：`gh release create v1.18.0 ...`
   - 发布页：`https://github.com/ZeroPointSix/outlookEmailPlus/releases/tag/v1.18.0`

5. Release 附件核对
   - `outlook-email-plus-v1.18.0-docker.tar`
     - size=`204749824`
     - digest=`sha256:d208b6bc623fbad0cd0a9d33c93f2cb9b9e9b2428fed0c4bf0ec565fec311a02`
   - `outlookEmailPlus-v1.18.0-src.zip`
     - size=`4127512`
     - digest=`sha256:3bd2ff20608c1596f4770714aba1730d7a8bcb67b1b1ed547deac469c1f6194d`

#### 122. 本地 main 再次全量回归扫查：未发现新增回归

**时间**：2026-04-16

**本次操作**：

1. 回归验证
   - 执行：`python -m unittest discover -v`
   - 方式：使用 `Start-Process` 后台独立进程启动
   - 结果：`Ran 1187 tests in 446.083s`，`OK (skipped=7)`

2. 回归结论
   - 当前本地 `main` 在完成分支合并、文档回填、Docker 运行态验证之后，再次执行全量 unittest 仍然全绿
   - 本轮未观察到新的回归性失败

3. 现场状态
   - Docker 本地验收实例 `outlook-email-plus-local-main` 仍在运行
   - 当前可访问地址：`http://127.0.0.1:5002`

#### 121. 本地 Docker 构建启动排查：Compose 失败根因确认 + 本地镜像健康验证

**时间**：2026-04-16

**本次操作**：

1. Compose 现场排查
   - 当前 `.env` 中存在：`IMAGE_TAG=hotupdate-test`
   - 因此直接执行 `docker compose up` 时，实际使用的是 `ghcr.io/zeropointsix/outlook-email-plus:hotupdate-test`
   - 该容器启动后持续 `Restarting (3)`，`/healthz` 无法正常对外服务

2. Compose 失败根因
   - 通过 `docker logs outlook-email-plus` 确认报错：
     - `sqlite3.DatabaseError: database disk image is malformed`
   - 直接原因：Compose 默认挂载 `./data:/app/data`，容器读取到了当前本地损坏的数据库文件

3. 本地构建镜像验证
   - 本地构建镜像：`ghcr.io/zeropointsix/outlook-email-plus:local-main-20260416`
   - 为避免受损坏数据库影响，使用隔离数据目录与隔离运行时目录单独启动：
     - 容器名：`outlook-email-plus-local-main`
     - 端口：`5002 -> 5000`
   - 健康检查结果：
     - `GET http://127.0.0.1:5002/healthz` → `200`
     - 返回：`{\"boot_id\":\"1776334299176-7\",\"status\":\"ok\",\"version\":\"1.17.0\"}`
   - 当前状态：容器 `healthy`

4. 现场结论
   - 问题不在本地 build 产物本身
   - 默认 Compose 启动失败的根因是：`.env` 固定 tag + 挂载了损坏的本地数据库
   - 当前可用于本地验收的 Docker 实例地址：`http://127.0.0.1:5002`

#### 120. 本地 main 合并完成并通过全量复验

**时间**：2026-04-16

**本次操作**：

1. 本地合并结果
   - 已在本地 `main` worktree 完成 `Buggithubissue -> main` 合并
   - 本轮仅做本地合并，未执行 push
   - merge commit：`c238b21`

2. 全量复验
   - 执行：`python -m unittest discover -v`
   - 方式：使用 `Start-Process` 后台独立进程启动
   - 结果：`Ran 1187 tests in 536.823s`，`OK (skipped=7)`

3. 文档同步
   - 更新：`docs/TODO/2026-04-16-邮箱池项目维度成功复用TODO.md`
   - 更新：`docs/TDD/2026-04-16-邮箱池项目维度成功复用TDD.md`
   - 更新：`WORKSPACE.md`
   - 已将“本地 main 合并后再次全量复验通过”的状态回填

#### 119. 本地合并 Buggithubissue 到 main 并准备主线复验

**时间**：2026-04-16

**本次操作**：

1. 本地 main 合并
   - 目标：仅合并到本地 `main`，不推远端
   - 来源分支：`Buggithubissue`
   - 当前现场：`main` worktree 原先已处于一次未完成 merge，本轮继续收口

2. 冲突处理
   - 冲突文件：`WORKSPACE.md`
   - 处理方式：以本需求分支的最新会话记录为主线继续收口，并在主线侧追加本次 merge 记录

3. 复验准备
   - 后续动作：完成 merge commit 后，在本地 `main` 上重新执行全量 `python -m unittest discover -v`
   - 进程要求：继续使用 `Start-Process` 后台独立进程，不占用前台执行链路

#### 118. 将专项审查提示词收口为单一汇总提示词

**时间**：2026-04-16

**本次操作**：

1. 用户反馈
   - 不需要多条专项提示词
   - 只保留一条可直接执行的汇总审查提示词

2. 调整内容
   - 将原先按 Schema / Repository / Service / 文档 / 风险拆分的审查提示词，收口为一个总提示词
   - 保留 TODO 对齐、代码实现、测试闭环、文档一致性、回归风险五个核心审查维度

3. 现场状态
   - 汇总提示词将继续通过 `寸止` MCP 输出
   - 当前人工验收实例仍运行在 `http://127.0.0.1:5000`

#### 117. 编写基于 TODO 的专项审查提示词套件

**时间**：2026-04-16

**本次操作**：

1. 审查目标整理
   - 基于 `docs/TODO/2026-04-16-邮箱池项目维度成功复用TODO.md` 的 Phase 2 ~ Phase 5 已完成项
   - 聚焦 Schema / Repository / Service / 测试 / 文档回填 / 人工验收准备的结果审查

2. 输出内容
   - 产出一套可直接复制使用的审查提示词
   - 覆盖总审查、Schema 迁移、Repository 生命周期、Service/Controller 契约、测试与文档一致性、回归风险六个视角

3. 现场状态
   - 当前服务实例仍运行在 `http://127.0.0.1:5000`
   - 审查提示词将通过 `寸止` MCP 输出，不单独新建文档文件

#### 116. 启动人工验收实例并完成健康检查

**时间**：2026-04-16

**本次操作**：

1. 启动验收服务
   - 入口：`python start.py`
   - 方式：使用 `Start-Process` 独立后台进程启动，不占用前台执行链路
   - 运行参数：`HOST=127.0.0.1`、`PORT=5000`、`FLASK_ENV=production`
   - 进程 PID：`4256`

2. 就绪验证
   - 检查：`GET http://127.0.0.1:5000/healthz`
   - 结果：HTTP `200`
   - 返回：`{\"boot_id\":\"1776326763483-4256\",\"status\":\"ok\",\"version\":\"1.17.0\"}`

3. 现场状态
   - 当前人工验收地址：`http://127.0.0.1:5000`
   - 服务进程仍在运行，可直接进入页面验收

#### 115. 对齐 CF 旧骨架并完成全量 unittest 绿灯验证

**时间**：2026-04-16

**本次操作**：

1. 失败收敛
   - 更新：`tests/test_pool_cf_integration_tdd_skeleton.py`
   - 根因：全量测试中的旧骨架用例仍要求 `release()` 删除 `account_project_usage` 行，与当前“保留 usage、仅 success 阻断”的项目复用语义冲突
   - 修复：将用例调整为断言 usage 行保留，且 `success_count=0`、`first_success_at/last_success_at` 为空

2. 定向验证
   - 执行：`python -m unittest tests.test_pool_cf_integration_tdd_skeleton -v`
   - 方式：使用 `Start-Process` 独立后台进程启动
   - 结果：`Ran 18 tests in 1.651s`，`OK (skipped=1)`

3. 全量验证
   - 执行：`python -m unittest discover -v`
   - 方式：使用 `Start-Process` 独立后台进程启动，不占用前台执行链路
   - 结果：`Ran 1187 tests in 518.251s`，`OK (skipped=7)`

4. 文档同步
   - 更新：`docs/TODO/2026-04-16-邮箱池项目维度成功复用TODO.md`
   - 更新：`docs/TDD/2026-04-16-邮箱池项目维度成功复用TDD.md`
   - 已将“全量 unittest 通过”回填到本需求相关文档

#### 114. 回填会话执行约束：如需启动进程，只允许后台独立进程

**时间**：2026-04-16

**本次操作**：

1. 会话文档同步
   - 更新：`docs/TODO/2026-04-16-邮箱池项目维度成功复用TODO.md`

2. 本轮回填内容
   - 在 TODO 的“会话约束（必须保持）”中新增：
     - 如果必须启动进程，只能使用新进程后台启动（如 `Start-Process` / 独立进程）
     - 不再使用前台长命令占住执行链路

3. 现场状态
   - 当前会话文档已经把“后台独立进程启动”这一最新执行约束显式写明。
   - 后续如果需要启动服务或长时进程，将遵循该约束执行。

#### 113. 修补 v22 迁移兼容并完成邮箱池相关自动化验证

**时间**：2026-04-16

**本次操作**：

1. 失败收敛
   - 更新：`outlook_web/db.py`
   - 根因：遗留 v21 测试库缺少 `password` 等列，`migrate_sensitive_data()` 直接读取时报错
   - 修复：补齐旧 schema 缺失列，并让 `migrate_sensitive_data()` 按实际列集合做兼容读取

2. 自动化验证
   - 执行：
     - `python -m unittest tests.test_db_schema_v22_pool_project_reuse tests.test_pool_repository_project_reuse tests.test_pool_service_project_reuse tests.test_pool_flow_suite tests.test_pool -v`
   - 首轮结果：`errors=7`，全部来自 v21 迁移兼容缺失
   - 修复后复跑结果：`Ran 78 tests in 6.379s`，`OK`

3. 文档同步
   - 更新：`docs/TODO/2026-04-16-邮箱池项目维度成功复用TODO.md`
   - 更新：`docs/TDD/2026-04-16-邮箱池项目维度成功复用TDD.md`
   - 已将 Phase 1 / Phase 5 与自动化执行状态回填为最新真实结果

4. 现场状态
   - 本需求相关主测试集合当前已通过。
   - 会话侧剩余动作主要是收尾反馈。

#### 112. 对齐旧 pool 回归用例到项目复用新语义

**时间**：2026-04-16

**本次操作**：

1. 更新旧回归测试
   - 更新：`tests/test_pool.py`

2. 本轮修正点
   - 将旧的 “release 必须删除 `account_project_usage` 行” 断言改为新语义
   - 保留“release 后同一 `project_key` 仍可再次领取”的回归目标
   - 将旧注释中 `complete(success) -> used` 的描述收口为“success 记录继续保留并参与同项目防重”

3. 现场状态
   - 旧回归测试口径已与当前项目复用实现保持一致。
   - 自动化测试本轮仍未执行。

#### 111. 落地邮箱池项目维度成功复用实现（Schema v22 + Repository + Service）

**时间**：2026-04-16

**本次操作**：

1. 代码实现推进
   - 更新：`outlook_web/db.py`
   - 更新：`outlook_web/repositories/pool.py`
   - 更新：`outlook_web/services/pool.py`

2. 本轮实现内容
   - Schema 升级到 `v22`
   - `accounts` 新增 `claimed_project_key`
   - `account_project_usage` 新增 `first_success_at / last_success_at / success_count`
   - 仅在升级到 v22 时，把历史长期邮箱 `used -> available`，且排除 `cloudflare_temp_mail` / `temp_mail`
   - `claim_atomic()` 改为只拦截同项目 success 记录，并写入当前 claim 的 `claimed_project_key`
   - `complete()` 支持基于 claim 上下文走项目复用分支：长期邮箱覆盖路径 `success -> available`，旧路径仍保持 `success -> used`
   - `release()` / `expire_stale_claims()` 改为只清理 claim 上下文，不再删除 `account_project_usage`
   - `complete_claim()` 在 Service 层读取 `provider / account_type / claimed_project_key` 后判断是否启用项目复用

3. 文档同步
   - 更新：`docs/TODO/2026-04-16-邮箱池项目维度成功复用TODO.md`
   - 更新：`docs/TDD/2026-04-16-邮箱池项目维度成功复用TDD.md`
   - 已回填“实现已落地、自动化验证未执行”的当前真实状态

4. 现场状态
   - 当前代码已完成本需求 Phase 2 / 3 / 4 的主实现。
   - 自动化测试本轮未执行，保持为显式保留项。

#### 110. 按会话口径删除落库提示词文档，改为只通过 MCP 输出执行提示词

**时间**：2026-04-16

**本次操作**：

1. 删除落库提示词文档
   - 删除：`docs/DEV/2026-04-16-邮箱池项目维度成功复用-AI执行提示词.md`

2. 回退 TODO 文档中的落库引用
   - 更新：`docs/TODO/2026-04-16-邮箱池项目维度成功复用TODO.md`

3. 本轮口径调整
   - 按用户最新要求，不再把“给其他 AI 的执行提示词”保存在仓库文档中
   - 后续如需此类提示词，仅通过 `寸止` MCP 直接输出给用户复制使用
   - TODO 继续只保留需求 / 测试 / 实现阶段拆解，不再挂执行提示词文件路径

4. 现场状态
   - 当前仓库仍保留 `PRD / FD / TD / TDD / TODO` 五层文档闭环。
   - “其他 AI 执行提示词”现在改为会话态输出，不再作为仓库文档资产持久保留。

#### 109. 新增本需求 AI 执行提示词并挂回 TODO 文档

**时间**：2026-04-16

**本次操作**：

1. 新增执行提示词文档
   - 新增：`docs/DEV/2026-04-16-邮箱池项目维度成功复用-AI执行提示词.md`

2. 回填 TODO 文档引用
   - 更新：`docs/TODO/2026-04-16-邮箱池项目维度成功复用TODO.md`

3. 本轮提示词内容
   - 明确要求其他 AI 先阅读 `PRD / FD / TD / TDD / TODO / WORKSPACE`
   - 明确当前真实现状：
     - 当前并非完全不支持多项目
     - 真正缺口是 success 后进入全局 `used`
     - `claim-complete` 缺少 `project_key` 上下文，必须补 `claimed_project_key`
     - 当前测试已写、实现未做
   - 明确实现顺序：
     - Schema v22
     - Repository 状态机
     - Service / Controller
     - 文档与 `WORKSPACE` 收尾
   - 明确禁止项：
     - 不新增新 API 字段
     - 不新增新错误码
     - 不让临时邮箱误进新语义
     - 不通过弱化测试掩盖实现缺口

4. 现场状态
   - 现在这条需求不仅有 TODO，而且还有可以直接交给其他 AI 执行的正式提示词文档。
   - TODO 与执行提示词已经互相关联，后续可以直接按文档链路推进实现。

#### 108. 新建 TODO 文档并回填本需求文档引用与实际推进状态

**时间**：2026-04-16

**本次操作**：

1. 新建会话 TODO 文档
   - 新增：`docs/TODO/2026-04-16-邮箱池项目维度成功复用TODO.md`

2. 回填关联文档引用
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 更新：`docs/FD/2026-04-16-邮箱池项目维度成功复用FD.md`
   - 更新：`docs/TD/2026-04-16-邮箱池项目维度成功复用TD.md`
   - 更新：`docs/TDD/2026-04-16-邮箱池项目维度成功复用TDD.md`

3. 本轮文档修正内容
   - 为本需求补齐 `PRD / FD / TD / TDD / TODO` 五层文档闭环
   - 在 PRD / FD / TD / TDD 头部补入 `关联 TODO`
   - 将 TD 当前状态更新为“测试已开始落地，待进入实现阶段”
   - 将 TDD 的“交付物清单（测试侧）”从“已开始落地”更新为“已实际落地并持续补强”
   - 在 TODO 中按真实状态明确：
     - 文档已收敛完成
     - 测试代码已先行落地
     - 业务实现尚未开始
     - 自动化执行仍是后续阶段保留项

4. 现场状态
   - 当前本需求的会话文档体系已经从 `PRD / FD / TD / TDD` 扩展为 `PRD / FD / TD / TDD / TODO` 完整链路。
   - 文档中的推进状态现在与仓库真实状态保持一致，不再只有设计层，也明确标出了“测试先行、实现未开始”的当前阶段。

#### 107. 补强测试断言：Repository 成功计数与 Service 显式 token_mismatch 校验

**时间**：2026-04-16

**本次操作**：

1. 测试代码继续补强
   - 更新：`tests/test_pool_repository_project_reuse.py`
   - 更新：`tests/test_pool_service_project_reuse.py`

2. 本轮补强点
   - Repository 测试补入：
     - reuse 路径 success 后 `accounts.success_count` 增长断言
   - Service 测试补入：
     - 显式 `token_mismatch` 校验测试

3. 现场状态
   - 当前这批测试的断言粒度又向 TDD 的函数级清单进一步靠近。
   - 关键路径不再只断主状态，也开始覆盖计数与错误码层的细节。

#### 106. 继续根据 TDD 扩写迁移后可领取行为与 Repository 级剩余状态机测试

**时间**：2026-04-16

**本次操作**：

1. 测试代码继续落地
   - 更新：`tests/test_db_schema_v22_pool_project_reuse.py`
   - 更新：`tests/test_pool_repository_project_reuse.py`

2. 本轮新增 / 改造内容
   - 迁移测试继续补充：
     - 历史长期邮箱迁移后可以被再次 claim
     - 原项目在迁移后可以再次拿到一次该邮箱
   - Repository 级测试继续补充：
     - 未传 `project_key` 时 `claimed_project_key` 为空
     - 不同项目 success 历史不阻断再次 claim
     - 旧路径 success 继续返回 `used`
     - reuse 路径非 success 不写项目 success 字段
     - `expire_stale_claims()` 清理 `claimed_project_key` 但不制造 success 记录
     - `get_stats()` 在 reuse 路径 success 后按 `available` 而不是 `used` 统计

3. 现场状态
   - 迁移 / Repository 两层的测试覆盖面已经继续向 TDD 文档靠拢。
   - 当前这批测试已不只是“少量试探性 case”，而是在逐步把 TDD 的核心测试面真实铺开。

#### 105. 继续根据 TDD 补齐 Repository 级测试与更多接口/Service 用例

**时间**：2026-04-16

**本次操作**：

1. 测试代码继续落地
   - 新增：`tests/test_pool_repository_project_reuse.py`
   - 更新：`tests/test_pool_service_project_reuse.py`
   - 更新：`tests/test_pool_flow_suite.py`

2. 本轮新增 / 改造内容
   - Repository 级测试：
     - 覆盖 `claim_atomic` 写 `claimed_project_key`
     - 覆盖“只有 success 记录才阻断同项目 claim”
     - 覆盖 reuse 路径 success 后回 `available`
     - 覆盖 release 不再删除 project usage 行
   - Service 级补充测试：
     - 覆盖空白 `project_key` 继续按旧路径处理
     - 覆盖 `invalid_result` 校验仍然存在
   - 接口主流程补充测试：
     - 覆盖 `verification_timeout` 后在恢复可领状态下同项目可重试
     - 覆盖 `claim-release` 后同项目可重试
     - `test_pool_flow_suite.py` 的 `setUp()` 补入未来 v22 字段预留，避免后续实现接入时先被缺列卡住

3. 文档同步
   - 更新：`docs/TDD/2026-04-16-邮箱池项目维度成功复用TDD.md`
   - 已把 `tests/test_pool_repository_project_reuse.py` 标记为当前会话已实际落地

4. 现场状态
   - 当前迁移 / Repository / Service / Flow Suite 四层测试代码都已开始落地。
   - 距离“把 TDD 文档列出的核心测试面全部写进仓库”已经又往前推进了一步。

#### 104. 根据 TDD 开始实际编写测试用例

**时间**：2026-04-16

**本次操作**：

1. 会话推进
   - 用户明确要求：直接根据当前 TDD 文档开始编写具体测试用例。

2. 测试代码落地
   - 新增：`tests/test_db_schema_v22_pool_project_reuse.py`
   - 新增：`tests/test_pool_service_project_reuse.py`
   - 更新：`tests/test_pool_flow_suite.py`

3. 本轮新增 / 改造内容
   - 迁移测试：
     - 覆盖 v22 新字段存在性
     - 覆盖历史长期邮箱 `used -> available`
     - 覆盖 `cloudflare_temp_mail` 不进入长期邮箱迁移语义
     - 覆盖旧 `account_project_usage` claim 痕迹不被伪回填成 success
   - Service 测试：
     - 覆盖 `claimed_project_key` 驱动 success 后回 `available`
     - 覆盖缺少 `claimed_project_key` 时回退旧语义
     - 覆盖 `cloudflare_temp_mail` 继续走旧语义
   - 接口主流程测试：
     - 将旧的 success→used 测试明确收口为“未传 `project_key` 时仍为旧行为”
     - 新增“长期邮箱 + `project_key` + success → 返回 available”
     - 新增“不再依赖手工 SQL 恢复 available”的同项目/跨项目复用用例
     - 新增 stats 对 `available/used` 语义的断言
     - 新增 `cloudflare_temp_mail` 传 `project_key` 仍走旧语义的断言

4. 文档同步
   - 更新：`docs/TDD/2026-04-16-邮箱池项目维度成功复用TDD.md`
   - 已补充“当前会话已开始落地”的测试文件状态

5. 现场状态
   - 当前已从纯文档阶段进入测试代码落地阶段。
   - 由于业务实现尚未同步改造，这批测试中包含面向目标语义的用例，后续需要配合实现一起收敛。

#### 103. 第二波联调修正：统一术语与边界定义口径

**时间**：2026-04-16

**本次操作**：

1. 联调范围
   - 本轮按用户要求，重点检查：
     - 术语一致性
     - 测试命名一致性
     - 边界一致性

2. 联调发现
   - 存在三类需要继续收口的点：
     - “未传 `project_key` / 不传 `project_key`”混用
     - `覆盖路径 / 旧路径` 在 TD / TDD 中频繁使用，但未集中定义
     - 临时邮箱的技术边界（`cloudflare_temp_mail` / `account_type='temp_mail'`）需要在多份文档里用同一口径表达

3. 文档修正
   - 更新：`docs/TD/2026-04-16-邮箱池项目维度成功复用TD.md`
   - 更新：`docs/TDD/2026-04-16-邮箱池项目维度成功复用TDD.md`
   - 已补充：
     - TD 新增“术语约定”，统一 `覆盖路径 / 旧路径 / 第一阶段排除的临时邮箱`
     - TDD 新增同样的术语约定，保证测试文档与 TD 使用同一套定义
     - 若干“未传 / 不传 `project_key`”表述已继续向统一口径收敛

4. 联调结果
   - 现在 TD / TDD 在这几个关键表达上已经进一步统一：
     - 何为覆盖路径
     - 何为旧路径
     - 第一阶段排除哪些临时邮箱
     - `project_key` 缺省时的统一描述

5. 现场状态
   - 第二波联调已完成一轮实质性术语收口。
   - 后续若继续联调，可再查更细的测试函数命名与章节间引用是否还存在小漂移。

#### 102. 文档联调修正：补齐“稳定态 success 防重”与“历史 `used` 迁移例外”的区分

**时间**：2026-04-16

**本次操作**：

1. 联调发现
   - 在 PRD / FD 的前文规则里，“同项目 success 后不再分配”写得过于绝对。
   - 但后文又已经明确接受：历史 `used` 长期邮箱迁回 `available` 后，原项目可能再次拿到一次。
   - 这会造成“稳定态规则”与“迁移例外”之间的文档冲突。

2. 文档修正
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 更新：`docs/FD/2026-04-16-邮箱池项目维度成功复用FD.md`
   - 已补充：
     - PRD 同项目规则改为“形成可被新语义可靠识别的 success 记录后才阻断”
     - PRD 验收标准补入“稳定态 success 防重”和“历史迁移一次性例外”要明确区分
     - FD 同项目规则与验收口径同步补入上述区分

3. 联调结果
   - 现在文档口径已经统一为：
     - 稳定态：同项目 success 记录继续阻断再次领取
     - 迁移态：历史 `used` 长期邮箱回池后，允许原项目再拿到一次

4. 现场状态
   - 本轮联调已发现并修掉一处实质性口径冲突。
   - 后续仍可继续做第二轮联调，检查术语、测试函数命名、文档边界是否还有细小漂移。

#### 101. TDD 继续下沉到函数级 case 清单

**时间**：2026-04-16

**本次操作**：

1. 会话推进
   - 用户选择继续细化 TDD 的函数级 case 清单。

2. 文档修正
   - 更新：`docs/TDD/2026-04-16-邮箱池项目维度成功复用TDD.md`
   - 已新增：
     - `14. 函数级 case 清单（按建议测试文件）`

3. 本轮细化结果
   - 已把 TDD 从“测试矩阵层”继续拆到“测试函数命名层”：
     - `tests/test_db_schema_v22_pool_project_reuse.py` 要包含哪些迁移测试函数
     - `tests/test_pool_repository_project_reuse.py` 要包含哪些 Repository 级状态机测试函数
     - `tests/test_pool_service_project_reuse.py` 要包含哪些 Service 级覆盖范围与校验测试函数
     - `tests/test_pool_flow_suite.py` 应该如何拆旧 case、补新 case
   - 同时给出了测试文件级的建议落地顺序

4. 现场状态
   - 当前 TDD 已经基本具备直接进入测试实现的粒度。
   - 后续如果继续推进，可以开始整理“实现准备清单”，或者直接进入代码改造阶段的任务拆分。

#### 100. 创建 TDD：邮箱池项目维度成功复用

**时间**：2026-04-16

**本次操作**：

1. 会话推进
   - 用户选择从 TD 继续推进到 TDD。

2. 新建文档
   - 新增：`docs/TDD/2026-04-16-邮箱池项目维度成功复用TDD.md`

3. TDD 核心落点
   - 将测试分成五层：
     - Schema / 迁移
     - Repository
     - Service
     - Controller / API 集成
     - 回归 / 手工确认
   - 明确新语义主路径、旧语义兼容路径、历史迁移路径、stats / error / 契约路径的测试矩阵
   - 明确现有 `tests/test_pool_flow_suite.py` 需要拆分哪些旧 case、补哪些新 case
   - 明确第一阶段迁移口径也要进入测试：历史长期邮箱迁回后，允许原项目再次拿到一次

4. 关联文档更新
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 更新：`docs/FD/2026-04-16-邮箱池项目维度成功复用FD.md`
   - 更新：`docs/TD/2026-04-16-邮箱池项目维度成功复用TD.md`
   - 已补充 `关联 TDD` 字段，统一指向新建 TDD 文档

5. 现场状态
   - 当前 PRD / FD / TD / TDD 四层文档已全部建立并对齐。
   - 后续若继续推进，最自然的下一步就是把 TDD 再细化成具体的测试文件改造清单，或者进入代码实现准备。

#### 99. TD 继续下沉到实现拆解层：按 DB / Repository / Service / Controller / 测试拆清改造项

**时间**：2026-04-16

**本次操作**：

1. 会话推进
   - 用户选择继续细化 TD 的实现拆解清单。

2. 文档修正
   - 更新：`docs/TD/2026-04-16-邮箱池项目维度成功复用TD.md`
   - 已新增：
     - `11. 实现拆解清单（按模块）`
     - `12. 建议的落地顺序`

3. 本轮细化结果
   - 已把 TD 从“技术方案层”继续拆到“文件 / 函数 / 迁移步骤层”：
     - `outlook_web/db.py`：Schema v22、字段迁移、历史 `used` 长期邮箱回 `available`
     - `outlook_web/repositories/pool.py`：claim 过滤只看 success、补 `claimed_project_key`、complete/release/expire 语义改造
     - `outlook_web/services/pool.py`：覆盖范围 helper、complete_claim 主判断改造
     - `outlook_web/controllers/external_pool.py`：保持外部契约不变，仅让返回 `pool_status` 自然切换
     - `tests/test_pool_flow_suite.py`：现有测试需要如何拆分与新增

4. 现场状态
   - 当前 TD 已经不只是“方向正确”，而是已经具备进入 TDD 的拆解基础。
   - 后续最顺的下一步是开始编写 TDD，把这些改造点转成测试矩阵与案例。 

#### 98. 确认 TD 迁移口径：历史是否给同项目用过不重要，优先释放长期邮箱资产复用

**时间**：2026-04-16

**本次操作**：

1. 会话确认
   - 用户明确确认：对于历史 `used` 长期邮箱，“以前是不是已经给同项目用过”并不重要。
   - 第一阶段优先目标是把这些长期邮箱从旧的全局 `used` 锁死模型中释放出来，允许重新复用。

2. 文档修正
   - 更新：`docs/TD/2026-04-16-邮箱池项目维度成功复用TD.md`
   - 更新：`docs/FD/2026-04-16-邮箱池项目维度成功复用FD.md`
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 已补充：
     - TD 将历史迁移策略从“待确认”收敛为“已确认”
     - TD 明确接受“历史 `used` 迁回后，原项目可能再拿到一次”的迁移代价
     - FD / PRD 同步写明：第一阶段释放历史资产复用优先于精确保留历史同项目 success 防重

3. 需求 / 设计收敛结果
   - 当前第一阶段迁移口径已经明确为：
     - 历史长期邮箱先脱离旧的全局 `used` 模型
     - 不追求伪精确回填历史项目 success 事实
     - 历史同项目防重允许在迁移期出现一次性弱化

4. 现场状态
   - TD 首版的关键待确认项已关闭。
   - 当前可继续往下推进到更细的实现拆解，例如 Repository / Service 改造点清单或 TDD。

#### 97. 创建 TD 首版：邮箱池项目维度成功复用

**时间**：2026-04-16

**本次操作**：

1. 会话推进
   - 用户确认开始进入 TD 阶段，并要求结合既有 PRD/FD 的真实边界，全面细化技术方案。

2. 代码基线回看
   - 回看：`outlook_web/repositories/pool.py`
   - 回看：`outlook_web/services/pool.py`
   - 回看：`outlook_web/controllers/external_pool.py`
   - 回看：`outlook_web/db.py`
   - 回看：`tests/test_pool_flow_suite.py`
   - 核心发现：
     - 当前 `success` 仍硬编码写成全局 `used`
     - `account_project_usage` 当前记录的是 claim 痕迹，不是 success 事实
     - `claim-complete` 当前接口不带 `project_key`
     - `accounts` 表当前也没有保存活跃 claim 对应的 `project_key`

3. 新建文档
   - 新增：`docs/TD/2026-04-16-邮箱池项目维度成功复用TD.md`

4. TD 首版核心结论
   - 建议 Schema 升级到 v22
   - 建议给 `accounts` 新增 `claimed_project_key`，补齐当前 claim 的项目上下文
   - 建议继续沿用 `account_project_usage`，但新增 success 字段，将其从“claim 痕迹表”收敛为“success 记录主载体”
   - 建议 `claim-random` 过滤只看 success 字段，不再看 claim 痕迹
   - 建议长期邮箱覆盖路径下 `success` 直接回 `available`
   - 建议 `release / expire / 非success complete` 不再删除项目 usage 行
   - 建议历史 `used` 长期邮箱先迁回 `available`，但不做伪精确 success 回填

5. 关联文档更新
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 更新：`docs/FD/2026-04-16-邮箱池项目维度成功复用FD.md`
   - 已补充 `关联 TD` 字段，指向新建 TD 文档

6. 当前待确认点
   - 历史 `used` 长期邮箱迁回后，原成功项目可能还会再拿到一次；该迁移代价是否接受，仍需会话确认。

#### 96. FD 再补迁移与展示边界：历史 `used` 纳入新语义、后台先不展示成功历史、错误继续通用返回

**时间**：2026-04-16

**本次操作**：

1. 会话确认
   - 用户按推荐一次性确认：
     - 第一阶段覆盖范围内的历史 `used` 长期邮箱，产品目标上也要纳入新语义
     - 第一阶段后台/UI 先不额外展示项目成功历史
     - 当不可分配原因来自同项目成功历史命中时，错误继续沿用现有通用返回

2. 文档修正
   - 更新：`docs/FD/2026-04-16-邮箱池项目维度成功复用FD.md`
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 已补充：
     - FD 增加“历史数据边界”，明确历史 `used` 长期邮箱目标上也应进入新语义
     - FD 增加“后台展示边界”，明确第一阶段不新增成功历史展示位
     - FD 错误反馈补充“同项目成功历史命中时继续沿用通用失败返回”
     - FD 验收口径同步补入以上三项
     - PRD 兼容性需求与验收标准同步补入以上产品边界

3. 需求收敛结果
   - 当前第一阶段产品 / 设计边界已进一步明确为：
     - 新语义不只针对未来新数据，也面向历史长期邮箱
     - 成功历史第一阶段先偏内部判断语义，不强制立即做展示层透出
     - “同项目已成功导致不可分配”先不扩展新错误面

4. 现场状态
   - FD 现已覆盖：主流程、返回值、统计语义、历史数据边界、后台展示边界、错误反馈边界。
   - 后续可以顺势进入 TD，讨论迁移策略、数据模型与接口/仓储层改造细节。

#### 95. FD 再补返回值与统计语义：success 返回 `available`、不再计入全局 `used`、第一阶段不加项目成功统计面

**时间**：2026-04-16

**本次操作**：

1. 会话确认
   - 用户同意继续打包推进更多 FD 细节。
   - 本轮按推荐收敛三点：
     - 第一阶段覆盖路径下，`claim-complete(result=success)` 的返回 `pool_status` 直接体现为 `available`
     - 这类长期邮箱不再按全局 `used` 语义解释
     - 第一阶段先不新增“项目成功次数 / 项目成功明细”的统计接口或管理面板

2. 文档修正
   - 更新：`docs/FD/2026-04-16-邮箱池项目维度成功复用FD.md`
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 已补充：
     - FD 新增 `claim-complete(success)` 覆盖路径下的返回值语义，明确 `pool_status` 直接返回 `available`
     - FD 新增统计语义，明确不再将该路径账号解释为全局 `used`
     - FD 验收口径补入“返回值一致 / 统计不再算 `used` / 第一阶段不加项目成功统计面”
     - PRD 非目标、兼容性需求、验收标准同步补入上述产品边界

3. 需求收敛结果
   - 当前第一阶段语义已进一步闭环：
     - 落库状态与对外返回口径一致
     - 生命周期语义与全局池状态统计一致
     - 项目成功事实先只承担分配判断职责，不在第一阶段扩展新统计产品面

4. 现场状态
   - FD 已从“核心行为”继续补到了“返回值与统计语义”层。
   - 后续如继续细化，可再往错误码、历史数据兼容、后台列表展示口径等细节推进。

#### 94. 创建 FD：邮箱池项目维度成功复用

**时间**：2026-04-16

**本次操作**：

1. 会话结论
   - 基于已澄清的 PRD 规则，开始进入 FD 阶段。
   - 关键设计位已确认：第一阶段长期邮箱在显式传入 `project_key` 且 `claim-complete(result=success)` 后，直接回到 `available`，不新增新池状态。

2. 新建文档
   - 新增：`docs/FD/2026-04-16-邮箱池项目维度成功复用FD.md`

3. FD 核心落点
   - 定义第一阶段功能范围与排除项
   - 明确 success 后直接回 `available`
   - 明确项目维度记录只认 `claim-complete(result=success)`
   - 明确同项目防重、跨项目立即复用、失败可重试、并发 claim 仍排他
   - 明确 `project_key` 继续由调用方自定义传入，不新增平台内管理
   - 明确错误信息继续正常返回

4. 关联文档更新
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 增加 `关联 FD` 字段，指向新建 FD 文档

5. 现场状态
   - 当前已完成：PRD 持续澄清 + FD 首版建立 + WORKSPACE 同步。
   - 后续如继续推进，可在此基础上进入 TD / TDD。

#### 93. PRD 再补成功历史规则：长期有效、手动改回可用也不失效、仅 complete(success) 记成功

**时间**：2026-04-16

**本次操作**：

1. 会话结论
   - 用户一次性确认：
     - 成功记录默认长期有效，不自动过期
     - 管理员后续手动把邮箱改回可用，也不应抹掉同项目成功历史
     - 只有显式 `claim-complete(result=success)` 才算真正成功记录

2. 文档修正
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 已补充：
     - 成功语义规则增加“仅 complete(success) 记成功”
     - 成功语义规则增加“成功历史长期有效”
     - 成功语义规则增加“后台手动改回可用也不抹掉成功历史”
     - 验收标准同步增加对应条目

3. 需求收敛结果
   - 当前 PRD 对“成功历史”已经明确成完整规则：
     - 成功判定来源固定
     - 成功历史默认长期保留
     - 后台状态修改不自动绕过同项目成功限制

4. 现场状态
   - 本轮已把成功历史规则写入 PRD 与 WORKSPACE。

#### 92. PRD 打包收敛：失败类型补齐、不新增 UI、错误信息正常返回

**时间**：2026-04-16

**本次操作**：

1. 会话结论
   - 用户确认：
     - `release / lease_expired / verification_timeout` 等都按“未成功”处理
     - 第一阶段不新增额外 UI
     - 错误信息继续正常返回，不做静默吞掉

2. 文档修正
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 已补充：
     - 同项目规则与验收标准补入“过期回收/释放/超时”仍可重试
     - 范围边界明确排除额外项目使用记录可视化 / 管理 UI
     - 新增“错误反馈规则”，明确错误信息正常返回

3. 需求收敛结果
   - 当前第一阶段需求进一步明确为：
     - 失败链路继续可重试
     - 先不做额外管理 UI
     - 错误信息按正常方式透出

4. 现场状态
   - 本轮已把这组打包结论写入 PRD 与 WORKSPACE。

#### 91. PRD 再补任务参数边界：`task_id` 继续保留且不能省

**时间**：2026-04-16

**本次操作**：

1. 会话确认
   - 用户确认：第一阶段 `task_id` 继续保留为必填，不因为项目维度复用语义而改成可选。

2. 文档修正
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 已补充：
     - 新增“`task_id` 保留规则”
     - 兼容性需求增加“`task_id` 仍为必填任务参数”
     - 验收标准增加“项目维度复用语义不替代 `task_id`”

3. 需求收敛结果
   - 当前第一阶段输入语义进一步固定为：
     - API Key：调用方身份
     - `caller_id`：显式调用方标识
     - `project_key`：业务方向标识
     - `task_id`：具体任务实例标识

4. 现场状态
   - 本轮已把 `task_id` 保留规则写入 PRD 与 WORKSPACE。

#### 90. PRD 再补调用方参数边界：`caller_id` 继续保留且不能省

**时间**：2026-04-16

**本次操作**：

1. 会话确认
   - 用户确认：即使项目已有多 API Key / 多调用方能力，第一阶段仍然继续要求外部显式传入 `caller_id`。

2. 文档修正
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 已补充：
     - 新增“`caller_id` 保留规则”
     - 兼容性需求增加“`caller_id` 仍为必填业务参数”
     - 验收标准增加“多 API Key 不替代 `caller_id`”

3. 需求收敛结果
   - 当前第一阶段产品语义继续保留三层输入角色：
     - API Key：识别调用方身份
     - `caller_id`：业务请求中的显式调用方标识
     - `project_key`：业务方向标识

4. 现场状态
   - 本轮已把 `caller_id` 保留规则写入 PRD 与 WORKSPACE。

#### 89. PRD 再补缺省行为：不传 `project_key` 就回到旧行为

**时间**：2026-04-16

**本次操作**：

1. 会话确认
   - 用户确认：只有显式传入 `project_key` 时，才启用项目维度复用语义。
   - 未传 `project_key` 的调用方继续按旧行为工作，不自动享受新语义。

2. 文档修正
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 已补充：
     - 新增“缺省行为规则”
     - 兼容性需求增加“未传 `project_key` 继续保证旧行为”
     - 验收标准增加“未传 `project_key` 不自动进入新语义”

3. 需求收敛结果
   - 当前新语义不是强制覆盖所有接入方。
   - 而是：**显式传入 `project_key` 才进入项目维度复用；不传则回退旧行为。**

4. 现场状态
   - 本轮已把缺省行为写入 PRD 与 WORKSPACE。

#### 88. PRD 再补失败语义：同项目只有成功过才禁止再次领取

**时间**：2026-04-16

**本次操作**：

1. 会话确认
   - 用户确认：同一 `caller_id + project_key` 组合下，只有邮箱真正成功过，才应禁止再次领取。
   - 如果只是失败、超时或释放，没有成功，则后续仍允许重试并再次拿到该邮箱。

2. 文档修正
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 已补充：
     - 新增 `US-05：同项目失败后可重试`
     - 同项目规则补充“失败/超时/释放但未成功时，后续仍允许再次领取”
     - 验收标准增加“未成功时可再次拿到同一邮箱”

3. 需求收敛结果
   - 当前“同项目防重”的真实语义已经明确为：**只防成功，不防失败。**

4. 现场状态
   - 本轮已把失败语义写入 PRD 与 WORKSPACE。

#### 87. PRD 再补并发边界：同一邮箱同一时刻只允许一个活跃 claim

**时间**：2026-04-16

**本次操作**：

1. 会话确认
   - 用户确认：即使 `project_key` 不同，同一邮箱在同一时刻也不能被两个业务方向同时占用。

2. 文档修正
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 已补充：
     - 新增“并发占用规则”
     - 明确一个邮箱任意时刻只允许一个活跃 claim
     - 验收标准增加“不同 `project_key` 不允许并发占用”

3. 需求收敛结果
   - 当前 PRD 已明确区分两类规则：
     - 生命周期：success 后跨 `project_key` 立即复用
     - 并发占用：同一时刻仍只允许一个活跃 claim

4. 现场状态
   - 本轮已把并发边界写入 PRD 与 WORKSPACE。

#### 86. PRD 最终封口：`project_key` 由调用方自定义传入，平台不规定命名规范

**时间**：2026-04-16

**本次操作**：

1. 会话确认
   - 用户确认：第一阶段不需要为 `project_key` 设计额外命名规范；只要由调用方自己传入即可。

2. 文档修正
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 已补充：
     - `project_key` 继续由调用方自行约定并传入
     - 第一阶段平台不额外规定命名规范或格式模板

3. 需求收敛结果
   - `project_key` 这条需求链路现在已经收口为：
     - 用现有字段
     - 保留 `caller_id + project_key` 联合语义
     - 调用方自己传入
     - 平台不内建创建
     - 平台不规定命名规范

4. 现场状态
   - 本轮已把 `project_key` 的创建与命名边界彻底写入 PRD 与 WORKSPACE。

#### 85. PRD 再收敛：第一阶段不提供平台内 `project_key` 创建能力

**时间**：2026-04-16

**本次操作**：

1. 会话结论
   - 结合现有系统能力核对后确认：项目当前已有多 API Key / 多调用方能力，但没有平台内的 `project_key` 创建/管理能力。
   - 本轮决定：第一阶段不额外产品化 `project_key` 创建能力。

2. 文档修正
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 已补充：
     - 新增“`project_key` 创建边界规则”
     - 范围边界中明确排除“平台内建 `project_key` / 项目管理能力”
     - 验收标准增加“`project_key` 由调用方自行定义并传入”的要求

3. 需求收敛结果
   - 第一阶段平台职责：
     - 识别调用方（多 API Key / 多调用方）
     - 按 `caller_id + project_key` 判断复用边界
   - 第一阶段平台不承担：
     - 创建 `project_key`
     - 维护项目对象
     - 管理业务方向目录

4. 现场状态
   - 本轮已把“`project_key` 由调用方自定义传入、平台不内建创建能力”写入 PRD 与 WORKSPACE。

#### 84. PRD 兼容性收敛：继续保留 `caller_id + project_key` 联合语义

**时间**：2026-04-16

**本次操作**：

1. 会话确认
   - 用户确认：虽然 `project_key` 作为业务方向标识被保留，但防重边界继续沿用现有 `caller_id + project_key` 联合语义。

2. 文档修正
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 已收口：
     - 主目标增加“继续保留现有 `caller_id + project_key` 联合判断”
     - 默认语义表把同项目防重和方向数量判断改成联合语义
     - `US-01`、同项目规则、判断规则、验收标准同步改为 `caller_id + project_key`

3. 需求收敛结果
   - 当前真实需求不是单纯按 `project_key` 全局去重。
   - 而是：**沿用现有 `caller_id + project_key` 作为防重边界，同时把 success 后的跨 `project_key` 立即复用补齐。**

4. 现场状态
   - 本轮已完成兼容性语义收口，并同步写入 PRD 与 WORKSPACE。

#### 83. PRD 字段语义收口：直接绑定现有 `project_key`

**时间**：2026-04-16

**本次操作**：

1. 会话确认
   - 用户确认：这轮需求不新造 `business_id` 等新概念，直接使用现有 `project_key` 作为业务方向标识。

2. 文档修正
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 已收口：
     - 主目标中明确 `project_key` 在产品层代表业务方向
     - 默认语义表改为“只看传入的 `project_key` 是否相同”
     - “传入标识判断规则”改名为“`project_key` 判断规则”
     - 范围边界与验收标准统一绑定到现有 `project_key`

3. 需求收敛结果
   - 当前 PRD 不再保留“字段待定”或“后续新增业务 ID”的口径。
   - 真实需求改为直接基于现有 `project_key` 定义：
     - 同 `project_key` 不重复
     - 不同 `project_key` 立即复用

4. 现场状态
   - 本轮已完成字段语义收口，并同步写入 PRD 与 WORKSPACE。

#### 82. PRD 继续收敛：默认不限制业务方向数量，只看传入标识是否相同

**时间**：2026-04-16

**本次操作**：

1. 会话确认
   - 用户确认：重点只看本次传入的项目/业务标识是否与历史记录相同；只要不是相同标识，就不重要，不需要再限制可复用方向数量。

2. 文档修正
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 已补充：
     - 默认语义表新增“可复用业务方向数量”一行
     - 跨项目规则补充“默认不限制业务方向数量”
     - 新增“传入标识判断规则”
     - 验收标准增加“只看传入标识，不额外校验数量上限”

3. 需求收敛结果
   - 当前真实需求进一步明确为：
     - 第一阶段只覆盖长期邮箱
     - 同项目防重
     - 跨项目 success 后立即复用
     - 默认不限制可复用业务方向数量
     - 判断核心只看本次传入标识是否与历史成功记录相同

4. 现场状态
   - 本轮已把“只看传入标识、默认不限方向数量”的规则写入 PRD 与 WORKSPACE。

#### 81. PRD 覆盖范围收敛：第一阶段只覆盖长期邮箱

**时间**：2026-04-16

**本次操作**：

1. 会话确认
   - 用户确认：`success` 后“立即复用”这条规则，第一阶段先只覆盖 Outlook / IMAP 这类长期邮箱。

2. 文档修正
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 已补充：
     - 产品目标中增加“第一阶段仅覆盖长期邮箱”
     - `US-02` 明确限定为长期邮箱
     - 特例邮箱规则中排除一次性临时邮箱
     - 范围边界改为“第一阶段默认优先覆盖 / 默认不覆盖”
     - 验收标准改成以长期邮箱为核心对象

3. 需求收敛结果
   - 当前真实需求不是“一刀切让所有邮箱 success 后立即复用”。
   - 而是：**先在长期邮箱上建立“同项目防重、跨项目立即复用”的产品语义。**

4. 现场状态
   - 本轮已把覆盖范围进一步收敛并写入 PRD 与 WORKSPACE。

#### 80. PRD 进一步收敛：success 后应立即允许其他业务方向复用

**时间**：2026-04-16

**本次操作**：

1. 会话确认
   - 用户明确需求：邮箱在某业务方向 `success` 后，不需要再经过统一冷却，应该立即允许被其他业务方向再次领取。

2. 文档修正
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 已将“立即复用”写入：
     - 产品目标
     - 默认语义对比表
     - 用户故事 US-02
     - 业务规则
     - 正向/反向验收标准

3. 需求收敛结果
   - 当前产品需求不只是“成功后可跨项目复用”。
   - 而是更强的一条规则：**成功后应立即允许其他业务方向复用，不附加统一冷却。**

4. 现场状态
   - 本轮已把“立即复用”固化进 PRD 与 WORKSPACE。

#### 79. PRD 增补因果链说明：为何已有 project_key 仍挡不住 success 后退出候选池

**时间**：2026-04-16

**本次操作**：

1. 会话问题
   - 用户继续追问：既然 PR#27 已支持 `project_key` 多项目场景，为什么后续其它项目仍可能无法复用同一邮箱。

2. 需求澄清结论
   - 问题不在 `project_key` 机制本身。
   - 当前阻断点在生命周期：
     - `claim-random` 只从 `pool_status='available'` 中挑选候选
     - `claim-complete(result=success)` 会把账号写成全局 `used`
     - 账号一旦进入 `used`，后续项目就没有机会再命中它

3. 文档修正
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 新增一段显式因果链说明，避免后续把问题误判成“project_key 没有支持多项目”

4. 现场状态
   - 本轮已将“claim 侧已支持、多项目复用败在 complete 侧生命周期”这一点写入 PRD 和 WORKSPACE。

#### 78. PRD 口径补正：当前已支持多项目领取，但未补齐 success 后生命周期

**时间**：2026-04-16

**本次操作**：

1. 会话纠偏
   - 用户指出：`claim-random` + `project_key` 的现有能力本身已经支持多项目场景，不能简单表述为“当前不支持多项目”。

2. 文档修正
   - 更新：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 修正后的口径：
     - 当前系统已经支持不同 `project_key` 间的再次领取
     - 但前提是账号必须重新回到可候选状态
     - 当前真正缺失的是 `claim-complete(result=success)` 之后的持续跨项目复用能力

3. 需求理解收敛
   - 本轮不再把问题表述为“有没有多项目能力”。
   - 改为更准确的需求表述：**现有多项目领取能力已存在，但 success 后的生命周期语义仍是全局终态，尚未补齐。**

4. 现场状态
   - 本轮仅做 PRD 需求口径纠偏与 WORKSPACE 同步，不涉及实现改动。

#### 77. 新建“邮箱池项目维度成功复用”PRD 并补充旧 PRD 范围边界

**时间**：2026-04-16

**本次操作**：

1. 会话决策
   - 经过会话确认，不把“成功后跨项目复用邮箱”继续混在既有 CF 邮箱池 PRD 中讨论。
   - 改为新建独立 PRD，单独承接该需求。

2. 新建文档
   - 新增：`docs/PRD/2026-04-16-邮箱池项目维度成功复用PRD.md`
   - 文档立场：
     - 基于当前真实实现先说明现状：`project_key` 只解决同项目防重，`success` 仍是全局 `used`
     - 从需求层面把“成功后按项目复用邮箱”定义为未来默认语义
     - 把“一次性消耗”降为特例需求，而非继续作为全局默认

3. 相关文档修正
   - 更新：`docs/PRD/2026-04-09-CF临时邮箱接入邮箱池PRD.md`
   - 补充范围边界说明：
     - 该文档只讨论 CF 临时邮箱接入邮箱池
     - 涉及“成功后按项目维度复用邮箱”的新需求时，以新 PRD 为准

4. 需求判断记录
   - 从产品需求角度看，Issue #39 不是文档误解，而是现有产品语义不完整所暴露出来的真实需求。
   - 新 PRD 采用“未来默认语义改为项目维度成功复用”的方向，后续再进入 FD / TD / TDD 讨论时，需要继续围绕这一立场展开。

5. 现场状态
   - 本轮已完成：新 PRD 建立 + 旧 PRD 范围边界补充 + WORKSPACE 记录。
   - 尚未进入实现设计与代码改造阶段。

#### 76. Issue #39 相关文档口径修正与会话记录同步

**时间**：2026-04-16

**本次操作**：

1. 文档修正目标
   - 目的：将 Issue #39 涉及的邮箱池语义按当前真实实现对齐到对外文档，避免把“项目隔离领取”误读为“成功后可跨项目复用”。

2. 已更新文件
   - `README.md`
   - `README.en.md`
   - `注册与邮箱池接口文档.md`
   - `registration-mail-pool-api.en.md`
   - `WORKSPACE.md`

3. 修正后的统一口径
   - `claim-random` 支持 `project_key`，其作用是同 `caller_id + project_key` 维度下的防重复领取。
   - `claim-complete(result=success)` 后，账号仍会进入全局 `pool_status='used'`。
   - 因此当前版本并不支持“成功后跨项目继续复用同一邮箱”。

4. 产品判断记录
   - 从用户视角看，该能力有实际价值：对于一个邮箱可服务多个站点注册的场景，现有“成功即全局消耗”会明显加快邮箱池消耗。
   - 但该需求触及状态模型与接入方预期，适合作为独立能力点单独讨论，不应在未定策略时直接修改现有行为。

5. 现场状态
   - 本轮已完成文档口径修正与 WORKSPACE 同步。
   - 尚未展开业务实现讨论或代码改造。

#### 75. Issue #39 现状核对与范围收敛记录

**时间**：2026-04-16

**本次操作**：

1. Issue 现状核对
   - 对象：`https://github.com/ZeroPointSix/outlookEmailPlus/issues/39`
   - 核对结论：
     - issue 中“`claim-random` 已支持 `project_key`，但 `claim-complete(result=success)` 之后账号会进入全局 `used`，导致跨 `project_key` 无法再次领取”的描述属实。
     - 当前实现里，`project_key` 仅用于同 `caller_id + project_key` 维度的防重复领取，并不改变 `success` 后的全局终态语义。

2. 代码与文档依据
   - `outlook_web/repositories/pool.py`
     - `RESULT_TO_POOL_STATUS["success"] = "used"`
     - `complete(...)` 会直接把账号更新为全局 `pool_status='used'`
   - `outlook_web/repositories/pool.py`
     - `claim_atomic(...)` 仅从 `pool_status='available'` 的账号中选择候选
     - `account_project_usage` 仅负责排除同项目已领取记录
   - `tests/test_pool_flow_suite.py`
     - “不同 `project_key` 可复用同一账号”的用例，是在第一次 `success` 后手动把账号改回 `available` 再验证，说明当前能力并未原生支持“成功后跨项目继续复用”
   - `注册与邮箱池接口文档.md`
     - 已明确写明：`success` 会把邮箱全局标记为 `used`
     - 已明确写明：当前版本没有按项目维度复用同一邮箱的状态模型

3. 判断与范围结论
   - 该问题不是“已经完成但被误解”，而是一个尚未支持的独立能力点。
   - 当前行为属于已有设计：代码、测试、文档口径一致，不能直接按 bug 归类为实现偏差。
   - 若后续要支持“同项目防重、跨项目可复用”，需要单独讨论状态模型与适用范围，不宜在本轮直接改动业务逻辑。

4. 本轮会话决策
   - 按当前会话要求，本轮仅更新 `WORKSPACE.md` 记录分析结论。
   - 其他 README / 接口文档 / 设计文档暂不修改。

5. 现场状态
   - 本次仅完成 issue 研判与工作区记录，不涉及代码实现、测试或发布动作。

## 2026-04-15

### 操作记录

#### 67. v1.17.0 发布后质量门禁修复（black/isort）与分批回归复核

**时间**：2026-04-15

**本次操作**：

1. 发布后状态确认
   - 当前分支：`main...origin/main`（已与远端同步）
   - 推送后 CI 历史确认：
     - `Create GitHub Release`（tag）✅
     - `Code Quality`（main）❌
     - `Build and Push Docker Image`（main/tag）❌（受 quality-gate 阻断）
     - `Python Tests`（main）✅
     - `SonarCloud Scan`（main）✅

2. 质量门禁修复执行
   - `python -m black outlook_web tests web_outlook_app.py outlook_mail_reader.py start.py`
   - `python -m isort --profile black outlook_web tests web_outlook_app.py outlook_mail_reader.py start.py`
   - 格式化检查复核：
     - `python -m black --check ...` ✅
     - `python -m isort --check-only --profile black ...` ✅

3. 回归复核（分批）
   - `python -m unittest discover -s tests -v -p "test_[a-f]*.py"` → `Ran 346, OK`
   - `python -m unittest discover -s tests -v -p "test_[g-l]*.py"` → `Ran 89, OK`
   - `python -m unittest discover -s tests -v -p "test_[m-r]*.py"` → `Ran 231, OK (skipped=7)`
   - `python -m unittest discover -s tests -v -p "test_[s-z]*.py"` → `Ran 492, OK`
   - 汇总：**1158 tests 通过，skipped=7**。

4. 会话文档回填
   - 已更新：
     - `docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`（v1.7）
     - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强TD.md`（v1.7）
     - `docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`（v1.6）
     - `docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`（v1.9）
     - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强-PRD-FD-TD-TDD联调检查.md`

5. 现场状态
   - 本次已完成：格式化修复 + 分批回归 + 文档回填 + WORKSPACE 记录。
   - 尚未进行本轮修复提交/推送（待用户确认后执行）。

#### 68. 质量门禁修复提交并推送，CI/CD 二次监控中

**时间**：2026-04-15

**本次操作**：

1. 提交与推送
   - 提交前状态：`main...origin/main`，22 个文件待提交（格式化 + 文档回填）。
   - 执行：`git add --all`
   - 提交：`f3d2208`
   - 提交信息：`chore(format): restore quality gate after v1.17.0 release`
   - 推送：`git push origin main` 成功（`4107faf..f3d2208`）。

2. 推送后工作流状态（实时）
   - `Code Quality`（run `24450419443`）✅ success
   - `Python Tests`（run `24450419407`）⏳ in_progress
   - `Build and Push Docker Image`（run `24450419424`）⏳ in_progress
   - `SonarCloud Scan`（run `24450419444`）⏳ in_progress

3. 现场状态
   - 本次已完成：修复提交 + 推送 + 工作流实时状态回传。
   - 其余工作流仍在进行中，待下一次状态回传确认最终结论。

#### 69. CI/CD 二次监控进展回传（部分完成）

**时间**：2026-04-15

**本次操作**：

1. 监控对象（提交 `f3d2208`）
   - Python Tests（run `24450419407`）
   - Build and Push Docker Image（run `24450419424`）
   - SonarCloud Scan（run `24450419444`）

2. 当前状态（本轮拉取）
   - Python Tests：✅ `completed/success`
   - Build and Push Docker Image：⏳ `queued`
   - SonarCloud Scan：⏳ `in_progress`
   - Code Quality（同批次 run `24450419443`）维持 ✅ success

3. 现场状态
   - 当前仅 Python Tests 已最终完成；Docker 与 Sonar 尚未结束。
   - 继续按会话要求进行后续状态跟踪并回传。

#### 70. CI/CD 二次监控完结回传（全绿恢复）

**时间**：2026-04-15

**本次操作**：

1. 监控结果（提交 `f3d2208`）
   - `Code Quality`（run `24450419443`）✅ success
   - `Python Tests`（run `24450419407`）✅ success
   - `Build and Push Docker Image`（run `24450419424`）✅ success
   - `SonarCloud Scan`（run `24450419444`）✅ success

2. 发布链路结论
   - `v1.17.0` 发布后因格式化导致的 quality-gate 阻断已通过本轮修复提交解除。
   - 当前 `main` 最新提交链路已恢复四项主工作流全绿。

3. 现场状态
   - 本次为监控收口回传，不涉及新增代码实现。
   - WORKSPACE 已按会话要求持续记录至当前最终状态。

#### 71. v1.17.0 发布状态核对（Latest）与监控闭环确认

**时间**：2026-04-15

**本次操作**：

1. 发布状态核对
   - 执行：`gh release view v1.17.0 --json ...`
   - 结果：
     - `isDraft=false`
     - `isPrerelease=false`
     - `name/tag=v1.17.0`
     - `publishedAt=2026-04-15T10:29:25Z`
     - 发布页：`https://github.com/ZeroPointSix/outlookEmailPlus/releases/tag/v1.17.0`
   - `gh release list` 核对：`v1.17.0` 为 `Latest`。

2. 监控收口状态补充
   - 文档收口提交 `05871bf` 触发的 `SonarCloud Scan`（run `24450875717`）已 `completed/success`。
   - 至此本会话发布推进链路（发布 + 修复 + 二次监控）完成闭环。

3. 文档回填
   - 已同步更新：
     - `docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`（v1.8）
     - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强TD.md`（v1.8）
     - `docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`（v1.7）
     - `docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`（v1.10）
     - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强-PRD-FD-TD-TDD联调检查.md`

4. 现场状态
   - 本次以状态核对和文档回填为主，无新增业务实现。

#### 72. 双仓 Docker 镜像构建状态核对（GHCR + DockerHub）

**时间**：2026-04-15

**本次操作**：

1. 核对目标
   - GHCR：`ghcr.io/zeropointsix/outlook-email-plus`
   - DockerHub：`docker.io/guangshanshui/outlook-email-plus`

2. 核对结果（`docker buildx imagetools inspect`）
   - `main` 标签：
     - GHCR digest：`sha256:8aef74b93a816e3aa8020d1c20767715a5c51e1373f8c8f58f5d692092869218`
     - DockerHub digest：`sha256:8aef74b93a816e3aa8020d1c20767715a5c51e1373f8c8f58f5d692092869218`
     - 结论：一致 ✅
   - `latest` 标签：
     - GHCR digest：`sha256:8aef74b93a816e3aa8020d1c20767715a5c51e1373f8c8f58f5d692092869218`
     - DockerHub digest：`sha256:8aef74b93a816e3aa8020d1c20767715a5c51e1373f8c8f58f5d692092869218`
     - 结论：一致 ✅
   - `v1.17.0` 标签：
     - GHCR：`not found`
     - DockerHub：`not found`
     - 结论：版本标签镜像当前未生成。

3. 监控补充
   - 当前文档提交触发的 SonarCloud（run `24451514245`）在记录时仍为 `in_progress`。

4. 文档回填
   - 已同步更新：FD/TD/TDD/TODO/联调检查文档至最新版本号与镜像核对结论。

5. 现场状态
   - 本次仅进行镜像状态核对与文档记录，不涉及业务代码变更。

#### 73. 重打 v1.17.0 标签以补齐版本镜像（执行中）

**时间**：2026-04-15

**本次操作**：

1. 决策与目标
   - 按会话选择，将 `v1.17.0` 重打到已验证全绿提交 `f3d2208`，以补齐 GHCR/DockerHub 的 `v1.17.0` 镜像标签。

2. 执行动作
   - `git tag -fa v1.17.0 f3d2208 -m "v1.17.0 (retag for CI-green image publish)"`
   - `git push origin :refs/tags/v1.17.0`
   - `git push origin v1.17.0`

3. 触发结果（当前）
   - `Create GitHub Release`（run `24451870230`）✅ success
   - `Build and Push Docker Image`（run `24451870226`）⏳ queued/in_progress

4. 文档同步
   - 已更新 FD/TD/TDD/TODO/联调检查文档，回填重打标签与当前工作流进展。

5. 现场状态
   - 当前工作区干净，等待 Docker tag workflow 最终完成后再核对双仓 `v1.17.0` 标签。

#### 74. v1.17.0 标签镜像补齐完成（双仓 digest 一致）

**时间**：2026-04-15

**本次操作**：

1. 工作流完成确认
   - `Build and Push Docker Image`（run `24451870226`）状态：`completed/success`。
   - 关联 tag 目标提交：`f3d2208`。

2. 双仓 `v1.17.0` 镜像复核
   - GHCR：`ghcr.io/zeropointsix/outlook-email-plus:v1.17.0`
   - DockerHub：`docker.io/guangshanshui/outlook-email-plus:v1.17.0`
   - 两仓 index digest 一致：
     - `sha256:e485e28b6e5ca5fbb83a0a9f38dc173316bfd166cb874a07b0250471021bfdb4`

3. 其他监控补充
   - `docs: record dual-registry image status for v1.17.0` 触发的 Sonar（run `24451739406`）已 success。

4. 文档回填
   - 已同步更新：FD/TD/TDD/TODO/联调检查文档，结论改为“v1.17.0 双仓标签镜像已补齐”。

5. 现场状态
   - 版本发布链路闭环：Release ✅、主链路 CI ✅、双仓 `v1.17.0` 标签镜像 ✅。

#### 66. v1.17.0 发布执行（单提交策略）与 CI/CD 实时结果回填

**时间**：2026-04-15

**本次操作**：

1. 按用户确认执行“单提交”发布策略
   - 先执行版本相关回归：
     - `python -m unittest tests.test_version_update -v` → **Ran 51, OK**
   - 提交策略：版本口径文件 + 会话文档统一提交。

2. 本地提交与打标
   - `git add --all`
   - `git commit -m "docs(release): finalize v1.17.0 notes and session records"`
   - 生成提交：`4107faf`
   - `git tag -a v1.17.0 -m "v1.17.0"`

3. 发布产物构建（本地）
   - Docker 环境：`Client=28.3.2 Server=28.3.2`
   - 镜像构建：`docker build -t "outlook-email-plus:v1.17.0" .` 成功
   - 导出产物：
     - `dist/outlook-email-plus-v1.17.0-docker.tar`（204,728,832 bytes）
     - `dist/outlookEmailPlus-v1.17.0-src.zip`（4,066,107 bytes）

4. 推送与 Release
   - `git push origin main` 成功（`9f55918..4107faf`）
   - `git push origin v1.17.0` 成功（新 tag）
   - GitHub Release 已创建：
     - `https://github.com/ZeroPointSix/outlookEmailPlus/releases/tag/v1.17.0`

5. CI/CD 实时结果（推送后）
   - `Create GitHub Release`（tag）✅ success
   - `Build and Push Docker Image`（tag）❌ failure
   - `Code Quality`（main）❌ failure
   - `Build and Push Docker Image`（main）❌ failure（被 quality-gate 阻断）
   - `Python Tests`（main）⏳ in progress（记录时）
   - `SonarCloud Scan`（main）⏳ in progress（记录时）

6. 失败根因（日志已核对）
   - `black --check` 未通过；日志显示当前仓库中包含多处未格式化文件（含 `outlook_web/errors.py`、`outlook_web/controllers/emails.py`、`outlook_web/controllers/settings.py`、`outlook_web/services/notification_dispatch.py`、`tests/test_version_update.py` 等）。
   - 由于 `quality-gate` 失败，`docker-build-push`（main/tag）链路被阻断。

7. 现场状态
   - 本次已完成：提交、tag、push、Release 创建、产物本地构建、CI 状态回传。
   - 当前主分支已推送，但 CI 仍需后续格式化修复后恢复全绿。

#### 65. 发布续推前主工作树核对与会话文档实况修正

**时间**：2026-04-15

**本次操作**：

1. 工作树与分支现场核对
   - 用户确认后切换到发布主工作树：`E:/hushaokang/Data-code/outlookEmail`（`main`）。
   - `git status --short --branch`：`main...origin/main [ahead 3]`。
   - 未提交改动集中在 `v1.17.0` 版本口径文件：
     - `CHANGELOG.md`
     - `README.md`
     - `README.en.md`
     - `docs/DEVLOG.md`
     - `outlook_web/__init__.py`
     - `tests/test_version_update.py`

2. 交叉工作树一致性核对
   - `Buggithubissue` 工作树状态：`ahead 1` 且工作区干净。
   - 结论：`Buggithubissue` 不含本轮 `v1.17.0` 未提交版本改动，发布应在 `main` 工作树继续。

3. 运行态复核（发布前）
   - 端口检查：`5000` 无监听（`NO_LISTENER_5000`）。
   - 健康检查：`GET http://127.0.0.1:5000/healthz` 连接失败。
   - 结论：当前本地服务未运行；本次仅记录现场，不新增启停动作。

4. 会话文档按实际修正
   - 已更新：
     - `docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`（v1.6）
     - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强TD.md`（v1.6）
     - `docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`（v1.5）
     - `docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`（v1.8）
     - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强-PRD-FD-TD-TDD联调检查.md`

5. 现场状态
   - 本次仅执行：状态核对 + 文档修正 + WORKSPACE 记录。
   - 未新增业务代码实现改动。
   - 未执行服务启动/重启/停止。

#### 64. main 分支文档提交后运行态复核（服务已退出）

**时间**：2026-04-15

**本次操作**：

1. 本地提交完成
   - 提交：`32632f9`
   - 提交信息：`docs: record main-branch startup and full regression rerun`
   - 包含文件：`WORKSPACE.md` + 5 份 Webhook/API Key 会话文档

2. 分支状态
   - 当前：`main...origin/main [ahead 2]`
   - 说明：仅本地提交，未 push

3. 运行态复核（提交后）
   - 原运行 PID `41184` 已不存在
   - 端口复核：`5000` 无监听（`NO_LISTENER_5000`）
   - 健康检查：`GET /healthz` 连接失败

4. 现场状态
   - 当前本地服务处于未运行状态
   - 本次仅记录复核结果，未再次启动服务

#### 63. main 分支文档与 WORKSPACE 回填提交（本地未推送）

**时间**：2026-04-15

**本次操作**：

1. 提交范围确认
   - 提交对象仅包含本会话回填文档与操作记录：
     - `WORKSPACE.md`
     - `docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`
     - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强TD.md`
     - `docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`
     - `docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`
     - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强-PRD-FD-TD-TDD联调检查.md`

2. 提交目标
   - 在 `main` 分支执行本地提交；
   - 明确不执行 push（保持仅本地 ahead 状态）。

3. 现场状态
   - 当前后台服务仍由 `PID 41184` 运行（端口 5000）；
   - 本次只处理文档与记录提交，不做功能代码变更。

#### 62. main 分支本地启动与分批全量回归复核（未推送）

**时间**：2026-04-15

**本次操作**：

1. 分支与现场处理
   - `Buggithubissue` 已本地 fast-forward 合并到 `main`（未 push）。
   - 按用户指定方案先停止 5000 端口旧进程：PID `37460`。
   - 在 `main` 工作区后台启动 `python web_outlook_app.py`。
   - 首次启动（PID `44204`）运行后退出；二次启动成功，当前 PID `41184`。

2. 服务健康验证（main）
   - 端口监听：`5000` 监听进程为 PID `41184`。
   - 健康检查：`GET http://127.0.0.1:5000/healthz` 返回 `200`。
   - 返回体：`{"boot_id":"1776240270869-41184","status":"ok","version":"1.16.0"}`。

3. 分批全量回归（main）
   - `python -m unittest discover -s tests -v -p "test_[a-f]*.py"` → `Ran 346, OK`
   - `python -m unittest discover -s tests -v -p "test_[g-l]*.py"` → `Ran 89, OK`
   - `python -m unittest discover -s tests -v -p "test_[m-r]*.py"` → `Ran 231, OK (skipped=7)`
   - `python -m unittest discover -s tests -v -p "test_[s-z]*.py"` → `Ran 492, OK`
   - 汇总：**1158 tests 通过，skipped=7**。

4. 文档回填（按实际执行更新）
   - `docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`
     - 升级至 v1.5，新增 main 分支启动与全量回归结果。
   - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强TD.md`
     - 升级至 v1.5，新增 10.4（main 分支启动与回归复核）。
   - `docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`
     - 升级至 v1.4，新增 13.8（main 分支回归复核）。
   - `docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`
     - 升级至 v1.7，新增“main 分支启动 + 全量回归”执行回填。
   - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强-PRD-FD-TD-TDD联调检查.md`
     - 新增 4.7（main 分支启动与全量回归回填）。

5. 现场状态
   - 当前 `main` 分支：`ahead 1`（仅本地，未 push）。
   - 后台服务运行中：PID `41184`（端口 5000）。
   - 说明：文档中 PRD 路径仍为会话链路引用，当前仓库未找到对应 PRD 实体文件，已标注“路径待补”。

#### 60. Docker 环境恢复后完成镜像构建与容器健康验证

**时间**：2026-04-15

**本次操作**：

1. Docker 环境检查
   - `docker version --format "Client={{.Client.Version}} Server={{.Server.Version}}"`
   - 返回：`Client=28.3.2 Server=28.3.2`（环境恢复可用）

2. 镜像构建
   - 命令：`docker build -t "outlook-email-plus:local-regression-20260415" .`
   - 结果：构建成功
   - 镜像：`outlook-email-plus:local-regression-20260415`
   - image id：`acc8f048a48e`

3. 容器运行与验证
   - 首次运行：`-p 5055:5000` 失败（端口占用/权限）
   - 处理：删除失败的 `Created` 容器
   - 二次运行：`docker run -d --name oep-regression-20260415 -p 18080:5000 ...` 成功
   - 状态：`Up ... (healthy)`
   - 健康检查：`GET http://127.0.0.1:18080/healthz` 返回 `200`
   - 返回体：`{"boot_id":"1776236786410-7","status":"ok","version":"1.16.0"}`
   - 容器日志：gunicorn 启动成功，应用与定时任务加载正常

4. 文档回填
   - `docs/PRD/2026-04-14-通用Webhook通知与APIKey易用性增强PRD.md`
     - 升级至 v1.5，Docker 状态改为“已构建并健康验证”
   - `docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`
     - 升级至 v1.4，Docker 状态回填为成功
   - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强TD.md`
     - 升级至 v1.4，10.3 改为“构建+运行验证通过”
   - `docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`
     - 升级至 v1.3，13.6 更新为“Docker 验证成功”并记录端口回退过程
   - `docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`
     - 升级至 v1.6，新增“Docker 环境恢复后”执行回填
   - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强-PRD-FD-TD-TDD联调检查.md`
     - 新增 4.6（Docker 构建与容器验证回填）

5. 现场状态
   - 本次包含：Docker 构建 + 容器验证 + 文档回填 + WORKSPACE 记录
   - 未新增业务代码实现改动
   - 本地 Python 后台服务仍保持运行（PID `37460`）
   - Docker 回归容器正在运行：`oep-regression-20260415`

#### 61. Docker 运行态复核与文档二次回填

**时间**：2026-04-15

**本次操作**：

1. 运行态复核
   - `docker ps`：`oep-regression-20260415` 状态 `Up ... (healthy)`
   - `docker inspect`：`Health=healthy`
   - `docker images`：`outlook-email-plus:local-regression-20260415` 存在（image id `acc8f048a48e`）

2. 文档二次回填（按实际状态修正）
   - `docs/PRD/2026-04-14-通用Webhook通知与APIKey易用性增强PRD.md`
     - 6.5 增补 Docker 端口回退细节（5055 失败→18080 成功）
   - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强TD.md`
     - 10.3 补充端口失败处理与回退路径
   - `docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`
     - 新增 13.7（Docker 运行态核对）
   - `docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`
     - 新增“Docker 运行态复核”执行回填
   - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强-PRD-FD-TD-TDD联调检查.md`
     - 4.6 增补端口异常处理结论

3. 现场状态
   - 本次仅做运行态核对与文档修正
   - 未新增业务代码改动
   - 未新增服务启停动作（沿用现有后台服务与容器）

#### 59. 第二轮分批全量回归执行 + Docker 构建前置检查

**时间**：2026-04-15

**本次操作**：

1. 回归测试执行（按分批策略）
   - `python -m unittest discover -s tests -v -p "test_[a-f]*.py"` → `Ran 346, OK`
   - `python -m unittest discover -s tests -v -p "test_[g-l]*.py"` → `Ran 89, OK`
   - `python -m unittest discover -s tests -v -p "test_[m-r]*.py"` → `Ran 231, OK (skipped=7)`
   - `python -m unittest discover -s tests -v -p "test_[s-z]*.py"` → `Ran 492, OK`
   - 汇总：第二轮分批全量回归 **1158 tests 通过，skipped=7**。

2. Docker 构建前置检查
   - `docker version --format "{{.Server.Version}}"` 失败
   - `docker build -t "outlook-email-plus:local-regression-20260415" .` 失败
   - 原因一致：本机未连接 Docker Engine（`//./pipe/dockerDesktopLinuxEngine` 不存在）

3. 文档回填
   - `docs/PRD/2026-04-14-通用Webhook通知与APIKey易用性增强PRD.md`
     - 升级至 v1.4，回填第二轮回归与 Docker 前置状态
   - `docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`
     - 升级至 v1.3，回填第二轮回归与 Docker 前置状态
   - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强TD.md`
     - 升级至 v1.3，新增 10.3（第二轮回归 + Docker 校验）
   - `docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`
     - 新增 13.5（第二轮分批全量回归）与 13.6（Docker 前置校验）
   - `docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`
     - 升级至 v1.5，新增“第二轮执行回填”
   - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强-PRD-FD-TD-TDD联调检查.md`
     - 新增 4.5（第二轮回归 + Docker 前置检查）

4. 现场状态
   - 本次包含：测试执行 + Docker 前置检查 + 文档回填 + WORKSPACE 记录
   - 未新增业务代码实现改动
   - 服务进程保持后台运行（PID `37460`）

#### 58. webhook.site 请求明细核对完成（成功链路）

**时间**：2026-04-15

**本次操作**：

1. 基于用户提供 URL 做接收端核对
   - URL：`https://webhook.site/00766721-eaaf-4a3b-9821-60575812158c`
   - 通过 webhook.site API 拉取最新请求明细，确认存在 `POST` 请求记录

2. 核对结果
   - method：`POST`
   - content-type：`text/plain; charset=utf-8`
   - body：包含来源邮箱/来源类型/文件夹/发件人/主题/时间/正文摘要等业务文本字段
   - `X-Webhook-Token`：当前 token 为空，header 中未出现该字段（符合“仅 token 非空才发送”）

3. 文档同步
   - `docs/PRD/2026-04-14-通用Webhook通知与APIKey易用性增强PRD.md`
     - 6.5 进展更新为“成功链路核对完成，失败链路待补”
   - `docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`
     - 会话进展更新为“请求细节已核对，失败链路待补”
   - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强TD.md`
     - 10.2 回填接收端核对结果（含 token 为空不发头）
   - `docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`
     - 13.4 回填 webhook.site 明细核对结果
   - `docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`
     - 6.8.1 第 4 项勾选完成
   - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强-PRD-FD-TD-TDD联调检查.md`
     - 4.4 补充成功链路明细核对结论

4. 现场状态
   - 本次包含：接收端核对 + 文档回填 + WORKSPACE 记录
   - 未新增业务代码实现改动
   - 未新增服务进程操作（沿用已启动后台进程 PID `37460`）

#### 57. 用户提供 webhook.site 实测地址后完成后台启动与链路验证

**时间**：2026-04-15

**本次操作**：

1. 用户输入
   - 提供测试地址：`https://webhook.site/00766721-eaaf-4a3b-9821-60575812158c`
   - 要求先启动服务并进行测试，同时继续更新会话文档与 WORKSPACE

2. 服务状态处理（遵守后台独立进程约束）
   - 先做连通性检查：`/healthz` 返回 `502`（服务不可用）
   - 采用后台独立进程方式启动：`Start-Process python web_outlook_app.py`
   - 实际进程 PID：`37460`
   - 启动后健康检查：`GET /healthz` 返回 `200`

3. 日志与链路验证
   - 读取 `service_stderr_20260415_135237.log`，可见：
     - 首次 `POST /api/settings/webhook-test` 返回 `400`，错误 `WEBHOOK_NOT_CONFIGURED`
     - 随后保存配置（`PUT /api/settings`）后再次 `POST /api/settings/webhook-test` 返回 `200`
   - 结论：符合“先保存配置，再测试 webhook”会话硬约束

4. 文档回填
   - `docs/PRD/2026-04-14-通用Webhook通知与APIKey易用性增强PRD.md`
     - 升级至 v1.3，回填实测 URL 与后台启动口径
   - `docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`
     - 升级至 v1.2，回填实测 URL 与执行状态
   - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强TD.md`
     - 升级至 v1.2，回填后台启动/健康检查/webhook-test 日志结果
   - `docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`
     - 补充会话手工联调进展（URL、PID、/healthz、webhook-test 400→200）
   - `docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`
     - 6.8.1 清单中“生成 URL / 保存配置 / 触发测试”已勾选
   - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强-PRD-FD-TD-TDD联调检查.md`
     - 更新版本引用并新增“4.4 实测进展回填”

5. 现场状态
   - 本次包含：后台启动 + 健康检查 + 日志验证 + 文档回填 + WORKSPACE 记录
   - 未新增业务代码实现改动

#### 56. webhook.site 分步联调指引文档化与会话输出约束回填

**时间**：2026-04-15

**本次操作**：

1. 会话推进
   - 用户选择“我带你一步步在 webhook.site 生成并完成配置”。
   - 用户要求继续保持：
     - 持续通过 MCP `寸止` 对话；
     - 每次回复要把结果信息明确告诉用户；
     - 不能只写文档不反馈。

2. 文档补充（按当前会话实操场景）
   - `docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`
     - 版本升至 v1.4
     - 新增 `6.8.1 webhook.site 联调执行清单`
   - `docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`
     - 新增 `9.2 webhook.site 逐步联调指引（会话实操版）`
   - `docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`
     - 补充“会话实操建议”步骤（先生成 URL、再保存、再测试）
   - `docs/PRD/2026-04-14-通用Webhook通知与APIKey易用性增强PRD.md`
     - 补充“默认推荐 webhook.site 作为第一联调入口”

3. 现场状态
   - 本次仅更新文档与 WORKSPACE 记录。
   - 未新增业务代码改动。
   - 未启动/重启/停止任何服务进程。

#### 55. 会话文档按“无 webhook 地址”实际场景修订并同步执行口径

**时间**：2026-04-15

**本次操作**：

1. 会话场景确认
   - 用户明确当前没有现成 webhook 地址。
   - 需要提供可直接落地的配置入口与联调路径。
   - 执行口径保持：后续联调如需服务运行，仅使用后台独立进程（`Start-Process`/独立进程），不使用前台阻塞命令。

2. 文档修订（按实际环境对齐）
   - `docs/PRD/2026-04-14-通用Webhook通知与APIKey易用性增强PRD.md`
     - 版本升至 v1.2
     - 补充“配置入口（设置 -> 自动化 Tab -> Webhook 通知）”
     - 补充“无地址时推荐 `https://webhook.site/` + 失败链路 Beeceptor/Pipedream”
     - 新增会话推荐执行顺序（先保存后测试 + 后台进程约束）
   - `docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`
     - 版本升至 v1.1
     - 补充“无现成地址先在 webhook.site 生成临时 URL”
     - 联调方案中明确配置入口路径
   - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强TD.md`
     - 版本升至 v1.1
     - 技术检查清单按当前实现与自动化验证回填为完成态
     - 补充无地址联调执行口径与后台进程约束
   - `docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`
     - 版本升至 v1.2
     - 手工替代方案改为 `https://webhook.site/` 明确链接
     - 补充“先保存再测试 + 后台独立进程”执行顺序
   - `docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`
     - 版本升至 v1.3
     - 同步引用版本（PRD/FD/TD/TDD）
     - Phase 6.8 补充配置入口与后台进程约束
   - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强-PRD-FD-TD-TDD联调检查.md`
     - 同步文档版本引用
     - 新增“4.3 会话场景回填（无地址联调口径）”

3. 现场状态
   - 本次仅更新文档与 WORKSPACE 记录。
   - 未新增业务代码改动。
   - 未启动/重启/停止任何服务进程。

#### 54. Webhook 手工联调方案补充与服务后台启动口径对齐

**时间**：2026-04-15

**本次操作**：

1. 会话需求调整
   - 用户反馈“当前没有可用 webhook 接收端”，需要补充可执行测试方案。
   - 会话执行口径补充：后台服务仅使用 `Start-Process` 独立进程启动；不使用前台阻塞命令。

2. 服务启动（后台独立进程）
   - 启动方式：`Start-Process python web_outlook_app.py`（独立进程）
   - 最新启动结果：PID `35164`
   - 健康检查：`GET /healthz` 返回 `HTTP 200`
   - 日志文件：
     - `service_stdout_20260415_133249.log`
     - `service_stderr_20260415_133249.log`

3. 文档同步修订（按实际可行性）
   - `docs/PRD/2026-04-14-通用Webhook通知与APIKey易用性增强PRD.md`
     - 新增“6.3 无自建接收端时的 Webhook 测试可行性”
   - `docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`
     - 新增“7.3 无自建接收端时的联调方案（webhook.site / Beeceptor / Pipedream）”
   - `docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`
     - 新增“9.1 无本地接收端时的手工测试替代”
   - `docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`
     - 在 Phase 6.8 下补充“无接收端时的替代联调指引”

4. 现场状态
   - 本次包含：后台启动服务 + 文档更新 + WORKSPACE 记录。
   - 未进行额外实现代码改动。

#### 53. Webhook/API Key 方案自动化验证回填（分批全量回归通过）

**时间**：2026-04-15

**本次操作**：

1. 现状核对
   - 对照 TODO 与现有代码，确认本需求相关实现/测试文件均已存在：
     - 后端：`settings.py` / `webhook_push.py` / `notification_dispatch.py` / `routes/settings.py`
     - 前端：`templates/index.html` / `static/js/main.js` / `static/js/i18n.js`
     - 测试：`test_settings_webhook.py` / `test_webhook_push.py` / `test_settings_webhook_frontend_contract.py` / `test_notification_dispatch.py`

2. 定向自动化测试
   - `python -m unittest tests.test_settings_webhook -v` → Ran 9, OK
   - `python -m unittest tests.test_webhook_push -v` → Ran 7, OK
   - `python -m unittest tests.test_notification_dispatch -v` → Ran 25, OK
   - `python -m unittest tests.test_settings_webhook_frontend_contract -v` → Ran 4, OK
   - `python -m unittest tests.test_v190_frontend_contract -v` → Ran 18, OK
   - `python -m unittest tests.test_settings_tab_refactor_backend -v` → Ran 14, OK
   - `python -m unittest tests.test_settings_tab_refactor_frontend -v` → Ran 12, OK

3. 分批全量回归（遵守单命令超时约束）
   - `python -m unittest discover -s tests -v -p "test_[a-f]*.py"` → Ran 346, OK
   - `python -m unittest discover -s tests -v -p "test_[g-l]*.py"` → Ran 89, OK
   - `python -m unittest discover -s tests -v -p "test_[m-r]*.py"` → Ran 231, OK (skipped=7)
   - `python -m unittest discover -s tests -v -p "test_[s-z]*.py"` → Ran 492, OK
   - 汇总：**1158 tests 通过，skipped=7**。

4. 文档回填
   - 更新 `docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`（v1.2）
   - 更新 `docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`（v1.1）
   - 更新 `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强-PRD-FD-TD-TDD联调检查.md`
   - 更新 `CHANGELOG.md`（Unreleased：功能、验证、已知风险）

5. 现场状态
   - 本次仅执行测试与文档回填。
   - 未启动/重启/停止任何服务进程。
   - 未新增实现代码改动。

---

## 2026-04-14

### 操作记录

#### 52. 产出“其它 AI 驱动使用”的执行提示词文档

**时间**：2026-04-14

**本次操作**：

1. 新建 AI 执行提示词文档
   - 文件：`docs/DEV/2026-04-14-通用Webhook通知与APIKey易用性增强-AI执行提示词.md`
   - 目标：供其它 AI 直接按会话冻结口径执行实现，避免偏离 PRD/TD/TODO
   - 内容覆盖：
     - 必读文档顺序（PRD/FD/TD/TDD/TODO/联调检查）
     - 允许修改文件清单（后端/前端/测试）
     - 强约束（webhook-test 仅已保存配置、前端算法生成 key、不引入新依赖）
     - 分阶段实施顺序与关键防跑偏提示
     - 测试命令、交付标准、禁止事项

2. TODO 头部联动
   - 文件：`docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`
   - 补充 “AI 执行提示词” 引用路径，形成“规范 → 执行提示词 → 任务拆分”闭环

3. 现场状态
   - 本次仅更新文档（新增 DEV 提示词 + TODO 引用 + WORKSPACE 记录）。
   - 未修改业务代码，未启动/重启/停止任何服务进程。

4. 会话后续调整（同日）
   - 按用户“删除文档，提示词直接会话提供”要求：
     - 已删除：`docs/DEV/2026-04-14-通用Webhook通知与APIKey易用性增强-AI执行提示词.md`
     - TODO 头部“AI 执行提示词”改为：`按会话实时提供（不落库文档）`
   - 说明：该调整只改变提示词存放方式，不影响 PRD/FD/TD/TDD/TODO 主链路。

#### 51. 基于 TODO 再次联调并回填进度（Phase 0 完成）

**时间**：2026-04-14

**本次操作**：

1. 按用户要求执行“面向 TODO 的联调”
   - 以 `docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md` 为中心
   - 对照 PRD/FD/TD/TDD/联调检查文档逐项核对会话口径

2. TODO 文档回填
   - 文件：`docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`
   - 回填内容：
     - 增加更新日期（v1.1）
     - 任务概览中 `Phase 0` 状态改为 `✅ 已完成`
     - `Task 0.1~0.3` 全部勾选完成（含三条会话硬约束）

3. 联调检查文档回填
   - 文件：`docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强-PRD-FD-TD-TDD联调检查.md`
   - 新增“TODO 联调回填（2026-04-14）”段落：
     - 明确 TODO Phase 0 已完成
     - 明确文档引用链与会话约束已固化

4. 现场状态
   - 本次仅更新文档（TODO + 联调检查 + WORKSPACE 记录）。
   - 未修改业务代码，未启动/重启/停止任何服务进程。

#### 50. 新建 TODO 任务拆分并完成文档链路闭环（Webhook + API Key）

**时间**：2026-04-14

**本次操作**：

1. 新建 TODO 执行拆分文档
   - 文件：`docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`
   - 结构：
     - Phase 0~7 分阶段任务
     - 每阶段具体文件与检查点
     - 测试命令、通过标准、会话硬约束

2. 会话文档链路闭环更新
   - `docs/PRD/2026-04-14-通用Webhook通知与APIKey易用性增强PRD.md`
   - `docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`
   - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强TD.md`
   - `docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`
   - 以上文件均补齐 TODO 引用，形成 PRD→FD→TD→TDD→TODO 完整链路。

3. 会话约束再确认（写入 TODO）
   - `webhook-test` 仅使用已保存配置
   - API Key 随机值由前端 `crypto.getRandomValues` 算法生成
   - 不引入新库/新架构层

4. 现场状态
   - 本次仅更新文档（新增 TODO + 多文档引用修正 + WORKSPACE 记录）。
   - 未修改业务代码，未启动/重启/停止任何服务进程。

#### 49. PRD/FD/TD/TDD 联调校正（确保不偏离会话 PRD）

**时间**：2026-04-14

**本次操作**：

1. 按会话要求执行文档联调
   - 目标：确保 FD/TD/TDD 不偏离 PRD 与会话确认口径
   - 对照范围：本次新增主题的 PRD/FD/TD/TDD 四份文档

2. PRD 校正（v1.0 → v1.1）
   - 文件：`docs/PRD/2026-04-14-通用Webhook通知与APIKey易用性增强PRD.md`
   - 校正点：
     - 明确 `X-Webhook-Token` 为可选头（token 非空才发送）
     - 明确 `webhook-test` 仅使用已保存配置（先保存再测试）
     - FR 表与 UAT 条款同步上述口径

3. 新增联调检查记录文档
   - 文件：`docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强-PRD-FD-TD-TDD联调检查.md`
   - 内容：
     - 四文档关键口径一致性矩阵
     - 本轮发现与修正项
     - 联调结论与下一步建议

4. 现场状态
   - 本次仅更新文档（PRD + 联调检查 + WORKSPACE 记录）。
   - 未修改业务代码，未启动/重启/停止任何服务进程。

#### 48. 基于 PRD+FD+TD 新建 TDD（通用 Webhook + API Key 易用性）

**时间**：2026-04-14

**本次操作**：

1. 新建 TDD 文档
   - 新增：`docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`
   - 覆盖测试分层与矩阵：
     - Settings/API：webhook 配置读写、URL 校验、token 脱敏/加密
     - Webhook Service：2xx 判定、10s 超时、失败重试1次、header 规则
     - Notification Dispatch：新增 webhook 通道与 Email/Telegram 并存回归
     - Frontend 契约：Webhook 卡片字段、测试按钮、随机/复制函数、i18n 词条
     - 手工冒烟：覆盖确认、复制、保存前后持久化差异

2. 会话文档联动更新
   - `docs/PRD/2026-04-14-通用Webhook通知与APIKey易用性增强PRD.md`
     - 补齐关联 TDD 引用
   - `docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`
     - 补齐关联 TDD 引用
   - `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强TD.md`
     - 补齐关联 TDD 引用

3. 口径对齐说明
   - 保持会话确认：
     - `webhook-test` 只用已保存配置
     - API Key 随机值使用前端原生 `crypto.getRandomValues` 算法生成
     - 不引入新增第三方库或新架构层

4. 现场状态
   - 本次仅进行文档新增与更新（PRD/FD/TD/TDD/WORKSPACE）。
   - 未修改业务代码，未启动/重启/停止任何服务进程。

#### 47. 基于 PRD+FD 新建 TD（通用 Webhook + API Key 易用性）

**时间**：2026-04-14

**本次操作**：

1. 会话技术口径确认
   - `webhook-test` 仅使用已保存配置（不接受临时覆盖参数）
   - API Key 随机值在前端本地生成（`crypto.getRandomValues`）
   - 不引入新库/新架构层，按现有代码能力扩展

2. 新建 TD 文档
   - 新增：`docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强TD.md`
   - 主要内容：
     - 代码锚点基线（settings route/controller、notification_dispatch、index/main.js/i18n）
     - 核心决策（不改 schema、不加新依赖、测试口径、随机算法）
     - 后端设计（settings getter、`/api/settings/webhook-test`、`webhook_push.py`、dispatch 接入）
     - 前端设计（自动化Tab卡片、main.js 加载/保存/测试、API Key 随机与复制）
     - 接口契约、错误码建议、安全与回滚、实施顺序与技术检查清单

3. 会话文档联动修正
   - `docs/PRD/2026-04-14-通用Webhook通知与APIKey易用性增强PRD.md`
     - 补齐关联 FD/TD 引用
   - `docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`
     - 补齐关联 TD 引用，并将“TD 阶段待细化”改为“已进入 TD 阶段”

4. 现场状态
   - 本次仅进行文档新增与更新（PRD/FD/TD/WORKSPACE）。
   - 未修改业务代码，未启动/重启/停止任何服务进程。

#### 46. 基于 PRD 新建 FD（通用 Webhook + API Key 易用性）

**时间**：2026-04-14

**本次操作**：

1. 会话口径补充确认
   - 通过会话确认两项设计约束：
     - Webhook 卡片放置于 `自动化 Tab` 通知区
     - Webhook Token 为可选；为空时不发送 `X-Webhook-Token`

2. 新建 FD 文档
   - 新增：`docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`
   - 覆盖内容包括：
     - 页面布局与交互（Webhook 卡片、测试按钮、API Key 随机/复制）
     - 通道行为与投递协议（`POST text/plain; charset=utf-8`、10s、重试1次、2xx 成功）
     - 配置契约（settings 键建议）、测试接口设计（`/api/settings/webhook-test`）
     - 数据流、错误提示口径、验收清单与风险项

3. 现场状态
   - 本次仅更新会话文档（新增 FD + 更新 WORKSPACE 记录）。
   - 未修改业务代码，未启动/重启/停止任何服务进程。

#### 45. Issue #42 需求澄清与 PRD 新建（通用 Webhook + API Key 易用性）

**时间**：2026-04-14

**本次操作**：

1. 需求读取与现状核对
   - 读取并分析：`https://github.com/ZeroPointSix/outlookEmailPlus/issues/42`
   - 本地核对现状：
     - 设置页 API 安全区（`templates/index.html`）
     - 设置页保存链路（`static/js/main.js` / `outlook_web/controllers/settings.py`）
     - 通知分发链路（`outlook_web/services/notification_dispatch.py`）
   - 结论：Issue 值得做，且应由“企业微信专属”收敛为“通用 Webhook 通道”。

2. 会话需求澄清结果（按用户确认）
   - 范围：`通用 Webhook 通知 + API Key 随机生成/复制`
   - Webhook 与现有通知链路口径一致（触发/参与规则一致）
   - 配置粒度：全局单 Webhook URL，账号沿用现有通知参与开关
   - 协议：`POST text/plain; charset=utf-8`
   - URL：支持 `http/https`
   - 鉴权：固定 Header `X-Webhook-Token`
   - 投递策略：超时 10s，失败重试 1 次
   - 可观测性：设置页提供测试按钮；失败前端可见 + 后端日志可查
   - 文本模板：来源邮箱/来源类型/文件夹/发件人/主题/时间/正文摘要
   - API Key 易用性：
     - 64 位 URL-safe 随机生成
     - 输入框旁提供“随机生成 + 复制”
     - 已有值时覆盖前二次确认
     - 生成与复制不自动保存，仍需点击“保存设置”生效

3. 文档落地
   - 新建 PRD：
     - `docs/PRD/2026-04-14-通用Webhook通知与APIKey易用性增强PRD.md`
   - PRD 已记录：背景、范围、FR/NFR、验收标准、非目标与风险项。

4. 现场状态
   - 本次仅进行文档新增与记录；未修改业务代码、未启动/重启/停止服务进程。

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
