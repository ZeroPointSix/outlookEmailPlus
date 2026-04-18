(function () {
  const DEFAULT_WAIT_SECONDS = 60;
  const FETCH_TIMEOUT_MS = 65000;
  const ACTION_TIMEOUT_MS = 10000;
  const MAX_HISTORY = 100;
  const CALLER_ID = 'browser-extension';

  let historyOpen = false;

  function getEl(id) {
    return document.getElementById(id);
  }

  function buildHeaders(apiKey, isJson = false) {
    const h = { 'X-API-Key': apiKey };
    if (isJson) h['Content-Type'] = 'application/json';
    return h;
  }

  function trimUrl(serverUrl) {
    return (serverUrl || '').replace(/\/+$/, '');
  }

  async function handleResponse(resp) {
    if (resp.ok) return resp.json();
    let msg;
    try {
      const body = await resp.json();
      msg = body.message || body.error || `HTTP ${resp.status}`;
    } catch {
      msg = resp.status >= 500 ? '服务器内部错误，请稍后重试' : `请求失败 (${resp.status})`;
    }
    throw new Error(msg);
  }

  function friendlyError(err) {
    if (err && err.name === 'AbortError') return '等待超时，可重试';
    if (err instanceof TypeError && /fetch/i.test(err.message)) {
      return '无法连接服务器，请检查地址和网络';
    }
    return (err && err.message) || '未知错误';
  }

  function resetClaimButton() {
    const btn = getEl('btn-claim');
    btn.innerHTML = '<span>📧</span> 申领邮箱';
    btn.disabled = false;
  }

  function resetFetchButtons() {
    const codeBtn = getEl('btn-get-code');
    const linkBtn = getEl('btn-get-link');
    codeBtn.innerHTML = '<span>🔢</span> 获取最新验证码';
    linkBtn.innerHTML = '<span>🔗</span> 获取验证链接';
    codeBtn.disabled = false;
    linkBtn.disabled = false;
  }

  function setTaskActionDisabled(disabled) {
    getEl('btn-complete').disabled = disabled;
    getEl('btn-release').disabled = disabled;
  }

  function formatTime(isoString) {
    if (!isoString) return '未知时间';
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) return isoString;
    return date.toLocaleString('zh-CN', { hour12: false });
  }

  async function renderState(state, data) {
    hideMessage();

    const stateEmpty = getEl('state-empty');
    const stateTask = getEl('state-task');
    const stateSettings = getEl('state-settings');
    const currentEmail = getEl('current-email');
    const resultBox = getEl('result-box');
    const resultLabel = getEl('result-label');
    const resultValue = getEl('result-value');
    const btnOpenLink = getEl('btn-open-link');
    const fetchWarning = getEl('fetch-warning');

    [stateEmpty, stateTask, stateSettings].forEach((el) => el.classList.remove('active'));

    resultBox.classList.remove('show');
    resultLabel.textContent = '验证码';
    resultValue.textContent = '';
    resultValue.classList.remove('link-mode');
    btnOpenLink.style.display = 'none';
    btnOpenLink.dataset.url = '';
    fetchWarning.style.display = 'none';
    currentEmail.textContent = data && data.email ? data.email : '';

    resetClaimButton();
    resetFetchButtons();
    setTaskActionDisabled(false);

    if (state === 'idle') {
      stateEmpty.classList.add('active');
      return;
    }

    if (state === 'claiming') {
      stateEmpty.classList.add('active');
      const btn = getEl('btn-claim');
      btn.innerHTML = '<div class="spinner"></div> 申领中…';
      btn.disabled = true;
      return;
    }

    if (state === 'claimed') {
      stateTask.classList.add('active');
      return;
    }

    if (state === 'fetching') {
      stateTask.classList.add('active');
      fetchWarning.style.display = 'block';
      if (data && data.fetchType === 'code') {
        getEl('btn-get-code').innerHTML = '<div class="spinner spinner-brown"></div> 等待邮件…';
      } else {
        getEl('btn-get-link').innerHTML = '<div class="spinner spinner-brown"></div> 获取中…';
      }
      getEl('btn-get-code').disabled = true;
      getEl('btn-get-link').disabled = true;
      setTaskActionDisabled(true);
      return;
    }

    if (state === 'result_code') {
      stateTask.classList.add('active');
      resultLabel.textContent = '验证码';
      resultValue.textContent = (data && data.code) || '';
      resultValue.classList.remove('link-mode');
      resultBox.classList.add('show');
      return;
    }

    if (state === 'result_link') {
      stateTask.classList.add('active');
      resultLabel.textContent = '验证链接';
      resultValue.textContent = (data && data.link) || '';
      resultValue.classList.add('link-mode');
      btnOpenLink.style.display = 'block';
      btnOpenLink.dataset.url = (data && data.link) || '';
      resultBox.classList.add('show');
      return;
    }

    if (state === 'settings') {
      stateSettings.classList.add('active');
      const config = await Storage.getConfig();
      getEl('cfg-server').value = config.serverUrl || '';
      getEl('cfg-apikey').value = config.apiKey || '';
      getEl('cfg-project').value = config.defaultProjectKey || '';
    }
  }

  async function apiClaimRandom(config, taskId, projectKey) {
    const url = `${trimUrl(config.serverUrl)}/api/external/pool/claim-random`;
    const body = { caller_id: CALLER_ID, task_id: taskId };
    if (projectKey) body.project_key = projectKey;

    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), ACTION_TIMEOUT_MS);
    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: buildHeaders(config.apiKey, true),
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      return handleResponse(resp);
    } finally {
      clearTimeout(timer);
    }
  }

  async function apiGetCode(config, email) {
    const base = trimUrl(config.serverUrl);
    const url = `${base}/api/external/verification-code?email=${encodeURIComponent(email)}&wait=${DEFAULT_WAIT_SECONDS}`;

    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
    try {
      const resp = await fetch(url, {
        headers: buildHeaders(config.apiKey),
        signal: ctrl.signal,
      });
      return handleResponse(resp);
    } finally {
      clearTimeout(timer);
    }
  }

  async function apiGetLink(config, email) {
    const base = trimUrl(config.serverUrl);
    const url = `${base}/api/external/verification-link?email=${encodeURIComponent(email)}&wait=${DEFAULT_WAIT_SECONDS}`;

    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
    try {
      const resp = await fetch(url, {
        headers: buildHeaders(config.apiKey),
        signal: ctrl.signal,
      });
      return handleResponse(resp);
    } finally {
      clearTimeout(timer);
    }
  }

  async function apiComplete(config, task) {
    const url = `${trimUrl(config.serverUrl)}/api/external/pool/claim-complete`;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), ACTION_TIMEOUT_MS);
    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: buildHeaders(config.apiKey, true),
        body: JSON.stringify({
          task_id: task.taskId,
          account_id: task.accountId,
          claim_token: task.claimToken,
          caller_id: CALLER_ID,
          result: 'success',
        }),
        signal: ctrl.signal,
      });
      return handleResponse(resp);
    } finally {
      clearTimeout(timer);
    }
  }

  async function apiRelease(config, task) {
    const url = `${trimUrl(config.serverUrl)}/api/external/pool/claim-release`;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), ACTION_TIMEOUT_MS);
    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: buildHeaders(config.apiKey, true),
        body: JSON.stringify({
          task_id: task.taskId,
          account_id: task.accountId,
          claim_token: task.claimToken,
          caller_id: CALLER_ID,
          result: 'network_error',
        }),
        signal: ctrl.signal,
      });
      return handleResponse(resp);
    } finally {
      clearTimeout(timer);
    }
  }

  async function requestPermissionForHost(serverUrl) {
    const url = new URL(serverUrl);
    const origin = `${url.protocol}//${url.host}/*`;
    const granted = await chrome.permissions.request({ origins: [origin] });
    return granted;
  }

  async function handleClaim() {
    const config = await Storage.getConfig();
    if (!config.serverUrl || !config.apiKey) {
      showError('请先在设置中配置服务器地址和 API Key');
      return;
    }

    const projectKey = config.defaultProjectKey || '';

    await renderState('claiming');

    const taskId = crypto.randomUUID();
    const task = {
      email: null,
      taskId,
      callerId: CALLER_ID,
      projectKey,
      claimedAt: new Date().toISOString(),
      code: null,
      link: null,
    };

    await Storage.setCurrentTask(task);

    try {
      const result = await apiClaimRandom(config, taskId, projectKey);
      if (!result || result.success === false) {
        throw new Error(result && result.message ? result.message : '申领失败，服务器无响应');
      }
      const data = result.data || {};
      if (!data.email) {
        throw new Error('服务器未返回邮箱地址');
      }
      task.email = data.email;
      task.accountId = data.account_id;
      task.claimToken = data.claim_token;
      await Storage.setCurrentTask(task);
      await renderState('claimed', task);
    } catch (err) {
      await Storage.clearCurrentTask();
      await renderState('idle');
      showError(friendlyError(err));
    }
  }

  async function handleGetCode() {
    const { currentTask } = await Storage.getAll();
    const config = await Storage.getConfig();
    if (!currentTask || !currentTask.email) {
      await renderState('idle');
      showError('当前没有进行中的任务');
      return;
    }

    await renderState('fetching', Object.assign({}, currentTask, { fetchType: 'code' }));

    try {
      const result = await apiGetCode(config, currentTask.email);
      if (!result || !result.data || !result.data.verification_code) {
        throw new Error('未获取到验证码');
      }
      currentTask.code = result.data.verification_code;
      await Storage.setCurrentTask(currentTask);
      await renderState('result_code', currentTask);
    } catch (err) {
      await renderState('claimed', currentTask);
      showError(friendlyError(err));
    }
  }

  async function handleGetLink() {
    const { currentTask } = await Storage.getAll();
    const config = await Storage.getConfig();
    if (!currentTask || !currentTask.email) {
      await renderState('idle');
      showError('当前没有进行中的任务');
      return;
    }

    await renderState('fetching', Object.assign({}, currentTask, { fetchType: 'link' }));

    try {
      const result = await apiGetLink(config, currentTask.email);
      if (!result || !result.data || !result.data.verification_link) {
        throw new Error('未获取到验证链接');
      }
      currentTask.link = result.data.verification_link;
      await Storage.setCurrentTask(currentTask);
      await renderState('result_link', currentTask);
    } catch (err) {
      await renderState('claimed', currentTask);
      showError(friendlyError(err));
    }
  }

  async function handleComplete() {
    const { currentTask } = await Storage.getAll();
    const config = await Storage.getConfig();
    if (!currentTask || !currentTask.taskId) {
      await renderState('idle');
      return;
    }

    setTaskActionDisabled(true);

    let apiError = false;
    try {
      await apiComplete(config, currentTask);
    } catch (err) {
      apiError = true;
    } finally {
      const entry = {
        id: currentTask.taskId,
        email: currentTask.email,
        projectKey: currentTask.projectKey,
        claimedAt: currentTask.claimedAt,
        completedAt: new Date().toISOString(),
        status: 'completed',
        code: currentTask.code,
        link: currentTask.link,
        apiError,
      };
      await Storage.appendHistory(entry);
      await Storage.clearCurrentTask();
      const { history = [] } = await Storage.getAll();
      renderHistory(history.slice(0, MAX_HISTORY));
      await renderState('idle');
      if (apiError) {
        showError('完成操作未能通知服务器，已记录本地历史');
      } else {
        showMessage('✅ 任务已完成', 'success');
      }
    }
  }

  async function handleRelease() {
    const { currentTask } = await Storage.getAll();
    const config = await Storage.getConfig();
    if (!currentTask || !currentTask.taskId) {
      await renderState('idle');
      return;
    }

    setTaskActionDisabled(true);

    let apiError = false;
    try {
      await apiRelease(config, currentTask);
    } catch (err) {
      apiError = true;
    } finally {
      const entry = {
        id: currentTask.taskId,
        email: currentTask.email,
        projectKey: currentTask.projectKey,
        claimedAt: currentTask.claimedAt,
        completedAt: new Date().toISOString(),
        status: 'released',
        code: currentTask.code,
        link: currentTask.link,
        apiError,
      };
      await Storage.appendHistory(entry);
      await Storage.clearCurrentTask();
      const { history = [] } = await Storage.getAll();
      renderHistory(history.slice(0, MAX_HISTORY));
      await renderState('idle');
      if (apiError) {
        showError('释放操作未能通知服务器，已记录本地历史');
      } else {
        showMessage('↩ 邮箱已释放', 'success');
      }
    }
  }

  async function handleCopy(text, btnElement) {
    try {
      await navigator.clipboard.writeText(text);
      const orig = btnElement.innerHTML;
      btnElement.innerHTML = '✓ 已复制';
      btnElement.classList.add('copied');
      setTimeout(() => {
        btnElement.innerHTML = orig;
        btnElement.classList.remove('copied');
      }, 1400);
    } catch {
      showError('复制失败，请手动复制');
    }
  }

  function handleOpenLink(url) {
    try {
      const parsed = new URL(url);
      if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
        showError('链接协议不合法，拒绝打开');
        return;
      }
    } catch {
      showError('链接格式不正确');
      return;
    }
    chrome.tabs.create({ url });
  }

  async function handleSaveSettings() {
    const serverUrl = getEl('cfg-server').value.trim().replace(/\/+$/, '');
    const apiKey = getEl('cfg-apikey').value.trim();
    const defaultProjectKey = getEl('cfg-project').value.trim();

    if (!serverUrl || !apiKey) {
      showError('请填写服务器地址和 API Key');
      return;
    }

    let granted;
    try {
      granted = await requestPermissionForHost(serverUrl);
    } catch {
      showError('服务器地址格式不正确');
      return;
    }

    if (!granted) {
      showError('需要授予访问权限才能正常使用，请重试');
      return;
    }

    await Storage.setConfig({
      serverUrl,
      apiKey,
      defaultProjectKey: defaultProjectKey || '',
    });
    showMessage('✅ 配置已保存', 'success');
    setTimeout(() => {
      renderState('idle');
    }, 500);
  }

  function renderHistory(history) {
    const list = getEl('history-list');
    const count = getEl('history-count');
    const safeHistory = Array.isArray(history) ? history.slice(0, MAX_HISTORY) : [];

    count.textContent = String(safeHistory.length);
    list.innerHTML = '';

    if (!safeHistory.length) {
      const empty = document.createElement('div');
      empty.className = 'history-item';
      empty.textContent = '暂无历史记录';
      list.appendChild(empty);
      return;
    }

    safeHistory.forEach((entry) => {
      const item = document.createElement('div');
      item.className = 'history-item';

      const email = document.createElement('div');
      email.className = 'history-email';
      email.textContent = entry.email || '-';

      const meta = document.createElement('div');
      meta.className = 'history-meta';

      const time = document.createElement('span');
      time.textContent = formatTime(entry.completedAt || entry.claimedAt);

      const result = document.createElement('span');
      result.className = 'history-code';
      if (entry.code) {
        result.textContent = `验证码: ${entry.code}`;
      } else if (entry.link) {
        result.textContent = '🔗 链接已提取';
      } else {
        result.textContent = '（未获取验证码）';
      }

      const status = document.createElement('span');
      if (entry.status === 'completed') {
        status.className = 'status-done';
        status.textContent = '✅ 完成';
      } else {
        status.className = 'status-release';
        status.textContent = '↩ 已释放';
      }

      meta.appendChild(time);
      meta.appendChild(result);
      meta.appendChild(status);

      if (entry.apiError) {
        const apiError = document.createElement('span');
        apiError.style.color = 'var(--clr-danger)';
        apiError.textContent = '⚠ API异常';
        meta.appendChild(apiError);
      }

      item.appendChild(email);
      item.appendChild(meta);
      list.appendChild(item);
    });
  }

  function showMessage(msg, type = 'info') {
    const bar = getEl('message-bar');
    bar.textContent = msg;
    bar.className = 'message-bar message-' + type;
    bar.style.display = 'block';
    if (type === 'success') {
      setTimeout(hideMessage, 3000);
    }
  }

  function showError(msg) {
    showMessage(msg, 'error');
  }

  function hideMessage() {
    const bar = getEl('message-bar');
    bar.style.display = 'none';
  }

  function toggleHistory() {
    historyOpen = !historyOpen;
    getEl('history-list').classList.toggle('open', historyOpen);
    getEl('history-caret').classList.toggle('open', historyOpen);
  }

  document.addEventListener('DOMContentLoaded', async () => {
    // 同步主应用主题（读 localStorage['ol_theme']）
    const savedTheme = localStorage.getItem('ol_theme') || 'light';
    document.documentElement.dataset.theme = savedTheme;
    const themeBtn = getEl('header-theme-btn');
    themeBtn.textContent = savedTheme === 'dark' ? '☀️' : '🌙';
    themeBtn.addEventListener('click', () => {
      const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      localStorage.setItem('ol_theme', next);
      themeBtn.textContent = next === 'dark' ? '☀️' : '🌙';
    });

    getEl('btn-claim').addEventListener('click', handleClaim);
    getEl('btn-get-code').addEventListener('click', handleGetCode);
    getEl('btn-get-link').addEventListener('click', handleGetLink);
    getEl('btn-complete').addEventListener('click', handleComplete);
    getEl('btn-release').addEventListener('click', handleRelease);
    getEl('btn-save').addEventListener('click', handleSaveSettings);
    getEl('btn-back').addEventListener('click', () => renderState('idle'));
    getEl('header-settings-btn').addEventListener('click', () => renderState('settings'));
    getEl('history-header').addEventListener('click', toggleHistory);
    getEl('btn-copy-email').addEventListener('click', () => handleCopy(getEl('current-email').innerText, getEl('btn-copy-email')));
    getEl('btn-copy-result').addEventListener('click', () => handleCopy(getEl('result-value').innerText, getEl('btn-copy-result')));
    getEl('btn-open-link').addEventListener('click', () => handleOpenLink(getEl('btn-open-link').dataset.url));

    const { currentTask, history = [] } = await Storage.getAll();
    renderHistory(history.slice(0, MAX_HISTORY));

    if (currentTask && currentTask.email) {
      await renderState('claimed', currentTask);
    } else if (currentTask && !currentTask.email) {
      await Storage.clearCurrentTask();
      await renderState('idle');
    } else {
      await renderState('idle');
    }
  });
})();
