# WORKSPACE — 工作区操作记录

> 本文档记录项目开发过程中的操作日志，按日期倒序排列。

---

## 2026-04-12

### 0xh. main 直接发布链路修复与 v1.15.1 补发（本次会话）

**时间**：2026-04-12

**背景**：

1. 用户要求在 `main` 分支直接执行发布，不再停留在 `dev`。
2. `v1.15.0` 首次发布后出现 CI 门禁失败：`Code Quality` 与 `Build and Push Docker Image` 失败。
3. 用户要求继续检查 CI/CD，并确保两个镜像仓库状态可核对。

**本次实际动作**：

1. 发布 `v1.15.0`：
   - 更新版本与发布文档：`outlook_web/__init__.py`、`CHANGELOG.md`、`docs/DEVLOG.md`、`README.md`、`README.en.md`、`tests/test_version_update.py`
   - 提交：`716c479 docs(release): prepare v1.15.0 notes and version bump`
   - 推送 `main` + tag `v1.15.0`
   - 自动创建 GitHub Release：`https://github.com/ZeroPointSix/outlookEmailPlus/releases/tag/v1.15.0`
2. CI 故障定位：
   - 失败根因是格式化门禁（`black --check` / `isort --check-only`）未通过，日志显示 47 文件需重排。
3. CI 修复：
   - 执行全仓格式化：`black` + `isort`
   - 提交：`61208e0 chore(format): align codebase with black and isort for CI`
   - 推送后，`main` 相关工作流全绿（Build&Push / Code Quality / Python Tests / SonarCloud）。
4. 为补齐“版本标签镜像”再发布 `v1.15.1`：
   - 版本与文档更新（同一套 release 文件）
   - 提交：`d09d67f docs(release): v1.15.1 ci gate recovery and mirror tag`
   - 推送 `main` + tag `v1.15.1`
   - 自动创建 GitHub Release：`https://github.com/ZeroPointSix/outlookEmailPlus/releases/tag/v1.15.1`
   - `v1.15.1` tag 的 `Build and Push Docker Image` 成功。
5. 两个镜像仓库核对（digest 级）：
   - GHCR 与 Docker Hub 均存在并一致：
     - `v1.15.1` / `v1.15.1-d09d67f` → `sha256:4b1985478bb0f2c0fdf1ec6ef705ee62858919a886c7a8c79acd880ac45dd964`
     - `main` / `main-d09d67f` / `latest` → `sha256:a409244bf43a7f2e921d86f4977eeced462942d589b66d57982f1ed8eb930a9f`

**文档同步**：

1. `CHANGELOG.md`：新增 `v1.15.1` 段并补充 CI/镜像一致性验证结果。
2. `docs/DEVLOG.md`：新增 `v1.15.1` 版本记录，补齐 tag 构建与双仓 digest 核对信息。
3. `README.md` / `README.en.md`：稳定版本更新为 `v1.15.1`。

**结论**：

1. `main` 发布链路已恢复，当前 `v1.15.1` 对应的 release / CI / 镜像均闭环。
2. 双仓（GHCR + Docker Hub）关键标签一致性正常。

### 0xg. 设置页 i18n 缺失补齐（本次会话）

**时间**：2026-04-12

**背景**：

1. 用户反馈设置页存在“部分中文文本在切换英文后未翻译”的问题。
2. 目标是补齐 i18n 缺失映射，不改动业务功能。

**本次实际动作**：

1. 定位页面文案来源：`templates/index.html`。
2. 定位翻译映射：`static/js/i18n.js` 的 `exactMap`。
3. 补齐缺失词条（摘要）：
   - `⚙️ 基础设置`、`🤖 验证码 AI 增强`
   - `启用验证码 AI 增强（系统级）`
   - `规则提取优先；仅在规则不足时触发 AI 回退。`
   - `AI 模型 ID`、`🤖 测试 AI 配置`
   - `建议先保存配置再测试。`
   - `自建域名临时邮箱服务`、`CF Worker 部署的临时邮箱`
   - `自动读取 CF Worker 的域名配置，同步至下方域名字段。`
   - `可用域名（只读 · 通过同步按钮更新）`
   - `默认域名（只读 · 通过同步按钮更新）`
   - 同时补充无空格/半角括号变体，避免口径差异导致匹配失败。
4. 回归验证：
   - `python -m pytest tests/test_settings_tab_refactor_frontend.py tests/test_settings_tab_refactor_backend.py -q`
   - 结果：`26 passed`

**文档同步**：

1. 新增 TD：`docs/TD/2026-04-12-设置页i18n缺失补齐-TD.md`

**续跑验证（同会话）**：

1. 用户确认效果后，执行全量测试：
   - `python -m pytest -q`
   - 结果：`1038 passed, 9 skipped in 320.79s`
2. 结论：i18n 补齐未引入全量回归问题。

### 0xa. dev 分支合并后“三项测试”执行与后台进程控制补记（本次会话）

**时间**：2026-04-12

**背景**：

1. 用户要求在 `dev` 分支执行三类验证：性能一次、回归一次、全量一次。
2. 用户强调命令方式必须为后台独立进程（`Start-Process`），并要求全程同步记录。

**本次实际动作**：

1. 分支状态确认：`dev`。
2. 回归测试（后台进程）执行并通过：
   - 输出文件：`test_regression_stdout.log` / `test_regression_stderr.log`
   - 结果：`139 passed in 138.80s`。
3. 全量测试（后台进程）执行并通过：
   - 输出文件：`test_full_stdout.log` / `test_full_stderr.log`
   - 结果：`1018 passed, 9 skipped in 481.62s`。
4. 性能测试阶段出现流程中断：
   - 曾尝试启动后台服务进程用于采样；
   - 用户当场中止并要求先解释“为何看起来停不下来”；
   - 已立即执行回滚：停止对应 PID，复核 `5000` 端口无监听。

**关于“为什么停不下来”的结论**：

1. `Start-Process` 启动的是独立后台常驻进程，不会因当前命令超时自动退出。
2. 工具超时仅终止“等待命令结果”，不会回收已启动服务进程。
3. 若重复执行启动命令会累计新的后台实例，需要显式停 PID/端口。

**文档同步**：

1. `docs/FD/2026-04-11-邮件获取性能优化FD.md`：新增 9.6（dev 分支合并后测试回填 + 机制说明）。
2. `docs/TD/2026-04-11-邮件获取性能优化TD.md`：新增 9.6（验证补记 + 后台进程机制说明）。
3. `docs/TDD/2026-04-11-邮件获取性能优化-TDD.md`：新增 15.7（回归/全量结果回填 + 流程约束）。

**当前状态**：

1. 回归与全量均通过。
2. 本轮性能数据未形成新的有效采样结论（沿用既有 A/B 数据）。

### 0xb. 按用户指定顺序完成三项验证（性能→全量→人工验收）（本次会话）

**时间**：2026-04-12

**背景**：

1. 用户明确要求：先性能测试，再全量测试，最后人工验收。
2. 全程要求后台独立进程方式执行，并同步记录结果。

**本次实际动作**：

1. 性能测试（先执行）：
   - 启动后台服务：`tmp_run_server.py`
   - 采样脚本：`tmp_benchmark_extract.py`
   - 样本：`HeatherWatson9399@outlook.com`、`KimMyers4896@outlook.com` 各 3 次
   - 结果：`avg=6137.83ms`、`min=4368.63ms`、`max=8375.27ms`（6/6 样本 200）
   - 完成后停服务并复核 5000 端口。
2. 全量测试（第二步）：
   - `pytest -q` 后台执行
   - 结果：`1018 passed, 9 skipped in 386.35s`
3. 人工验收（第三步）：
   - 脚本：`tests/verify_verification_ai_endpoints.py`
   - 结果：6/6 步骤通过（登录、settings、csrf、ai-test、accounts、extract）
   - 提取接口返回：`status=200`、`success=true`
   - 完成后停服务并复核 5000 端口无监听。

**过程问题与处理**：

1. 首次人工验收因服务未成功驻留触发连接拒绝；
2. 立即按同流程重启后台服务并重跑，第二次成功。

**文档同步**：

1. FD 增补：`9.7 按用户指定顺序的三项验证`。
2. TD 增补：`9.7 三阶段执行结果回填`。
3. TDD 增补：`15.8 用户指定顺序验证回填`。

### 0xc. 会话续跑：清理临时脚本 + 启动 AI 配置联调环境（本次会话）

**时间**：2026-04-12

**背景**：

1. 用户选择“清理临时脚本并保留文档更新”。
2. 用户要求随后启动服务，由其手工配置 AI 模型并观察效果。

**本次实际动作**：

1. 删除临时脚本：
   - `tmp_benchmark_extract.py`
   - `tmp_run_server.py`
2. 为满足用户后续配置需要，按后台独立进程重新启动 `dev` 服务单实例。
3. 运行态确认：`127.0.0.1:5000` 监听正常。

**文档同步**：

1. FD 增补：`9.8 会话续跑：清理临时脚本并为 AI 配置留出运行环境`。
2. TD 增补：`9.8 会话续跑：AI 配置联调准备`。
3. TDD 增补：`15.9 会话续跑记录（AI 配置前置环境）`。

### 0xd. AI 配置完成后的性能复测（本次会话）

**时间**：2026-04-12

**背景**：

1. 用户已完成 AI 模型相关配置。
2. 用户要求立即重跑性能测试，并同步文档与工作记录。

**本次实际动作**：

1. 复测前确认服务已在 `dev` 分支运行（5000 端口监听）。
2. 重新执行 6 次采样（2 账号 × 3 次）：
   - `HeatherWatson9399@outlook.com`: 3795.02 / 4337.85 / 8278.73 ms
   - `KimMyers4896@outlook.com`: 3920.99 / 4648.93 / 7326.86 ms
3. 统计结果：
   - `avg=5384.73ms`
   - `min=3795.02ms`
   - `max=8278.73ms`
   - 全部样本 `status=200`
4. 与同会话 AI 配置前采样（`avg=6137.83ms`）对比：平均下降约 **12.3%**。

**结论**：

1. AI 配置后本轮样本表现优于配置前，最佳样本进入 4s 内。
2. 长尾仍存在（8s+），后续需扩样验证稳定性。

**文档同步**：

1. FD 增补：`9.9 AI 配置后性能复测`。
2. TD 增补：`9.9 AI 配置后性能复测结果`。
3. TDD 增补：`15.10 AI 配置后性能复测回填`。

### 0xe. AI 配置后全量稳定性复测（本次会话）

**时间**：2026-04-12

**背景**：

1. 用户在 AI 配置后要求再跑一轮全量测试验证稳定性。

**本次实际动作**：

1. 后台执行 `pytest -q`。
2. 结果：`1018 passed, 9 skipped in 395.42s (0:06:35)`。
3. stderr 为空，未出现新增失败。

**结论**：

1. AI 配置后未引入全量回归。
2. 当前可继续进行后续人工验收或提交前检查。

**文档同步**：

1. FD 增补：`9.10 AI 配置后全量稳定性复测`。
2. TD 增补：`9.10 AI 配置后全量验证`。
3. TDD 增补：`15.11 AI 配置后全量测试回填`。

### 0xf. AI 配置后人工验收复跑（本次会话）

**时间**：2026-04-12

**背景**：

1. 在“性能复测 + 全量复测”之后，用户要求继续执行人工验收并同步文档。

**本次实际动作**：

1. 在现有运行态服务上执行：`tests/verify_verification_ai_endpoints.py`。
2. 验收结果：
   - 6/6 步骤全部通过；
   - `stderr` 空。
3. 关键输出：
   - AI 探测：`connectivity_ok=true`、`contract_ok=true`；
   - 提取接口：`status=200`、`success=true`。

**补充观察**：

1. settings 输出中 `verification_ai_enabled=false`；
2. 但 AI 探测链路已通过，说明连通性与配置开关是独立状态。

**文档同步**：

1. FD 增补：`9.11 AI 配置后人工验收复跑`。
2. TD 增补：`9.11 AI 配置后人工验收结果`。
3. TDD 增补：`15.12 AI 配置后人工验收回填`。

### 0x. 性能优化真实环境 A/B 对照（main vs dev-5.3Codex）+ 文档回填（本次会话）

**时间**：2026-04-12

**背景**：

1. 用户要求确认“优化是否真实有效”，而不是只看单元测试通过。
2. 用户明确要求：
   - 代码使用 `dev-5.3Codex`；
   - 数据库复用 `main` 侧真实库；
   - 启动方式仅允许后台独立进程，不允许前台阻塞式运行。

**本次实际动作**：

1. 运行环境统一：
   - 配置来源：`E:\hushaokang\Data-code\outlookEmail\.env`
   - 数据库：`E:\hushaokang\Data-code\outlookEmail\data\outlook_accounts.db`
   - 端口：`5000`
   - 变量：`PERF_LOGGING=true`、`SCHEDULER_AUTOSTART=false`
2. A/B 对照执行（同账号、同接口、同数据库）：
   - 接口：`GET /api/emails/{email}/extract-verification`
   - 账号：`HeatherWatson9399@outlook.com`、`KimMyers4896@outlook.com`
   - each 分支各 6 次样本
3. 日志验证：
   - 成功读取 `[PERF] extract_verification | ... | 总耗时=...ms`
   - 确认性能埋点代码仍存在，并未丢失。

**A/B 结果摘要**：

| 分支 | 样本量 | 平均值 | 最小值 | 最大值 |
|------|--------|--------|--------|--------|
| main | 6 | 6910ms | 5141ms | 9208ms |
| dev-5.3Codex | 6 | 5309ms | 4220ms | 8109ms |

**结论**：

1. 优化有效：平均耗时下降约 **23.2%**。
2. 但当前仍未稳定达到 `≤4s`（best 约 4.22s，存在 8s+ 长尾）。
3. 当前判断应为：**“策略有效，但尚未完全达标”**。

**本次同步更新文档**：

| 文件 | 变更 |
|------|------|
| `docs/FD/2026-04-11-邮件获取性能优化FD.md` | 升级 v1.2，新增“实测状态回填（2026-04-12）” |
| `docs/TD/2026-04-11-邮件获取性能优化TD.md` | 升级 v1.1，新增“实测对照记录（2026-04-12）” |
| `docs/TDD/2026-04-11-邮件获取性能优化-TDD.md` | 升级 v1.2，新增“真实环境 A/B 性能对照补充” |

---

### 0y. 新增单策略 PRD：Graph Top-N 下调（本次会话）

**时间**：2026-04-12

**背景**：

1. 用户确认“可以单独做第三点策略”（Graph 列表窗口下调）。
2. 目标是在不引入高风险行为变更前提下继续压缩提取耗时。

**本次实际动作**：

1. 新建独立 PRD：
   - `docs/PRD/2026-04-12-验证码提取提速P0-GraphTopN策略PRD.md`
2. PRD 明确内容：
   - 范围仅覆盖 Top-N 策略
   - 固定值 `top=3`（不做配置化）
   - 不改对外接口契约
   - 风险（漏检概率）与回滚（改回 20）
   - 验收指标（成功率/NOT_FOUND 比例/P50-P95）

**结论**：

1. 该策略复杂度低、改造边界清晰，适合作为下一步 P0 低风险增量。
2. 后续可在同一 A/B 口径下再次验证增益并回填 FD/TD/TDD。

### 0z. Top-N 策略落地（固定 top=3，非配置化）

**时间**：2026-04-12

**背景**：用户确认“不需要可配置，直接固定为 3”。

**本次实际动作**：

1. 代码改动：
   - 文件：`outlook_web/services/verification_channel_routing.py`
   - 新增常量：`VERIFICATION_FETCH_TOP = 3`
   - 统一链路调用处由 `top=20` 改为 `top=VERIFICATION_FETCH_TOP`
2. 文档联动：
   - 更新 PRD：`docs/PRD/2026-04-12-验证码提取提速P0-GraphTopN策略PRD.md`
     - 从“可配置化”改为“固定 top=3”
   - 更新 FD/TD/TDD：补充本会话决议与后续验证项

**结论**：

1. 该改动为小范围低复杂度变更。
2. 下一步执行针对性回归 + 实测采样，确认是否进一步降低平均耗时和长尾。

**执行结果回填（同日）**：

1. 回归：`python -m unittest tests.test_verification_channel_memory_v1 tests.test_external_api.ExternalApiVerificationErrorTests tests.test_web_graph_auth_fallback tests.test_extract_verification_group_policy` → 22/22 通过。
2. 真实采样（固定 top=3）出现多次 `404`，且平均耗时上升至约 10s+，长尾达 20s 级。
3. 结论：固定 `top=3` 不满足当前上线条件，需暂缓并回退/改方案。

---

## 2026-04-11

### 0x. PR #36 分析 → 性能埋点 → AUTH_EXPIRED Bug 修复（本次会话）

**时间**：2026-04-11

**背景**：用户要求分析 PR #36（EucalyZ/outlookEmailPlus:dev → ZeroPointSix/outlookEmailPlus:main），判断是否应合并。

**本次实际动作**：

1. **PR #36 分析与拒绝**：
   - 分析发现 6 个关键问题、4 个中等问题（SSE 缺少 account_type 路由、无界缓存、XSS 风险等）
   - 向 PR 提交拒绝评论（issuecomment-4229331624）
   - 创建内部优化 PRD: `docs/PRD/2026-04-11-邮件获取性能优化PRD.md`（v1.1）

2. **全链路性能埋点**（commit `1dba74c`）：
   - 在 `outlook_web/controllers/emails.py` 添加 72 行 `[PERF]` 性能埋点
   - 覆盖 `api_get_emails`、`api_get_email_detail`、`api_extract_verification` 三个核心函数
   - 在 `outlook_web/services/imap.py` 添加 IMAP SEARCH/FETCH/结果诊断日志

3. **发现并修复 AUTH_EXPIRED Bug**：
   - **问题**：`extract_verification` 在收件箱为空时误报 `ACCOUNT_AUTH_EXPIRED`（401），实际应返回 `EMAIL_NOT_FOUND`（404）
   - **根因**：IMAP 连接成功但返回空邮件时，`graph_auth_expired` 标志"污染"了最终错误判断
   - **修复**：增加 `imap_connected` 追踪，仅当 Graph 和 IMAP 都失败时才报 AUTH_EXPIRED
   - **日志证据**：`imap_search | total=0 (空信箱)` + `imap_new | success=True | count=0` → 误报 AUTH_EXPIRED
   - **BUG 文档**：`docs/BUG/2026-04-11-验证码提取-空信箱误报AUTH_EXPIRED-BUG.md`

4. **PERF 日志生产环境控制**：
   - 所有 `[PERF]` 日志从 `INFO` 降级为 `DEBUG`
   - 新增 `PERF_LOGGING=true` 环境变量控制（`outlook_web/app.py`）
   - 生产环境默认不输出，开发时设置环境变量即可开启

**修改文件清单**：
| 文件 | 变更 |
|------|------|
| `outlook_web/controllers/emails.py` | 性能埋点 + `imap_connected` Bug 修复 + 日志 DEBUG 降级 |
| `outlook_web/services/imap.py` | IMAP 搜索/FETCH 诊断日志 |
| `outlook_web/app.py` | `PERF_LOGGING` 环境变量支持 |
| `docs/PRD/2026-04-11-邮件获取性能优化PRD.md` | 性能优化 PRD v1.2（加入实测数据 + IMAP 连接复用 P0） |
| `docs/BUG/2026-04-11-验证码提取-空信箱误报AUTH_EXPIRED-BUG.md` | Bug 分析文档 |

**性能数据摘要**（从日志采集）：

| 账号场景 | 链路 | 耗时 | 备注 |
|----------|------|------|------|
| Terrance (preferred_channel=imap_new) | IMAP fetch + IMAP detail | 8.5-9.7s | 最优路径 |
| Troy (无 preferred_channel) | Graph×2 + IMAP×2 + detail IMAP | 15.5s | 完整回退链 |
| Laurie (全部失败) | Graph×2 + IMAP×2 | 14.5s | 账号失效 |

**下一步**：性能优化（IMAP 连接 4-5s 是主要瓶颈）

5. **PRD v1.2 更新**（续 session）：
   - 加入实测 `[PERF]` 埋点数据，标注已完成的 P0 项（渠道记忆 `21298b6`、IMAP 回退 `ed48929`）
   - 新增 3.1.2 "IMAP 连接复用"（从 Out of Scope 升级为 P0，最大单点收益 ~4-5s）
   - 新增 3.1.3 "IMAP OAuth Token 短期缓存"
   - 优先级矩阵加入"状态"列，区分已完成/待实施
   - 更新预期优化效果表：验证码提取目标从 8.5s → 4s

6. **PRD v1.3 + FD v1.0**（续 session）：
   - 分析 Web 端 vs 外部 API 验证码提取路径差异（600 行 vs 130 行）
   - 确认方案 B：统一两条路径（重构 + 优化一起做）
   - PRD v1.3 新增 3.1.0 "验证码提取路径统一"重构前置需求
   - 创建 FD: `docs/FD/2026-04-11-邮件获取性能优化FD.md`（v1.0）
   - FD 覆盖：路径统一 + 6 项性能优化的系统行为设计、接口契约、文件清单
   - 更新预期优化效果表：验证码提取目标从 8.5s → 4s

7. **TDD v1.0 + 43 测试用例**（续 session）：
   - 深度分析全部 6+ 验证码提取入口的行为差异
   - 发现 3 个关键行为不一致：`apply_confidence_gate`（Web 缺失）、`enforce_mutual_exclusion`（Web=True/External=False）、filter 能力差异
   - 创建 TDD: `docs/TDD/2026-04-11-邮件获取性能优化-TDD.md`（v1.0）
   - 创建 6 个测试文件共 43 个测试用例（TDD red phase）：
     - `tests/test_imap_token_cache.py` — A 层：8 cases
     - `tests/test_graph_permission_precheck.py` — B 层：9 cases
     - `tests/test_imap_connection_reuse.py` — C 层：7 cases
     - `tests/test_channel_capability_cache.py` — D 层：8 cases
     - `tests/test_imap_batch_fetch.py` — E 层：5 cases
     - `tests/test_imap_concurrent_servers.py` — F 层：6 cases

8. **TD v1.0 技术设计**（续 session）：
   - 创建 TD: `docs/TD/2026-04-11-邮件获取性能优化TD.md`（v1.0）
   - 覆盖 7 项核心技术决策（统一函数位置、连接复用粒度、Token 缓存作用域、通道缓存独立模块、批量 FETCH 解析、并发取消策略）
   - 详细设计：统一入口函数签名与伪代码、IMAP 组合函数、Token 缓存线程安全、Graph scope 解析、通道缓存模块、批量 FETCH 响应解析、并发双服务器竞速
   - 三阶段实施顺序：Phase 1 基础设施 → Phase 2 IMAP 优化 → Phase 3 路径统一
   - 兼容性/回滚/降级策略分析

**新增文件清单（7-8 步）**：
| 文件 | 变更 |
|------|------|
| `docs/TDD/2026-04-11-邮件获取性能优化-TDD.md` | 测试设计文档 v1.0 |
| `docs/TD/2026-04-11-邮件获取性能优化TD.md` | 技术设计文档 v1.0 |
| `tests/test_imap_token_cache.py` | Token 缓存测试（8 cases） |
| `tests/test_graph_permission_precheck.py` | Graph 权限预检测试（9 cases） |
| `tests/test_imap_connection_reuse.py` | IMAP 连接复用测试（7 cases） |
| `tests/test_channel_capability_cache.py` | 通道能力缓存测试（8 cases） |
| `tests/test_imap_batch_fetch.py` | 批量 FETCH 测试（5 cases） |
| `tests/test_imap_concurrent_servers.py` | 并发双服务器测试（6 cases） |

9. **四文档联调对齐**（续 session）：
   - 发现并修复 6 项文档间不一致：
     - TDD B层矩阵缺 3 个用例（G-07/G-08/G-09） → 补齐至 9 cases
     - TDD C层 R-04 用例名与实际测试不一致 → 更名为 `test_token_failure_no_connection`
     - TDD D层矩阵缺 C-08（`test_filter_no_cache_returns_all`） → 补齐至 8 cases
     - TDD F层 P-05/P-06 用例名与实际测试不一致 → 更名匹配
     - FD 缺少 TD/TDD 关联引用 → 补充
     - FD 缺少行为变更说明（`apply_confidence_gate`/`enforce_mutual_exclusion` 统一后的影响） → 补充
   - 四文档版本对齐：PRD v1.3 ← FD v1.1 ← TD v1.0 ← TDD v1.1
   - 四文档交叉引用补全

**文档联调变更清单**：
| 文件 | 变更 |
|------|------|
| `docs/PRD/2026-04-11-邮件获取性能优化PRD.md` | 补充 FD/TD/TDD 关联引用 |
| `docs/FD/2026-04-11-邮件获取性能优化FD.md` | v1.0→v1.1：补 TD/TDD 引用、增行为变更说明 |
| `docs/TDD/2026-04-11-邮件获取性能优化-TDD.md` | v1.0→v1.1：补 TD 引用、同步测试矩阵与实际文件 |
| `docs/TD/2026-04-11-邮件获取性能优化TD.md` | 更新关联版本号 FD v1.1/TDD v1.1 |

### 0w. 按用户要求执行全量回归 + 提交前文档对齐（本次会话）

**时间**：2026-04-11

**背景**：用户要求“先跑全量测试，若无问题准备本地提交”，并明确要求将本轮操作同步到文档。

**本次实际动作**：

1. 执行全量测试：
   - 命令：`python -m unittest discover -s tests -v`
   - 结果：`Ran 984 tests in 196.747s`，`OK (skipped=7)`。

2. 工作区变更盘点（提交前）：
   - 业务代码：`outlook_web/controllers/emails.py`、`outlook_web/services/{external_api.py,temp_mail_service.py,verification_extractor.py}`
   - 测试：`tests/test_ai_fallback_trigger_condition.py`、`tests/test_external_api.py`、`tests/test_verification_ai_json_contract.py`、`tests/test_verification_extractor_options.py`、`tests/test_web_graph_auth_fallback.py`
   - 文档：`WORKSPACE.md`、`docs/TODO/2026-04-10-验证码提取提速与AI增强TODO.md`

3. 提交策略确认：
   - 已与用户确认采用“两次提交”：
     1) 代码 + 测试
     2) 文档

**结论**：

1. 当前代码基线在全量回归下稳定可提交。
2. 本条目用于锁定“先验证后提交”的操作证据，避免后续追溯缺失。

### 0u. 手工排查补记：验证码返回“code+link”与性能慢的现场定位（本次会话）

**时间**：2026-04-11

**用户现场反馈**：

1. Web 提取接口仍返回 `1181 + 链接`（期望 web 只返回 code）。
2. 提取接口体感较慢。
3. 要求基于当前真实数据直接调用接口验证，并将过程同步到文档。

**本次实际排查动作**：

1. 全量回归复核：
   - 执行 `python -m unittest discover -s tests -v`
   - 结果：`Ran 984 tests in 186.955s`，`OK (skipped=7)`。

2. 真实数据直连接口验证（初次）：
   - 账号样本：`SophiaClark1205@outlook.com`、`JessicaReynolds3096@outlook.com`
   - `/api/emails/<email>/extract-verification` 返回 `verification_code=1181` 且 `verification_link` 非空。
   - 单次耗时约 `5.7s`～`10.0s`。

3. 关键根因定位（运行态而非代码逻辑）：
   - 发现本机 **两个** `python web_outlook_app.py` 进程同时监听 `:5000`（PID `26524`、`46048`）。
   - 这是典型“旧进程残留 + 新进程并存”场景，会导致请求命中旧代码版本，出现“看起来没生效”的现象。

4. 修复与复测：
   - 强制停止全部 `web_outlook_app.py` 进程后，只启动单实例（PID `45152`）。
   - 复测同一账号：
     - `verification_code=1181`
     - `verification_link=None`
     - `formatted=1181`
   - 行为与“web 互斥（有 code 不返 link）”一致。
   - 复测耗时约 `7.3s`（仍偏慢，但已排除“旧代码未生效”问题）。

5. external 现场说明：
   - 当前数据中 `external_api_key` 未配置（legacy_key_set=false，multi_keys=0），
     因此本轮先完成 web 真实链路验证；external 需先配置 key 才能做同口径实测。

**当前结论**：

1. “web 仍返回 code+link”并非新逻辑无效，根因是本地双进程监听同端口导致命中旧实例。
2. 单实例重启后，web 互斥行为已按预期生效。
3. 体感慢主要仍在上游读取链路（Graph/IMAP 回退），不是本次互斥收口逻辑造成。

### 0v. 本地镜像构建与容器实测（本次会话）

**时间**：2026-04-11

**背景**：用户要求本地构建镜像并进行容器化验证。

**本次实际操作**：

1. Docker 运行态检查：
   - 初始 `docker version` 无法连接 daemon；经用户手动拉起 Docker Desktop 后恢复正常。

2. 本地镜像构建：
   - 命令：`docker build -t outlook-email-plus:local-20260411 .`
   - 结果：构建成功，镜像 ID `8d84bb870e21`，大小约 `170MB`。

3. 容器首跑问题与修复：
   - 首次 `docker run` 启动失败，日志报 `sqlite3.OperationalError: disk I/O error`。
   - 根因：宿主机本地进程占用同一 `data/outlook_accounts.db` 挂载文件。
   - 处理：停止宿主机 `web_outlook_app.py` 进程后重启容器。

4. 容器成功启动与功能实测：
   - 容器名：`outlook-email-plus-local-test`
   - 端口映射：`5002 -> 5000`
   - 状态：`Up (healthy)`
   - `/healthz`：200
   - 登录：200
   - 真实账号提取接口复测：
     - `GET /api/emails/SophiaClark1205@outlook.com/extract-verification?code_source=all`
     - 返回：`code=1181, link=None, formatted=1181`
     - 耗时：约 `9.97s`

**结论**：

1. 本地镜像可成功构建并正常容器化运行。
2. 容器内行为与当前代码一致（web 互斥生效：有 code 不返 link）。
3. 耗时仍主要受上游读取链路影响，未见镜像化引入额外语义偏差。


### 0t. AI fallback 触发条件收紧：方案 A（任一 high 即跳过 AI）

**时间**：2026-04-11

**背景**：上一轮排查发现 `enhance_verification_with_ai_fallback()` 的触发条件过于宽泛——只要 code 或 link 任一字段低置信就会触发 AI 调用。这导致"验证码已高置信命中，但因为链接低置信，仍然会打 AI"的浪费。

**用户决策**：采用方案 A——任一字段高置信即跳过 AI，对外仍保留 `verification_code`/`verification_link` 双字段结构。

**本次代码改动（已完成）**：

1. 文件：`outlook_web/services/verification_extractor.py`
   - `enhance_verification_with_ai_fallback()` 触发条件从 `if not needs_ai_code and not needs_ai_link` 改为 `if code_confidence == "high" or link_confidence == "high": return result`
   - 因为只有 both-low 才会进入 AI 分支，`needs_ai_code`/`needs_ai_link` 不再需要，移除条件守卫
   - 对外 API 返回结构（`verification_code`/`verification_link`/`formatted`）不变

2. 新增测试文件：`tests/test_ai_fallback_trigger_condition.py`（12 用例）
   - `AiFallbackTriggerConditionTests`：8 个用例覆盖核心触发逻辑
     - code=high + link=high → 不触发 AI
     - code=high + link=low → 不触发 AI
     - code=low + link=high → 不触发 AI
     - code=low + link=low → 触发 AI
     - AI 关闭 → 不触发
     - AI 配置不完整 → 不触发
     - AI 返回 None → 回退规则
     - AI 返回空 → 回退规则
   - `AiFallbackEdgeCaseTests`：4 个边界用例
     - confidence 字段缺失默认 low
     - 空 extracted 触发 AI
     - link_confidence 缺失但 code=high → 不触发

**全量回归结果**：

1. 执行命令：`python -m unittest discover -s tests 2>&1`
2. 结果：`Ran 967 tests in 204.140s`，`OK (skipped=7)`，0 failures。

**文档同步**：

1. `CHANGELOG.md`：补充 AI fallback 触发条件收紧说明。

---

### 0n. 邮件通知测试接口 502 回归修复 + 文档实况同步（本次会话补记）

**时间**：2026-04-11

**背景**：上一轮全量测试出现 2 个失败用例，均指向 `/api/settings/email-test` 返回 502。

**本次排查结论**：

1. 失败可稳定复现于：
   - `tests.test_notification_dispatch.NotificationDispatchTests.test_email_test_endpoint_sends_real_message_via_saved_recipient`
   - `tests.test_v190_i18n_email_notification_tdd.V190ApiContractRedTests.test_t_api_007_email_test_success_uses_saved_recipient_and_message_en`
2. 根因不是接口逻辑主链路错误，而是 SMTP 传输模式冲突：
   - 测试场景端口为 `587`（应走 STARTTLS）
   - 运行环境残留 `EMAIL_NOTIFICATION_SMTP_USE_SSL=true`
   - 导致走到 `SMTP_SSL` 分支并触发发送异常，最终映射为 `EMAIL_TEST_SEND_FAILED`（502）

**本次代码修复（已完成）**：

1. 文件：`outlook_web/services/email_push.py`
2. 新增 `_normalize_smtp_transport_mode(...)` 规范化逻辑：
   - 端口 `587`：强制 `use_tls=true`、`use_ssl=false`
   - 端口 `465`：强制 `use_ssl=true`、`use_tls=false`
   - 其他端口若 `TLS+SSL` 同时为 true：优先保留 SSL，关闭 TLS
3. 在 `get_email_push_service_config()` 中统一调用该规范化函数，避免环境残留造成模式冲突。

**新增测试（已完成）**：

1. 新增 `tests/test_email_push_transport_mode.py`（3 用例）覆盖：
   - 587 端口冲突自动纠正
   - 465 端口冲突自动纠正
   - 非标准端口双开时兜底优先级
2. 失败用例复跑通过（2/2）。

**本轮验证结果**：

1. 通知相关回归：`python -m unittest tests.test_notification_dispatch tests.test_v190_i18n_email_notification_tdd -v` → **44 passed**。
2. 全量回归：`python -m unittest discover -s tests -v` → `Ran 952 tests in 309.437s`，`OK (skipped=7)`。

**文档同步**：

1. `CHANGELOG.md`：补充 SMTP 传输模式冲突修复说明。
2. `docs/TODO/2026-04-10-验证码提取提速与AI增强TODO.md`：补记本轮回归修复与全量转绿结论。

#### 0o. 按用户要求再次执行全量测试（本次会话补记）

**时间**：2026-04-11

**背景**：用户要求“继续全量测试”。

**执行结果**：

1. 执行命令：`python -m unittest discover -s tests -v`
2. 结果：`Ran 955 tests in 301.981s`，`OK (skipped=7)`。

**结论**：

- 当前工作区在本轮 SMTP 传输模式修复后，全量回归继续保持通过状态。

#### 0p. 验证码提取端到端人工验收（本次会话补记）

**时间**：2026-04-11

**背景**：用户要求立即执行一次验证码提取 E2E 人工验收。

**执行方式**：

1. 脚本：`python tests/verify_verification_ai_endpoints.py`
2. 流程覆盖：
   - 登录
   - 读取系统级 AI 配置（`/api/settings`）
   - 获取 CSRF（`/api/csrf-token`）
   - AI 探测（`/api/settings/verification-ai-test`）
   - 读取账号列表
   - 执行提取（`/api/emails/<email>/extract-verification`）

**关键结果**：

1. AI 探测：`status=200`，`ok=true`，`connectivity_ok=true`，`contract_ok=true`。
2. 目标账号：`[REDACTED]`（脚本自动选取首个账号）。
3. 提取接口：`status=200`，`success=true`，返回了 `verification_code` 与 `verification_link`。

**结论**：

- 当前运行态下，验证码提取端到端链路可用，满足人工验收的核心路径要求。

#### 0q. 按用户要求追加 3 账号抽样 + External E2E（本次会话补记）

**时间**：2026-04-11

**背景**：用户要求继续做端到端抽样，并补做 External 验证码接口验收。

**执行动作**：

1. Web E2E 抽样（3 账号）：
   - `[REDACTED-1]`
   - `[REDACTED-2]`
   - `[REDACTED-3]`
2. External E2E：
   - 先检查配置，发现当前环境无已配置 External API Key（`external_api_key_set=false`）。
   - 按用户授权临时写入测试 key（`[REDACTED-KEY]`）执行接口验收。
   - 验收后恢复为原状态（清空 key）。

**结果**：

1. Web E2E：
   - 前 2 个账号：`HTTP 200 + success=true`，返回 code/link；
   - 第 3 个账号：`HTTP 502 + IMAP_CONNECT_FAILED`（历史已知连通问题）。
2. External E2E（3 账号）：
   - `/api/external/verification-code`：`404 + VERIFICATION_CODE_NOT_FOUND`
   - `/api/external/verification-link`：`404 + VERIFICATION_LINK_NOT_FOUND`
   - 错误码与接口语义稳定，且恢复配置后系统状态回到执行前。

**结论**：

- 本轮 External E2E 已完成链路级验收（鉴权→查询→稳定错误语义），当前样本邮箱在 external 条件下未命中验证码/链接属于数据层结果，不是接口异常。

#### 0r. 按用户要求清理敏感痕迹并重做验收（本次会话补记）

**时间**：2026-04-11

**背景**：用户明确要求仅允许使用 Outlook/Hotmail 账号进行人工验收，并删除此前非目标账号痕迹。

**执行动作**：

1. 文档清理：
   - 将会话文档中的具体非目标账号与临时测试 key 全部替换为 `[REDACTED]` 占位。
2. 仅限目标范围重测：
   - 重新筛选账号，仅保留 provider 为 Outlook/Hotmail 的样本进行 E2E 抽样。
   - 对抽样账号执行 `extract-verification` 验收。

**重测结果**：

1. Outlook/Hotmail 抽样结果均为：`HTTP 200 + success=true`。
2. 均可提取到验证码与链接（链路可用）。

**结论**：

- 已按用户要求完成敏感痕迹清理与范围纠偏，后续人工验收仅使用 Outlook/Hotmail 账号。

#### 0s. Outlook/Hotmail 再扩样 3 账号验收（本次会话补记）

**时间**：2026-04-11

**背景**：用户要求在范围纠偏后继续扩样验证（仅 Outlook/Hotmail）。

**执行动作**：

1. 从账号列表筛选 provider 为 Outlook/Hotmail（含邮箱后缀兜底判断）。
2. 取前 3 个样本执行 `GET /api/emails/<email>/extract-verification?code_source=all`。

**结果**：

1. 3/3 样本均 `HTTP 200 + success=true`。
2. 3/3 均提取到验证码与链接。
3. 本轮样本 `ai_used` 未触发（规则路径已命中，符合“规则优先”设计）。

**结论**：

- 在用户限定的 Outlook/Hotmail 范围内，端到端提取链路稳定可用。

---

## 2026-04-10

### 0e. 新增“验证码 AI 配置可用性探测”闭环（本次会话补记）

**时间**：2026-04-11

**背景**：用户要求“重点根据当前配置先验证 AI 验证码能力是否真的可行”，不仅是保存配置。

**本次实际代码改动（已完成）**：

1. **后端新增探测接口（仅测已保存配置）**
   - 文件：`outlook_web/controllers/settings.py`, `outlook_web/routes/settings.py`
   - 新增路由：`POST /api/settings/verification-ai-test`
   - 行为：
     - 从 settings repository 读取已保存的系统级 AI 配置（enabled/base_url/api_key/model）
     - 调用 `probe_verification_ai_runtime(...)` 执行主动探测
     - 返回结构化结果：`success/ok/enabled/probe`
     - 记录审计日志：`verification_ai_test`

2. **前端新增测试入口（Basic Tab）**
   - 文件：`templates/index.html`, `static/js/main.js`
   - 在“验证码 AI 增强”区域新增：
     - 按钮：`#btnTestVerificationAi`
     - 结果区：`#verificationAiTestResult`
   - 新增函数：`testVerificationAiConfig()`
     - 调用 `/api/settings/verification-ai-test`
     - 在页面内展示可用性结论与关键信息（如 latency/code/confidence）

3. **自动化测试补齐**
   - 新增：
     - `tests/test_settings_verification_ai_probe.py`（后端接口）
     - `tests/test_settings_verification_ai_probe_frontend.py`（前端契约）
   - 执行结果：
     - `python -m unittest tests.test_settings_verification_ai_probe tests.test_settings_verification_ai_config -v` → **6 passed**
     - `python -m unittest tests.test_settings_verification_ai_probe_frontend -v` → **2 passed**

4. **文档同步**
   - `CHANGELOG.md`：新增“验证码 AI 配置可用性探测（settings）”小节

**当前状态结论**：

- “已保存配置是否可用”现在可在设置页一键验证，能更直接判断 AI 验证码能力是否可行。
- 探测失败场景可返回明确错误类别，便于定位配置/网络/契约问题。

#### 0f. 探测口径调整：连通性优先（本次会话补记）

**时间**：2026-04-11

**背景**：用户明确“作为测试只需要正常返回 200 即可”，测试目标优先验证连通性。

**本次调整**：

1. `POST /api/settings/verification-ai-test` 返回口径调整：
   - `ok`：连通性优先（HTTP 2xx 即 `true`）
   - `connectivity_ok`：是否 2xx
   - `contract_ok`：是否满足固定 JSON 契约
2. 前端结果文案同步：
   - 连通成功但契约不通过时，显示“连通正常 + 契约提示”，不再判定为整体失败。
3. 测试补齐：
   - 新增“连通成功但契约无效仍应 ok=true”用例并通过。

**本地实测（当前配置）**：

- 上游返回 HTTP 200；模型 `Qwen/Qwen3-14B` 响应 `choices=null`。
- 在新口径下结果为：`ok=true`、`connectivity_ok=true`、`contract_ok=false`，满足“连通性测试通过”的目标。

#### 0g. 重启后 E2E 复测与问题定位（本次会话补记）

**时间**：2026-04-11

**执行背景**：按用户要求“重启服务后重新做验证码提取端到端验证”，并定位“AI 测试提示缺少 choices 字段”的根因。

**本次实际操作**：

1. 服务重启与健康检查：
   - 清理旧 `python web_outlook_app.py/start.py` 进程
   - 重新启动 `python web_outlook_app.py`
   - `/healthz` 返回正常（重启成功）

2. 配置探测（已保存配置）：
   - `POST /api/settings/verification-ai-test`（携带 CSRF）
   - 结果：
     - `ok=true`
     - `connectivity_ok=true`
     - `contract_ok=false`
     - `probe_error=invalid_response_format`
     - `probe_message=AI 响应缺少 choices 字段`
   - 说明：连通性达标，但模型返回结构不满足当前契约解析要求。

3. 验证码提取 E2E 抽样（前 8 账号）：
   - 7 个账号：`HTTP 200 + success=true`
   - 1 个账号（`[REDACTED]`）：超时/连接失败
   - 多数返回 `confidence=low`，`ai_used=null`

4. 失败账号复测与定位：
   - 关闭环境代理后复测同账号，返回：`IMAP_CONNECT_FAILED`（WinError 10060）
   - 结论：该账号问题属于 IMAP 网络连通性，不是验证码提取逻辑回归。

**问题定位结论**：

1. “AI 探测报 choices 问题”来源于上游模型响应格式（`choices=null`），不是本地请求未发出。
2. “E2E 中 ai_used 为空”与上面一致：AI fallback 被触发后未通过契约校验，按设计快速回退规则结果。
3. E2E 主链路整体可用；单账号失败由 IMAP 连通性导致。

#### 0h. OpenAI 兼容格式探测脚本与实测结论（本次会话补记）

**时间**：2026-04-11

**背景**：用户要求确认“OpenAI 兼容格式是否可指定返回格式”，并定位当前模型为何返回 `choices` 问题。

**本次新增脚本**：

1. `tests/verify_verification_ai_endpoints.py`
   - 串行调用：`/api/settings`、`/api/csrf-token`、`/api/settings/verification-ai-test`、`/api/accounts`、`/api/emails/<email>/extract-verification`
   - 用于手工联调时完整观察返回体。
2. `tests/verify_openai_compatible_response_format.py`
   - 对同一 OpenAI 兼容端点分别测试：
     - `response_format={"type":"json_object"}`
     - `response_format={"type":"json_schema", ...}`
     - 不带 `response_format`
     - `tools + tool_choice`

**实测结论**：

1. `Qwen/Qwen3-14B`（当前配置）在四种请求下均返回 `HTTP 200`，但 `choices=null`。
   - 说明并非本地请求体字段问题（`response_format/tools` 均未改变该行为）。
2. `deepseek-ai/DeepSeek-V3.2` 在同端点可返回标准 `choices` 列表。
   - 且对 `json_schema`/`tools` 请求均有结构化响应。
3. 因此当前“缺少 choices”根因更偏向**模型/供应商实现差异**，不是我方是否设置 `response_format`。

#### 0i. 临时切换 DeepSeek 复测（本次会话补记）

**时间**：2026-04-11

**操作**：按用户要求临时将 `verification_ai_model` 切换为 `deepseek-ai/DeepSeek-V3.2` 后复测，再恢复原模型。

**结果**：

1. 设置切换成功（`PUT /api/settings` 返回 200）。
2. `verification-ai-test` 结果：
   - `ok=true`
   - `connectivity_ok=true`
   - `contract_ok=false`
   - `probe_error=invalid_ai_output`
   - `response_preview` 显示 `confidence: 1.0`（数字）
3. E2E（`extract-verification`）抽样结果仍以规则结果为主，`ai_used` 仍为空。
4. 已将模型恢复为原值：`Qwen/Qwen3-14B`。

**结论**：

- DeepSeek 模型可返回 `choices`，但当前固定契约下（`confidence` 必须为 `high/low` 字符串）仍不通过，导致 AI 回退不生效。

#### 0j. AI 解析口径放宽（只要有 code/link 就接受）（本次会话补记）

**时间**：2026-04-11

**背景**：用户确认“最终只要返回验证码或验证链接即可，不需要严格卡 confidence/schema”。

**本次代码调整**：

1. 文件：`outlook_web/services/verification_extractor.py`
2. 调整 `_parse_verification_ai_content(...)` 解析策略：
   - 不再强制 `schema_version` 必须匹配
   - 不再强制 `verification_code/verification_link/confidence/reason` 的严格类型
   - 只要 `verification_code` 或 `verification_link` 任一可解析非空，即接受
   - `confidence` 支持数值/布尔/字符串，统一归一到 `high/low`
   - `reason` 非字符串时做兜底字符串化

**验证结果**：

1. 单元测试：
   - `tests.test_settings_verification_ai_probe`
   - `tests.test_verification_ai_json_contract`
   - 结果：通过
2. 重启服务后复测：
   - 临时切 `deepseek-ai/DeepSeek-V3.2` 时，`verification-ai-test` 结果变为：
     - `ok=true`
     - `connectivity_ok=true`
     - `contract_ok=true`
     - `parsed_output` 正常返回 code/link/confidence

**备注**：

- 对 `Qwen/Qwen3-14B`，若上游仍返回 `choices=null`，该问题依旧存在（无可解析内容）。

#### 0k. Qwen 模型列表筛选与端到端实测（本次会话补记）

**时间**：2026-04-11

**背景**：用户要求优先用千问模型并完成一次真实端到端验证。

**本次操作**：

1. 拉取模型列表并筛选 Qwen 候选（`/v1/models`）。
2. 对多个 Qwen 模型执行 `POST /api/settings/verification-ai-test` 探测。
3. 选定可通过契约的模型后执行端到端提取验证。

**探测结论**：

1. `Qwen/Qwen3-8B`、`Qwen/Qwen3-32B`、`Qwen/Qwen3-30B-A3B`：
   - 连通可达，但仍出现 `invalid_response_format`（choices 不可用）。
2. `Qwen/Qwen3-235B-A22B-Instruct-2507`、`Qwen/Qwen3-Coder-30B-A3B-Instruct`：
   - `connectivity_ok=true` 且 `contract_ok=true`。

**端到端实测（最终）**：

1. 将默认模型设置为：`Qwen/Qwen3-235B-A22B-Instruct-2507`。
2. `verification-ai-test` 返回成功，含 `parsed_output`。
3. 对 Outlook 账号抽样调用 `extract-verification`：
   - 全部 `HTTP 200 + success=true`
   - 其中至少 1 条结果出现 `ai_used=true`，证明 AI fallback 实际生效。

#### 0l. 按用户要求继续切换 Qwen 并复验（本次会话补记）

**时间**：2026-04-11

**本次动作**：

1. 再次拉取模型列表并批量探测多个 Qwen 候选：
   - `Qwen/Qwen3-14B`
   - `Qwen/Qwen3-8B`
   - `Qwen/Qwen3-32B`
   - `Qwen/Qwen3-30B-A3B`
   - `Qwen/Qwen3-235B-A22B`
   - `Qwen/Qwen3-235B-A22B-Instruct-2507`
   - `Qwen/Qwen3-Coder-30B-A3B-Instruct`
   - `Qwen/QVQ-72B-Preview`

2. 探测结论（verification-ai-test）：
   - 稳定可用：
     - `Qwen/Qwen3-235B-A22B-Instruct-2507`
     - `Qwen/Qwen3-Coder-30B-A3B-Instruct`
   - 不稳定（`choices` 不可用）：
     - `Qwen/Qwen3-14B`
     - `Qwen/Qwen3-8B`
     - `Qwen/Qwen3-32B`
     - `Qwen/Qwen3-30B-A3B`
   - 超时：
     - `Qwen/Qwen3-235B-A22B`
     - `Qwen/QVQ-72B-Preview`

3. 最终保留默认模型为：`Qwen/Qwen3-235B-A22B-Instruct-2507`，并再次执行 E2E 脚本确认：
   - `verification-ai-test`：`contract_ok=true`
   - `extract-verification`：`HTTP 200 + success=true`（链路稳定）

#### 0m. TODO 文档按实际实现回修 + 全量测试 + 服务就绪（本次会话补记）

**时间**：2026-04-11

**本次操作**：

1. 按当前真实实现回修：
   - `docs/TODO/2026-04-10-验证码提取提速与AI增强TODO.md`
   - 重点：
     - 将旧的分组级 AI 任务标注为“迁移到系统级 settings”
     - 补充 Phase 10（AI 探测与模型联调）
     - 补充 Phase 11（解析放宽与 E2E 复验）
     - 明确 `GROUP_AI_MODEL_REQUIRED` 不再是运行期主错误码
2. 按用户要求准备验证：
   - 执行全量测试（见本会话后续执行结果）
   - 确认服务保持可用，便于继续人工测试。

### 操作记录

#### 0. AI 配置系统级化 + 固定 JSON 契约（本轮代码落地）

**时间**：2026-04-10

**本次实际代码改动（已完成）**：

1. **settings 后端闭环**
   - 文件：`outlook_web/controllers/settings.py`
   - `GET /api/settings` 增加：
     - `verification_ai_enabled`
     - `verification_ai_base_url`
     - `verification_ai_model`
     - `verification_ai_api_key_set`
     - `verification_ai_api_key_masked`
   - `PUT /api/settings` 增加系统级 AI 保存逻辑：
     - `verification_ai_enabled/base_url/api_key/model`
     - API Key 加密存储、脱敏占位回写保护
     - 启用 AI 时完整性校验（缺项即返回 `VERIFICATION_AI_CONFIG_INCOMPLETE`）

2. **settings 前端闭环（Basic Tab）**
   - 文件：`templates/index.html`, `static/js/main.js`
   - 在“基础”Tab 新增“验证码 AI 增强”区：
     - 开关、Base URL、API Key、模型 ID
   - `loadSettings/saveSettings` 同步新增字段读取与提交
   - 前端保存前本地校验：AI 开启时要求 URL / Key / Model 完整

3. **group AI 去运行期化（软兼容）**
   - 文件：`templates/partials/modals.html`, `static/js/features/groups.js`, `outlook_web/controllers/groups.py`, `outlook_web/repositories/groups.py`
   - 分组弹窗移除 AI 字段（仅保留 length / regex）
   - group API 对历史 `verification_ai_*` payload 软兼容：接收但忽略
   - 运行期策略解析不再从 group 读取 AI 配置

4. **提取链路接入 AI fallback（规则优先）**
   - 文件：`outlook_web/services/verification_extractor.py`
   - 新增能力：
     - 系统级 AI 配置读取与完整性判断
     - 固定 JSON 输入契约构造（`verification_ai_v1`）
     - AI 输出 JSON 结构/类型校验
     - 规则低置信度时 AI fallback，AI 失败快速回退
   - Web / External / Temp Mail 已接入：
     - `outlook_web/controllers/emails.py`
     - `outlook_web/services/external_api.py`
     - `outlook_web/services/temp_mail_service.py`

5. **错误码与默认配置**
   - 文件：`outlook_web/errors.py`, `outlook_web/db.py`
   - 新增错误码：`VERIFICATION_AI_CONFIG_INCOMPLETE`
   - DB 初始化补充 4 个 settings key：
     - `verification_ai_enabled`
     - `verification_ai_base_url`
     - `verification_ai_api_key`
     - `verification_ai_model`

6. **测试新增/更新**
   - 新增：
     - `tests/test_settings_verification_ai_config.py`
     - `tests/test_verification_ai_json_contract.py`
   - 更新：
     - `tests/test_group_policy_frontend_contract.py`
     - `tests/test_groups_verification_policy_api.py`
     - `tests/test_extract_verification_group_policy.py`
     - `tests/test_external_verification_group_policy.py`

7. **本轮回归结果（已执行）**
   - `python -m unittest tests.test_settings_verification_ai_config tests.test_verification_ai_json_contract tests.test_group_policy_frontend_contract tests.test_groups_verification_policy_api tests.test_extract_verification_group_policy tests.test_external_verification_group_policy -v` → **22 passed**
   - `python -m unittest tests.test_verification_extractor_options tests.test_settings_external_api_key -v` → **47 passed**
   - `python -m unittest tests.test_external_api -v` → **111 passed**
   - `python -m unittest tests.test_settings_tab_refactor_frontend tests.test_settings_tab_refactor_backend -v` → **26 passed**
   - `python -m py_compile ...`（本轮改动核心 Python 文件）→ **通过**

8. **全量回归（discover）**
   - `python -m unittest discover -s tests -v`（延长超时后完整执行）
   - 结果：`Ran 946 tests in 191.540s`，`OK (skipped=7)`

**说明**：本轮已完成从专项回归到全量 discover 的闭环验证。

#### 0a. 全量复跑 + 文档实况回填（本次会话补记）

**时间**：2026-04-10

**本次实际操作**：

1. 按会话决策再次执行全量回归：
   - `python -m unittest discover -s tests -v`
   - 结果：`Ran 946 tests in 206.872s`，`OK (skipped=7)`

2. 按“根据实际修改文档”完成专项文档回填与纠偏：
   - `docs/BUG/2026-04-10-验证码策略-分组AI配置口径错误与长度校验易用性BUG.md`
     - 状态由“待修复”改为“已修复”，补充修复落地文件与验证结果。
   - `docs/FD/2026-04-10-AI识别配置系统级化与固定JSON契约FD.md`
     - confidence 口径改为 `high/low`，补充实施状态回填。
   - `docs/TD/2026-04-10-AI识别配置系统级化与固定JSON契约TD.md`
     - confidence 枚举改为 `high/low`，补充实施状态与全量测试结果。
   - `docs/TDD/2026-04-10-AI识别配置系统级化与固定JSON契约TDD.md`
     - 补充执行结果回填（含全量回归结论）。
   - `docs/TODO/2026-04-10-验证码提取提速与AI增强TODO.md`
     - Phase 9 从“待实施”更新为“已完成”，勾选 9.2/9.3/9.4/9.6 任务。

**状态结论**：

- 会话相关文档已与代码与测试现状对齐。
- WORKSPACE 已完成本次操作留痕。

#### 0b. 人工联调前运行态校验（本次会话补记）

**时间**：2026-04-10

**背景问题**：人工反馈“前端看起来与修复前一致”。

**本次排查与操作**：

1. 识别到本地启动受环境影响：
   - `SECRET_KEY` 缺失会导致应用无法按当前工作区实例稳定启动。
   - 全局代理环境变量（`HTTP_PROXY/HTTPS_PROXY`）会干扰本地 127.0.0.1 请求验证。
2. 停止旧进程并以当前工作区重启服务，明确注入测试环境变量：
   - `SECRET_KEY=dev-secret-key-for-manual-test`
   - `LOGIN_PASSWORD=admin123`
3. 运行态验证（登录后真实页面与接口）：
   - 首页包含系统级 AI 设置标识：`settingsVerificationAiEnabled`、文案“验证码 AI 增强”。
   - 分组弹窗保留 `groupVerificationCodeLength/groupVerificationCodeRegex`，无 `groupVerificationAi*` 控件。
   - settings API：AI 开启缺项返回 `VERIFICATION_AI_CONFIG_INCOMPLETE`；完整保存后 API Key 脱敏回显。
   - groups API：历史 `verification_ai_*` 入参被忽略，长度 `6 位` 规范化为 `6-6`。

**结论**：本轮修复在运行态可复核，前端与后端行为与专项目标一致。

#### 0c. 人工反馈问题排查：解密失败与自动调度未启动（本次会话补记）

**时间**：2026-04-11

**用户反馈**：

1. AI 服务已配置，但提取链路“看起来没走新逻辑”。
2. 出现“获取邮件信息失败”，怀疑数据库加密/解密密钥错误。
3. 观察到自动调度似乎未启动。

**本次排查动作（代码+运行态）**：

1. 核查密钥与加解密机制：
   - `outlook_web/security/crypto.py` 基于 `SECRET_KEY` 派生 Fernet 密钥，`SECRET_KEY` 变更会导致历史 `enc:` 数据解密失败（预期行为）。
2. 核查启动方式差异：
   - `start.py` 会自动 `load_dotenv()`；
   - `web_outlook_app.py` 原先未显式加载 `.env`，在部分本地启动方式下可能拿不到一致环境变量。
3. 代码修复：
   - 更新 `web_outlook_app.py`：增加 `.env` 自动加载（`python-dotenv`），并保持无该依赖时的兼容降级。
4. 运行态复验：
   - 使用 `python web_outlook_app.py`（不手工注入 SECRET_KEY）可正常启动：`/healthz` 200。
   - 登录后获取账号列表正常（24 个账号）。
   - 邮件列表接口可正常返回（首账号 `EMAIL_FETCH_SUCCESS=True`）。
   - `/api/scheduler/status` 显示 `enabled=true`、`autostart=true`。
   - 连续两次采样（间隔 70s）确认 `scheduler_heartbeat` 时间与 PID 已更新，说明自动调度正常运行。

**文档同步**：

1. `CHANGELOG.md`：补充“web_outlook_app 直启自动加载 .env”的 why。
2. `docs/BUG/2026-04-10-...BUG.md`：补充运行态误配场景与补丁说明。

**当前结论**：

- 本次“获取邮件失败/疑似解密失败”主要由启动环境不一致触发，非 AI 迁移逻辑本身回退。
- 自动调度经运行态验证已正常启动并持续心跳。

#### 0d. 人工测试反馈回填 + 指南落地（本次会话补记）

**时间**：2026-04-11

**用户反馈结论（人工）**：

1. “完整 AI 配置保存”可用。
2. “分组字段范围 + 长度容错”可用并能规范化保存。
3. “Web 验证码提取”可用。
4. “AI 异常快速回退”与 “External 人工联调”不易现场复现，需由自动化补强。

**本次补强动作**：

1. 新增人工测试指南文档：
   - `docs/DEV/2026-04-11-AI系统级配置与提取链路人工测试指南.md`
   - 覆盖：启动前置、系统级 AI 配置、分组容错、提取链路、调度状态、常见故障排查。
2. 自动化补测执行：
   - `python -m unittest tests.test_settings_verification_ai_config tests.test_verification_ai_json_contract tests.test_external_verification_group_policy -v`
   - 结果：`Ran 8 tests ... OK`
3. 文档回填：
   - `docs/TDD/2026-04-10-AI识别配置系统级化与固定JSON契约TDD.md`
   - `docs/TODO/2026-04-10-验证码提取提速与AI增强TODO.md`

**状态**：

- 人工可测部分已确认通过。
- 不便人工构造部分已由自动化用例补齐并通过。

#### 1. 验证码提取提速 + AI 增强（V1）需求澄清与 PRD 建档

**时间**：2026-04-10

**背景**：围绕“点击验证码按钮耗时较长、默认长度策略与业务不匹配、希望引入轻量 AI 提升通用性”进行会话澄清。

**本次确认的需求决策（以会话结论为准）**：

1. V1 采用双 P0 范围：
   - P0-A：验证码提取链路提速
   - P0-B：AI 提取能力（验证码/认证链接）
2. 默认验证码策略改为 **6 位**（`6-6`）
3. 增加“**按账号分组（group）配置映射范围**”能力
4. 参数优先级：请求显式参数 > 分组配置 > 系统默认（6-6）

**本次实际操作**：

- 新增 PRD 文档：
  - `docs/PRD/2026-04-10-验证码提取提速与AI增强PRD.md`
- 文档内容覆盖：
  - 现状问题拆解（慢链路定位）
  - V1 双 P0 目标与范围
  - 分组映射与默认 6 位策略
  - AI 兜底触发条件、输出门控、时延与成本约束
  - 验收指标（P50/P95）与风险应对

**说明**：本次为需求与文档阶段，未改动业务代码。

#### 1b. PRD 澄清补充：分组设置项范围确认

**时间**：2026-04-10

**会话确认结果**：

1. 配置入口：放在每个分组的设置界面
2. V1 分组配置项：
   - 验证码范围（code_length）
   - AI 开关
   - AI 模型选择

**文档同步**：

- 更新 `docs/PRD/2026-04-10-验证码提取提速与AI增强PRD.md`
  - 新增分组配置入口说明
  - 新增 V1 分组配置项章节
  - 补充“AI 开关开启才触发 AI 兜底”的约束

#### 1c. PRD 澄清补充：模型配置口径

**时间**：2026-04-10

**会话确认结果**：

1. 分组模型配置采用“自由填写模型 ID”
2. V1 仅考虑 OpenAI 兼容格式
3. 配置侧保持简单，不引入多供应商复杂配置

**文档同步**：

- 更新 `docs/PRD/2026-04-10-验证码提取提速与AI增强PRD.md`
  - In Scope 新增“仅支持 OpenAI 兼容模型配置”
  - 分组配置项改为“AI 模型 ID（自由填写）”
  - 新增 V1 配置简化原则章节

#### 1d. PRD 澄清补充：模型ID缺省处理

**时间**：2026-04-10

**会话确认结果**：

1. 当分组 AI 开关开启但模型 ID 为空时，直接报错
2. 错误需明确提示“请填写模型 ID”
3. 不自动回退默认模型

**文档同步**：

- 更新 `docs/PRD/2026-04-10-验证码提取提速与AI增强PRD.md`
  - 新增“模型 ID 缺省处理”章节
  - 配置简化原则补充“AI 开启时模型 ID 必填”

#### 1e. PRD 澄清补充：提速范围优先级

**时间**：2026-04-10

**会话确认结果**：

1. 提速范围中，Web 与 External 两条链路作为同级 P0
2. 不做先后优先，V1 同步纳入验收

**文档同步**：

- 更新 `docs/PRD/2026-04-10-验证码提取提速与AI增强PRD.md`
  - 目标层补充 External 耗时波动治理
  - In Scope 调整为“Web + External 同级 P0”
  - 提速需求新增“双入口同级 P0”定义
  - 性能验收补充 External P50/P95 指标

#### 1f. PRD 结构重构：仅保留需求与 Use Case

**时间**：2026-04-10

**触发原因**：会话中明确要求 PRD 仅讨论“需求 + Use Case”，不展开实现口径。

**本次操作**：

1. 删除原 `docs/PRD/2026-04-10-验证码提取提速与AI增强PRD.md`（偏实现化版本）
2. 重新创建同名 PRD（v2.0），结构聚焦：
   - 背景
   - 目标
   - 需求范围（In/Out）
   - 核心需求定义
   - 用户角色
   - Use Cases（UC-01 ~ UC-05）
   - 需求层验收标准
   - 风险与边界

**说明**：本次仍为文档层操作，未改动业务代码。

#### 1g. PRD 澄清补充：默认 6 位的作用边界

**时间**：2026-04-10

**会话确认结果**：

1. 默认 6 位仅作用于“验证码提取”
2. 链接提取不受默认 6 位策略影响

**文档同步**：

- 更新 `docs/PRD/2026-04-10-验证码提取提速与AI增强PRD.md`
  - 背景、In Scope、策略需求、验收标准均改为同一口径
  - 明确“仅验证码默认 6 位，链接提取不受影响”

#### 1h. PRD 澄清补充：分组验证码配置表达能力

**时间**：2026-04-10

**会话确认结果**：

1. 分组配置中的验证码策略支持：
   - 长度范围
   - 自定义正则

**文档同步**：

- 更新 `docs/PRD/2026-04-10-验证码提取提速与AI增强PRD.md`
  - In Scope 配置项补充“自定义正则”
  - 核心需求补充“长度范围 + 自定义正则”
  - 验收标准同步为“范围 + 自定义正则 + AI 开关 + 模型 ID”

#### 2. FD 编写：验证码提取提速与 AI 增强（V1）

**时间**：2026-04-10

**前置澄清（会话确认）**：

1. 分组内“长度范围 + 自定义正则”并存时：自定义正则优先
2. FD 数据承载方案：扩展 `groups` 表字段（不新建策略表）

**本次实际操作**：

1. 更新 PRD：
   - `docs/PRD/2026-04-10-验证码提取提速与AI增强PRD.md`
   - 在“策略配置需求”补充：分组内 regex 优先于 length

2. 新增 FD：
   - `docs/FD/2026-04-10-验证码提取提速与AI增强FD.md`
   - 内容覆盖：
     - 功能边界与系统行为
     - groups 表 4 字段扩展方案
     - groups API 契约扩展与校验规则
     - 分组设置弹窗交互项与规则
     - 统一策略解析口径与错误反馈规范

**说明**：本次仅文档设计，不涉及业务代码修改。

#### 3. TD 编写：验证码提取提速与 AI 增强（V1）

**时间**：2026-04-10

**会话确认结果（新增）**：

1. 分组内“长度范围 + 自定义正则”并存时，自定义正则优先
2. 技术落地采用 `groups` 表扩展 4 字段方案（简单直观）

**本次实际操作**：

1. 更新 PRD 版本到 v2.1，补充“regex 优先”规则
2. 新增 TD 文档：
   - `docs/TD/2026-04-10-验证码提取提速与AI增强TD.md`
3. TD 核心内容：
   - Schema 迁移（groups 4 字段）
   - groups repository/controller/route 扩展点
   - 分组弹窗字段扩展与校验规则
   - Web + External 提取链路统一策略解析
   - 兼容性、回滚、验收映射
4. 修正文档引用：external controller 文件归并为 `outlook_web/controllers/emails.py`

**说明**：本次为文档阶段，未改动业务代码。

#### 4. PRD/FD/TD 文档联调对齐

**时间**：2026-04-10

**目标**：按“需求口径一致、UseCase 可映射、文档可执行”完成三份文档联调。

**本次实际操作**：

1. 新增联调检查文档：
   - `docs/TD/2026-04-10-验证码提取提速与AI增强-PRD-FD-TD联调检查.md`
2. 检查项覆盖：
   - Web + External 同级 P0
   - 默认 6 位边界（仅验证码）
   - 分组配置项与优先级（含 regex > length）
   - AI 开启模型必填约束
3. 发现并修复：
   - TD 影响文件清单中 `controllers/emails.py` 重复项已去重

**联调结论**：

- PRD / FD / TD 口径一致，可进入 TDD 与开发阶段。

#### 5. TDD 编写：验证码提取提速与 AI 增强（V1）

**时间**：2026-04-10

**目标**：将已对齐的 PRD/FD/TD 转换为可执行测试设计，确保后续开发可按测试矩阵推进。

**本次实际操作**：

1. 新增 TDD 文档：
   - `docs/TDD/2026-04-10-验证码提取提速与AI增强-TDD.md`
2. 覆盖内容：
   - 分层测试策略（Repository / groups API / Web 提取 / External 提取 / 前端契约）
   - 关键测试矩阵（配置、优先级、默认边界）
   - 回归清单与执行命令
3. 重点校验目标：
   - 请求参数 > 分组配置 > 默认
   - 组内 regex > length
   - 仅验证码默认 6 位、链接不受影响
   - AI 开启模型必填

**说明**：本次仅新增测试设计文档，未改动业务代码与测试代码。

#### 6. 任务拆分 TODO 文档落地（验证码提取提速与 AI 增强）

**时间**：2026-04-10

**背景**：在完成 PRD/FD/TD/TDD 后，进入“可执行实施清单”阶段，按用户要求将实现任务做分阶段拆分，便于后续由其他 AI 或开发同学按清单推进。

**本次实际操作**：

1. 新增 TODO 文档：
   - `docs/TODO/2026-04-10-验证码提取提速与AI增强TODO.md`
2. 文档采用“执行导向拆解”结构：
   - Phase 0~8（基线冻结 → DB → Repo/API → 前端 → Web/External → 错误码统一 → TDD 转绿 → 发布收尾）
   - 每个阶段均拆为可勾选任务项（`- [ ]`）
3. 明确本需求的统一口径（写入 TODO 头部基线）：
   - Web + External 同级 P0
   - 默认 6 位仅作用于验证码
   - 分组内 regex > length
   - request > group > default

**补充说明**：

- 中途误进入实现代码编辑（`db.py / repositories/groups.py / controllers/groups.py`）后，已按要求回滚，不将该误操作纳入本次方案推进范围。

#### 7. 验证码提取提速 + AI 增强（V1）实施收尾回填（Phase 8）

**时间**：2026-04-10

**背景**：在完成 V1 代码与分层测试后，进入发布前文档收尾阶段，对 TODO 执行状态、FD/TD/TDD 实施结果、工作区记录与变更说明进行统一回填。

**本次实际操作**：

1. 回填 TODO 执行状态：
   - 更新 `docs/TODO/2026-04-10-验证码提取提速与AI增强TODO.md`
   - 将 Phase 0~6 标记为已完成
   - 将 Phase 7 标记为“部分完成（7.7 待确认）”
   - 将 Phase 8 标记为“进行中（8.6 待完成）”
   - 明确全量 `discover` 输出曾被会话截断，发布前需复跑并留档

2. 回填 FD 实施结果与偏差：
   - 更新 `docs/FD/2026-04-10-验证码提取提速与AI增强FD.md`
   - 新增“实现结果与偏差回填”章节（端到端落地情况、V1 范围边界、后续建议）

3. 回填 TD 实施结果与偏差：
   - 更新 `docs/TD/2026-04-10-验证码提取提速与AI增强TD.md`
   - 新增“实现结果与偏差回填”章节（Schema v20、链路对齐、复用 extractor 说明）

4. 回填 TDD 执行结果：
   - 更新 `docs/TDD/2026-04-10-验证码提取提速与AI增强-TDD.md`
   - 新增“执行结果回填”章节（分层通过项、重点回归通过项、全量待复跑项）

5. 补充发布说明记录（why 导向）：
   - 更新 `CHANGELOG.md`，新增 Unreleased 条目，强调本次改动目标是统一 Web/External 策略口径、减少提取歧义、避免 AI 配置静默降级。

**当前状态**：

- 文档回填已完成（FD/TD/TDD/TODO/WORKSPACE/CHANGELOG）
- 全量测试已复跑通过：`Ran 938 tests ... OK (skipped=7)`
- 发布门槛已满足，可进入人工验收与发布流程

**说明**：本次主要为文档与记录收尾，不新增功能代码。

#### 8. 验证码提取提速 + AI 增强（V1）回归修复与全量转绿

**时间**：2026-04-10

**背景**：在首次全量回归中发现 7 个失败，集中于 external temp-mail 兼容测试（verification-code / verification-link 返回 404）。

**根因结论**：

1. `get_verification_result()` 仍强依赖 `require_account()`，导致 task temp-mail 场景无法进入统一提取链路。
2. verification-link 复用了验证码默认长度策略，导致“默认 6 位仅作用于验证码”的边界被破坏。

**修复动作**：

1. `outlook_web/services/external_api.py`
   - `get_verification_result()` 改为基于 `accounts_repo.get_account_by_email()`可选读取分组策略，不再硬依赖 account 必须存在。
   - 增加 `apply_default_code_length` 参数，控制是否应用默认 `6-6`。

2. `outlook_web/controllers/emails.py`
   - `/api/external/verification-link` 调用 `get_verification_result(..., apply_default_code_length=False)`，恢复链接提取边界。

**验证结果**：

- `tests.test_external_api_temp_mail_compat`：6/6 通过
- `tests.test_external_verification_group_policy`：3/3 通过
- `tests.test_extract_verification_group_policy`：5/5 通过
- `tests.test_external_api`：111/111 通过
- 全量：`python -m unittest discover -s tests -v` → `Ran 938 tests ... OK (skipped=7)`

**状态**：V1 本轮开发 + 回归 + 文档回填已闭环完成，下一步进入人工启动验证。

#### 9. 需求澄清后文档修订：AI 配置改为系统级（分组仅保留 length/regex）

**时间**：2026-04-10

**用户反馈要点**：

1. 分组不应承载 AI 模型配置。
2. AI URL / API Key / 模型 ID 属于系统级基础设置，应在设置页统一维护。
3. 当前仅在分组配置模型 ID 不完整，无法形成可用的真实 AI 配置闭环。
4. 线上操作反馈出现 `GROUP_VERIFICATION_LENGTH_INVALID`，长度配置体验需优化。

**本次实际操作（文档层）**：

1. 更新 PRD：
   - `docs/PRD/2026-04-10-验证码提取提速与AI增强PRD.md`
   - 将 AI 配置口径改为系统级（开关/Base URL/API Key/模型 ID）
   - 分组策略仅保留 length/regex

2. 更新 FD：
   - `docs/FD/2026-04-10-验证码提取提速与AI增强FD.md`
   - 数据模型与接口契约改为“groups 规则 + settings AI 配置”
   - 标记当前实现存在“分组级 AI 字段遗留”待后续清理

3. 更新 TD：
   - `docs/TD/2026-04-10-验证码提取提速与AI增强TD.md`
   - 技术决策改为“AI 配置系统级，groups 去 AI 化”
   - 增补受影响文件（settings controller/repo）

4. 更新 TDD：
   - `docs/TDD/2026-04-10-验证码提取提速与AI增强-TDD.md`
   - 测试目标改为分组仅校验 length/regex
   - 增加“需求澄清说明”，指明后续测试迁移方向

5. 更新 TODO：
   - `docs/TODO/2026-04-10-验证码提取提速与AI增强TODO.md`
   - 新增 Phase 9（待实施）：AI 配置上收系统级 + groups 去 AI 化 + 长度容错优化

**结果与状态**：

- 文档口径已按最新需求完成修订。
- 代码层“groups 去 AI 化 + settings AI 配置化 + 长度容错”尚未实施，已进入 Phase 9 待执行。

#### 10. BUG 单独建档：分组 AI 配置口径错误 + 验证码长度格式报错

**时间**：2026-04-10

**触发背景**：用户明确要求将本问题作为 BUG 独立记录，而不是直接按需求方案推进。

**本次操作**：

1. 新增 BUG 文档：
   - `docs/BUG/2026-04-10-验证码策略-分组AI配置口径错误与长度校验易用性BUG.md`

2. 文档内容覆盖：
   - 问题拆分：
     - 分组级 AI 配置口径错误（缺 URL/API Key 闭环）
     - `GROUP_VERIFICATION_LENGTH_INVALID` 高频触发（严格 `min-max` 导致易用性差）
   - 复现步骤与预期行为
   - 根因定位（groups controller/repo + groups.js + modal）
   - 修复方向（仅建议，待后续实施）

**状态结论**：

- 本问题已以 BUG 形式单独立项。
- 当前阶段先完成“记录与对齐”，后续在充分读取上下文后再进入代码实施。

#### 11. BUG 修复（Phase 9 局部）：验证码长度格式容错

**时间**：2026-04-10

**背景**：在 BUG 文档已确认的前提下，按会话决策先落地“长度易用性修复”，AI 系统级迁移后续再做。

**本次代码改动**：

1. `outlook_web/repositories/groups.py`
   - 增强 `_validate_code_length()` 的输入规范化，兼容常见用户输入：
     - 单值：`6` → `6-6`
     - 波浪线：`4~8` / `4～8` → `4-8`
     - 带后缀：`4-8位`、`6 位` → 去后缀后解析
     - 去除中间空白后再校验
   - 仍保持最终存储格式为标准 `min-max`。
   - 对非法输入继续返回原错误码：`GROUP_VERIFICATION_LENGTH_INVALID`（兼容既有错误契约）。

2. 测试补充与回归：
   - `tests/test_group_verification_policy_repo.py`
     - 新增 `test_normalize_group_policy_accepts_common_length_formats`
   - `tests/test_groups_verification_policy_api.py`
     - 新增 `test_update_group_accepts_single_length_input`
     - 新增 `test_update_group_accepts_tilde_length_input`

**执行结果**：

- `python -m unittest tests.test_group_verification_policy_repo -v` → 5/5 通过
- `python -m unittest tests.test_groups_verification_policy_api -v` → 7/7 通过
- `python -m unittest tests.test_extract_verification_group_policy -v` → 5/5 通过
- `python -m unittest tests.test_external_verification_group_policy -v` → 3/3 通过
- `python -m unittest tests.test_group_policy_frontend_contract -v` → 2/2 通过

**状态**：

- Phase 9 中“长度容错优化”已完成并通过分层回归。
- “AI 配置系统级迁移（groups 去 AI 化）”仍待后续独立实施。

#### 12. 新开 PRD：AI 识别配置系统级化与测试闭环

**时间**：2026-04-10

**背景**：会话确认切换到方案 A（软迁移），并要求围绕 AI 板块单独讨论需求与测试口径，新增独立 PRD。

**本次操作**：

1. 新增独立 PRD 文档：
   - `docs/PRD/2026-04-10-AI识别配置系统级化与测试闭环PRD.md`

2. PRD 聚焦内容：
   - AI 配置系统级闭环（开关/Base URL/API Key/模型 ID）
   - Web/External 统一读取口径
   - 分组策略收敛为 length/regex
   - 软迁移兼容（deprecated 分组 AI 字段）
   - 安全要求（密钥存储/脱敏/日志）
   - 测试闭环与 UC-01~UC-05 验收口径

**状态**：

- 已完成“独立 PRD 建档”。
- 下一步进入该 PRD 对应 FD/TD/TDD 与实施方案讨论。

#### 13. 文档优先推进：AI 配置修复专项补齐 FD/TD/TDD（含固定 JSON 契约）

**时间**：2026-04-10

**背景**：会话明确要求“先考虑文档相关内容”，并聚焦“修复 AI 配置 + 验证码提取加速 + 固定 JSON 输入输出”。

**本次文档操作**：

1. 更新 PRD（专项口径增强）：
   - `docs/PRD/2026-04-10-AI识别配置系统级化与测试闭环PRD.md`
   - 增加“提取加速”与“固定 JSON 输入/输出契约”目标与验收项

2. 新增 FD：
   - `docs/FD/2026-04-10-AI识别配置系统级化与固定JSON契约FD.md`
   - 明确 settings 闭环、规则优先快路径、固定 JSON 输入输出格式、异常回退规范

3. 新增 TD：
   - `docs/TD/2026-04-10-AI识别配置系统级化与固定JSON契约TD.md`
   - 明确分层改造范围（settings/front/提取链路）、契约校验点、兼容策略与错误语义

4. 新增 TDD：
   - `docs/TDD/2026-04-10-AI识别配置系统级化与固定JSON契约TDD.md`
   - 建立配置闭环/JSON 契约/快路径回退/Web-External 一致性测试矩阵

**状态**：

- AI 专项文档链（PRD/FD/TD/TDD）已建立。
- 下一步可按该文档链进入代码实施与测试落地。

## 2026-04-09

### 操作记录

#### 7. CF临时邮箱接入邮箱池：Phase 1-3 实现 + 部分测试通过

**时间**：2026-04-09

**目标**：实现 CF 临时邮箱接入邮箱池的核心链路（动态创建 claim + 智能删除 complete）。

**实际完成内容**：

**Phase 1: DB Schema v19** ✅
- `outlook_web/db.py`：`DB_SCHEMA_VERSION = 19`，新增 `temp_mail_meta TEXT` 列
- 迁移幂等：重复启动不报错
- 新增唯一索引 `idx_pool_claim_token`、`idx_pool_tasks_unique`

**Phase 2: Pool - claim 动态创建** ✅
- `outlook_web/repositories/pool.py`：
  - 新增 `insert_claimed_account()` — 纯 DB 写入（INSERT accounts + claim_log + project_usage）
  - 移除了对 `services.temp_mail_provider_cf` 的违规导入（架构修复）
- `outlook_web/services/pool.py`：
  - 新增 `_create_cf_mailbox_for_pool()` — 调用 CF Provider 创建邮箱
  - 新增 `_delete_cf_mailbox_nonblocking()` — 非阻塞删除远程 CF 邮箱
  - `claim_random()` 增强：池空且 provider=cloudflare_temp_mail 时动态创建
  - Provider 白名单校验：None/'' + 现有 provider + cloudflare_temp_mail

**Phase 3: Pool - complete 智能删除** ✅
- `services/pool.py` `complete_claim()` 增强：
  - 事务提交后判断 `result in ('success', 'credential_invalid')` 才调用远程删除
  - 删除失败非阻塞：仅 warning 日志，不影响本地状态流转
  - 其他 result（timeout/network_error/provider_blocked）不触发删除

**Phase 5 部分测试** ✅
- `tests/test_module_boundaries.py`：3/3 通过（验证 repositories 不依赖 services）
- `tests/test_pool_cf_integration_tdd_skeleton.py`：18/18 通过
- `tests/test_pool.py`：全部通过（Repository + Service + API）
- `tests/test_pool_flow_suite.py`：全部通过
- Pool 相关 70 测试总耗时 4.4s，0 failures
- 全量测试套件无 FAIL、无 ERROR

**修改文件清单**：
- `outlook_web/db.py` — Schema v19 迁移（+143 行）
- `outlook_web/repositories/pool.py` — 新增 `insert_claimed_account()`，移除 CF 导入（+155 行）
- `outlook_web/services/pool.py` — CF 动态创建/删除逻辑（+219 行）
- `tests/test_db_migration_task_token_unique.py` — 适配新迁移
- `tests/test_pool.py` — 新增 CF 相关 Service/Repository 测试（+153 行）
- `tests/test_pool_flow_suite.py` — 适配增强逻辑（+51 行）
- `tests/test_pool_cf_integration_tdd_skeleton.py` — **新增** 18 个 TDD 骨架测试

**架构约束验证**：
- Route → Controller → Service → Repository 分层严格保持
- Repository 层不依赖任何 Service（包括 temp_mail_provider_cf）
- CF 上游调用（create_mailbox / delete_mailbox）全部在 Service 层

**待完成**：
- ~~Phase 0: 文档对齐收尾（PRD/FD/TD 接口名/schema 版本）~~ ✅ 已完成
- ~~Phase 4: external 读信链路适配（mailbox_resolver 识别 CF pool 账号）~~ ✅ 已完成
- Phase 5: 补充 external 读信链路测试、DB v19 迁移测试
- Phase 6: 联调与验收

#### 7b. Phase 0 文档对齐收尾

**时间**：2026-04-09

**操作内容**：
- PRD：6 处修改
  - `§2.4.1` 标题和所有 `/claim` 引用 → `claim-random`
  - "加密存储" → "明文 JSON 存储"（JWT 已签名，本期不额外加密）
- FD：3 处修改
  - 数据流图和参考资料中 `/claim` → `claim-random`
- TD：4 处修改
  - `Schema v18` → `Schema v19`
  - 所有 `/claim` 引用 → `claim-random`
- TODO：Phase 0 任务全部标记为 `[x]`

#### 7c. Phase 4 读信链路适配 + 真实 E2E 测试

**时间**：2026-04-09

**操作内容**：

1. **mailbox_resolver.py 适配**：
   - CF pool 账号（`provider='cloudflare_temp_mail'`）→ 返回 `kind='temp'`
   - meta 从 `accounts.temp_mail_meta` 解析，包含 `provider_jwt`
   - 外部读信链路自动走 `TempMailService → CF Provider → 真实 CF Worker API`

2. **真实 CF Worker E2E 测试**（`tests/test_pool_cf_real_e2e.py`）：
   - CF Worker: `https://temp.zerodotsix.top` + 真实 admin key
   - E2E-01: claim-random → 真实创建 CF 邮箱 ✅
   - E2E-02: 读取邮件列表（新邮箱为空，正确返回 404）✅
   - E2E-03: complete(success) → 远程 CF 邮箱已删除 ✅
   - E2E-04: complete(verification_timeout) → 远程邮箱保留 ✅
   - 4/4 全部通过（11.961s）

3. **测试结果汇总**：
   - Pool 相关 70 测试（含 TDD 骨架）：0 failures, 1 skipped
   - 真实 E2E 4 测试：0 failures
   - 模块边界测试 3/3 通过

**修改文件**：
- `outlook_web/services/mailbox_resolver.py` — 新增 CF pool 账号 → `kind='temp'` 逻辑
- `outlook_web/services/refresh.py` — 排除 CF pool 账号进入 OAuth 刷新链路（`provider='cloudflare_temp_mail'`）
- `tests/test_pool_cf_real_e2e.py` — **新增** 真实 CF Worker E2E 测试（4 个用例）
- `tests/test_pool_cf_integration_tdd_skeleton.py` — E2E mock 测试 skip（已由真实 E2E 替代）

#### 7d. Phase 6 风险修复 + 联调验收

**时间**：2026-04-09

**发现并修复的风险**：
- CF pool 账号（account_type='outlook'）会被 `refresh.py` 误选入 OAuth token 刷新链路
- 修复：`is_refreshable_outlook_account()` 新增 `provider` 参数，排除 `cloudflare_temp_mail`
- 修复：`build_refreshable_outlook_account_where()` SQL 新增 `provider != 'cloudflare_temp_mail'` 条件
- 验证：refresh 测试 7/7 通过

**Phase 6 进度**：
- ✅ Task 6.1: 本地联调脚本（已被真实 E2E 覆盖）
- ✅ Task 6.3: 日志与审计（claim/complete audit 有 provider、account_id、result）
- ✅ Task 6.4: 风险清单复核（refresh 排除 + 缓存依赖已通过 E2E 验证）
- ✅ Task 6.5: 验收清单（claim → read → complete 全链路真实验证通过）

#### 7e. Phase 6.2 前端 UI 保护 + 后端删除/编辑守卫

**时间**：2026-04-09

**操作内容**：

1. **前端 UI 保护**（`static/js/features/groups.js`）：
   - `getProviderLabel()` 新增 `cloudflare_temp_mail: 'CF 临时邮箱'` 标签
   - 新增 `isCfPoolAccount` 变量，识别 CF pool 账号
   - CF pool 账号的编辑和删除按钮设为 `disabled` + `opacity:0.3` + 提示文案

2. **后端删除保护**（`outlook_web/controllers/accounts.py`）：
   - `api_delete_account()` 新增 CF pool 检查，返回 403
   - `api_delete_account_by_email()` 新增 CF pool 检查，返回 403
   - `api_batch_delete_accounts()` 新增 CF pool 跳过逻辑
   - `api_update_account()` 新增 CF pool 检查，返回 403

3. **全量测试**：917 测试通过，0 failures

**修改文件**：
- `static/js/features/groups.js` — CF provider 标签 + 编辑/删除按钮禁用
- `outlook_web/controllers/accounts.py` — 删除/编辑 CF pool 账号保护（4 处）

#### 7f. 临时邮箱页面 CF 域名下拉不显示：BUG 确认 + 方案 A 选定 + 文档对齐更新

**时间**：2026-04-09

**背景**：在验收 CF Worker 临时邮箱/邮箱池接入时发现一个前端体验 BUG —— 设置页已同步的 CF 域名在「⚡ 临时邮箱」页选择 `cloudflare_temp_mail` provider 后，域名下拉不展示。

**根因结论**（已记录到 BUG 文档）：
- `/api/temp-emails/options` 当前不支持按 provider 返回（始终按全局 runtime provider 返回 options）
- `CloudflareTempMailProvider.get_options()` 读取的是 `temp_mail_*` key，但设置页同步写入的是 `cf_worker_*` key，导致 domains 为空

**本次决策**：确认采用 **修复方案 A（推荐）**
- options API 支持 `provider_name` 参数（后端按 provider 返回 options）
- CF provider 的 options 读取口径切换为 `cf_worker_*`
- 前端请求 options 时携带当前选择的 provider

**本次实际操作**（按“以代码为准”修正文档）：
- 更新/对齐文档：
  - `docs/FD/2026-04-09-CF临时邮箱接入邮箱池FD.md`（修正“读信无需改动/解析返回 kind=account/account_type=temp_mail”等不准确描述；强调 resolver 返回 `kind='temp'`）
  - `docs/TD/2026-04-09-CF临时邮箱接入邮箱池TD.md`（修正“Repository 层进行网络调用”的伪代码与函数命名；对齐实际实现：网络调用在 Service，Repository 仅 DB 写入）
  - `docs/TODO/2026-04-09-CF临时邮箱接入邮箱池TODO.md`（补齐 Phase 4/6 的已完成勾选，保持与 WORKSPACE 的真实进度一致）
  - `docs/BUG/2026-04-09-临时邮箱-CF域名配置不生效-Options口径不一致BUG.md`（状态更新为“已确认方案 A，待实施”）

#### 7g. BUG 修复实施完成 + 人工验收通过（含一次配置值误报排查）

**时间**：2026-04-09

**实施内容**：

1. **方案 A 落地**：
   - `/api/temp-emails/options` 支持 `provider_name` 参数（后端按 provider 返回 options）
   - `TempMailService.get_options(provider_name=...)` 支持按 provider 取配置
   - 前端 `loadTempEmailOptions()` 带 provider 查询参数

2. **v0.3.1 快速修复**：
   - `CloudflareTempMailProvider.get_options()` 增加自动同步逻辑：
     - 当 `cf_worker_domains` 为空且 `cf_worker_base_url` 已配置时，自动请求 `GET {base_url}/open_api/settings`
     - 成功后写回 `cf_worker_domains` / `cf_worker_default_domain`
     - 失败非阻塞（warning）

3. **人工验收（真实环境）**：
   - provider=CF 后域名下拉可见（`zerodotsix.top`, `outlookmailplus.tech`）
   - 指定域名创建邮箱成功

4. **现场故障排查记录**：
   - 现象：创建时报 `UNAUTHORIZED` / 502
   - 根因：`cf_worker_admin_key` 配置值错误（写入了 `admin123`，实际应为 `1234567890-=`）
   - 结论：非代码保存链路缺陷，修正配置值后恢复

#### 7h. 文档二次对齐收尾（按“代码与测试结果为准”）

**时间**：2026-04-09

**目标**：将 `FD/TD/TODO/BUG` 与当前实现、真实人工验收、全量测试结果一致化，清理历史“计划态/样例态”描述。

**本次对齐动作**：

1. `docs/TODO/2026-04-09-CF临时邮箱接入邮箱池TODO.md`
   - 将全量测试从 `917/917` 更新为 `919/919`
   - 明确 claim/complete audit 当前字段覆盖现状（claim-complete 额外 provider 标为后续增强）
   - 明确 `mailbox_resolver` + external read 最小链路已由真实 E2E 覆盖
   - 文末声明更新为“已持续回填，默认以代码和测试为准”

2. `docs/FD/2026-04-09-CF临时邮箱接入邮箱池FD.md`
   - 修正测试文件引用：去除不存在的 `test_pool_cf_integration.py / test_external_pool_cf_e2e.py / test_pool_cf_contract.py`
   - 对齐当前实际测试文件：`test_pool_cf_integration_tdd_skeleton.py`、`test_pool_cf_real_e2e.py`、`test_temp_emails_api_regression.py`、`test_temp_mail_provider_cf.py`
   - 调整“文档更新”章节为当前仓库状态描述（CHANGELOG/API 文档按可选同步）

3. `docs/TD/2026-04-09-CF临时邮箱接入邮箱池TD.md`
   - 将“动态创建在 claim_atomic 中调用 `_create_cf_temp_email_for_pool()`”改为真实实现：Service 层 `_create_cf_mailbox_for_pool()` + Repository `insert_claimed_account()`
   - 将 external claim-random 示例对齐为当前 controller 结构（返回字段以当前实现为准）
   - 修正里程碑与验收项：标注已完成项、待发布项、测试结果（919/919）
   - 将不存在测试文件替换为当前真实文件

4. `docs/BUG/2026-04-09-临时邮箱-CF域名配置不生效-Options口径不一致BUG.md`
   - 状态改为“已修复”
   - 补充 v0.3.1 自动同步实现与人工验收结论
   - 补充“UNAUTHORIZED 为配置值错误而非保存链路缺陷”的排查记录

**验证**：
- 重点回归：`tests.test_temp_mail_provider_cf` + `tests.test_temp_emails_api_regression` 通过
- 全量测试：`python -m unittest discover -s tests -v` → `Ran 919 tests ... OK (skipped=7)`

#### 7i. README 与对外接口文档同步更新（面向接入方）

**时间**：2026-04-09

**背景**：在完成 CF 临时邮箱接入池能力与人工验收后，补齐对外可见文档，避免接入方沿用旧字段/旧错误码。

**本次更新文件**：

1. `README.md`
   - 补充 CF 临时邮箱最近更新：
     - options 支持 `provider_name`（前端切换 provider 时域名下拉正确联动）
     - v0.3.1 自动同步 domains（`cf_worker_domains` 为空时自动回源）
     - `cf_worker_admin_key` 配置不一致会导致 `UNAUTHORIZED` 的注意事项
   - 在核心能力中补充 `provider=cloudflare_temp_mail` 且池空动态创建
   - 在环境变量说明中补充 CF Worker 对应项（并注明设置页 key 名）

2. `注册与邮箱池接口文档.md`
   - `claim-random` 的 `provider` 可选值补全：`outlook/imap/custom/cloudflare_temp_mail`
   - 明确 `provider=cloudflare_temp_mail` 且池空时会动态创建
   - 成功返回字段补全：`email_domain`、`claimed_at`
   - 错误码对齐：`NO_AVAILABLE_ACCOUNT` → `no_available_account`
   - 补充 `claim-complete` 下 CF 删除策略（success/credential_invalid 删除，失败非阻塞）

3. `registration-mail-pool-api.en.md`
   - 与中文接口文档做同口径同步（provider 枚举、动态创建行为、返回字段、错误码大小写、CF 删除策略）

**结果**：
- 接入方文档与当前实现保持一致，减少对接歧义和现场排障成本。

#### 7j. 对外接口文档补充“可复制接入示例”（中英）

**时间**：2026-04-09

**背景**：为降低接入成本，按当前真实接口契约补充可直接复制的 curl 与响应示例。

**更新文件**：

1. `注册与邮箱池接口文档.md`
   - 新增：
     - CF 池 `claim-random` 可复制请求示例
     - `claim-random` 成功/无可用账号响应示例
     - `claim-complete` 可复制请求与成功响应示例
     - `claim-release` 可复制请求示例

2. `registration-mail-pool-api.en.md`
   - 同步新增英文版可复制示例（claim-random / claim-complete / claim-release）

**文档口径**：
- provider 明确支持 `cloudflare_temp_mail`
- no-available 错误码统一为 `no_available_account`
- claim-random 成功字段示例包含 `email_domain`、`claimed_at`

---

#### 4. CF临时邮箱接入邮箱池：文档补齐 + TDD 编写

**时间**：2026-04-09

**目标**：按“文档先行”流程补齐该功能的文档链路，并在进入实现前完成 TDD（测试设计文档）。

**本次实际操作**：

- 确认 PRD 已存在：`docs/PRD/2026-04-09-CF临时邮箱接入邮箱池PRD.md`
- 编写/补齐（当前工作区内为未提交状态）：
  - `docs/FD/2026-04-09-CF临时邮箱接入邮箱池FD.md`
  - `docs/TD/2026-04-09-CF临时邮箱接入邮箱池TD.md`
  - `docs/TDD/2026-04-09-CF临时邮箱接入邮箱池-TDD.md`

**关键内容**：

- 明确测试目标：动态创建、智能删除、兼容不破坏、外部 API 契约稳定
- 明确测试分层：Repository → Service → Controller →（可选）external 读信链路
- 明确 Mock 策略：禁止真实网络，统一 patch `CloudflareTempMailProvider.*`

**对话规范**：后续需求确认/方案选择/完成前反馈，统一通过“寸止 MCP”进行。

#### 5. 文档与代码现状对齐：schema 版本与项目地图修正

**时间**：2026-04-09

**目标**：在“充分阅读源代码”后，将仓库内关键说明文档与代码现状对齐，并记录本次操作。

**本次实际操作**：

- 对照源码确认：
  - `outlook_web/__init__.py` 版本号为 `1.13.0`
  - `outlook_web/db.py` 当前 `DB_SCHEMA_VERSION = 19`（含 v18: accounts 新增 `temp_mail_meta`）
- 修正文档不一致处：
  - `CLAUDE.md`：
    - `outlook_web/__init__.py` 版本号注释 `v1.12.0` → `v1.13.0`
    - `db.py` schema 注释 `v18` → `v19`
    - Database 章节 `schema v18` → `schema v19`
  - `docs/项目地图.md`：
    - “凭据加密（schema v18）” → “（schema v19）”
    - “数据库迁移框架（v18）” → “（v19）”

**说明**：本次仅做“事实对齐”的最小改动，不调整原有结构与叙事。

#### 6. 深读主链路源码并对齐 CF 邮箱池文档（external_pool 路由实际为 claim-random/claim-complete）

**时间**：2026-04-09

**目标**：按“以源码为准”的原则深读邮箱池/CF Provider/外部 API 安全链路，并将 FD/TD 文档中的接口路径与行为描述对齐到当前实现。

**本次实际操作（可核对点）**：

- 深读源码文件（节选）：
  - `outlook_web/routes/external_pool.py`：外部邮箱池路由实际为
    - `POST /api/external/pool/claim-random`
    - `POST /api/external/pool/claim-release`
    - `POST /api/external/pool/claim-complete`
    - `GET  /api/external/pool/stats`
  - `outlook_web/controllers/external_pool.py`：claim-random/complete/release 的参数透传与 audit 逻辑
  - `outlook_web/security/external_api_guard.py`：公网模式下的 IP 白名单、限流、功能开关（feature 禁用）
  - `outlook_web/repositories/pool.py`：provider=cloudflare_temp_mail 时无可用邮箱会动态创建；complete 后按结果非阻塞删除远程 CF 邮箱
  - `outlook_web/services/temp_mail_provider_cf.py`：CF Worker API 适配（x-admin-auth / Bearer jwt），meta 标准化（provider_jwt/provider_mailbox_id/provider_capabilities）

- 文档对齐改动：
  - `docs/FD/2026-04-09-CF临时邮箱接入邮箱池FD.md`
    - 将 `/api/external/pool/claim` 对齐为实际路由 `/api/external/pool/claim-random`
    - 将 `/api/external/pool/complete` 对齐为实际路由 `/api/external/pool/claim-complete`
    - 修正“邮件读取已支持无需改动”的表述，避免与当前 resolver 行为产生误导
  - `docs/TD/2026-04-09-CF临时邮箱接入邮箱池TD.md`
    - 将 external pool 章节中的 `/claim`、`/complete` 路由对齐为 `/claim-random`、`/claim-complete`
    - 将 complete 响应示例调整为“以 controller 实现为准”的兼容表述

**说明**：本次仍坚持“最小必要改动”，只修正与源码不一致的接口路径与高风险误导点。

#### 3. 分支同步与联系方式添加

**时间**：2026-04-09

**分支同步**：
- `Buggithubissue`、`dev`、`feature` 三个分支均已落后 main，无独立提交
- 使用 `git branch -f` + `git push --force` 将所有分支 fast-forward 到 main（`7952820`）
- 注意：三个分支被 worktree 占用（`E:/hushaokang/Data-code/EnsoAi/outlookEmail/` 下），无法 checkout，改用 `git branch -f` 直接重置
- `feature` 无远程分支，仅本地同步

**联系方式**：
- `README.md`：新增"联系方式"章节 → `outlookmailplus@163.com`
- `README.en.md`：新增"Contact"章节 → `outlookmailplus@163.com`

**修改文件**：
- `README.md`：末尾新增联系方式
- `README.en.md`：末尾新增 Contact 章节

**Commits**：
- `301b122`：fix: 移除 sonar-project.properties 中已删除的 fix_format.py 引用
- `7952820`：docs: 添加联系邮箱，同步所有分支到 main

---

#### 2. v1.13.0 发布与 SonarCloud 修复

**时间**：2026-04-09

**版本发布**：
- 版本号：`1.12.0` → `1.13.0`（`outlook_web/__init__.py`）
- 更新 CHANGELOG.md、DEVLOG.md、README.md、README.en.md 版本引用
- 更新 `tests/test_version_update.py` 中所有版本断言和 mock 数据
- 本地 893 测试全部通过（0 failures, 6 skipped）
- CI 全量通过（Python Tests / Code Quality / Docker Build）
- Git Tag `v1.13.0` → 触发 `create-github-release.yml` 自动创建 GitHub Release
- Docker 镜像双仓库推送成功：
  - GHCR: `ghcr.io/zeropointsix/outlook-email-plus:v1.13.0` / `:latest`
  - Docker Hub: `guangshanshui/outlook-email-plus:v1.13.0` / `:latest`
  - Digest: `sha256:8909cf0300c956d2db803157dfdeced2a24e6b6c09c149509f87ae6025ff086d`
  - 架构: `linux/amd64` + `linux/arm64`

**SonarCloud 失败修复**：
- 根因：`sonar-project.properties` 中 `sonar.sources` / `sonar.inclusions` / `sonar.coverage.exclusions` 引用了已删除的 `fix_format.py`
- 该文件在 commit `04824bc` 已删除，但 SonarCloud 配置未同步清理
- 修复：从 3 处配置项中移除 `fix_format.py` 引用
- 同步清理：`docs/项目地图.md` 中可清理项目列表移除 `fix_format.py`

**修改文件**：
- `outlook_web/__init__.py`：版本号 → `1.13.0`
- `tests/test_version_update.py`：版本断言 + mock tag_name
- `CHANGELOG.md`：新增 `[v1.13.0]` 段落
- `docs/DEVLOG.md`：新增 `v1.13.0` 段落
- `README.md` / `README.en.md`：版本引用更新
- `sonar-project.properties`：移除 `fix_format.py` 引用（3 处）
- `docs/项目地图.md`：移除已删除文件记录

---

#### 1. hotupdate-test 分支端到端测试与合并

**时间**：2026-04-09

**背景**：`hotupdate-test` 分支在 `main` 基础上新增 24 个提交，用于热更新功能的端到端验证（Watchtower + Docker API 双模式）。分支使用 GHCR 远程镜像（`ghcr.io/zeropointsix/outlook-email-plus:hotupdate-test`）进行了完整的两种更新方式的实际测试。

**测试环境**：
- 端口 5002：Watchtower 模式（`docker-compose.hotupdate-test.yml`，含 Watchtower sidecar）
- 端口 5003：Docker API 模式（`docker-compose.docker-api-test.yml`，挂载 docker.sock）
- 镜像：`ghcr.io/zeropointsix/outlook-email-plus:hotupdate-test`

**发现并修复的问题**：

| # | 问题 | 修复 | Commit |
|---|------|------|--------|
| 1 | GHCR 镜像不在白名单 | 添加 `ghcr.io/zeropointsix/` 到 ALLOWED_IMAGE_PREFIXES | 早期提交 |
| 2 | 本地镜像检测误判 | 重写 `_looks_like_local_image_ref()` 为 namespace 白名单 | 早期提交 |
| 3 | 版本比较 pre-release 后缀问题 | `_version_gt()` 忽略 `-hotupdate-test` 等后缀 | 早期提交 |
| 4 | Watchtower 连通测试超时 (5s) | 增加到 35s，添加详细注释说明 Watchtower 同步行为 | `6441de2` |
| 5 | Emoji 前缀 i18n 翻译匹配失败 | 在 exactMap 中添加 `🔄`/`🚀` 前缀变体 | `6441de2` |
| 6 | 设置页 Tab 标签缺少翻译 | 添加 基础/临时邮箱/API 安全/自动化 翻译 | `6441de2` |
| 7 | Watchtower 200 响应误判为"更新成功" | 改为 `already_latest: true`（Watchtower 同步完成 → 未更新我们） | `2b49547` |
| 8 | 连通性/更新结果 i18n 缺失 | 添加 连通正常/检查完毕/测试中/更新失败 等翻译 | `2b49547` |
| 9 | 测试断言不匹配 | 更新 `test_watchtower_success` 断言 `already_latest` + `"检查完毕"` | `3672888` |

**合并过程**：

1. 版本号从 `1.12.8-hotupdate-test` 回退至 `1.12.0`（与 main 一致）
2. 删除测试专用 compose 文件（`docker-compose.hotupdate-test.yml`、`docker-compose.docker-api-test.yml`）
3. 移除 CI docker-build-push 中 `hotupdate-test` 分支触发
4. 清理 `start.py` 测试注释、恢复 `WORKSPACE.md`
5. Fast-forward 合并到 main（`6f5c707`）
6. 推送 main、删除远程和本地 `hotupdate-test` 分支
7. 停止并删除所有测试容器和 volume

**Watchtower 同步行为关键发现**：

Watchtower `POST /v1/update` 是**同步接口**——完整执行镜像拉取和 digest 比对后才返回 200。如果我们的容器需要更新，Watchtower 会在返回前 kill 旧容器并启动新容器，因此**我们永远收不到 200 响应**。反过来，如果收到了 200 响应，说明 Watchtower 判定当前已是最新版本，无需更新。

**Watchtower DNS 问题**：

测试环境中 Watchtower 将 `ghcr.io` 解析为 `198.18.2.198`（VPN/代理干扰），导致 HEAD 请求失败，fallback 到完整 pull（需 25-30s），这是连通测试超时需要从 5s 增加到 35s 的根本原因。

---

## 2026-04-07

### 操作记录

#### 7. Docker API 自更新安全策略强化（策略A）

**时间**：2026-04-07 下午

**背景**：原有 Docker API 自更新功能存在安全隐患——本地构建镜像可能误触发更新，导致不可预期的行为。

**目标**：实施策略A（彻底禁止本地构建镜像触发 Docker API 更新），确保只有官方远程镜像才能触发更新。

**实施内容**：

1. **镜像白名单收紧**：
   - 移除 `outlook-email-plus`（无 namespace）白名单项
   - 仅保留 `guangshanshui/outlook-email-plus`官方镜像前缀
   
2. **新增本地构建检测**：
   - `validate_image_for_update()`：镜像白名单 + RepoDigests 检测双重校验
   - `_looks_like_local_image_ref()`：基于 namespace 的启发式本地镜像检测（修复 bug：改为 namespace 白名单判断）
   - `_has_repo_digests()`：通过 Docker API 检查镜像 RepoDigests（本地 build 镜像为空）
   
3. **API 层前置校验**：
   - `_trigger_docker_api_update()` 在触发阶段就获取容器镜像并校验
   - 校验失败返回 403/500，避免等到 spawn updater 内部才失败
   
4. **部署信息展示优化**：
   - `api_deployment_info()` 不再依赖 `DOCKER_SELF_UPDATE_ALLOW` 环境变量
   - 只要 docker.sock 可用就通过 Docker API 获取真实镜像名（更准确）
   
5. **测试用例调整**：
   - `docker-compose.docker-api-test.yml` 镜像改为 `guangshanshui/outlook-email-plus:latest`（形成负向用例：本地 build 但伪装官方名也会被 RepoDigests 检测拦截）

**修改文件**：
- `outlook_web/services/docker_update.py`：
  - 白名单收紧
  - 新增 `validate_image_for_update()`, `_looks_like_local_image_ref()`, `_has_repo_digests()`
  - `get_container_info()` 通过 `client.images.get()` 获取 RepoDigests
  - `spawn_update_helper_container()` 和 `self_update()` 调用新校验函数
  - Bug修复：`_looks_like_local_image_ref()` 改为 namespace 白名单判断（`guangshanshui`, `docker.io/guangshanshui`, `ghcr.io/guangshanshui`）
- `outlook_web/controllers/system.py`：
  - `_trigger_docker_api_update()` API 层镜像校验
  - `api_deployment_info()` 获取镜像名逻辑优化
- `docker-compose.docker-api-test.yml`：测试镜像名调整

**代码逻辑测试结果**（PowerShell环境）：
```
=== 白名单校验 ===
guangshanshui/outlook-email-plus:latest  → ✅ 通过
guangshanshui/outlook-email-plus:test    → ✅ 通过
outlook-email-plus:latest                → ❌ 拦截（无 namespace）
myregistry/outlook-email-plus:latest     → ❌ 拦截（非官方 namespace）

=== 启发式检测 ===
guangshanshui/outlook-email-plus:*       → False（正确识别为官方）
outlook-email-plus:*                     → True（正确识别为本地）
其他namespace/*                          → True（正确识别为非官方）
```

**文档产出**：
- `docs/DEV/manual-acceptance-checklist.md`：人工验收清单（4 个测试用例 + 验收标准 + 快速测试脚本）

**待验收项（当时）**：
- [ ] 负向用例1：本地构建镜像触发更新被拦截
- [ ] 负向用例2：本地构建伪装官方名触发更新被拦截
- [ ] 正向用例3：官方远程镜像成功触发更新流程
- [ ] 部署信息准确性验证

**端到端实际测试记录（Docker Desktop / Windows）**：

环境：
- Docker Desktop 4.43.2（Engine 28.3.2，Context: desktop-linux）
- Docker Compose v2.38.2

执行：
1) 启动负向用例（本地 build + 伪装官方镜像名）：
   - 命令：`docker compose -f docker-compose.docker-api-test.yml up -d --build`
   - 容器：`outlook-dockerapi-test`（端口 5003→5000）
   - 镜像：`guangshanshui/outlook-email-plus:latest`（本地 build）
   - 镜像 RepoDigests：`[]`（确认本地 build 特征）

2) 通过脚本模拟前端触发更新（含 CSRF）：
   - `POST /login` → ✅ success
   - `GET /api/csrf-token` → ✅ 返回 csrf_token
   - `POST /api/system/trigger-update?method=docker_api` + `X-CSRFToken` → ✅ 返回 403
     - message：`检测到本地构建镜像（RepoDigests 为空），已按安全策略禁止 Docker API 一键更新...`
   - 结论：策略A拦截生效；未创建 updater 容器；旧容器未被 stop

3) 正向用例尝试（远程拉取官方镜像）被环境网络阻塞：
   - `docker pull guangshanshui/outlook-email-plus:v1.11.0` → ❌ 超时
   - 错误：`Client.Timeout exceeded while awaiting headers`（auth.docker.io token 请求超时）
   - 影响：无法在当前环境完成“远程镜像 RepoDigests 非空 → 允许触发 updater → self_update 跑完”的正向验收

**结论（阶段性）**：负向端到端已通过；正向端到端当时受 DockerHub 网络访问影响未完成。

---

#### 13. 策略A 正向端到端验收补全：真实“热更新切换”演示（A2 + 远程镜像 tag 变更）

**时间**：2026-04-07 晚

**目标**：补齐策略A的正向端到端验收，验证当远程镜像 tag 指向新 digest 时，A2 updater 能完成完整切换流程：

- pull 最新镜像
- digest 不同 → create 新容器
- stop 旧容器释放端口
- start 新容器 + health
- rename（新容器接管原名称）
- 旧容器保留为 backup（remove_old=false）

**验收环境/对象**：

- 镜像 tag：`guangshanshui/outlook-email-plus:a2-strategyA-canary`
- 初始运行容器：`outlook-canary`（端口 `5005 -> 5000`，挂载 `/var/run/docker.sock`）
- 触发更新方式：应用内接口 `POST /api/system/trigger-update?method=docker_api`（登录 + CSRF）

**关键证据（更新前）**：

- 运行中容器：`outlook-canary`
- 容器使用的 image id（旧）：`sha256:056f69613d8dac7a486ed77a32c8041fb522c4f63d0fad8f6d0149078190e84e`
- 容器镜像引用仍为 tag：`guangshanshui/outlook-email-plus:a2-strategyA-canary`
- 本地同 tag 已被重新打到新镜像（新 image id）：`sha256:21aba8bda26d893f59af319eaeb5a72d06eedfd3b4f521a0d004e2bd9503b2fb`

说明：容器创建时记录的是当时 tag 对应的镜像 ID；后续重新 push 同 tag 后，容器仍显示原 tag，但 image id 不会自动变化，因此能触发“digest 不同 → 更新”。

**触发更新（PowerShell / Invoke-RestMethod，带 session cookie 与 CSRF）**：

```powershell
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession

# 1) 登录（写入 session cookie）
$loginBody = @{ password = 'admin123' } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://localhost:5005/login' -Method Post -ContentType 'application/json' -Body $loginBody -WebSession $session

# 2) 获取 CSRF token
$csrf = (Invoke-RestMethod -Uri 'http://localhost:5005/api/csrf-token' -Method Get -WebSession $session).csrf_token

# 3) 触发 Docker API 更新（A2 helper）
Invoke-RestMethod -Uri 'http://localhost:5005/api/system/trigger-update?method=docker_api' -Method Post -Headers @{ 'X-CSRFToken' = $csrf } -WebSession $session
```

接口返回（关键字段）：

```json
{"success": true, "message": "更新任务已启动: oep-updater-1775571256 (e21bf4afbbdb)"}
```

**关键证据（更新后）**：

1) `outlook-canary` 名称仍存在，且重新变为运行态并健康：

- 新容器 ID（short）：`e0ba3c44dcc9`
- 新容器 image id：`sha256:21aba8bda26d893f59af319eaeb5a72d06eedfd3b4f521a0d004e2bd9503b2fb`
- 端口仍为：`0.0.0.0:5005->5000/tcp`

2) 旧容器被 rename 为 backup 并退出（符合 A2 设计：保留旧容器便于回滚）：

- 旧容器名称：`outlook-canary_backup_1775571270`
- 旧容器 image id：`sha256:056f69613d8dac7a486ed77a32c8041fb522c4f63d0fad8f6d0149078190e84e`
- 状态：Exited(0)

3) `/healthz` 访问正常（证明新容器已接管服务）：

```json
{"status":"ok","version":"1.12.0","boot_id":"1775571264516-7"}
```

**结论**：策略A + A2 helper 的“正向端到端热更新切换”已完成，验证了 digest 变化场景下的 stop/start/rename/backup 全链路行为。

**关联 Issue/PR**：待 Docker 容器内实际验收通过后提交

---

#### 1. mystatus 插件状态确认

**背景**：尝试使用 `mystatus` 工具查询 AI 账户配额使用情况。

**实际情况**：

| 项目 | 状态 |
|------|------|
| 插件安装 | `opencode-mystatus@1.2.4` 已安装于全局 `~/.config/opencode/node_modules/` |
| 全局配置 | `~/.config/opencode/opencode.json` 已注册 `plugin` 和 `command` |
| 项目配置 | 项目级 `opencode.json` 未单独配置 mystatus 插件（使用全局配置） |
| 工具可用性 | 当前会话工具列表中**未注册** `mystatus` 工具，无法直接调用 |

**配置位置**：

- 全局插件配置：`C:\Users\PLA30\.config\opencode\opencode.json`
  ```json
  "plugin": ["opencode-mystatus"],
  "command": {
    "mystatus": {
      "description": "Query quota usage for all AI accounts",
      "template": "Use the mystatus tool to query quota usage. Return the result as-is without modification."
    }
  }
  ```
- 插件源码位置：`C:\Users\PLA30\.config\opencode\node_modules\opencode-mystatus\`

**支持平台**：

| Platform | Account Type |
|----------|-------------|
| OpenAI | Plus / Team / Pro |
| Zhipu AI | Coding Plan |
| Z.ai | Coding Plan |
| GitHub Copilot | Individual / Business |
| Google Cloud | Antigravity |

**结论**：`mystatus` 作为 opencode 插件需要在 opencode 运行时环境中通过 `/mystatus` 命令或自然语言触发，当前通过外部 Agent 调用时无法直接使用该工具。

#### 2. 热更新功能开发状态确认

**关联文档**：
- AI 提示词：`docs/DEV/hot-update-ai-prompt.md`
- 基线记录：`docs/DEV/hot-update-baseline.md`

**功能概述**：为 Outlook Email Plus 实现 Docker 部署环境下的一键更新功能，支持 Watchtower 和 Docker API 两种更新方式。

**实施进度（全部已完成）**：

| 阶段 | 内容 | 状态 | Commit |
|------|------|------|--------|
| Phase 1 | BUG 修复（Token 为空启动失败、浏览器缓存旧 JS） | ✅ | 91a8f35 |
| Phase 2 | UI 提示优化（镜像标签/构建模式检测） | ✅ | 91a8f35 |
| Phase 3 | 内置 Docker API 自更新 | ✅ | 91a8f35 |
| P0 | BUG-006 GitHub 仓库地址修复 | ✅ | e6d27b6 |

**核心产出**：
- 新增：`outlook_web/services/docker_update.py`（591 行，经代码验证 2026-04-07，原文档记录 839 行已修正）
- 新增 API：`/api/system/version-check`、`/api/system/trigger-update`、`/api/system/test-watchtower`、`/api/system/deployment-info`
- 新增设置项：`watchtower_url`、`watchtower_token`（加密存储）、`update_method`
- 前端：版本更新 Banner、Watchtower 配置 UI、Docker API 更新方式选择
- 前端补齐：设置页一键更新区域的部署信息警告（`/api/system/deployment-info` → `#deploymentWarnings`）
- 安全：默认关闭 Docker API 自更新、镜像白名单校验、审计日志

**当前版本**：v1.12.0，热更新验证已通过（v1.12.0 → v1.12.1）

#### 3. 文档更新

- 创建 `WORKSPACE.md` 工作区操作记录文档
- 确认项目结构：项目级 `opencode.json` 仅配置了子代理（context-retriever, small-task-executor），mystatus 依赖全局配置
- 记录热更新功能完整实施状态

#### 4. 热更新文档代码验证与清理

**操作内容**：

1. **代码验证**：逐一对比 `hot-update-ai-prompt.md` 中的描述与实际代码
   - ✅ 4 个 API 端点全部存在且已注册路由
   - ✅ `update_method` 设置项 GET/PUT 支持
   - ✅ 静态文件缓存控制 `set_static_cache_control()` 
   - ✅ GitHub 仓库地址 `ZeroPointSix/outlookEmailPlus`
   - ✅ `docker-compose.yml` 配置完整（Token 默认值、docker.sock 注释、DOCKER_SELF_UPDATE_ALLOW）
   - ✅ `.env.example` 模板完整
   - ⚠️ **发现差异**：`docker_update.py` 实际 591 行，文档记录为 839 行 → **已修正**

2. **文档清理**：清理 `hot-update-ai-prompt.md`
   - 删除"待实施任务 (可选扩展)"部分（第 154-318 行），该部分重复了已完成的 Phase 1-3 任务描述
   - 新增"代码验证记录"表格，记录 13 项验证结果
   - 修正 `docker_update.py` 行数为实际值 591
   - 保留"参考文件清单"和"注意事项"部分

**已修改文件**：
- `docs/DEV/hot-update-ai-prompt.md` — 删除冗余内容，新增验证记录，修正数据

#### 5. README 生产配置更新

**操作内容**：
- 更新 `README.md` 中 docker-compose 生产配置示例，同步 Phase 3 新功能
  - 新增 `DOCKER_SELF_UPDATE_ALLOW` 环境变量（注释状态）
  - 新增 docker.sock 挂载选项（注释状态）
  - 新增"更新方式"说明段落，指导用户如何切换 Watchtower/Docker API 模式
- 修正 README "最近更新"版本号：v1.11.0 → v1.12.0
- 新增"一键更新"功能说明段落

**已修改文件**：
- `README.md` — 版本号更新、docker-compose 示例更新、功能说明补充

#### 6. 热更新功能完整性详细分析

**结论：功能已完整实现**，所有文档描述的功能点均在代码中找到对应实现。

**后端功能验证（全部 ✅）**：

| 功能 | 位置 | 状态 |
|------|------|------|
| 版本检测 API（10 分钟缓存） | system.py:353 | ✅ |
| 更新触发 API（双模式） | system.py:402 | ✅ |
| Watchtower 更新（DB→env fallback + 加密 Token） | system.py:438 | ✅ |
| Docker API 更新（安全检查→socket→白名单→12 步流程） | system.py:500 + docker_update.py | ✅ |
| 部署信息检测（镜像/标签/本地构建/Watchtower 连通性） | system.py:561 | ✅ |
| Watchtower 连通性测试 | system.py:732 | ✅ |
| 设置项 update_method（GET/PUT） | settings.py:351/1013 | ✅ |
| 静态文件缓存控制 | app.py:124 | ✅ |

**前端功能验证（全部 ✅）**：

| 功能 | 位置 | 状态 |
|------|------|------|
| 页面加载版本检查 | main.js:3763 `checkVersionUpdate()` | ✅ |
| 双模式触发更新 + 差异化超时 | main.js:3790 `triggerUpdate()` (120s/10s) | ✅ |
| 重启轮询等待 | main.js:3880 `waitForRestart()` | ✅ |
| 部署信息警告渲染（设置页） | main.js: `loadDeploymentInfo()` / `renderDeploymentWarnings()` | ✅ |
| Watchtower 连通性测试 | main.js:2169 `testWatchtower()` | ✅ |
| 设置加载/保存 update_method | main.js:1743/2100 | ✅ |

**Docker API 自更新 12 步流程（docker_update.py）**：

| 步骤 | 函数 | 状态 |
|------|------|------|
| 1. 启用开关检查 | `is_docker_api_enabled()` | ✅ |
| 2. Socket 可访问性 | `check_docker_socket()` | ✅ |
| 3. 获取当前容器信息 | `get_current_container_info()` | ✅ |
| 4. 镜像名白名单校验 | `validate_image_name()` | ✅ |
| 5. 拉取最新镜像 | `pull_latest_image()` | ✅ |
| 6. Digest 比较 | `compare_image_digest()` | ✅ |
| 7. 创建新容器（复制配置） | `create_new_container()` + `_parse_volumes()` + `_parse_ports()` | ✅ |
| 8. 启动新容器 | `start_new_container()` | ✅ |
| 9. 健康检查 | `health_check_new_container()` | ✅ |
| 10. 停止旧容器 | `stop_old_container()` | ✅ |
| 11. 重命名容器 | `rename_containers()` | ✅ |
| 12. 清理/保留旧容器 | `cleanup_old_container()` | ✅ |

**发现的问题（非阻塞）**：

| # | 问题 | 严重度 | 说明 |
|---|------|--------|------|
| 1 | `can_auto_update` 未考虑 Docker API 模式 | 低 | `api_deployment_info()` 中 `can_auto_update` 仅检查 Watchtower 连通性，用户选 Docker API 模式且无 Watchtower 时会误报为不可更新 |
| 2 | `self_update()` 同步调用风险 | 低 | system.py:531 注释说明同步调用可能中断响应，但 Docker API 模式下前端有 120s 超时 + `waitForRestart()` 轮询兜底 |
| 3 | `docker-compose.hotupdate-test.yml` 含硬编码密钥 | 低 | 测试专用文件，不影响生产安全 |

#### 7. 热更新功能非阻塞问题修复

**修复 #1：`can_auto_update` 逻辑支持 Docker API 模式**

- **文件**：`outlook_web/controllers/system.py`
- **问题**：`api_deployment_info()` 中 `can_auto_update` 仅检查 Watchtower 连通性
- **修复**：新增 `docker_api_available` 检测（检查 `DOCKER_SELF_UPDATE_ALLOW` + socket 可用性），`can_auto_update` 逻辑改为 `watchtower_reachable or docker_api_available`
- **新增返回字段**：`deployment.docker_api_available`（布尔值）

**修复 #2：`self_update()` 同步→异步**

- **文件**：`outlook_web/controllers/system.py`
- **问题**：`_trigger_docker_api_update()` 同步调用 `self_update()`，旧容器被停止时响应无法到达客户端
- **修复**：使用 `threading.Thread(daemon=True)` 在后台线程执行自更新，主线程立即返回 `{"success": True, "message": "Docker API 自更新已启动，容器即将重启"}`
- **审计日志**：移入后台线程，确保更新结果被记录
- **前端兼容**：前端已有 `waitForRestart()` 轮询 `/healthz` 等待新容器启动，无需修改

**修复 #3：清理测试配置硬编码密钥**

- **文件**：`docker-compose.hotupdate-test.yml`
- **问题**：SECRET_KEY 和 WATCHTOWER_HTTP_API_TOKEN 为硬编码明文值
- **修复**：改为 `${SECRET_KEY:-please-change-this-secret-key-for-testing}` 和 `${WATCHTOWER_HTTP_API_TOKEN:-test-hotupdate-token}` 格式，支持 `.env` 文件注入
- **附加**：更新文件头注释（移除版本号引用，添加使用方式说明）

**已修改文件汇总**：
- `outlook_web/controllers/system.py` — can_auto_update 逻辑 + self_update 异步化
- `docker-compose.hotupdate-test.yml` — 密钥环境变量化

#### 8. README 环境变量补充

**操作内容**：
- 在 `README.md` 的"常用环境变量"部分新增"一键更新相关"小节
- 补充环境变量说明：
  - `WATCHTOWER_HTTP_API_TOKEN` — Watchtower API 鉴权令牌
  - `WATCHTOWER_API_URL` — Watchtower API 地址
  - `DOCKER_SELF_UPDATE_ALLOW` — 是否启用 Docker API 自更新
  - `DOCKER_IMAGE` — 当前容器镜像名（可选）
- 添加安全提示说明 Docker API 自更新的风险

**已修改文件**：
- `README.md` — 新增一键更新相关环境变量说明

#### 9. 一键更新功能人工验收 BUG 分析

**分析范围**：dev 分支相对于 main 分支新增的一键更新功能

**功能概述**：
- 版本检测：GET `/api/system/version-check`，对比 GitHub 最新 release 与本地版本
- 触发更新：POST `/api/system/trigger-update?method=watchtower|docker_api`
- Watchtower 配置：设置页可配置 URL + Token（加密存储）
- Docker API 自更新：12 步流程（拉取镜像→创建容器→健康检查→切换）

**潜在 BUG 分析**：

| # | 问题描述 | 严重度 | 复现条件 | 影响 | 建议处理 |
|---|---------|--------|----------|------|----------|
| 1 | **镜像名检测依赖 DOCKER_IMAGE 环境变量** | 低 | 未设置 DOCKER_IMAGE 时 | `api_deployment_info()` 无法准确获取镜像名，可能显示 `unknown` | 可接受，用户可手动设置 |
| 2 | **容器名冲突风险** | 低 | Docker API 自更新失败后重试 | 新容器使用 `{name}_new` 临时名称，若上次失败未清理可能冲突 | 代码中已有 force 删除逻辑，风险较低 |
| 3 | **审计日志在后台线程中记录** | 低 | Docker API 自更新 | 若新容器启动后旧容器被停止，审计日志写入数据库时机可能不稳定 | 非阻塞，日志可能丢失但不影响功能 |
| 4 | **前端超时固定 120s** | 信息 | Docker API 大镜像拉取 | 若镜像很大，拉取时间超过 120s，前端可能误报超时（但后台仍在执行） | 可接受，前端会继续轮询 `/healthz` |

**健康检查说明**：
- `docker_update.py` 中的 `health_check_new_container()` 检查的是 Docker 容器状态和 Docker 原生 healthcheck
- 前端 `waitForRestart()` 轮询的 `/healthz` 端点是应用级健康检查（已存在于 `system.py:39`）
- 两者是独立的：容器启动后，后端健康检查通过 → 前端轮询 `/healthz` 确认应用可用

**验收建议**：

1. **Watchtower 模式验收**：
   - [ ] 部署 docker-compose（含 watchtower 服务）
   - [ ] 在设置页配置 Watchtower URL + Token
   - [ ] 点击"测试连通性"按钮，确认返回成功
   - [ ] 触发版本检测，确认 Banner 显示
   - [ ] 点击"立即更新"，确认容器重启

2. **Docker API 模式验收**：
   - [ ] 修改 docker-compose 启用 `DOCKER_SELF_UPDATE_ALLOW=true`
   - [ ] 挂载 `/var/run/docker.sock`
   - [ ] 在设置页切换"更新方式"为 Docker API
   - [ ] 确认部署信息显示 `docker_api_available: true`
   - [ ] 触发更新，确认 12 步流程正常执行

3. **边界条件验收**：
   - [ ] 使用固定版本标签（如 `:v1.12.0`），确认 UI 警告正确
   - [ ] 本地构建镜像，确认 UI 警告正确
   - [ ] 未配置 Watchtower Token，确认错误提示

**结论**：一键更新功能已基本完整，无阻塞性 BUG。建议按上述验收清单进行人工测试。

#### 10. Docker API 自更新实测发现阻塞 BUG 并修复（dev 分支）

**实测背景**：尝试在 Docker 容器中调用 `/api/system/trigger-update?method=docker_api` 做完整 12 步自更新模拟。

**实际问题**：接口直接返回 500。

- 容器日志报错：`ModuleNotFoundError: No module named 'outlook_web.models'`
- 根因：`outlook_web/controllers/system.py::_trigger_docker_api_update()` 中错误引用 `from outlook_web.models import AuditLog`，但项目不存在 `outlook_web/models.py` 以及 `AuditLog` 类

**修复策略（方案 A）**：移除 `AuditLog` 依赖。

- 主线程：使用现有 `outlook_web.audit.log_audit()` 记录一次 `trigger_docker_api_update_start`（含 method/remove_old/username）
- 后台线程：仅执行 `docker_update.self_update()` 并写入应用日志（logger），避免后台线程依赖 Flask request context / DB 连接

**修改文件**：
- `outlook_web/controllers/system.py` — 移除 `outlook_web.models.AuditLog` 引用，改用 `log_audit`

---

#### 11. A2 方案实现：按需 helper job 容器（避免"自杀"问题）

**背景问题**：Docker API 模式实测发现核心阻塞——容器无法在内部 stop 自己后继续执行后续步骤（进程被杀死）。原始方案使用 daemon 线程在后台执行 self_update()，但旧容器被 stop 的瞬间后台线程也会被杀死，导致"create 新容器→stop 旧→rename→cleanup"流程中断。

**方案选型**：

| 方案 | 描述 | 优势 | 劣势 |
|------|------|------|------|
| A1: 两阶段脚本 | app 容器内写脚本→nohup 后台执行→exit | 最简单 | 可靠性差，进程管理困难 |
| **A2: 按需 helper job 容器** | app 通过 Docker API 临时创建 updater 容器 | 可靠、隔离、auto_remove 自动清理 | 短暂 2 容器并存 |
| A3: 外部 updater 服务 | 额外部署常驻 updater 容器 | 最稳 | 增加部署复杂度 |

**选定方案**：A2（按需 helper job 容器）

**架构设计**：

```
┌─────────────────────────────┐
│  App 容器（用户请求）          │
│                             │
│  1. 鉴权 + 安全校验            │
│  2. 记录审计日志（主线程）       │
│  3. Docker API 创建 updater 容器│
│  4. 立即返回 HTTP 响应          │
└─────────────┬───────────────┘
              │ docker.sock
              ▼
┌─────────────────────────────┐
│  Updater 容器（短生命周期）     │
│                             │
│  1. sleep(2) 等 HTTP 响应     │
│  2. pull 最新镜像              │
│  3. create 新容器（复制配置）   │
│  4. stop 旧容器（释放端口）     │
│  5. start 新容器               │
│  6. healthcheck 新容器         │
│  7. rename 容器                │
│  8. cleanup 旧容器             │
│  9. 退出 → auto_remove 自动清理 │
└─────────────────────────────┘
```

**关键设计决策**：

1. **start_delay_seconds=2**：updater 容器启动后延迟 2 秒再执行更新操作，给 app 容器的 HTTP 响应留出到达客户端的时间
2. **先 stop 旧容器再 start 新容器**：解决 host port 映射场景下端口冲突问题（docker-compose 常见 5000:5000 映射）
3. **auto_remove=True**：updater 容器退出后自动删除，保持"单容器部署体验"
4. **失败回滚**：新容器启动失败或健康检查失败时，尝试恢复旧容器
5. **透传 Docker 凭证**：支持 DOCKER_AUTH_CONFIG / DOCKER_CONFIG 环境变量，确保 updater 可拉取私有镜像
6. **Watchtower 排除**：updater 容器添加 `com.centurylinklabs.watchtower.enable=false` 标签

**新增/修改文件清单**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `outlook_web/services/docker_update_helper.py` | **新增**（69 行） | updater 容器入口模块，读取环境变量调用 `self_update()` |
| `outlook_web/services/docker_update.py` | 修改 | 新增 `get_container_info()`、`spawn_update_helper_container()`；增强 `validate_image_name()` 支持 digest 和 registry port；增强 volumes 解析支持 named volume；`self_update()` 新增 `target_container_id` 参数；调整步骤顺序（先 stop 旧再 start 新）；失败时尝试恢复旧容器 |
| `outlook_web/controllers/system.py` | 修改 | `healthz()` 新增 `boot_id` 和 `version` 字段；`_trigger_docker_api_update()` 改为调用 `spawn_update_helper_container()`；`api_deployment_info()` 增强 Docker API 检测和上下文感知警告 |
| `static/js/main.js` | 修改 | `waitForRestart()` 增加 boot_id 变化检测；Docker API 模式超时放宽到 180s；`triggerUpdate()` 统一走 waitForRestart 逻辑；`loadSettings()` 触发部署信息加载；新增 `loadDeploymentInfo()` / `renderDeploymentWarnings()`；语言切换时重渲染部署警告 |
| `templates/index.html` | 修改 | 新增 `#deploymentWarnings` 容器；微调缩进格式 |
| `tests/test_error_and_trace.py` | 修改 | 适配 healthz 新增 `boot_id` / `version` 字段 |
| `tests/test_smoke_contract.py` | 修改 | 适配 healthz 新增字段 |
| `docker-compose.docker-api-test.yml` | **新增**（45 行） | Docker API 模式专用测试 compose 配置 |
| `docker-compose.hotupdate-test.yml` | 修改 | 新增 DOCKER_IMAGE 环境变量 |

**self_update() 步骤顺序调整**：

原方案（先 start 新再 stop 旧）在 host port 映射场景下会产生端口冲突：

```
原: pull → compare → get_info → validate → pull_image → compare_digest → create → start_new → health_check → stop_old → rename → cleanup
新: pull → compare → get_info → validate → pull_image → compare_digest → create → stop_old → start_new → health_check → rename → cleanup
```

**前端轮询优化**：

通过 `boot_id`（`{timestamp}-{pid}`）判断容器是否发生了真正的进程重启：
- 首次轮询前记录 `initialBootId`
- 后续轮询中检测 `boot_id` 是否变化
- `boot_id` 变化 或 `seenDown`（曾看到服务不可用）时判定为重启完成

#### 12. A2 方案本地 Docker 验证（dev 分支）

**验证环境**：
- Docker Desktop 4.43.2 (Engine 28.3.2)
- 本地构建镜像 `outlook-email-a2-test:latest`（基于 dev 分支源码）
- 容器名 `outlook-dockerapi-test`，端口映射 5003:5000
- 挂载 docker.sock，DOCKER_SELF_UPDATE_ALLOW=true

**验证步骤与结果**：

| # | 测试项 | 结果 | 说明 |
|---|--------|------|------|
| 1 | `healthz` 返回 `boot_id` + `version` | ✅ | `{"status":"ok","boot_id":"1775563642828-8","version":"1.12.0"}` — A2 代码已生效 |
| 2 | 登录 + CSRF token 获取 | ✅ | Cookie-based session + X-CSRFToken |
| 3 | 部署信息 API | ✅ | `docker_api_available:true`，`is_local_build:true`，警告正确 |
| 4 | 触发更新 API（白名单校验） | ✅ | 返回 `"镜像名不在白名单内: outlook-email-a2-test:latest"` — 正确拦截 |
| 5 | Docker socket 连通性 | ✅ | `check_docker_socket()` 返回可用 |
| 6 | 容器内省 `get_container_info()` | ✅ | 返回完整容器信息（name/image/volumes/networks/restart_policy） |
| 7 | updater 容器创建 + 运行 + auto_remove | ✅ | 容器创建成功 → 正常运行 → 退出后自动删除 |
| 8 | 完整 helper 流程 (`python -m docker_update_helper`) | ✅ | 步骤 1-3 通过（权限/socket/容器信息），步骤 4 白名单拦截（本地构建镜像），原容器完好 |

**关键发现**：

1. **A2 核心逻辑完全通过**：updater 容器可以由 app 容器通过 docker.sock 创建、运行、自动清理
2. **白名单机制正常**：本地构建镜像被正确拦截，不会误更新
3. **auto_remove 有效**：updater 容器退出后自动删除，保持"单容器体验"
4. **原容器保护有效**：即使更新流程被拦截，原容器状态不受影响（status=running）
5. **无法端到端验证 pull→create→stop→start→rename**：因为本地构建镜像无法从远程 registry pull；完整流程需在真实远程镜像环境下验证

**清理**：
- 停止并删除测试容器和 volume
- 删除临时测试脚本 `test_a2_spawn.py` / `test_a2_helper.py`
- 删除本地测试镜像 `outlook-email-a2-test:latest`

**结论**：A2 方案的核心逻辑（updater 容器创建、运行、自动清理、白名单保护）已全部验证通过。完整端到端测试（含 pull→create→stop→start→rename）需在远程镜像环境下进行。

---

### 待办：本地端到端测试指南

> 以下是用户自行在本地进行端到端测试的完整步骤，覆盖 Watchtower 模式和 Docker API 模式。

#### 前提条件

1. Docker Desktop 运行中（Engine 28.x+）
2. dev 分支最新代码
3. 端口 5002、5003 未被占用

#### 方式一：Docker API 模式测试（A2 方案核心验证）

```bash
# 1. 构建本地镜像（含 A2 代码改动）
docker compose -f docker-compose.docker-api-test.yml up -d --build

# 2. 等待容器启动（约 20 秒）
# 查看健康状态
docker ps --filter "name=outlook-dockerapi-test"

# 3. 浏览器访问
# 打开 http://localhost:5003
# 使用密码 admin123 登录

# 4. 测试验证项
# 4a. 访问 /healthz 确认 boot_id 和 version 字段
#     浏览器直接访问 http://localhost:5003/healthz
#     期望: {"status":"ok","boot_id":"...","version":"1.12.0"}

# 4b. 进入"设置"→"自动化"→"一键更新"
#     - 切换更新方式为"Docker API"
#     - 确认看到部署信息警告（本地构建提示/Docker API 可用提示）
#     - 点击"立即更新"按钮
#     期望: 弹出"镜像名不在白名单内"错误（本地构建镜像无法自动更新，这是正确行为）

# 5. 测试完毕后清理
docker compose -f docker-compose.docker-api-test.yml down -v
docker rmi outlook-email-a2-test:latest  # 清理本地测试镜像
```

**注意**：本地构建镜像无法完成完整 pull→create→stop→start→rename 流程，因为远程 registry 没有 `outlook-email-a2-test` 镜像。白名单校验会正确拦截。

#### 方式二：Watchtower 模式测试（原有功能回归验证）

```bash
# 1. 启动 app + watchtower 双容器
docker compose -f docker-compose.hotupdate-test.yml up -d

# 2. 等待容器启动（约 20 秒）
docker ps --filter "name=outlook-hotupdate-test"

# 3. 浏览器访问 http://localhost:5002
# 使用密码 admin123 登录

# 4. 测试验证项
# 4a. 进入"设置"→"自动化"→"一键更新"
#     - 确认 Watchtower 配置显示
#     - 点击"测试连通性"
#     期望: 返回"连接成功"

# 4b. 点击"检查更新"（页面顶部或设置页）
#     期望: 显示当前版本和最新版本信息

# 4c. 点击"立即更新"
#     期望: 按钮变为"等待容器重启..."，前端轮询 /healthz
#     注意: 如果已是最新版本，Watchtower 不会触发容器重建

# 5. 测试完毕后清理
docker compose -f docker-compose.hotupdate-test.yml down -v
```

#### 方式三：远程镜像 + Docker API 端到端测试（最完整，需发布新版本）

```bash
# 1. 先提交 A2 代码到 dev 分支
# 2. 合并到 main 并发布新版本（如 v1.13.0）
# 3. 等待 Docker Hub 镜像发布
# 4. 使用远程镜像启动容器

docker run -d \
  --name oep-e2e-test \
  -p 5004:5000 \
  -e SECRET_KEY=test-secret-key \
  -e LOGIN_PASSWORD=admin123 \
  -e DOCKER_SELF_UPDATE_ALLOW=true \
  -e SCHEDULER_AUTOSTART=true \
  -v /var/run/docker.sock:/var/run/docker.sock \
  guangshanshui/outlook-email-plus:v1.13.0

# 5. 浏览器访问 http://localhost:5004，登录
# 6. 设置 → 自动化 → 一键更新 → 切换到 Docker API 模式
# 7. 点击"立即更新"
#    期望:
#    - 后端创建 updater 容器 (oep-updater-xxxxx)
#    - updater 容器 pull 最新镜像
#    - 如果有新版本：stop 旧容器 → create/start 新容器 → rename → cleanup
#    - 如果已是最新：返回"镜像已是最新，无需更新"
#    - 前端检测到 boot_id 变化 → 刷新页面

# 8. 清理
docker rm -f oep-e2e-test
```

#### 关键验证检查清单

- [ ] `GET /healthz` 返回 `boot_id` + `version`
- [ ] `GET /api/system/deployment-info` 返回正确的部署信息
- [ ] `docker_api_available` 在挂载 docker.sock 时为 true
- [ ] 更新方式切换 UI 正常（Watchtower ↔ Docker API）
- [ ] 部署警告根据更新方式动态变化（Watchtower 不可达时 info vs error）
- [ ] 触发更新时 CSRF 保护正常
- [ ] 白名单校验正确拦截非白名单镜像
- [ ] updater 容器创建成功并正确退出
- [ ] 前端 waitForRestart 轮询正常（boot_id 变化检测）
- [ ] 语言切换时部署警告重渲染

#### 13. 生成功能验证提示词（给其他 AI 审查用）

**操作内容**：
- 创建 `VERIFICATION_PROMPT.md`，包含 A2 方案的完整功能验证提示词
- 覆盖 5 大类验证点（后端 API / Docker 服务 / 前端 / 安全 / 边界条件），共 30+ 个具体检查项
- 附带改动文件清单和已知限制说明
- 用于交给其他 AI 审查代码变更的完整性和正确性

**已新增文件**：
- `VERIFICATION_PROMPT.md` — 功能验证提示词

---

### 待办：项目文件归类清理（暂缓，提交后执行）

> 以下为扫描项目结构后的清理建议，待 dev 分支提交后再执行。

#### 需删除的文件

| 文件 | 原因 |
|------|------|
| `fix_format.py` | 一次性格式修复脚本，已完成使命 |
| `NUL` | Windows 空文件，已在 .gitignore |
| `EhushaokangData-codeoutlookEmailserver.log` | 日志文件（文件名异常），已在 .gitignore |
| `-p/` 空目录 | 空目录，无内容 |
| `.ruff_cache/` | Linter 缓存目录 |

#### 需移动归类的文件

| 文件 | 目标位置 |
|------|---------|
| `注册与邮箱池接口文档.md` | → `docs/API/注册与邮箱池接口文档.md` |
| `registration-mail-pool-api.en.md` | → `docs/API/registration-mail-pool-api.en.md` |
| `VERIFICATION_PROMPT.md` | → `docs/DEV/VERIFICATION_PROMPT.md` |
| `docs/2026-04-05-设置页面重构-AI执行提示词.md` | → `docs/DEV/` 或删除 |

#### .gitignore 需补充

```
.ruff_cache/
-p/
```

**执行结果**（Commit: `04824bc`）：
- ✅ 删除 `fix_format.py`
- ✅ 移动 `注册与邮箱池接口文档.md` → `docs/API/`
- ✅ 移动 `registration-mail-pool-api.en.md` → `docs/API/`
- ✅ 移动 `VERIFICATION_PROMPT.md` → `docs/DEV/`
- ✅ 移动 `设置页面重构-AI执行提示词.md` → `docs/DEV/`
- ✅ `.gitignore` 补充 `.ruff_cache/` 和 `-p/`
- 注：`NUL`、`-p/`、`.ruff_cache/`、`Ehushaokang...server.log` 已在 .gitignore 中，物理文件已被清理

---

### 历史记录：A2 方案开发期间的修改清单（已合并至 main）

> 以下修改已通过 `hotupdate-test` 分支合并到 main（2026-04-09），此处仅作历史参考。

| 文件 | 修改类型 | 说明 |
|------|---------|------|
| `outlook_web/services/docker_update_helper.py` | **新增** | updater 容器入口模块 |
| `outlook_web/services/docker_update.py` | Modified | helper 容器创建、步骤顺序调整、失败回滚 |
| `outlook_web/controllers/system.py` | Modified | A2 触发逻辑、healthz 增强、部署信息增强 |
| `static/js/main.js` | Modified | boot_id 检测、部署警告渲染、超时优化 |
| `templates/index.html` | Modified | deploymentWarnings 容器 |
| `tests/test_error_and_trace.py` | Modified | 适配 healthz 新字段 |
| `tests/test_smoke_contract.py` | Modified | 适配 healthz 新字段 |
| `docs/DEV/hot-update-ai-prompt.md` | Modified | 文档清理 + 补充 |
| `docs/DEV/hot-update-baseline.md` | Modified | 文档补充 |
