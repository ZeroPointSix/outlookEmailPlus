# Issue #55 实现蓝图：标准模式多选邮箱批量拉取

## 关联正式文档

- PRD：`docs/PRD/2026-04-25-标准模式多选邮箱批量拉取PRD.md`
- FD：`docs/FD/2026-04-25-标准模式多选邮箱批量拉取FD.md`
- TD：`docs/TD/2026-04-25-标准模式多选邮箱批量拉取TD.md`
- TDD：`docs/TDD/2026-04-25-标准模式多选邮箱批量拉取TDD.md`
- TODO：`docs/TODO/2026-04-25-Issue55-标准模式多选邮箱批量拉取TODO.md`

## 已创建测试文件

- `tests/test_batch_fetch_frontend_contract.py`
- `tests/test_batch_fetch_email_api_contract.py`
- `tests/batch-fetch/jest.config.js`
- `tests/batch-fetch/setup.js`
- `tests/batch-fetch/batch-fetch-main.test.js`

## 最近测试运行结果

- Python：
  - 命令：`python -m unittest tests.test_batch_fetch_frontend_contract tests.test_batch_fetch_email_api_contract -v`
  - 结果：`13` 个用例全部通过（GREEN）
  - 原红灯已全部消除
- Jest：
  - 命令：`npx jest --config tests\\batch-fetch\\jest.config.js --runInBand`
  - 结果：`8` 个用例全部通过（GREEN）
  - jest-environment-jsdom 已安装，setup.js mock 恢复已修复

## 仓库级全量测试结果（2026-04-25）

- Python 全量：
  - 命令：`python -m unittest discover -s tests -v -f`
  - 结果：`1404` 个用例全部通过，`skipped=7`
- 浏览器扩展 Jest：
  - 命令：`npm run test:browser-extension`
  - 结果：`12` 个用例全部通过（GREEN）
  - 修复点：
    - `browser-extension/popup.js`
    - `browser-extension/popup.html`
  - 本轮后结论：
    - 仓库级 Python 全量通过
    - 浏览器扩展 Jest 全量通过
    - 当前会话涉及的仓库级测试入口已全部转绿
  - 最新复跑确认：
    - 在“部分成功按账号成功处理”语义落地后再次复跑
    - Python：`1404` 通过，`skipped=7`
    - 浏览器扩展 Jest：`12/12` 通过
  - 人工验收后再次复跑：
    - Python：`1404` 通过，`skipped=7`
    - 日志确认：`Ran 1404 tests in 454.408s`
    - 浏览器扩展 Jest：`12/12` 通过

## 本地人工验收服务（2026-04-25）

- 启动命令：`python start.py`
- 实际监听地址：`http://127.0.0.1:5000`
- 监听进程 PID：`8640`
- 健康检查：
  - `GET /healthz`
  - 状态：`200`
  - 响应：`{"boot_id":"1777097456978-8640","status":"ok","version":"2.3.0"}`
- 说明：
  - 本轮最初尝试按 `5600` 端口启动后台实例
  - 但实际启动日志显示服务绑定到了默认 `5000`
  - 因此当前人工验收应以 `http://127.0.0.1:5000` 为准

## 实现后代码审查收尾（已完成）

在代码审查指出 3 个收尾问题后，当前已经完成对应修正：

1. `static/js/main.js`
   - 批量拉取进度已改为按账号完成数更新
   - 最终成功/失败汇总已改为账号级统计，不再使用 `successCount / 2`
2. `static/js/main.js`
   - 未选中账号时的错误提示已改为批量拉取邮件场景专用文案
3. `static/js/main.js`
   - 批量拉取成功后已补上 `account_summary` 回写
   - 若接口返回 `account_summary`，现已调用 `syncAccountSummaryToAccountCache(...)`

当前判断：

- 这 3 项代码审查问题已完成修复
- 对应回归测试已补齐并通过

## 最终 diff 审查收口（已定）

在最后一轮 diff 审查指出“部分成功语义”问题后，当前已按用户选择完成收口：

1. `static/js/main.js`
   - 当同一账号出现“部分成功”（例如 `inbox` 成功、`junkemail` 失败）时
   - 当前口径已改为：
     - **只要任一 folder 成功，即按该账号成功处理**
     - 保留已成功 folder 的缓存
     - 不再把该账号列入失败列表

当前判断：

- 该语义问题已完成口径决策并落实到实现
- 对应 Issue #55 定向回归已再次通过

## 一、问题定位

Issue #55 的真实场景不是紧凑模式，也不是多账号混合邮件浏览，而是：

- 用户位于**标准模式**
- 在账号列表中通过复选框勾选多个邮箱
- 触发一个新的批量动作：**批量拉取邮件**

当前推荐做法不是重构邮件区，而是做一版**标准模式 latest-only 轻量批量拉取 / 预热缓存**。

---

## 二、现状边界

### 2.1 已有能力

1. 标准模式已有账号多选：
   - `account-select-checkbox`
   - `selectedAccountIds`
   - `batchActionBar`
2. 现有邮件获取接口可直接复用：
   - `GET /api/emails/<email_addr>`
3. 前端已有缓存模型：
   - `emailListCache[${email}_${folder}]`

### 2.2 当前不能直接复用成“多账号浏览”的原因

1. 右侧邮件面板由 `currentAccount` 驱动
2. `currentEmails` / `currentFolder` / 分页 / 详情 / 删除 都是单账号语义
3. 因此 V1 不应改成多账号混合邮件列表

### 2.3 架构约束

1. 项目当前存在**单 worker / 单进程**约束
2. 因此批量拉取如果设计成“单个后端请求里长时间串行处理全部账号”，可用性会很差
3. V1 应优先避免：
   - 长时间阻塞 worker
   - 大并发请求风暴
   - 看起来是“批量功能”，实际却把界面卡住

---

## 三、推荐方案 A（V1）

### 3.1 前端入口

在**标准模式** `batchActionBar` 中新增一个按钮：

- 文案：`批量拉取邮件`
- 入口函数建议：`showBatchFetchConfirm()` / `batchFetchSelectedEmails()`
- 视觉层级：普通动作按钮（`ghost`）

说明：

- 只在标准模式显示
- 继续沿用 `selectedAccountIds` 作为选择来源
- 只改标准模式 `batchActionBar`，不改 `compactBatchActionBar`
- 不与现有 `刷新 Token` 争夺主按钮层级

### 3.2 账号解析

从 `selectedAccountIds` 解析出本次要处理的账号集合：

1. 扫描 `accountsCache` 各分组数组，并按 ID 回查账号信息
2. 提取最小必要字段：
   - `id`
   - `email`
   - `account_type`
   - `provider`
3. 默认沿用当前批量操作语义：
   - **允许跨分组处理所有已选账号**
4. 当前先按用户要求：
   - **不设置单次选择上限**

### 3.3 批量执行策略

V1 推荐直接复用现有前端请求链路，不新增后端 selected fetch API；并且默认只做**latest-only 轻量拉取**：

1. 对每个目标账号发起两类请求：
   - `GET /api/emails/<email_addr>?folder=inbox&skip=0&top=10`
   - `GET /api/emails/<email_addr>?folder=junkemail&skip=0&top=10`
2. 设计意图：
   - 对齐当前“验证码 / 最新邮件”场景
   - 不追求整箱同步
   - 优先拿到最新候选内容
3. 执行方式：
   - 串行
   - 或极小并发（建议上限 1~2）
4. 原因：
   - 当前单 worker 架构下，长阻塞接口和大并发都不友好
   - 这样更接近“轻量探测/预热”，而不是“批量完整拉信”
   - 保持前端实现简单，且不需要立即引入任务编排

### 3.4 缓存回写

单个账号拉取成功后，结果直接写入现有缓存：

- key：`${email}_${folder}`
- value：
  - `emails`
  - `has_more`
  - `skip`
  - `method`

如果当前正在查看的 `currentAccount` 刚好也在本次批量集合中，并且 folder 一致，则：

1. 用最新缓存刷新当前 `currentEmails`
2. 更新 `emailCount`
3. 重新渲染右侧邮件列表

### 3.5 完成反馈

V1 推荐用前端常驻 Toast / 进度提示即可：

1. 开始时：
   - 显示 `正在批量拉取邮件... 0 / N`
2. 进行中：
   - 更新成功数 / 当前进度
3. 完成后：
   - 汇总成功数 / 失败数
   - 展示失败账号列表

说明：

- 当前标准模式账号卡片并不直接显示 `latest_email_*` 摘要
- 因此 V1 不强依赖“卡片即时变更”作为核心反馈

### 3.6 最终成品形态（当前收敛版）

这个功能最终不应被实现成“多账号邮件浏览器”，而应被实现成：

1. 用户在**标准模式**勾选多个邮箱
2. 点击 `batchActionBar` 中的 **“批量拉取邮件”**
3. 系统对每个已选邮箱执行：
   - `inbox + junkemail`
   - latest-only
   - 串行或极小并发拉取
4. 拉取结果回写现有缓存
5. 当前账号不被强制切换（已确认）
6. 用户随后点击这些已拉取账号时，右侧列表能更快拿到最新数据

---

## 四、明确不纳入 V1 的内容

1. 多账号混合邮件列表
2. 改造右侧详情区为多账号上下文
3. 后端 SSE 编排版批量拉取
4. 紧凑模式同步入口

---

## 五、后续可升级方案 B

如果后续确认需要：

- 更稳定的进度流
- 后端统一错误聚合
- 可审计的批量拉取任务
- 规避单 worker 下长阻塞请求的体验问题

则应优先考虑**job / probe 化**，而不是直接做长时间 SSE：

1. 创建批量拉取任务
2. 立即返回任务 ID
3. 由调度器或后台轮询逐步推进
4. 前端通过状态轮询拿结果

这样更符合当前架构约束。

---

## 六、剩余非阻塞讨论点

1. **失败账号是否需要“重试失败项”入口**
   - V1 可不做

---

## 七、当前结论

Issue #55 适合按以下顺序推进：

1. 先落地 **方案 A：标准模式 latest-only 轻量批量拉取**
2. 默认处理 `inbox + junkemail`
3. 当前先不设单次选择上限
4. 先解决“多选后快速拿到最新邮件/验证码状态”的效率问题
5. 不把范围扩成“多账号混合浏览”
