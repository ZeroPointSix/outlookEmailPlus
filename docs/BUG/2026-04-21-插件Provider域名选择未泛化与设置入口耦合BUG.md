# 插件 Provider 域名选择未泛化，且设置入口仍与插件管理耦合 (BUG)

**创建日期**: 2026-04-21  
**关联功能**: 临时邮箱插件化 / Temp Emails / 设置页 Provider 配置 / 插件管理  
**分析人员**: AI 代码分析助手  
**状态**: 🟢 主干已落地，人工验收已通过

## 概述

在继续接入真实第三方临时邮箱插件（如 `cloudflare_temp_mail_test_plugin`）后，系统已经能完成：

1. 插件加载
2. 插件出现在设置页 Provider 单选组
3. 插件出现在临时邮箱页面 Provider 下拉
4. 插件配置 Schema 读取、保存、测试连接

但真实交互仍存在两个体验层问题：

1. **第三方插件即使返回 `domains`，临时邮箱页面也不能手动选域名**
2. **插件运行时配置仍嵌在“插件管理”卡片中，没有落到对应 Provider 的设置入口**

这说明当前插件化主链虽然已闭环，但前端交互仍停留在“后端能力已经通了，前端体验还没完全泛化”的阶段。

## 当前状态（截至本会话）

本 BUG 对应的前端主干已在本会话完成第一轮修复：

1. 设置页已新增独立 `#pluginProviderConfigPanel`，插件 Provider 选中后不再只有空白。
2. 插件配置表单已迁出插件管理卡片，改为渲染到独立 Provider 设置面板；插件卡片中的入口已改为“打开设置”。
3. 临时邮箱页已去掉 `cloudflare_temp_mail` 的域名硬编码，改为按 `/api/temp-emails/options` 返回的 `domains` / `domain_strategy` 判定域名下拉。
4. `temp_emails.js` 额外加入了按 Provider 维度的 options cache 与请求防串号保护，避免切换 Provider 后复用错误的旧 options。
5. 设置页首次加载时，若保存的是插件 Provider，当前实现也会在插件 radio 延后注入后优先恢复该 Provider，而不是错误回退到 `legacy_bridge`。
6. 为消除旧静态资源缓存干扰，当前人工验收实例已按 `2.1.1` 版本重新拉起到 `127.0.0.1:5097`；在将 `dev` fast-forward 合入 `main`、保留 `main` 工作树原有 `WORKSPACE.md` 本地记录到 stash、并在主干工作树重新执行完整回归后，最新完整全量结果已更新为 `Ran 1357 tests in 463.280s`、`OK (skipped=7)`。

当前剩余事项已不再包括页面级人工验收；本轮问题对应的前端主干、最新回归结果与人工验收结论都已经落地。

---

## 影响范围

- **用户侧 UI**：
  - 插件 Provider 可以选，但不一定能像内置 CF 一样选域名
  - 设置页里“插件管理”和“插件配置”混在一起，职责不清晰
- **功能侧**：
  - 第三方插件的 `get_options().domains` 无法自然转化为“页面可选域名”
  - 插件一多后，安装界面会不断堆积业务配置项
- **可维护性**：
  - `plugins.js`、`main.js`、`temp_emails.js` 各自掌握一部分 Provider 逻辑，职责边界模糊

---

## 复现步骤（修复前）

1. 在运行时插件目录放入一个已实现 `get_options().domains` 的第三方插件。
2. 重启或执行 `POST /api/system/reload-plugins`，确认插件成功加载。
3. 进入「设置 → 临时邮箱」：
   - 在 Provider 单选组中能看到该插件
   - 在「插件管理」卡片中能看到该插件
4. 打开「⚡ 临时邮箱」页面：
   - 在 `#tempEmailProviderSelect` 里选择该插件
5. 观察 `#tempEmailDomainSelect`：
   - **实际**：通常仍为禁用状态，或只显示“自动分配域名”
   - **预期**：若插件 `get_options()` 返回了可用域名，应允许用户手动选择
6. 回到设置页继续观察配置入口：
   - **实际**：插件配置仍在“插件管理”卡片内部点击“配置”后展开
   - **预期**：插件管理只负责安装 / 卸载 / 应用变更；插件配置应进入对应 Provider 设置区

---

## 预期行为 vs 实际行为（修复前）

### 预期

1. 临时邮箱页面对所有 Provider 统一按 `get_options()` 决定是否显示 / 启用域名下拉
2. 设置页中“插件管理”仅承担生命周期操作：
   - 安装
   - 卸载
   - 应用变更
   - 故障展示
3. 插件自己的 base_url / token / domains / timeout 等配置，应出现在对应 Provider 设置区

### 实际

1. 临时邮箱页面是否允许选域名，仍写死在 `cloudflare_temp_mail`
2. 插件配置表单仍内嵌在插件管理卡片里
3. 设置页的 Provider 单选组只会在内置 GPTMail / CF 两张配置卡片之间切换；插件选中后只是把两个内置面板都隐藏

---

## 关键代码定位（修复前）

### 1) 临时邮箱页域名选择逻辑

文件：`static/js/features/temp_emails.js`

- `loadTempEmails()`
  - 当前逻辑：
    - `domainSelect.disabled = providerSelect.value !== 'cloudflare_temp_mail'`
    - 只有选中 `cloudflare_temp_mail` 时才调用 `loadTempEmailOptions(...)`
- `onTempEmailProviderChange(selectedProvider)`
  - 当前逻辑：
    - `selectedProvider === 'cloudflare_temp_mail'` → 启用域名下拉并加载 options
    - 其余 provider → 禁用域名下拉并回退“自动分配域名”

### 2) 插件 Provider 注入逻辑

文件：`static/js/features/plugins.js`

- `_refreshProviderSelect()`
  - 已把已安装插件注入 `#tempEmailProviderSelect`
- `_refreshProviderRadios()`
  - 已把已安装插件注入设置页 `.provider-radio-group`
- `toggleConfig()` / `_renderConfigForm()`
  - 当前仍把插件配置表单渲染在插件管理卡片内部

### 3) 设置页 Provider 面板切换逻辑

文件：`static/js/main.js`

- `onTempMailProviderChange(provider)`
  - 当前只支持：
    - `legacy_bridge` → 显示 `#gptmailConfigPanel`
    - `cloudflare_temp_mail` → 显示 `#cfWorkerConfigPanel`
    - 其余 provider → 两张内置卡片都隐藏

### 4) 设置页结构

文件：`templates/index.html`

- 已有：
  - Provider 单选组
  - `#gptmailConfigPanel`
  - `#cfWorkerConfigPanel`
  - `#pluginManagerCard`
- 当前没有一个独立的“插件 Provider 配置承载区”

---

## 根因总结（Root Cause）

该问题不是单点故障，而是三个前端层职责没有一起收敛：

### 根因 1：Provider 注入成功，但域名选择能力仍按 provider 名称硬编码

- `plugins.js` 已负责“把插件放进下拉”
- `temp_emails.js` 却仍按 `cloudflare_temp_mail` 判断“能不能选域名”

于是形成了：

- **插件能选**
- **插件也能返回 `domains`**
- **但页面仍不知道应该给它开放域名选择 UI**

### 根因 2：设置页 Provider 单选组与插件配置承载区没有打通

- `main.js.onTempMailProviderChange()` 仍只认识内置 GPTMail / CF Worker
- 插件 radio 虽然被注入进去了，但选中后只会把两张内置面板隐藏掉

于是设置页没有真正的“插件 Provider 设置位”。

### 根因 3：插件管理卡片兼任了生命周期管理与运行时配置

- 当前插件管理卡片既负责：
  - 安装 / 卸载 / 应用变更
- 又负责：
  - 读取 config schema
  - 渲染配置表单
  - 保存配置
  - 测试连接

这会让安装界面承载越来越多业务设置，和用户对“插件管理”的直觉不一致。

---

## 方案对比

### 方案 A（保守）

**内容**：

1. 只改 `temp_emails.js`
2. 让第三方插件也能根据 `get_options().domains` 启用域名下拉
3. 保留插件配置仍在“插件管理”卡片里的现状

**优点**：

- 改动面较小
- 可以快速修复“插件不能手动选域名”的表层现象

**❌ 反驳**：

1. 只修了“域名选择”，没有解决“插件管理 vs 运行时设置”的职责混乱
2. 设置页 Provider 单选组仍没有真正的插件设置承载区
3. 后续插件一多，配置表单会继续堆在插件管理卡片里，体验会越来越差

### 方案 B（推荐）

**内容**：

1. 把临时邮箱页的域名选择逻辑改为 **Provider-agnostic**
   - 根据 `/api/temp-emails/options` 返回的 `domains` / `domain_strategy` 判定
2. 把设置页中的插件运行时配置迁到 **对应 Provider 设置区 / 统一 Provider 设置面板**
3. 把「插件管理」卡片收敛成纯生命周期入口
   - 安装
   - 卸载
   - 应用变更
   - 故障展示

**优势**：

- 与当前产品判断一致
- 插件体验与内置 Provider 的设置语义更统一
- 后续接新插件时，不再需要把配置继续塞回安装界面

**Trade-off**：

- 前端改造面会比方案 A 大
- 需要同时协调 `plugins.js`、`main.js`、`temp_emails.js`、`index.html`

### ✅ 最终推荐：方案 B

因为这个问题本质上已经不是单纯的“某个插件少了个域名下拉”，而是**插件 Provider 的前端承载模型还没完全收口**。继续在旧结构上打补丁，只会让后续接更多插件时越来越难维护。

---

## 建议修复边界

本 BUG 推荐的实施边界如下：

1. **复用现有插件配置 API**
   - `GET /api/plugins/{name}/config/schema`
   - `GET /api/plugins/{name}/config`
   - `POST /api/plugins/{name}/config`
   - `POST /api/plugins/{name}/test-connection`
2. **不新增新的插件配置后端协议**，优先改前端承载位置
3. **不改产品路径**
   - `/api/temp-emails/*`
   - `/api/external/temp-emails/*`
4. **优先把体验统一到当前设置页 Provider 单选模型里**
5. **`/api/settings` 只继续负责全局 Provider 选择与内置配置**
   - `main.js.saveSettings()` 当前只序列化：
     - `temp_mail_provider`
     - `temp_mail_*`
     - `cf_worker_*`
   - 因此插件自己的运行时配置不应硬塞进 `/api/settings`，而应继续走 `/api/plugins/{name}/config`

---

## 验收标准（修复后）

1. 选择任意已安装插件 Provider，若其 `get_options()` 返回可用域名，则临时邮箱页允许手动选择域名。
2. 选择不支持手动域名的 Provider 时，域名下拉正确禁用，并显示该 Provider 对应的提示文案。
3. 设置页中选中插件 Provider 时，能看到独立的插件配置区域，而不是只能去插件管理卡片里展开配置。
4. 插件管理卡片不再承载复杂业务配置，只保留生命周期操作和状态展示。
5. 内置 GPTMail / CF Worker 的既有配置区保持不变。
6. 插件加载失败时，`load_failed` 卡片展示不受本次改造影响。

---

## 关联 TODO

- `docs/TODO/2026-04-21-插件Provider域名选择泛化与设置入口解耦TODO.md`
- `docs/DEV/2026-04-21-插件Provider域名选择泛化与设置入口解耦-实施提示词.md`
- `docs/TODO/2026-04-21-临时邮箱插件化TODO.md`（T4.5）
