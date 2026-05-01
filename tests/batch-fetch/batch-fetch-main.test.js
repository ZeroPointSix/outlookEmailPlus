/**
 * tests/batch-fetch/batch-fetch-main.test.js — B 类：前端行为测试
 *
 * 测试目标：
 *   - 标准模式批量拉取邮件的账号解析
 *   - latest-only `inbox + junkemail` 请求编排
 *   - 缓存回写与当前视图刷新
 *   - 失败不中断与进度提示
 *
 * 注意：
 *   当前套件已覆盖 Issue #55 的主要行为回归，包括账号级统计、
 *   专用错误文案和 `account_summary` 回写。
 */

'use strict';

function createAccount(id, email) {
  return {
    id,
    email,
    account_type: 'outlook',
    provider: 'outlook',
  };
}

function createSuccessPayload({ folder, subject, summary }) {
  return {
    success: true,
    emails: [
      {
        id: `${folder}-1`,
        subject,
        from: 'noreply@example.com',
        date: '2030-01-01T00:00:00Z',
      },
    ],
    method: 'Graph API',
    has_more: false,
    account_summary: summary || {
      latest_email_subject: subject,
      latest_email_folder: folder,
    },
  };
}

function createFailurePayload(message) {
  return {
    success: false,
    error: {
      code: 'EMAIL_FETCH_FAILED',
      message,
    },
  };
}

function okJson(payload) {
  return {
    ok: true,
    json: async () => payload,
  };
}

describe('Issue #55 批量拉取邮件行为', () => {
  test('TC-B01: resolveSelectedAccountsForBatchFetch 应跨分组扫描 accountsCache', () => {
    expect(typeof resolveSelectedAccountsForBatchFetch).toBe('function');

    selectedAccountIds = new Set([101, 202]);
    accountsCache = {
      1: [createAccount(101, 'alpha@example.com')],
      2: [createAccount(202, 'beta@example.com')],
      3: [createAccount(303, 'ignored@example.com')],
    };

    const accounts = resolveSelectedAccountsForBatchFetch();

    expect(accounts).toEqual([
      expect.objectContaining({ id: 101, email: 'alpha@example.com' }),
      expect.objectContaining({ id: 202, email: 'beta@example.com' }),
    ]);
  });

  test('TC-B02: batchFetchSelectedEmails 应为每个账号预热 inbox + junkemail 缓存', async () => {
    expect(typeof resolveSelectedAccountsForBatchFetch).toBe('function');
    expect(typeof batchFetchSelectedEmails).toBe('function');

    selectedAccountIds = new Set([101, 202]);
    accountsCache = {
      1: [createAccount(101, 'alpha@example.com')],
      2: [createAccount(202, 'beta@example.com')],
    };

    fetch
      .mockResolvedValueOnce(okJson(createSuccessPayload({ folder: 'inbox', subject: 'alpha inbox' })))
      .mockResolvedValueOnce(okJson(createSuccessPayload({ folder: 'junkemail', subject: 'alpha junk' })))
      .mockResolvedValueOnce(okJson(createSuccessPayload({ folder: 'inbox', subject: 'beta inbox' })))
      .mockResolvedValueOnce(okJson(createSuccessPayload({ folder: 'junkemail', subject: 'beta junk' })));

    const accounts = resolveSelectedAccountsForBatchFetch();
    await batchFetchSelectedEmails(accounts);

    expect(fetch).toHaveBeenCalledTimes(4);
    expect(fetch.mock.calls.map(call => call[0])).toEqual([
      '/api/emails/alpha%40example.com?folder=inbox&skip=0&top=10',
      '/api/emails/alpha%40example.com?folder=junkemail&skip=0&top=10',
      '/api/emails/beta%40example.com?folder=inbox&skip=0&top=10',
      '/api/emails/beta%40example.com?folder=junkemail&skip=0&top=10',
    ]);
    expect(emailListCache['alpha@example.com_inbox']).toEqual(expect.objectContaining({ emails: expect.any(Array) }));
    expect(emailListCache['alpha@example.com_junkemail']).toEqual(expect.objectContaining({ emails: expect.any(Array) }));
    expect(emailListCache['beta@example.com_inbox']).toEqual(expect.objectContaining({ emails: expect.any(Array) }));
    expect(emailListCache['beta@example.com_junkemail']).toEqual(expect.objectContaining({ emails: expect.any(Array) }));
    expect(syncAccountSummaryToAccountCache).toHaveBeenCalledWith(
      'alpha@example.com',
      expect.objectContaining({ latest_email_subject: 'alpha inbox' }),
    );
    expect(syncAccountSummaryToAccountCache).toHaveBeenCalledWith(
      'beta@example.com',
      expect.objectContaining({ latest_email_subject: 'beta inbox' }),
    );
  });

  test('TC-B02b: showBatchFetchConfirm 在未选中账号时应提示专用文案', () => {
    expect(typeof showBatchFetchConfirm).toBe('function');

    selectedAccountIds = new Set();

    showBatchFetchConfirm();

    expect(showToast).toHaveBeenCalledWith('请选择要批量拉取邮件的账号', 'error');
  });

  test('TC-B03: 当前账号与当前文件夹双命中时才刷新右侧列表', async () => {
    expect(typeof batchFetchSelectedEmails).toBe('function');

    currentAccount = 'alpha@example.com';
    currentFolder = 'inbox';
    selectedAccountIds = new Set([101]);
    accountsCache = {
      1: [createAccount(101, 'alpha@example.com')],
    };

    fetch
      .mockResolvedValueOnce(okJson(createSuccessPayload({ folder: 'inbox', subject: 'alpha inbox' })))
      .mockResolvedValueOnce(okJson(createSuccessPayload({ folder: 'junkemail', subject: 'alpha junk' })));

    const accounts = resolveSelectedAccountsForBatchFetch();
    await batchFetchSelectedEmails(accounts);

    expect(renderEmailList).toHaveBeenCalledTimes(1);
    expect(currentEmails).toEqual(expect.any(Array));
    expect(currentAccount).toBe('alpha@example.com');
  });

  test('TC-B04: 当前账号未命中时不刷新右侧列表', async () => {
    expect(typeof batchFetchSelectedEmails).toBe('function');

    currentAccount = 'watching@example.com';
    currentFolder = 'inbox';
    selectedAccountIds = new Set([101]);
    accountsCache = {
      1: [createAccount(101, 'alpha@example.com')],
    };

    fetch
      .mockResolvedValueOnce(okJson(createSuccessPayload({ folder: 'inbox', subject: 'alpha inbox' })))
      .mockResolvedValueOnce(okJson(createSuccessPayload({ folder: 'junkemail', subject: 'alpha junk' })));

    const accounts = resolveSelectedAccountsForBatchFetch();
    await batchFetchSelectedEmails(accounts);

    expect(renderEmailList).not.toHaveBeenCalled();
    expect(currentAccount).toBe('watching@example.com');
  });

  test('TC-B05: 单个 folder 失败时按账号部分成功处理，后续账号继续执行', async () => {
    expect(typeof batchFetchSelectedEmails).toBe('function');

    selectedAccountIds = new Set([101, 202]);
    accountsCache = {
      1: [createAccount(101, 'alpha@example.com')],
      2: [createAccount(202, 'beta@example.com')],
    };

    fetch
      .mockResolvedValueOnce(okJson(createSuccessPayload({ folder: 'inbox', subject: 'alpha inbox' })))
      .mockResolvedValueOnce(okJson(createFailurePayload('alpha junk failed')))
      .mockResolvedValueOnce(okJson(createSuccessPayload({ folder: 'inbox', subject: 'beta inbox' })))
      .mockResolvedValueOnce(okJson(createSuccessPayload({ folder: 'junkemail', subject: 'beta junk' })));

    const accounts = resolveSelectedAccountsForBatchFetch();
    await batchFetchSelectedEmails(accounts);

    expect(fetch).toHaveBeenCalledTimes(4);
    expect(emailListCache['alpha@example.com_inbox']).toBeDefined();
    expect(emailListCache['alpha@example.com_junkemail']).toBeUndefined();
    expect(emailListCache['beta@example.com_inbox']).toBeDefined();
    expect(emailListCache['beta@example.com_junkemail']).toBeDefined();
    const finalToastMessage = showToast.mock.calls[showToast.mock.calls.length - 1][0];
    expect(finalToastMessage).toContain('成功 2');
    expect(finalToastMessage).toContain('失败 0');
    expect(finalToastMessage).not.toContain('alpha@example.com');
    expect(showToast).toHaveBeenLastCalledWith(finalToastMessage, 'success');
  });

  test('TC-B06: 单个账号全部失败时不自动切换当前账号，且后续账号继续处理', async () => {
    expect(typeof batchFetchSelectedEmails).toBe('function');

    currentAccount = 'watching@example.com';
    currentFolder = 'inbox';
    selectedAccountIds = new Set([101, 202]);
    accountsCache = {
      1: [createAccount(101, 'alpha@example.com')],
      2: [createAccount(202, 'beta@example.com')],
    };

    fetch
      .mockRejectedValueOnce(new Error('alpha inbox network failed'))
      .mockRejectedValueOnce(new Error('alpha junk network failed'))
      .mockResolvedValueOnce(okJson(createSuccessPayload({ folder: 'inbox', subject: 'beta inbox' })))
      .mockResolvedValueOnce(okJson(createSuccessPayload({ folder: 'junkemail', subject: 'beta junk' })));

    const accounts = resolveSelectedAccountsForBatchFetch();
    await batchFetchSelectedEmails(accounts);

    expect(fetch).toHaveBeenCalledTimes(4);
    expect(currentAccount).toBe('watching@example.com');
    expect(emailListCache['beta@example.com_inbox']).toBeDefined();
    expect(emailListCache['beta@example.com_junkemail']).toBeDefined();
    const finalToastMessage = showToast.mock.calls[showToast.mock.calls.length - 1][0];
    expect(finalToastMessage).toContain('成功 1');
    expect(finalToastMessage).toContain('失败 1');
    expect(finalToastMessage).toContain('alpha@example.com');
  });

  test('TC-B07: 批量执行过程中应驱动持久 Toast 进度更新', async () => {
    expect(typeof batchFetchSelectedEmails).toBe('function');

    selectedAccountIds = new Set([101]);
    accountsCache = {
      1: [createAccount(101, 'alpha@example.com')],
    };

    fetch
      .mockResolvedValueOnce(okJson(createSuccessPayload({ folder: 'inbox', subject: 'alpha inbox' })))
      .mockResolvedValueOnce(okJson(createSuccessPayload({ folder: 'junkemail', subject: 'alpha junk' })));

    const accounts = resolveSelectedAccountsForBatchFetch();
    await batchFetchSelectedEmails(accounts);

    expect(showPersistentToast).toHaveBeenCalledWith(expect.any(String), '正在批量拉取邮件 0 / 1');
    expect(updatePersistentToast).toHaveBeenLastCalledWith(expect.any(String), '正在批量拉取邮件 1 / 1');
    expect(showToast).toHaveBeenLastCalledWith('批量拉取完成：成功 1，失败 0', 'success');
  });
});
