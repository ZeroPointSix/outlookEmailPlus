/**
 * chrome.storage.local 封装
 * 通过 <script src="storage.js"> 引入，暴露全局 Storage 对象
 */
const Storage = {
  /**
   * 读取所有存储数据
   * @returns {Promise<{config?: object, currentTask?: object|null, history?: Array}>}
   */
  async getAll() {
    return chrome.storage.local.get(['config', 'currentTask', 'history']);
  },

  /**
   * 写入当前任务
   * @param {object} task - 任务对象 {email, taskId, callerId, projectKey, claimedAt, code, link}
   */
  async setCurrentTask(task) {
    await chrome.storage.local.set({ currentTask: task });
  },

  /**
   * 清空当前任务
   */
  async clearCurrentTask() {
    await chrome.storage.local.set({ currentTask: null });
  },

  /**
   * 追加历史记录（最新在前，最多保留 100 条）
   * @param {object} entry - 历史条目
   */
  async appendHistory(entry) {
    const { history = [] } = await chrome.storage.local.get('history');
    const next = [entry, ...history].slice(0, 100);
    await chrome.storage.local.set({ history: next });
  },

  /**
   * 读取配置
   * @returns {Promise<{serverUrl?: string, apiKey?: string, defaultProjectKey?: string}>}
   */
  async getConfig() {
    const { config = {} } = await chrome.storage.local.get('config');
    return config;
  },

  /**
   * 写入配置
   * @param {object} config - 配置对象 {serverUrl, apiKey, defaultProjectKey}
   */
  async setConfig(config) {
    await chrome.storage.local.set({ config });
  },
};
