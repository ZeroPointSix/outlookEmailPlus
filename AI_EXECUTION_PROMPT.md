# AI 执行提示词 - Outlook 邮件管理工具批量操作与自动化增强

## 项目背景

你正在为一个 Outlook 邮件管理工具添加三个核心功能：

1. **全选功能**：在分组面板的排序按钮右边添加全选复选框，支持一键选中当前分组下的所有邮箱账号，用于批量操作（移动分组、打标签）
2. **邮件信息快速复制功能**：在每个邮箱账号名称右边添加复制按钮，点击后自动提取最新邮件中的验证码和链接并复制到剪贴板
3. **自动轮询与通知功能**：支持定时轮询选中邮箱的新邮件，检测到新邮件时显示页面通知和视觉提示（红点）

## 核心技术要求

### 验证码提取算法
- **智能识别**：基于关键词（"验证码"、"code"、"OTP"等）搜索上下文（前后50字符），提取4-8位数字/字母组合
- **保底提取**：使用正则表达式提取所有4-8位数字/字母组合，过滤日期（1900-2100）和时间（00:00-23:59）格式
- **链接提取**：使用正则提取所有HTTP/HTTPS链接并去重
- **输出格式**：`验证码 链接1 链接2`（空格分隔）

### 性能指标
- 全选1000个邮箱：< 100ms
- 验证码提取API响应：< 2秒
- 轮询不影响页面交互

### 轮询机制
- 客户端定时器（setInterval）
- 默认配置：10秒间隔，5次轮询
- 静默轮询，仅在检测到新邮件时显示通知
- 切换邮箱或达到次数后自动停止

## 参考文档

在开始实现前，请仔细阅读以下文档：

1. **PRD（产品需求文档）**：`docs/PRD/Outlook邮件管理工具-批量操作与自动化增强PRD.md`
   - 了解业务目标、用户故事、功能需求

2. **FD（功能设计文档）**：`docs/FD/Outlook邮件管理工具-批量操作与自动化增强FD.md`
   - 了解需要实现的功能清单（27项功能验收 + 5项非功能验收 + 5项回归验收）

3. **TDD（技术设计文档）**：`docs/TDD/Outlook邮件管理工具-批量操作与自动化增强TDD.md`
   - 了解详细的技术实现方案、算法设计、API规范、数据结构

4. **TODO（任务清单）**：`docs/TODO/Outlook邮件管理工具-批量操作与自动化增强TODO.md`
   - 这是你的主要执行指南，包含详细的任务分解和验收标准

5. **测试文档**：`docs/TEST/` 目录下的测试文档
   - 了解测试用例和验收标准

6. **测试代码**：`tests/` 目录下的测试文件
   - 参考已准备好的测试用例结构

## 执行计划

请严格按照以下阶段顺序执行，每个阶段完成后进行自测：

### 阶段 0：准备工作（必须先完成）

```bash
# 1. 确认现有测试通过
python -m unittest discover -s tests -v

# 2. 准备测试邮件样本
# 创建至少10封测试邮件，覆盖不同验证码格式（参考测试文档中的15个邮件样本）
```

**验收标准**：
- [ ] 所有现有单元测试通过
- [ ] 测试邮件样本已准备（至少10封）
- [ ] 已仔细阅读所有参考文档

---

### 阶段 1：后端基础（2-3天）

**目标**：实现验证码提取服务和API接口

#### 1.1 创建验证码提取服务

**文件**：`outlook_web/services/verification_extractor.py`

**核心函数**：
```python
def smart_extract_verification_code(email_content: str) -> Optional[str]:
    """智能识别验证码（基于关键词）"""
    pass

def fallback_extract_verification_code(email_content: str) -> Optional[str]:
    """保底提取验证码（正则 + 过滤）"""
    pass

def extract_links(email_content: str) -> List[str]:
    """提取所有HTTP/HTTPS链接"""
    pass

def extract_email_text(email: dict) -> str:
    """从邮件对象提取纯文本（HTML转文本）"""
    pass

def extract_verification_info(email: dict) -> dict:
    """完整提取流程（验证码 + 链接 + 格式化）"""
    pass
```

**实现要点**：
- 关键词列表：`["验证码", "code", "验证", "verification", "OTP", "动态码", "校验码", "verify code"]`
- 验证码正则：`r'\b[A-Z0-9]{4,8}\b'`
- 链接正则：`r'https?://[^\s<>"{}|\\^`\[\]]+'`
- 日期过滤：`1900 <= year <= 2100`
- 时间过滤：`00:00 <= time <= 23:59`

#### 1.2 创建API接口

**文件**：`outlook_web/routes/emails.py` 和 `outlook_web/legacy.py`

**路由**：`GET /api/emails/<email>/extract-verification`

**响应格式**：
```json
{
  "success": true,
  "data": {
    "verification_code": "123456",
    "links": ["https://example.com/verify"],
    "formatted": "123456 https://example.com/verify"
  },
  "trace_id": "uuid"
}
```

**错误处理**：
- 邮箱不存在 → 404
- 未找到邮件 → 404
- 未找到验证信息 → 404
- Token过期 → 401
- 服务器错误 → 500

#### 1.3 编写单元测试

**文件**：`tests/test_verification_extractor.py`（已创建，需要实现TODO部分）

**测试覆盖**：
- 智能识别：中文关键词、英文关键词、OTP关键词
- 保底提取：纯数字、数字+字母、过滤日期/时间
- 链接提取：单个、多个、去重
- 边界情况：空邮件、未找到、HTML转文本

**验收标准**：
- [ ] 所有单元测试通过（18个测试用例）
- [ ] 验证码提取成功率 > 90%（基于测试邮件样本）
- [ ] API响应时间 < 2秒

---

### 阶段 2：后端配置（1天）

**目标**：添加轮询配置到数据库和设置API

#### 2.1 数据库变更

**文件**：`outlook_web/db.py`

**修改位置**：`init_db()` 函数

**添加配置**：
```python
# 在 init_db() 函数中添加
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
               ("enable_auto_polling", "false"))
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
               ("polling_interval", "10"))
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
               ("polling_count", "5"))
```

#### 2.2 更新设置API

**文件**：`outlook_web/legacy.py`

**修改接口**：
- `GET /api/settings`：添加返回 `enable_auto_polling`、`polling_interval`、`polling_count`
- `PUT /api/settings`：添加处理这三个字段，验证范围（interval: 5-300, count: 1-100）

**验收标准**：
- [ ] 数据库初始化时自动创建配置项
- [ ] GET /api/settings 返回轮询配置
- [ ] PUT /api/settings 可以更新轮询配置
- [ ] 参数验证正确（超出范围返回400错误）

---

### 阶段 3：前端基础（2-3天）

**目标**：实现全选功能和复制按钮

#### 3.1 全选功能

**文件**：`static/js/features/accounts.js` 或 `static/js/main.js`

**核心函数**：
```javascript
// 全选状态枚举
const SelectAllState = {
    NONE: 'none',      // 未选中
    PARTIAL: 'partial', // 部分选中
    ALL: 'all'         // 全选
};

// 全选/取消全选
function toggleSelectAll() {
    const state = getSelectAllState();
    if (state === SelectAllState.ALL) {
        unselectAllAccounts();
    } else {
        selectAllAccounts();
    }
}

// 选中所有邮箱
function selectAllAccounts() {
    // 使用 Set 数据结构（O(1)查找）
    // 使用 requestAnimationFrame 优化渲染
}

// 更新全选复选框状态
function updateSelectAllCheckbox() {
    const checkbox = document.getElementById('selectAllAccounts');
    const state = getSelectAllState();

    checkbox.checked = (state === SelectAllState.ALL);
    checkbox.indeterminate = (state === SelectAllState.PARTIAL);
}
```

**HTML结构**（在排序按钮右边添加）：
```html
<label class="select-all-container">
    <input type="checkbox" id="selectAllAccounts" />
    <span>全选</span>
</label>
```

**CSS样式**：
```css
.select-all-container {
    display: inline-flex;
    align-items: center;
    margin-left: 10px;
}

input[type="checkbox"]:indeterminate {
    /* 半选状态样式 */
}
```

#### 3.2 复制按钮

**文件**：`static/js/features/accounts.js`

**核心函数**：
```javascript
async function copyVerificationInfo(email) {
    const btn = event.target;

    // 1. 设置加载状态
    btn.disabled = true;
    btn.classList.add('loading');

    try {
        // 2. 调用API提取验证信息
        const response = await fetch(`/api/emails/${email}/extract-verification`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || '提取失败');
        }

        // 3. 复制到剪贴板
        await copyToClipboard(data.data.formatted);

        // 4. 显示成功状态
        showNotification('已复制');
        btn.classList.add('success');
        setTimeout(() => btn.classList.remove('success'), 1000);

    } catch (error) {
        // 5. 处理错误
        if (error.message.includes('未找到')) {
            showNotification('未找到验证信息', 'error');
        } else {
            showNotification('复制失败', 'error');
        }
    } finally {
        // 6. 恢复按钮状态
        btn.disabled = false;
        btn.classList.remove('loading');
    }
}

async function copyToClipboard(text) {
    // 优先使用 Clipboard API
    if (navigator.clipboard) {
        await navigator.clipboard.writeText(text);
    } else {
        // 降级方案：execCommand
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
    }
}
```

**HTML结构**（在账号名称右边添加）：
```html
<button class="copy-verification-btn" onclick="copyVerificationInfo('${account.email}')">
    <i class="icon-copy"></i>
</button>
```

**验收标准**：
- [ ] 全选复选框显示在排序按钮右边
- [ ] 点击全选可以选中/取消选中所有邮箱
- [ ] 半选状态正确显示
- [ ] 切换分组时全选状态重置
- [ ] 复制按钮显示在账号名称右边
- [ ] 点击复制按钮成功复制验证码和链接
- [ ] 显示"已复制"通知
- [ ] 按钮有加载/成功/失败状态的视觉反馈
- [ ] 全选1000个邮箱耗时 < 100ms

---

### 阶段 4：前端轮询与通知（2-3天）

**目标**：实现自动轮询和新邮件通知

#### 4.1 设置界面

**文件**：`templates/index.html` 或设置模态框

**HTML结构**：
```html
<div class="setting-item">
    <label>
        <input type="checkbox" id="enableAutoPolling" />
        启用自动轮询
    </label>
</div>
<div class="setting-item">
    <label>轮询间隔（秒）：</label>
    <input type="number" id="pollingInterval" min="5" max="300" value="10" />
    <span class="hint">建议：10-30秒</span>
</div>
<div class="setting-item">
    <label>轮询次数：</label>
    <input type="number" id="pollingCount" min="1" max="100" value="5" />
    <span class="hint">建议：3-10次</span>
</div>
```

#### 4.2 轮询逻辑

**文件**：`static/js/features/polling.js` 或 `static/js/main.js`

**核心函数**：
```javascript
// 全局变量
let pollingTimer = null;
let pollingCount = 0;
let pollingMaxCount = 5;
let pollingInterval = 10000; // 毫秒
let isPollingEnabled = false;
let lastEmailIds = new Set();

// 启动轮询
function startPolling(email) {
    if (!isPollingEnabled) return;

    stopPolling(); // 先停止之前的轮询

    pollingCount = 0;
    lastEmailIds = new Set(getCurrentEmails().map(e => e.id));

    console.log(`开始轮询邮箱: ${email}, 间隔: ${pollingInterval}ms, 次数: ${pollingMaxCount}`);

    pollingTimer = setInterval(() => {
        pollForNewEmails(email);
    }, pollingInterval);
}

// 停止轮询
function stopPolling() {
    if (pollingTimer) {
        clearInterval(pollingTimer);
        pollingTimer = null;
        console.log('停止轮询');
    }
}

// 轮询检查新邮件
async function pollForNewEmails(email) {
    pollingCount++;
    console.log(`轮询第 ${pollingCount}/${pollingMaxCount} 次`);

    try {
        // 1. 获取最新邮件列表
        const response = await fetch(`/api/emails/${email}`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error('获取邮件失败');
        }

        // 2. 检测新邮件
        const newEmails = detectNewEmails(lastEmailIds, data.emails);

        // 3. 如果有新邮件，显示通知
        if (newEmails.length > 0) {
            showNewEmailNotification(email, newEmails);
            showNewEmailBadge(email);
        }

        // 4. 更新邮件ID集合
        lastEmailIds = new Set(data.emails.map(e => e.id));

        // 5. 达到次数后停止
        if (pollingCount >= pollingMaxCount) {
            stopPolling();
            console.log('轮询已完成');
        }

    } catch (error) {
        console.error('轮询失败:', error);
        stopPolling();
        showNotification('轮询失败，已自动停止', 'error');
    }
}

// 检测新邮件
function detectNewEmails(oldEmailIds, newEmails) {
    return newEmails.filter(email => !oldEmailIds.has(email.id));
}
```

#### 4.3 通知组件

**文件**：`static/js/features/notification.js`

**核心函数**：
```javascript
function showNewEmailNotification(email, newEmails) {
    const notification = document.createElement('div');
    notification.className = 'email-notification';
    notification.innerHTML = `
        <div class="notification-header">
            <span>${email}</span>
            <button class="close-btn" onclick="this.parentElement.parentElement.remove()">×</button>
        </div>
        <div class="notification-body">
            收到新邮件：${newEmails[0].subject}
        </div>
    `;

    document.body.appendChild(notification);

    // 5秒后自动消失
    setTimeout(() => {
        notification.remove();
    }, 5000);
}

function showNewEmailBadge(email) {
    const accountItem = document.querySelector(`[data-email="${email}"]`);
    if (accountItem) {
        const badge = document.createElement('span');
        badge.className = 'new-email-badge';
        accountItem.appendChild(badge);
    }
}

function hideNewEmailBadge(email) {
    const badge = document.querySelector(`[data-email="${email}"] .new-email-badge`);
    if (badge) {
        badge.remove();
    }
}
```

**CSS样式**：
```css
.email-notification {
    position: fixed;
    top: 20px;
    right: 20px;
    background: white;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    padding: 16px;
    min-width: 300px;
    animation: slideIn 0.3s ease-out;
    z-index: 9999;
}

@keyframes slideIn {
    from {
        transform: translateX(400px);
        opacity: 0;
    }
    to {
        transform: translateX(0);
        opacity: 1;
    }
}

.new-email-badge {
    display: inline-block;
    width: 8px;
    height: 8px;
    background: #ff4444;
    border-radius: 50%;
    margin-left: 8px;
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
```

**集成到现有代码**：
```javascript
// 在 selectAccount() 函数中添加
function selectAccount(email) {
    // ... 现有代码 ...

    // 启动轮询
    startPolling(email);

    // 清除红点
    hideNewEmailBadge(email);
}

// 在 loadAccountsByGroup() 函数中添加
function loadAccountsByGroup(groupId) {
    // 停止轮询
    stopPolling();

    // ... 现有代码 ...
}

// 在页面卸载时停止轮询
window.addEventListener('beforeunload', () => {
    stopPolling();
});
```

**验收标准**：
- [ ] 设置界面显示轮询配置项
- [ ] 启用轮询后选中邮箱时自动开始轮询
- [ ] 轮询到达次数后自动停止
- [ ] 检测到新邮件时显示通知
- [ ] 邮箱列表显示红点提示
- [ ] 轮询过程不影响页面操作
- [ ] 切换邮箱时停止当前轮询
- [ ] 通知5秒后自动消失

---

### 阶段 5：优化与完善（1-2天）

**目标**：性能优化、用户体验优化、测试完善

#### 5.1 性能优化

**全选性能优化**：
```javascript
function selectAllAccounts() {
    const accounts = Array.from(document.querySelectorAll('.account-item'));

    // 使用 DocumentFragment 减少重排重绘
    requestAnimationFrame(() => {
        accounts.forEach(account => {
            const checkbox = account.querySelector('.account-checkbox');
            checkbox.checked = true;
            selectedAccounts.add(account.dataset.email);
        });
        updateBatchActionBar();
        updateSelectAllCheckbox();
    });
}
```

**验证码提取性能优化**：
- 优化正则表达式（避免回溯）
- 缓存邮件内容（避免重复提取）

**轮询性能优化**：
- 使用 `async/await` 避免阻塞
- 使用 `AbortController` 支持取消请求

#### 5.2 用户体验优化

- 复制按钮添加 tooltip 提示
- 通知组件支持多条通知队列
- 设置界面添加配置说明和建议值

#### 5.3 测试完善

**运行所有测试**：
```bash
# 单元测试
python -m unittest discover -s tests -v

# 手动测试（参考 tests/test_frontend_manual.py）
# 在浏览器中执行测试用例
```

**验收标准**：
- [ ] 所有单元测试通过（18个）
- [ ] 所有API测试通过（9个）
- [ ] 所有前端测试通过（21个）
- [ ] 所有性能测试通过（3个）
- [ ] 所有回归测试通过（5个）

---

## 最终验收清单（必须全部通过）

### 功能验收（27项）

#### 全选功能（7项）
- [ ] 全选复选框显示在排序按钮右边
- [ ] 点击全选复选框可以选中/取消选中当前分组下的所有邮箱
- [ ] 全选状态与邮箱列表选中状态实时同步（全选/半选/未选）
- [ ] 全选后可以执行批量移动分组操作
- [ ] 全选后可以执行批量打标签/去标签操作
- [ ] 切换分组时全选状态重置
- [ ] 搜索或筛选后，全选只影响当前显示的邮箱

#### 复制功能（9项）
- [ ] 复制按钮显示在邮箱名称右边
- [ ] 点击复制按钮可以自动提取验证码和链接
- [ ] 验证码提取成功率 > 90%（基于测试邮件样本）
- [ ] 链接提取能正确提取所有 HTTP/HTTPS 链接
- [ ] 复制成功后显示"已复制"通知
- [ ] 未找到验证信息时显示"未找到验证信息"提示
- [ ] 邮箱无数据时自动触发获取邮件操作
- [ ] 复制按钮有加载状态、成功状态、失败状态的视觉反馈
- [ ] 后端 API `/api/emails/<email>/extract-verification` 正常工作

#### 轮询功能（11项）
- [ ] 设置中心有"自动轮询"配置项（开关、间隔、次数）
- [ ] 启用轮询后，选中邮箱时自动开始轮询
- [ ] 轮询到达设置次数后自动停止
- [ ] 检测到新邮件时显示页面通知（邮箱地址 + 邮件主题）
- [ ] 邮箱列表显示新邮件视觉提示（红点/角标）
- [ ] 轮询过程静默进行，不干扰用户操作
- [ ] 轮询失败时停止并显示错误提示
- [ ] 切换邮箱时停止当前轮询
- [ ] 设置保存后下次选中邮箱时生效
- [ ] 数据库 settings 表包含轮询配置项
- [ ] 通知 5 秒后自动消失或点击关闭

### 非功能验收（5项）
- [ ] 全选操作在 100ms 内完成（1000 个邮箱）
- [ ] 验证码提取 API 响应时间 < 2 秒
- [ ] 轮询不影响页面正常使用
- [ ] 所有操作都有明确的成功/失败反馈
- [ ] 错误提示清晰易懂

### 回归验收（5项）
- [ ] 现有批量操作功能正常（移动分组、打标签）
- [ ] 现有邮件获取功能正常
- [ ] 现有设置功能正常
- [ ] 单元测试通过：`python -m unittest discover -s tests -v`
- [ ] 前端页面关键路径抽样回归（登录、分组/账号、邮件查看）

---

## 重要提示

### 开发原则
1. **小步快跑**：每完成一个小功能就测试，不要一次性写太多代码
2. **测试驱动**：先写测试用例，再实现功能
3. **代码复用**：优先使用现有的函数和组件，避免重复造轮子
4. **错误处理**：所有异步操作都要有 try-catch，所有API调用都要处理错误
5. **性能优先**：注意性能指标，使用性能分析工具验证

### 常见陷阱
1. **验证码识别**：不要过度依赖智能识别，保底规则很重要
2. **浏览器兼容性**：Clipboard API 需要降级方案
3. **轮询性能**：高频轮询会影响性能，使用异步请求
4. **内存泄漏**：记得在页面卸载时清理定时器
5. **状态同步**：全选状态要与邮箱列表实时同步

### 调试技巧
```javascript
// 开启调试日志
const DEBUG = true;
function log(...args) {
    if (DEBUG) console.log('[DEBUG]', ...args);
}

// 性能测试
console.time('全选性能');
selectAllAccounts();
console.timeEnd('全选性能');

// 网络请求监控
// 打开浏览器开发者工具 -> Network 标签
```

---

## 开始执行

现在请按照以下步骤开始执行：

1. **阅读所有参考文档**（PRD、FD、TDD、TODO、测试文档）
2. **完成阶段0的准备工作**（确认测试通过、准备测试数据）
3. **从阶段1开始逐步实现**（后端 → 前端 → 优化）
4. **每个阶段完成后进行自测**（单元测试 + 手动测试）
5. **最终完成所有验收清单**（37项验收标准）

**预计总时间**：8-12天（P0必须完成）

**里程碑**：
- 里程碑1：后端API完成，单元测试通过（3天）
- 里程碑2：前端基础功能完成，手动测试通过（6天）
- 里程碑3：轮询与通知功能完成，集成测试通过（9天）
- 里程碑4：所有验收清单通过，文档更新完成（12天）

祝你开发顺利！如有疑问，请参考技术设计文档（TDD）中的详细说明。
