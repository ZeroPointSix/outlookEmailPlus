// ==================== 插件管理 ====================

const PluginManager = (() => {
    let _plugins = [];
    let _cardExpanded = false;
    let _activeConfig = null;

    // ── 公共 fetch 包装（Content-Type；CSRF 由 main.js 的 fetch 覆写层自动注入）──

    async function _post(url, body) {
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        return { ok: resp.ok, status: resp.status, data: await resp.json() };
    }

    async function _get(url) {
        const resp = await fetch(url);
        return { ok: resp.ok, status: resp.status, data: await resp.json() };
    }

    function _getCheckedProviderRadio(group) {
        return Array.from(group.querySelectorAll('input[name="tempMailProvider"]')).find(el => el.checked) || null;
    }

    function _findProviderRadio(group, value) {
        return Array.from(group.querySelectorAll('input[name="tempMailProvider"]')).find(el => el.value === value) || null;
    }

    function _getPluginByName(name) {
        return _plugins.find(item => item && item.name === name) || null;
    }

    function _getInstalledPluginByName(name) {
        return _plugins.find(item => item && item.name === name && item.status === 'installed') || null;
    }

    function _getProviderConfigElements() {
        return {
            panel: document.getElementById('pluginProviderConfigPanel'),
            title: document.getElementById('pluginProviderConfigTitle'),
            body: document.getElementById('pluginProviderConfigBody'),
        };
    }

    function _resetProviderConfigPanel() {
        const { panel, title, body } = _getProviderConfigElements();
        if (panel) panel.style.display = 'none';
        if (title) title.textContent = '🧩 插件 Provider 配置';
        if (body) {
            body.innerHTML = '<div class="form-hint">请选择一个已安装插件 Provider。</div>';
        }
        _activeConfig = null;
    }

    function _scrollToProviderConfigPanel() {
        const { panel } = _getProviderConfigElements();
        if (panel && typeof panel.scrollIntoView === 'function') {
            panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }

    // ── 折叠卡片 ─────────────────────────────────────────────────────────────

    function toggleCard() {
        _cardExpanded = !_cardExpanded;
        const body = document.getElementById('pluginManagerBody');
        const icon = document.getElementById('pluginManagerToggleIcon');
        if (body) body.style.display = _cardExpanded ? 'block' : 'none';
        if (icon) icon.classList.toggle('open', _cardExpanded);
        if (_cardExpanded && _plugins.length === 0) loadPlugins();
    }

    // ── 加载插件列表 ──────────────────────────────────────────────────────────

    async function loadPlugins() {
        const content = document.getElementById('pluginManagerContent');
        if (!content) return;
        content.innerHTML = '<div style="text-align:center;padding:1rem;color:var(--text-muted);font-size:0.85rem;">加载中…</div>';

        try {
            const { ok, data } = await _get('/api/plugins');
            if (!ok || !data.success) throw new Error((data.error && data.error.message) || '加载失败');
            _plugins = (data.data && data.data.plugins) || [];
            _renderPluginList(data.data && data.data.installed_count != null ? data.data.installed_count : 0);
            _refreshProviderRadios();
            _refreshProviderSelect();
        } catch (err) {
            content.innerHTML = `<div style="color:var(--clr-danger);padding:0.5rem 0;font-size:0.85rem;">加载插件列表失败：${escapeHtml(String(err.message || err))}</div>`;
        }
    }

    // ── 渲染插件列表 ──────────────────────────────────────────────────────────

    function _renderPluginList(installedCount) {
        const content = document.getElementById('pluginManagerContent');
        if (!content) return;

        const badge = document.getElementById('pluginManagerBadge');
        if (badge) {
            badge.textContent = installedCount > 0 ? `已安装 ${installedCount} 个` : '无插件';
            badge.className = installedCount > 0 ? 'badge badge-info' : 'badge';
            badge.style.display = 'inline-flex';
        }

        const installed = _plugins.filter(p => p.status === 'installed');
        const failed    = _plugins.filter(p => p.status === 'load_failed');
        const available = _plugins.filter(p => p.status === 'available');

        let html = `
            <div style="display:flex;align-items:center;justify-content:space-between;gap:0.8rem;margin-bottom:1rem;flex-wrap:wrap;">
                <button class="btn btn-sm" onclick="PluginManager.loadPlugins()">🔄 刷新</button>
                <button class="btn btn-sm" onclick="PluginManager.openCustomInstallModal()">➕ 自定义安装</button>
            </div>`;

        if (_plugins.length === 0) {
            html += '<div style="text-align:center;padding:1.5rem 0;color:var(--text-muted);font-size:0.85rem;">暂无可用插件</div>';
        } else {
            html += '<div style="display:flex;flex-direction:column;gap:0.6rem;">';
            [...installed, ...failed, ...available].forEach(p => { html += _renderPluginItem(p); });
            html += '</div>';
        }

        html += `
            <div style="display:flex;align-items:center;justify-content:space-between;padding:0.8rem 1rem;margin-top:1rem;background:var(--bg-secondary);border-radius:6px;border:1px solid var(--border-light);">
                <span style="font-size:0.78rem;color:var(--text-muted);">安装、卸载或更新插件文件后，点击应用使插件生效</span>
                <button class="btn btn-sm btn-primary" onclick="PluginManager.applyChanges()">🔄 应用变更</button>
            </div>`;

        content.innerHTML = html;
    }

    function _renderPluginItem(p) {
        const name        = escapeHtml(p.name || '');
        const displayName = escapeHtml(p.display_name || p.name || '');
        const desc        = escapeHtml(p.description || '');
        const author      = escapeHtml(p.author || '');
        const version     = escapeHtml(p.version || '');
        const minVer      = escapeHtml(p.min_app_version || '');
        const status      = p.status;

        let badge = '';
        let actions = '';
        let borderStyle = '';

        if (status === 'installed') {
            badge   = '<span style="background:rgba(58,125,68,0.1);color:var(--clr-jade);padding:0.15rem 0.55rem;border-radius:20px;font-size:0.65rem;font-weight:500;">已安装</span>';
            actions = `<button class="btn btn-sm" onclick="PluginManager.toggleConfig('${name}')">打开设置</button>
                       <button class="btn btn-sm btn-outline-danger" onclick="PluginManager.confirmUninstall('${name}','${displayName}')">卸载</button>`;
        } else if (status === 'load_failed') {
            badge       = '<span style="background:rgba(192,57,43,0.1);color:var(--clr-danger);padding:0.15rem 0.55rem;border-radius:20px;font-size:0.65rem;font-weight:500;">加载失败</span>';
            borderStyle = 'border-color:rgba(192,57,43,0.3);';
            actions     = `<button class="btn btn-sm btn-outline-danger" onclick="PluginManager.confirmUninstall('${name}','${displayName}')">卸载</button>`;
        } else {
            badge   = '<span style="background:rgba(200,150,62,0.1);color:var(--clr-accent);padding:0.15rem 0.55rem;border-radius:20px;font-size:0.65rem;font-weight:500;">可安装</span>';
            actions = `<button class="btn btn-sm btn-primary" onclick="PluginManager.install('${name}')">安装</button>`;
        }

        const errorBlock = (status === 'load_failed' && p.error)
            ? `<div style="border-top:1px solid rgba(192,57,43,0.15);padding:0.6rem 0.85rem;margin-top:0.7rem;background:rgba(192,57,43,0.04);border-radius:6px;font-size:0.78rem;color:var(--clr-danger);">
                   ⚠️ 加载失败：${escapeHtml(String(p.error))}
               </div>` : '';

        return `
            <div class="plugin-item" id="plugin-item-${name}"
                 style="border:1px solid var(--border-light);border-radius:6px;padding:0.9rem 1rem;transition:border-color 0.2s,background 0.2s;${borderStyle}">
                <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;">
                    <div style="flex:1;">
                        <div style="font-size:0.9rem;font-weight:600;display:flex;align-items:center;gap:0.5rem;">
                            ${displayName} ${badge}
                        </div>
                        ${desc ? `<div style="font-size:0.78rem;color:var(--text-muted);margin-top:0.2rem;">${desc}</div>` : ''}
                        <div style="font-size:0.72rem;color:var(--text-muted);margin-top:0.3rem;display:flex;gap:0.8rem;">
                            ${author  ? `<span>👤 ${author}</span>`  : ''}
                            ${version ? `<span>📦 ${version}</span>` : ''}
                            ${minVer  ? `<span>📋 ${minVer}+</span>` : ''}
                        </div>
                    </div>
                    <div style="display:flex;gap:0.4rem;flex-shrink:0;">${actions}</div>
                </div>
                ${errorBlock}
            </div>`;
    }

    // ── 配置面板 ──────────────────────────────────────────────────────────────

    function toggleConfig(name) {
        const group = document.querySelector('.provider-radio-group');
        const radio = group ? _findProviderRadio(group, name) : null;
        if (radio) {
            radio.checked = true;
        }

        if (typeof onTempMailProviderChange === 'function') {
            onTempMailProviderChange(name);
        } else {
            showProviderConfig(name);
        }
        _scrollToProviderConfigPanel();
    }

    async function showProviderConfig(name) {
        const { panel, title, body } = _getProviderConfigElements();
        if (!panel || !title || !body) return;
        const plugin = _getInstalledPluginByName(name);

        panel.style.display = 'block';
        if (!plugin) {
            title.textContent = '🧩 插件 Provider 配置';
            body.innerHTML = `<div class="form-hint">未找到已安装的插件 Provider：${escapeHtml(String(name || ''))}</div>`;
            _activeConfig = null;
            return;
        }

        _activeConfig = name;
        title.textContent = `🧩 ${plugin.display_name || plugin.name} 配置`;
        body.innerHTML = '<div style="text-align:center;padding:0.8rem 0;color:var(--text-muted);font-size:0.83rem;">加载配置…</div>';

        try {
            const [schemaRes, configRes] = await Promise.all([
                _get(`/api/plugins/${encodeURIComponent(name)}/config/schema`),
                _get(`/api/plugins/${encodeURIComponent(name)}/config`),
            ]);
            if (!schemaRes.ok) throw new Error((schemaRes.data.error && schemaRes.data.error.message) || '加载 schema 失败');
            if (!configRes.ok) throw new Error((configRes.data.error && configRes.data.error.message) || '加载配置失败');

            const fields = (schemaRes.data.data && schemaRes.data.data.config_schema && schemaRes.data.data.config_schema.fields) || [];
            const config = (configRes.data.data && configRes.data.data.config) || {};
            if (_activeConfig !== name) return;
            body.innerHTML = _renderConfigForm(name, fields, config);
        } catch (err) {
            if (_activeConfig !== name) return;
            body.innerHTML = `<div style="color:var(--clr-danger);font-size:0.83rem;">加载失败：${escapeHtml(String(err.message || err))}</div>`;
        }
    }

    function _renderConfigForm(name, fields, currentConfig) {
        let fieldsHtml = '';
        for (const field of fields) {
            const key         = field.key || '';
            const label       = escapeHtml(field.label || key);
            const type        = field.type || 'text';
            const required    = field.required ? '<span style="color:var(--clr-danger);margin-left:0.15rem;">*</span>' : '';
            const hint        = escapeHtml(field.hint || field.description || '');
            const placeholder = escapeHtml(field.placeholder || '');
            const rawVal      = currentConfig[key] !== undefined ? currentConfig[key] : (field.default !== undefined ? field.default : '');
            const currentVal  = escapeHtml(String(rawVal));
            const inputId     = `plugin-field-${escapeHtml(name)}-${escapeHtml(key)}`;

            let inputHtml = '';
            if (type === 'textarea') {
                inputHtml = `<textarea class="form-input" id="${inputId}" placeholder="${placeholder}" style="min-height:70px;resize:vertical;font-family:inherit;">${currentVal}</textarea>`;
            } else if (type === 'select' && Array.isArray(field.options)) {
                const opts = field.options.map(opt => {
                    const v = typeof opt === 'object' ? opt.value : opt;
                    const l = typeof opt === 'object' ? opt.label : opt;
                    return `<option value="${escapeHtml(String(v))}" ${String(v) === String(rawVal) ? 'selected' : ''}>${escapeHtml(String(l))}</option>`;
                }).join('');
                inputHtml = `<select class="form-input" id="${inputId}">${opts}</select>`;
            } else if (type === 'toggle') {
                const checked = (String(rawVal) === 'true' || String(rawVal) === '1') ? 'checked' : '';
                inputHtml = `<label style="display:flex;align-items:center;gap:8px;cursor:pointer;"><input type="checkbox" id="${inputId}" ${checked}><span>${label}</span></label>`;
            } else {
                const inputType = type === 'password' ? 'password' : type === 'number' ? 'number' : type === 'url' ? 'url' : 'text';
                inputHtml = `<input type="${inputType}" class="form-input" id="${inputId}" placeholder="${placeholder}" value="${currentVal}" autocomplete="off">`;
            }

            if (type !== 'toggle') {
                fieldsHtml += `
                    <div class="form-group" style="margin-bottom:0.9rem;">
                        <label class="form-label" for="${inputId}">${label}${required}</label>
                        ${inputHtml}
                        ${hint ? `<div class="form-hint" style="font-size:0.72rem;color:var(--text-muted);margin-top:0.25rem;">${hint}</div>` : ''}
                    </div>`;
            } else {
                fieldsHtml += `
                    <div class="form-group" style="margin-bottom:0.9rem;">
                        ${inputHtml}
                        ${hint ? `<div class="form-hint" style="font-size:0.72rem;color:var(--text-muted);margin-top:0.25rem;">${hint}</div>` : ''}
                    </div>`;
            }
        }

        const testId = `plugin-test-${escapeHtml(name)}`;
        return `
            ${fieldsHtml || '<div style="color:var(--text-muted);font-size:0.83rem;padding:0.4rem 0;">该插件无可配置项。</div>'}
            <div id="${testId}" style="display:none;margin-top:0.5rem;border-radius:6px;padding:0.5rem 0.75rem;font-size:0.78rem;"></div>
            <div style="display:flex;gap:0.5rem;margin-top:0.5rem;flex-wrap:wrap;">
                <button class="btn btn-sm btn-ghost" onclick="PluginManager.testConnection('${escapeHtml(name)}','${testId}')">测试连接</button>
                <div style="flex:1;"></div>
                <button class="btn btn-sm btn-primary" onclick="PluginManager.saveConfig('${escapeHtml(name)}')">保存</button>
            </div>`;
    }

    // ── 安装 ──────────────────────────────────────────────────────────────────

    async function install(name, url) {
        const btn = document.querySelector(`#plugin-item-${name} .btn-primary`);
        if (btn) { btn.disabled = true; btn.textContent = '安装中…'; }

        try {
            const body = { name };
            if (url) body.url = url;
            const { ok, data } = await _post('/api/plugins/install', body);
            if (!ok || !data.success) {
                showToast((data.error && data.error.message) || '安装失败', 'error');
                if (btn) { btn.disabled = false; btn.textContent = '安装'; }
                return;
            }
            showToast(data.message || '安装成功，请点击「应用变更」', 'success');
            await loadPlugins();
        } catch (err) {
            showToast(String(err.message || '安装失败'), 'error');
            if (btn) { btn.disabled = false; btn.textContent = '安装'; }
        }
    }

    // ── 卸载 ──────────────────────────────────────────────────────────────────

    function confirmUninstall(name, displayName) {
        if (!confirm(`确认卸载插件「${displayName}」？\n\n卸载后插件文件将被删除，关联邮箱记录保留。`)) return;
        uninstall(name);
    }

    async function uninstall(name) {
        try {
            const { ok, data } = await _post(`/api/plugins/${encodeURIComponent(name)}/uninstall`, { clean_config: false });
            if (!ok || !data.success) {
                showToast((data.error && data.error.message) || '卸载失败', 'error');
                return;
            }
            showToast(data.message || '插件已卸载', 'success');
            if (_activeConfig === name) {
                _resetProviderConfigPanel();
            }
            await loadPlugins();
        } catch (err) {
            showToast(String(err.message || '卸载失败'), 'error');
        }
    }

    // ── 保存配置 ──────────────────────────────────────────────────────────────

    async function saveConfig(name) {
        const config = {};
        const prefix = `plugin-field-${name}-`;
        document.querySelectorAll(`[id^="${prefix}"]`).forEach(el => {
            const key = el.id.slice(prefix.length);
            config[key] = el.type === 'checkbox' ? (el.checked ? 'true' : 'false') : el.value;
        });

        try {
            const { ok, data } = await _post(`/api/plugins/${encodeURIComponent(name)}/config`, { config });
            if (!ok || !data.success) {
                showToast((data.error && data.error.message) || '保存失败', 'error');
                return;
            }
            showToast('配置已保存', 'success');
            await showProviderConfig(name);
        } catch (err) {
            showToast(String(err.message || '保存失败'), 'error');
        }
    }

    // ── 测试连接 ──────────────────────────────────────────────────────────────

    async function testConnection(name, resultId) {
        const el = document.getElementById(resultId);
        if (el) {
            el.style.cssText = 'display:block;border-radius:6px;padding:0.5rem 0.75rem;font-size:0.78rem;margin-top:0.5rem;background:var(--bg-secondary);color:var(--text-muted);border:1px solid var(--border-light);';
            el.textContent = '⏳ 测试中…';
        }
        try {
            const { ok, data } = await _post(`/api/plugins/${encodeURIComponent(name)}/test-connection`, {});
            if (el) {
                if (ok && data.success) {
                    const latency = data.data && data.data.latency_ms ? ` · 延迟 ${data.data.latency_ms}ms` : '';
                    el.innerHTML = `✅ 连接成功${latency}`;
                    el.style.background = 'rgba(58,125,68,0.08)';
                    el.style.color = 'var(--clr-jade)';
                    el.style.border = '1px solid rgba(58,125,68,0.2)';
                } else {
                    const msg = (data.error && data.error.message) || '连接失败';
                    el.innerHTML = `❌ ${escapeHtml(msg)}`;
                    el.style.background = 'rgba(192,57,43,0.06)';
                    el.style.color = 'var(--clr-danger)';
                    el.style.border = '1px solid rgba(192,57,43,0.15)';
                }
            }
        } catch (err) {
            if (el) {
                el.innerHTML = `❌ ${escapeHtml(String(err.message || '请求失败'))}`;
                el.style.background = 'rgba(192,57,43,0.06)';
                el.style.color = 'var(--clr-danger)';
                el.style.border = '1px solid rgba(192,57,43,0.15)';
            }
        }
    }

    // ── 应用变更（热刷新）────────────────────────────────────────────────────

    async function applyChanges() {
        try {
            const { ok, data } = await _post('/api/system/reload-plugins', {});
            if (!ok || !data.success) {
                showToast((data.error && data.error.message) || '应用失败', 'error');
                return;
            }
            const loaded = (data.data && data.data.loaded) || 0;
            const failedArr = (data.data && data.data.failed) || [];
            showToast(
                failedArr.length > 0
                    ? `已加载 ${loaded} 个插件，${failedArr.length} 个失败`
                    : `已应用，成功加载 ${loaded} 个插件`,
                failedArr.length > 0 ? 'warning' : 'success'
            );
            await loadPlugins();
        } catch (err) {
            showToast(String(err.message || '应用失败'), 'error');
        }
    }

    // ── 自定义安装模态框 ──────────────────────────────────────────────────────

    function openCustomInstallModal() {
        const modal = document.getElementById('pluginCustomInstallModal');
        if (modal) modal.style.display = 'flex';
        const nameEl = document.getElementById('customPluginName');
        const urlEl  = document.getElementById('customPluginUrl');
        if (nameEl) nameEl.value = '';
        if (urlEl)  urlEl.value  = '';
    }

    function closeCustomInstallModal() {
        const modal = document.getElementById('pluginCustomInstallModal');
        if (modal) modal.style.display = 'none';
    }

    async function customInstall() {
        const nameEl = document.getElementById('customPluginName');
        const urlEl  = document.getElementById('customPluginUrl');
        const name   = nameEl ? nameEl.value.trim() : '';
        const url    = urlEl  ? urlEl.value.trim()  : '';
        if (!name) { showToast('请输入插件名称', 'warning'); return; }
        if (!url)  { showToast('请输入下载地址', 'warning'); return; }
        if (!confirm(`⚠️ 安全提示\n\n您正在从第三方 URL 安装插件，代码将在服务器上执行。\n请仅安装来自可信来源的插件。\n\n继续安装「${name}」？`)) return;
        closeCustomInstallModal();
        await install(name, url);
    }

    // ── Provider 集成 ────────────────────────────────────────────────────────

    function _refreshProviderRadios() {
        const group = document.querySelector('.provider-radio-group');
        if (!group) return;
        const previousValue = _getCheckedProviderRadio(group)?.value || '';
        const pendingValue = String(group.dataset.pendingProvider || '').trim();
        // 移除已有插件 radio
        group.querySelectorAll('.provider-radio[data-plugin]').forEach(el => el.remove());
        _plugins.filter(p => p.status === 'installed').forEach(p => {
            const label = document.createElement('label');
            label.className = 'provider-radio';
            label.setAttribute('data-plugin', p.name);
            label.innerHTML = `
                <input type="radio" name="tempMailProvider" value="${escapeHtml(p.name)}" onchange="onTempMailProviderChange('${escapeHtml(p.name)}')">
                <span class="provider-radio-label">
                    <span class="provider-name">🧩 ${escapeHtml(p.display_name || p.name)}</span>
                    <span class="provider-desc">第三方插件 Provider</span>
                 </span>`;
            group.appendChild(label);
        });

        const fallbackRadio = _findProviderRadio(group, previousValue)
            || _findProviderRadio(group, pendingValue)
            || _getCheckedProviderRadio(group)
            || _findProviderRadio(group, 'legacy_bridge')
            || group.querySelector('input[name="tempMailProvider"]');
        if (fallbackRadio) {
            fallbackRadio.checked = true;
            group.dataset.pendingProvider = '';
            if (typeof onTempMailProviderChange === 'function') {
                onTempMailProviderChange(fallbackRadio.value);
            }
        }
    }

    function _refreshProviderSelect() {
        const sel = document.getElementById('tempEmailProviderSelect');
        if (!sel) return;
        const previousValue = sel.value;
        sel.querySelectorAll('option[data-plugin]').forEach(el => el.remove());
        _plugins.filter(p => p.status === 'installed').forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.name;
            opt.setAttribute('data-plugin', p.name);
            opt.textContent = `🧩 ${p.display_name || p.name}`;
            sel.appendChild(opt);
        });

        const hasPrevious = Array.from(sel.options).some(opt => opt.value === previousValue);
        sel.value = hasPrevious ? previousValue : (sel.options[0] ? sel.options[0].value : '');
        if (typeof onTempEmailProviderChange === 'function') {
            onTempEmailProviderChange(sel.value);
        }
    }

    function init() {
        const bootstrap = () => {
            loadPlugins();
        };

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', bootstrap, { once: true });
            return;
        }

        bootstrap();
    }

    // ── Public API ────────────────────────────────────────────────────────────

    return {
        init,
        toggleCard,
        loadPlugins,
        install,
        confirmUninstall,
        uninstall,
        toggleConfig,
        showProviderConfig,
        hideProviderConfig: _resetProviderConfigPanel,
        saveConfig,
        testConnection,
        applyChanges,
        openCustomInstallModal,
        closeCustomInstallModal,
        customInstall,
        hasInstalledProvider: name => !!_getInstalledPluginByName(name),
        getPluginByName: name => _getPluginByName(name),
    };
})();

window.PluginManager = PluginManager;
PluginManager.init();
