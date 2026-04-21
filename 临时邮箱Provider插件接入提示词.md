# 临时邮箱 Provider 插件接入提示词

> 用法：把下面整段提示词复制给 AI / Agent，并把方括号中的占位信息替换成你的目标 Provider 信息。
>
> 目标不是重做插件系统，而是**在当前已完成的插件架构上新增一个 Provider 插件**。

---

## 可直接发送给 Agent 的提示词

```markdown
你是一个 Python/Flask 后端开发者，正在为 OutlookMail Plus 接入一个新的“临时邮箱 Provider 插件”。

你的目标不是修改现有插件系统主干，而是**基于当前已经完成的插件架构，新增一个可运行的 Provider 插件**。

## 项目信息

- 项目：OutlookMail Plus
- 技术栈：Python 3.11+ / Flask / SQLite / 原生 JS / Docker
- 分层约定：Route → Controller → Service → Repository
- 当前插件系统已完成，不要重做 registry / factory / plugin manager 主干

## 在开始前必须先阅读

1. `临时邮箱Provider插件接入说明.md`
2. `docs/TD/2026-04-21-临时邮箱插件化TD.md`
3. `docs/TDD/2026-04-21-临时邮箱插件化TDD.md`
4. `docs/FD/2026-04-21-临时邮箱插件化FD.md`
5. `docs/TODO/2026-04-21-临时邮箱插件化TODO.md`

## 这次要接入的 Provider 信息

- Provider 名称：`[provider_name]`
- Provider 展示名：`[provider_label]`
- 作者：`[provider_author]`
- 版本：`[provider_version]`
- 上游服务说明：`[一句话描述该临时邮箱平台]`
- API 文档 / 接口说明：`[粘贴文档链接或关键接口说明]`
- 鉴权方式：`[Bearer Token / API Key / JWT / 无鉴权 / 其他]`
- 域名列表接口：`[METHOD URL + 返回示例]`
- 创建邮箱接口：`[METHOD URL + 请求参数 + 返回示例]`
- 邮件列表接口：`[METHOD URL + 返回示例]`
- 邮件详情接口：`[METHOD URL + 返回示例；如果没有请明确写“无单独详情接口”]`
- 删除单封接口：`[METHOD URL + 返回示例；如没有写无]`
- 清空邮箱接口：`[METHOD URL + 返回示例；如没有写无]`
- 删除邮箱接口：`[METHOD URL + 返回示例；如没有写无]`
- 配置项：`[例如 base_url / api_key / account_id / project_id / admin_key]`
- 依赖库：`[如 requests / pyjwt / 无额外依赖]`

## 必须遵守的实现边界

1. **不要重做插件系统主干**
   - 不要推翻现有 `_REGISTRY`
   - 不要重写现有 `load_plugins()` / `reload_plugins()` 设计
   - 不要改产品路径 `/api/temp-emails/*` 与 `/api/external/temp-emails/*`
2. **优先做插件本身**
   - 新增一个 Provider 插件文件
   - 只在确有必要时补少量配套代码
3. **遵守当前真实路径口径**
   - 运行时插件目录实际是：`<DATABASE_PATH 上级目录>/plugins/temp_mail_providers/`
   - 当前加载器只扫描该目录下一层的 `*.py`，不要把插件做成嵌套目录结构
4. **理解当前前端限制**
   - 插件 provider 虽然会被注入临时邮箱页面的 Provider 下拉
   - 但当前 `temp_emails.js` 仍把“域名下拉是否可用”硬编码在 `cloudflare_temp_mail`
   - 如果你的任务包含“让插件支持手动选域名”，就不能只写 Provider 插件，还需要单独改前端逻辑
5. **错误处理要显式**
   - 不要 silent fallback
   - 不要把失败伪装成成功
6. **返回结构要兼容平台**
   - `get_options()` 提供 domains / prefix_rules / provider 元信息
   - `create_mailbox()` 返回 `{ success, email, meta }` 或 `{ success: False, error, error_code }`
   - `list_messages()` 返回平台标准消息结构
7. **区分插件管理与运行时设置**
   - 当前实现会把 `config_schema` 渲染在插件管理卡片中
   - 但产品方向应是：插件管理只负责安装 / 卸载 / 应用变更，业务配置应放到对应 Provider 设置位
   - 如果本次任务涉及 UI 改造，不要继续把复杂业务设置堆进安装界面
8. **让当前 UI 兼容可用**
   - 如果需要配置，必须给出 `config_schema`
   - 保存配置后，“测试连接”应能通过 `get_options()` 做最小连通性检查

## 你要完成的任务

### 任务 1：实现 Provider 插件

创建一个新的 Provider 类，要求：

- 继承 `TempMailProviderBase`
- 使用 `@register_provider`
- 声明：
  - `provider_name`
  - `provider_label`
  - `provider_version`
  - `provider_author`
  - `config_schema`
- 实现：
  - `get_options()`
  - `create_mailbox()`
  - `delete_mailbox()`
  - `list_messages()`
  - `get_message_detail()`
  - `delete_message()`
  - `clear_messages()`

### 任务 2：处理配置读取

如果这个 Provider 需要配置项，请从 settings 中按如下 key 读取：

```text
plugin.[provider_name].[field_key]
```

并确保默认值合理。

### 任务 3：处理消息结构归一化

把上游邮件结构归一化成平台标准字段，至少保证：

```python
{
    "id": "...",
    "message_id": "...",
    "from_address": "...",
    "subject": "...",
    "content": "...",
    "html_content": "...",
    "has_html": True or False,
    "timestamp": 1710000000,
}
```

### 任务 4：补最小测试

按当前代码风格补最小必要测试，至少覆盖：

1. Provider 能被注册 / 发现
2. `get_options()` 返回结构稳定
3. `create_mailbox()` 成功与失败分支
4. 邮件列表归一化
5. 如存在 detail fallback，覆盖 fallback 行为

### 任务 5：补文档

如果你新增了一个正式接入的 Provider，请同步更新：

- `README.md`（如需要对外暴露）
- 相关实现说明 / 使用说明（如本次改动直接影响使用方式）

## 实现建议

1. 先参考：
   - `outlook_web/services/temp_mail_provider_cf.py`
   - `outlook_web/services/temp_mail_provider_custom.py`
2. 如果上游没有单独 detail 接口：
   - 允许通过 `list_messages()` 回退过滤
3. 如果上游有 provider 侧 mailbox id / token：
   - 放进 `meta`
4. 如果上游接口会超时或返回非 JSON：
   - 给出清晰 `error` / `error_code`
5. 如果这个 Provider 是通过插件安装分发：
   - 视情况补 `registry.json` 条目

## 交付要求

最终请直接产出：

1. 新的 Provider 插件代码
2. 必要的测试代码
3. 必要的文档更新
4. 一段简短说明，明确：
   - 新增了哪些文件
   - Provider 的配置项是什么
   - 如何人工验收

## 验收标准

以下条件至少要成立：

1. 插件能被系统加载
2. 插件管理中可以看到它
3. 配置表单能正常渲染（如有配置）
4. 测试连接可用
5. 能创建邮箱
6. 能读取邮件
7. 失败时不会影响内置 Provider
8. 如果故障加载，UI 会显示 `load_failed` 错误态

> 如果本次任务还包含“插件域名可手动选择”，请额外确认：
>
> - 临时邮箱页在选中该插件时会正确启用域名下拉
> - 域名列表来自该插件的 `get_options()`，而不是写死 provider 名称

请直接开始实现，不要只给方案。
```

---

## 什么时候用这份提示词最合适

适合以下场景：

1. 你已经有某个临时邮箱平台的 API 文档
2. 你希望 AI 直接帮你在当前仓库里实现一个新的 Provider 插件
3. 你希望 AI 不要再去重做插件系统，而是专注在“新增 Provider”

---

## 搭配阅读

- `临时邮箱Provider插件接入说明.md`
- `docs/TD/2026-04-21-临时邮箱插件化TD.md`
- `docs/TDD/2026-04-21-临时邮箱插件化TDD.md`
