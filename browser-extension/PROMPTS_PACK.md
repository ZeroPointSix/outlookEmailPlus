=== E-01 提示词 ===

# E-01：创建 manifest.json（Chrome MV3 清单）

## 任务

在 `E:\hushaokang\Data-code\EnsoAi\outlookEmail\dev\browser-extension\manifest.json` 创建 Chrome/Edge Manifest V3 扩展清单文件。

## 完整文件内容

请创建文件，内容**严格**如下（JSON，UTF-8 无 BOM）：

```json
{
  "manifest_version": 3,
  "name": "邮箱池快捷操作",
  "version": "0.1.0",
  "description": "OutlookMail Plus 伴生扩展 — 快捷申领邮箱、获取验证码",
  "icons": {
    "16": "icons/icon16.png",
    "48": "icons/icon48.png",
    "128": "icons/icon128.png"
  },
  "action": {
    "default_icon": {
      "16": "icons/icon16.png",
      "48": "icons/icon48.png"
    },
    "default_popup": "popup.html",
    "default_title": "邮箱池"
  },
  "permissions": ["storage", "tabs"],
  "optional_host_permissions": ["<all_urls>"],
  "commands": {
    "_execute_action": {
      "suggested_key": {
        "default": "Ctrl+Shift+E",
        "mac": "Command+Shift+E"
      },
      "description": "打开邮箱池快捷操作面板"
    }
  }
}
```

## 关键约束

1. **必须使用 `optional_host_permissions`**，不能用 `host_permissions`。原因：用户首次安装时不弹权限确认，而是在保存设置时通过 `chrome.permissions.request()` 动态申请。
2. **`permissions` 仅含 `storage` 和 `tabs`**。`storage` 用于 `chrome.storage.local` 持久化；`tabs` 用于 `chrome.tabs.create` 打开验证链接。
3. **`_execute_action`** 是 Chrome MV3 内置命令名，绑定到 action 按钮（即 Popup 面板的快捷键触发）。
4. **`default_popup` 指向 `popup.html`**（正式版，非预览版）。
5. 文件编码 UTF-8，JSON 合法，无注释，无尾逗号。

## 验证标准

- `manifest.json` 是合法 JSON，可被 `JSON.parse()` 解析
- `manifest_version` 为 `3`
- `optional_host_permissions` 包含 `"<all_urls>"`
- `permissions` 数组恰好包含 `"storage"` 和 `"tabs"`
- `action.default_popup` 为 `"popup.html"`
- `commands._execute_action` 存在且快捷键正确

## 依赖

无前置依赖，可独立执行。


=== E-02 提示词 ===

# E-02：创建 storage.js（chrome.storage.local 封装）

## 任务

在 `E:\hushaokang\Data-code\EnsoAi\outlookEmail\dev\browser-extension\storage.js` 创建 Chrome Storage 封装模块。

## 完整文件内容

请创建文件，内容**严格**如下：

```javascript
/**
 * chrome.storage.local 封装
 * 通过 <script src="storage.js"> 引入，暴露全局 Storage 对象
 */
const Storage = {
  /**
   * 读取所有存储数据
   * @returns {Promise<{config?: object, currentTask?: object|null, history?: Array}>}
   */
  async getAll() {
    return chrome.storage.local.get(['config', 'currentTask', 'history']);
  },

  /**
   * 写入当前任务
   * @param {object} task - 任务对象 {email, taskId, callerId, projectKey, claimedAt, code, link}
   */
  async setCurrentTask(task) {
    await chrome.storage.local.set({ currentTask: task });
  },

  /**
   * 清空当前任务
   */
  async clearCurrentTask() {
    await chrome.storage.local.set({ currentTask: null });
  },

  /**
   * 追加历史记录（最新在前，最多保留 100 条）
   * @param {object} entry - 历史条目
   */
  async appendHistory(entry) {
    const { history = [] } = await chrome.storage.local.get('history');
    const next = [entry, ...history].slice(0, 100);
    await chrome.storage.local.set({ history: next });
  },

  /**
   * 读取配置
   * @returns {Promise<{serverUrl?: string, apiKey?: string, defaultProjectKey?: string}>}
   */
  async getConfig() {
    const { config = {} } = await chrome.storage.local.get('config');
    return config;
  },

  /**
   * 写入配置
   * @param {object} config - 配置对象 {serverUrl, apiKey, defaultProjectKey}
   */
  async setConfig(config) {
    await chrome.storage.local.set({ config });
  },
};
```

## 数据结构说明

`chrome.storage.local` 中存储三个顶层键：

```json
{
  "config": {
    "serverUrl": "https://demo.outlookmailplus.tech",
    "apiKey": "sk-xxxx",
    "defaultProjectKey": "my-project"
  },
  "currentTask": {
    "email": "abc@example.com",
    "taskId": "uuid-v4",
    "callerId": "browser-extension",
    "projectKey": "my-project",
    "claimedAt": "2026-04-18T10:00:00.000Z",
    "code": null,
    "link": null
  },
  "history": [
    {
      "id": "uuid-v4",
      "email": "abc@example.com",
      "projectKey": "my-project",
      "claimedAt": "2026-04-18T10:00:00.000Z",
      "completedAt": "2026-04-18T10:05:00.000Z",
      "status": "completed",
      "code": "123456",
      "link": null,
      "apiError": false
    }
  ]
}
```

## 关键约束

1. **不使用 ES modules**（无 `export`/`import`）。MV3 Popup 通过 `<script src="storage.js">` 引入，`Storage` 作为全局变量。
2. **`appendHistory` 限制最多 100 条**，超出时丢弃最旧的条目。
3. **每次操作先 `get` 再 `set`**，不依赖内存缓存，保证 Popup 重新打开后数据一致。
4. **`clearCurrentTask` 写入 `null`**（不使用 `chrome.storage.local.remove`），保持读取时的一致性。

## 验证标准

- 文件语法正确，无 ES module 语法（无 `export`/`import`）
- `Storage` 对象包含 6 个方法：`getAll`、`setCurrentTask`、`clearCurrentTask`、`appendHistory`、`getConfig`、`setConfig`
- `appendHistory` 中 `slice(0, 100)` 正确限制条数
- 所有方法返回 Promise（async 函数）

## 依赖

- E-01（manifest.json 中声明了 `storage` 权限）


=== E-03 提示词 ===

# E-03：创建 popup.js（主交互逻辑 — 状态机 + API + 事件处理）

## 任务

在 `E:\hushaokang\Data-code\EnsoAi\outlookEmail\dev\browser-extension\popup.js` 创建 Popup 主交互逻辑文件。这是整个扩展最核心、最复杂的文件，包含状态机渲染、5 个 API 调用、全部事件处理器和初始化逻辑。

## 项目上下文

该文件通过 `<script src="popup.js">` 引入到 `popup.html`，在它之前已引入 `storage.js`（暴露全局 `Storage` 对象）。popup.js 自身也不使用 ES modules，所有函数和常量为全局作用域或 IIFE 内部。

## 完整模块结构

```
popup.js
├── 常量与配置
│   ├── DEFAULT_WAIT_SECONDS = 60
│   ├── FETCH_TIMEOUT_MS = 65000
│   ├── ACTION_TIMEOUT_MS = 10000
│   └── MAX_HISTORY = 100
├── UI 渲染函数
│   ├── renderState(state, data)
│   ├── renderHistory(history)
│   ├── showError(msg)
│   ├── showMessage(msg, type)
│   └── hideMessage()
├── API 调用（5 个独立函数）
│   ├── apiClaimRandom(config, taskId, projectKey)
│   ├── apiGetCode(config, email)
│   ├── apiGetLink(config, email)
│   ├── apiComplete(config, taskId)
│   └── apiRelease(config, taskId)
├── 权限辅助
│   └── requestPermissionForHost(serverUrl)
├── 事件处理器
│   ├── handleClaim()
│   ├── handleGetCode()
│   ├── handleGetLink()
│   ├── handleComplete()
│   ├── handleRelease()
│   ├── handleCopy(text, btnElement)
│   ├── handleOpenLink(url)
│   └── handleSaveSettings()
├── 历史记录辅助
│   └── toggleHistory()
└── 初始化
    └── init() → DOMContentLoaded 绑定
```

## 详细实现规格

### 1. 常量与配置

```javascript
const DEFAULT_WAIT_SECONDS = 60;
const FETCH_TIMEOUT_MS = 65000;   // 比服务端 wait=60 多 5s 缓冲
const ACTION_TIMEOUT_MS = 10000;  // 完成/释放等短操作超时
const MAX_HISTORY = 100;
const CALLER_ID = 'browser-extension';
```

### 2. 状态机设计

7 个互斥状态，通过 `renderState(state, data)` 切换 UI：

| 状态 | 含义 | UI 行为 |
|------|------|---------|
| `idle` | 无任务 | 显示 `state-empty`（申领按钮 + 历史记录） |
| `claiming` | 申领中 | 申领按钮变为 loading（`<div class="spinner"></div> 申领中…`），禁用按钮 |
| `claimed` | 已申领 | 显示 `state-task`（邮箱卡片 + 获取验证码/链接 + 完成/释放），隐藏 result-box |
| `fetching` | 等待验证码/链接 | 获取按钮变 loading，显示倒计时区域 `⚠️ 等待验证码期间请勿关闭面板`，禁用获取/完成/释放按钮 |
| `result_code` | 已获取验证码 | 显示 result-box（验证码 + 复制按钮），启用完成/释放 |
| `result_link` | 已获取链接 | 显示 result-box（链接 + 复制按钮 + 新标签打开按钮），启用完成/释放 |
| `settings` | 设置面板 | 显示 `state-settings`，填充当前配置值 |

`renderState(state, data)` 的实现要点：
- 先隐藏所有状态 div（移除 `.active`）
- 根据 state 添加对应 div 的 `.active`
- `idle` 时：恢复申领按钮原始状态，从 storage 读取 `defaultProjectKey` 填入输入框
- `claiming` 时：保持 `state-empty` 显示，改按钮为 loading 并 disabled
- `claimed` 时：显示 `state-task`，填充邮箱地址，隐藏 result-box，启用所有按钮
- `fetching` 时：保持 `state-task` 显示，禁用获取/完成/释放按钮，显示警告提示
- `result_code` 时：保持 `state-task`，result-box 显示验证码模式（大字体），启用完成/释放
- `result_link` 时：保持 `state-task`，result-box 显示链接模式（小字体 link-mode class + 打开链接按钮），启用完成/释放
- `settings` 时：显示 `state-settings`，从 storage 读取配置填入表单

### 3. API 调用函数

所有 API 函数接收 `config` 对象（含 `serverUrl`、`apiKey`）。`serverUrl` 需 **trim 末尾斜杠**。

#### 3.1 公共辅助：构造请求头和处理响应

```javascript
function buildHeaders(apiKey, isJson = false) {
  const h = { 'X-API-Key': apiKey };
  if (isJson) h['Content-Type'] = 'application/json';
  return h;
}

function trimUrl(serverUrl) {
  return serverUrl.replace(/\/+$/, '');
}

async function handleResponse(resp) {
  if (resp.ok) return resp.json();
  let msg;
  try {
    const body = await resp.json();
    msg = body.message || body.error || `HTTP ${resp.status}`;
  } catch {
    msg = resp.status >= 500
      ? '服务器内部错误，请稍后重试'
      : `请求失败 (${resp.status})`;
  }
  throw new Error(msg);
}
```

#### 3.2 五个 API 函数

```javascript
async function apiClaimRandom(config, taskId, projectKey) {
  const url = `${trimUrl(config.serverUrl)}/api/external/pool/claim-random`;
  const body = { caller_id: CALLER_ID, task_id: taskId };
  if (projectKey) body.project_key = projectKey;

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ACTION_TIMEOUT_MS);
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: buildHeaders(config.apiKey, true),
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    return handleResponse(resp);
  } finally {
    clearTimeout(timer);
  }
}

async function apiGetCode(config, email) {
  const base = trimUrl(config.serverUrl);
  const url = `${base}/api/external/verification-code?email=${encodeURIComponent(email)}&wait=${DEFAULT_WAIT_SECONDS}`;

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
  try {
    const resp = await fetch(url, {
      headers: buildHeaders(config.apiKey),
      signal: ctrl.signal,
    });
    return handleResponse(resp);
  } finally {
    clearTimeout(timer);
  }
}

async function apiGetLink(config, email) {
  const base = trimUrl(config.serverUrl);
  const url = `${base}/api/external/verification-link?email=${encodeURIComponent(email)}&wait=${DEFAULT_WAIT_SECONDS}`;

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
  try {
    const resp = await fetch(url, {
      headers: buildHeaders(config.apiKey),
      signal: ctrl.signal,
    });
    return handleResponse(resp);
  } finally {
    clearTimeout(timer);
  }
}

async function apiComplete(config, taskId) {
  const url = `${trimUrl(config.serverUrl)}/api/external/pool/claim-complete`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ACTION_TIMEOUT_MS);
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: buildHeaders(config.apiKey, true),
      body: JSON.stringify({ task_id: taskId, result: 'success' }),
      signal: ctrl.signal,
    });
    return handleResponse(resp);
  } finally {
    clearTimeout(timer);
  }
}

async function apiRelease(config, taskId) {
  const url = `${trimUrl(config.serverUrl)}/api/external/pool/claim-release`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ACTION_TIMEOUT_MS);
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: buildHeaders(config.apiKey, true),
      body: JSON.stringify({ task_id: taskId }),
      signal: ctrl.signal,
    });
    return handleResponse(resp);
  } finally {
    clearTimeout(timer);
  }
}
```

### 4. 权限申请辅助

```javascript
async function requestPermissionForHost(serverUrl) {
  const url = new URL(serverUrl);
  const origin = `${url.protocol}//${url.hostname}/*`;
  const granted = await chrome.permissions.request({ origins: [origin] });
  return granted;
}
```

此函数必须在用户操作的回调中同步调用（即在 click handler 里直接 `await`，不能延迟到下一个微任务）。

### 5. 错误处理策略

统一的错误分类函数：

```javascript
function friendlyError(err) {
  if (err.name === 'AbortError') return '等待超时，可重试';
  if (err instanceof TypeError && /fetch/i.test(err.message))
    return '无法连接服务器，请检查地址和网络';
  return err.message || '未知错误';
}
```

### 6. 事件处理器详细逻辑

#### 6.1 handleClaim()

```
1. 读取 config = await Storage.getConfig()
2. 校验 config.serverUrl 和 config.apiKey 非空，否则 showError('请先在设置中配置服务器地址和 API Key')
3. 读取 projectKey：优先取页面输入框 #project-key-input 的值，其次取 config.defaultProjectKey
4. renderState('claiming')
5. 生成 taskId = crypto.randomUUID()
6. 构建 task 对象 { email: null, taskId, callerId: CALLER_ID, projectKey, claimedAt: new Date().toISOString(), code: null, link: null }
7. ★★★ 立即写入 storage：await Storage.setCurrentTask(task)（先写再请求，防 Popup 关闭丢失）
8. try:
   - result = await apiClaimRandom(config, taskId, projectKey)
   - task.email = result.email
   - await Storage.setCurrentTask(task)
   - renderState('claimed', task)
9. catch(err):
   - await Storage.clearCurrentTask()
   - renderState('idle')
   - showError(friendlyError(err))
```

#### 6.2 handleGetCode()

```
1. 读取 { currentTask } = await Storage.getAll()
2. 读取 config = await Storage.getConfig()
3. renderState('fetching')   // 显示 loading + "请勿关闭面板"
4. try:
   - result = await apiGetCode(config, currentTask.email)
   - currentTask.code = result.code
   - await Storage.setCurrentTask(currentTask)
   - renderState('result_code', currentTask)
5. catch(err):
   - renderState('claimed', currentTask)  // 恢复到 claimed，允许重试
   - showError(friendlyError(err))
```

#### 6.3 handleGetLink()

```
1. 读取 { currentTask } = await Storage.getAll()
2. 读取 config = await Storage.getConfig()
3. renderState('fetching')
4. try:
   - result = await apiGetLink(config, currentTask.email)
   - currentTask.link = result.link
   - await Storage.setCurrentTask(currentTask)
   - renderState('result_link', currentTask)
5. catch(err):
   - renderState('claimed', currentTask)
   - showError(friendlyError(err))
```

#### 6.4 handleComplete()

**关键：即使 API 调用失败，仍清空 currentTask 并写入历史（标记 apiError）**

```
1. 读取 { currentTask } = await Storage.getAll()
2. 读取 config = await Storage.getConfig()
3. 禁用完成/释放按钮
4. let apiError = false
5. try:
   - await apiComplete(config, currentTask.taskId)
6. catch(err):
   - apiError = true
   - showError('完成操作未能通知服务器: ' + friendlyError(err))
7. finally:
   - 构建 history entry:
     { id: currentTask.taskId, email: currentTask.email, projectKey: currentTask.projectKey,
       claimedAt: currentTask.claimedAt, completedAt: new Date().toISOString(),
       status: 'completed', code: currentTask.code, link: currentTask.link, apiError }
   - await Storage.appendHistory(entry)
   - await Storage.clearCurrentTask()
   - renderState('idle')
   - 如果 !apiError，showMessage('✅ 任务已完成', 'success')
```

#### 6.5 handleRelease()

与 handleComplete 类似，但 status 为 `'released'`，API 调用 `apiRelease`：

```
1. 读取 { currentTask } = await Storage.getAll()
2. 读取 config = await Storage.getConfig()
3. 禁用按钮
4. let apiError = false
5. try:
   - await apiRelease(config, currentTask.taskId)
6. catch(err):
   - apiError = true
   - showError('释放操作未能通知服务器: ' + friendlyError(err))
7. finally:
   - 构建 history entry（status: 'released'，其余同上）
   - await Storage.appendHistory(entry)
   - await Storage.clearCurrentTask()
   - renderState('idle')
   - 如果 !apiError，showMessage('↩ 邮箱已释放', 'success')
```

#### 6.6 handleCopy(text, btnElement)

```javascript
async function handleCopy(text, btnElement) {
  try {
    await navigator.clipboard.writeText(text);
    const orig = btnElement.innerHTML;
    btnElement.innerHTML = '✓ 已复制';
    btnElement.classList.add('copied');
    setTimeout(() => {
      btnElement.innerHTML = orig;
      btnElement.classList.remove('copied');
    }, 1400);
  } catch {
    showError('复制失败，请手动复制');
  }
}
```

#### 6.7 handleOpenLink(url)

```javascript
function handleOpenLink(url) {
  chrome.tabs.create({ url });
}
```

#### 6.8 handleSaveSettings()

```
1. 从表单读取 serverUrl, apiKey, defaultProjectKey
2. serverUrl = serverUrl.trim().replace(/\/+$/, '')
3. 校验 serverUrl 和 apiKey 非空
4. ★★★ 调用 requestPermissionForHost(serverUrl)（必须在 click 回调中同步调用）
5. 如果 granted === false：showError('需要授予访问权限才能正常使用，请重试') 并 return
6. await Storage.setConfig({ serverUrl, apiKey, defaultProjectKey: defaultProjectKey.trim() || '' })
7. showMessage('✅ 配置已保存', 'success')
8. 短暂延迟后切换回 idle 状态
```

### 7. renderHistory(history)

```
1. 接收 history 数组
2. 更新 #history-count 文本
3. 清空 #history-list 内容
4. 遍历 history，为每条 entry 创建 DOM：
   - div.history-item
     - div.history-email → entry.email
     - div.history-meta:
       - span → 格式化时间（可用 toLocaleString 或简单的日期格式）
       - span.history-code → 如果 entry.code 则显示 `验证码: ${entry.code}`，如果 entry.link 则显示 `🔗 链接已提取`，否则 `（未获取验证码）`
       - span → 状态：entry.status === 'completed' ? `<span class="status-done">✅ 完成</span>` : `<span class="status-release">↩ 已释放</span>`
       - 如果 entry.apiError，追加 `<span style="color:var(--clr-danger)">⚠ API异常</span>`
5. 如果 history 为空，显示 "暂无历史记录" 提示
```

### 8. showError / showMessage / hideMessage

使用 `#message-bar` 元素（在 popup.html 中会有此元素）：

```javascript
function showMessage(msg, type = 'info') {
  const bar = document.getElementById('message-bar');
  bar.textContent = msg;
  bar.className = 'message-bar message-' + type;
  bar.style.display = 'block';
  if (type === 'success') {
    setTimeout(hideMessage, 3000);
  }
}

function showError(msg) {
  showMessage(msg, 'error');
  // error 不自动消失，需用户操作后或下次状态变更时隐藏
}

function hideMessage() {
  const bar = document.getElementById('message-bar');
  bar.style.display = 'none';
}
```

### 9. init() 和 DOMContentLoaded

```javascript
document.addEventListener('DOMContentLoaded', async () => {
  // 1. 绑定事件
  document.getElementById('btn-claim').addEventListener('click', handleClaim);
  document.getElementById('btn-get-code').addEventListener('click', handleGetCode);
  document.getElementById('btn-get-link').addEventListener('click', handleGetLink);
  document.getElementById('btn-complete').addEventListener('click', handleComplete);
  document.getElementById('btn-release').addEventListener('click', handleRelease);
  document.getElementById('btn-save').addEventListener('click', handleSaveSettings);
  document.getElementById('btn-back').addEventListener('click', () => renderState('idle'));
  document.getElementById('header-settings-btn').addEventListener('click', () => renderState('settings'));
  document.getElementById('history-header').addEventListener('click', toggleHistory);

  // 复制按钮通过事件委托或 renderState 时动态绑定

  // 2. 恢复状态
  const { currentTask, history = [] } = await Storage.getAll();
  renderHistory(history);

  if (currentTask && currentTask.email) {
    // 有进行中的任务，恢复到 claimed 状态
    renderState('claimed', currentTask);
  } else if (currentTask && !currentTask.email) {
    // task_id 已写入但 email 还没拿到（上次 Popup 在 claiming 时关闭了）
    // 清理掉这个不完整的任务
    await Storage.clearCurrentTask();
    renderState('idle');
  } else {
    renderState('idle');
  }
});
```

### 10. toggleHistory()

```javascript
let historyOpen = false;
function toggleHistory() {
  historyOpen = !historyOpen;
  document.getElementById('history-list').classList.toggle('open', historyOpen);
  document.getElementById('history-caret').classList.toggle('open', historyOpen);
}
```

## 关键约束清单

1. **task_id 先写 storage 再发请求**（步骤 6.1 中的 ★★★ 标记）。防止 Popup 在请求中途被关闭导致 task_id 丢失。
2. **AbortController 超时**：验证码/链接等待用 65000ms（`FETCH_TIMEOUT_MS`），完成/释放用 10000ms（`ACTION_TIMEOUT_MS`）。
3. **完成/释放失败时仍清 task、写 history**（步骤 6.4/6.5 的 `finally` 块），history entry 中 `apiError: true`。
4. **serverUrl 末尾斜杠 trim**：`trimUrl()` 函数。
5. **错误类型区分**：`friendlyError()` 函数区分 AbortError / TypeError(fetch) / HTTP 4xx/5xx。
6. **`fetching` 状态必须显示** `⚠️ 等待验证码期间请勿关闭面板`。
7. **`chrome.permissions.request` 必须在用户点击回调中直接 `await`**，不能放在异步链或 setTimeout 中。
8. **不使用 ES modules**，全局作用域或 IIFE 包裹。
9. **DOM ID 引用**与 popup.html 一致，关键 ID：`btn-claim`、`btn-get-code`、`btn-get-link`、`btn-complete`、`btn-release`、`btn-save`、`btn-back`、`header-settings-btn`、`state-empty`、`state-task`、`state-settings`、`current-email`、`result-box`、`result-label`、`result-value`、`message-bar`、`project-key-input`、`cfg-server`、`cfg-apikey`、`cfg-project`、`history-header`、`history-list`、`history-count`、`history-caret`。
10. **init 中状态恢复**：如果 `currentTask` 存在且有 email，恢复到 `claimed`；如果 `currentTask` 存在但无 email（说明上次 claiming 中途关闭），清除并显示 idle。

## 验证标准

- 文件语法正确（无 ES module，可在浏览器环境运行）
- 包含所有 5 个 API 函数和 8 个事件处理器
- `handleClaim` 中先 `setCurrentTask` 再 `apiClaimRandom`
- `handleComplete`/`handleRelease` 在 `finally` 中执行清理
- `friendlyError` 正确区分 3 种错误类型
- `requestPermissionForHost` 在 `handleSaveSettings` 中被同步 `await`
- DOMContentLoaded 中绑定所有事件监听器
- 状态恢复逻辑完整

## 依赖

- E-01（manifest.json 声明权限）
- E-02（storage.js 的 `Storage` 全局对象，popup.js 在其之后引入）


=== E-04 提示词 ===

# E-04：创建正式版 popup.html（MV3 CSP 合规）

## 任务

1. **先**将当前的 `E:\hushaokang\Data-code\EnsoAi\outlookEmail\dev\browser-extension\popup.html`（预览版）**重命名**为 `popup.preview.html`
2. **再**创建全新的 `E:\hushaokang\Data-code\EnsoAi\outlookEmail\dev\browser-extension\popup.html`（正式版）

执行命令（PowerShell）：
```powershell
Rename-Item -Path "E:\hushaokang\Data-code\EnsoAi\outlookEmail\dev\browser-extension\popup.html" -NewName "popup.preview.html"
```
然后创建新文件 `popup.html`。

## 正式版与预览版的核心区别

| 维度 | 预览版 | 正式版 |
|------|--------|--------|
| 内联 JS | 有 `<script>` 块和 `onclick` | **无**（MV3 CSP 禁止） |
| JS 引入 | 内联 | `<script src="storage.js">` + `<script src="popup.js">` |
| CSS | 内联 `<style>` | 内联 `<style>`（MV3 允许内联 CSS，保持原样） |
| Preview Bar | 底部预览状态切换栏 | **移除** |
| 消息提示 | 无 | **新增** `#message-bar` |
| 倒计时/警告 | 无 | **新增** `#fetch-warning` |
| 链接操作 | 无 | **新增** result 区域内 `#btn-open-link` 按钮 |
| 复制按钮 | `onclick="copyText(...)"` | `id` 引用，JS 中 addEventListener 绑定 |
| body 样式 | 居中+padding（浏览器预览用） | 适配 Popup 窗口（无 padding，无居中） |

## 正式版 HTML 完整结构要求

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>邮箱池助手</title>
  <style>
    /* 完整保留预览版的所有 CSS 变量和样式规则（从 :root 到 .status-release）*/
    /* 但需移除 .preview-bar / .ps-btn 相关样式 */
    /* 需修改 body 样式：移除 display:flex/justify-content/align-items/padding/min-height */
    /* body 新样式：margin:0; width:380px; （固定 Popup 宽度）*/

    /* ★ 新增样式 */
    /* .message-bar: 消息提示条 */
    /* .message-error: 红色背景 */
    /* .message-success: 绿色背景 */
    /* .message-warning: 黄色背景 */
    /* #fetch-warning: 获取等待警告区域 */
  </style>
</head>
<body>

<div class="popup">
  <!-- Header：与预览版相同结构，但按钮无 onclick -->
  <div class="header">
    <div class="header-logo">
      <div class="logo-mark">📬</div>
      <div>
        <div class="logo-text">邮箱池助手</div>
        <div class="logo-sub">OutlookMail Plus</div>
      </div>
    </div>
    <button class="header-btn" id="header-settings-btn" title="设置">⚙</button>
  </div>

  <!-- ★ 消息提示条 -->
  <div id="message-bar" class="message-bar" style="display:none;"></div>

  <div class="content">
    <!-- ① state-empty：与预览版相同结构，但按钮无 onclick -->
    <div class="state-empty active" id="state-empty">
      <div class="empty-hint">
        <div class="empty-icon">📬</div>
        <div>暂无进行中的申领任务<br>从邮箱池申领一个邮箱开始使用</div>
      </div>
      <div class="form-group">
        <label class="form-label">项目 Key（可选）</label>
        <input class="form-input" type="text" id="project-key-input"
               placeholder="e.g. OpenAI / Grok / Claude">
      </div>
      <button class="btn btn-primary" id="btn-claim">
        <span>📧</span> 申领邮箱
      </button>
    </div>

    <!-- ② state-task -->
    <div class="state-task" id="state-task">
      <div class="email-card">
        <div class="card-label">当前申领邮箱</div>
        <div class="status-badge badge-waiting">
          <span class="badge-dot"></span>等待使用
        </div>
        <div class="email-row">
          <span class="email-address" id="current-email"></span>
          <button class="btn-copy" id="btn-copy-email">📋 复制</button>
        </div>
      </div>

      <!-- ★ 获取等待警告（fetching 状态时显示）-->
      <div id="fetch-warning" style="display:none;
        background:rgba(230,126,34,.1); border:1px solid rgba(230,126,34,.3);
        border-radius:var(--radius-sm); padding:8px 10px; margin-bottom:8px;
        font-size:12px; color:var(--clr-warn); text-align:center;">
        ⚠️ 等待验证码期间请勿关闭面板
      </div>

      <button class="btn btn-outline" id="btn-get-code">
        <span>🔢</span> 获取最新验证码
      </button>
      <button class="btn btn-ghost" id="btn-get-link" style="margin-top:6px">
        <span>🔗</span> 获取验证链接
      </button>

      <!-- 结果展示框 -->
      <div class="result-box" id="result-box">
        <div class="result-label" id="result-label">验证码</div>
        <div class="result-row">
          <span class="result-value" id="result-value"></span>
          <button class="btn-copy" id="btn-copy-result">📋 复制</button>
        </div>
        <!-- ★ 打开链接按钮（仅 result_link 状态显示）-->
        <button class="btn btn-outline" id="btn-open-link"
                style="display:none; margin-top:8px; font-size:12px;">
          🔗 在新标签页中打开
        </button>
      </div>

      <hr class="divider">
      <div class="btn-row">
        <button class="btn btn-jade" id="btn-complete">✅ 完成（成功）</button>
        <button class="btn btn-danger-outline" id="btn-release">↩ 释放邮箱</button>
      </div>
    </div>

    <!-- ③ state-settings -->
    <div class="state-settings" id="state-settings">
      <div class="settings-title">⚙️ 服务配置</div>
      <div class="settings-group">
        <label class="form-label">服务器地址</label>
        <input class="form-input" type="url" id="cfg-server"
               placeholder="https://your-server.com">
      </div>
      <div class="settings-group">
        <label class="form-label">API Key（X-API-Key）</label>
        <input class="form-input" type="password" id="cfg-apikey"
               placeholder="your-api-key-here">
      </div>
      <div class="settings-group">
        <label class="form-label">默认项目 Key（可选）</label>
        <input class="form-input" type="text" id="cfg-project"
               placeholder="留空则不传 project_key">
      </div>
      <button class="btn btn-primary" id="btn-save">💾 保存配置</button>
      <button class="btn btn-ghost" id="btn-back" style="margin-top:6px">← 返回</button>
    </div>
  </div>

  <!-- History -->
  <div class="history-section">
    <div class="history-header" id="history-header">
      <div class="history-title">
        📋 历史记录
        <span class="history-count" id="history-count">0</span>
      </div>
      <span class="history-caret" id="history-caret">▼</span>
    </div>
    <div class="history-list" id="history-list"></div>
  </div>
</div>

<script src="storage.js"></script>
<script src="popup.js"></script>
</body>
</html>
```

## CSS 要点

从预览版**完整复制**以下 CSS（保留所有设计 Token 和组件样式）：
- `:root` 变量定义
- `* { box-sizing... }` 重置
- `.popup` / `.header` / `.header-logo` / `.logo-mark` / `.logo-text` / `.logo-sub` / `.header-btn`
- `.content` / `.state-empty` / `.state-task` / `.state-settings` / `.active`
- `.empty-hint` / `.empty-icon`
- `.form-group` / `.form-label` / `.form-input`
- `.btn` / `.btn-primary` / `.btn-jade` / `.btn-outline` / `.btn-danger-outline` / `.btn-ghost` / `.btn-row`
- `.email-card` / `.card-label` / `.status-badge` / `.badge-waiting` / `.badge-dot` / `@keyframes pulse`
- `.email-row` / `.email-address` / `.btn-copy` / `.btn-copy.copied`
- `.result-box` / `.result-box.show` / `.result-label` / `.result-row` / `.result-value` / `.result-value.link-mode`
- `.divider`
- `.settings-title` / `.settings-group`
- `.spinner` / `.spinner-brown` / `@keyframes spin`
- `.history-section` / `.history-header` / `.history-title` / `.history-count` / `.history-caret` / `.history-list` / `.history-item` / `.history-email` / `.history-meta` / `.history-code` / `.status-done` / `.status-release`

**需修改**的 CSS：
- `body`：改为 `body { font-family: var(--font); margin: 0; width: 380px; background: var(--bg); }`
- `.popup`：改为 `width: 100%;`（去掉固定 380px，由 body 控制宽度）

**需新增**的 CSS：

```css
/* 消息提示条 */
.message-bar {
  padding: 8px 12px;
  font-size: 12px;
  text-align: center;
  border-bottom: 1px solid var(--border-light);
}
.message-error { background: rgba(192,57,43,.1); color: var(--clr-danger); }
.message-success { background: rgba(58,125,68,.1); color: var(--clr-jade); }
.message-warning { background: rgba(230,126,34,.1); color: var(--clr-warn); }
```

**需移除**的 CSS：
- `.preview-bar` 及其所有子样式
- `.ps-btn` 及其所有状态样式

## 关键约束

1. **无任何内联 JS**：无 `onclick`，无 `<script>` 块（仅 `<script src="...">` 引入外部文件）
2. **MV3 CSP 合规**：Manifest V3 禁止内联脚本，所有 JS 必须为外部文件
3. **script 引入顺序**：先 `storage.js`，后 `popup.js`（popup.js 依赖 Storage 全局对象）
4. **所有交互元素必须有 id**，供 popup.js 中 `addEventListener` 绑定
5. **设置表单输入框无 `value` 预填值**（由 popup.js init 时从 storage 读取并填充）
6. **history-list 初始为空**（由 popup.js renderHistory 动态生成）
7. **history-count 初始为 `0`**
8. **current-email 初始为空**（由 renderState 动态填充）

## 验证标准

- HTML 合法，无内联 JS
- 包含 `<script src="storage.js">` 和 `<script src="popup.js">`
- 所有交互元素有 id 属性
- 无 `onclick`/`onchange` 等内联事件
- 无 `.preview-bar` 相关元素
- 有 `#message-bar`、`#fetch-warning`、`#btn-open-link` 新增元素
- CSS 保留所有设计 Token 和组件样式

## 依赖

- E-03（popup.js 中绑定的 DOM ID 需与此 HTML 一致）
- E-05（重命名当前 popup.html 为 popup.preview.html，操作上与 E-04 同步）


=== E-05 提示词 ===

# E-05：保留预览版为 popup.preview.html

## 任务

确认 `E:\hushaokang\Data-code\EnsoAi\outlookEmail\dev\browser-extension\popup.preview.html` 文件存在且内容完整。

## 上下文

此任务在 E-04 中已完成重命名操作（`popup.html` → `popup.preview.html`）。E-05 的职责是**验证**预览版文件的完整性和可用性。

如果 E-04 尚未执行，需先执行重命名：
```powershell
Rename-Item -Path "E:\hushaokang\Data-code\EnsoAi\outlookEmail\dev\browser-extension\popup.html" -NewName "popup.preview.html"
```

## 验证清单

1. 文件 `popup.preview.html` 存在于 `browser-extension\` 目录
2. 文件包含完整的内联 CSS（`:root` 变量 + 所有组件样式）
3. 文件包含底部 Preview Bar（`.preview-bar` + `.ps-btn` 按钮组）
4. 文件包含内联 `<script>` 块（含 `previewState`、`switchContent`、`doClaimEmail` 等预览交互函数）
5. 文件可独立在浏览器中打开使用（`file://` 协议），无需扩展环境
6. 文件 title 为 "邮箱池助手 - UI Preview"

## 预览版的用途

- 供设计师/PM 在浏览器中直接打开查看 UI 效果
- 作为 UI 回归参考基准
- 底部 Preview Bar 可切换 5 种状态预览

## 依赖

- 与 E-04 同步执行（E-04 负责重命名 + 创建正式版，E-05 负责验证预览版）


=== E-06 提示词 ===

# E-06：生成扩展图标（3 种尺寸 PNG）

## 任务

在 `E:\hushaokang\Data-code\EnsoAi\outlookEmail\dev\browser-extension\icons\` 目录下生成 3 个 PNG 图标文件：
- `icon16.png` — 16×16 像素
- `icon48.png` — 48×48 像素
- `icon128.png` — 128×128 像素

## 设计规格

- **主色调**：砖红色 `#B85C38`（与项目国风配色一致）
- **辅助色**：`#C8963E`（金色，用于渐变或装饰）
- **风格**：国风配色，简洁。信封图形为主体，或"邮"字/📬 图标化
- **背景**：圆角矩形背景（radius ≈ 20%），砖红到金色渐变
- **前景**：白色信封图形（简笔画风格）

## Python Pillow 生成脚本

请先确保安装 Pillow：`pip install Pillow`

然后执行以下 Python 脚本：

```python
"""
为 OutlookMail Plus 浏览器扩展生成 3 种尺寸的图标。
用法：在项目目录下运行 python generate_icons.py
"""
import os
from PIL import Image, ImageDraw, ImageFont

ICON_DIR = r"E:\hushaokang\Data-code\EnsoAi\outlookEmail\dev\browser-extension\icons"
os.makedirs(ICON_DIR, exist_ok=True)

SIZES = [16, 48, 128]
PRIMARY = (184, 92, 56)    # #B85C38
ACCENT  = (200, 150, 62)   # #C8963E
WHITE   = (255, 255, 255)

def make_icon(size):
    """生成单个图标"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 圆角矩形背景（砖红色渐变效果用纯色替代以保证小尺寸清晰度）
    radius = max(size // 5, 2)
    draw.rounded_rectangle(
        [0, 0, size - 1, size - 1],
        radius=radius,
        fill=PRIMARY,
    )

    if size >= 48:
        # 48px 和 128px：绘制信封图形
        margin = size // 5
        env_left = margin
        env_right = size - margin
        env_top = size * 3 // 10
        env_bottom = size * 7 // 10

        # 信封矩形
        draw.rectangle(
            [env_left, env_top, env_right, env_bottom],
            outline=WHITE,
            width=max(size // 24, 1),
        )

        # 信封翻盖（V 形）
        mid_x = size // 2
        flap_bottom = (env_top + env_bottom) // 2 + size // 20
        line_w = max(size // 24, 1)
        draw.line(
            [(env_left, env_top), (mid_x, flap_bottom), (env_right, env_top)],
            fill=WHITE,
            width=line_w,
        )

        # 小装饰：右上角金色小圆点
        dot_r = max(size // 16, 2)
        dot_cx = env_right - dot_r
        dot_cy = env_top - dot_r
        draw.ellipse(
            [dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r],
            fill=ACCENT,
        )
    else:
        # 16px：极简信封（仅画基本轮廓）
        m = 3
        draw.rectangle([m, m + 2, size - m - 1, size - m - 1], outline=WHITE, width=1)
        mid = size // 2
        draw.line([(m, m + 2), (mid, mid + 1), (size - m - 1, m + 2)], fill=WHITE, width=1)

    return img

for s in SIZES:
    icon = make_icon(s)
    path = os.path.join(ICON_DIR, f"icon{s}.png")
    icon.save(path, "PNG")
    print(f"✅ Generated {path} ({s}x{s})")

print("Done! All icons generated.")
```

## 执行步骤

1. 确保 Python 环境可用，安装 Pillow：
   ```powershell
   pip install Pillow
   ```
2. 将上述脚本保存为临时文件并执行：
   ```powershell
   python generate_icons.py
   ```
3. 验证 3 个文件已生成
4. 删除临时脚本文件

## 验证标准

- `icons\icon16.png` 存在且为 16×16 PNG
- `icons\icon48.png` 存在且为 48×48 PNG
- `icons\icon128.png` 存在且为 128×128 PNG
- 所有文件为合法 PNG 格式（可被浏览器渲染）
- 主色调为砖红色系

可用 Python 验证：
```python
from PIL import Image
for s in [16, 48, 128]:
    img = Image.open(rf"E:\hushaokang\Data-code\EnsoAi\outlookEmail\dev\browser-extension\icons\icon{s}.png")
    assert img.size == (s, s), f"icon{s}.png size mismatch"
    assert img.format == "PNG"
    print(f"✅ icon{s}.png OK")
```

## 依赖

无前置依赖，可独立执行。仅需 Python + Pillow。


=== E-07 提示词 ===

# E-07：创建 README.md（安装与使用说明）

## 任务

在 `E:\hushaokang\Data-code\EnsoAi\outlookEmail\dev\browser-extension\README.md` 创建浏览器扩展的安装和使用说明文档。

## 文档结构与完整内容

请创建以下 Markdown 文件：

```markdown
# 📬 邮箱池快捷操作 — 浏览器扩展

> OutlookMail Plus 伴生扩展 v0.1.0

Chrome / Edge 浏览器扩展，提供「申领邮箱 → 获取验证码/链接 → 完成/释放」一站式快捷操作面板。

## 功能

- 🔑 一键从邮箱池申领可用邮箱
- 📋 邮箱地址、验证码一键复制
- 🔗 验证链接一键打开
- 📊 操作历史记录（最近 100 条）
- ⌨️ 快捷键 `Ctrl+Shift+E`（Mac: `Cmd+Shift+E`）快速呼出
- 🔒 API Key 本地存储，权限按需申请

## 安装（开发者模式）

### Chrome

1. 打开 `chrome://extensions/`
2. 开启右上角 **开发者模式**
3. 点击 **加载已解压的扩展程序**
4. 选择 `browser-extension` 文件夹
5. 扩展图标出现在工具栏

### Edge

1. 打开 `edge://extensions/`
2. 开启左下角 **开发人员模式**
3. 点击 **加载解压缩**
4. 选择 `browser-extension` 文件夹

## 首次使用

1. 点击工具栏的扩展图标（或按 `Ctrl+Shift+E`）
2. 点击右上角 ⚙ 进入设置
3. 填写：
   - **服务器地址**：你的 OutlookMail Plus 服务地址（如 `https://demo.outlookmailplus.tech`）
   - **API Key**：外部接口的 X-API-Key
   - **默认项目 Key**（可选）：常用的 project_key
4. 点击 **保存配置**，浏览器会弹出权限确认框，选择 **允许**
5. 返回主面板，点击 **申领邮箱** 开始使用

## 使用流程

```
申领邮箱 → 复制邮箱地址 → 去目标网站注册
                ↓
        获取验证码 / 获取验证链接
                ↓
        复制验证码 / 打开链接
                ↓
        完成（成功）或 释放邮箱
```

## 文件结构

```
browser-extension/
├── manifest.json          # Chrome MV3 清单
├── popup.html             # 正式版弹出面板
├── popup.preview.html     # UI 预览版（可独立在浏览器打开）
├── popup.js               # 主交互逻辑
├── storage.js             # chrome.storage.local 封装
├── icons/
│   ├── icon16.png         # 16×16 图标
│   ├── icon48.png         # 48×48 图标
│   └── icon128.png        # 128×128 图标
└── README.md              # 本文件
```

## 技术栈

- Chrome Extension Manifest V3
- 原生 JavaScript（无框架、无构建步骤）
- chrome.storage.local 本地持久化
- chrome.permissions 动态权限申请

## 与主应用的关系

本扩展调用 OutlookMail Plus 的**外部 API**（`/api/external/*`），需要：

1. 主应用已启用 CORS（`flask-cors`，已配置在 `outlook_web/app.py`）
2. 已在主应用设置中创建 API Key
3. 网络可达主应用服务地址

## 权限说明

| 权限 | 用途 | 申请时机 |
|------|------|----------|
| `storage` | 存储配置和任务状态 | 安装时自动获取 |
| `tabs` | 打开验证链接到新标签 | 安装时自动获取 |
| 主机权限 | 访问你的服务器 API | 保存设置时按需申请 |

## 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| "请先在设置中配置" | 未配置服务器地址或 API Key | 点击 ⚙ 填写配置 |
| "无法连接服务器" | 服务器地址错误或网络不通 | 检查地址、网络、CORS 配置 |
| "等待超时" | 60s 内未收到新邮件 | 确认邮件已发送，重试 |
| 权限弹窗被拒绝 | 浏览器权限被拒绝 | 重新保存设置并允许权限 |
| 扩展图标灰色 | 扩展被禁用或加载失败 | 检查 manifest.json 语法 |

## 开发调试

- **UI 预览**：直接在浏览器打开 `popup.preview.html`，底部状态栏可切换各状态
- **扩展调试**：右键扩展图标 → 审查弹出内容，打开 DevTools
- **日志**：popup.js 中的关键操作有 console.log，可在 DevTools Console 查看
```

## 关键约束

1. 使用中文编写
2. 包含 Chrome 和 Edge 两种浏览器的安装步骤
3. 文件结构必须与实际文件一致
4. 权限说明要准确反映 manifest.json 中的声明
5. 故障排查覆盖常见问题

## 验证标准

- Markdown 格式正确，可正常渲染
- 安装步骤清晰、可操作
- 文件结构与实际一致
- 权限说明与 manifest.json 匹配

## 依赖

- E-01（manifest.json 已创建，需引用其中的权限和版本号信息）
