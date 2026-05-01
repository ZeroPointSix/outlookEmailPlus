/**
 * tests/batch-fetch/setup.js — 批量拉取邮件 Jest 全局 Mock 设置
 *
 * 职责：
 *   1. 提供 main.js 在 jsdom 中加载所需的最小全局依赖
 *   2. 使用 fs.readFileSync + 间接 eval 装载整个 main.js
 *   3. 在每个测试前重置批量拉取相关状态与 DOM
 *
 * 注意（RED 阶段）：
 *   Issue #55 逻辑尚未在 main.js 中实现时，
 *   showBatchFetchConfirm / batchFetchSelectedEmails 等符号可能不存在；
 *   对应行为测试预期失败，这是 TDD 红灯阶段的正常现象。
 */

'use strict';

const fs = require('fs');
const path = require('path');

global.CSS = { escape: (s) => String(s) };

class LocalStorageMock {
  constructor() {
    this.store = {};
  }

  getItem(key) {
    return Object.prototype.hasOwnProperty.call(this.store, key) ? this.store[key] : null;
  }

  setItem(key, value) {
    this.store[key] = String(value);
  }

  removeItem(key) {
    delete this.store[key];
  }

  clear() {
    this.store = {};
  }
}

global.localStorage = new LocalStorageMock();
try {
  Object.defineProperty(window, 'localStorage', { configurable: true, value: global.localStorage });
} catch (_) {
  // jsdom 可能已定义
}

global.fetch = jest.fn();
global.confirm = jest.fn(() => true);
global.alert = jest.fn();
window.fetch = global.fetch;
window.confirm = global.confirm;
window.alert = global.alert;

global.translateAppTextLocal = (text) => String(text == null ? '' : text);
global.translateAppText = (text) => String(text == null ? '' : text);
window.translateAppText = global.translateAppText;
window.getCurrentUiLanguage = () => 'zh';
global.getUiLanguage = () => 'zh';
global.formatSelectedItemsLabel = (count) => `已选 ${count} 项`;
global.escapeHtml = (text) => String(text == null ? '' : text);
global.escapeJs = (text) => String(text == null ? '' : text)
  .replace(/\\/g, '\\\\')
  .replace(/'/g, "\\'")
  .replace(/"/g, '\\"')
  .replace(/</g, '\\u003C')
  .replace(/>/g, '\\u003E');
global.sortEmailsByNewestFirst = (list) => Array.isArray(list) ? list.slice() : [];
global.handleApiError = jest.fn();
global.showErrorDetailModal = jest.fn();
global.renderEmailList = jest.fn();
global.renderAccountList = jest.fn();
global.renderCompactAccountList = jest.fn();
global.renderCompactGroupStrip = jest.fn();
global.updateTopbar = jest.fn();
global.updateSelectAllCheckbox = jest.fn();
global.syncAccountSummaryToAccountCache = jest.fn();

function installBaseDom() {
  document.body.innerHTML = `
    <div id="app"></div>
    <div id="groupPanel"></div>
    <div id="accountPanel"></div>
    <div id="batchActionBar" style="display:none;">
      <span id="selectedCount">已选 0 项</span>
    </div>
    <div id="compactBatchActionBar" style="display:none;">
      <span id="compactSelectedCount">已选 0 项</span>
    </div>
    <div id="emailList"></div>
    <span id="emailCount"></span>
    <span id="methodTag"></span>
    <div id="toast-container"></div>
  `;
}

function loadMainJs() {
  const filePath = path.resolve(__dirname, '../../static/js/main.js');
  const source = fs.readFileSync(filePath, 'utf8');
  const processedSource = source.replace(/\b(let|const)\b(\s)/g, 'var$2');
  (0, eval)(processedSource);
}

installBaseDom();
loadMainJs();

beforeEach(() => {
  jest.clearAllMocks();
  installBaseDom();

  // Re-establish mocks because indirect eval from loadMainJs may have overwritten globals
  global.fetch = jest.fn();
  global.confirm = jest.fn(() => true);
  global.alert = jest.fn();
  window.fetch = global.fetch;
  window.confirm = global.confirm;
  window.alert = global.alert;

  global.csrfToken = null;
  global.csrfTokenRefreshPromise = null;
  global.currentAccount = null;
  global.currentGroupId = 1;
  global.currentEmails = [];
  global.currentMethod = 'graph';
  global.currentFolder = 'inbox';
  global.groups = [];
  global.accountsCache = {};
  global.emailListCache = {};
  global.isTempEmailGroup = false;
  global.currentPage = 'mailbox';
  global.mailboxViewMode = 'standard';
  global.currentSkip = 0;
  global.hasMoreEmails = true;
  global.selectedAccountIds = new Set();
  global.currentEmailDetail = null;
  global.lastDeploymentInfo = null;

  global.renderEmailList = jest.fn();
  global.renderAccountList = jest.fn();
  global.renderCompactAccountList = jest.fn();
  global.renderCompactGroupStrip = jest.fn();
  global.updateTopbar = jest.fn();
  global.updateSelectAllCheckbox = jest.fn();
  global.syncAccountSummaryToAccountCache = jest.fn();
  global.handleApiError = jest.fn();
  global.showErrorDetailModal = jest.fn();
  global.showToast = jest.fn();
  global.showPersistentToast = jest.fn();
  global.updatePersistentToast = jest.fn();
  global.dismissPersistentToast = jest.fn();
});

afterEach(() => {
  document.body.innerHTML = '';
});
