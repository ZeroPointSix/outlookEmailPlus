/**
 * chrome.storage.local 封装
 * 通过 <script src="storage.js"> 引入，暴露全局 Storage 对象
 */
const Storage = {
  /**
   * 读取所有存储数据
 * @returns {Promise<{config?: object, currentTask?: object|null, history?: Array, lastGeneratedProfile?: object|null, savedProfiles?: Array}>}
   */
  async getAll() {
    return chrome.storage.local.get([
      'config',
      'currentTask',
      'history',
      'lastGeneratedProfile',
      'savedProfiles',
    ]);
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

  /**
   * 读取最近一次生成的资料
   * @returns {Promise<object|null>}
   */
  async getLastGeneratedProfile() {
    const { lastGeneratedProfile = null } = await chrome.storage.local.get('lastGeneratedProfile');
    return lastGeneratedProfile;
  },

  /**
   * 写入最近一次生成的资料
   * @param {object|null} profile - 资料对象
   */
  async setLastGeneratedProfile(profile) {
    await chrome.storage.local.set({ lastGeneratedProfile: profile || null });
  },

  /**
   * 读取已保存资料
   * @returns {Promise<Array>}
   */
  async getSavedProfiles() {
    const { savedProfiles = [] } = await chrome.storage.local.get('savedProfiles');
    return Array.isArray(savedProfiles) ? savedProfiles : [];
  },

  /**
   * 保存或更新一条资料
   * @param {object} profile - 资料对象
   * @returns {Promise<Array>}
   */
  async upsertSavedProfile(profile) {
    const savedProfiles = await this.getSavedProfiles();
    const next = [profile].concat(savedProfiles.filter((item) => item.id !== profile.id)).slice(0, 20);
    await chrome.storage.local.set({ savedProfiles: next });
    return next;
  },

  /**
   * 删除一条已保存资料
   * @param {string} profileId - 资料 id
   * @returns {Promise<Array>}
   */
  async deleteSavedProfile(profileId) {
    const savedProfiles = await this.getSavedProfiles();
    const next = savedProfiles.filter((item) => item.id !== profileId);
    await chrome.storage.local.set({ savedProfiles: next });
    return next;
  },
};
