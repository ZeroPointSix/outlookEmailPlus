# Outlook 邮件管理工具｜批量操作与自动化增强 TDD（技术设计细节）

- 文档状态：草案
- 版本：V1.0
- 日期：2026-02-24
- 对齐 PRD：`docs/PRD/Outlook邮件管理工具-批量操作与自动化增强PRD.md`
- 对齐 FD：`docs/FD/Outlook邮件管理工具-批量操作与自动化增强FD.md`

---

## 1. 文档目的

本 TDD 用于描述"为满足 PRD/FD，批量操作与自动化增强需要采用的技术设计细节"。

重点回答：

- 验证码提取算法的具体实现方案
- 全选功能的性能优化策略（支持 1000+ 邮箱）
- 轮询机制的技术实现（定时器、状态管理、新邮件检测）
- 前端剪贴板 API 的使用与兼容性处理
- 数据库 schema 变更与配置管理
- API 接口设计与错误处理

---

## 2. 设计原则与硬约束（必须满足）

### 2.1 行为兼容性（对用户无感）

- 保持现有 API 路径/方法/参数语义/响应结构不变
- 保持统一错误结构、`trace_id` 透传、默认脱敏策略不变
- 保持登录/会话/CSRF 行为不变
- 新增功能不影响现有功能的正常使用

### 2.2 性能要求

- 全选操作在 100ms 内完成（1000 个邮箱）
- 验证码提取 API 响应时间 < 2 秒
- 轮询操作不阻塞主线程，不影响页面交互

### 2.3 可靠性要求

- 验证码提取成功率 > 90%（基于常见邮件格式）
- 轮询失败时自动停止并提示用户
- 剪贴板操作失败时有降级方案

### 2.4 安全要求

- 验证码提取 API 需要登录验证
- 复制内容不包含敏感信息
- 轮询频率有合理限制

---

## 3. 总体架构设计

### 3.1 功能模块划分

```
批量操作与自动化增强
├── 功能1：全选功能（纯前端）
│   ├── UI 组件（全选复选框）
│   ├── 状态管理（selectedAccounts Set）
│   └── 性能优化（批量 DOM 更新）
│
├── 功能2：邮件信息快速复制（前后端）
│   ├── 后端
│   │   ├── API 接口（/api/emails/<email>/extract-verification）
│   │   ├── 验证码提取服务（智能识别 + 保底规则）
│   │   └── 链接提取服务
│   └── 前端
│       ├── 复制按钮组件
│       ├── 剪贴板 API 调用
│       └── 反馈提示
│
└── 功能3：自动轮询与通知（前后端）
    ├── 后端
    │   ├── 数据库配置项（settings 表）
    │   └── 设置 API 更新
    └── 前端
        ├── 设置界面
        ├── 轮询逻辑（定时器）
        ├── 新邮件检测
        └── 通知组件
```

### 3.2 技术栈

- **后端**：Flask + SQLite + Python 正则表达式
- **前端**：原生 JavaScript + Clipboard API + CSS3 动画
- **数据存储**：SQLite settings 表（key-value 结构）

---

## 4. 后端技术设计细节

### 4.1 验证码提取服务

#### 4.1.1 模块位置

```
outlook_web/services/verification_extractor.py
```

#### 4.1.2 核心算法设计

**智能识别阶段：**

```python
# 关键词列表（支持中英文）
VERIFICATION_KEYWORDS = [
    "验证码", "code", "验证", "verification",
    "OTP", "动态码", "校验码", "verify code",
    "confirmation code", "security code"
]

# 验证码模式（4-8位数字或字母）
VERIFICATION_PATTERN = r'\b[A-Z0-9]{4,8}\b'

def smart_extract_verification_code(email_content):
    """
    智能提取验证码

    算法：
    1. 遍历关键词列表
    2. 在邮件内容中查找关键词位置
    3. 在关键词前后 50 个字符范围内搜索验证码模式
    4. 返回第一个匹配的验证码
    """
    content_lower = email_content.lower()

    for keyword in VERIFICATION_KEYWORDS:
        keyword_lower = keyword.lower()
        pos = content_lower.find(keyword_lower)

        if pos != -1:
            # 提取关键词前后 50 个字符
            start = max(0, pos - 50)
            end = min(len(email_content), pos + len(keyword) + 50)
            context = email_content[start:end]

            # 在上下文中搜索验证码
            matches = re.findall(VERIFICATION_PATTERN, context, re.IGNORECASE)
            if matches:
                # 过滤掉纯字母的匹配（验证码通常包含数字）
                for match in matches:
                    if any(c.isdigit() for c in match):
                        return match

    return None
```

**保底提取阶段：**

```python
def fallback_extract_verification_code(email_content):
    """
    保底提取验证码

    算法：
    1. 提取所有 4-8 位的数字/字母组合
    2. 过滤掉常见的非验证码模式（日期、时间等）
    3. 返回第一个匹配项
    """
    # 提取所有可能的验证码
    matches = re.findall(VERIFICATION_PATTERN, email_content, re.IGNORECASE)

    # 过滤规则
    filtered = []
    for match in matches:
        # 必须包含至少一个数字
        if not any(c.isdigit() for c in match):
            continue

        # 排除纯数字且长度为 4 的（可能是年份）
        if match.isdigit() and len(match) == 4:
            year = int(match)
            if 1900 <= year <= 2100:
                continue

        # 排除常见的时间格式（如 1234 可能是 12:34）
        if match.isdigit() and len(match) == 4:
            hour = int(match[:2])
            minute = int(match[2:])
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                continue

        filtered.append(match)

    return filtered[0] if filtered else None
```

**链接提取：**

```python
def extract_links(email_content):
    """
    提取所有 HTTP/HTTPS 链接

    算法：
    1. 使用正则表达式提取所有链接
    2. 去重并保持顺序
    """
    # 链接正则表达式
    LINK_PATTERN = r'https?://[^\s<>"{}|\\^`\[\]]+'

    matches = re.findall(LINK_PATTERN, email_content, re.IGNORECASE)

    # 去重并保持顺序
    seen = set()
    unique_links = []
    for link in matches:
        if link not in seen:
            seen.add(link)
            unique_links.append(link)

    return unique_links
```

#### 4.1.3 完整提取流程

```python
def extract_verification_info(email_address):
    """
    提取验证信息的完整流程

    返回：
    {
        "verification_code": "123456",
        "links": ["https://example.com/verify"],
        "formatted": "123456 https://example.com/verify"
    }
    """
    # 1. 获取最新邮件（同时从收件箱和垃圾邮件获取）
    latest_email = get_latest_email(email_address)

    if not latest_email:
        raise ValueError("未找到邮件")

    # 2. 提取邮件内容（HTML 转纯文本）
    email_content = extract_email_text(latest_email)

    # 3. 提取验证码（智能识别 + 保底）
    verification_code = smart_extract_verification_code(email_content)
    if not verification_code:
        verification_code = fallback_extract_verification_code(email_content)

    # 4. 提取链接
    links = extract_links(email_content)

    # 5. 格式化输出
    parts = []
    if verification_code:
        parts.append(verification_code)
    parts.extend(links)

    formatted = " ".join(parts) if parts else None

    if not formatted:
        raise ValueError("未找到验证信息")

    return {
        "verification_code": verification_code,
        "links": links,
        "formatted": formatted
    }
```

### 4.2 API 接口设计

#### 4.2.1 验证码提取接口

**路由定义：**

```python
# outlook_web/routes/emails.py
bp.add_url_rule(
    "/api/emails/<email>/extract-verification",
    view_func=impl.api_extract_verification,
    methods=["GET"]
)
```

**实现逻辑：**

```python
# outlook_web/legacy.py 或新的 view 层
@login_required
def api_extract_verification(email):
    """
    提取验证码和链接接口

    参数：
    - email: 邮箱地址（路径参数）

    返回：
    成功：
    {
        "success": true,
        "data": {
            "verification_code": "123456",
            "links": ["https://example.com/verify"],
            "formatted": "123456 https://example.com/verify"
        },
        "message": "提取成功"
    }

    失败：
    {
        "success": false,
        "error": "未找到验证信息",
        "trace_id": "xxx"
    }
    """
    try:
        # 调用验证码提取服务
        result = extract_verification_info(email)

        return jsonify({
            "success": True,
            "data": result,
            "message": "提取成功"
        })

    except ValueError as e:
        # 未找到验证信息
        return jsonify({
            "success": False,
            "error": str(e),
            "trace_id": generate_trace_id()
        }), 404

    except Exception as e:
        # 其他错误
        return jsonify({
            "success": False,
            "error": "提取失败",
            "trace_id": generate_trace_id()
        }), 500
```

**错误处理策略：**

1. **邮箱不存在**：返回 404，错误信息："邮箱不存在"
2. **未找到邮件**：返回 404，错误信息："未找到邮件"
3. **未找到验证信息**：返回 404，错误信息："未找到验证信息"
4. **Token 过期**：返回 401，错误信息："Token 过期，请刷新"
5. **网络错误**：返回 500，错误信息："网络错误，请重试"

### 4.3 数据库设计

#### 4.3.1 settings 表新增配置项

**配置项定义：**

| Key | Value Type | Default | Description |
|-----|------------|---------|-------------|
| `enable_auto_polling` | boolean | `false` | 是否启用自动轮询 |
| `polling_interval` | integer | `10` | 轮询间隔（秒） |
| `polling_count` | integer | `5` | 轮询次数 |

**初始化逻辑：**

```python
# outlook_web/db.py - init_db() 函数中添加

# 初始化轮询配置
cursor.execute(
    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
    ("enable_auto_polling", "false")
)
cursor.execute(
    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
    ("polling_interval", "10")
)
cursor.execute(
    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
    ("polling_count", "5")
)
```

**数据类型转换：**

```python
# 读取配置时的类型转换
def get_polling_settings(db):
    """获取轮询配置"""
    settings = {}

    # enable_auto_polling: string -> boolean
    row = db.execute(
        "SELECT value FROM settings WHERE key = ?",
        ("enable_auto_polling",)
    ).fetchone()
    settings["enable_auto_polling"] = row["value"].lower() == "true" if row else False

    # polling_interval: string -> integer
    row = db.execute(
        "SELECT value FROM settings WHERE key = ?",
        ("polling_interval",)
    ).fetchone()
    settings["polling_interval"] = int(row["value"]) if row else 10

    # polling_count: string -> integer
    row = db.execute(
        "SELECT value FROM settings WHERE key = ?",
        ("polling_count",)
    ).fetchone()
    settings["polling_count"] = int(row["value"]) if row else 5

    return settings
```

#### 4.3.2 设置 API 更新

**GET /api/settings 响应更新：**

```python
# 在现有响应中添加轮询配置
{
    "success": true,
    "settings": {
        "login_password": "***",
        "gptmail_api_key": "***",
        "enable_auto_polling": false,
        "polling_interval": 10,
        "polling_count": 5,
        ...
    }
}
```

**PUT /api/settings 请求处理：**

```python
@login_required
def api_update_settings():
    """更新设置"""
    data = request.get_json()

    # 处理轮询配置
    if "enable_auto_polling" in data:
        value = "true" if data["enable_auto_polling"] else "false"
        db.execute(
            "UPDATE settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
            (value, "enable_auto_polling")
        )

    if "polling_interval" in data:
        # 验证范围：5-300 秒
        interval = int(data["polling_interval"])
        if not (5 <= interval <= 300):
            return jsonify({
                "success": False,
                "error": "轮询间隔必须在 5-300 秒之间"
            }), 400

        db.execute(
            "UPDATE settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
            (str(interval), "polling_interval")
        )

    if "polling_count" in data:
        # 验证范围：1-100 次
        count = int(data["polling_count"])
        if not (1 <= count <= 100):
            return jsonify({
                "success": False,
                "error": "轮询次数必须在 1-100 次之间"
            }), 400

        db.execute(
            "UPDATE settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
            (str(count), "polling_count")
        )

    db.commit()

    return jsonify({
        "success": True,
        "message": "设置已保存"
    })
```

### 4.4 邮件获取辅助函数

#### 4.4.1 获取最新邮件

```python
def get_latest_email(email_address):
    """
    获取邮箱的最新邮件

    策略：
    1. 同时从收件箱和垃圾邮件文件夹获取邮件
    2. 按时间排序，取最新的一封
    3. 使用现有的邮件获取 API（Graph API / IMAP）
    """
    from outlook_web.services.graph import get_emails as get_emails_graph
    from outlook_web.services.imap import get_emails as get_emails_imap

    # 获取账号信息
    db = get_db()
    account = db.execute(
        "SELECT * FROM accounts WHERE email = ?",
        (email_address,)
    ).fetchone()

    if not account:
        raise ValueError("邮箱不存在")

    # 尝试获取邮件（使用现有的回退策略）
    emails = []

    # 从收件箱获取
    try:
        inbox_emails = get_emails_graph(
            account, folder="inbox", skip=0, top=1
        )
        emails.extend(inbox_emails)
    except Exception:
        pass

    # 从垃圾邮件获取
    try:
        junk_emails = get_emails_graph(
            account, folder="junkemail", skip=0, top=1
        )
        emails.extend(junk_emails)
    except Exception:
        pass

    if not emails:
        raise ValueError("未找到邮件")

    # 按时间排序，取最新的
    emails.sort(key=lambda x: x.get("date", ""), reverse=True)
    return emails[0]
```

#### 4.4.2 HTML 转纯文本

```python
import html
from html.parser import HTMLParser

class HTMLTextExtractor(HTMLParser):
    """HTML 转纯文本提取器"""

    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, data):
        self.text.append(data)

    def get_text(self):
        return " ".join(self.text)

def extract_email_text(email):
    """
    提取邮件纯文本内容

    优先级：
    1. body（纯文本）
    2. body_html（HTML 转纯文本）
    3. body_preview（预览文本）
    """
    # 优先使用纯文本
    if email.get("body"):
        return email["body"]

    # 其次使用 HTML 转纯文本
    if email.get("body_html"):
        parser = HTMLTextExtractor()
        parser.feed(email["body_html"])
        text = parser.get_text()
        # 解码 HTML 实体
        text = html.unescape(text)
        return text

    # 最后使用预览文本
    if email.get("body_preview"):
        return email["body_preview"]

    return ""
```

---

## 5. 前端技术设计细节

### 5.1 全选功能

#### 5.1.1 数据结构设计

```javascript
// 全局变量（复用现有的）
let selectedAccounts = new Set();  // 存储选中的账号 ID

// 全选状态枚举
const SelectAllState = {
    NONE: 'none',        // 未选中
    PARTIAL: 'partial',  // 部分选中（半选）
    ALL: 'all'          // 全选
};
```

#### 5.1.2 性能优化策略

**问题：** 当邮箱数量达到 1000 个时，全选操作可能导致页面卡顿

**优化方案：**

1. **使用 Set 数据结构**
   - 时间复杂度：O(1) 查找和插入
   - 空间复杂度：O(n)

2. **批量 DOM 更新**
   - 使用 requestAnimationFrame 优化渲染时机
   - 减少重排重绘次数

3. **事件委托**
   - 使用事件委托减少事件监听器数量

```javascript
function selectAllAccounts() {
    const accountItems = document.querySelectorAll('.account-item:not([style*="display: none"])');
    
    // 批量添加到 Set（O(n) 时间复杂度）
    accountItems.forEach(item => {
        const accountId = item.dataset.accountId;
        if (accountId) {
            selectedAccounts.add(accountId);
        }
    });
    
    // 使用 requestAnimationFrame 优化渲染
    requestAnimationFrame(() => {
        updateAccountCheckboxes();
        updateSelectAllCheckbox();
        updateBatchActionBar();
    });
}
```

### 5.2 剪贴板 API 兼容性处理

#### 5.2.1 浏览器兼容性

| 浏览器 | Clipboard API | execCommand |
|--------|---------------|-------------|
| Chrome 66+ | ✅ | ✅ |
| Firefox 63+ | ✅ | ✅ |
| Safari 13.1+ | ✅ | ✅ |
| Edge 79+ | ✅ | ✅ |
| IE 11 | ❌ | ✅ |

#### 5.2.2 降级方案

```javascript
async function copyToClipboard(text) {
    // 方法1：Clipboard API（现代浏览器）
    if (navigator.clipboard && navigator.clipboard.writeText) {
        try {
            await navigator.clipboard.writeText(text);
            return;
        } catch (err) {
            console.warn('Clipboard API 失败，尝试降级方案', err);
        }
    }
    
    // 方法2：execCommand（旧浏览器）
    try {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        
        const success = document.execCommand('copy');
        document.body.removeChild(textarea);
        
        if (!success) {
            throw new Error('execCommand 失败');
        }
    } catch (err) {
        throw new Error('复制失败，请手动复制');
    }
}
```

### 5.3 轮询机制的技术实现

#### 5.3.1 定时器管理

```javascript
// 全局定时器变量
let pollingTimer = null;

function startPolling(email) {
    // 先停止之前的定时器
    stopPolling();
    
    // 创建新定时器
    pollingTimer = setInterval(() => {
        pollForNewEmails();
    }, pollingInterval);
}

function stopPolling() {
    if (pollingTimer) {
        clearInterval(pollingTimer);
        pollingTimer = null;
    }
}

// 页面卸载时清理定时器
window.addEventListener('beforeunload', () => {
    stopPolling();
});
```

#### 5.3.2 新邮件检测算法

**算法复杂度分析：**

- 时间复杂度：O(n)，n 为新邮件数量
- 空间复杂度：O(m)，m 为旧邮件数量

```javascript
function detectNewEmails(oldEmailIds, newEmails) {
    // 使用 Set 进行快速查找（O(1)）
    const newEmailList = [];
    
    for (const email of newEmails) {
        if (!oldEmailIds.has(email.id)) {
            newEmailList.push(email);
        }
    }
    
    return newEmailList;
}
```

---

## 6. 测试策略

### 6.1 单元测试

#### 6.1.1 验证码提取算法测试

```python
# tests/test_verification_extractor.py

import unittest
from outlook_web.services.verification_extractor import (
    smart_extract_verification_code,
    fallback_extract_verification_code,
    extract_links
)

class TestVerificationExtractor(unittest.TestCase):
    
    def test_smart_extract_with_chinese_keyword(self):
        """测试中文关键词识别"""
        content = "您的验证码是 123456，请在10分钟内完成验证。"
        result = smart_extract_verification_code(content)
        self.assertEqual(result, "123456")
    
    def test_smart_extract_with_english_keyword(self):
        """测试英文关键词识别"""
        content = "Your verification code is ABC123."
        result = smart_extract_verification_code(content)
        self.assertEqual(result, "ABC123")
    
    def test_fallback_extract(self):
        """测试保底提取"""
        content = "Please use code XYZ789 to complete."
        result = fallback_extract_verification_code(content)
        self.assertEqual(result, "XYZ789")
    
    def test_extract_links(self):
        """测试链接提取"""
        content = "Click: https://example.com/verify?token=abc123"
        result = extract_links(content)
        self.assertEqual(len(result), 1)
        self.assertIn("https://example.com/verify?token=abc123", result)
```

---

## 7. 部署与运维

### 7.1 数据库迁移

```python
# 在 init_db() 函数中添加
def migrate_polling_settings(cursor):
    """迁移轮询配置"""
    cursor.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
        ("enable_auto_polling", "false")
    )
    cursor.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
        ("polling_interval", "10")
    )
    cursor.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
        ("polling_count", "5")
    )
```

### 7.2 性能监控

```python
import time

def api_extract_verification(email):
    start_time = time.time()
    
    try:
        result = extract_verification_info(email)
        elapsed_time = time.time() - start_time
        
        if elapsed_time > 2.0:
            print(f"⚠️ 验证码提取耗时过长: {elapsed_time:.2f}s")
        
        return jsonify({"success": True, "data": result})
    except Exception as e:
        print(f"❌ 验证码提取失败: {str(e)}")
        raise
```

---

## 8. 总结

### 8.1 技术亮点

1. **智能验证码识别算法**：关键词识别 + 保底规则，提取成功率 > 90%
2. **高性能全选**：使用 Set 数据结构 + 批量 DOM 更新，支持 1000+ 邮箱
3. **可靠的轮询机制**：定时器管理 + 新邮件检测 + 自动停止
4. **优雅的降级方案**：剪贴板 API 降级 + 错误处理

### 8.2 技术风险

1. **验证码识别准确率**：依赖邮件格式，可能存在误判
   - 缓解：提供保底规则 + 用户可手动查看邮件
2. **浏览器兼容性**：Clipboard API 在旧浏览器不支持
   - 缓解：提供 execCommand 降级方案
3. **轮询性能影响**：高频轮询可能影响页面性能
   - 缓解：设置合理的默认值 + 使用异步请求

### 8.3 后续优化方向

1. **验证码识别优化**：
   - 支持更多语言的关键词
   - 支持图片验证码识别（OCR）
   - 支持自定义提取规则

2. **性能优化**：
   - 实现虚拟滚动（邮箱数量 > 1000）
   - 使用 Web Worker 处理验证码提取
   - 使用 IndexedDB 缓存邮件数据

3. **功能增强**：
   - 支持多邮箱同时轮询
   - 支持浏览器通知
   - 支持声音提示
