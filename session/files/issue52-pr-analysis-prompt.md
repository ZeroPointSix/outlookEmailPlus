# Issue #52 执行提示词（PR 流程，前端优先）

> 目标：在最小改动下优先修复“前端邮件列表顺序异常”，并按仓库 PR 流程输出可审查变更。

## 0. 前提

- 先阅读：
  - `docs/BUG/2026-04-22-Issue52-邮件列表倒序与验证码提取失败分析.md`
  - `CLAUDE.md`
  - `WORKSPACE.md` 最新记录

## 1. 上下文确认

1. 明确本次会话口径：当前优先前端顺序问题
2. 确认影响文件边界
3. 明确测试范围（定向 + 全量）

## 2. 实施顺序（建议）

1. **先测后改**：先写/补会失败的回归用例（前端列表顺序）
2. **最小修复**：只改前端显示层顺序逻辑，不做无关重构
3. **验证**：
   - 定向测试（与前端顺序相关）
   - 全量回归 `python -m unittest discover -s tests -v`

## 2.1 新逻辑说明（当前口径）

前端新增“显示层排序兜底”统一策略：

1. 新增 `resolveEmailSortTimestamp(email)`：
   - 读取 `receivedDateTime/date/created_at/received_at`
   - 用 `Date.parse` 解析时间戳
2. 新增 `sortEmailsByNewestFirst(list)`：
   - 按时间戳降序
   - 同时间按原索引稳定排序
3. 在三处接入：
   - `loadEmails` 成功后
   - cache 恢复前
   - `loadMoreEmails` 合并后
4. 不改变后端分页协议和接口结构。

## 3. PR 输出模板

### 标题（示例）

`fix: normalize frontend email list ordering for Issue #52`

### Summary

- 统一前端邮件列表显示顺序口径，修复“倒序/乱序”用户可见问题。
- 在首页加载、缓存恢复、分页追加后统一执行最新优先兜底排序。
- 不修改后端分页协议与外部接口结构。

### Validation

- 受影响定向测试：xxx
- 全量测试：xxx

### Risk & Compatibility

- 不改变外部 API 结构
- 不改变既有后端错误码契约

## 4. 当前会话进展（2026-04-22）

1. 前端排序兜底代码已在 `emails.js` / `main.js` 接入完毕（首屏、缓存恢复、分页追加、切换文件夹）。
2. 已补充前端契约测试：
   - `tests/test_v190_frontend_contract.py`
   - `test_frontend_email_list_sorting_fallback_is_present_on_all_key_paths`
3. 已执行定向验证：
   - `python -m unittest tests.test_v190_frontend_contract.V190FrontendContractTests.test_frontend_email_list_sorting_fallback_is_present_on_all_key_paths -v`
   - 结果：`OK`
4. 下一步建议：执行全量回归并准备 PR 文案。

## 5. 分批全量回归结果（2026-04-22）

按功能域分批执行（每批控制在 300000ms 内），结果如下：

1. Batch 1（前端契约/响应式/设置前端）：`Ran 128 tests` → `OK`
2. Batch 2（核心后端/迁移/安全/OAuth）：`Ran 251 tests` → `OK`
3. Batch 3（external/pool API + verification + notification）：`Ran 393 tests` → `OK`
4. Batch 4（IMAP + settings backend + account flow）：`Ran 149 tests` → `OK`
5. Batch 5（pool + temp-mail）：`Ran 223 tests` → `OK (skipped=1)`
6. Batch 6（overview + version/system + smoke）：`Ran 113 tests` → `OK (skipped=6)`
7. 余量核对：`tests.test_frontend_manual` 单独执行 → `NO TESTS RAN`

结论：本次分批全量回归未出现 FAIL/ERROR，可进入 PR 文案整理与提交环节。
