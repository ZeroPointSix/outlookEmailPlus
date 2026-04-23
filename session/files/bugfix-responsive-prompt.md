# 实现提示词：标准模式小窗 UI 排版错乱 — 响应式断点修复（方案 B）

> 本提示词供其他 AI 代理执行精确代码修改。
> 修改前必须通读本提示词全文，严格按以下步骤执行，不得自作主张改动范围。

---

## 一、任务背景与目标

- **来源**：GitHub Issue #50，用户反馈浏览器小窗模式下标准模式 UI 排版错乱
- **关联文档**：
  - BUG 文档：`docs/BUG/2026-04-21-标准模式小窗UI排版错乱-Grid断点适配缺陷.md`
  - TODO 文档：`docs/TODO/2026-04-21-Grid断点适配缺陷修复TODO.md`
- **关键前提**：BUG 文档中分析的 `layout.css` Grid 四栏布局系统已废弃，**当前生产代码实际使用 `.workspace` flex 三栏布局**
- **目标**：在平板断点（769px~1024px）下，默认折叠 `groups-column`，仅显示 `accounts-column + emails-column`，并提供「展开分组」按钮让用户临时查看分组

---

## 二、实际生产代码状态（修改前必须确认）

### 2.1 布局结构
- 模板：`templates/index.html` 中使用 `<div class="workspace workspace-mailbox">`
- 三栏：
  - `.groups-column { width: 220px; flex-shrink: 0; }`
  - `.accounts-column { width: 280px; flex-shrink: 0; }`
  - `.emails-column { flex: 1; min-width: 0; }`

### 2.2 平板断点现状
- `@media (max-width: 1024px) and (min-width: 769px)` 只处理了 sidebar（缩为 60px）
- `.groups-column { width: 180px; }` 和 `.accounts-column { width: 240px; }` 仍为固定宽度
- `.workspace` 保持 `flex-direction: row`，无折叠机制
- **问题区间**：800px~1024px 时，三栏内容开始挤压错位

---

## 三、修改范围（仅限以下 4 个文件）

| 序号 | 文件 | 修改类型 | 说明 |
|------|------|---------|------|
| 1 | `static/css/main.css` | 编辑 | 平板断点中增加 groups 折叠与展开覆盖样式 |
| 2 | `templates/index.html` | 编辑 | `accounts-column` header 中增加「展开分组」按钮 |
| 3 | `static/js/main.js` | 编辑 | 增加 `toggleGroupsColumn()` 函数 |
| 4 | `static/js/i18n.js` | 编辑 | 增加「展开分组」词条 |

**严禁修改**其他文件（如 `layout.css`、`layout-manager.js`、后端代码、测试代码等）。

---

## 四、逐文件精确修改说明

### 文件 1：`static/css/main.css`

**修改位置**：第 1337–1352 行，`@media (max-width: 1024px) and (min-width: 769px)` 规则块内部。

**当前代码**（第 1337–1352 行）：
```css
@media (max-width: 1024px) and (min-width: 769px) {
  .sidebar { width: 60px; overflow: hidden; }
  .sidebar .nav-item span:not(.nav-icon),
  .sidebar-logo span, .sidebar-logo small,
  .user-chip-info, .nav-section { display: none; }
  .sidebar-logo { justify-content: center; padding: 1rem 0.5rem; }
  .nav-item { justify-content: center; padding: 0.7rem; }
  .sidebar-bottom { padding: 0.5rem; }
  .user-chip { justify-content: center; }
  .btn-logout, .btn-github, .btn-theme { font-size: 0; padding: 0.45rem 0; }
  .btn-github { gap: 0; overflow: hidden; }
  .btn-github span { display: none; }
  .page { padding: 1rem; }
  .groups-column { width: 180px; }
  .accounts-column { width: 240px; }
}
```

**修改方式**：将 `.groups-column { width: 180px; }` 和 `.accounts-column { width: 240px; }` 替换为以下规则：

```css
  /* 平板断点：默认折叠 groups 栏 */
  .groups-column { width: 240px; }
  .workspace.workspace-mailbox .groups-column {
    display: none;
  }
  /* 展开覆盖：groups 作为浮动侧边面板 */
  .workspace.workspace-mailbox .groups-column.groups-expanded {
    display: flex;
    position: absolute;
    left: 60px;              /* sidebar 缩后宽度 */
    top: 52px;               /* topbar 高度 */
    height: calc(100vh - 52px);
    width: 220px;
    z-index: 20;
    box-shadow: 4px 0 24px rgba(0,0,0,0.25);
    border-right: 1px solid var(--border);
    background: var(--bg-card);
  }
  /* 隐藏 groups 与 accounts 之间的 resizer */
  .workspace-resizer[data-resize-role="groups-to-accounts"] {
    display: none;
  }
```

**注意**：
- 不要删除该 `@media` 中已有的任何规则（sidebar、page padding 等），只替换最后两行 `.groups-column` / `.accounts-column` 的定义。
- `.groups-column { width: 240px; }` 放在前面是为了让非 `.workspace-mailbox` 场景（如临时邮箱页左侧）仍保持合理宽度。
- `.workspace.workspace-mailbox .groups-column.groups-expanded` 使用绝对定位，避免展开后挤占 accounts/emails 空间。

---

### 文件 2：`templates/index.html`

**修改位置**：`#accountPanel`（accounts-column）的 `.column-header` 内部，在 `<span class="column-title">` 的开头增加一个按钮。

**当前代码**（约第 200–210 行）：
```html
                    <!-- Accounts Column -->
                    <div class="workspace-panel accounts-column" id="accountPanel">
                        <div class="column-header">
                            <span class="column-title">
                                <span class="group-color-dot" id="currentGroupColor" style="background-color:#666;"></span>
                                <span id="currentGroupName">选择分组</span>
                            </span>
```

**修改方式**：将 `<span class="column-title">` 内部替换为：

```html
                            <span class="column-title">
                                <button class="btn-icon btn-toggle-groups" id="btnToggleGroups" onclick="toggleGroupsColumn()" title="展开分组">
                                    ☰
                                </button>
                                <span class="group-color-dot" id="currentGroupColor" style="background-color:#666;"></span>
                                <span id="currentGroupName">选择分组</span>
                            </span>
```

**注意**：
- 按钮使用 `.btn-icon`（已有样式）+ `.btn-toggle-groups`（新增标识类）
- 按钮文字用 `☰`（汉堡图标），简洁不占空间
- title 使用中文「展开分组」，由 i18n 在运行时翻译（见文件 4）

---

### 文件 3：`static/js/main.js`

**修改位置**：在 `initResizeHandles()` 函数附近（约第 701–747 行）之后，新增一个函数。请搜索 `function initResizeHandles()`，在其闭合大括号 `}` 之后添加。

**新增代码**：

```javascript
        // ==================== 平板断点 groups 栏展开/折叠 ====================

        function toggleGroupsColumn() {
            const groupPanel = document.getElementById('groupPanel');
            const btn = document.getElementById('btnToggleGroups');
            if (!groupPanel) return;
            const isExpanded = groupPanel.classList.toggle('groups-expanded');
            if (btn) {
                btn.title = isExpanded ? translateAppTextLocal('收起分组') : translateAppTextLocal('展开分组');
            }
        }
```

**注意**：
- `translateAppTextLocal` 是项目中已有的翻译函数，可直接调用。
- 如果 `translateAppTextLocal('收起分组')` 在 i18n 中未命中，会回退显示原文，不会报错。

---

### 文件 4：`static/js/i18n.js`

**修改位置**：在 `exactMap` 对象中，找到 `'分组': 'Groups',` 附近，追加两条词条。

**当前代码位置参考**（约第 203 行附近）：
```javascript
        '分组': 'Groups',
        '添加分组': 'Add Group',
```

**修改方式**：在 `'分组': 'Groups',` 之后立即追加：

```javascript
        '展开分组': 'Expand Groups',
        '收起分组': 'Collapse Groups',
```

**注意**：
- 必须放在 `exactMap` 内部，不要放错到 `regexMap` 数组里。
- 保持缩进和逗号格式与周围一致。

---

## 五、按钮样式补充（可选但建议）

如果希望在桌面端（≥1025px）隐藏「展开分组」按钮（因为桌面端 groups 栏默认展开，不需要这个按钮），请在 `static/css/main.css` 中**任意合适位置**（建议在 `.btn-icon` 规则附近，或直接在平板断点规则外面）添加：

```css
/* 桌面端隐藏「展开分组」按钮 */
.btn-toggle-groups { display: none; }
```

这样配合平板断点中 `.workspace.workspace-mailbox .groups-column { display: none; }`，按钮和折叠行为只会在 769px~1024px 生效。

> 如果你找不到 `.btn-icon` 的位置，也可以不添加这条规则。按钮在桌面端会显示，但点击后 groups 栏已经默认展开，不会有实际副作用，只是 UI 上多一个无用按钮。建议尽量加上。

---

## 六、验收标准

修改完成后，请按以下矩阵在浏览器中人工验收：

| 窗口宽度 | 预期行为 | 验收要点 |
|----------|---------|---------|
| 1366px | 三栏全部展开，无「展开分组」按钮 | groups 可见 ✅ |
| 1024px | sidebar 缩为 60px，groups **隐藏**，accounts + emails 展开 | groups 不可见，有「☰」按钮 ✅ |
| 900px | 同上 | 点击「☰」按钮后 groups 以浮动面板出现 ✅ |
| 800px | 同上 | 按钮不与其他 header 元素重叠 ✅ |
| 768px | 进入移动端断点，sidebar 抽屉、三栏 column | 无需测试 groups 折叠 ✅ |
| 点击「☰」后 | groups 浮动面板出现，覆盖在 accounts 左侧 | 面板可正常滚动、选择分组 ✅ |
| 再次点击「☰」 | groups 浮动面板消失 | 回到 accounts + emails 两栏 ✅ |

---

## 七、修改后必须执行的检查

1. **全量回归测试**：
   ```bash
   python -m unittest discover -s tests -v
   ```
   - 预期结果：`OK (skipped=7)`
   - 如果失败，检查是否误改了其他文件

2. **代码格式检查**（如果本地有 black/isort）：
   - 本任务只改前端文件，Python 测试不应受影响。
   - 但如果改动了 HTML/JS/CSS 后不小心触发了其他格式化工具，请确认 diff 范围。

3. **i18n 检查**：
   - 将 UI 语言切换为 English，确认「☰」按钮的 tooltip 显示为 "Expand Groups" / "Collapse Groups"

---

## 八、禁止事项

- ❌ 不要修改 `layout.css`、`layout-manager.js`、`state-manager.js`
- ❌ 不要修改后端 Python 代码
- ❌ 不要修改测试文件
- ❌ 不要删除或改动 `@media (max-width: 1024px) and (min-width: 769px)` 中已有的 sidebar 规则
- ❌ 不要引入新的 JS 库或 CSS 框架
- ❌ 不要改动 `mailbox-compact-layout`（简洁模式）的样式

---

## 九、文档回写（修改完成后由执行 AI 执行）

修改完成后，请更新以下文档：

1. `docs/TODO/2026-04-21-Grid断点适配缺陷修复TODO.md`
   - Task 2 状态改为「✅ 已完成」
   - Task 5（人工验收）、Task 6（全量回归）、Task 7（文档回写）根据实际结果更新

2. `WORKSPACE.md`
   - 在 2026-04-21 下新增一条操作记录，简述本次代码修改内容

---

*提示词生成时间：2026-04-21*
*方案：B（平板断点折叠 groups）*
*执行前请再次确认当前生产代码与上述「实际生产代码状态」一致*
