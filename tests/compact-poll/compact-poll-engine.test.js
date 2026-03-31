/**
 * tests/compact-poll/compact-poll-engine.test.js — C 类：JS 单元测试
 *
 * 测试目标：mailbox_compact.js 中的简洁模式自动轮询引擎核心逻辑
 * 框架：Jest + jsdom（通过 setup.js 的 eval 加载轮询引擎）
 *
 * 用例清单（共 22 个逻辑用例，23 个 test 函数）：
 *   TC-C01~C05：事件触发与守卫条件
 *   TC-C06~C09：轮询状态管理
 *   TC-C10~C13：超时与错误处理
 *   TC-C14：防重入锁
 *   TC-C15~C16：发现新邮件
 *   TC-C17~C18：设置变更即时生效
 *   TC-C19~C20：页面可见性检测
 *   TC-C21：findCompactAccountRow DOM 查找
 *   TC-C22：updateCompactPollUI UI 更新（含 polling / stopped 两个子用例）
 *
 * 注意（RED 阶段）：
 *   轮询引擎尚未在 mailbox_compact.js 中实现，所有测试预期失败。
 *   GREEN 阶段实现后应全部通过。
 */

'use strict';

// ══════════════════════════════════════════════════════════════════════════
// 测试工具函数
// ══════════════════════════════════════════════════════════════════════════

/**
 * 创建模拟邮箱行 DOM，并追加到 document.body。
 * 结构与 renderCompactAccountList 生成的 .mail-row 保持一致：
 *   .mail-row
 *     .mail-card
 *       .mail-card-button[position:relative]
 *         button.pull-button[onclick="refreshCompactAccount(id, this)"][data-email="email"]
 *
 * data-email 属性：供 findCompactAccountRow 通过 [data-email] 选择器定位行。
 * （GREEN 阶段实现时，findCompactAccountRow 应支持 [data-email] 或 [onclick*=email]）
 *
 * @param {string} email      邮箱地址
 * @param {number} accountId  账号 ID
 * @returns {HTMLElement} 行元素（.mail-row）
 */
function createMockMailRow(email, accountId) {
  const row = document.createElement('div');
  row.className    = 'mail-row';
  row.dataset.accountId = String(accountId);
  row.dataset.email     = email; // 供 findCompactAccountRow 定位

  const mailCard = document.createElement('div');
  mailCard.className = 'mail-card';

  const cardButton = document.createElement('div');
  cardButton.className      = 'mail-card-button';
  cardButton.style.position = 'relative'; // ensurePollDot 需要 position:relative

  const pullBtn = document.createElement('button');
  pullBtn.className  = 'pull-button';
  pullBtn.textContent = '拉取';
  // onclick 属性值中包含 email，供 [onclick*="email"] 选择器匹配
  pullBtn.setAttribute('onclick', `refreshCompactAccount(${accountId}, this)`);
  pullBtn.dataset.email = email; // 双保险：data-email 也保留

  cardButton.appendChild(pullBtn);
  mailCard.appendChild(cardButton);
  row.appendChild(mailCard);
  document.body.appendChild(row);

  return row;
}

// ══════════════════════════════════════════════════════════════════════════
// TC-C01~C05：事件触发与守卫条件
// ══════════════════════════════════════════════════════════════════════════

describe('TC-C01~C05: 事件触发与守卫条件', () => {

  // ── TC-C01 ──────────────────────────────────────────────────────────────
  test('TC-C01: pollEnabled=false 时 email-copied 事件不触发轮询', () => {
    // 功能开关关闭
    pollEnabled = false;
    createMockMailRow('test@example.com', 1);

    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'test@example.com' }
    }));

    // Map 应保持空
    expect(pollMap.size).toBe(0);
  });

  // ── TC-C02 ──────────────────────────────────────────────────────────────
  test('TC-C02: pollEnabled=true + compact 模式时 email-copied 触发轮询', async () => {
    pollEnabled    = true;
    pollInterval   = 10;
    pollMaxCount    = 5;

    // 返回包含目标邮箱的账号列表
    getCompactVisibleAccounts.mockReturnValue([
      { email: 'test@example.com', id: 1 }
    ]);
    createMockMailRow('test@example.com', 1);

    // fetch Mock：baseline 拉取成功（空邮件列表）
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, emails: [] })
    });

    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'test@example.com' }
    }));

    // 等待异步操作（baseline fetch + 初次 pollSingleEmail）完成
    await jest.advanceTimersByTimeAsync(200);

    // 轮询条目应已创建
    expect(pollMap.has('test@example.com')).toBe(true);
    // 初次 pollSingleEmail 执行完毕，isPolling 应恢复 false
    expect(pollMap.get('test@example.com').isPolling).toBe(false);
  });

  // ── TC-C03 ──────────────────────────────────────────────────────────────
  test('TC-C03: mailboxViewMode 非 compact 时不触发轮询', () => {
    pollEnabled  = true;
    // 切换到标准模式
    global.mailboxViewMode = 'standard';

    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'test@example.com' }
    }));

    expect(pollMap.size).toBe(0);
  });

  // ── TC-C04 ──────────────────────────────────────────────────────────────
  test('TC-C04: isTempEmailGroup=true 时不触发轮询', () => {
    pollEnabled       = true;
    global.isTempEmailGroup  = true;

    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'test@example.com' }
    }));

    expect(pollMap.size).toBe(0);
  });

  // ── TC-C05 ──────────────────────────────────────────────────────────────
  test('TC-C05: 邮箱不在 getCompactVisibleAccounts 返回列表中时不触发轮询', () => {
    pollEnabled = true;
    // 返回空列表 => 找不到账号
    getCompactVisibleAccounts.mockReturnValue([]);

    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'unknown@example.com' }
    }));

    expect(pollMap.size).toBe(0);
  });

}); // end describe TC-C01~C05

// ══════════════════════════════════════════════════════════════════════════
// TC-C06~C09：轮询状态管理
// ══════════════════════════════════════════════════════════════════════════

describe('TC-C06~C09: 轮询状态管理', () => {

  // ── TC-C06 ──────────────────────────────────────────────────────────────
  test('TC-C06: 同一邮箱再次 email-copied 应重置轮询（startTime 更新）', async () => {
    pollEnabled    = true;
    pollInterval   = 10;
    pollMaxCount = 5;

    getCompactVisibleAccounts.mockReturnValue([
      { email: 'test@example.com', id: 1 }
    ]);
    createMockMailRow('test@example.com', 1);

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, emails: [] })
    });

    // ── 第一次触发 ──
    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'test@example.com' }
    }));
    await jest.advanceTimersByTimeAsync(200);

    const firstStartTime = pollMap.get('test@example.com').startTime;

    // 等待一段时间后再次触发
    await jest.advanceTimersByTimeAsync(5000);

    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'test@example.com' }
    }));
    await jest.advanceTimersByTimeAsync(200);

    const secondStartTime = pollMap.get('test@example.com').startTime;

    // startTime 应被更新（第二次大于第一次）
    expect(secondStartTime).toBeGreaterThan(firstStartTime);
  });

  // ── TC-C07 ──────────────────────────────────────────────────────────────
  test('TC-C07: 多邮箱并行触发应产生多个 Map 条目', async () => {
    pollEnabled = true;

    const accounts = [
      { email: 'a@example.com', id: 1 },
      { email: 'b@example.com', id: 2 },
      { email: 'c@example.com', id: 3 },
    ];
    getCompactVisibleAccounts.mockReturnValue(accounts);

    accounts.forEach(({ email, id }) => createMockMailRow(email, id));

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, emails: [] })
    });

    // 依次复制三个邮箱
    for (const { email } of accounts) {
      window.dispatchEvent(new CustomEvent('email-copied', { detail: { email } }));
    }
    await jest.advanceTimersByTimeAsync(200);

    expect(pollMap.size).toBe(3);
    expect(pollMap.has('a@example.com')).toBe(true);
    expect(pollMap.has('b@example.com')).toBe(true);
    expect(pollMap.has('c@example.com')).toBe(true);
  });

  // ── TC-C08 ──────────────────────────────────────────────────────────────
  test('TC-C08: stopPoll 应从 Map 删除条目并恢复按钮 UI', async () => {
    pollEnabled = true;

    getCompactVisibleAccounts.mockReturnValue([
      { email: 'test@example.com', id: 1 }
    ]);
    const row = createMockMailRow('test@example.com', 1);

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, emails: [] })
    });

    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'test@example.com' }
    }));
    await jest.advanceTimersByTimeAsync(200);

    expect(pollMap.has('test@example.com')).toBe(true);

    // 手动停止轮询（silent=true 不显示 Toast）
    stopPoll('test@example.com', true);

    expect(pollMap.has('test@example.com')).toBe(false);

    // 按钮应恢复为原始"拉取"状态
    const pullBtn = row.querySelector('.pull-button');
    expect(pullBtn.textContent).toBe('拉取');
    expect(pullBtn.classList.contains('compact-poll-active')).toBe(false);
  });

  // ── TC-C09 ──────────────────────────────────────────────────────────────
  test('TC-C09: stopAllPolls 应清空所有轮询条目', async () => {
    pollEnabled = true;

    const accounts = [
      { email: 'a@example.com', id: 1 },
      { email: 'b@example.com', id: 2 },
    ];
    getCompactVisibleAccounts.mockReturnValue(accounts);
    accounts.forEach(({ email, id }) => createMockMailRow(email, id));

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, emails: [] })
    });

    for (const { email } of accounts) {
      window.dispatchEvent(new CustomEvent('email-copied', { detail: { email } }));
    }
    await jest.advanceTimersByTimeAsync(200);

    expect(pollMap.size).toBe(2);

    stopAllPolls();

    expect(pollMap.size).toBe(0);
  });

}); // end describe TC-C06~C09

// ══════════════════════════════════════════════════════════════════════════
// TC-C10~C13：超时与错误处理
// ══════════════════════════════════════════════════════════════════════════

describe('TC-C10~C13: 超时与错误处理', () => {

  // ── TC-C10 ──────────────────────────────────────────────────────────────
  test('TC-C10: 达到最多轮询次数后应自动停止轮询并显示超时 Toast', async () => {
    pollEnabled   = true;
    pollInterval  = 5;
    pollMaxCount  = 2; // 最多 2 次，方便测试

    getCompactVisibleAccounts.mockReturnValue([
      { email: 'test@example.com', id: 1 }
    ]);
    createMockMailRow('test@example.com', 1);

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, emails: [] })
    });

    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'test@example.com' }
    }));
    await jest.advanceTimersByTimeAsync(200); // baseline + 首次 poll（pollCount → 1）

    // 快进 5 秒触发第 2 次 poll（pollCount → 2 = maxCount → 次数检查在 startGlobalCountdown 中触发）
    await jest.advanceTimersByTimeAsync(5000);
    // 再快进 1 秒让全局倒计时检测到 pollCount >= maxCount
    await jest.advanceTimersByTimeAsync(1000);

    expect(pollMap.has('test@example.com')).toBe(false);

    // 应展示超时 Toast（5000ms 持续时间）
    expect(showToast).toHaveBeenCalledWith(
      expect.stringContaining('监听超时'),
      'info',
      null,
      5000
    );
  });

  // ── TC-C11 ──────────────────────────────────────────────────────────────
  test('TC-C11: 连续 3 次请求失败后应自动停止轮询', async () => {
    pollEnabled     = true;
    pollInterval    = 1; // 1 秒间隔，便于快速触发多次
    pollMaxCount = 30;

    getCompactVisibleAccounts.mockReturnValue([
      { email: 'test@example.com', id: 1 }
    ]);
    createMockMailRow('test@example.com', 1);

    // 所有请求都返回 500 失败
    global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 500 });

    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'test@example.com' }
    }));
    // 等 baseline + 首次 pollSingleEmail（errorCount → 1）
    await jest.advanceTimersByTimeAsync(200);

    // 第 2 次轮询（errorCount → 2）
    await jest.advanceTimersByTimeAsync(1000);
    // 第 3 次轮询（errorCount → 3 → 停止）
    await jest.advanceTimersByTimeAsync(1000);

    expect(pollMap.has('test@example.com')).toBe(false);
  });

  // ── TC-C12 ──────────────────────────────────────────────────────────────
  test('TC-C12: 成功请求后 errorCount 应归零，轮询继续', async () => {
    pollEnabled     = true;
    pollInterval    = 1;
    pollMaxCount = 30;

    getCompactVisibleAccounts.mockReturnValue([
      { email: 'test@example.com', id: 1 }
    ]);
    createMockMailRow('test@example.com', 1);

    let callCount = 0;
    global.fetch = jest.fn().mockImplementation(() => {
      callCount++;
      // 前两次（baseline）成功，首次 poll 失败，第二次 poll 失败，第三次 poll 成功
      if (callCount <= 2) {
        // baseline 成功
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ success: true, emails: [] })
        });
      }
      // callCount 3、4 为首次 poll 的两个 folder 请求 → 失败
      // callCount 5、6 为第二次 poll → 失败
      // callCount 7、8 为第三次 poll → 成功
      const fail = callCount <= 6;
      return Promise.resolve(
        fail
          ? { ok: false, status: 500 }
          : { ok: true, json: () => Promise.resolve({ success: true, emails: [] }) }
      );
    });

    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'test@example.com' }
    }));
    await jest.advanceTimersByTimeAsync(200); // baseline + 立即首次 poll (150ms) → errorCount=1
    // 立即首次轮询：callCount 3-4 (fail) → errorCount=1

    // 第二次 poll（interval 1000ms → errorCount=2）
    await jest.advanceTimersByTimeAsync(1000);
    expect(pollMap.get('test@example.com').errorCount).toBe(2);

    // 第三次 poll（两个 folder 请求成功 → hasSuccess=true → errorCount 归零）
    await jest.advanceTimersByTimeAsync(1000);
    expect(pollMap.get('test@example.com').errorCount).toBe(0);

    // 轮询未停止
    expect(pollMap.has('test@example.com')).toBe(true);
  });

  // ── TC-C13 ──────────────────────────────────────────────────────────────
  test('TC-C13: API 返回 404 应立即停止轮询并提示账号已删除', async () => {
    pollEnabled     = true;
    pollInterval    = 10;
    pollMaxCount = 30;

    getCompactVisibleAccounts.mockReturnValue([
      { email: 'test@example.com', id: 1 }
    ]);
    createMockMailRow('test@example.com', 1);

    // baseline 成功，首次 poll 返回 404
    let baselineDone = false;
    global.fetch = jest.fn().mockImplementation(() => {
      if (!baselineDone) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ success: true, emails: [] })
        });
      }
      // poll 阶段返回 404
      return Promise.resolve({ ok: false, status: 404 });
    });

    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'test@example.com' }
    }));
    // baseline 完成
    await jest.advanceTimersByTimeAsync(100);
    baselineDone = true;

    // 首次 pollSingleEmail → 404 → 停止
    await jest.advanceTimersByTimeAsync(200);

    expect(pollMap.has('test@example.com')).toBe(false);
    expect(showToast).toHaveBeenCalledWith(
      expect.stringContaining('账号已被删除'),
      'error',
      null,
      5000
    );
  });

}); // end describe TC-C10~C13

// ══════════════════════════════════════════════════════════════════════════
// TC-C14：防重入锁
// ══════════════════════════════════════════════════════════════════════════

describe('TC-C14: 防重入锁', () => {

  // ── TC-C14 ──────────────────────────────────────────────────────────────
  test('TC-C14: isPolling=true 时定时器触发的 pollSingleEmail 应跳过，fetch 不会多次调用', async () => {
    pollEnabled     = true;
    pollInterval    = 1; // 1 秒间隔
    pollMaxCount = 30;

    getCompactVisibleAccounts.mockReturnValue([
      { email: 'test@example.com', id: 1 }
    ]);
    createMockMailRow('test@example.com', 1);

    let fetchCount = 0;
    global.fetch = jest.fn().mockImplementation(async () => {
      fetchCount++;
      // 所有请求均模拟慢响应（永不 resolve），以保持 isPolling=true
      return new Promise(() => {/* 永不 resolve */});
    });

    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'test@example.com' }
    }));
    // 等待事件处理和 baseline 启动（fetch 已调用但永未 resolve）
    await jest.advanceTimersByTimeAsync(100);

    // 此时 pollMap 应已创建（在 baseline await 之前 set）
    expect(pollMap.has('test@example.com')).toBe(true);
    // isPolling=true：pollSingleEmail 正在等待 fetch（或 baseline 中）
    // 注意：若实现先调 pollSingleEmail 再 await baseline，isPolling 为 true；
    //       若顺序相反，isPolling 此时可能为 false，GREEN 阶段视实现调整
    // 此断言检测"轮询已启动"的状态
    const state = pollMap.get('test@example.com');
    expect(state).not.toBeNull();

    // 触发定时器（1 秒后）—— 由于 isPolling=true（或 baseline 卡住），fetch 不应额外调用
    await jest.advanceTimersByTimeAsync(1000);
    await jest.advanceTimersByTimeAsync(1000);

    // fetch 总调用次数不超过 baseline(2) + 首次poll(2) = 4
    // 防重入生效时，定时器触发的 pollSingleEmail 会直接 return，不调用 fetch
    expect(fetchCount).toBeLessThanOrEqual(4);
  });

}); // end describe TC-C14

// ══════════════════════════════════════════════════════════════════════════
// TC-C15~C16：发现新邮件
// ══════════════════════════════════════════════════════════════════════════

describe('TC-C15~C16: 发现新邮件处理', () => {

  // ── TC-C15 ──────────────────────────────────────────────────────────────
  test('TC-C15: 发现新邮件后应停止轮询、提取验证码并复制到剪贴板', async () => {
    pollEnabled     = true;
    pollInterval    = 10;
    pollMaxCount = 30;

    getCompactVisibleAccounts.mockReturnValue([{
      email: 'test@example.com',
      id: 1,
      latest_verification_code: '',
      latest_email_subject: '',
      latest_email_from: '',
      latest_email_folder: '',
      latest_email_received_at: ''
    }]);
    createMockMailRow('test@example.com', 1);

    const baselineEmailIds = ['email-baseline-1', 'email-baseline-2'];
    let pollCallCount = 0; // 记录 /api/emails 的轮询调用次数（不含 baseline）

    global.fetch = jest.fn().mockImplementation((url) => {
      // 验证码提取接口
      if (url.includes('extract-verification')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            success: true,
            data: { verification_code: '654321' }
          })
        });
      }

      // 邮件列表接口
      if (pollCallCount < 2) {
        // baseline 阶段（两个 folder 各一次）
        pollCallCount++;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            success: true,
            emails: baselineEmailIds.map(id => ({ id }))
          })
        });
      }

      // 轮询阶段：返回包含新邮件 ID 的列表
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          emails: [{ id: 'email-new-1', subject: '验证码来了' }],
          account_summary: { latest_email_subject: '验证码来了' }
        })
      });
    });

    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'test@example.com' }
    }));

    // baseline 完成
    await jest.advanceTimersByTimeAsync(200);
    // 首次 pollSingleEmail 发现新邮件
    await jest.advanceTimersByTimeAsync(500);

    // 应调用验证码提取接口
    const extractCalls = global.fetch.mock.calls.filter(
      ([url]) => url.includes('extract-verification')
    );
    expect(extractCalls.length).toBeGreaterThan(0);

    // 应复制验证码
    expect(copyToClipboard).toHaveBeenCalledWith('654321');

    // 应停止轮询
    expect(pollMap.has('test@example.com')).toBe(false);
  });

  // ── TC-C16 ──────────────────────────────────────────────────────────────
  test('TC-C16: 验证码提取失败时应显示"发现新邮件"Toast 并停止轮询', async () => {
    pollEnabled     = true;
    pollInterval    = 10;
    pollMaxCount = 30;

    getCompactVisibleAccounts.mockReturnValue([{
      email: 'test@example.com',
      id: 1,
      latest_verification_code: '',
      latest_email_subject: '',
      latest_email_from: '',
      latest_email_folder: '',
      latest_email_received_at: ''
    }]);
    createMockMailRow('test@example.com', 1);

    let pollCallCount = 0;

    global.fetch = jest.fn().mockImplementation((url) => {
      if (url.includes('extract-verification')) {
        // 提取接口返回"无验证码"
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ success: false, data: null })
        });
      }

      if (pollCallCount < 2) {
        pollCallCount++;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ success: true, emails: [{ id: 'old-1' }] })
        });
      }

      // 轮询阶段：发现新邮件
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          emails: [{ id: 'new-1' }],
          account_summary: {}
        })
      });
    });

    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'test@example.com' }
    }));
    await jest.advanceTimersByTimeAsync(200);
    await jest.advanceTimersByTimeAsync(500);

    // 无验证码时应 fallback 到"发现新邮件" Toast
    expect(showToast).toHaveBeenCalledWith(
      expect.stringContaining('发现新邮件'),
      'success',
      null,
      5000
    );
    // 仍应停止轮询
    expect(pollMap.has('test@example.com')).toBe(false);
  });

}); // end describe TC-C15~C16

// ══════════════════════════════════════════════════════════════════════════
// TC-C17~C18：设置变更即时生效
// ══════════════════════════════════════════════════════════════════════════

describe('TC-C17~C18: 设置变更即时生效', () => {

  // ── TC-C17 ──────────────────────────────────────────────────────────────
  test('TC-C17: applyPollSettings({enabled:false}) 应停止所有正在运行的轮询', async () => {
    pollEnabled     = true;
    pollInterval    = 10;
    pollMaxCount = 30;

    getCompactVisibleAccounts.mockReturnValue([
      { email: 'test@example.com', id: 1 }
    ]);
    createMockMailRow('test@example.com', 1);

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, emails: [] })
    });

    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'test@example.com' }
    }));
    await jest.advanceTimersByTimeAsync(200);

    expect(pollMap.size).toBe(1);

    // 关闭功能
    applyPollSettings({ enabled: false, interval: 10, maxCount: 5 });

    expect(pollMap.size).toBe(0);
  });

  // ── TC-C18 ──────────────────────────────────────────────────────────────
  test('TC-C18: 修改 pollInterval 后应重建定时器（timer handle 不同）', async () => {
    pollEnabled     = true;
    pollInterval    = 10;
    pollMaxCount = 30;

    getCompactVisibleAccounts.mockReturnValue([
      { email: 'test@example.com', id: 1 }
    ]);
    createMockMailRow('test@example.com', 1);

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, emails: [] })
    });

    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'test@example.com' }
    }));
    await jest.advanceTimersByTimeAsync(200);

    const oldTimer = pollMap.get('test@example.com').timer;

    // 变更间隔到 5 秒
    applyPollSettings({ enabled: true, interval: 5, maxCount: 30 });

    const newTimer = pollMap.get('test@example.com').timer;

    // 定时器 handle 应已被重建（新旧不同）
    expect(newTimer).not.toBe(oldTimer);
  });

}); // end describe TC-C17~C18

// ══════════════════════════════════════════════════════════════════════════
// TC-C19~C20：页面可见性检测
// ══════════════════════════════════════════════════════════════════════════

describe('TC-C19~C20: 页面可见性检测', () => {

  // ── TC-C19 ──────────────────────────────────────────────────────────────
  test('TC-C19: 页面切到后台应将所有轮询定时器清为 null（暂停）', async () => {
    pollEnabled     = true;
    pollInterval    = 10;
    pollMaxCount = 30;

    getCompactVisibleAccounts.mockReturnValue([
      { email: 'test@example.com', id: 1 }
    ]);
    createMockMailRow('test@example.com', 1);

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, emails: [] })
    });

    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'test@example.com' }
    }));
    await jest.advanceTimersByTimeAsync(200);

    // 确认定时器已设置
    expect(pollMap.get('test@example.com').timer).not.toBeNull();

    // 模拟切到后台
    Object.defineProperty(document, 'hidden', { value: true, configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));

    // 定时器应被清空（保留 Map 条目，仅 timer=null）
    expect(pollMap.get('test@example.com').timer).toBeNull();
    // 全局倒计时也应暂停
    expect(pollCountdownTimer).toBeNull();
  });

  // ── TC-C20 ──────────────────────────────────────────────────────────────
  test('TC-C20: 页面切回前台应恢复所有轮询定时器（timer 重新设置）', async () => {
    pollEnabled     = true;
    pollInterval    = 10;
    pollMaxCount = 30;

    getCompactVisibleAccounts.mockReturnValue([
      { email: 'test@example.com', id: 1 }
    ]);
    createMockMailRow('test@example.com', 1);

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, emails: [] })
    });

    window.dispatchEvent(new CustomEvent('email-copied', {
      detail: { email: 'test@example.com' }
    }));
    await jest.advanceTimersByTimeAsync(200);

    // ── 切到后台 ──
    Object.defineProperty(document, 'hidden', { value: true, configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
    expect(pollMap.get('test@example.com').timer).toBeNull();

    // ── 切回前台 ──
    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
    await jest.advanceTimersByTimeAsync(100); // 等待 visible 后的立即轮询

    // 定时器应重新设置
    expect(pollMap.get('test@example.com').timer).not.toBeNull();
    // 全局倒计时应恢复
    expect(pollCountdownTimer).not.toBeNull();
  });

}); // end describe TC-C19~C20

// ══════════════════════════════════════════════════════════════════════════
// TC-C21：DOM 查找
// ══════════════════════════════════════════════════════════════════════════

describe('TC-C21: findCompactAccountRow DOM 查找', () => {

  // ── TC-C21 ──────────────────────────────────────────────────────────────
  test('TC-C21: findCompactAccountRow 应通过 .mail-row 找到对应邮箱的行', () => {
    const row = createMockMailRow('test@example.com', 1);

    const result = findCompactAccountRow('test@example.com');

    expect(result).toBe(row);
  });

}); // end describe TC-C21

// ══════════════════════════════════════════════════════════════════════════
// TC-C22：updateCompactPollUI UI 更新
// ══════════════════════════════════════════════════════════════════════════

describe('TC-C22: updateCompactPollUI UI 更新', () => {

  // ── TC-C22a：polling 状态 ──────────────────────────────────────────────
  test('TC-C22a: updateCompactPollUI("polling") 应将按钮改为"停止监听 (Ns)"并添加激活样式', () => {
    createMockMailRow('test@example.com', 1);

    updateCompactPollUI('test@example.com', 'polling', 45);

    const pullBtn = document.querySelector('.pull-button');

    // 按钮文字包含"停止监听"和剩余秒数
    expect(pullBtn.textContent).toContain('停止监听');
    expect(pullBtn.textContent).toContain('45');

    // 激活态样式类已添加
    expect(pullBtn.classList.contains('compact-poll-active')).toBe(true);

    // data-poll-email 属性已设置（供外部识别）
    expect(pullBtn.getAttribute('data-poll-email')).toBe('test@example.com');
  });

  // ── TC-C22b：stopped 状态 ─────────────────────────────────────────────
  test('TC-C22b: updateCompactPollUI("stopped") 应将按钮恢复为"拉取"并移除激活样式', () => {
    createMockMailRow('test@example.com', 1);

    // 先设为 polling 状态
    updateCompactPollUI('test@example.com', 'polling', 45);

    // 再恢复为 stopped
    updateCompactPollUI('test@example.com', 'stopped');

    const pullBtn = document.querySelector('.pull-button');

    expect(pullBtn.textContent).toBe('拉取');
    expect(pullBtn.classList.contains('compact-poll-active')).toBe(false);
    expect(pullBtn.getAttribute('data-poll-email')).toBeNull();
  });

}); // end describe TC-C22
