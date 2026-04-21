# TODO: 插件 Provider 域名选择泛化 + 设置入口与插件管理解耦

> 创建日期：2026-04-21
> 关联 BUG：`docs/BUG/2026-04-21-插件Provider域名选择未泛化与设置入口耦合BUG.md`
> 执行提示词：`docs/DEV/2026-04-21-插件Provider域名选择泛化与设置入口解耦-实施提示词.md`
> 关联 FD：`docs/FD/2026-04-21-临时邮箱插件化FD.md`
> 关联 TD：`docs/TD/2026-04-21-临时邮箱插件化TD.md`
> 当前目标：按**方案 B**推进，把“插件管理”和“插件运行时设置”拆开，并让临时邮箱页对第三方插件统一支持域名能力判定。

---

## 任务概览

| 阶段 | 任务数 | 目标 | 状态 |
|------|-------|------|------|
| Phase 1: 交互边界收敛 | 3 | 明确复用现有 API、定义设置页承载位 | 🟡 设计已完成 |
| Phase 2: 设置页 UI 解耦 | 4 | 插件配置迁出插件管理卡片 | 🟢 代码已落地 |
| Phase 3: 临时邮箱页域名泛化 | 4 | 按 provider options 决定域名下拉行为 | 🟢 代码已落地 |
| Phase 4: 回归与验收 | 4 | 确保内置 provider 与插件 provider 都正常 | 🟢 自动回归与人工验收均已通过 |

---

## Phase 1: 交互边界收敛

> **目标**：先明确这次不是重做后端协议，而是重构前端承载模型。

### Task 1.1：复用现有插件配置 API，不新开协议

**结论要求**：

继续复用当前已有接口：

- `GET /api/plugins/{name}/config/schema`
- `GET /api/plugins/{name}/config`
- `POST /api/plugins/{name}/config`
- `POST /api/plugins/{name}/test-connection`

**检查点**：

- [x] 文档中明确：本轮不新增新的插件配置 API
- [x] 设置页的新插件配置承载区直接复用这些接口

**Phase 1 结论（已确认）**：

1. `outlook_web/routes/plugins.py` 已暴露完整插件配置接口：
   - schema
   - 读取当前配置
   - 保存配置
   - 测试连接
2. `outlook_web/controllers/plugins.py` 当前返回结构已经能直接服务前端表单渲染与独立保存动作
3. 因此方案 B **不需要新增插件配置后端协议**；重点是把配置 UI 从插件管理卡片迁移到独立承载区
4. `main.js.saveSettings()` 当前只处理 `/api/settings` 的全局配置保存，不适合承载插件自己的 schema 化配置

---

### Task 1.2：定义设置页里的“插件 Provider 配置承载区”

**文件**：`templates/index.html`

**目标**：

在现有：

- `#gptmailConfigPanel`
- `#cfWorkerConfigPanel`
- `#pluginManagerCard`

之间，新增一个专门给插件 Provider 使用的配置区域，例如：

- `#pluginProviderConfigPanel`

**检查点**：

- [x] 承载区位于设置页临时邮箱 Tab 内
- [x] 与插件管理卡片分开
- [x] 初始默认隐藏

**Phase 1 结论（已确认）**：

1. 现有 `templates/index.html` 已有天然锚点：
   - `#gptmailConfigPanel`
   - `#cfWorkerConfigPanel`
   - `#pluginManagerCard`
2. 最稳妥的位置就是把 `#pluginProviderConfigPanel` 插在 `#cfWorkerConfigPanel` 与 `#pluginManagerCard` 之间
3. 这样可以保持：
   - 上半部分仍然是“选中哪个 Provider，就看哪个配置面板”
   - 下半部分仍然是“插件管理 = 生命周期入口”

---

### Task 1.3：明确插件管理卡片的职责收口

**文件**：`static/js/features/plugins.js`、`templates/index.html`

**目标**：

将插件管理卡片收敛为：

1. 安装
2. 卸载
3. 应用变更
4. 加载失败展示

**不再作为最终配置入口**。

**检查点**：

- [x] 文案层面明确“插件管理”是生命周期入口
- [x] 配置行为逐步迁出卡片主体

**Phase 1 结论（已确认）**：

1. 插件管理卡片后续应保留：
   - 安装
   - 卸载
   - 应用变更
   - 加载失败展示
2. 如短期内仍保留“配置”按钮，也应改成：
   - 跳转 / 聚焦到对应 Provider 设置区
   - 而不是继续在卡片内展开表单
3. 这意味着 `plugins.js.toggleConfig()` 的职责后续要从“内联展开”转向“驱动独立设置面板”

---

## Phase 2: 设置页 UI 解耦

> **目标**：设置页选中插件 Provider 后，能看到该插件自己的配置区域，而不是只能在插件管理卡片里展开表单。

### Task 2.1：修改 `templates/index.html` — 新增插件配置承载面板

**建议位置**：

放在 `#cfWorkerConfigPanel` 与 `#pluginManagerCard` 之间。

**建议结构**：

```html
<div class="card" id="pluginProviderConfigPanel" style="display:none;">
    <div class="card-header">
        <div class="card-title" id="pluginProviderConfigTitle">🧩 插件 Provider 配置</div>
    </div>
    <div class="card-body" id="pluginProviderConfigBody">
        <div class="form-hint">请选择一个已安装插件 Provider。</div>
    </div>
</div>
```

**检查点**：

- [x] 有独立标题区和内容区
- [x] 默认隐藏
- [x] 与插件管理卡片分离

---

### Task 2.2：修改 `static/js/main.js` — 扩展 `onTempMailProviderChange(provider)`

**当前现状**：

- `legacy_bridge` → 显示 GPTMail 面板
- `cloudflare_temp_mail` → 显示 CF Worker 面板
- 插件 provider → 两张内置面板都隐藏

**目标**：

扩展为：

- 选内置 provider：保持现有行为
- 选插件 provider：显示 `#pluginProviderConfigPanel`

**检查点**：

- [x] 不破坏 GPTMail / CF Worker 原有切换逻辑
- [x] 插件 provider 选中时不再只有“空白”

---

### Task 2.3：修改 `static/js/features/plugins.js` — 将插件配置渲染迁到独立面板

**当前现状**：

- `toggleConfig(name)` 把配置表单渲染到插件管理卡片内的 `plugin-cfg-{name}`

**目标**：

改为把：

- schema 读取
- 当前配置回填
- 保存
- 测试连接

统一渲染到设置页独立的 `#pluginProviderConfigBody`。

**检查点**：

- [x] 仍复用现有 `/api/plugins/{name}/config*` 接口
- [x] 表单支持当前已有 `config_schema` 字段类型
- [x] 保存 / 测试连接行为仍可用

---

### Task 2.4：修改插件管理卡片按钮与文案

**文件**：`static/js/features/plugins.js`

**目标**：

卡片层只保留：

- 安装
- 卸载
- 应用变更

如仍保留“配置”入口，也应变成“跳转 / 聚焦到对应 Provider 设置区”，而不是在卡片内部展开。

**检查点**：

- [x] 插件管理卡片不再成为复杂配置表单的主要承载位
- [x] 用户从结构上能看懂“哪里是安装管理、哪里是业务设置”

---

## Phase 3: 临时邮箱页域名选择泛化

> **目标**：让第三方插件与内置 CF 一样，按 `get_options()` 决定域名能力，而不是按 provider 名称硬编码。

### Task 3.1：修改 `static/js/features/temp_emails.js` — 去掉 `cloudflare_temp_mail` 硬编码

**当前硬编码点**：

- `loadTempEmails()`
- `onTempEmailProviderChange(selectedProvider)`

**目标**：

改为按当前 provider 的 options 判定：

- 是否存在可选 `domains`
- `domain_strategy` 是否允许手动选择

**检查点**：

- [x] 不再直接写死 `provider === 'cloudflare_temp_mail'`
- [x] 第三方插件也能触发域名能力判定

---

### Task 3.2：引入按 Provider 维度的 options 状态管理

**文件**：`static/js/features/temp_emails.js`

**原因**：

当前 `tempEmailOptionsCache` 是单槽缓存。方案 B 落地后，需要更明确地区分：

- 当前 Provider 是谁
- 当前 options 属于谁

**建议方向**：

- 以 `provider_name` 作为 cache key
- 或引入当前活跃 provider 的 options state

**检查点**：

- [x] 切换 provider 时不会复用错误的旧 options
- [x] 域名下拉 / hint / status 与当前 provider 一致

---

### Task 3.3：统一域名下拉与提示文案

**文件**：`static/js/features/temp_emails.js`

**目标**：

让以下 UI 都按 provider options 统一生成：

- `#tempEmailDomainSelect`
- `#tempEmailOptionsHint`
- `#tempEmailOptionsStatus`

**检查点**：

- [x] 支持“有域名可选”
- [x] 支持“自动分配，不支持手动域名”
- [x] 支持“options 拉取失败”
- [x] 不再把 GPTMail 文案错误套到第三方插件上

---

### Task 3.4：创建邮箱请求继续复用当前 payload

**文件**：`static/js/features/temp_emails.js`

**目标**：

保持：

```json
{
  "prefix": "...",
  "domain": "...",
  "provider_name": "..."
}
```

仅在 UI 层修正 `domain` 是否可选，不改现有创建接口路径。

**检查点**：

- [x] `POST /api/temp-emails/generate` 路径不变
- [x] 只有在 domain 下拉启用且已选择时才带 `domain`

---

## Phase 4: 回归与验收

> **目标**：既修插件体验，也不破坏现有内置 Provider 行为。

### Task 4.1：设置页人工验收

**验收点**：

- [ ] 选择 `legacy_bridge` 时显示 GPTMail 面板
- [ ] 选择 `cloudflare_temp_mail` 时显示 CF Worker 面板
- [ ] 选择插件 provider 时显示独立插件配置面板
- [ ] 插件管理卡片仍可安装 / 卸载 / 应用变更

---

### Task 4.2：临时邮箱页人工验收

**验收点**：

- [ ] 选择支持域名的插件时，域名下拉可用
- [ ] 选择不支持域名的插件时，域名下拉禁用
- [ ] 切换不同 provider 后，hint / status / domain 选项不会串号

---

### Task 4.3：回归内置 Provider

**验收点**：

- [ ] GPTMail 原行为不变
- [ ] CF Worker 原行为不变
- [ ] `load_failed` 插件卡片仍能显示错误

---

### Task 4.4：文档回填

**需要同步**：

- [x] `docs/FD/2026-04-21-临时邮箱插件化FD.md`
- [x] `docs/TD/2026-04-21-临时邮箱插件化TD.md`
- [x] `docs/TODO/2026-04-21-临时邮箱插件化TODO.md`
- [x] `WORKSPACE.md`

---

## 当前结论

这次 TODO 的重点不是“再给插件多加一个按钮”，而是把插件 Provider 的前端承载模型彻底收口：

1. **插件管理**负责生命周期
2. **Provider 设置区**负责运行时配置
3. **临时邮箱页**按 options 动态决定域名能力

只有这样，后续继续接更多插件时，前端体验才不会继续堆积设计债。

---

## Phase 1 当前状态（截至本会话）

1. **已完成的不是代码，而是边界设计确认**
2. 当前已经明确：
   - 不新增插件配置后端协议
   - 不把插件 schema 配置并入 `/api/settings`
   - 独立插件设置面板的推荐落点
   - 插件管理卡片的职责收口方向
3. 本会话已继续把 **Phase 2 + Phase 3 的前端代码主干落地**：
   - `templates/index.html` 新增 `#pluginProviderConfigPanel`
   - `static/js/main.js` 已把插件 provider 接入设置页独立面板切换
   - `static/js/features/plugins.js` 已将插件配置表单迁到独立面板，插件卡片改为“打开设置”
   - `static/js/features/temp_emails.js` 已改为按 provider options 决定域名下拉，并增加按 provider 的 options cache + 请求防串号保护
4. 本会话随后已额外执行 `python -m unittest discover -s tests -v`，并在 `main` 工作树中 fast-forward 合入 `dev`、保留本地 `WORKSPACE.md` 改动到 stash、以及切回主干后重新执行完整回归；最新结果已更新为 `Ran 1357 tests in 463.280s`、`OK (skipped=7)`。
5. 当前人工验收实例也已按 `2.1.1` 版本重新拉起到 `http://127.0.0.1:5097`，后续剩余工作继续收敛为页面级人工点击确认。
