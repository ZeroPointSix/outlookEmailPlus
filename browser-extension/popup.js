(function () {
  const DEFAULT_WAIT_SECONDS = 60;
  const FETCH_TIMEOUT_MS = 65000;
  const ACTION_TIMEOUT_MS = 10000;
  const MAX_HISTORY = 100;
  const CALLER_ID = 'browser-extension';
  const PROFILE_COPY_FIELD_IDS = [
    'profile-first-name',
    'profile-last-name',
    'profile-full-name',
    'profile-username',
    'profile-password',
    'profile-email',
    'profile-phone',
    'profile-company',
    'profile-country',
    'profile-state',
    'profile-city',
    'profile-postal',
    'profile-address1',
    'profile-address2',
  ];
  const DEFAULT_PROFILE_PASSWORD_LENGTH = 16;
  const StorageApi = window.ExtensionStorage;

  if (!StorageApi) {
    throw new Error('ExtensionStorage is not loaded');
  }

  let historyOpen = false;
  let activePage = 'mail';
  let previousContentPage = 'mail';

  function getEl(id) {
    return document.getElementById(id);
  }

  function buildHeaders(apiKey, isJson) {
    const headers = { 'X-API-Key': apiKey };
    if (isJson) headers['Content-Type'] = 'application/json';
    return headers;
  }

  function trimUrl(serverUrl) {
    return (serverUrl || '').replace(/\/+$/, '');
  }

  async function handleResponse(resp) {
    if (resp.ok) return resp.json();
    let message;
    try {
      const body = await resp.json();
      message = body.message || body.error || `HTTP ${resp.status}`;
    } catch {
      message = resp.status >= 500 ? '服务端内部错误，请稍后再试' : `请求失败 (${resp.status})`;
    }
    throw new Error(message);
  }

  function friendlyError(err) {
    if (err && err.name === 'AbortError') return '等待超时，可以稍后重试';
    if (err instanceof TypeError && /fetch/i.test(err.message)) {
      return '无法连接服务端，请检查地址和网络';
    }
    return (err && err.message) || '未知错误';
  }

  function showMessage(message, type) {
    const bar = getEl('message-bar');
    bar.textContent = message;
    bar.className = `message-bar message-${type || 'success'}`;
    bar.style.display = 'block';
    if (type === 'success') {
      setTimeout(hideMessage, 3000);
    }
  }

  function showError(message) {
    showMessage(message, 'error');
  }

  function hideMessage() {
    getEl('message-bar').style.display = 'none';
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

  function setMailStatusPill(text) {
    getEl('mail-status-pill').textContent = text;
  }

  function formatTime(isoString) {
    if (!isoString) return '未知时间';
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) return isoString;
    return date.toLocaleString('zh-CN', { hour12: false });
  }

  function getPasswordLength() {
    const parsed = Number.parseInt(getEl('profile-password-length').value, 10);
    const safeValue = Number.isFinite(parsed) ? parsed : DEFAULT_PROFILE_PASSWORD_LENGTH;
    return Math.max(8, Math.min(32, safeValue));
  }

  async function setActivePage(page) {
    if (page !== 'settings') {
      previousContentPage = page;
    }
    activePage = page;

    ['mail', 'profile', 'settings'].forEach((name) => {
      const nav = getEl(`nav-${name}`);
      const pageEl = getEl(`page-${name}`);
      const isActive = name === page;
      nav.classList.toggle('active', isActive);
      pageEl.classList.toggle('active', isActive);
    });

    if (page === 'settings') {
      await loadSettingsForm();
      return;
    }

    if (page === 'profile') {
      const { currentTask } = await StorageApi.getAll();
      refreshClaimedEmailState(currentTask);
    }
  }

  async function renderMailboxState(state, data) {
    const stateEmpty = getEl('state-empty');
    const stateTask = getEl('state-task');
    const currentEmail = getEl('current-email');
    const resultBox = getEl('result-box');
    const resultLabel = getEl('result-label');
    const resultValue = getEl('result-value');
    const btnOpenLink = getEl('btn-open-link');
    const fetchWarning = getEl('fetch-warning');

    [stateEmpty, stateTask].forEach((el) => el.classList.remove('active'));
    currentEmail.textContent = data && data.email ? data.email : '';
    fetchWarning.style.display = 'none';
    resultBox.classList.remove('show');
    resultLabel.textContent = '验证码';
    resultValue.textContent = '';
    resultValue.classList.remove('link-mode');
    btnOpenLink.style.display = 'none';
    btnOpenLink.dataset.url = '';

    resetClaimButton();
    resetFetchButtons();
    setTaskActionDisabled(false);

    if (state === 'idle') {
      setMailStatusPill('等待领取');
      stateEmpty.classList.add('active');
      return;
    }

    if (state === 'claiming') {
      setMailStatusPill('申领中');
      stateEmpty.classList.add('active');
      const btn = getEl('btn-claim');
      btn.innerHTML = '<div class="spinner"></div> 申领中...';
      btn.disabled = true;
      return;
    }

    stateTask.classList.add('active');

    if (state === 'claimed') {
      setMailStatusPill('任务进行中');
      return;
    }

    if (state === 'fetching') {
      setMailStatusPill('等待收码');
      fetchWarning.style.display = 'block';
      if (data && data.fetchType === 'code') {
        getEl('btn-get-code').innerHTML = '<div class="spinner spinner-brown"></div> 等待邮件...';
      } else {
        getEl('btn-get-link').innerHTML = '<div class="spinner spinner-brown"></div> 获取中...';
      }
      getEl('btn-get-code').disabled = true;
      getEl('btn-get-link').disabled = true;
      setTaskActionDisabled(true);
      return;
    }

    if (state === 'result_code') {
      setMailStatusPill('验证码已就绪');
      resultLabel.textContent = '验证码';
      resultValue.textContent = (data && data.code) || '';
      resultBox.classList.add('show');
      return;
    }

    if (state === 'result_link') {
      setMailStatusPill('验证链接已就绪');
      resultLabel.textContent = '验证链接';
      resultValue.textContent = (data && data.link) || '';
      resultValue.classList.add('link-mode');
      btnOpenLink.style.display = 'block';
      btnOpenLink.dataset.url = (data && data.link) || '';
      resultBox.classList.add('show');
    }
  }

  async function loadSettingsForm() {
    const config = await StorageApi.getConfig();
    getEl('cfg-server').value = config.serverUrl || '';
    getEl('cfg-apikey').value = config.apiKey || '';
    getEl('cfg-project').value = config.defaultProjectKey || '';
  }

  function refreshClaimedEmailState(currentTask) {
    const checkbox = getEl('profile-use-claimed-email');
    const hint = getEl('profile-claimed-email-hint');
    if (currentTask && currentTask.email) {
      checkbox.disabled = false;
      hint.textContent = `当前可复用邮箱：${currentTask.email}`;
      return;
    }
    checkbox.checked = false;
    checkbox.disabled = true;
    hint.textContent = '当前没有可复用的邮箱任务。';
  }

  function renderProfileForm(profile) {
    const next = ProfileGenerator.normalizeProfile(profile || ProfileGenerator.createBlankProfile());
    const page = getEl('page-profile');
    page.dataset.seed = next.seed !== undefined && next.seed !== null ? String(next.seed) : '';
    page.dataset.createdAt = next.createdAt || '';
    page.dataset.stateCode = next.stateCode || '';

    getEl('profile-id').value = next.id || '';
    getEl('profile-first-name').value = next.firstName || '';
    getEl('profile-last-name').value = next.lastName || '';
    getEl('profile-full-name').value = next.fullName || '';
    getEl('profile-username').value = next.username || '';
    getEl('profile-password').value = next.password || '';
    getEl('profile-email').value = next.email || '';
    getEl('profile-phone').value = next.phone || '';
    getEl('profile-company').value = next.company || '';
    getEl('profile-country').value = next.country || 'United States';
    getEl('profile-state').value = next.state || '';
    getEl('profile-city').value = next.city || '';
    getEl('profile-postal').value = next.postalCode || '';
    getEl('profile-address1').value = next.addressLine1 || '';
    getEl('profile-address2').value = next.addressLine2 || '';
    getEl('profile-seed-pill').textContent = next.seed !== undefined && next.seed !== null ? `Seed ${next.seed}` : '本地生成';
  }

  function buildProfileFromForm() {
    const page = getEl('page-profile');
    return ProfileGenerator.normalizeProfile({
      id: getEl('profile-id').value.trim() || undefined,
      seed: page.dataset.seed ? Number(page.dataset.seed) : undefined,
      createdAt: page.dataset.createdAt || undefined,
      locale: 'en_US',
      country: getEl('profile-country').value.trim() || 'United States',
      countryCode: 'US',
      firstName: getEl('profile-first-name').value.trim(),
      lastName: getEl('profile-last-name').value.trim(),
      fullName: getEl('profile-full-name').value.trim(),
      username: getEl('profile-username').value.trim(),
      password: getEl('profile-password').value.trim(),
      email: getEl('profile-email').value.trim(),
      phone: getEl('profile-phone').value.trim(),
      company: getEl('profile-company').value.trim(),
      state: getEl('profile-state').value.trim(),
      stateCode: page.dataset.stateCode || '',
      city: getEl('profile-city').value.trim(),
      postalCode: getEl('profile-postal').value.trim(),
      addressLine1: getEl('profile-address1').value.trim(),
      addressLine2: getEl('profile-address2').value.trim(),
    });
  }

  function renderSavedProfiles(profiles) {
    const list = getEl('saved-profiles-list');
    const count = getEl('saved-profiles-count');
    const safeProfiles = Array.isArray(profiles) ? profiles : [];
    count.textContent = String(safeProfiles.length);
    list.innerHTML = '';

    if (!safeProfiles.length) {
      const empty = document.createElement('div');
      empty.className = 'saved-empty';
      empty.textContent = '还没有保存资料，可以先生成一组再保存。';
      list.appendChild(empty);
      return;
    }

    safeProfiles.forEach((profile) => {
      const item = document.createElement('div');
      item.className = 'saved-profile-item';

      const top = document.createElement('div');
      top.className = 'saved-profile-top';

      const info = document.createElement('div');

      const name = document.createElement('div');
      name.className = 'saved-profile-name';
      name.textContent = profile.fullName || profile.email || '未命名资料';

      const meta = document.createElement('div');
      meta.className = 'saved-profile-meta';
      meta.textContent = [profile.city, profile.state, profile.email].filter(Boolean).join(' · ') || '自定义资料';

      info.appendChild(name);
      info.appendChild(meta);

      const actions = document.createElement('div');
      actions.className = 'saved-profile-actions';

      const loadBtn = document.createElement('button');
      loadBtn.className = 'btn btn-outline';
      loadBtn.type = 'button';
      loadBtn.dataset.action = 'load';
      loadBtn.dataset.profileId = profile.id;
      loadBtn.textContent = '载入';

      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'btn btn-danger-outline';
      deleteBtn.type = 'button';
      deleteBtn.dataset.action = 'delete';
      deleteBtn.dataset.profileId = profile.id;
      deleteBtn.textContent = '删除';

      actions.appendChild(loadBtn);
      actions.appendChild(deleteBtn);
      top.appendChild(info);
      top.appendChild(actions);
      item.appendChild(top);
      list.appendChild(item);
    });
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
        apiError.textContent = '⚠ API 异常';
        meta.appendChild(apiError);
      }

      item.appendChild(email);
      item.appendChild(meta);
      list.appendChild(item);
    });
  }

  function toggleHistory() {
    historyOpen = !historyOpen;
    getEl('history-list').classList.toggle('open', historyOpen);
    getEl('history-caret').classList.toggle('open', historyOpen);
  }

  async function handleCopy(text, button) {
    if (!text) {
      showError('没有可复制的内容');
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      if (button) {
        const original = button.innerHTML;
        button.innerHTML = '✓ 已复制';
        button.classList.add('copied');
        setTimeout(() => {
          button.innerHTML = original;
          button.classList.remove('copied');
        }, 1400);
      }
    } catch {
      showError('复制失败，请手动复制');
    }
  }

  async function handleCopyField(input) {
    if (!input) return;
    const value = input.value.trim();
    if (!value) {
      showError('没有可复制的内容');
      return;
    }

    try {
      await navigator.clipboard.writeText(value);
      input.classList.add('copied');
      showMessage('已复制', 'success');
      setTimeout(() => {
        input.classList.remove('copied');
      }, 700);
    } catch {
      showError('复制失败，请手动复制');
    }
  }

  function handleOpenLink(url) {
    try {
      const parsed = new URL(url);
      if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
        showError('链接协议不合法，已拒绝打开');
        return;
      }
    } catch {
      showError('链接格式不正确');
      return;
    }
    chrome.tabs.create({ url });
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
    return chrome.permissions.request({ origins: [origin] });
  }

  async function handleClaim() {
    await setActivePage('mail');
    const config = await StorageApi.getConfig();
    if (!config.serverUrl || !config.apiKey) {
      showError('请先在设置中配置服务端地址和 API Key');
      return;
    }

    const projectKey = config.defaultProjectKey || '';
    await renderMailboxState('claiming');

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

    await StorageApi.setCurrentTask(task);

    try {
      const result = await apiClaimRandom(config, taskId, projectKey);
      if (!result || result.success === false) {
        throw new Error(result && result.message ? result.message : '申领失败，服务端无响应');
      }
      const data = result.data || {};
      if (!data.email) {
        throw new Error('服务端未返回邮箱地址');
      }
      task.email = data.email;
      task.accountId = data.account_id;
      task.claimToken = data.claim_token;
      await StorageApi.setCurrentTask(task);
      refreshClaimedEmailState(task);
      await renderMailboxState('claimed', task);
    } catch (err) {
      await StorageApi.clearCurrentTask();
      refreshClaimedEmailState(null);
      await renderMailboxState('idle');
      showError(friendlyError(err));
    }
  }

  async function handleGetCode() {
    await setActivePage('mail');
    const { currentTask } = await StorageApi.getAll();
    const config = await StorageApi.getConfig();
    if (!currentTask || !currentTask.email) {
      await renderMailboxState('idle');
      showError('当前没有进行中的任务');
      return;
    }

    await renderMailboxState('fetching', Object.assign({}, currentTask, { fetchType: 'code' }));

    try {
      const result = await apiGetCode(config, currentTask.email);
      if (!result || !result.data || !result.data.verification_code) {
        throw new Error('未获取到验证码');
      }
      currentTask.code = result.data.verification_code;
      await StorageApi.setCurrentTask(currentTask);
      await renderMailboxState('result_code', currentTask);
    } catch (err) {
      await renderMailboxState('claimed', currentTask);
      showError(friendlyError(err));
    }
  }

  async function handleGetLink() {
    await setActivePage('mail');
    const { currentTask } = await StorageApi.getAll();
    const config = await StorageApi.getConfig();
    if (!currentTask || !currentTask.email) {
      await renderMailboxState('idle');
      showError('当前没有进行中的任务');
      return;
    }

    await renderMailboxState('fetching', Object.assign({}, currentTask, { fetchType: 'link' }));

    try {
      const result = await apiGetLink(config, currentTask.email);
      if (!result || !result.data || !result.data.verification_link) {
        throw new Error('未获取到验证链接');
      }
      currentTask.link = result.data.verification_link;
      await StorageApi.setCurrentTask(currentTask);
      await renderMailboxState('result_link', currentTask);
    } catch (err) {
      await renderMailboxState('claimed', currentTask);
      showError(friendlyError(err));
    }
  }

  async function finalizeTask(currentTask, entry) {
    await StorageApi.appendHistory(entry);
    await StorageApi.clearCurrentTask();
    const { history = [] } = await StorageApi.getAll();
    renderHistory(history.slice(0, MAX_HISTORY));
    refreshClaimedEmailState(null);
    await renderMailboxState('idle');
  }

  async function handleComplete() {
    await setActivePage('mail');
    const { currentTask } = await StorageApi.getAll();
    const config = await StorageApi.getConfig();
    if (!currentTask || !currentTask.taskId) {
      await renderMailboxState('idle');
      return;
    }

    setTaskActionDisabled(true);
    let apiError = false;
    try {
      await apiComplete(config, currentTask);
    } catch {
      apiError = true;
    } finally {
      await finalizeTask(currentTask, {
        id: currentTask.taskId,
        email: currentTask.email,
        projectKey: currentTask.projectKey,
        claimedAt: currentTask.claimedAt,
        completedAt: new Date().toISOString(),
        status: 'completed',
        code: currentTask.code,
        link: currentTask.link,
        apiError,
      });

      if (apiError) {
        showError('完成操作未能通知服务端，已记录本地历史');
      } else {
        showMessage('✅ 任务已完成', 'success');
      }
    }
  }

  async function handleRelease() {
    await setActivePage('mail');
    const { currentTask } = await StorageApi.getAll();
    const config = await StorageApi.getConfig();
    if (!currentTask || !currentTask.taskId) {
      await renderMailboxState('idle');
      return;
    }

    setTaskActionDisabled(true);
    let apiError = false;
    try {
      await apiRelease(config, currentTask);
    } catch {
      apiError = true;
    } finally {
      await finalizeTask(currentTask, {
        id: currentTask.taskId,
        email: currentTask.email,
        projectKey: currentTask.projectKey,
        claimedAt: currentTask.claimedAt,
        completedAt: new Date().toISOString(),
        status: 'released',
        code: currentTask.code,
        link: currentTask.link,
        apiError,
      });

      if (apiError) {
        showError('释放操作未能通知服务端，已记录本地历史');
      } else {
        showMessage('↩ 邮箱已释放', 'success');
      }
    }
  }

  async function handleGenerateProfile() {
    await setActivePage('profile');
    const { currentTask } = await StorageApi.getAll();
    const useClaimedEmail = getEl('profile-use-claimed-email').checked && currentTask && currentTask.email;
    const profile = ProfileGenerator.generateProfile({
      claimedEmail: useClaimedEmail ? currentTask.email : '',
      passwordLength: getPasswordLength(),
    });

    renderProfileForm(profile);
    await StorageApi.setLastGeneratedProfile(profile);
    showMessage('已生成一组美国资料', 'success');
  }

  async function handleGeneratePassword() {
    await setActivePage('profile');
    const profile = buildProfileFromForm();
    profile.password = ProfileGenerator.generatePassword(getPasswordLength());
    renderProfileForm(profile);
    await StorageApi.setLastGeneratedProfile(profile);
    showMessage('随机密码已刷新', 'success');
  }

  async function handleSaveProfile() {
    await setActivePage('profile');
    const profile = buildProfileFromForm();
    if (!profile.fullName && !profile.email) {
      showError('请先生成或填写资料后再保存');
      return;
    }
    const nextProfiles = await StorageApi.upsertSavedProfile(profile);
    await StorageApi.setLastGeneratedProfile(profile);
    renderSavedProfiles(nextProfiles);
    showMessage('资料已保存', 'success');
  }

  async function handleResetProfile() {
    await setActivePage('profile');
    const blankProfile = ProfileGenerator.createBlankProfile();
    renderProfileForm(blankProfile);
    await StorageApi.setLastGeneratedProfile(blankProfile);
    showMessage('已清空当前编辑内容', 'success');
  }

  async function handleSavedProfileAction(event) {
    const button = event.target.closest('button[data-action]');
    if (!button) return;

    const profileId = button.dataset.profileId;
    if (!profileId) return;

    if (button.dataset.action === 'load') {
      const savedProfiles = await StorageApi.getSavedProfiles();
      const profile = savedProfiles.find((item) => item.id === profileId);
      if (!profile) {
        showError('未找到要加载的资料');
        return;
      }
      renderProfileForm(profile);
      await StorageApi.setLastGeneratedProfile(profile);
      await setActivePage('profile');
      showMessage('资料已载入', 'success');
      return;
    }

    if (button.dataset.action === 'delete') {
      const nextProfiles = await StorageApi.deleteSavedProfile(profileId);
      renderSavedProfiles(nextProfiles);
      showMessage('资料已删除', 'success');
    }
  }

  async function handleSaveSettings() {
    const serverUrl = getEl('cfg-server').value.trim().replace(/\/+$/, '');
    const apiKey = getEl('cfg-apikey').value.trim();
    const defaultProjectKey = getEl('cfg-project').value.trim();

    if (!serverUrl || !apiKey) {
      showError('请填写服务端地址和 API Key');
      return;
    }

    let granted;
    try {
      granted = await requestPermissionForHost(serverUrl);
    } catch {
      showError('服务端地址格式不正确');
      return;
    }

    if (!granted) {
      showError('需要授予访问权限后才能正常使用，请重试');
      return;
    }

    await StorageApi.setConfig({
      serverUrl,
      apiKey,
      defaultProjectKey: defaultProjectKey || '',
    });

    showMessage('✅ 配置已保存', 'success');
    setTimeout(() => {
      setActivePage(previousContentPage || 'mail');
    }, 450);
  }

  function setupProfileCopyFields() {
    PROFILE_COPY_FIELD_IDS.forEach((fieldId) => {
      const input = getEl(fieldId);
      if (!input) return;
      input.classList.add('copy-on-click');
      input.addEventListener('click', () => handleCopyField(input));
    });
  }

  document.addEventListener('DOMContentLoaded', async () => {
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

    ['mail', 'profile', 'settings'].forEach((page) => {
      getEl(`nav-${page}`).addEventListener('click', () => setActivePage(page));
    });

    getEl('header-settings-btn').addEventListener('click', () => setActivePage('settings'));
    getEl('btn-back').addEventListener('click', () => setActivePage(previousContentPage || 'mail'));

    getEl('btn-claim').addEventListener('click', handleClaim);
    getEl('btn-get-code').addEventListener('click', handleGetCode);
    getEl('btn-get-link').addEventListener('click', handleGetLink);
    getEl('btn-complete').addEventListener('click', handleComplete);
    getEl('btn-release').addEventListener('click', handleRelease);
    getEl('btn-save').addEventListener('click', handleSaveSettings);
    getEl('history-header').addEventListener('click', toggleHistory);
    getEl('btn-copy-email').addEventListener('click', () => handleCopy(getEl('current-email').innerText, getEl('btn-copy-email')));
    getEl('btn-copy-result').addEventListener('click', () => handleCopy(getEl('result-value').innerText, getEl('btn-copy-result')));
    getEl('btn-open-link').addEventListener('click', () => handleOpenLink(getEl('btn-open-link').dataset.url));

    getEl('btn-generate-profile').addEventListener('click', handleGenerateProfile);
    getEl('btn-generate-password').addEventListener('click', handleGeneratePassword);
    getEl('btn-save-profile').addEventListener('click', handleSaveProfile);
    getEl('btn-reset-profile').addEventListener('click', handleResetProfile);
    getEl('saved-profiles-list').addEventListener('click', handleSavedProfileAction);

    setupProfileCopyFields();

    const allData = await StorageApi.getAll();
    const currentTask = allData.currentTask;
    renderHistory((allData.history || []).slice(0, MAX_HISTORY));
    renderSavedProfiles(allData.savedProfiles || []);
    refreshClaimedEmailState(currentTask);

    if (allData.lastGeneratedProfile) {
      renderProfileForm(allData.lastGeneratedProfile);
    } else {
      renderProfileForm(ProfileGenerator.createBlankProfile());
    }

    if (currentTask && currentTask.email) {
      await renderMailboxState('claimed', currentTask);
    } else if (currentTask && !currentTask.email) {
      await StorageApi.clearCurrentTask();
      await renderMailboxState('idle');
    } else {
      await renderMailboxState('idle');
    }

    await setActivePage('mail');
  });
})();
