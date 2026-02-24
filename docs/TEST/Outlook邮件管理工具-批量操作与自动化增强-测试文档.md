# Outlook 邮件管理工具｜批量操作与自动化增强 测试文档

- 文档状态：草案
- 版本：V1.0
- 日期：2026-02-24
- 对齐 PRD：`docs/PRD/Outlook邮件管理工具-批量操作与自动化增强PRD.md`
- 对齐 FD：`docs/FD/Outlook邮件管理工具-批量操作与自动化增强FD.md`
- 对齐 TDD：`docs/TDD/Outlook邮件管理工具-批量操作与自动化增强TDD.md`
- 对齐 TODO：`docs/TODO/Outlook邮件管理工具-批量操作与自动化增强TODO.md`

---

## 1. 测试概述

### 1.1 测试目标

本测试文档旨在验证批量操作与自动化增强功能的正确性、性能和可靠性，确保：

1. **验证码提取功能**：
   - 智能识别算法准确率 > 90%
   - 保底提取算法覆盖常见格式
   - 链接提取完整准确
   - API 响应时间 < 2 秒

2. **全选功能**：
   - 全选/半选/未选状态正确
   - 与批量操作无缝集成
   - 性能满足要求（1000 个邮箱 < 100ms）

3. **自动轮询与通知功能**：
   - 轮询机制稳定可靠
   - 新邮件检测准确
   - 通知显示正常
   - 配置管理正确

### 1.2 测试范围

**包含：**
- 后端验证码提取服务单元测试
- 后端 API 接口集成测试
- 前端全选功能测试
- 前端复制功能测试
- 前端轮询功能测试
- 前端通知功能测试
- 性能测试
- 边界情况测试
- 回归测试

**不包含：**
- 现有功能的完整回归测试（仅抽样验证）
- 安全渗透测试
- 压力测试（超过 1000 个邮箱）

### 1.3 测试环境

**后端环境：**
- Python 3.8+
- Flask 3.0+
- SQLite 3
- 测试框架：unittest

**前端环境：**
- Chrome 最新版
- Firefox 最新版
- Safari 最新版（可选）
- Edge 最新版（可选）

**测试数据：**
- 测试邮箱账号：10 个
- 测试邮件样本：20 封（覆盖不同验证码格式）
- 测试分组：3 个

---

## 2. 测试数据准备

### 2.1 测试邮件样本

#### 样本 1：中文验证码（纯数字）
```
主题：【测试网站】验证码通知
内容：
尊敬的用户：
您的验证码是 123456，请在10分钟内完成验证。
如非本人操作，请忽略此邮件。
```

#### 样本 2：英文验证码（纯数字）
```
主题：Verification Code
内容：
Dear User,
Your verification code is 654321. Please verify within 10 minutes.
If this was not you, please ignore this email.
```

#### 样本 3：验证码（数字+字母）
```
主题：Account Verification
内容：
Hello,
Your OTP is ABC123. This code will expire in 5 minutes.
Thank you.
```

#### 样本 4：验证码（大小写混合）
```
主题：Security Code
内容：
Your security code: XyZ789
Please enter this code to continue.
```

#### 样本 5：包含链接的验证邮件
```
主题：Verify Your Email
内容：
Please click the link below to verify your email:
https://example.com/verify?token=abc123def456
This link will expire in 24 hours.
```

#### 样本 6：同时包含验证码和链n```
主题：Complete Your Registration
内容：
Your verification code is 999888.
Or click here to verify: https://example.com/activate?code=999888
```

#### 样本 7：多个链接
```
主题：Welcome to Our Service
内容：
Activate your account: https://example.com/activate
Visit our website: https://example.com
Read our terms: https://example.com/terms
```

#### 样本 8：无验证码的普通邮件
```
主题：Newsletter
内容：
Welcome to our newsletter!
This is a regular email without any verification code.
Thank you for subscribing.
```

#### 样本 9：包含日期和时间（干扰项）
```
主题：Meeting Reminder
内容：
Meeting scheduled for 2024-01-15 at 14:30.
Please confirm your attendance.
```

#### 样本 10：空邮件
```
主题：Test Empty Email
内容：
（空内容）
```

#### 样本 11：HTML 格式邮件
```html
主题：Verification Required
内容：
<html>
<body>
<p>Your verification code is <strong>777666</strong></p>
<p>Click <a href="https://example.com/verify">here</a> to verify.</p>
</body>
</html>
```

#### 样本 12：验证码在关键词前面
```
主题：Code Notification
内容：
888999 is your verification code.
Please use it to complete the process.
```

#### 样本 13：多个验证码（取第一个）
```
主题：Multiple Codes
内容：
Your code is 111222.
Previous code 333444 has expired.
```

#### 样本 14：验证码包含空格
```
主题：Verification
内容：
Your code: 555 666
Please enter without spaces.
```

#### 样本 15：验证码包含连字符
```
主题：Access Code
内容：
Your access code is 777-888.
Valid for 15 minutes.
```

### 2.2 测试账号数据

```python
# 测试账号列表
TEST_ACCOUNTS = [
    {
        "id": 1,
        "email": "test1@example.com",
        "group_id": 1,
        "remark": "测试账号1"
    },
    {
        "id": 2,
        "email": "test2@example.com",
        "group_id": 1,
        "remark": "测试账号2"
    },
    # ... 共 10 个测试账号
]
```

### 2.3 测试分组数据

```python
# 测试分组列表
TEST_GROUPS = [
    {"id": 1, "name": "测试分组1", "color": "#409eff"},
    {"id": 2, "name": "测试分组2", "color": "#67c23a"},
    {"id": 3, "name": "测试分组3", "color": "#e6a23c"}
]
```

---

## 3. 单元测试用例（后端）

### 3.1 验证码提取算法测试

#### 测试用例 UT-001：智能识别 - 中文关键词 + 纯数字验证码

**测试目的：** 验证智能识别算法能正确识别中文关键词附近的纯数字验证码

**前置条件：** 验证码提取服务已实现

**测试步骤：**
1. 准备测试邮件内容（样本 1）
2. 调用 `smart_extract_verification_code(content)`
3. 验证返回结果

**预期结果：** 返回 `"123456"`

**测试代码：**
```python
def test_smart_extract_chinese_keyword_pure_number(self):
    content = "您的验证码是 123456，请在10分钟内完成验证。"
    result = smart_extract_verification_code(content)
    self.assertEqual(result, "123456")
```

**测试状态：** ⬜ 待执行

---

#### 测试用例 UT-002：智能识别 - 英文关键词 + 纯数字验证码

**测试目的：** 验证智能识别算法能正确识别英文关键词附近的纯数字验证码

**前置条件：** 验证码提取服务已实现

**测试步骤：**
1. 准备测试邮件内容（样本 2）
2. 调用 `smart_extract_verification_code(content)`
3. 验证返回结果

**预期结果：** 返回 `"654321"`

**测试代码：**
```python
def test_smart_extract_english_keyword_pure_number(self):
    content = "Your verification code is 654321. Please verify within 10 minutes."
    result = smart_extract_verification_code(content)
    self.assertEqual(result, "654321")
```

**测试状态：** ⬜ 待执行

---

#### 测试用例 UT-003：智能识别 - OTP 关键词 + 数字字母混合

**测试目的：** 验证智能识别算法能正确识别 OTP 关键词附近的数字字母混合验证码

**前置条件：** 验证码提取服务已实现

**测试步骤：**
1. 准备测试邮件内容（样本 3）
2. 调用 `smart_extract_verification_code(content)`
3. 验证返回结果

**预期结果：** 返回 `"ABC123"`

**测试代码：**
```python
def test_smart_extract_otp_keyword_alphanumeric(self):
    content = "Your OTP is ABC123. This code will expire in 5 minutes."
    result = smart_extract_verification_code(content)
    self.assertEqual(result, "ABC123")
```

**测试状态：** ⬜ 待执行

---

#### 测试用例 UT-004：智能识别 - 验证码在关键词前面

**测试目的：** 验证智能识别算法能识别验证码在关键词前面的情况

**前置条件：** 验证码提取服务已实现

**测试步骤：**
1. 准备测试邮件内容（样本 12）
2. 调用 `smart_extract_verification_code(content)`
3. 验证返回结果

**预期结果：** 返回 `"888999"`

**测试代码：**
```python
def test_smart_extract_code_before_keyword(self):
    content = "888999 is your verification code."
    result = smart_extract_verification_code(content)
    self.assertEqual(result, "888999")
```

**测试状态：** ⬜ 待执行

---

#### 测试用例 UT-005：保底提取 - 无关键词的验证码

**测试目的：** 验证保底提取算法能在没有关键词的情况下提取验证码

**前置条件：** 验证码提取服务已实现

**测试步骤：**
1. 准备测试邮件内容（无关键词但包含验证码）
2. 调用 `fallback_extract_verification_code(content)`
3. 验证返回结果

**预期结果：** 返回验证码

**测试代码：**
```python
def test_fallback_extract_without_keyword(self):
    content = "Please use code XYZ789 to complete your registration."
    result = fallback_extract_verification_code(content)
    self.assertEqual(result, "XYZ789")
```

**测试状态：** ⬜ 待执行

---

#### 测试用例 UT-006：保底提取 - 过滤日期格式

**测试目的：** 验证保底提取算法能正确过滤日期格式（避免误判）

**前置条件：** 验证码提取服务已实现

**测试步骤：**
1. 准备包含日期的测试邮件内容（样本 9）
2. 调用 `fallback_extract_verification_code(content)`
3. 验证返回结果

**预期结果：** 不返回日期（2024），返回 None 或其他验证码

**测试代码：**
```python
def test_fallback_extract_filter_date(self):
    content = "Meeting scheduled for 2024-01-15 at 14:30."
    result = fallback_extract_verification_code(content)
    # 2024 应该被过滤掉
    self.assertNotEqual(result, "2024")
```

**测试状态：** ⬜ 待执行

---

#### 测试用例 UT-007：保底提取 - 过滤时间格式

**测试目的：** 验证保底提取算法能正确过滤时间格式（避免误判）

**前置条件：** 验证码提取服务已实现

**测试步骤：**
1. 准备包含时间的测试邮件内容
2. 调用 `fallback_extract_verification_code(content)`
3. 验证返回结果

**预期结果：** 不返回时间（1430），返回 None 或其他验证码

**测试代码：**
```python
def test_fallback_extract_filter_time(self):
    content = "Meeting at 1430 hours."
    result = fallback_extract_verification_code(content)
    # 1430 应该被过滤掉（14:30）
    self.assertNotEqual(result, "1430")
```

**测试状态：** ⬜ 待执行

---

#### 测试用例 UT-008：链接提取 - 单个链接

**测试目的：** 验证链接提取算法能正确提取单个 HTTP/HTTPS 链接

**前置条件：** 验证码提取服务已实现

**测试步骤：**
1. 准备包含单个链接的测试邮件内容（样本 5）
2. 调用 `extract_links(content)`
3. 验证返回结果

**预期结果：** 返回 `["https://example.com/verify?token=abc123def456"]`

**测试代码：**
```python
def test_extract_single_link(self):
    content = "Please click: https://example.com/verify?token=abc123def456"
    result = extract_links(content)
    self.assertEqual(len(result), 1)
    self.assertEqual(result[0], "https://example.com/verify?token=abc123def456")
```

**测试状态：** ⬜ 待执行

---

#### 测试用例 UT-009：链接提取 - 多个链接

**测试目的：** 验证链接提取算法能正确提取多个链接并去重

**前置条件：** 验证码提取服务已实现

**测试步骤：**
1. 准备包含多个链接的测试邮件内容（样本 7）
2. 调用 `extract_links(content)`
3. 验证返回结果

**预期结果：** 返回 3 个不同的链接

**测试代码：**
```python
def test_extract_multiple_links(self):
    content = """
    Activate: https://example.com/activate
    Visit: https://example.com
    Terms: https://example.com/terms
    """
    result = extract_links(content)
    self.assertEqual(len(result), 3)
    self.assertIn("https://example.com/activate", result)
    self.assertIn("https://example.com", result)
    self.assertIn("https://example.com/terms", result)
```

**测试状态：** ⬜ 待执行

---

#### 测试用例 UT-010：链接提取 - 链接去重

**测试目的：** 验证链接提取算法能正确去重重复的链接

**前置条件：** 验证码提取服务已实现

**测试步骤：**
1. 准备包含重复链接的测试邮件内容
2. 调用 `extract_links(content)`
3. 验证返回结果

**预期结果：** 返回去重后的链接列表

**测试代码：**
```python
def test_extract_links_deduplication(self):
    content = """
    Link1: https://example.com/verify
    Link2: https://example.com/verify
    Link3: https://example.com/help
    """
    result = extract_links(content)
    self.assertEqual(len(result), 2)  # 去重后只有 2 个
```

**测试状态：** ⬜ 待执行

---

