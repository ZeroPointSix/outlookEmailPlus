// 全局状态
        let csrfToken = null;
        let csrfTokenRefreshPromise = null;
        let currentAccount = null;
        let currentGroupId = null;
        let currentEmails = [];
        let currentMethod = 'graph';
        let currentFolder = 'inbox';
        let isListVisible = true;
        let groups = [];
        let accountsCache = {};
        let editingGroupId = null;
        let selectedColor = '#B85C38';
        let isTempEmailGroup = false;
        let tempEmailGroupId = null;
        let isLoadingMore = false;
        let hasMoreEmails = true;
        let currentSkip = 0;
        let lastRefreshTime = null;
        let mailboxViewMode = localStorage.getItem('ol_mailbox_view_mode') || 'standard';
        let latestInvalidTokenDetectedCount = 0;
        let invalidTokenGovernanceCandidates = [];
        let selectedInvalidTokenCandidateIds = new Set();

        // 缓存与信任模式
        let emailListCache = {};
        let currentEmailDetail = null;
        let isTrustedMode = false;

        // 轮询相关（Phase 2: 变量保留用于设置读写，实际轮询由统一引擎处理）
        let maxPollingCount = 5;
        let pollingInterval = 10;
        let autoPollingEnabled = false;
        // [Phase 3] compact 独立变量已废弃，统一使用上方标准字段

        // 导航状态
        let currentPage = 'dashboard';
        let accountPanelDensitySyncHandle = null;

        // ==================== 布局状态管理 (ui_layout_v2) ====================
        // 布局状态缓存
        let uiLayoutV2 = null;
        let layoutSaveDebounceTimer = null;
        const LAYOUT_SAVE_DEBOUNCE_MS = 2000;

        // 默认布局状态
        function getDefaultLayoutV2() {
            return {
                version: 2,
                sidebar: { collapsed: false },
                mailbox: { groupPanelWidth: 220, accountPanelWidth: 280 },
                tempEmails: { listPanelWidth: 300 }
            };
        }

        // 从后端读取布局状态
        async function loadLayoutFromServer() {
            try {
                const response = await fetch('/api/settings');
                const data = await response.json();
                if (data.success && data.settings && data.settings.ui_layout_v2) {
                    const layout = data.settings.ui_layout_v2;
                    if (layout.version === 2) {
                        uiLayoutV2 = layout;
                        return layout;
                    }
                }
            } catch (error) {
                console.warn('加载布局状态失败:', error);
            }
            return null;
        }

        // 迁移旧 localStorage key 到 ui_layout_v2
        function migrateOldLayoutKeys() {
            const migrated = { version: 2, sidebar: {}, mailbox: {}, tempEmails: {} };
            let needsMigration = false;

            try {
                // 迁移侧边栏折叠状态
                const oldSidebarCollapsed = localStorage.getItem('ol_sidebar_collapsed');
                if (oldSidebarCollapsed !== null) {
                    migrated.sidebar.collapsed = oldSidebarCollapsed === 'true';
                    needsMigration = true;
                } else {
                    migrated.sidebar.collapsed = false;
                }

                // 迁移列宽
                const oldColumnWidths = localStorage.getItem('ol_column_widths');
                if (oldColumnWidths) {
                    try {
                        const widths = JSON.parse(oldColumnWidths);
                        // groupPanel / accountPanel 的宽度迁移
                        if (widths.groupPanel) {
                            const w = parseInt(widths.groupPanel, 10);
                            if (!isNaN(w) && w > 0) {
                                migrated.mailbox.groupPanelWidth = w;
                                needsMigration = true;
                            }
                        }
                        if (widths.accountPanel) {
                            const w = parseInt(widths.accountPanel, 10);
                            if (!isNaN(w) && w > 0) {
                                migrated.mailbox.accountPanelWidth = w;
                                needsMigration = true;
                            }
                        }
                        // temp-emails 列宽迁移（如果有）
                        if (widths.tempEmailPanel) {
                            const w = parseInt(widths.tempEmailPanel, 10);
                            if (!isNaN(w) && w > 0) {
                                migrated.tempEmails.listPanelWidth = w;
                                needsMigration = true;
                            }
                        }
                    } catch (e) {
                        console.warn('解析旧列宽数据失败:', e);
                    }
                }

                // 设置默认值
                if (!migrated.mailbox.groupPanelWidth) migrated.mailbox.groupPanelWidth = 220;
                if (!migrated.mailbox.accountPanelWidth) migrated.mailbox.accountPanelWidth = 280;
                if (!migrated.tempEmails.listPanelWidth) migrated.tempEmails.listPanelWidth = 300;

            } catch (e) {
                console.warn('迁移布局状态失败:', e);
                return null;
            }

            return needsMigration ? migrated : null;
        }

        // 清理旧 localStorage key（可选，迁移成功后调用）
        function cleanupOldLayoutKeys() {
            try {
                localStorage.removeItem('ol_sidebar_collapsed');
                localStorage.removeItem('ol_column_widths');
            } catch (e) {}
        }

        // 保存布局状态到后端（带 debounce）
        function saveLayoutToServer() {
            if (!uiLayoutV2) return;

            if (layoutSaveDebounceTimer) {
                clearTimeout(layoutSaveDebounceTimer);
            }

            layoutSaveDebounceTimer = setTimeout(async () => {
                try {
                    await fetch('/api/settings', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ ui_layout_v2: uiLayoutV2 })
                    });
                } catch (error) {
                    console.warn('保存布局状态失败:', error);
                }
            }, LAYOUT_SAVE_DEBOUNCE_MS);
        }

        // 初始化布局状态
        async function initLayoutState() {
            // 1. 先尝试从后端加载
            let layout = await loadLayoutFromServer();

            // 2. 如果后端没有有效布局，尝试迁移旧 key
            if (!layout) {
                const migrated = migrateOldLayoutKeys();
                if (migrated) {
                    uiLayoutV2 = migrated;
                    // 保存迁移结果到后端
                    try {
                        await fetch('/api/settings', {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ ui_layout_v2: migrated })
                        });
                        // 迁移成功后清理旧 key
                        cleanupOldLayoutKeys();
                        console.log('布局状态迁移完成');
                    } catch (e) {
                        console.warn('保存迁移布局失败:', e);
                    }
                } else {
                    // 使用默认布局
                    uiLayoutV2 = getDefaultLayoutV2();
                }
            } else {
                uiLayoutV2 = layout;
            }

            // 3. 应用布局状态
            applyLayoutState();
        }

        // 应用布局状态到 DOM
        function applyLayoutState() {
            if (!uiLayoutV2) return;

            // 应用侧边栏折叠状态
            const app = document.getElementById('app');
            if (app && uiLayoutV2.sidebar && uiLayoutV2.sidebar.collapsed) {
                app.classList.add('sidebar-collapsed');
            }

            // 应用 mailbox 列宽
            if (uiLayoutV2.mailbox) {
                const groupPanel = document.getElementById('groupPanel');
                const accountPanel = document.getElementById('accountPanel');
                if (groupPanel && uiLayoutV2.mailbox.groupPanelWidth) {
                    groupPanel.style.width = uiLayoutV2.mailbox.groupPanelWidth + 'px';
                }
                if (accountPanel && uiLayoutV2.mailbox.accountPanelWidth) {
                    accountPanel.style.width = uiLayoutV2.mailbox.accountPanelWidth + 'px';
                }
            }

            // 应用 temp-emails 列宽
            if (uiLayoutV2.tempEmails) {
                const tempEmailPanel = document.getElementById('tempEmailPanel');
                if (tempEmailPanel && uiLayoutV2.tempEmails.listPanelWidth) {
                    tempEmailPanel.style.width = uiLayoutV2.tempEmails.listPanelWidth + 'px';
                }
            }
        }

        // 更新布局状态中的侧边栏折叠
        function updateLayoutSidebarCollapsed(collapsed) {
            if (!uiLayoutV2) uiLayoutV2 = getDefaultLayoutV2();
            uiLayoutV2.sidebar.collapsed = collapsed;
            saveLayoutToServer();
        }

        // 更新布局状态中的列宽
        function updateLayoutColumnWidths() {
            if (!uiLayoutV2) uiLayoutV2 = getDefaultLayoutV2();

            // 读取 mailbox 列宽
            const groupPanel = document.getElementById('groupPanel');
            const accountPanel = document.getElementById('accountPanel');
            if (groupPanel && groupPanel.style.width) {
                const w = parseInt(groupPanel.style.width, 10);
                if (!isNaN(w) && w > 0) {
                    uiLayoutV2.mailbox.groupPanelWidth = w;
                }
            }
            if (accountPanel && accountPanel.style.width) {
                const w = parseInt(accountPanel.style.width, 10);
                if (!isNaN(w) && w > 0) {
                    uiLayoutV2.mailbox.accountPanelWidth = w;
                }
            }

            // 读取 temp-emails 列宽
            const tempEmailPanel = document.getElementById('tempEmailPanel');
            if (tempEmailPanel && tempEmailPanel.style.width) {
                const w = parseInt(tempEmailPanel.style.width, 10);
                if (!isNaN(w) && w > 0) {
                    uiLayoutV2.tempEmails.listPanelWidth = w;
                }
            }

            saveLayoutToServer();
        }

        function getUiLanguage() {
            return window.getCurrentUiLanguage ? window.getCurrentUiLanguage() : 'zh';
        }

        function translateAppTextLocal(text) {
            return window.translateAppText ? window.translateAppText(text) : text;
        }

        function formatGroupDisplayName(name) {
            return translateAppTextLocal(String(name || '').trim());
        }

        function formatGroupDescription(description, fallback = '未填写说明') {
            const rawDescription = String(description || '').trim();
            return translateAppTextLocal(rawDescription || fallback);
        }

        function isTempMailboxGroup(groupOrName) {
            const rawName = typeof groupOrName === 'string'
                ? String(groupOrName || '').trim()
                : String(groupOrName?.name || '').trim();
            return rawName === '临时邮箱' || rawName === 'Temp Mailboxes' || rawName === 'Temp Mailbox';
        }

        function formatAccountStatusLabel(status) {
            const normalized = String(status || 'active').trim().toLowerCase();
            const zhStatusMap = {
                active: '正常',
                inactive: '停用',
                disabled: '停用',
                paused: '停用'
            };
            return translateAppTextLocal(zhStatusMap[normalized] || normalized || '正常');
        }

        function isRefreshableOutlookAccount(accountLike) {
            const accountType = String(accountLike?.account_type || 'outlook').trim().toLowerCase();
            const provider = String(accountLike?.provider || 'outlook').trim().toLowerCase();
            return accountType !== 'imap' && provider === 'outlook';
        }

        function formatSelectedItemsLabel(count) {
            return getUiLanguage() === 'en' ? `${count} selected` : `已选 ${count} 项`;
        }

        const pickApiMessage = (payload, fallbackZh, fallbackEn) => (
            window.pickApiMessage ? window.pickApiMessage(payload, fallbackZh, fallbackEn) : (fallbackZh || fallbackEn || '')
        );

        const formatUiDateTime = (dateStr, options = {}) => (
            window.formatUiDateTime ? window.formatUiDateTime(dateStr, options) : (dateStr || '')
        );

        const formatUiRelativeTime = (dateStr, fallbackZh = '从未刷新', fallbackEn = 'Never refreshed') => (
            window.formatUiRelativeTime ? window.formatUiRelativeTime(dateStr, fallbackZh, fallbackEn) : (dateStr || fallbackZh)
        );

        function parseIntegerSetting(value, fallback) {
            if (value === null || value === undefined) {
                return fallback;
            }
            const normalized = String(value).trim();
            if (!normalized) {
                return fallback;
            }
            const parsed = Number.parseInt(normalized, 10);
            return Number.isNaN(parsed) ? fallback : parsed;
        }

        function isAutoPollingEnabledSetting(value) {
            return value === true || value === 'true';
        }

        // 应用标准轮询设置到内部变量（Phase 2: 仅更新变量，实际轮询由统一引擎处理）
        function applyPollingSettings(settings, { restart = false } = {}) {
            // [Phase 3 兼容] 任一开关开启即启用轮询：
            // - enable_auto_polling：合并后的统一开关
            // - enable_compact_auto_poll：deprecated 旧字段，历史用户可能只设置了这个
            autoPollingEnabled = isAutoPollingEnabledSetting(settings.enable_auto_polling)
                || isAutoPollingEnabledSetting(settings.enable_compact_auto_poll);
            maxPollingCount = parseIntegerSetting(settings.polling_count, 5);
            pollingInterval = parseIntegerSetting(settings.polling_interval, 10);
            // [Phase 3] 合并后统一由标准字段驱动引擎
            if (typeof applyPollSettings === 'function') {
                applyPollSettings({
                    enabled: autoPollingEnabled,
                    interval: pollingInterval,
                    maxCount: maxPollingCount
                });
            }
        }

        // ==================== 标准模式轮询指示器 ====================
        // 在标准模式下，在账号卡片邮箱地址旁显示/隐藏轮询绿点。
        // 由统一轮询引擎通过 UI 回调调用（mailbox_compact.js 中根据 mailboxViewMode 分发）。

        function showStandardPollDot(email) {
            if (!email) return;
            var allCards = document.querySelectorAll('#accountList .account-card');
            allCards.forEach(function(card) {
                var emailEl = card.querySelector('.account-email');
                if (emailEl && emailEl.textContent.trim() === email) {
                    // 在 .account-info 容器中添加状态行（避免 .account-email 的 overflow:hidden 裁剪）
                    var infoEl = card.querySelector('.account-info');
                    if (infoEl && !infoEl.querySelector('.standard-poll-status')) {
                        var statusEl = document.createElement('div');
                        statusEl.className = 'standard-poll-status';
                        statusEl.innerHTML = '<span class="standard-poll-dot"></span>' + translateAppTextLocal('轮询监听中…');
                        infoEl.appendChild(statusEl);
                    }
                    // 给卡片加上边框高亮
                    card.classList.add('standard-poll-active');
                }
            });
        }

        function hideStandardPollDot(email) {
            if (email) {
                var allCards = document.querySelectorAll('#accountList .account-card');
                allCards.forEach(function(card) {
                    var emailEl = card.querySelector('.account-email');
                    if (emailEl && emailEl.textContent.trim() === email) {
                        var infoEl = card.querySelector('.account-info');
                        if (infoEl) {
                            var statusEl = infoEl.querySelector('.standard-poll-status');
                            if (statusEl) statusEl.remove();
                        }
                        card.classList.remove('standard-poll-active');
                    }
                });
            } else {
                // 无参数时清除所有
                document.querySelectorAll('.standard-poll-status').forEach(function(el) { el.remove(); });
                document.querySelectorAll('.standard-poll-active').forEach(function(el) { el.classList.remove('standard-poll-active'); });
            }
        }

        // ==================== 主题 & 导航 ====================

        function applyTheme(theme) {
            document.documentElement.dataset.theme = theme;
            localStorage.setItem('ol_theme', theme);
            const btn = document.getElementById('themeToggleBtn');
            if (btn) btn.textContent = theme === 'dark' ? '☀ 浅色模式' : '☾ 深色模式';
        }

        function toggleTheme() {
            const current = document.documentElement.dataset.theme || 'light';
            applyTheme(current === 'dark' ? 'light' : 'dark');
        }

        function applyAccountPanelDensityClasses(panel, width) {
            panel.classList.toggle('is-narrow', width < 240);
            panel.classList.toggle('is-compact', width < 170);
        }

        function navigate(page) {
            currentPage = page;
            // Hide all pages
            document.querySelectorAll('.page').forEach(p => p.classList.add('page-hidden'));
            const target = document.getElementById('page-' + page);
            if (target) {
                target.classList.remove('page-hidden');
                target.style.display = '';
            }
            // Update nav active state
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            const navBtn = document.querySelector(`.nav-item[data-page="${page}"]`);
            if (navBtn) navBtn.classList.add('active');
            // Update topbar
            updateTopbar(page);
            // Close mobile sidebar
            closeSidebar();
            // Load page data
            if (page === 'dashboard' && typeof initOverview === 'function') initOverview();
            if (page === 'mailbox') {
                if (groups.length === 0) {
                    loadGroups();
                } else if (currentGroupId) {
                    loadAccountsByGroup(currentGroupId);
                }
                if (typeof switchMailboxViewMode === 'function') {
                    switchMailboxViewMode(mailboxViewMode);
                }
                syncAccountPanelDensityIfVisible();
                scheduleAccountPanelDensitySync();
            }
            if (page === 'temp-emails' && typeof loadTempEmails === 'function') loadTempEmails(true);
            if (page === 'settings') loadSettings();
            if (page === 'refresh-log') loadRefreshLogPage();
            if (page === 'audit') loadAuditLogPage();
        }

        function updateTopbar(page) {
            const titleEl = document.getElementById('topbarTitle');
            const subtitleEl = document.getElementById('topbarSubtitle');
            const actionsEl = document.getElementById('topbar-actions');
            const mailboxViewModeTemplate = document.getElementById('mailboxViewModeSwitcherTemplate');
            const titles = {
                'dashboard': ['数据概览', '运营数据大盘'],
                'mailbox': ['账号管理', '管理邮箱账号与查看邮件'],
                'temp-emails': ['临时邮箱', '创建和管理临时邮箱'],
                'refresh-log': ['刷新日志', 'Token 刷新历史记录'],
                'settings': ['系统设置', '配置系统参数'],
                'audit': ['审计日志', '系统操作记录']
            };
            const t = titles[page] || [page, ''];
            if (titleEl) titleEl.textContent = translateAppTextLocal(t[0]);
            if (subtitleEl) subtitleEl.textContent = translateAppTextLocal(t[1]);
            // Context actions
            if (actionsEl) {
                actionsEl.classList.remove('topbar-actions-compact');
                if (page === 'mailbox') {
                    const switcherHtml = mailboxViewModeTemplate ? mailboxViewModeTemplate.innerHTML.trim() : '';
                    const isCompactMode = mailboxViewMode === 'compact';
                    actionsEl.innerHTML = isCompactMode ? `
                        ${switcherHtml}
                    ` : `
                        ${switcherHtml}
                        <button class="btn-inline primary" onclick="showAddAccountModal()">＋ 添加账号</button>
                        <button class="btn-inline ghost" onclick="showExportModal()">📤 导出</button>
                        <button class="btn-inline ghost" onclick="showRefreshModal()">🔄 全量刷新 Token</button>
                    `;
                    actionsEl.classList.toggle('topbar-actions-compact', isCompactMode);
                    if (subtitleEl) {
                        subtitleEl.textContent = translateAppTextLocal(
                            isCompactMode ? '按分组查看账号摘要与验证码' : '管理邮箱账号与查看邮件'
                        );
                    }
                    const standardBtn = document.getElementById('mailboxStandardModeBtn');
                    const compactBtn = document.getElementById('mailboxCompactModeBtn');
                    if (standardBtn) {
                        standardBtn.classList.toggle('active', mailboxViewMode === 'standard');
                    }
                    if (compactBtn) {
                        compactBtn.classList.toggle('active', mailboxViewMode === 'compact');
                    }
                } else if (page === 'temp-emails') {
                    actionsEl.innerHTML = `
                        <button class="btn btn-sm btn-primary" onclick="generateTempEmail()">＋ 创建邮箱</button>
                    `;
                } else {
                    actionsEl.innerHTML = '';
                }
            }
        }

        function toggleSidebar() {
            const isMobile = window.innerWidth <= 768;
            if (isMobile) {
                // Mobile: toggle drawer
                const sidebar = document.getElementById('sidebar');
                const backdrop = document.getElementById('sidebarBackdrop');
                sidebar.classList.toggle('mob-open');
                backdrop.classList.toggle('show');
            } else {
                // Desktop: toggle collapsed state
                const app = document.getElementById('app');
                app.classList.toggle('sidebar-collapsed');
                const collapsed = app.classList.contains('sidebar-collapsed');
                // 使用新的布局状态管理保存
                updateLayoutSidebarCollapsed(collapsed);
            }
        }

        function closeSidebar() {
            const sidebar = document.getElementById('sidebar');
            const backdrop = document.getElementById('sidebarBackdrop');
            if (sidebar) sidebar.classList.remove('mob-open');
            if (backdrop) backdrop.classList.remove('show');
        }

        function logout() {
            if (!confirm(translateAppTextLocal('确认退出登录？'))) return;
            window.location.href = '/logout';
        }

        // ==================== Dashboard ====================

        let _dashboardLoading = false;

        async function loadDashboard() {
            // Bug 3 修复：防重入，避免 dashboard 被多次并发触发导致重复轮询
            if (_dashboardLoading) return;
            _dashboardLoading = true;
            try {
                const [groupsRes, tempRes] = await Promise.all([
                    fetch('/api/groups'),
                    fetch('/api/temp-emails').catch(() => ({ json: () => ({ success: false }) }))
                ]);
                const groupsData = await groupsRes.json();
                const tempData = await tempRes.json();

                let totalAccounts = 0, validTokens = 0, expiredTokens = 0;
                const groupSummary = [];

                if (groupsData.success && groupsData.groups) {
                    for (const g of groupsData.groups) {
                        const accRes = await fetch(`/api/accounts?group_id=${g.id}`);
                        const accData = await accRes.json();
                        const accounts = accData.success ? (accData.accounts || []) : [];
                        totalAccounts += accounts.length;
                        accounts.forEach(a => {
                            if (!isRefreshableOutlookAccount(a)) {
                                return;
                            }
                            if (a.last_refresh_status === 'failed') expiredTokens++;
                            else validTokens++;
                        });
                        groupSummary.push({ id: g.id, name: g.name, color: g.color || '#666', count: accounts.length, isTempGroup: g.name === '临时邮箱' });
                    }
                }

                // Update stat cards
                const el = (id, val) => { const e = document.getElementById(id); if (e) e.textContent = val; };
                el('statTotalAccounts', totalAccounts);
                el('statValidTokens', validTokens);
                el('statExpiredTokens', expiredTokens);
                el('statTempEmails', tempData.success ? (tempData.emails || []).length : 0);

                // Update topbar subtitle with summary
                const sub = document.getElementById('topbarSubtitle');
                if (sub && currentPage === 'dashboard') {
                    sub.textContent = translateAppTextLocal(`共 ${totalAccounts} 个账号 · ${validTokens} 个 Token 有效`);
                }

                // Group summary list
                const groupListEl = document.getElementById('dashboardGroupList');
                if (groupListEl) {
                    if (groupSummary.length === 0) {
                        groupListEl.innerHTML = `<li style="color:var(--text-muted);padding:1rem;">${translateAppTextLocal('暂无分组')}</li>`;
                    } else {
                        groupListEl.innerHTML = groupSummary.map(g => {
                            const clickAction = g.isTempGroup
                                ? `navigate('temp-emails')`
                                : `navigate('mailbox'); setTimeout(function(){ selectGroup(${g.id}); }, 100)`;
                            return `<li style="cursor:pointer;" onclick="${clickAction}"><span style="display:flex;align-items:center;gap:0.5rem;"><span class="group-color-dot" style="background:${escapeHtml(g.color)};"></span>${escapeHtml(g.name)}</span><span class="badge badge-gray">${g.count}</span></li>`;
                        }).join('');
                    }
                }

                // Refresh log summary
                const refreshListEl = document.getElementById('dashboardRefreshList');
                if (refreshListEl) {
                    try {
                        const refreshRes = await fetch('/api/accounts/refresh-stats');
                        const refreshData = await refreshRes.json();
                        if (refreshData.success && refreshData.stats) {
                            const rs = refreshData.stats;
                            refreshListEl.innerHTML = `
                                <li><span>${translateAppTextLocal('上次刷新时间')}</span><span class="badge badge-gray">${escapeHtml(rs.last_refresh_time || translateAppTextLocal('暂无'))}</span></li>
                                <li><span>${translateAppTextLocal('成功账号数')}</span><span class="badge" style="background:var(--clr-jade);color:white;">${rs.success_count}</span></li>
                                <li><span>${translateAppTextLocal('失败账号数')}</span><span class="badge" style="background:${rs.failed_count > 0 ? 'var(--clr-danger)' : 'var(--clr-jade)'};color:white;">${rs.failed_count}</span></li>
                            `;
                        } else {
                            refreshListEl.innerHTML = `<li style="color:var(--text-muted);padding:1rem;">${translateAppTextLocal('暂无刷新记录')}</li>`;
                        }
                    } catch (e) {
                        refreshListEl.innerHTML = `<li style="color:var(--text-muted);padding:1rem;">${translateAppTextLocal('前往刷新日志查看详情')}</li>`;
                    }
                }
            } catch (e) {
                console.error('Dashboard load error:', e);
            } finally {
                _dashboardLoading = false;
            }
        }

        // ==================== 分组搜索过滤 ====================

        function filterGroups(query) {
            const items = document.querySelectorAll('#groupList .group-item');
            const q = query.toLowerCase();
            items.forEach(item => {
                const name = item.querySelector('.group-name');
                if (name && name.textContent.toLowerCase().includes(q)) {
                    item.style.display = '';
                } else {
                    item.style.display = q ? 'none' : '';
                }
            });
        }

        // ==================== 三栏拖拽调整 ====================

        function updateAccountPanelDensity() {
            const panel = document.getElementById('accountPanel');
            if (!panel) return;
            const width = panel.getBoundingClientRect().width;
            applyAccountPanelDensityClasses(panel, width);
        }

        function syncAccountPanelDensityIfVisible() {
            const page = document.getElementById('page-mailbox');
            const panel = document.getElementById('accountPanel');
            if (!page || !panel || page.classList.contains('page-hidden')) {
                return false;
            }

            const width = panel.getBoundingClientRect().width;
            if (width <= 0) {
                return false;
            }

            applyAccountPanelDensityClasses(panel, width);
            return true;
        }

        function scheduleAccountPanelDensitySync() {
            // 使用双层 rAF（以及 setTimeout fallback）刻意等待切页/拖拽后的布局回流完成，
            // 避免首次进入 mailbox 时按 0 宽或旧宽度错误计算紧凑模式。
            const runSync = () => {
                accountPanelDensitySyncHandle = null;
                syncAccountPanelDensityIfVisible();
            };

            if (accountPanelDensitySyncHandle !== null) {
                if (typeof cancelAnimationFrame === 'function') {
                    cancelAnimationFrame(accountPanelDensitySyncHandle);
                } else {
                    clearTimeout(accountPanelDensitySyncHandle);
                }
                accountPanelDensitySyncHandle = null;
            }

            if (typeof requestAnimationFrame === 'function') {
                accountPanelDensitySyncHandle = requestAnimationFrame(() => {
                    accountPanelDensitySyncHandle = requestAnimationFrame(runSync);
                });
                return;
            }

            accountPanelDensitySyncHandle = setTimeout(runSync, 0);
        }

        function initResizeHandles() {
            // 支持新的 .workspace-resizer 和旧的 .resize-handle 类名
            document.querySelectorAll('.workspace-resizer, .resize-handle').forEach(handle => {
                handle.addEventListener('mousedown', function(e) {
                    e.preventDefault();
                    const leftId = this.dataset.left;
                    const rightId = this.dataset.right;
                    const leftPanel = document.getElementById(leftId);
                    const rightPanel = document.getElementById(rightId);
                    if (!leftPanel) return;

                    this.classList.add('active');
                    document.body.style.cursor = 'col-resize';
                    document.body.style.userSelect = 'none';

                    const startX = e.clientX;
                    const startWidth = leftPanel.offsetWidth;

                    function onMouseMove(ev) {
                        const delta = ev.clientX - startX;
                        const newWidth = Math.max(120, Math.min(startWidth + delta, 500));
                        leftPanel.style.width = newWidth + 'px';
                        updateAccountPanelDensity();
                    }

                    function onMouseUp() {
                        handle.classList.remove('active');
                        document.body.style.cursor = '';
                        document.body.style.userSelect = '';
                        document.removeEventListener('mousemove', onMouseMove);
                        document.removeEventListener('mouseup', onMouseUp);
                        // 使用新的布局状态管理保存列宽
                        updateLayoutColumnWidths();
                    }

                    document.addEventListener('mousemove', onMouseMove);
                    document.addEventListener('mouseup', onMouseUp);
                });
            });

            // 布局状态已在 initLayoutState() 中恢复，这里只需更新紧凑模式
            if (currentPage === 'mailbox') {
                syncAccountPanelDensityIfVisible();
                scheduleAccountPanelDensitySync();
            }
            window.addEventListener('resize', scheduleAccountPanelDensitySync, { passive: true });
        }

        // 平板断点 groups 栏展开/折叠 — 方案 B: 点击 ☰ 按钮后 groups 作为浮动面板覆盖在内容上方
        // 仅在平板断点(769-1024px)下有意义，按钮由 CSS .btn-toggle-groups 控制显隐
        // HTML 绑定: index.html 中 #btnToggleGroups onclick="toggleGroupsColumn()"
        function toggleGroupsColumn() {
            const groupPanel = document.getElementById('groupPanel');
            const btn = document.getElementById('btnToggleGroups');
            if (!groupPanel) return;
            const isExpanded = groupPanel.classList.toggle('groups-expanded');
            if (isExpanded) {
                groupPanel.style.display = 'flex';
                groupPanel.style.position = 'absolute';
                groupPanel.style.left = '60px';
                groupPanel.style.top = '52px';
                groupPanel.style.height = 'calc(100vh - 52px)';
                groupPanel.style.width = '220px';
                groupPanel.style.zIndex = '20';
                groupPanel.style.boxShadow = '4px 0 24px rgba(0,0,0,0.25)';
                groupPanel.style.borderRight = '1px solid var(--border)';
                groupPanel.style.background = 'var(--bg-card)';
            } else {
                groupPanel.style.cssText = '';
                handleResponsiveGroups();
            }
            if (btn) {
                btn.title = isExpanded ? translateAppTextLocal('收起分组') : translateAppTextLocal('展开分组');
            }
        }

        // resize 监听: 窗口尺寸变化时自动同步 groups 栏显隐状态
        // 与 CSS @media 断点(768/1024px) 配合，但通过 JS 内联 style 确保即时生效
        // 展开(groups-expanded)状态下不干预，避免覆盖用户操作
        function handleResponsiveGroups() {
            const groupPanel = document.getElementById('groupPanel');
            if (!groupPanel) return;
            const isExpanded = groupPanel.classList.contains('groups-expanded');
            // 展开状态下不干预
            if (isExpanded) return;
            const width = window.innerWidth;
            if (width > 768 && width <= 1024) {
                groupPanel.style.display = 'none';
            } else {
                groupPanel.style.cssText = '';
            }
        }
        window.addEventListener('resize', handleResponsiveGroups, { passive: true });

        // ==================== 邮件详情显示控制 ====================

        function showEmailDetailSection() {
            const section = document.getElementById('emailDetailSection');
            if (section) section.style.display = 'flex';
        }

        function hideEmailDetailSection() {
            const section = document.getElementById('emailDetailSection');
            if (section) section.style.display = 'none';
        }

        function stopRefresh() {
            // Placeholder for stopping a bulk refresh operation
            showToast(translateAppTextLocal('刷新已停止'), 'warn');
            const bar = document.getElementById('refreshProgressBar');
            if (bar) bar.style.display = 'none';
        }

        // ==================== CSRF 防护 ====================

        function isMutationRequest(method) {
            const normalizedMethod = (method || 'GET').toUpperCase();
            return !['GET', 'HEAD', 'OPTIONS'].includes(normalizedMethod);
        }

        function cloneHeaders(headers) {
            return new Headers(headers || {});
        }

        function buildFetchRequest(input, options = {}) {
            if (input instanceof Request) {
                const mergedHeaders = cloneHeaders(input.headers);
                const optionHeaders = cloneHeaders(options.headers);
                optionHeaders.forEach((value, key) => mergedHeaders.set(key, value));

                const requestOptions = {
                    ...options,
                    headers: mergedHeaders
                };

                return {
                    method: (requestOptions.method || input.method || 'GET').toUpperCase(),
                    setHeader(name, value) {
                        mergedHeaders.set(name, value);
                    },
                    execute() {
                        return originalFetch(new Request(input, requestOptions));
                    }
                };
            }

            const requestOptions = {
                ...options,
                headers: cloneHeaders(options.headers)
            };

            return {
                method: (requestOptions.method || 'GET').toUpperCase(),
                setHeader(name, value) {
                    requestOptions.headers.set(name, value);
                },
                execute() {
                    return originalFetch(input, requestOptions);
                }
            };
        }

        async function parseJsonSafely(response) {
            const contentType = response.headers.get('content-type') || '';
            if (!contentType.includes('application/json')) {
                return null;
            }

            try {
                return await response.clone().json();
            } catch (error) {
                return null;
            }
        }

        function isCsrfFailurePayload(payload) {
            if (!payload || typeof payload !== 'object') {
                return false;
            }

            const error = payload.error && typeof payload.error === 'object' ? payload.error : payload;
            return error.code === 'CSRF_TOKEN_INVALID';
        }

        // 初始化 CSRF Token
        async function initCSRFToken({ force = false, silent = false } = {}) {
            if (!force && csrfToken) {
                return csrfToken;
            }

            // 单飞刷新：并发写请求共享同一次 token 拉取；若后端明确返回 CSRF_TOKEN_INVALID，
            // fetch 包装层会强制刷新 token 并只重放一次原请求，避免无限重试或抢刷 token。
            if (csrfTokenRefreshPromise) {
                return csrfTokenRefreshPromise;
            }

            csrfTokenRefreshPromise = (async () => {
                try {
                    const response = await originalFetch('/api/csrf-token');
                    if (!response.ok) {
                        throw new Error(`csrf_token_http_${response.status}`);
                    }

                    const data = await response.json();
                    if (data.csrf_disabled) {
                        csrfToken = null;
                        console.warn('CSRF protection is disabled. Install flask-wtf for better security.');
                        return csrfToken;
                    }

                    if (!data.csrf_token) {
                        throw new Error('csrf_token_missing_in_response');
                    }

                    csrfToken = data.csrf_token;
                    return csrfToken;
                } catch (error) {
                    if (!silent) {
                        showToast(translateAppTextLocal('初始化安全会话失败，请刷新页面后重试'), 'error');
                    }
                    console.error('Failed to initialize CSRF token:', error);
                    throw error;
                } finally {
                    csrfTokenRefreshPromise = null;
                }
            })();

            return csrfTokenRefreshPromise;
        }

        // 包装 fetch 请求，自动添加 CSRF Token
        const originalFetch = window.fetch;
        window.fetch = async function (input, options = {}) {
            const request = buildFetchRequest(input, options);
            const shouldAttachCsrf = isMutationRequest(request.method);

            if (shouldAttachCsrf && !csrfToken) {
                try {
                    await initCSRFToken({ silent: true });
                } catch (error) {
                    // 让原请求继续发出，由后端返回明确的 CSRF 错误提示
                }
            }

            if (shouldAttachCsrf && csrfToken) {
                request.setHeader('X-CSRFToken', csrfToken);
            }

            const response = await request.execute();
            if (!shouldAttachCsrf || options.__skipCsrfRetry || response.status !== 400) {
                return response;
            }

            const payload = await parseJsonSafely(response);
            if (!isCsrfFailurePayload(payload)) {
                return response;
            }

            try {
                await initCSRFToken({ force: true, silent: true });
            } catch (error) {
                return response;
            }

            if (!csrfToken) {
                return response;
            }

            const retryRequest = buildFetchRequest(input, {
                ...options,
                __skipCsrfRetry: true
            });
            retryRequest.setHeader('X-CSRFToken', csrfToken);
            return retryRequest.execute();
        };

        // 初始化
        document.addEventListener('DOMContentLoaded', async function () {
            // 应用保存的主题
            applyTheme(localStorage.getItem('ol_theme') || 'light');

            // 初始化 CSRF Token。失败时不阻断首屏，其它初始化继续执行，
            // 具体的写请求再走按需恢复逻辑。
            try {
                await initCSRFToken();
            } catch (error) {}

            // 初始化布局状态（从后端读取或迁移旧 localStorage）
            await initLayoutState();

            closeAllModals();
            loadGroups();
            if (typeof loadTags === 'function') {
                loadTags();
            }
            initColorPicker();
            initEmailListScroll();
            initResizeHandles();
            handleResponsiveGroups();

            // 初始化轮询设置
            initPollingSettings();

            // 初始化“一键更新配置”更新方式切换显隐逻辑（避免 index.html 内联脚本）
            initUpdateMethodConfigToggles();

            // 请求浏览器通知权限
            if ('Notification' in window && Notification.permission === 'default') {
                Notification.requestPermission();
            }

            // 绑定搜索框事件
            const searchInput = document.getElementById('globalSearch');
            if (searchInput) {
                const debouncedSearch = debounce((e) => {
                    searchAccounts(e.target.value);
                }, 300);
                searchInput.addEventListener('input', debouncedSearch);
            }

            // 加载数据概览
            if (typeof initOverview === 'function') initOverview();

            // 检查是否有版本更新（页面加载时调一次）
            checkVersionUpdate();
        });

        // 初始化颜色选择器
        function initColorPicker() {
            document.querySelectorAll('.color-option').forEach(option => {
                option.addEventListener('click', function () {
                    document.querySelectorAll('.color-option').forEach(o => o.classList.remove('selected'));
                    this.classList.add('selected');
                    selectedColor = this.dataset.color;
                    // 同步更新自定义颜色输入框
                    document.getElementById('customColorInput').value = selectedColor;
                    document.getElementById('customColorHex').value = selectedColor;
                });
            });
        }

        // 初始化邮件列表滚动监听
        function initEmailListScroll() {
            const emailList = document.getElementById('emailList');
            emailList.addEventListener('scroll', function () {
                // 检查是否滚动到底部
                if (emailList.scrollHeight - emailList.scrollTop <= emailList.clientHeight + 50) {
                    if (!isLoadingMore && hasMoreEmails && currentAccount && !isTempEmailGroup) {
                        loadMoreEmails();
                    }
                }
            });
        }

        // 加载更多邮件
        async function loadMoreEmails() {
            if (isLoadingMore || !hasMoreEmails) return;

            isLoadingMore = true;
            currentSkip += 20; // 每页20封

            // 在列表底部显示加载状态
            const emailList = document.getElementById('emailList');
            const loadingDiv = document.createElement('div');
            loadingDiv.className = 'loading-overlay';
            loadingDiv.id = 'loadingMore';
            loadingDiv.innerHTML = `<span class="spinner"></span> ${translateAppTextLocal('加载更多…')}`;
            emailList.appendChild(loadingDiv);

            // 禁用按钮
            const refreshBtn = document.querySelector('.refresh-btn');
            const folderTabs = document.querySelectorAll('.email-tab');
            if (refreshBtn) {
                refreshBtn.disabled = true;
            }
            folderTabs.forEach(tab => tab.disabled = true);

            try {
                const response = await fetch(
                    `/api/emails/${encodeURIComponent(currentAccount)}?method=${currentMethod}&folder=${currentFolder}&skip=${currentSkip}&top=20`
                );
                const data = await response.json();

                if (data.success && data.emails.length > 0) {
                    // 追加新邮件到列表
                    const mergedEmails = currentEmails.concat(data.emails || []);
                    currentEmails = (typeof sortEmailsByNewestFirst === 'function')
                        ? sortEmailsByNewestFirst(mergedEmails)
                        : mergedEmails;
                    hasMoreEmails = data.has_more;

                    // 移除加载状态
                    const loadingEl = document.getElementById('loadingMore');
                    if (loadingEl) loadingEl.remove();

                    renderEmailList(currentEmails, { scrollToTop: false });

                    // 更新邮件数量
                    document.getElementById('emailCount').textContent = `(${currentEmails.length})`;

                    // 更新缓存
                    if (currentAccount && !isTempEmailGroup) {
                        const cacheKey = `${currentAccount}_${currentFolder}`;
                        if (emailListCache[cacheKey]) {
                            emailListCache[cacheKey].emails = currentEmails;
                            emailListCache[cacheKey].has_more = hasMoreEmails;
                            emailListCache[cacheKey].skip = currentSkip;
                        }
                    }
                } else {
                    hasMoreEmails = false;
                    // 显示"没有更多邮件"
                    const loadingEl = document.getElementById('loadingMore');
                    if (loadingEl) {
                        loadingEl.innerHTML = `<div style="text-align:center;padding:20px;color:#999;font-size:13px;">${translateAppTextLocal('没有更多邮件了')}</div>`;
                    }
                }
            } catch (error) {
                const loadingEl = document.getElementById('loadingMore');
                if (loadingEl) loadingEl.remove();
                showToast(translateAppTextLocal('加载失败'), 'error');
            } finally {
                isLoadingMore = false;
                // 启用按钮
                if (refreshBtn) {
                    refreshBtn.disabled = false;
                }
                folderTabs.forEach(tab => tab.disabled = false);
            }
        }

        // 切换文件夹（不触发查询）
        function switchFolder(folder) {
            if (currentFolder === folder) return;

            currentFolder = folder;

            // 更新按钮状态
            document.querySelectorAll('.email-tab').forEach(tab => {
                tab.classList.toggle('active', tab.dataset.folder === folder);
            });

            const cacheKey = `${currentAccount}_${folder}`;

            // 检查是否有缓存
            if (emailListCache[cacheKey]) {
                const cache = emailListCache[cacheKey];
                currentEmails = (typeof sortEmailsByNewestFirst === 'function')
                    ? sortEmailsByNewestFirst(cache.emails || [])
                    : (cache.emails || []);
                hasMoreEmails = cache.has_more;
                currentSkip = cache.skip;
                currentMethod = cache.method || 'graph';

                cache.emails = currentEmails;

                // 恢复 UI
                const methodTag = document.getElementById('methodTag');
                methodTag.textContent = currentMethod;
                methodTag.style.display = 'inline';
                document.getElementById('emailCount').textContent = `(${currentEmails.length})`;

                renderEmailList(currentEmails);
            } else {
                // 清空邮件列表，显示提示
                document.getElementById('emailList').innerHTML = `
                    <div class="empty-state">
                        <span class="empty-icon">📬</span>
                        <p>${translateAppTextLocal(folder === 'inbox' ? '点击"获取邮件"按钮获取收件箱' : '点击"获取邮件"按钮获取垃圾邮件')}</p>
                    </div>
                `;
                document.getElementById('emailCount').textContent = '';
                document.getElementById('methodTag').style.display = 'none';

                // 重置分页状态
                currentEmails = [];
                currentSkip = 0;
                hasMoreEmails = true;
            }
        }

        // 选择自定义颜色（颜色选择器）
        function selectCustomColor(color) {
            selectedColor = color;
            document.getElementById('customColorHex').value = color;
            // 取消预设颜色的选中状态
            document.querySelectorAll('.color-option').forEach(o => o.classList.remove('selected'));
        }

        // 选择自定义颜色（十六进制输入）
        function selectCustomColorHex(value) {
            // 验证十六进制颜色格式
            const hexPattern = /^#[0-9A-Fa-f]{6}$/;
            if (hexPattern.test(value)) {
                selectedColor = value;
                document.getElementById('customColorInput').value = value;
                // 取消预设颜色的选中状态
                document.querySelectorAll('.color-option').forEach(o => o.classList.remove('selected'));
            } else {
                showToast(translateAppTextLocal('请输入有效的十六进制颜色（如 #FF5500）'), 'error');
            }
        }

        // 显示消息提示
        function showToast(message, type = 'info', errorDetail = null, persistent = false) {
            let container = document.getElementById('toast-container');
            if (!container) {
                container = document.createElement('div');
                container.id = 'toast-container';
                container.setAttribute('aria-live', 'polite');
                document.body.appendChild(container);
            }

            const toast = document.createElement('div');
            toast.className = 'toast ' + type;

            const messageSpan = document.createElement('span');
            messageSpan.textContent = translateAppTextLocal(message);
            toast.appendChild(messageSpan);

            if (errorDetail && type === 'error') {
                const detailLink = document.createElement('a');
                detailLink.href = 'javascript:void(0)';
                detailLink.textContent = ' ' + translateAppTextLocal('[详情]');
                detailLink.style.cssText = 'color:var(--clr-danger);text-decoration:underline;margin-left:8px;';
                detailLink.onclick = function (e) {
                    e.stopPropagation();
                    showErrorDetailModal(errorDetail);
                };
                toast.appendChild(detailLink);
            }

            container.appendChild(toast);

            if (persistent) {
                // persistent 模式：追加关闭按钮，不自动消失
                const closeBtn = document.createElement('button');
                closeBtn.textContent = '×';
                closeBtn.style.cssText = 'background:none;border:none;color:inherit;cursor:pointer;margin-left:12px;font-size:1.1rem;opacity:0.8;';
                closeBtn.onclick = () => {
                    toast.style.opacity = '0';
                    setTimeout(() => toast.remove(), 300);
                };
                toast.appendChild(closeBtn);
            } else {
                const duration = (errorDetail && type === 'error') ? 8000 : 3000;
                setTimeout(() => {
                    toast.style.opacity = '0';
                    toast.style.transform = 'translateX(30px)';
                    setTimeout(() => toast.remove(), 300);
                }, duration);
            }
        }

        function buildRefreshErrorSuggestions({ accountType, provider, errorMessage }) {
            const language = getUiLanguage();
            const normalizedAccountType = String(accountType || 'outlook').trim().toLowerCase();
            const normalizedProvider = String(provider || 'outlook').trim().toLowerCase();
            const normalizedErrorMessage = String(errorMessage || '').trim();
            const looksLikeTokenRefreshError = /aadsts|refresh[_\s-]?token|invalid[_\s-]?grant|expired/i.test(normalizedErrorMessage);

            if (normalizedAccountType === 'imap') {
                if (normalizedProvider === 'gmail') {
                    return language === 'en'
                        ? [
                            'Confirm IMAP is enabled and use an app password instead of your normal account password.',
                            'If this looks like an old Outlook token-refresh error, switch the account to IMAP credentials and save again.',
                            'Re-check the IMAP host, port, and SSL settings before retrying.',
                        ]
                        : [
                            '请确认 Gmail 已开启 IMAP，并使用应用专用密码而不是普通登录密码。',
                            '如果这里其实是旧的 Outlook token-refresh error，请把账号切回 IMAP 凭据后重新保存。',
                            '请重新检查 IMAP 主机、端口和 SSL 配置后再重试。',
                        ];
                }

                return language === 'en'
                    ? [
                        'Check the IMAP host, port, SSL/TLS, and account password settings.',
                        'Confirm the mailbox provider allows IMAP login from third-party apps.',
                        'If this error came from a migrated Outlook account, remove the old token-refresh settings and save the IMAP credentials again.',
                    ]
                    : [
                        '请检查 IMAP 主机、端口、SSL/TLS 和账号密码配置是否正确。',
                        '请确认当前邮箱服务商允许第三方客户端通过 IMAP 登录。',
                        '如果这是从旧 Outlook 账号迁移过来的异常，请清理旧的刷新 Token 配置并重新保存 IMAP 凭据。',
                    ];
            }

            if (looksLikeTokenRefreshError) {
                return language === 'en'
                    ? [
                        'Check whether the Client ID and Refresh Token are complete and do not contain extra spaces.',
                        'Use the "Get Refresh Token" flow again to generate a fresh authorization token.',
                        'Confirm the Microsoft account or tenant permissions have not been revoked or expired.',
                    ]
                    : [
                        '请检查 Client ID 和 Refresh Token 是否填写完整且没有多余空格。',
                        '请重新使用“获取 Refresh Token”功能生成新的授权凭据。',
                        '请确认 Microsoft 账号权限未被撤销，且租户策略没有使当前 Token 失效。',
                    ];
            }

            return language === 'en'
                ? [
                    'Open the account editor and verify the saved Outlook authorization information.',
                    'Retry the refresh after confirming network, proxy, and Microsoft service availability.',
                    'If the problem persists, re-authorize the account to obtain a new Refresh Token.',
                ]
                : [
                    '请打开账号编辑弹窗，确认当前保存的 Outlook 授权信息仍然有效。',
                    '请检查网络、代理和 Microsoft 服务状态后再次尝试刷新。',
                    '如果问题持续存在，请重新授权该账号并获取新的 Refresh Token。',
                ];
        }

        // 显示刷新错误信息
        function showRefreshError(accountId, errorMessage, accountEmail, accountType = 'outlook', provider = 'outlook') {
            document.getElementById('refreshErrorModal').classList.add('show');
            document.getElementById('refreshErrorEmail').textContent = translateAppTextLocal(`账号：${accountEmail || '未知'}`);
            document.getElementById('refreshErrorMessage').textContent = translateAppTextLocal(errorMessage);
            const suggestionsEl = document.getElementById('refreshErrorSuggestions');
            const suggestions = buildRefreshErrorSuggestions({ accountType, provider, errorMessage });
            if (suggestionsEl) {
                suggestionsEl.innerHTML = suggestions.map(item => `<li>${escapeHtml(item)}</li>`).join('');
            }
            document.getElementById('editAccountFromErrorBtn').onclick = function () {
                hideRefreshErrorModal();
                showEditAccountModal(accountId);
            };
        }

        // 隐藏刷新错误模态框
        function hideRefreshErrorModal() {
            document.getElementById('refreshErrorModal').classList.remove('show');
        }

        // ==================== 统一错误处理相关 ====================

        // 显示统一错误详情模态框
        function showErrorDetailModal(error) {
            document.getElementById('errorDetailModal').classList.add('show');
            document.getElementById('errorModalUserMessage').textContent = window.resolveApiErrorMessage
                ? window.resolveApiErrorMessage(error, '发生未知错误', 'Unknown error')
                : (error.message || '发生未知错误');
            document.getElementById('errorModalCode').textContent = error.code || '-';
            document.getElementById('errorModalType').textContent = error.type || '-';
            document.getElementById('errorModalStatus').textContent = error.status || '-';
            document.getElementById('errorModalTraceId').textContent = error.trace_id || '-';

            const detailsEl = document.getElementById('errorModalDetails');
            const detailsContainer = document.getElementById('errorModalDetailsContainer');
            const toggleBtn = document.getElementById('toggleTraceBtn');

            detailsEl.textContent = error.details || translateAppTextLocal('暂无详细技术堆栈信息');

            // 重置堆栈显示状态
            detailsContainer.style.display = 'none';
            toggleBtn.textContent = translateAppTextLocal('显示堆栈/细节');
        }

        // 隐藏统一错误详情模态框
        function hideErrorDetailModal() {
            document.getElementById('errorDetailModal').classList.remove('show');
        }

        // 邮件获取失败详情弹框
        function showEmailFetchErrorModal(details) {
            if (!details) return;

            const methodNames = {
                'graph': 'Graph API',
                'imap_new': 'IMAP（新服务器）',
                'imap_old': 'IMAP（旧服务器）'
            };

            function translateError(err) {
                if (!err) return '未知错误';
                // err 可能是 string 或 object
                if (typeof err === 'string') return err;

                const code = err.code || '';
                const details = typeof err.details === 'string' ? err.details : JSON.stringify(err.details || '');
                const msg = err.message || '';

                // 翻译常见错误
                if (code === 'GRAPH_TOKEN_EXCEPTION' && details.includes('ProxyError')) {
                    return '代理连接失败：无法连接到代理服务器，请检查代理地址是否正确以及代理是否在运行';
                }
                if (code === 'GRAPH_TOKEN_FAILED' || code === 'IMAP_TOKEN_FAILED') {
                    if (details.includes('invalid_grant')) {
                        return 'Token 已失效或权限不足：请重新授权登录或更换 refresh_token';
                    }
                    if (details.includes('invalid_client')) {
                        return 'Client ID 无效：请检查 client_id 配置是否正确';
                    }
                    return `令牌获取失败：${msg}`;
                }
                if (code === 'EMAIL_FETCH_FAILED') {
                    return `获取邮件失败：${msg}`;
                }
                if (code === 'IMAP_CONNECTION_FAILED') {
                    return 'IMAP 连接失败：无法连接到邮件服务器';
                }
                return msg || details || '未知错误';
            }

            let html = '';
            const methods = ['graph', 'imap_new', 'imap_old'];
            methods.forEach(method => {
                const err = details[method];
                if (err !== undefined) {
                    const name = methodNames[method] || method;
                    const reason = translateError(err);
                    const codeText = (err && typeof err === 'object') ? (err.code || '-') : '-';
                    html += `
                        <div style="background: #fff5f5; border: 1px solid #fde2e2; border-radius: 8px; padding: 14px 16px; margin-bottom: 12px;">
                            <div style="font-weight: 600; color: #dc3545; margin-bottom: 6px; font-size: 14px;">${name}</div>
                            <div style="color: #333; font-size: 13px; line-height: 1.6;">${reason}</div>
                            <div style="color: #999; font-size: 12px; margin-top: 4px;">错误代码: ${codeText}</div>
                        </div>
                    `;
                }
            });

            if (!html) {
                html = '<div style="color:#666;">无详细错误信息</div>';
            }

            document.getElementById('emailFetchErrorContent').innerHTML = html;
            document.getElementById('emailFetchErrorModal').classList.add('show');
        }

        function hideEmailFetchErrorModal() {
            document.getElementById('emailFetchErrorModal').classList.remove('show');
        }

        // 切换堆栈信息的显示/隐藏
        function toggleStackTrace() {
            const container = document.getElementById('errorModalDetailsContainer');
            const btn = document.getElementById('toggleTraceBtn');

            if (container.style.display === 'none') {
                container.style.display = 'block';
                btn.textContent = translateAppTextLocal('隐藏堆栈/细节');
            } else {
                container.style.display = 'none';
                btn.textContent = translateAppTextLocal('显示堆栈/细节');
            }
        }

        // 复制错误详情到剪贴板
        function copyErrorDetails() {
            const userMessage = document.getElementById('errorModalUserMessage').textContent;
            const details = document.getElementById('errorModalDetails').textContent;
            const code = document.getElementById('errorModalCode').textContent;
            const type = document.getElementById('errorModalType').textContent;
            const status = document.getElementById('errorModalStatus').textContent;
            const traceId = document.getElementById('errorModalTraceId').textContent;
            const userMessageHeader = translateAppTextLocal('【用户错误信息】');
            const detailHeader = translateAppTextLocal('【错误详情】');
            const technicalHeader = translateAppTextLocal('【技术堆栈/细节】');

            const fullErrorText = `
${userMessageHeader}
${userMessage}

${detailHeader}
Code: ${code}
Type: ${type}
Status: ${status}
Trace ID: ${traceId}

${technicalHeader}
${details}
            `.trim();

            navigator.clipboard.writeText(fullErrorText).then(() => {
                showToast(translateAppTextLocal('错误详情已复制'), 'success');
            }).catch(() => {
                // 降级方案
                const textarea = document.createElement('textarea');
                textarea.value = fullErrorText;
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
                showToast(translateAppTextLocal('错误详情已复制'), 'success');
            });
        }

        // 统一处理 API 响应错误
        function handleApiError(data, defaultMessage = '请求失败') {
            if (!data.success) {
                const error = data.error || data;
                const userMessage = window.resolveApiErrorMessage
                    ? window.resolveApiErrorMessage(error, defaultMessage, 'Request failed')
                    : (typeof error === 'string' ? translateAppTextLocal(error) : translateAppTextLocal(defaultMessage));
                showToast(userMessage, 'error', error && typeof error === 'object' ? error : null);
                return true;
            }
            return false;
        }

        function escapeJs(str) {
            if (!str) return '';
            return str.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"').replace(/\n/g, '\\n').replace(/\r/g, '\\r');
        }

        // ==================== 工具函数 ====================

        // HTML 转义
        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // 格式化日期
        function formatDate(dateStr) {
            return formatUiDateTime(dateStr, { fallback: dateStr || '' });
        }

        // ==================== 设置相关 ====================

        // ==================== 一键更新配置（更新方式切换） ====================

        function toggleUpdateMethodConfig() {
            const watchtowerConfigArea = document.getElementById('watchtowerConfigArea');
            const dockerApiWarning = document.getElementById('dockerApiWarning');
            if (!watchtowerConfigArea || !dockerApiWarning) return;

            const selectedMethod = document.querySelector('input[name="updateMethod"]:checked')?.value;
            if (selectedMethod === 'docker_api') {
                watchtowerConfigArea.style.display = 'none';
                dockerApiWarning.style.display = 'block';
            } else {
                watchtowerConfigArea.style.display = 'block';
                dockerApiWarning.style.display = 'none';
            }
        }

        function initUpdateMethodConfigToggles() {
            try {
                const updateMethodRadios = document.getElementsByName('updateMethod');
                if (!updateMethodRadios || updateMethodRadios.length === 0) {
                    return;
                }

                updateMethodRadios.forEach((radio) => {
                    if (!radio) return;
                    // 防止重复绑定（某些情况下可能多次初始化）
                    if (radio.dataset && radio.dataset.boundUpdateMethodToggle === 'true') {
                        return;
                    }
                    radio.addEventListener('change', toggleUpdateMethodConfig);
                    if (radio.dataset) {
                        radio.dataset.boundUpdateMethodToggle = 'true';
                    }
                });

                // 初始化时调用一次，确保初始显隐正确
                toggleUpdateMethodConfig();
            } catch (e) {
                // 静默失败：不影响其它功能
            }
        }

        // 显示设置模态框
        async function showSettingsModal() {
            document.getElementById('settingsModal').classList.add('show');
            await loadSettings();
        }

        // 隐藏设置模态框
        function hideSettingsModal() {
            document.getElementById('settingsModal').classList.remove('show');
            // 清空密码输入框
            document.getElementById('settingsPassword').value = '';
        }

        function buildExternalApiKeysEditorItems(items) {
            if (!Array.isArray(items)) return [];

            return items.map((item, index) => {
                if (!item || typeof item !== 'object' || Array.isArray(item)) {
                    throw new Error(`第 ${index + 1} 项必须是对象`);
                }

                const normalized = {
                    name: item.name || '',
                    api_key: item.api_key || item.api_key_masked || '',
                    enabled: !(item.enabled === false || item.enabled === 'false' || item.enabled === 0 || item.enabled === '0'),
                    pool_access: item.pool_access === true || item.pool_access === 'true' || item.pool_access === 1 || item.pool_access === '1',
                    allowed_emails: Array.isArray(item.allowed_emails) ? item.allowed_emails : []
                };

                if (item.id !== undefined && item.id !== null && item.id !== '') {
                    normalized.id = item.id;
                }

                return normalized;
            });
        }

        function setExternalApiKeysEditor(items) {
            const editorEl = document.getElementById('settingsExternalApiKeysJson');
            if (!editorEl) return;

            const normalized = buildExternalApiKeysEditorItems(items);
            const prettyValue = normalized.length ? JSON.stringify(normalized, null, 2) : '';
            editorEl.value = prettyValue;
            editorEl.dataset.originalCanonical = JSON.stringify(normalized);

            const hintEl = document.getElementById('externalApiKeysJsonHint');
            if (!hintEl) return;

            if (normalized.length > 0) {
                hintEl.textContent = `当前已配置 ${normalized.length} 个多 Key。保留已有脱敏 api_key 表示不修改该 Key；清空后保存表示清空全部多 Key。`;
            } else {
                hintEl.textContent = '用于按调用方维护多个 Key、邮箱范围授权和启停状态。保留已有脱敏 api_key 表示不修改该 Key；清空后保存表示清空全部多 Key。';
            }
        }

        // 加载设置
        async function loadSettings() {
            try {
                const response = await fetch('/api/settings');
                const data = await response.json();

                if (data.success) {
                    // 密码不回显
                    document.getElementById('settingsPassword').value = '';

                    const verificationAiEnabledEl = document.getElementById('settingsVerificationAiEnabled');
                    if (verificationAiEnabledEl) {
                        verificationAiEnabledEl.checked = !!data.settings.verification_ai_enabled;
                    }

                    const verificationAiBaseUrlEl = document.getElementById('settingsVerificationAiBaseUrl');
                    if (verificationAiBaseUrlEl) {
                        verificationAiBaseUrlEl.value = data.settings.verification_ai_base_url || '';
                    }

                    const verificationAiModelEl = document.getElementById('settingsVerificationAiModel');
                    if (verificationAiModelEl) {
                        verificationAiModelEl.value = data.settings.verification_ai_model || '';
                    }

                    const verificationAiApiKeyEl = document.getElementById('settingsVerificationAiApiKey');
                    if (verificationAiApiKeyEl) {
                        const maskedValue = data.settings.verification_ai_api_key_masked || '';
                        verificationAiApiKeyEl.value = maskedValue;
                        verificationAiApiKeyEl.dataset.maskedValue = maskedValue;
                        verificationAiApiKeyEl.dataset.isSet = data.settings.verification_ai_api_key_set ? 'true' : 'false';
                    }

                    const verificationAiApiKeyHintEl = document.getElementById('verificationAiApiKeyHint');
                    if (verificationAiApiKeyHintEl) {
                        if (data.settings.verification_ai_api_key_set) {
                            verificationAiApiKeyHintEl.textContent = `已设置：${data.settings.verification_ai_api_key_masked || ''}`;
                        } else {
                            verificationAiApiKeyHintEl.textContent = '未设置';
                        }
                    }

                    const verificationAiTestResultEl = document.getElementById('verificationAiTestResult');
                    if (verificationAiTestResultEl) {
                        verificationAiTestResultEl.textContent = '建议先保存配置再测试。';
                        verificationAiTestResultEl.style.color = 'var(--text-secondary, #666)';
                    }

                    // v0.3: Provider 选择器改为单选按钮
                    const rawProvider = data.settings.temp_mail_provider || 'legacy_bridge';
                    const mappedProvider = (rawProvider === 'custom_domain_temp_mail' || rawProvider === 'legacy_bridge' || rawProvider === 'legacy_gptmail' || rawProvider === 'gptmail')
                        ? 'legacy_bridge'
                        : rawProvider;
                    const providerGroup = document.querySelector('.provider-radio-group');
                    if (providerGroup) {
                        providerGroup.dataset.pendingProvider = mappedProvider;
                    }
                    const radioBtn = document.querySelector(`input[name="tempMailProvider"][value="${mappedProvider}"]`);
                    if (radioBtn) {
                        radioBtn.checked = true;
                        if (providerGroup) {
                            providerGroup.dataset.pendingProvider = '';
                        }
                    }
                    if (typeof onTempMailProviderChange === 'function') {
                        onTempMailProviderChange(mappedProvider);
                    }

                    const tempMailApiBaseUrlEl = document.getElementById('settingsTempMailApiBaseUrl');
                    if (tempMailApiBaseUrlEl) {
                        tempMailApiBaseUrlEl.value = data.settings.temp_mail_api_base_url || '';
                    }

                    // 临时邮箱 API Key（v0.3: ID 从 settingsApiKey 改为 settingsTempMailApiKey）
                    const tempMailApiKeyEl = document.getElementById('settingsTempMailApiKey');
                    if (tempMailApiKeyEl) {
                        const maskedValue = data.settings.temp_mail_api_key_masked || '';
                        tempMailApiKeyEl.value = maskedValue;
                        tempMailApiKeyEl.dataset.maskedValue = maskedValue;
                        tempMailApiKeyEl.dataset.isSet = data.settings.temp_mail_api_key_set ? 'true' : 'false';
                    }

                    const tempMailDomainsEl = document.getElementById('settingsTempMailDomains');
                    if (tempMailDomainsEl) {
                        const domains = Array.isArray(data.settings.temp_mail_domains) ? data.settings.temp_mail_domains : [];
                        tempMailDomainsEl.value = domains.length ? JSON.stringify(domains, null, 2) : '';
                    }

                    const tempMailDefaultDomainEl = document.getElementById('settingsTempMailDefaultDomain');
                    if (tempMailDefaultDomainEl) {
                        tempMailDefaultDomainEl.value = data.settings.temp_mail_default_domain || '';
                    }

                    const tempMailPrefixRulesEl = document.getElementById('settingsTempMailPrefixRules');
                    if (tempMailPrefixRulesEl) {
                        const prefixRules = data.settings.temp_mail_prefix_rules || {};
                        tempMailPrefixRulesEl.value = Object.keys(prefixRules).length ? JSON.stringify(prefixRules, null, 2) : '';
                    }

                    // CF Worker 独立配置
                    const cfWorkerBaseUrlEl = document.getElementById('settingsCfWorkerBaseUrl');
                    if (cfWorkerBaseUrlEl) {
                        cfWorkerBaseUrlEl.value = data.settings.cf_worker_base_url || '';
                    }

                    const cfWorkerAdminKeyEl = document.getElementById('settingsCfWorkerAdminKey');
                    if (cfWorkerAdminKeyEl) {
                        const cfMasked = data.settings.cf_worker_admin_key_masked || '';
                        cfWorkerAdminKeyEl.value = cfMasked;
                        cfWorkerAdminKeyEl.dataset.maskedValue = cfMasked;
                        cfWorkerAdminKeyEl.dataset.isSet = data.settings.cf_worker_admin_key_set ? 'true' : 'false';
                    }

                    // v0.3: CF Worker 独立域名配置（只读字段）
                    const cfWorkerDomainsEl = document.getElementById('settingsCfWorkerDomains');
                    if (cfWorkerDomainsEl) {
                        const cfDomains = data.settings.cf_worker_domains || [];
                        cfWorkerDomainsEl.value = cfDomains.length ? JSON.stringify(cfDomains, null, 2) : '';
                        cfWorkerDomainsEl.classList.add('readonly-field');
                        cfWorkerDomainsEl.readOnly = true;
                        if (!cfDomains.length) {
                            cfWorkerDomainsEl.setAttribute('placeholder', '尚未同步，请点击上方按钮同步');
                        }
                    }

                    const cfWorkerDefaultDomainEl = document.getElementById('settingsCfWorkerDefaultDomain');
                    if (cfWorkerDefaultDomainEl) {
                        cfWorkerDefaultDomainEl.value = data.settings.cf_worker_default_domain || '';
                        cfWorkerDefaultDomainEl.classList.add('readonly-field');
                        cfWorkerDefaultDomainEl.readOnly = true;
                        if (!cfWorkerDefaultDomainEl.value) {
                            cfWorkerDefaultDomainEl.setAttribute('placeholder', '尚未同步');
                        }
                    }

                    const cfWorkerPrefixRulesEl = document.getElementById('settingsCfWorkerPrefixRules');
                    if (cfWorkerPrefixRulesEl) {
                        const cfPrefixRules = data.settings.cf_worker_prefix_rules || {};
                        cfWorkerPrefixRulesEl.value = Object.keys(cfPrefixRules).length ? JSON.stringify(cfPrefixRules, null, 2) : '';
                    }

                    const externalApiKeyEl = document.getElementById('settingsExternalApiKey');
                    if (externalApiKeyEl) {
                        const maskedValue = data.settings.external_api_key_masked || '';
                        externalApiKeyEl.value = maskedValue;
                        externalApiKeyEl.dataset.maskedValue = maskedValue;
                        externalApiKeyEl.dataset.isSet = data.settings.external_api_key_set ? 'true' : 'false';
                    }

                    const externalHintEl = document.getElementById('externalApiKeyHint');
                    if (externalHintEl) {
                        if (data.settings.external_api_key_set) {
                            externalHintEl.textContent = translateAppTextLocal(`已设置：${data.settings.external_api_key_masked || ''}`);
                        } else {
                            externalHintEl.textContent = '未设置（设置后可通过 /api/external/* 对外开放接口读取邮件与验证码）';
                        }
                    }

                    setExternalApiKeysEditor(data.settings.external_api_keys || []);

                    // P1：公网安全配置
                    const publicModeEl = document.getElementById('externalApiPublicMode');
                    if (publicModeEl) publicModeEl.checked = data.settings.external_api_public_mode === true;

                    const ipWhitelistEl = document.getElementById('externalApiIpWhitelist');
                    if (ipWhitelistEl) {
                        const wl = data.settings.external_api_ip_whitelist;
                        ipWhitelistEl.value = Array.isArray(wl) ? wl.join('\n') : '';
                    }

                    const rateLimitEl = document.getElementById('externalApiRateLimit');
                    if (rateLimitEl) rateLimitEl.value = data.settings.external_api_rate_limit_per_minute || 60;

                    const disableRawEl = document.getElementById('externalApiDisableRaw');
                    if (disableRawEl) disableRawEl.checked = data.settings.external_api_disable_raw_content === true;

                    const disableWaitEl = document.getElementById('externalApiDisableWait');
                    if (disableWaitEl) disableWaitEl.checked = data.settings.external_api_disable_wait_message === true;

                    const poolExternalEnabledEl = document.getElementById('poolExternalEnabled');
                    if (poolExternalEnabledEl) poolExternalEnabledEl.checked = data.settings.pool_external_enabled === true;

                    const disablePoolClaimRandomEl = document.getElementById('externalApiDisablePoolClaimRandom');
                    if (disablePoolClaimRandomEl) disablePoolClaimRandomEl.checked = data.settings.external_api_disable_pool_claim_random === true;

                    const disablePoolClaimReleaseEl = document.getElementById('externalApiDisablePoolClaimRelease');
                    if (disablePoolClaimReleaseEl) disablePoolClaimReleaseEl.checked = data.settings.external_api_disable_pool_claim_release === true;

                    const disablePoolClaimCompleteEl = document.getElementById('externalApiDisablePoolClaimComplete');
                    if (disablePoolClaimCompleteEl) disablePoolClaimCompleteEl.checked = data.settings.external_api_disable_pool_claim_complete === true;

                    const disablePoolStatsEl = document.getElementById('externalApiDisablePoolStats');
                    if (disablePoolStatsEl) disablePoolStatsEl.checked = data.settings.external_api_disable_pool_stats === true;

                    // 加载刷新配置
                    document.getElementById('refreshIntervalDays').value = data.settings.refresh_interval_days || '30';
                    document.getElementById('refreshDelaySeconds').value = data.settings.refresh_delay_seconds || '5';
                    document.getElementById('refreshCron').value = data.settings.refresh_cron || '0 2 * * *';

                    // 设置定时刷新开关
                    const enableScheduled = data.settings.enable_scheduled_refresh !== 'false';
                    document.getElementById('enableScheduledRefresh').checked = enableScheduled;

                    // 设置刷新策略单选框
                    const useCron = data.settings.use_cron_schedule === 'true';
                    document.querySelector('input[name="refreshStrategy"][value="' + (useCron ? 'cron' : 'days') + '"]').checked = true;
                    toggleRefreshStrategy();

                    // 加载轮询设置（后端返回 boolean，兼容处理）
                    // [Phase 3 兼容] 任一开关开启，设置面板复选框就显示为勾选状态
                    const enablePolling = isAutoPollingEnabledSetting(data.settings.enable_auto_polling)
                        || isAutoPollingEnabledSetting(data.settings.enable_compact_auto_poll);
                    document.getElementById('enableAutoPolling').checked = enablePolling;
                    document.getElementById('pollingInterval').value = String(parseIntegerSetting(data.settings.polling_interval, 10));
                    document.getElementById('pollingCount').value = String(parseIntegerSetting(data.settings.polling_count, 5));

                    // [Phase 3] 简洁模式独立面板已合并，使用统一引擎配置
                    applyPollingSettings(data.settings);

                    // 加载 Telegram 推送设置
                    const tgToken = document.getElementById('telegramBotToken');
                    const tgChat = document.getElementById('telegramChatId');
                    const tgPoll = document.getElementById('telegramPollInterval');
                    const tgProxy = document.getElementById('telegramProxyUrl');
                    const emailEnabled = document.getElementById('emailNotificationEnabled');
                    const emailRecipient = document.getElementById('emailNotificationRecipient');
                    const webhookEnabledEl = document.getElementById('webhookNotificationEnabled');
                    const webhookUrlEl = document.getElementById('webhookNotificationUrl');
                    const webhookTokenEl = document.getElementById('webhookNotificationToken');
                    if (tgToken) tgToken.value = data.telegram_bot_token || '';
                    if (tgChat) tgChat.value = data.telegram_chat_id || '';
                    if (tgPoll) tgPoll.value = String(parseIntegerSetting(data.telegram_poll_interval, 600));
                    if (tgProxy) tgProxy.value = (data.settings && data.settings.telegram_proxy_url) || '';
                    if (emailEnabled) emailEnabled.checked = !!data.settings.email_notification_enabled;
                    if (emailRecipient) emailRecipient.value = data.settings.email_notification_recipient || '';
                    if (webhookEnabledEl) webhookEnabledEl.checked = data.settings.webhook_notification_enabled === true;
                    if (webhookUrlEl) webhookUrlEl.value = (data.settings && data.settings.webhook_notification_url) || '';
                    if (webhookTokenEl) {
                        const webhookMasked = (data.settings && data.settings.webhook_notification_token) || '';
                        webhookTokenEl.value = webhookMasked;
                        webhookTokenEl.dataset.maskedValue = webhookMasked;
                        webhookTokenEl.dataset.isSet = webhookMasked ? 'true' : 'false';
                    }

                    // 加载 Watchtower 一键更新设置
                    const wtUrl = document.getElementById('watchtowerUrl');
                    const wtToken = document.getElementById('watchtowerToken');
                    if (wtUrl) wtUrl.value = (data.settings && data.settings.watchtower_url) || '';
                    if (wtToken) wtToken.value = (data.settings && data.settings.watchtower_token) || '';
                    
                    // 加载更新方式设置
                    const updateMethod = (data.settings && data.settings.update_method) || 'watchtower';
                    const updateMethodRadios = document.getElementsByName('updateMethod');
                    updateMethodRadios.forEach(radio => {
                        radio.checked = (radio.value === updateMethod);
                    });

                    // 触发更新方式切换逻辑（index.html 内联脚本绑定了 change 事件）
                    // 注意：直接设置 radio.checked 不会触发 change，需手动派发事件以更新显隐。
                    try {
                        const selectedUpdateMethodRadio = document.querySelector('input[name="updateMethod"]:checked');
                        if (selectedUpdateMethodRadio) {
                            selectedUpdateMethodRadio.dispatchEvent(new Event('change'));
                        }
                    } catch (e) {
                        // 静默失败
                    }

                    // 加载部署信息警告（用于一键更新的部署提示）
                    loadDeploymentInfo({ silent: true });
                }
            } catch (error) {
                console.error('loadSettings error:', error);
                showToast(translateAppTextLocal('加载设置失败'), 'error');
            }
        }

        // ==================== 部署信息检测（用于一键更新提示） ====================

        // 缓存最近一次部署信息，用于语言切换时重渲染
        let lastDeploymentInfo = null;

        function pickDeploymentWarningText(warning, keyZh, keyEn) {
            if (!warning || typeof warning !== 'object') return '';
            const zh = String(warning[keyZh] || '').trim();
            const en = String(warning[keyEn] || '').trim();
            return getUiLanguage() === 'en' ? (en || zh) : (zh || en);
        }

        function normalizeDeploymentWarningSeverity(severityRaw) {
            const normalized = String(severityRaw || 'info').trim().toLowerCase();
            if (normalized === 'error' || normalized === 'warning' || normalized === 'info') return normalized;
            // 兼容后端可能返回的其它值
            return 'info';
        }

        function buildDeploymentWarningStyle(severity) {
            // 统一用 CSS 变量，兼容浅色/深色主题
            if (severity === 'error') {
                return {
                    color: 'var(--clr-danger)',
                    background: 'rgba(192,57,43,0.08)',
                    icon: '⛔'
                };
            }
            if (severity === 'warning') {
                return {
                    color: 'var(--clr-warn)',
                    background: 'rgba(230,126,34,0.08)',
                    icon: '⚠️'
                };
            }
            return {
                color: 'var(--clr-accent)',
                background: 'rgba(200,150,62,0.08)',
                icon: 'ℹ️'
            };
        }

        function renderDeploymentWarnings(deployment) {
            const container = document.getElementById('deploymentWarnings');
            if (!container) return;

            const warnings = Array.isArray(deployment && deployment.warnings) ? deployment.warnings : [];
            if (warnings.length === 0) {
                container.innerHTML = '';
                return;
            }

            const html = warnings.map((warning) => {
                const severity = normalizeDeploymentWarningSeverity(warning && warning.severity);
                const style = buildDeploymentWarningStyle(severity);

                const title = pickDeploymentWarningText(warning, 'message', 'message_en');
                const suggestion = pickDeploymentWarningText(warning, 'suggestion', 'suggestion_en');

                const suggestionHtml = suggestion
                    ? `<div style="margin-top:6px;font-size:0.78rem;color:var(--text-muted);">
                            <strong>${escapeHtml(translateAppTextLocal('处理建议'))}：</strong>${escapeHtml(suggestion)}
                       </div>`
                    : '';

                return `
                    <div class="form-hint" style="background:${style.background}; padding: 12px; border-radius: 6px; border-left: 3px solid ${style.color}; margin-bottom: 10px;">
                        <div style="display:flex; gap: 10px; align-items:flex-start;">
                            <div style="font-size: 1rem; line-height: 1.2;">${style.icon}</div>
                            <div style="flex: 1;">
                                <div style="font-weight: 600; color: var(--text);">${escapeHtml(title)}</div>
                                ${suggestionHtml}
                            </div>
                        </div>
                    </div>
                `;
            }).join('');

            container.innerHTML = html;
        }

        async function loadDeploymentInfo({ silent = true } = {}) {
            const container = document.getElementById('deploymentWarnings');
            if (!container) return;

            try {
                const res = await fetch('/api/system/deployment-info', { cache: 'no-store' });
                if (!res.ok) return;
                const data = await res.json();
                if (!data || !data.success || !data.deployment) {
                    if (!silent) {
                        handleApiError(data || { success: false, error: '请求失败' }, '请求失败');
                    }
                    return;
                }

                lastDeploymentInfo = data.deployment;
                renderDeploymentWarnings(lastDeploymentInfo);

                // 根据后端推荐的更新方式自动选择 radio
                const recommended = data.deployment.recommended_method;
                if (recommended) {
                    const radios = document.getElementsByName('updateMethod');
                    radios.forEach(radio => {
                        if (radio.value === recommended) {
                            radio.checked = true;
                            radio.dispatchEvent(new Event('change'));
                        }
                    });
                }
            } catch (e) {
                if (!silent) {
                    showToast(`${translateAppTextLocal('请求失败')}: ${e.message}`, 'error');
                }
            }
        }

        // 切换刷新策略
        function toggleRefreshStrategy() {
            const strategy = document.querySelector('input[name="refreshStrategy"]:checked').value;
            document.getElementById('daysStrategyContainer').style.display = strategy === 'days' ? 'block' : 'none';
            document.getElementById('cronStrategyContainer').style.display = strategy === 'cron' ? 'block' : 'none';
        }

        // 选择 Cron 样例
        async function selectCronExample(cronExpr) {
            document.getElementById('refreshCron').value = cronExpr;
            await validateCronExpression();
        }

        // 验证 Cron 表达式
        async function validateCronExpression() {
            const cronExpr = document.getElementById('refreshCron').value.trim();
            const resultEl = document.getElementById('cronValidationResult');

            if (!cronExpr) {
                resultEl.innerHTML = '';
                return;
            }

            try {
                const response = await fetch('/api/settings/validate-cron', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cron_expression: cronExpr })
                });

                const data = await response.json();

                if (data.success && data.valid) {
                    const nextRun = formatUiDateTime(data.next_run, { fallback: data.next_run, includeSeconds: false });
                    resultEl.innerHTML = `
                        <div style="color: #28a745;">
                            ✓ ${translateAppTextLocal('表达式有效')}<br>
                            ${translateAppTextLocal('下次执行:')} ${nextRun}
                        </div>
                    `;
                } else {
                    resultEl.innerHTML = `
                        <div style="color: #dc3545;">
                            ✗ ${window.resolveApiErrorMessage ? window.resolveApiErrorMessage(data.error || data, '表达式无效', 'Invalid expression') : (data.error && data.error.message ? data.error.message : (data.error || '表达式无效'))}
                        </div>
                    `;
                }
            } catch (error) {
                resultEl.innerHTML = `
                    <div style="color: #dc3545;">
                        ✗ ${translateAppTextLocal('验证失败:')} ${error.message}
                    </div>
                `;
            }
        }

        // 保存设置
        async function saveSettings() {
            const password = document.getElementById('settingsPassword').value;

            const verificationAiEnabledEl = document.getElementById('settingsVerificationAiEnabled');
            const verificationAiBaseUrlEl = document.getElementById('settingsVerificationAiBaseUrl');
            const verificationAiApiKeyEl = document.getElementById('settingsVerificationAiApiKey');
            const verificationAiModelEl = document.getElementById('settingsVerificationAiModel');

            const verificationAiEnabled = verificationAiEnabledEl ? verificationAiEnabledEl.checked : false;
            const verificationAiBaseUrl = verificationAiBaseUrlEl ? verificationAiBaseUrlEl.value.trim() : '';
            const verificationAiModel = verificationAiModelEl ? verificationAiModelEl.value.trim() : '';
            const verificationAiApiKey = verificationAiApiKeyEl ? verificationAiApiKeyEl.value.trim() : '';
            const verificationAiApiKeyMasked = verificationAiApiKeyEl ? (verificationAiApiKeyEl.dataset.maskedValue || '') : '';
            const verificationAiApiKeyIsSet = verificationAiApiKeyEl ? verificationAiApiKeyEl.dataset.isSet === 'true' : false;

            // v0.3: Provider 改为 radio button
            const tempMailProviderRadio = document.querySelector('input[name="tempMailProvider"]:checked');
            const tempMailApiBaseUrlEl = document.getElementById('settingsTempMailApiBaseUrl');
            const tempMailApiKeyEl = document.getElementById('settingsTempMailApiKey');
            const tempMailDomainsEl = document.getElementById('settingsTempMailDomains');
            const tempMailDefaultDomainEl = document.getElementById('settingsTempMailDefaultDomain');
            const tempMailPrefixRulesEl = document.getElementById('settingsTempMailPrefixRules');

            const tempMailApiKey = tempMailApiKeyEl ? tempMailApiKeyEl.value.trim() : '';
            const tempMailApiKeyMasked = tempMailApiKeyEl ? (tempMailApiKeyEl.dataset.maskedValue || '') : '';
            const tempMailApiKeyIsSet = tempMailApiKeyEl ? tempMailApiKeyEl.dataset.isSet === 'true' : false;

            const externalApiKeyEl = document.getElementById('settingsExternalApiKey');
            const externalApiKey = externalApiKeyEl ? externalApiKeyEl.value.trim() : '';
            const externalApiKeyMasked = externalApiKeyEl ? (externalApiKeyEl.dataset.maskedValue || '') : '';
            const externalApiKeyIsSet = externalApiKeyEl ? externalApiKeyEl.dataset.isSet === 'true' : false;
            const externalApiKeysJsonEl = document.getElementById('settingsExternalApiKeysJson');
            const externalApiKeysRaw = externalApiKeysJsonEl ? externalApiKeysJsonEl.value.trim() : '';
            const originalExternalApiKeysCanonical = externalApiKeysJsonEl
                ? (externalApiKeysJsonEl.dataset.originalCanonical || '[]')
                : '[]';

            const refreshDays = document.getElementById('refreshIntervalDays').value;
            const refreshDelay = document.getElementById('refreshDelaySeconds').value;
            const refreshCron = document.getElementById('refreshCron').value.trim();
            const strategy = document.querySelector('input[name="refreshStrategy"]:checked').value;
            const enableScheduled = document.getElementById('enableScheduledRefresh').checked;

            // 轮询设置
            const enablePolling = document.getElementById('enableAutoPolling').checked;
            const pollingInterval = document.getElementById('pollingInterval').value;
            const pollingCount = document.getElementById('pollingCount').value;
            const emailNotificationEnabled = document.getElementById('emailNotificationEnabled').checked;
            const emailNotificationRecipient = document.getElementById('emailNotificationRecipient').value.trim();

            const settings = {};

            // 只有输入了密码才更新密码
            if (password) {
                settings.login_password = password;
            }

            settings.verification_ai_enabled = verificationAiEnabled;
            settings.verification_ai_base_url = verificationAiBaseUrl;
            settings.verification_ai_model = verificationAiModel;

            if (!(verificationAiApiKeyIsSet && verificationAiApiKey && verificationAiApiKey === verificationAiApiKeyMasked)) {
                settings.verification_ai_api_key = verificationAiApiKey;
            }

            if (verificationAiEnabled) {
                if (!verificationAiBaseUrl) {
                    showToast('请填写 AI Base URL', 'error');
                    return;
                }
                if (!verificationAiModel) {
                    showToast('请填写 AI 模型 ID', 'error');
                    return;
                }
                const hasApiKey = !!verificationAiApiKey || (verificationAiApiKeyIsSet && verificationAiApiKey === verificationAiApiKeyMasked);
                if (!hasApiKey) {
                    showToast('请填写 AI API Key', 'error');
                    return;
                }
            }

            settings.temp_mail_provider = tempMailProviderRadio ? (tempMailProviderRadio.value.trim() || 'legacy_bridge') : 'legacy_bridge';
            settings.temp_mail_api_base_url = tempMailApiBaseUrlEl ? tempMailApiBaseUrlEl.value.trim() : '';
            settings.temp_mail_default_domain = tempMailDefaultDomainEl ? tempMailDefaultDomainEl.value.trim() : '';

            if (tempMailDomainsEl) {
                const rawDomains = tempMailDomainsEl.value.trim();
                if (rawDomains) {
                    try {
                        settings.temp_mail_domains = JSON.parse(rawDomains);
                    } catch (error) {
                        showToast(translateAppTextLocal('临时邮箱域名配置必须是合法 JSON'), 'error');
                        return;
                    }
                } else {
                    settings.temp_mail_domains = [];
                }
            }

            if (tempMailPrefixRulesEl) {
                const rawPrefixRules = tempMailPrefixRulesEl.value.trim();
                if (rawPrefixRules) {
                    try {
                        settings.temp_mail_prefix_rules = JSON.parse(rawPrefixRules);
                    } catch (error) {
                        showToast(translateAppTextLocal('临时邮箱前缀规则必须是合法 JSON'), 'error');
                        return;
                    }
                } else {
                    settings.temp_mail_prefix_rules = {
                        min_length: 1,
                        max_length: 32,
                        pattern: '^[a-z0-9][a-z0-9._-]*$'
                    };
                }
            }

            // 临时邮箱 API Key：仅当用户真实输入时才覆盖（避免把脱敏占位符写回 DB）
            if (!(tempMailApiKeyIsSet && tempMailApiKey && tempMailApiKey === tempMailApiKeyMasked)) {
                settings.temp_mail_api_key = tempMailApiKey;
            }

            // CF Worker 独立配置
            const cfWorkerBaseUrlEl = document.getElementById('settingsCfWorkerBaseUrl');
            const cfWorkerAdminKeyEl = document.getElementById('settingsCfWorkerAdminKey');
            if (cfWorkerBaseUrlEl) {
                settings.cf_worker_base_url = cfWorkerBaseUrlEl.value.trim();
            }
            if (cfWorkerAdminKeyEl) {
                const cfKey = cfWorkerAdminKeyEl.value.trim();
                const cfKeyMasked = cfWorkerAdminKeyEl.dataset.maskedValue || '';
                const cfKeyIsSet = cfWorkerAdminKeyEl.dataset.isSet === 'true';
                // 仅当用户真实输入时才覆盖（避免把脱敏占位符写回 DB）
                if (!(cfKeyIsSet && cfKey && cfKey === cfKeyMasked)) {
                    settings.cf_worker_admin_key = cfKey;
                }
            }

            // v0.3: CF Worker 独立前缀规则（域名字段只读，不保存）
            const cfWorkerPrefixRulesEl = document.getElementById('settingsCfWorkerPrefixRules');
            if (cfWorkerPrefixRulesEl) {
                const rawCfPrefixRules = cfWorkerPrefixRulesEl.value.trim();
                if (rawCfPrefixRules) {
                    try {
                        settings.cf_worker_prefix_rules = JSON.parse(rawCfPrefixRules);
                    } catch (error) {
                        showToast(translateAppTextLocal('CF Worker 前缀规则必须是合法 JSON'), 'error');
                        return;
                    }
                } else {
                    settings.cf_worker_prefix_rules = {
                        min_length: 1,
                        max_length: 32,
                        pattern: '^[a-z0-9][a-z0-9._-]*$'
                    };
                }
            }

            // 对外开放 API Key：允许清空（空字符串）
            if (!(externalApiKeyIsSet && externalApiKey && externalApiKey === externalApiKeyMasked)) {
                settings.external_api_key = externalApiKey;
            }

            if (externalApiKeysJsonEl) {
                if (externalApiKeysRaw) {
                    let parsedExternalApiKeys;
                    try {
                        parsedExternalApiKeys = JSON.parse(externalApiKeysRaw);
                    } catch (error) {
                        showToast(translateAppTextLocal('多 Key 配置必须是合法 JSON'), 'error');
                        return;
                    }

                    if (!Array.isArray(parsedExternalApiKeys)) {
                        showToast(translateAppTextLocal('多 Key 配置必须是 JSON 数组'), 'error');
                        return;
                    }

                    let normalizedExternalApiKeys;
                    try {
                        normalizedExternalApiKeys = buildExternalApiKeysEditorItems(parsedExternalApiKeys);
                    } catch (error) {
                        showToast(error.message || '多 Key 配置格式无效', 'error');
                        return;
                    }

                    const nextCanonical = JSON.stringify(normalizedExternalApiKeys);
                    if (nextCanonical !== originalExternalApiKeysCanonical) {
                        settings.external_api_keys = normalizedExternalApiKeys;
                    }
                } else if (originalExternalApiKeysCanonical !== '[]') {
                    settings.external_api_keys = [];
                }
            }

            // P1：公网安全配置
            const publicModeEl = document.getElementById('externalApiPublicMode');
            if (publicModeEl) settings.external_api_public_mode = publicModeEl.checked;

            const ipWhitelistEl = document.getElementById('externalApiIpWhitelist');
            if (ipWhitelistEl) {
                const lines = ipWhitelistEl.value.trim().split('\n').map(l => l.trim()).filter(l => l);
                settings.external_api_ip_whitelist = lines;
            }

            const rateLimitEl = document.getElementById('externalApiRateLimit');
            if (rateLimitEl) {
                const rl = parseInt(rateLimitEl.value);
                if (!isNaN(rl)) settings.external_api_rate_limit_per_minute = rl;
            }

            const disableRawEl = document.getElementById('externalApiDisableRaw');
            if (disableRawEl) settings.external_api_disable_raw_content = disableRawEl.checked;

            const disableWaitEl = document.getElementById('externalApiDisableWait');
            if (disableWaitEl) settings.external_api_disable_wait_message = disableWaitEl.checked;

            const poolExternalEnabledEl = document.getElementById('poolExternalEnabled');
            if (poolExternalEnabledEl) settings.pool_external_enabled = poolExternalEnabledEl.checked;

            const disablePoolClaimRandomEl = document.getElementById('externalApiDisablePoolClaimRandom');
            if (disablePoolClaimRandomEl) settings.external_api_disable_pool_claim_random = disablePoolClaimRandomEl.checked;

            const disablePoolClaimReleaseEl = document.getElementById('externalApiDisablePoolClaimRelease');
            if (disablePoolClaimReleaseEl) settings.external_api_disable_pool_claim_release = disablePoolClaimReleaseEl.checked;

            const disablePoolClaimCompleteEl = document.getElementById('externalApiDisablePoolClaimComplete');
            if (disablePoolClaimCompleteEl) settings.external_api_disable_pool_claim_complete = disablePoolClaimCompleteEl.checked;

            const disablePoolStatsEl = document.getElementById('externalApiDisablePoolStats');
            if (disablePoolStatsEl) settings.external_api_disable_pool_stats = disablePoolStatsEl.checked;

            // 刷新配置
            const days = parseInt(refreshDays);
            const delay = parseInt(refreshDelay);

            if (isNaN(days) || days < 1 || days > 90) {
                showToast(translateAppTextLocal('刷新周期必须在 1-90 天之间'), 'error');
                return;
            }

            if (isNaN(delay) || delay < 0 || delay > 60) {
                showToast(translateAppTextLocal('刷新间隔必须在 0-60 秒之间'), 'error');
                return;
            }

            settings.refresh_interval_days = days;
            settings.refresh_delay_seconds = delay;
            settings.use_cron_schedule = strategy === 'cron';
            settings.enable_scheduled_refresh = enableScheduled;

            if (strategy === 'cron') {
                if (!refreshCron) {
                    showToast(translateAppTextLocal('请输入 Cron 表达式'), 'error');
                    return;
                }
                settings.refresh_cron = refreshCron;
            }

            // 轮询配置验证
            const pInterval = parseInt(pollingInterval);
            const pCount = parseInt(pollingCount);

            if (isNaN(pInterval) || pInterval < 3 || pInterval > 300) {
                showToast(translateAppTextLocal('轮询间隔必须在 3-300 秒之间'), 'error');
                return;
            }

            // 0 表示持续轮询，1-100 表示有限次数
            if (isNaN(pCount) || pCount < 0 || pCount > 100) {
                showToast(translateAppTextLocal('轮询次数必须在 0-100 次之间（0 表示持续轮询）'), 'error');
                return;
            }

            settings.enable_auto_polling = enablePolling;
            settings.polling_interval = pInterval;
            settings.polling_count = pCount;
            settings.email_notification_enabled = emailNotificationEnabled;
            settings.email_notification_recipient = emailNotificationRecipient;

            // [Phase 3] 简洁模式独立配置已合并，统一通过标准字段传递
            // 向后端同步 compact 字段（deprecated 兼容），镜像标准字段值
            settings.enable_compact_auto_poll   = enablePolling;
            settings.compact_poll_interval      = pInterval;
            settings.compact_poll_max_count     = pCount;

            // Telegram 推送配置
            const tgBotTokenEl = document.getElementById('telegramBotToken');
            const tgChatIdEl = document.getElementById('telegramChatId');
            const tgPollIntervalEl = document.getElementById('telegramPollInterval');
            const tgProxyUrlEl = document.getElementById('telegramProxyUrl');
            const tgBotToken = tgBotTokenEl ? tgBotTokenEl.value.trim() : '';
            const tgChatId = tgChatIdEl ? tgChatIdEl.value.trim() : '';
            const tgPollInterval = tgPollIntervalEl ? parseInt(tgPollIntervalEl.value) : NaN;
            const tgProxyUrl = tgProxyUrlEl ? tgProxyUrlEl.value.trim() : '';

            if (tgBotToken) {
                settings.telegram_bot_token = tgBotToken;
            }
            if (tgChatId !== undefined) {
                settings.telegram_chat_id = tgChatId;
            }
            if (!isNaN(tgPollInterval)) {
                if (tgPollInterval < 10 || tgPollInterval > 86400) {
                    showToast(translateAppTextLocal('Telegram 轮询间隔必须在 10-86400 秒之间'), 'error');
                    return;
                }
                settings.telegram_poll_interval = tgPollInterval;
            }
            settings.telegram_proxy_url = tgProxyUrl;

            // Webhook 通知配置
            const webhookEnabledEl = document.getElementById('webhookNotificationEnabled');
            const webhookUrlEl = document.getElementById('webhookNotificationUrl');
            const webhookTokenEl = document.getElementById('webhookNotificationToken');
            const webhookEnabled = webhookEnabledEl ? webhookEnabledEl.checked : false;
            const webhookUrl = webhookUrlEl ? webhookUrlEl.value.trim() : '';
            const webhookToken = webhookTokenEl ? webhookTokenEl.value.trim() : '';
            const webhookTokenMasked = webhookTokenEl ? (webhookTokenEl.dataset.maskedValue || '') : '';
            const webhookTokenIsSet = webhookTokenEl ? webhookTokenEl.dataset.isSet === 'true' : false;

            if (webhookEnabled && !webhookUrl) {
                showToast(translateAppTextLocal('启用 Webhook 通知时必须填写 Webhook URL'), 'error');
                return;
            }
            if (webhookUrl && !(webhookUrl.startsWith('http://') || webhookUrl.startsWith('https://'))) {
                showToast(translateAppTextLocal('Webhook URL 必须以 http:// 或 https:// 开头'), 'error');
                return;
            }
            settings.webhook_notification_enabled = webhookEnabled;
            settings.webhook_notification_url = webhookUrl;
            if (!(webhookTokenIsSet && webhookToken && webhookToken === webhookTokenMasked)) {
                settings.webhook_notification_token = webhookToken;
            }

            // Watchtower 一键更新配置
            const wtUrlEl = document.getElementById('watchtowerUrl');
            const wtTokenEl = document.getElementById('watchtowerToken');
            const wtUrl = wtUrlEl ? wtUrlEl.value.trim() : '';
            const wtToken = wtTokenEl ? wtTokenEl.value.trim() : '';
            settings.watchtower_url = wtUrl;
            if (wtToken) {
                settings.watchtower_token = wtToken;
            }
            
            // 更新方式配置
            const updateMethodRadio = document.querySelector('input[name="updateMethod"]:checked');
            if (updateMethodRadio) {
                settings.update_method = updateMethodRadio.value;
            }

            try {
                const response = await fetch('/api/settings', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(settings)
                });

                const data = await response.json();

                if (data.success) {
                    applyPollingSettings(settings, { restart: true });
                    // [Phase 3] applyPollingSettings 已内含引擎同步，无需额外调用
                    showToast(pickApiMessage(data, '设置已保存，重启应用后生效', 'Settings saved successfully'), 'success');
                    hideSettingsModal();
                } else {
                    handleApiError(data, '保存设置失败');
                }
            } catch (error) {
                showToast(translateAppTextLocal('保存设置失败'), 'error');
            }
        }

        async function testTelegramPush() {
            const btn = document.getElementById('btnTestTelegram');
            if (btn) { btn.disabled = true; btn.textContent = translateAppTextLocal('⏳ 发送中…'); }
            try {
                const resp = await fetch('/api/settings/telegram-test', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
                const data = await resp.json();
                if (data.success) {
                    showToast(pickApiMessage(data, '测试消息已发送，请检查 Telegram', 'Test message sent successfully. Please check Telegram'), 'success');
                } else {
                    handleApiError(data, '发送失败');
                }
            } catch (e) {
                showToast(`${translateAppTextLocal('请求失败')}: ${e.message}`, 'error');
            } finally {
                if (btn) { btn.disabled = false; btn.textContent = translateAppTextLocal('📨 发送测试消息'); }
            }
        }

        async function testTelegramProxy() {
            const btn = document.getElementById('btnTestTelegramProxy');
            const resultEl = document.getElementById('telegramProxyTestResult');
            const proxyInput = document.getElementById('telegramProxyUrl');
            const proxyUrl = proxyInput ? proxyInput.value.trim() : '';
            if (btn) { btn.disabled = true; btn.textContent = translateAppTextLocal('⏳ 测试中…'); }
            if (resultEl) resultEl.textContent = '';
            try {
                const resp = await fetch('/api/settings/test-telegram-proxy', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ proxy_url: proxyUrl })
                });
                const data = await resp.json();
                if (data.ok) {
                    if (resultEl) { resultEl.textContent = '✅ 连通'; resultEl.style.color = 'var(--success, green)'; }
                } else {
                    if (resultEl) { resultEl.textContent = `❌ ${data.message || '失败'}`; resultEl.style.color = 'var(--danger, red)'; }
                }
            } catch (e) {
                if (resultEl) { resultEl.textContent = `❌ ${e.message}`; resultEl.style.color = 'var(--danger, red)'; }
            } finally {
                if (btn) { btn.disabled = false; btn.textContent = translateAppTextLocal('🔗 测试连通性'); }
            }
        }

        async function testWatchtower() {
            const btn = document.getElementById('btnTestWatchtower');
            const resultEl = document.getElementById('watchtowerTestResult');
            const urlInput = document.getElementById('watchtowerUrl');
            const tokenInput = document.getElementById('watchtowerToken');
            const wtUrl = urlInput ? urlInput.value.trim() : '';
            const wtToken = tokenInput ? tokenInput.value.trim() : '';
            if (btn) { btn.disabled = true; btn.textContent = translateAppTextLocal('⏳ 测试中…'); }
            if (resultEl) resultEl.textContent = '';
            try {
                const body = {};
                if (wtUrl) body.url = wtUrl;
                if (wtToken && !wtToken.startsWith('****')) body.token = wtToken;
                const resp = await fetch('/api/system/test-watchtower', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCSRFToken()
                    },
                    body: JSON.stringify(body)
                });
                const data = await resp.json();
                if (data.success) {
                    if (resultEl) { resultEl.textContent = translateAppTextLocal('✅ 连通正常'); resultEl.style.color = 'var(--success, green)'; }
                } else {
                    if (resultEl) { resultEl.textContent = `❌ ${data.message || translateAppTextLocal('失败')}`; resultEl.style.color = 'var(--danger, red)'; }
                }
            } catch (e) {
                if (resultEl) { resultEl.textContent = `❌ ${e.message}`; resultEl.style.color = 'var(--danger, red)'; }
            } finally {
                if (btn) { btn.disabled = false; btn.textContent = translateAppTextLocal('🔗 测试连通性'); }
            }
        }

        async function testEmailNotification() {
            const btn = document.getElementById('btnTestEmailNotification');
            if (btn) { btn.disabled = true; btn.textContent = translateAppTextLocal('⏳ 发送中…'); }
            try {
                const resp = await fetch('/api/settings/email-test', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
                const data = await resp.json();
                if (data.success) {
                    showToast(pickApiMessage(data, '测试邮件已提交，请检查收件箱', 'Test email accepted. Please check your inbox'), 'success');
                } else {
                    handleApiError(data, '测试邮件发送失败');
                }
            } catch (e) {
                showToast(`${translateAppTextLocal('请求失败')}: ${e.message}`, 'error');
            } finally {
                if (btn) { btn.disabled = false; btn.textContent = translateAppTextLocal('📨 发送测试邮件'); }
            }
        }

        async function testWebhookNotification() {
            const btn = document.getElementById('btnTestWebhookNotification');
            if (btn) { btn.disabled = true; btn.textContent = translateAppTextLocal('⏳ 发送中…'); }
            try {
                const resp = await fetch('/api/settings/webhook-test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                const data = await resp.json();
                if (data.success) {
                    showToast(pickApiMessage(data, 'Webhook 测试成功', 'Webhook test succeeded'), 'success');
                } else {
                    handleApiError(data, 'Webhook 测试失败');
                }
            } catch (e) {
                showToast(`${translateAppTextLocal('请求失败')}: ${e.message}`, 'error');
            } finally {
                if (btn) { btn.disabled = false; btn.textContent = translateAppTextLocal('测试 Webhook'); }
            }
        }

        function generateExternalApiKey() {
            const input = document.getElementById('settingsExternalApiKey');
            if (!input) return;

            const currentValue = input.value.trim();
            if (currentValue) {
                const confirmed = confirm(translateAppTextLocal('当前已存在 API Key，是否覆盖？'));
                if (!confirmed) return;
            }

            const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
            const bytes = new Uint8Array(64);
            window.crypto.getRandomValues(bytes);
            const key = Array.from(bytes, b => alphabet[b % alphabet.length]).join('');

            input.value = key;
            showToast(translateAppTextLocal('已生成新的 API Key（尚未保存）'), 'success');
        }

        async function copyExternalApiKey() {
            const input = document.getElementById('settingsExternalApiKey');
            if (!input) return;

            const value = input.value || '';
            const maskedValue = input.dataset.maskedValue || '';
            const isSet = input.dataset.isSet === 'true';
            let copyValue = value.trim();

            if (isSet && copyValue && maskedValue && copyValue === maskedValue) {
                try {
                    const resp = await fetch('/api/settings/external-api-key/plaintext');
                    const data = await resp.json();
                    if (!resp.ok || !data.success || !data.api_key) {
                        throw new Error((data && (data.message || data.error?.message)) || '获取真实 API Key 失败');
                    }
                    copyValue = String(data.api_key || '').trim();
                } catch (error) {
                    showToast(`${translateAppTextLocal('请求失败')}: ${error.message}`, 'error');
                    return;
                }
            }

            if (!copyValue) {
                showToast(translateAppTextLocal('当前没有可复制的 API Key'), 'warning');
                return;
            }

            try {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    await navigator.clipboard.writeText(copyValue);
                } else {
                    const tempInput = document.createElement('textarea');
                    tempInput.value = copyValue;
                    tempInput.setAttribute('readonly', 'readonly');
                    tempInput.style.position = 'fixed';
                    tempInput.style.opacity = '0';
                    tempInput.style.pointerEvents = 'none';
                    document.body.appendChild(tempInput);
                    tempInput.focus();
                    tempInput.select();
                    const ok = document.execCommand('copy');
                    document.body.removeChild(tempInput);
                    if (!ok) {
                        throw new Error('execCommand_copy_failed');
                    }
                }
                showToast(translateAppTextLocal('内容已复制到剪贴板'), 'success');
            } catch (error) {
                showToast(translateAppTextLocal('复制失败，请手动复制'), 'error');
            }
        }

        async function testVerificationAiConfig() {
            const btn = document.getElementById('btnTestVerificationAi');
            const resultEl = document.getElementById('verificationAiTestResult');
            if (btn) { btn.disabled = true; btn.textContent = translateAppTextLocal('⏳ 测试中…'); }
            if (resultEl) {
                resultEl.textContent = '正在验证已保存的 AI 配置连通性...';
                resultEl.style.color = 'var(--text-secondary, #666)';
            }

            try {
                const resp = await fetch('/api/settings/verification-ai-test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                const data = await resp.json();

                if (!data.success) {
                    handleApiError(data, 'AI 配置测试失败');
                    if (resultEl) {
                        resultEl.textContent = '❌ AI 配置测试失败';
                        resultEl.style.color = 'var(--danger, red)';
                    }
                    return;
                }

                const probe = data.probe || {};
                if (data.ok) {
                    const parsed = probe.parsed_output || {};
                    const code = parsed.verification_code || '-';
                    const confidence = parsed.confidence || '-';
                    const latency = probe.latency_ms || 0;
                    const connectivityOnly = data.connectivity_ok && !data.contract_ok;
                    if (resultEl) {
                        if (connectivityOnly) {
                            resultEl.textContent = `✅ 连通正常（${latency}ms，HTTP ${probe.http_status || 200}）；契约校验未通过：${probe.error || '-'}`;
                            resultEl.style.color = 'var(--warning, #ff8c00)';
                        } else {
                            resultEl.textContent = `✅ 可用（${latency}ms，code=${code}，confidence=${confidence}）`;
                            resultEl.style.color = 'var(--success, green)';
                        }
                    }
                    showToast(connectivityOnly ? 'AI 连通性测试成功' : 'AI 配置测试成功', 'success');
                    return;
                }

                const message = probe.message || 'AI 配置测试失败';
                const detail = probe.error ? `（${probe.error}）` : '';
                if (resultEl) {
                    resultEl.textContent = `❌ ${message}${detail}`;
                    resultEl.style.color = 'var(--danger, red)';
                }
                showToast(message, 'warning');
            } catch (e) {
                const msg = `${translateAppTextLocal('请求失败')}: ${e.message}`;
                if (resultEl) {
                    resultEl.textContent = `❌ ${msg}`;
                    resultEl.style.color = 'var(--danger, red)';
                }
                showToast(msg, 'error');
            } finally {
                if (btn) { btn.disabled = false; btn.textContent = translateAppTextLocal('🤖 测试 AI 配置'); }
            }
        }

        async function syncCfWorkerDomains() {
            const btn = document.getElementById('btnSyncCfWorkerDomains');
            const hintEl = document.getElementById('cfWorkerSyncTime');
            if (btn) { btn.disabled = true; btn.textContent = translateAppTextLocal('⏳ 同步中…'); }
            try {
                const resp = await fetch('/api/settings/cf-worker-sync-domains', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                const data = await resp.json();
                if (data.success) {
                    // v0.3: 同步成功后更新 CF Worker 独立域名只读字段（不覆盖 GPTMail 的 temp_mail_* 字段）
                    updateCfWorkerReadonlyFields(data);
                    const msg = data.message || `已同步 ${(data.domains || []).length} 个域名`;
                    showToast(msg, 'success');
                    if (hintEl) {
                        const versionInfo = data.version ? ` (${data.version})` : '';
                        const titleInfo = data.title ? `「${data.title}」` : '';
                        hintEl.textContent = `✅ 同步成功 ${titleInfo}${versionInfo}：${(data.domains || []).join(', ')}  — 上次同步：${new Date().toLocaleString()}`;
                    }
                } else {
                    const errMsg = (data.error && data.error.message) || '同步失败，请检查 CF Worker 地址配置';
                    handleApiError(data, errMsg);
                    if (hintEl) { hintEl.textContent = `❌ ${errMsg}`; }
                }
            } catch (e) {
                showToast(`${translateAppTextLocal('请求失败')}: ${e.message}`, 'error');
                if (hintEl) { hintEl.textContent = `❌ 请求失败: ${e.message}`; }
            } finally {
                if (btn) { btn.disabled = false; btn.textContent = translateAppTextLocal('☁ 从 CF Worker 同步域名'); }
            }
        }

        // ==================== v0.3: 设置页面 Tab 重构 ====================

        // 当前激活的 Tab（默认 basic）
        let currentSettingsTab = 'basic';

        // Tab 切换函数
        function switchSettingsTab(tabName) {
            const prevTab = currentSettingsTab;
            if (prevTab === tabName) return; // 同一 Tab 无操作
            currentSettingsTab = tabName;

            // 1. 基础 Tab 切走时，密码框有内容则清空 + Toast 提示
            if (prevTab === 'basic') {
                const pwdEl = document.getElementById('settingsPassword');
                if (pwdEl && pwdEl.value.trim()) {
                    pwdEl.value = '';
                    showToast('密码修改未保存，如需修改请在「基础」Tab 重新输入后点击保存', 'warning');
                }
            }

            // 2. 立即更新 Tab 按钮视觉状态
            document.querySelectorAll('.settings-tab').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.tab === tabName);
            });

            // 3. 立即更新 Tab 内容区显隐
            document.querySelectorAll('.settings-tab-pane').forEach(pane => {
                pane.classList.toggle('active', pane.id === `settings-tab-${tabName}`);
            });

            // 4. 后台异步触发自动保存（基础 Tab 除外）
            if (prevTab !== 'basic') {
                autoSaveSettings(prevTab);
            }
        }

        // 自动保存逻辑（密码除外）
        async function autoSaveSettings(tabName) {
            if (tabName === 'basic') return;

            const settings = {};

            if (tabName === 'temp-mail') {
                const provider = document.querySelector('input[name="tempMailProvider"]:checked')?.value || 'legacy_bridge';
                settings.temp_mail_provider = provider;

                if (provider === 'legacy_bridge') {
                    const baseUrlEl = document.getElementById('settingsTempMailApiBaseUrl');
                    if (baseUrlEl) settings.temp_mail_api_base_url = baseUrlEl.value.trim();

                    const apiKeyEl = document.getElementById('settingsTempMailApiKey');
                    if (apiKeyEl) {
                        const val = apiKeyEl.value.trim();
                        const masked = apiKeyEl.dataset.maskedValue || '';
                        const isSet = apiKeyEl.dataset.isSet === 'true';
                        if (!(isSet && val && val === masked)) {
                            settings.temp_mail_api_key = val;
                        }
                    }

                    const defaultDomainEl = document.getElementById('settingsTempMailDefaultDomain');
                    if (defaultDomainEl) settings.temp_mail_default_domain = defaultDomainEl.value.trim();

                    const domainsEl = document.getElementById('settingsTempMailDomains');
                    if (domainsEl && domainsEl.value.trim()) {
                        try { settings.temp_mail_domains = JSON.parse(domainsEl.value.trim()); } catch (_) {}
                    }

                    const prefixRulesEl = document.getElementById('settingsTempMailPrefixRules');
                    if (prefixRulesEl && prefixRulesEl.value.trim()) {
                        try { settings.temp_mail_prefix_rules = JSON.parse(prefixRulesEl.value.trim()); } catch (_) {}
                    }
                } else {
                    // CF Worker 面板字段（只读域名字段不写入）
                    const cfBaseUrlEl = document.getElementById('settingsCfWorkerBaseUrl');
                    if (cfBaseUrlEl) settings.cf_worker_base_url = cfBaseUrlEl.value.trim();

                    const cfAdminKeyEl = document.getElementById('settingsCfWorkerAdminKey');
                    if (cfAdminKeyEl) {
                        const val = cfAdminKeyEl.value.trim();
                        const masked = cfAdminKeyEl.dataset.maskedValue || '';
                        const isSet = cfAdminKeyEl.dataset.isSet === 'true';
                        if (!(isSet && val && val === masked)) {
                            settings.cf_worker_admin_key = val;
                        }
                    }

                    const cfPrefixRulesEl = document.getElementById('settingsCfWorkerPrefixRules');
                    if (cfPrefixRulesEl && cfPrefixRulesEl.value.trim()) {
                        try { settings.cf_worker_prefix_rules = JSON.parse(cfPrefixRulesEl.value.trim()); } catch (_) {}
                    }
                }
            } else if (tabName === 'api-security') {
                const externalApiKeyEl = document.getElementById('settingsExternalApiKey');
                if (externalApiKeyEl) {
                    const val = externalApiKeyEl.value.trim();
                    const masked = externalApiKeyEl.dataset.maskedValue || '';
                    const isSet = externalApiKeyEl.dataset.isSet === 'true';
                    if (!(isSet && val && val === masked)) {
                        settings.external_api_key = val;
                    }
                }

                const externalApiKeysJsonEl = document.getElementById('settingsExternalApiKeysJson');
                if (externalApiKeysJsonEl && externalApiKeysJsonEl.value.trim()) {
                    try {
                        const parsed = JSON.parse(externalApiKeysJsonEl.value.trim());
                        if (Array.isArray(parsed)) settings.external_api_keys = parsed;
                    } catch (_) {}
                }

                const publicModeEl = document.getElementById('externalApiPublicMode');
                if (publicModeEl) settings.external_api_public_mode = publicModeEl.checked;

                const ipWhitelistEl = document.getElementById('externalApiIpWhitelist');
                if (ipWhitelistEl) {
                    settings.external_api_ip_whitelist = ipWhitelistEl.value.trim().split('\n').map(l => l.trim()).filter(l => l);
                }

                const rateLimitEl = document.getElementById('externalApiRateLimit');
                if (rateLimitEl) {
                    const rl = parseInt(rateLimitEl.value);
                    if (!isNaN(rl)) settings.external_api_rate_limit_per_minute = rl;
                }

                const disableRawEl = document.getElementById('externalApiDisableRaw');
                if (disableRawEl) settings.external_api_disable_raw_content = disableRawEl.checked;

                const disableWaitEl = document.getElementById('externalApiDisableWait');
                if (disableWaitEl) settings.external_api_disable_wait_message = disableWaitEl.checked;

                const poolExternalEnabledEl = document.getElementById('poolExternalEnabled');
                if (poolExternalEnabledEl) settings.pool_external_enabled = poolExternalEnabledEl.checked;

                const dpcrEl = document.getElementById('externalApiDisablePoolClaimRandom');
                if (dpcrEl) settings.external_api_disable_pool_claim_random = dpcrEl.checked;

                const dpcreleaseEl = document.getElementById('externalApiDisablePoolClaimRelease');
                if (dpcreleaseEl) settings.external_api_disable_pool_claim_release = dpcreleaseEl.checked;

                const dpccEl = document.getElementById('externalApiDisablePoolClaimComplete');
                if (dpccEl) settings.external_api_disable_pool_claim_complete = dpccEl.checked;

                const dpsEl = document.getElementById('externalApiDisablePoolStats');
                if (dpsEl) settings.external_api_disable_pool_stats = dpsEl.checked;
            } else if (tabName === 'automation') {
                const enableScheduled = document.getElementById('enableScheduledRefresh')?.checked;
                if (enableScheduled !== undefined) settings.enable_scheduled_refresh = enableScheduled;

                const strategy = document.querySelector('input[name="refreshStrategy"]:checked')?.value;
                if (strategy) settings.use_cron_schedule = strategy === 'cron';

                const refreshDays = parseInt(document.getElementById('refreshIntervalDays')?.value);
                if (!isNaN(refreshDays) && refreshDays >= 1 && refreshDays <= 90) settings.refresh_interval_days = refreshDays;

                const refreshDelay = parseInt(document.getElementById('refreshDelaySeconds')?.value);
                if (!isNaN(refreshDelay) && refreshDelay >= 0 && refreshDelay <= 60) settings.refresh_delay_seconds = refreshDelay;

                const refreshCron = document.getElementById('refreshCron')?.value?.trim();
                if (refreshCron && strategy === 'cron') settings.refresh_cron = refreshCron;

                const enablePolling = document.getElementById('enableAutoPolling')?.checked;
                if (enablePolling !== undefined) {
                    settings.enable_auto_polling = enablePolling;
                    settings.enable_compact_auto_poll = enablePolling;
                }

                const pInterval = parseInt(document.getElementById('pollingInterval')?.value);
                if (!isNaN(pInterval) && pInterval >= 3 && pInterval <= 300) {
                    settings.polling_interval = pInterval;
                    settings.compact_poll_interval = pInterval;
                }

                const pCount = parseInt(document.getElementById('pollingCount')?.value);
                if (!isNaN(pCount) && pCount >= 0 && pCount <= 100) {
                    settings.polling_count = pCount;
                    settings.compact_poll_max_count = pCount;
                }

                const emailNotifEnabled = document.getElementById('emailNotificationEnabled')?.checked;
                if (emailNotifEnabled !== undefined) settings.email_notification_enabled = emailNotifEnabled;

                const emailRecipient = document.getElementById('emailNotificationRecipient')?.value?.trim();
                if (emailRecipient !== undefined) settings.email_notification_recipient = emailRecipient;

                const tgToken = document.getElementById('telegramBotToken')?.value?.trim();
                if (tgToken) settings.telegram_bot_token = tgToken;

                const tgChatId = document.getElementById('telegramChatId')?.value?.trim();
                if (tgChatId !== undefined) settings.telegram_chat_id = tgChatId;

                const tgPoll = parseInt(document.getElementById('telegramPollInterval')?.value);
                if (!isNaN(tgPoll) && tgPoll >= 10 && tgPoll <= 86400) settings.telegram_poll_interval = tgPoll;

                const tgProxyUrlQuick = document.getElementById('telegramProxyUrl')?.value?.trim();
                if (tgProxyUrlQuick !== undefined) settings.telegram_proxy_url = tgProxyUrlQuick;

                const webhookEnabledQuick = document.getElementById('webhookNotificationEnabled')?.checked;
                if (webhookEnabledQuick !== undefined) settings.webhook_notification_enabled = webhookEnabledQuick;

                const webhookUrlQuick = document.getElementById('webhookNotificationUrl')?.value?.trim();
                if (webhookUrlQuick !== undefined) settings.webhook_notification_url = webhookUrlQuick;

                const webhookTokenEl = document.getElementById('webhookNotificationToken');
                if (webhookTokenEl) {
                    const val = webhookTokenEl.value.trim();
                    const masked = webhookTokenEl.dataset.maskedValue || '';
                    const isSet = webhookTokenEl.dataset.isSet === 'true';
                    if (!(isSet && val && val === masked)) {
                        settings.webhook_notification_token = val;
                    }
                }
            }

            if (Object.keys(settings).length === 0) return;

            // 显示保存中圆点
            const prevTabBtn = document.querySelector(`.settings-tab[data-tab="${tabName}"]`);
            let dotEl = null;
            if (prevTabBtn) {
                dotEl = document.createElement('span');
                dotEl.className = 'tab-save-dot';
                prevTabBtn.appendChild(dotEl);
                prevTabBtn.classList.add('saving');
            }

            try {
                const resp = await fetch('/api/settings', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(settings)
                });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                // 保存成功：移除圆点
                if (prevTabBtn) {
                    prevTabBtn.classList.remove('saving');
                    if (dotEl) dotEl.remove();
                }
            } catch (e) {
                // 保存失败：圆点变红保留 + 持久 Toast
                if (prevTabBtn) {
                    prevTabBtn.classList.remove('saving');
                    prevTabBtn.classList.add('save-error');
                }
                showToast(`保存失败，[${tabName}] Tab 的修改尚未保存，请手动重试`, 'error', null, true);
            }
        }

        // Provider 切换面板显隐
        function onTempMailProviderChange(provider) {
            const gptmailPanel = document.getElementById('gptmailConfigPanel');
            const cfWorkerPanel = document.getElementById('cfWorkerConfigPanel');
            const pluginPanel = document.getElementById('pluginProviderConfigPanel');
            const pluginManager = typeof window !== 'undefined' && window.PluginManager ? window.PluginManager : null;

            if (provider === 'legacy_bridge') {
                if (gptmailPanel) gptmailPanel.style.display = 'block';
                if (cfWorkerPanel) cfWorkerPanel.style.display = 'none';
                if (pluginManager && typeof pluginManager.hideProviderConfig === 'function') {
                    pluginManager.hideProviderConfig();
                } else if (pluginPanel) {
                    pluginPanel.style.display = 'none';
                }
            } else if (provider === 'cloudflare_temp_mail') {
                if (gptmailPanel) gptmailPanel.style.display = 'none';
                if (cfWorkerPanel) cfWorkerPanel.style.display = 'block';
                if (pluginManager && typeof pluginManager.hideProviderConfig === 'function') {
                    pluginManager.hideProviderConfig();
                } else if (pluginPanel) {
                    pluginPanel.style.display = 'none';
                }
            } else {
                if (gptmailPanel) gptmailPanel.style.display = 'none';
                if (cfWorkerPanel) cfWorkerPanel.style.display = 'none';
                if (pluginPanel) pluginPanel.style.display = 'block';
                if (pluginManager && typeof pluginManager.showProviderConfig === 'function') {
                    pluginManager.showProviderConfig(provider);
                }
            }
        }

        // 同步成功后更新 CF Worker 只读字段
        function updateCfWorkerReadonlyFields(data) {
            const domainsEl = document.getElementById('settingsCfWorkerDomains');
            const defaultDomainEl = document.getElementById('settingsCfWorkerDefaultDomain');
            const syncTimeEl = document.getElementById('cfWorkerSyncTime');

            if (domainsEl && data.domains) {
                domainsEl.value = JSON.stringify(
                    data.domains.map(d => ({ name: d, enabled: true })),
                    null, 2
                );
                domainsEl.classList.add('readonly-field');
                domainsEl.readOnly = true;
            }

            if (defaultDomainEl && data.default_domain) {
                defaultDomainEl.value = data.default_domain;
                defaultDomainEl.classList.add('readonly-field');
                defaultDomainEl.readOnly = true;
            }

            if (syncTimeEl) {
                syncTimeEl.textContent = `上次同步：${new Date().toLocaleString()}`;
                syncTimeEl.style.display = 'block';
            }
        }

        // ==================== 自动轮询功能 ====================

        // 初始化轮询设置
        async function initPollingSettings() {
            try {
                const response = await fetch('/api/settings');
                const data = await response.json();

                if (data.success) {
                    // [Phase 3] 统一使用 applyPollingSettings（内部已调用引擎 applyPollSettings）
                    applyPollingSettings(data.settings);
                }
            } catch (error) {
                console.error('初始化轮询设置失败:', error);
            }
        }

        // ==================== 工具函数 ====================

        // 相对时间格式化
        function formatRelativeTime(timestamp) {
            return formatUiRelativeTime(timestamp, '从未刷新', 'Never refreshed');
        }

        // ==================== Token 刷新管理 ====================

        // 显示刷新模态框
        async function showRefreshModal() {
            document.getElementById('refreshModal').classList.add('show');
            resetInvalidTokenGovernanceState();
            // 加载统计数据
            await loadRefreshStats();
            // 自动加载失败列表（如果有失败记录）
            await autoLoadFailedListIfNeeded();
            // 自动加载失效 token 治理候选（若存在）
            await loadInvalidTokenGovernanceCandidates({
                keepVisibleWhenEmpty: false,
                silentWhenEmpty: true
            });
        }

        // 自动加载失败列表（如果有失败记录）
        async function autoLoadFailedListIfNeeded() {
            try {
                const response = await fetch('/api/accounts/refresh-logs/failed');
                const data = await response.json();

                if (data.success && data.logs && data.logs.length > 0) {
                    // 有失败记录，自动显示失败列表
                    showFailedListFromData(data.logs.map(log => ({
                        id: log.account_id,
                        email: log.account_email,
                        error: log.error_message
                    })));
                }
            } catch (error) {
                console.error('自动加载失败列表失败:', error);
            }
        }

        // 隐藏刷新模态框
        function hideRefreshModal() {
            const modal = document.getElementById('refreshModal');
            modal.classList.remove('show');

            // 确保所有内容都被隐藏，防止残留
            const progress = document.getElementById('refreshProgress');
            if (progress) {
                progress.style.display = 'none';
            }
            const failedList = document.getElementById('failedListContainer');
            if (failedList) {
                failedList.style.display = 'none';
            }
            const logsContainer = document.getElementById('refreshLogsContainer');
            if (logsContainer) {
                logsContainer.style.display = 'none';
            }
            resetInvalidTokenGovernanceState();

            // 重置按钮状态
            const refreshAllBtn = document.getElementById('refreshAllBtn');
            if (refreshAllBtn) {
                refreshAllBtn.disabled = false;
                refreshAllBtn.textContent = translateAppTextLocal('🔄 全量刷新');
            }

            const retryFailedBtn = document.getElementById('retryFailedBtn');
            if (retryFailedBtn) {
                retryFailedBtn.disabled = false;
                retryFailedBtn.textContent = translateAppTextLocal('🔁 重试失败');
            }
        }

        // ==================== 失效 Token 治理面板 ====================

        /** 重置治理面板状态（模态框打开/关闭时调用） */
        function resetInvalidTokenGovernanceState() {
            latestInvalidTokenDetectedCount = 0;
            invalidTokenGovernanceCandidates = [];
            const container = document.getElementById('invalidTokenGovernanceContainer');
            if (container) container.style.display = 'none';
            const summary = document.getElementById('invalidTokenSummary');
            if (summary) summary.style.display = 'none';
            const listWrap = document.getElementById('invalidTokenCandidateListWrap');
            if (listWrap) listWrap.style.display = 'none';
        }

        /** 显示检测摘要横幅（刷新完成有 invalid token 时调用） */
        function showInvalidTokenDetectionSummary(count, failedList) {
            const summary = document.getElementById('invalidTokenSummary');
            const summaryText = document.getElementById('invalidTokenSummaryText');
            if (!summary || !summaryText) return;

            summaryText.textContent = `检测到 ${count} 个疑似失效 Token 的账号，需要治理处理`;
            summary.style.display = 'block';

            // 同时显示治理面板容器
            const container = document.getElementById('invalidTokenGovernanceContainer');
            if (container) container.style.display = 'block';
        }

        /** 隐藏治理面板 */
        function hideInvalidTokenGovernance() {
            const container = document.getElementById('invalidTokenGovernanceContainer');
            if (container) container.style.display = 'none';
            const summary = document.getElementById('invalidTokenSummary');
            if (summary) summary.style.display = 'none';
            const listWrap = document.getElementById('invalidTokenCandidateListWrap');
            if (listWrap) listWrap.style.display = 'none';
        }

        /** 从后端加载治理候选列表并渲染 */
        async function loadInvalidTokenGovernanceCandidates(options = {}) {
            const { keepVisibleWhenEmpty = false, silentWhenEmpty = false } = options;

            try {
                const response = await fetch('/api/accounts/invalid-token-candidates?limit=200');
                const data = await response.json();

                if (!data.success) {
                    if (!silentWhenEmpty) {
                        showToast('加载失效 Token 候选失败', 'error');
                    }
                    return;
                }

                invalidTokenGovernanceCandidates = data.candidates || [];
                const count = invalidTokenGovernanceCandidates.length;

                // 更新数量标签
                const countEl = document.getElementById('invalidTokenCandidateCount');
                if (countEl) {
                    countEl.textContent = `${count} 个`;
                }

                if (count === 0) {
                    if (!keepVisibleWhenEmpty) {
                        hideInvalidTokenGovernance();
                    }
                    return;
                }

                // 渲染候选列表
                const listEl = document.getElementById('invalidTokenCandidateList');
                const listWrap = document.getElementById('invalidTokenCandidateListWrap');

                if (!listEl || !listWrap) return;

                let html = '';
                invalidTokenGovernanceCandidates.forEach(item => {
                    const statusBadge = item.account_status === 'inactive'
                        ? '<span style="background-color:#fbbf24;color:#78350f;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;">已停用</span>'
                        : '<span style="background-color:#34d399;color:#064e3b;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;">活跃</span>';

                    html += `
                        <div style="padding:10px 12px;border-bottom:1px solid #e5e5e5;display:flex;justify-content:space-between;align-items:start;gap:10px;">
                            <div style="flex:1;min-width:0;">
                                <div style="font-weight:600;margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${escapeHtml(item.account_email)}">${escapeHtml(item.account_email)}</div>
                                <div style="font-size:12px;color:#dc3545;margin-bottom:2px;word-break:break-all;">${escapeHtml(item.error_message || '未知错误')}</div>
                                <div style="font-size:11px;color:#999;">原因: ${escapeHtml(item.reason_label || item.reason_code || '-')} ｜ 刷新时间: ${formatDateTime(item.created_at)}</div>
                            </div>
                            <div style="flex-shrink:0;display:flex;align-items:center;gap:4px;">
                                ${statusBadge}
                            </div>
                        </div>
                    `;
                });

                listEl.innerHTML = html;
                listWrap.style.display = 'block';

                // 确保容器可见
                const container = document.getElementById('invalidTokenGovernanceContainer');
                if (container) container.style.display = 'block';

            } catch (error) {
                console.error('加载失效 Token 候选失败:', error);
                if (!silentWhenEmpty) {
                    showToast('加载失效 Token 候选失败', 'error');
                }
            }
        }

        /** 批量将失效 Token 候选账号置为停用 */
        async function batchSetInvalidTokenInactive() {
            if (invalidTokenGovernanceCandidates.length === 0) {
                showToast('没有需要处理的候选账号', 'warning');
                return;
            }

            // 只取状态不是 inactive 的账号
            const targetCandidates = invalidTokenGovernanceCandidates.filter(c => c.account_status !== 'inactive');
            if (targetCandidates.length === 0) {
                showToast('所有候选账号已经是停用状态', 'info');
                return;
            }

            const accountIds = targetCandidates.map(c => c.account_id);
            const confirmed = confirm(`确定要将 ${accountIds.length} 个失效 Token 账号置为停用吗？停用后账号将不再参与刷新和使用。`);
            if (!confirmed) return;

            await initCSRFToken();

            try {
                const response = await fetch('/api/accounts/batch-update-status', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ account_ids: accountIds, status: 'inactive' })
                });

                const data = await response.json();
                if (data.success) {
                    showToast(pickApiMessage(data, data.message, '批量停用成功'), 'success');
                    // 刷新候选列表与统计
                    await loadInvalidTokenGovernanceCandidates({ keepVisibleWhenEmpty: true, silentWhenEmpty: true });
                    await loadRefreshStats();
                    if (currentGroupId) {
                        delete accountsCache[currentGroupId];
                        loadAccountsByGroup(currentGroupId, true);
                    }
                } else {
                    handleApiError(data, '批量停用失败');
                }
            } catch (error) {
                console.error('批量停用失败:', error);
                showToast('批量停用请求失败', 'error');
            }
        }

        /** 批量删除失效 Token 候选账号（二次确认） */
        async function batchDeleteInvalidTokenCandidates() {
            if (invalidTokenGovernanceCandidates.length === 0) {
                showToast('没有需要处理的候选账号', 'warning');
                return;
            }

            const accountIds = invalidTokenGovernanceCandidates.map(c => c.account_id);
            const emailPreview = invalidTokenGovernanceCandidates.slice(0, 3).map(c => c.account_email).join(', ')
                + (accountIds.length > 3 ? ` 等 ${accountIds.length} 个` : '');

            const confirmed = confirm(
                `⚠️ 危险操作：确定要删除 ${accountIds.length} 个失效 Token 账号吗？\n\n涉及账号：${emailPreview}\n\n此操作不可撤销，请确认！`
            );
            if (!confirmed) return;

            // 二次确认
            const doubleConfirmed = confirm('再次确认：删除账号将同时清除所有相关数据，是否继续？');
            if (!doubleConfirmed) return;

            await initCSRFToken();

            try {
                const response = await fetch('/api/accounts/batch-delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ account_ids: accountIds })
                });

                const data = await response.json();
                if (data.success) {
                    showToast(pickApiMessage(data, data.message, '批量删除成功'), 'success');
                    hideInvalidTokenGovernance();
                    await loadRefreshStats();
                    if (currentGroupId) {
                        delete accountsCache[currentGroupId];
                        loadAccountsByGroup(currentGroupId, true);
                    }
                    loadGroups();
                } else {
                    handleApiError(data, '批量删除失败');
                }
            } catch (error) {
                console.error('批量删除失败:', error);
                showToast('批量删除请求失败', 'error');
            }
        }

        // ==================== 刷新统计与全量刷新 ====================

        // 加载刷新统计
        async function loadRefreshStats() {
            try {
                const response = await fetch('/api/accounts/refresh-stats');
                const data = await response.json();

                console.log('刷新统计数据:', data);

                if (data.success) {
                    const stats = data.stats;

                    // 优先使用保存的本地刷新时间
                    if (lastRefreshTime && lastRefreshTime instanceof Date) {
                        document.getElementById('lastRefreshTime').textContent = formatDateTime(lastRefreshTime.toISOString());
                    } else if (stats.last_refresh_time) {
                        document.getElementById('lastRefreshTime').textContent = formatDateTime(stats.last_refresh_time);
                    } else {
                        document.getElementById('lastRefreshTime').textContent = '-';
                    }

                    document.getElementById('totalRefreshCount').textContent = stats.total;
                    document.getElementById('successRefreshCount').textContent = stats.success_count;
                    document.getElementById('failedRefreshCount').textContent = stats.failed_count;

                    console.log('统计数据已更新到页面');
                }
            } catch (error) {
                console.error('加载刷新统计失败:', error);
            }
        }

        // 全量刷新所有账号
        async function refreshAllAccounts() {
            const btn = document.getElementById('refreshAllBtn');
            const progress = document.getElementById('refreshProgress');
            const progressText = document.getElementById('refreshProgressText');

            if (btn.disabled) return;

            if (!confirm('确定要刷新所有账号的 Token 吗？')) {
                return;
            }

            btn.disabled = true;
            btn.textContent = translateAppTextLocal('刷新中...');
            progress.style.display = 'block';
            progressText.innerHTML = translateAppTextLocal('正在初始化...');

            try {
                const eventSource = new EventSource('/api/accounts/trigger-scheduled-refresh?force=true');
                let totalCount = 0;
                let successCount = 0;
                let failedCount = 0;

                eventSource.onmessage = function (event) {
                    try {
                        const data = JSON.parse(event.data);

                        if (data.type === 'start') {
                            totalCount = data.total;
                            const delayInfo = data.delay_seconds > 0 ? `（间隔 ${data.delay_seconds} 秒）` : '';
                            progressText.innerHTML = `${translateAppTextLocal('总共')} <strong>${totalCount}</strong> ${translateAppTextLocal('个账号')}${delayInfo}，${translateAppTextLocal('准备开始刷新...')}`;
                            // 初始化统计
                            document.getElementById('totalRefreshCount').textContent = totalCount;
                            document.getElementById('successRefreshCount').textContent = '0';
                            document.getElementById('failedRefreshCount').textContent = '0';
                        } else if (data.type === 'progress') {
                            successCount = data.success_count;
                            failedCount = data.failed_count;
                            // 实时更新统计
                            document.getElementById('successRefreshCount').textContent = successCount;
                            document.getElementById('failedRefreshCount').textContent = failedCount;
                            progressText.innerHTML = `
                                ${translateAppTextLocal('正在处理')}: <strong>${data.email}</strong><br>
                                ${translateAppTextLocal('进度')}: <strong>${data.current}/${data.total}</strong> |
                                ${translateAppTextLocal('成功')}: <strong style="color: #28a745;">${successCount}</strong> |
                                ${translateAppTextLocal('失败')}: <strong style="color: #dc3545;">${failedCount}</strong>
                            `;
                        } else if (data.type === 'delay') {
                            progressText.innerHTML += `<br><span style="color: #999;">${translateAppTextLocal('等待')} ${data.seconds} ${translateAppTextLocal('秒后继续...')}</span>`;
                        } else if (data.type === 'complete') {
                            eventSource.close();
                            progress.style.display = 'none';
                            btn.disabled = false;
                            btn.textContent = translateAppTextLocal('🔄 全量刷新');

                            const invalidTokenFailedCount = Number(data.invalid_token_failed_count || 0);
                            latestInvalidTokenDetectedCount = invalidTokenFailedCount;

                            // 直接更新统计数据，使用本地时间
                            const now = new Date();
                            lastRefreshTime = now; // 保存刷新时间
                            document.getElementById('lastRefreshTime').textContent = formatUiRelativeTime(new Date().toISOString(), '刚刚', 'Just now');
                            document.getElementById('totalRefreshCount').textContent = data.total;
                            document.getElementById('successRefreshCount').textContent = data.success_count;
                            document.getElementById('failedRefreshCount').textContent = data.failed_count;

                            showToast(`${
                                getUiLanguage() === 'en'
                                    ? `Refresh completed. Success: ${data.success_count}, Failed: ${data.failed_count}`
                                    : `刷新完成！成功: ${data.success_count}, 失败: ${data.failed_count}`
                            }`,
                                data.failed_count > 0 ? 'warning' : 'success');

                            if (invalidTokenFailedCount > 0) {
                                showInvalidTokenDetectionSummary(invalidTokenFailedCount, data.invalid_token_failed_list || []);
                                loadInvalidTokenGovernanceCandidates({
                                    keepVisibleWhenEmpty: true,
                                    silentWhenEmpty: false
                                });
                            }

                            // 如果有失败的，显示失败列表
                            if (data.failed_count > 0) {
                                showFailedListFromData(data.failed_list);
                            }

                            // 刷新账号列表以更新刷新时间
                            if (currentGroupId) {
                                loadAccountsByGroup(currentGroupId, true);
                            }
                        } else if (data.type === 'error') {
                            eventSource.close();
                            progress.style.display = 'none';
                            btn.disabled = false;
                            btn.textContent = translateAppTextLocal('🔄 全量刷新');

                            const errCode = data.error && data.error.code;
                            if (errCode === 'NO_MAIL_PERMISSION') {
                                showToast(buildRefreshAllPermissionErrorSummary(data.error || {}), 'error', data.error || null, true);
                            } else {
                                const userMessage = window.resolveApiErrorMessage
                                    ? window.resolveApiErrorMessage(data.error || {}, '刷新过程中出现错误', 'Refresh failed during execution')
                                    : translateAppTextLocal('刷新过程中出现错误');

                                if (errCode === 'REFRESH_CONFLICT') {
                                    showToast(userMessage, 'warning', data.error || null, true);
                                } else {
                                    showToast(userMessage, 'error', data.error || null, true);
                                }
                            }
                        }
                    } catch (e) {
                        console.error('解析进度数据失败:', e);
                    }
                };

                eventSource.onerror = function (error) {
                    console.error('EventSource 错误:', error);
                    eventSource.close();
                    progress.style.display = 'none';
                    btn.disabled = false;
                    btn.textContent = translateAppTextLocal('🔄 全量刷新');
                    showToast(translateAppTextLocal('刷新过程中出现错误'), 'error');
                };

            } catch (error) {
                progress.style.display = 'none';
                btn.disabled = false;
                btn.textContent = translateAppTextLocal('🔄 全量刷新');
                showToast(translateAppTextLocal('刷新请求失败'), 'error');
            }
        }

        function buildRefreshAllPermissionErrorSummary(errorPayload) {
            const traceId = String(errorPayload && errorPayload.trace_id || '').trim();
            const lang = getUiLanguage();

            if (lang === 'en') {
                const lines = [
                    'This Outlook account is missing mail read permission, so full refresh cannot proceed.',
                    '[Code] NO_MAIL_PERMISSION',
                    '',
                    'Suggested actions:',
                    '1. Re-authorize the account and ensure Mail.Read or Mail.ReadWrite scope is granted.',
                    '2. Save account settings and retry full refresh.',
                    traceId
                        ? `3. If it still fails, share Trace ID: ${traceId}`
                        : '3. If it still fails, capture and share the Trace ID for backend diagnostics.',
                ];
                return lines.join('\n');
            }

            const lines = [
                '当前账号缺少邮件读取权限，导致全量刷新无法继续。',
                '[Code] NO_MAIL_PERMISSION',
                '',
                '建议处理：',
                '1. 重新授权账号，并确保授予 Mail.Read 或 Mail.ReadWrite 权限。',
                '2. 保存账号设置后再次执行“全量刷新”。',
                traceId
                    ? `3. 若仍失败，请反馈 Trace ID：${traceId}`
                    : '3. 若仍失败，请记录并反馈 Trace ID 以便后端排查。',
            ];
            return lines.join('\n');
        }

        // 重试失败的账号
        async function retryFailedAccounts() {
            const btn = document.getElementById('retryFailedBtn');
            const progress = document.getElementById('refreshProgress');
            const progressText = document.getElementById('refreshProgressText');

            if (btn.disabled) return;

            btn.disabled = true;
            btn.textContent = translateAppTextLocal('重试中...');
            progress.style.display = 'block';
            progressText.textContent = translateAppTextLocal('正在重试失败的账号...');

            try {
                const response = await fetch('/api/accounts/refresh-failed', {
                    method: 'POST'
                });
                const data = await response.json();

                progress.style.display = 'none';
                btn.disabled = false;
                btn.textContent = translateAppTextLocal('🔁 重试失败');

                if (data.success) {
                    if (data.total === 0) {
                        showToast(translateAppTextLocal('没有需要重试的失败账号'), 'info');
                    } else {
                        showToast(`${
                            getUiLanguage() === 'en'
                                ? `Retry completed. Success: ${data.success_count}, Failed: ${data.failed_count}`
                                : `重试完成！成功: ${data.success_count}, 失败: ${data.failed_count}`
                        }`,
                            data.failed_count > 0 ? 'warning' : 'success');

                        // 刷新统计
                        loadRefreshStats();

                        // 失效 Token 治理
                        const retryInvalidTokenCount = Number(data.invalid_token_failed_count || 0);
                        latestInvalidTokenDetectedCount = retryInvalidTokenCount;
                        if (retryInvalidTokenCount > 0) {
                            showInvalidTokenDetectionSummary(retryInvalidTokenCount, data.invalid_token_failed_list || []);
                            loadInvalidTokenGovernanceCandidates({
                                keepVisibleWhenEmpty: true,
                                silentWhenEmpty: false
                            });
                        }

                        // 如果还有失败的，显示失败列表
                        if (data.failed_count > 0) {
                            showFailedListFromData(data.failed_list);
                        } else {
                            hideFailedList();
                        }
                    }
                } else {
                    const errCode = data && data.error && data.error.code;
                    if (errCode === 'REFRESH_CONFLICT') {
                        const msg = window.resolveApiErrorMessage
                            ? window.resolveApiErrorMessage(data.error, '当前已有刷新任务执行中，请等待当前任务完成后再重试', 'Another refresh task is already running. Wait for it to finish and retry.')
                            : translateAppTextLocal('当前已有刷新任务执行中，请等待当前任务完成后再重试');
                        showToast(msg, 'warning', data.error || null, true);
                    } else {
                        handleApiError(data, '重试失败');
                    }
                }
            } catch (error) {
                progress.style.display = 'none';
                btn.disabled = false;
                btn.textContent = translateAppTextLocal('🔁 重试失败');
                showToast(translateAppTextLocal('重试请求失败'), 'error');
            }
        }

        // 单个账号重试
        async function retrySingleAccount(accountId, accountEmail) {
            try {
                const response = await fetch(`/api/accounts/${accountId}/retry-refresh`, {
                    method: 'POST'
                });
                const data = await response.json();

                if (data.success) {
                    showToast(
                        getUiLanguage() === 'en'
                            ? `${accountEmail} refreshed successfully`
                            : `${accountEmail} 刷新成功`,
                        'success'
                    );
                    loadRefreshStats();

                    // 刷新失败列表
                    loadFailedLogs();
                } else {
                    handleApiError(data, `${accountEmail} 刷新失败`);
                }
            } catch (error) {
                handleApiError({
                    success: false,
                    error: {
                        message: '刷新请求失败',
                        message_en: 'Refresh request failed',
                        details: error.message,
                        code: 'NETWORK_ERROR',
                        type: 'Frontend'
                    }
                });
            }
        }

        // 显示失败列表（从数据）
        function showFailedListFromData(failedList) {
            const container = document.getElementById('failedListContainer');
            const listEl = document.getElementById('failedList');

            // 隐藏其他列表
            hideRefreshLogs();

            if (!failedList || failedList.length === 0) {
                container.style.display = 'none';
                return;
            }

            let html = '';
            failedList.forEach(item => {
                html += `
                    <div style="padding: 12px; border-bottom: 1px solid #e5e5e5; display: flex; justify-content: space-between; align-items: start;">
                        <div style="flex: 1;">
                            <div style="font-weight: 600; margin-bottom: 4px;">${escapeHtml(item.email)}</div>
                            <div style="font-size: 12px; color: #dc3545;">${escapeHtml(item.error || '未知错误')}</div>
                        </div>
                        <button class="btn btn-sm btn-primary" onclick="retrySingleAccount(${item.id}, '${escapeHtml(item.email)}')">
                            重试
                        </button>
                    </div>
                `;
            });

            listEl.innerHTML = html;
            container.style.display = 'block';
        }

        // 隐藏失败列表
        function hideFailedList() {
            document.getElementById('failedListContainer').style.display = 'none';
        }

        // 加载失败日志
        async function loadFailedLogs() {
            const container = document.getElementById('failedListContainer');
            const listEl = document.getElementById('failedList');

            hideRefreshLogs();

            try {
                const response = await fetch('/api/accounts/refresh-logs/failed');
                const data = await response.json();

                if (data.success) {
                    if (data.logs.length === 0) {
                        listEl.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">暂无失败状态的邮箱</div>';
                    } else {
                        let html = '';
                        data.logs.forEach(log => {
                            html += `
                                <div style="padding: 12px; border-bottom: 1px solid #e5e5e5; display: flex; justify-content: space-between; align-items: center;">
                                    <div style="flex: 1;">
                                        <div style="font-weight: 600; margin-bottom: 4px;">${escapeHtml(log.account_email)}</div>
                                        <div style="font-size: 12px; color: #dc3545;">${escapeHtml(log.error_message || '未知错误')}</div>
                                        <div style="font-size: 11px; color: #999; margin-top: 4px;">最后刷新: ${formatDateTime(log.created_at)}</div>
                                    </div>
                                    <button class="btn btn-sm btn-primary" onclick="retrySingleAccount(${log.account_id}, '${escapeJs(log.account_email)}')">
                                        重试
                                    </button>
                                </div>
                            `;
                        });
                        listEl.innerHTML = html;
                    }
                    container.style.display = 'block';
                }
            } catch (error) {
                showToast(translateAppTextLocal('加载失败邮箱列表失败'), 'error');
            }
        }

        // 加载刷新历史
        async function loadRefreshLogs() {
            const container = document.getElementById('refreshLogsContainer');
            const listEl = document.getElementById('refreshLogsList');

            try {
                const response = await fetch('/api/accounts/refresh-logs?limit=1000');
                const data = await response.json();

                if (data.success) {
                    if (data.logs.length === 0) {
                        listEl.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">暂无全量刷新历史</div>';
                    } else {
                        listEl.innerHTML = `<div style="padding: 12px; background-color: #f8f9fa; border-bottom: 1px solid #e5e5e5; font-size: 13px; color: #666;">近半年刷新历史（共 ${data.logs.length} 条）</div>`;
                        let html = '';
                        data.logs.forEach(log => {
                            const statusColor = log.status === 'success' ? '#28a745' : '#dc3545';
                            const statusText = log.status === 'success' ? '成功' : '失败';
                            const typeText = translateAppTextLocal(log.refresh_type === 'manual' ? '手动' : '自动');
                            const typeColor = log.refresh_type === 'manual' ? '#007bff' : '#28a745';
                            const typeBgColor = log.refresh_type === 'manual' ? '#e7f3ff' : '#e8f5e9';

                            html += `
                                <div style="padding: 14px; border-bottom: 1px solid #e5e5e5; transition: background-color 0.2s;"
                                     onmouseover="this.style.backgroundColor='#f8f9fa'"
                                     onmouseout="this.style.backgroundColor='transparent'">
                                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 6px;">
                                        <div style="font-weight: 600; font-size: 14px;">${escapeHtml(log.account_email)}</div>
                                        <div style="display: flex; gap: 8px; align-items: center;">
                                            <span style="font-size: 11px; padding: 3px 8px; background-color: ${typeBgColor}; color: ${typeColor}; border-radius: 4px; font-weight: 500;">${typeText}</span>
                                            <span style="font-size: 13px; color: ${statusColor}; font-weight: 600;">${statusText}</span>
                                        </div>
                                    </div>
                                    <div style="font-size: 12px; color: #888;">${formatDateTime(log.created_at)}</div>
                                    ${log.error_message ? `<div style="font-size: 12px; color: #dc3545; margin-top: 6px; padding: 6px; background-color: #fff5f5; border-radius: 4px;">${escapeHtml(log.error_message)}</div>` : ''}
                                </div>
                            `;
                        });
                        listEl.innerHTML += html;
                    }
                    container.style.display = 'block';
                }
            } catch (error) {
                showToast(translateAppTextLocal('加载刷新历史失败'), 'error');
            }
        }

        // 隐藏刷新历史
        function hideRefreshLogs() {
            document.getElementById('refreshLogsContainer').style.display = 'none';
        }

        // ==================== 页面级：刷新日志 ====================

        async function loadRefreshLogPage() {
            const container = document.getElementById('refreshLogContainer');
            if (!container) return;
            container.innerHTML = `<div class="loading-overlay"><span class="spinner"></span> ${translateAppTextLocal('加载中…')}</div>`;

            try {
                const response = await fetch('/api/accounts/refresh-logs?limit=200');
                const data = await response.json();

                if (data.success && data.logs && data.logs.length > 0) {
                    container.innerHTML = `
                        <div style="padding:0.6rem 1rem;font-size:0.78rem;color:var(--text-muted);border-bottom:1px solid var(--border-light);">
                            ${translateAppTextLocal(`共 ${data.logs.length} 条记录`)}
                        </div>
                        <div class="dashboard-list-wrap">
                            ${data.logs.map(log => {
                                const isSuccess = log.status === 'success';
                                const statusBadge = isSuccess
                                    ? `<span class="badge" style="background:var(--clr-jade);color:white;">${translateAppTextLocal('成功')}</span>`
                                    : `<span class="badge" style="background:var(--clr-danger);color:white;">${translateAppTextLocal('失败')}</span>`;
                                const typeText = translateAppTextLocal(
                                    log.refresh_type === 'manual' ? '手动' : (log.refresh_type === 'scheduled' ? '定时' : (log.refresh_type || '-'))
                                );
                                return `
                                    <div style="padding:0.75rem 1rem;border-bottom:1px solid var(--border-light);display:flex;align-items:center;gap:0.8rem;">
                                        <div style="flex:1;min-width:0;">
                                            <div style="font-weight:600;font-size:0.85rem;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(log.account_email || '-')}</div>
                                            <div style="font-size:0.72rem;color:var(--text-muted);margin-top:2px;">${formatDateTime(log.created_at)} · ${escapeHtml(typeText)}</div>
                                            ${log.error_message ? `<div style="font-size:0.72rem;color:var(--clr-danger);margin-top:4px;padding:4px 8px;background:rgba(185,28,28,0.06);border-radius:4px;">${escapeHtml(log.error_message)}</div>` : ''}
                                        </div>
                                        ${statusBadge}
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    `;
                } else {
                    container.innerHTML = `<div class="empty-state"><span class="empty-icon">📭</span><p>${translateAppTextLocal('暂无刷新记录')}</p></div>`;
                }
            } catch (error) {
                container.innerHTML = `<div class="empty-state"><span class="empty-icon">⚠️</span><p>${translateAppTextLocal('加载刷新历史失败')}</p></div>`;
            }
        }

        // ==================== 页面级：审计日志 ====================

        function translateAuditDetailValue(value) {
            if (typeof value === 'string') {
                return translateAppTextLocal(value);
            }
            if (Array.isArray(value)) {
                return value.map(translateAuditDetailValue);
            }
            if (value && typeof value === 'object') {
                return Object.fromEntries(
                    Object.entries(value).map(([key, nestedValue]) => [key, translateAuditDetailValue(nestedValue)])
                );
            }
            return value;
        }

        function formatAuditDetailText(details) {
            if (details == null) {
                return '';
            }
            if (typeof details === 'string') {
                const trimmed = details.trim();
                if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
                    try {
                        return JSON.stringify(translateAuditDetailValue(JSON.parse(trimmed)));
                    } catch (error) {
                        return translateAppTextLocal(details);
                    }
                }
                return translateAppTextLocal(details);
            }
            if (typeof details === 'object') {
                try {
                    return JSON.stringify(translateAuditDetailValue(details));
                } catch (error) {
                    return translateAppTextLocal(String(details));
                }
            }
            return translateAppTextLocal(String(details));
        }

        async function loadAuditLogPage() {
            const container = document.getElementById('auditLogContainer');
            if (!container) return;
            container.innerHTML = `<div class="loading-overlay"><span class="spinner"></span> ${translateAppTextLocal('加载中…')}</div>`;

            try {
                const response = await fetch('/api/audit-logs?limit=200');
                const data = await response.json();

                if (data.success && data.logs && data.logs.length > 0) {
                    container.innerHTML = `
                        <div style="padding:0.6rem 1rem;font-size:0.78rem;color:var(--text-muted);border-bottom:1px solid var(--border-light);">
                            ${translateAppTextLocal(`共 ${data.total || data.logs.length} 条记录`)}
                        </div>
                        <div class="dashboard-list-wrap">
                            ${data.logs.map(log => {
                                const actionColor = log.action === 'delete' ? 'var(--clr-danger)' : (log.action === 'create' ? 'var(--clr-jade)' : 'var(--clr-primary)');
                                const actionLabel = translateAppTextLocal(log.action || '-');
                                const resourceTypeLabel = translateAppTextLocal(log.resource_type || '-');
                                const detailText = formatAuditDetailText(log.details);
                                return `
                                    <div style="padding:0.75rem 1rem;border-bottom:1px solid var(--border-light);">
                                        <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:4px;">
                                            <span class="badge" style="background:${actionColor};color:white;font-size:0.68rem;">${escapeHtml(actionLabel)}</span>
                                            <span style="font-size:0.78rem;color:var(--text-muted);">${escapeHtml(resourceTypeLabel)}</span>
                                            <span style="font-size:0.72rem;color:var(--text-muted);margin-left:auto;">${formatDateTime(log.created_at)}</span>
                                        </div>
                                        <div style="font-size:0.82rem;color:var(--text);">${escapeHtml(log.resource_id || '-')}</div>
                                        ${detailText ? `<div style="font-size:0.72rem;color:var(--text-muted);margin-top:4px;word-break:break-all;">${escapeHtml(detailText).substring(0, 200)}</div>` : ''}
                                        <div style="font-size:0.68rem;color:var(--text-muted);margin-top:2px;">IP: ${escapeHtml(log.user_ip || '-')} ${log.trace_id ? '· trace: ' + escapeHtml(log.trace_id) : ''}</div>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    `;
                } else {
                    container.innerHTML = `<div class="empty-state"><span class="empty-icon">📭</span><p>${translateAppTextLocal('暂无审计记录')}</p></div>`;
                }
            } catch (error) {
                container.innerHTML = `<div class="empty-state"><span class="empty-icon">⚠️</span><p>${translateAppTextLocal('加载审计日志失败')}</p></div>`;
            }
        }

        // 格式化日期时间
        function formatDateTime(dateStr) {
            return formatUiDateTime(dateStr, { fallback: '-' });
        }

        // 统一关闭所有模态框的函数 (修复 bug：防止模态框意外残留)
        function closeAllModals() {
            hideAddGroupModal();
            hideAddAccountModal();
            hideEditAccountModal();
            hideExportModal();
            hideSettingsModal();
            hideRefreshModal();
            hideRefreshErrorModal();
            hideErrorDetailModal();
            closeFullscreenEmail();
        }

        // HTML 转义
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // 键盘快捷键
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                hideAddGroupModal();
                hideAddAccountModal();
                hideEditAccountModal();
                hideExportModal();
                hideSettingsModal();
                hideRefreshModal();
                hideRefreshErrorModal();
                hideErrorDetailModal();
                closeFullscreenEmail();
            }
        });
        // ==================== 标签管理 ====================

        let allTags = [];

        // 显示标签管理模态框
        async function showTagManagementModal() {
            document.getElementById('tagManagementModal').classList.add('show');
            await loadTags();
        }

        // 隐藏标签管理模态框
        function hideTagManagementModal() {
            document.getElementById('tagManagementModal').classList.remove('show');
        }

        // 加载标签列表
        async function loadTags() {
            try {
                const response = await fetch('/api/tags');
                const data = await response.json();
                if (data.success) {
                    allTags = data.tags;
                    renderTagList();
                    updateTagFilter();  // Update Filter Dropdown
                }
            } catch (error) {
                showToast(translateAppTextLocal('加载标签失败'), 'error');
            }
        }

        // 更新标签筛选下拉框
        function updateTagFilter() {
            const container = document.getElementById('tagFilterContainer');
            if (!container) return;

            if (allTags.length === 0) {
                container.style.display = 'none';
                return;
            }

            container.style.display = 'flex';

            let html = '';
            allTags.forEach(tag => {
                html += `
                    <label style="display: inline-flex; align-items: center; gap: 4px; font-size: 11px; cursor: pointer; padding: 2px 6px; border: 1px solid #e5e5e5; border-radius: 12px; background: white; user-select: none;">
                        <input type="checkbox" class="tag-filter-checkbox" value="${tag.id}" onchange="handleTagFilterChange()" style="margin: 0;">
                        <span style="width: 8px; height: 8px; border-radius: 50%; background-color: ${tag.color}; display: inline-block;"></span>
                        ${escapeHtml(tag.name)}
                    </label>
                `;
            });
            container.innerHTML = html;
            /* Old dropdown code removed */


        }

        // 渲染标签列表
        function renderTagList() {
            const listEl = document.getElementById('tagList');
            if (!allTags.length) {
                listEl.innerHTML = `<div style="text-align: center; color: #999; padding: 20px;">${translateAppTextLocal('暂无标签')}</div>`;
                return;
            }

            let html = '';
            allTags.forEach(tag => {
                html += `
                    <div style="display: flex; align-items: center; justify-content: space-between; padding: 8px; border-bottom: 1px solid #f0f0f0;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span class="tag-badge" style="background-color: ${tag.color};">${escapeHtml(tag.name)}</span>
                        </div>
                        <button class="btn btn-sm btn-danger" onclick="deleteTag(${tag.id})">${translateAppTextLocal('删除')}</button>
                    </div>
                `;
            });
            listEl.innerHTML = html;
        }

        // 创建标签
        async function createTag() {
            const nameInput = document.getElementById('newTagName');
            const colorInput = document.getElementById('newTagColor');
            const name = nameInput.value.trim();
            const color = colorInput.value;

            if (!name) {
                showToast(translateAppTextLocal('请输入标签名称'), 'error');
                return;
            }

            try {
                const response = await fetch('/api/tags', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, color })
                });
                const data = await response.json();

                if (data.success) {
                    nameInput.value = '';
                    showToast(translateAppTextLocal('标签创建成功'), 'success');
                    await loadTags();
                    // 刷新账号列表以重新加载标签（如果是在查看列表时添加标签，可能不需要立即刷新列表，但为了保持一致性可以刷新）
                    // 但通常添加标签不影响当前列表显示，除非是给账号打标
                } else {
                    handleApiError(data, '创建失败');
                }
            } catch (error) {
                showToast(translateAppTextLocal('创建标签失败'), 'error');
            }
        }

        // 删除标签
        async function deleteTag(id) {
            if (!confirm('确定要删除这个标签吗？')) return;

            try {
                const response = await fetch(`/api/tags/${id}`, { method: 'DELETE' });
                const data = await response.json();

                if (data.success) {
                    showToast(translateAppTextLocal('标签已删除'), 'success');
                    await loadTags();
                    // 刷新账号列表以更新标签显示
                    if (currentGroupId) {
                        loadAccountsByGroup(currentGroupId, true);
                    }
                } else {
                    handleApiError(data, '删除失败');
                }
            } catch (error) {
                showToast(translateAppTextLocal('删除标签失败'), 'error');
            }
        }

        // ==================== 批量操作 ====================

        // 全局选中的账号 ID 集合（跨分组保持）
        let selectedAccountIds = new Set();
        let batchMoveGroupContext = { scopedAccountIds: null };

        function getActiveAccountCheckboxes() {
            const selector = mailboxViewMode === 'compact'
                ? '#compactAccountList .account-select-checkbox'
                : '#accountList .account-select-checkbox';
            return Array.from(document.querySelectorAll(selector));
        }

        function handleAccountSelectionChange(accountId, checked) {
            if (checked) {
                selectedAccountIds.add(accountId);
            } else {
                selectedAccountIds.delete(accountId);
            }
            updateBatchActionBar();
            updateSelectAllCheckbox();
        }

        // 更新批量操作栏状态
        function updateBatchActionBar() {
            const barConfigs = [
                { barId: 'batchActionBar', countId: 'selectedCount', active: mailboxViewMode === 'standard' },
                { barId: 'compactBatchActionBar', countId: 'compactSelectedCount', active: mailboxViewMode === 'compact' }
            ];

            barConfigs.forEach(config => {
                const bar = document.getElementById(config.barId);
                const countSpan = document.getElementById(config.countId);
                if (!bar || !countSpan) return;

                if (selectedAccountIds.size > 0 && config.active) {
                    bar.style.display = 'flex';
                    countSpan.textContent = formatSelectedItemsLabel(selectedAccountIds.size);
                } else {
                    bar.style.display = 'none';
                }
            });
        }

        window.addEventListener('ui-language-changed', () => {
            updateTopbar(currentPage);
            updateBatchActionBar();

            // 语言切换后，重渲染部署警告文案（后端同时返回中英文）
            if (lastDeploymentInfo) {
                try {
                    renderDeploymentWarnings(lastDeploymentInfo);
                } catch (e) {}
            }
        });

        // 显示批量刷新 Token 确认框
        async function showBatchRefreshConfirm() {
            if (selectedAccountIds.size === 0) {
                showToast('请选择要刷新 Token 的账号', 'error');
                return;
            }

            const accountIds = Array.from(selectedAccountIds);

            // 检查是否有 IMAP 账号（通过 data-account-type 属性判断）
            let imapCount = 0;
            const allCheckboxes = document.querySelectorAll('.account-select-checkbox');
            allCheckboxes.forEach(cb => {
                const id = parseInt(cb.dataset.accountId || cb.value);
                if (accountIds.includes(id)) {
                    const card = cb.closest('[data-account-type]');
                    if (card && card.dataset.accountType === 'imap') {
                        imapCount++;
                    }
                }
            });

            const outlookCount = accountIds.length - imapCount;

            if (outlookCount === 0) {
                showToast('所选账号均为 IMAP 账号，不支持 Token 刷新', 'warning');
                return;
            }

            let confirmMsg;
            if (imapCount > 0) {
                confirmMsg = `已选 ${accountIds.length} 个账号，其中 ${imapCount} 个 IMAP 账号不支持 Token 刷新将被跳过，确认刷新 ${outlookCount} 个 Outlook 账号？`;
            } else {
                confirmMsg = `确认刷新选中的 ${accountIds.length} 个账号的 Token？`;
            }

            if (!confirm(confirmMsg)) {
                return;
            }

            await batchRefreshSelected(accountIds);
        }

        // 执行指定账号批量刷新 Token（SSE 流式）
        async function batchRefreshSelected(accountIds) {
            await initCSRFToken();

            // 显示常驻进度 Toast
            const toastId = 'batch-refresh-toast-' + Date.now();
            showPersistentToast(toastId, `🔄 正在刷新 Token... 0 / ${accountIds.length}`);

            try {
                const response = await fetch('/api/accounts/refresh/selected', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ account_ids: accountIds })
                });

                if (!response.ok || !response.body) {
                    dismissPersistentToast(toastId);
                    showToast('刷新请求失败，请稍后重试', 'error');
                    return;
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let totalCount = accountIds.length;

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop(); // 保留未完整的行

                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue;
                        let data;
                        try {
                            data = JSON.parse(line.slice(6));
                        } catch (e) {
                            continue;
                        }

                        handleBatchRefreshSSEEvent(data, toastId, totalCount);

                        if (data.type === 'start') {
                            totalCount = data.total;
                        }
                        if (data.type === 'complete' || data.type === 'error') {
                            break;
                        }
                    }
                }
            } catch (error) {
                dismissPersistentToast(toastId);
                showToast('刷新执行出现错误，请稍后重试', 'error');
                console.error('batchRefreshSelected error:', error);
            }
        }

        function buildSelectedRefreshActionGuide(errorPayload) {
            const lang = getUiLanguage();
            const code = String(errorPayload && errorPayload.code || '').trim();
            const traceId = String(errorPayload && errorPayload.trace_id || '').trim();
            const details = errorPayload && errorPayload.details;
            const detailText = typeof details === 'string'
                ? details
                : (details ? JSON.stringify(details) : '');

            if (code === 'REFRESH_CONFLICT') {
                if (lang === 'en') {
                    return [
                        'Another refresh task is running. Wait for it to finish before retrying.',
                        'Go to refresh logs and verify the current task has completed.',
                        traceId ? `If it keeps happening, share Trace ID: ${traceId}` : 'If it keeps happening, capture and share the Trace ID.',
                    ];
                }
                return [
                    '当前已有刷新任务在执行，请等待其完成后再重试。',
                    '先到刷新历史确认当前任务已结束。',
                    traceId ? `若持续出现，请反馈 Trace ID：${traceId}` : '若持续出现，请记录并反馈 Trace ID。',
                ];
            }

            if (code === 'REFRESH_SELECTED_STREAM_FAILED') {
                if (lang === 'en') {
                    return [
                        'Recheck selected accounts (status, account type, and authorization fields).',
                        'Verify network/proxy connectivity and retry selected refresh.',
                        traceId ? `If retry fails, share Trace ID: ${traceId}` : 'If retry fails, capture and share the Trace ID.',
                    ];
                }
                return [
                    '请先检查所选账号状态、账号类型与授权字段是否完整。',
                    '请检查网络/代理连通性后重新执行“Selected 刷新”。',
                    traceId ? `若重试仍失败，请反馈 Trace ID：${traceId}` : '若重试仍失败，请记录并反馈 Trace ID。',
                ];
            }

            if (/token|refresh|aadsts|invalid_grant|proxy|timeout|network/i.test(detailText)) {
                if (lang === 'en') {
                    return [
                        'Re-authorize or refresh credentials for the affected account(s).',
                        'Check network/proxy settings and retry once.',
                        traceId ? `Still failing? Share Trace ID: ${traceId}` : 'Still failing? Capture and share the Trace ID.',
                    ];
                }
                return [
                    '请重新授权或更新异常账号的凭据。',
                    '请检查网络/代理配置后重试一次。',
                    traceId ? `仍失败请反馈 Trace ID：${traceId}` : '仍失败请记录并反馈 Trace ID。',
                ];
            }

            return lang === 'en'
                ? [
                    'Retry the selected refresh once after reloading the page.',
                    'If the same error repeats, open error details and keep the Trace ID.',
                    traceId ? `Current Trace ID: ${traceId}` : 'Keep the Trace ID from error details for backend troubleshooting.',
                ]
                : [
                    '请刷新页面后重试一次“Selected 刷新”。',
                    '若同样错误再次出现，请打开详情并保留 Trace ID。',
                    traceId ? `当前 Trace ID：${traceId}` : '请保留错误详情中的 Trace ID 供后端排查。',
                ];
        }

        function buildSelectedRefreshErrorSummary(errorPayload) {
            const code = String(errorPayload && errorPayload.code || '').trim();
            const rawMessage = window.resolveApiErrorMessage
                ? window.resolveApiErrorMessage(errorPayload, '刷新执行失败', 'Refresh failed')
                : ((errorPayload && (errorPayload.message || errorPayload.message_en)) || '刷新执行失败');
            const guide = buildSelectedRefreshActionGuide(errorPayload);
            const guideText = guide.map((item, idx) => `${idx + 1}. ${item}`).join('\n');
            const codeLine = code ? `\n[Code] ${code}` : '';
            return `${rawMessage}${codeLine}\n\n建议处理：\n${guideText}`;
        }

        // 处理批量刷新 SSE 事件
        function handleBatchRefreshSSEEvent(data, toastId, totalCount) {
            if (data.type === 'start') {
                const total = data.total;
                updatePersistentToast(toastId, `🔄 正在刷新 Token... 0 / ${total}`);

            } else if (data.type === 'progress') {
                if (data.result === 'processing') {
                    // 刚开始处理该账号
                    updatePersistentToast(toastId, `🔄 正在刷新 Token... ${data.current - 1} / ${data.total}`);
                } else {
                    // 该账号刷新完成（success 或 failed）
                    updatePersistentToast(toastId, `🔄 正在刷新 Token... ${data.current} / ${data.total}`);
                    // 更新对应账号卡片状态
                    if (data.account_id) {
                        updateAccountCardRefreshStatus(data.account_id, data.result, data.last_refresh_at, data.error_message);
                    }
                }

            } else if (data.type === 'complete') {
                const { total, success_count, failed_count, failed_list } = data;
                dismissPersistentToast(toastId);

                if (failed_count === 0) {
                    showToast(`✅ Token 刷新完成：成功 ${success_count} 个`, 'success');
                } else {
                    let detail = null;
                    if (failed_list && failed_list.length > 0) {
                        detail = '失败账号：\n' + failed_list.map(f => `${f.email}：${f.error || '未知错误'}`).join('\n');
                    }
                    showToast(`⚠️ Token 刷新完成：成功 ${success_count} 个，失败 ${failed_count} 个`, 'warning', detail, true);
                }

                // 刷新账号列表以同步状态
                if (currentGroupId) {
                    loadAccountsByGroup(currentGroupId, true);
                }

            } else if (data.type === 'error') {
                dismissPersistentToast(toastId);
                const errCode = data.error && data.error.code;
                if (errCode === 'REFRESH_CONFLICT') {
                    showToast(buildSelectedRefreshErrorSummary(data.error), 'warning', data.error || null, true);
                } else {
                    showToast(buildSelectedRefreshErrorSummary(data.error || {}), 'error', data.error || null, true);
                }
            }
        }

        // 更新账号卡片的刷新状态显示
        function updateAccountCardRefreshStatus(accountId, result, lastRefreshAt, errorMessage) {
            // 标准视图：查找 data-account-id 匹配的卡片
            const cards = document.querySelectorAll(`[data-account-id="${accountId}"]`);
            cards.forEach(card => {
                // 更新刷新状态徽章（如果存在）
                const refreshBadge = card.querySelector('.refresh-status-badge, [data-refresh-status]');
                if (refreshBadge) {
                    refreshBadge.textContent = result === 'success' ? '✅' : '❌';
                    refreshBadge.title = result === 'success' ? '刷新成功' : (errorMessage || '刷新失败');
                }
                // 更新最后刷新时间（如果存在）
                if (lastRefreshAt) {
                    const timeEl = card.querySelector('[data-refresh-time], .last-refresh-at');
                    if (timeEl) {
                        timeEl.textContent = formatUiRelativeTime(lastRefreshAt, '刚刚', 'Just now');
                        timeEl.title = lastRefreshAt;
                    }
                }
            });
        }

        // 显示持久 Toast（用于进度展示）
        function showPersistentToast(id, message) {
            // 先清除同 id 的旧 toast
            dismissPersistentToast(id);
            showToast(message, 'info', null, true);
            // 给最后一个 toast 打上 id 标记
            const toasts = document.querySelectorAll('.toast');
            if (toasts.length > 0) {
                toasts[toasts.length - 1].dataset.persistentId = id;
            }
        }

        // 更新持久 Toast 内容
        function updatePersistentToast(id, message) {
            const toast = document.querySelector(`.toast[data-persistent-id="${id}"]`);
            if (toast) {
                const msgEl = toast.querySelector('span') || toast;
                msgEl.textContent = message;
            } else {
                // 如果 toast 已被用户关闭，重新显示
                showPersistentToast(id, message);
            }
        }

        // 关闭持久 Toast
        function dismissPersistentToast(id) {
            const toast = document.querySelector(`.toast[data-persistent-id="${id}"]`);
            if (toast) {
                toast.remove();
            }
        }

        // 显示批量删除确认
        function showBatchDeleteConfirm() {
            if (selectedAccountIds.size === 0) {
                showToast(translateAppTextLocal('请选择要删除的账号'), 'error');
                return;
            }

            if (!confirm(`确定要删除选中的 ${selectedAccountIds.size} 个账号吗？此操作不可恢复！`)) {
                return;
            }

            batchDeleteAccounts();
        }

        // 批量删除账号
        async function batchDeleteAccounts() {
            const accountIds = Array.from(selectedAccountIds);

            // 确保使用最新的 CSRF token
            await initCSRFToken();

            try {
                const response = await fetch('/api/accounts/batch-delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ account_ids: accountIds })
                });

                const data = await response.json();
                if (data.success) {
                    showToast(pickApiMessage(data, data.message, 'Accounts deleted successfully'), 'success');
                    // 清空选中状态
                    selectedAccountIds.clear();
                    // 刷新分组和邮箱列表
                    loadGroups();
                    if (currentGroupId) {
                        delete accountsCache[currentGroupId];
                        loadAccountsByGroup(currentGroupId, true);
                    }
                    // 更新批量操作栏
                    updateBatchActionBar();
                } else {
                    handleApiError(data, '删除失败');
                }
            } catch (error) {
                showToast(translateAppTextLocal('删除失败'), 'error');
            }
        }

        let batchActionType = ''; // 'add' or 'remove'
        let batchTagContext = { scopedAccountIds: null };

        // 显示批量打标模态框
        async function showBatchTagModal(type, options = {}) {
            batchActionType = type;
            batchTagContext = {
                scopedAccountIds: Array.isArray(options.scopedAccountIds) && options.scopedAccountIds.length > 0
                    ? [...options.scopedAccountIds]
                    : null
            };
            document.getElementById('batchTagTitle').textContent = translateAppTextLocal(type === 'add' ? '批量添加标签' : '批量移除标签');
            document.getElementById('batchTagModal').classList.add('show');

            // 加载标签选项
            await loadTagsForSelect();
        }

        function hideBatchTagModal() {
            document.getElementById('batchTagModal').classList.remove('show');
            batchTagContext = { scopedAccountIds: null };
        }

        // 加载标签到下拉框
        async function loadTagsForSelect() {
            const select = document.getElementById('batchTagSelect');
            select.innerHTML = `<option value="">${translateAppTextLocal('加载中...')}</option>`;

            try {
                const response = await fetch('/api/tags');
                const data = await response.json();
                if (data.success) {
                    let html = `<option value="">${translateAppTextLocal('请选择标签...')}</option>`;
                    data.tags.forEach(tag => {
                        html += `<option value="${tag.id}">${escapeHtml(tag.name)}</option>`;
                    });
                    select.innerHTML = html;
                }
            } catch (error) {
                select.innerHTML = `<option value="">${translateAppTextLocal('加载失败')}</option>`;
            }
        }

        // 确认批量打标
        async function confirmBatchTag() {
            const tagId = document.getElementById('batchTagSelect').value;
            if (!tagId) {
                showToast(translateAppTextLocal('请选择标签'), 'error');
                return;
            }

            const accountIds = batchTagContext.scopedAccountIds ? [...batchTagContext.scopedAccountIds] : Array.from(selectedAccountIds);

            if (accountIds.length === 0) return;

            try {
                const hasScopedAccountIds = Boolean(batchTagContext.scopedAccountIds);
                const response = await fetch('/api/accounts/tags', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        account_ids: accountIds,
                        tag_id: parseInt(tagId),
                        action: batchActionType
                    })
                });

                const data = await response.json();
                if (data.success) {
                    showToast(pickApiMessage(data, data.message, 'Tag update completed'), 'success');
                    hideBatchTagModal();
                    if (!hasScopedAccountIds) {
                        selectedAccountIds.clear();
                    }
                    // 刷新列表
                    loadGroups();
                    if (currentGroupId) {
                        delete accountsCache[currentGroupId];
                        loadAccountsByGroup(currentGroupId, true);
                    }
                    updateBatchActionBar();
                } else {
                    handleApiError(data, '操作失败');
                }
            } catch (error) {
                showToast(translateAppTextLocal('请求失败'), 'error');
            }
        }

        // ==================== 批量移动分组 ====================

        // 显示批量移动分组模态框
        async function showBatchMoveGroupModal(options = {}) {
            batchMoveGroupContext = {
                scopedAccountIds: Array.isArray(options.scopedAccountIds) && options.scopedAccountIds.length > 0
                    ? [...options.scopedAccountIds]
                    : null
            };
            document.getElementById('batchMoveGroupModal').classList.add('show');
            await loadGroupsForBatchMove();
        }

        function hideBatchMoveGroupModal() {
            document.getElementById('batchMoveGroupModal').classList.remove('show');
            batchMoveGroupContext = { scopedAccountIds: null };
        }

        // 加载分组到下拉框
        async function loadGroupsForBatchMove() {
            const select = document.getElementById('batchMoveGroupSelect');
            select.innerHTML = `<option value="">${translateAppTextLocal('加载中...')}</option>`;

            try {
                const response = await fetch('/api/groups');
                const data = await response.json();
                if (data.success) {
                    let html = `<option value="">${translateAppTextLocal('请选择分组...')}</option>`;
                    data.groups.filter(g => !g.is_system).forEach(group => {
                        html += `<option value="${group.id}">${escapeHtml(group.name)}</option>`;
                    });
                    select.innerHTML = html;
                }
            } catch (error) {
                select.innerHTML = `<option value="">${translateAppTextLocal('加载失败')}</option>`;
            }
        }

        // 确认批量移动分组
        async function confirmBatchMoveGroup() {
            const groupId = document.getElementById('batchMoveGroupSelect').value;
            if (!groupId) {
                showToast(translateAppTextLocal('请选择目标分组'), 'error');
                return;
            }

            const accountIds = batchMoveGroupContext.scopedAccountIds
                ? [...batchMoveGroupContext.scopedAccountIds]
                : Array.from(selectedAccountIds);

            if (accountIds.length === 0) return;

            try {
                const hasScopedAccountIds = Boolean(batchMoveGroupContext.scopedAccountIds);
                const response = await fetch('/api/accounts/batch-update-group', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        account_ids: accountIds,
                        group_id: parseInt(groupId)
                    })
                });

                const data = await response.json();
                if (data.success) {
                    showToast(pickApiMessage(data, data.message, 'Accounts moved successfully'), 'success');
                    hideBatchMoveGroupModal();
                    if (!hasScopedAccountIds) {
                        selectedAccountIds.clear();
                    }
                    // 刷新分组列表
                    loadGroups();
                    // 刷新当前分组的邮箱列表
                    if (currentGroupId) {
                        delete accountsCache[currentGroupId];
                        loadAccountsByGroup(currentGroupId, true);
                    }
                    updateBatchActionBar();
                } else {
                    handleApiError(data, '操作失败');
                }
            } catch (error) {
                showToast(translateAppTextLocal('请求失败'), 'error');
            }
        }

        // ==================== 版本更新检测 ====================

        function getCSRFToken() {
            const meta = document.querySelector('meta[name="csrf-token"]');
            return meta ? meta.getAttribute('content') : '';
        }

        /**
         * 页面加载时调用一次，检查是否有可用更新
         */
        async function checkVersionUpdate() {
            try {
                const res = await fetch('/api/system/version-check');
                if (!res.ok) return;
                const data = await res.json();
                if (data.has_update) {
                    const banner = document.getElementById('versionUpdateBanner');
                    const msg = document.getElementById('versionUpdateMsg');
                    if (!banner || !msg) return;
                    msg.innerHTML = `发现新版本 <strong>v${data.latest_version}</strong>（当前 v${data.current_version}）
                        <a href="${data.release_url}" target="_blank" class="ms-1">查看更新日志</a>`;
                    banner.classList.remove('d-none');
                    document.getElementById('app').style.paddingTop = banner.offsetHeight + 'px';
                }
            } catch (e) {
                // 静默失败
            }
        }

        function dismissVersionBanner() {
            document.getElementById('versionUpdateBanner').classList.add('d-none');
            document.getElementById('app').style.paddingTop = '';
        }

        /**
         * 用户点击"立即更新"时触发
         */
        async function triggerUpdate() {
            const btn = document.getElementById('btnTriggerUpdate');
            btn.disabled = true;
            btn.textContent = translateAppTextLocal('正在触发更新...');

            // 获取更新方式（从设置中读取或默认为 watchtower）
            let updateMethod = 'watchtower';
            try {
                const settingsRes = await fetch('/api/settings');
                const settingsData = await settingsRes.json();
                if (settingsData.success && settingsData.settings) {
                    updateMethod = settingsData.settings.update_method || 'watchtower';
                }
            } catch (e) {
                console.warn('Failed to load update method, using default (watchtower):', e);
            }

            try {
                // 根据更新方式决定 timeout 和 URL
                const timeout = updateMethod === 'docker_api' ? 120000 : 60000;  // Docker API 模式 120s, Watchtower 模式 60s
                const url = `/api/system/trigger-update?method=${updateMethod}`;
                
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), timeout);
                
                const res = await fetch(url, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': getCSRFToken() },
                    signal: controller.signal
                });
                clearTimeout(timeoutId);
                
                const data = await res.json();
                if (data.success) {
                    // 镜像已是最新，无需等待重启
                    if (data.already_latest) {
                        showToast(translateAppTextLocal('当前已是最新版本，无需更新'), 'info', 5000);
                        btn.disabled = false;
                        btn.textContent = translateAppTextLocal('立即更新');
                        return;
                    }

                    // 记录本次更新方式，供 waitForRestart 调整等待时长
                    try {
                        window.__lastUpdateMethod = updateMethod;
                    } catch (e) {}

                    // Docker API 与 Watchtower 都可能触发容器重启：统一走“等待恢复”逻辑
                    btn.textContent = translateAppTextLocal('等待容器重启...');
                    if (updateMethod === 'docker_api') {
                        showToast(translateAppTextLocal('Docker API 更新已启动，等待容器重启...'), 'info', 5000);
                    }
                    await waitForRestart();
                } else {
                    const msg = data.message || '未知错误';
                    // 区分常见错误场景，给出友好提示
                    if (updateMethod === 'docker_api') {
                        if (msg.includes('未启用') || msg.includes('DOCKER_SELF_UPDATE_ALLOW')) {
                            showToast(translateAppTextLocal('Docker API 自更新功能未启用。请在 .env 中设置 DOCKER_SELF_UPDATE_ALLOW=true，并在 docker-compose.yml 中挂载 docker.sock'), 'warning', 10000);
                        } else if (msg.includes('docker.sock') || msg.includes('无法连接')) {
                            showToast(translateAppTextLocal('无法访问 Docker API。请确认已在 docker-compose.yml 中挂载 /var/run/docker.sock'), 'warning', 8000);
                        } else {
                            showToast(translateAppTextLocal('Docker API 更新失败：') + msg, 'error', 8000);
                        }
                    } else {
                        if (msg.includes('WATCHTOWER_HTTP_API_TOKEN') || (msg.includes('未配置') && res.status === 500)) {
                            showToast(translateAppTextLocal('一键更新需要配置 Watchtower 服务（仅 Docker 部署支持）。请在 .env 中设置 WATCHTOWER_HTTP_API_TOKEN，并使用含 Watchtower 的 docker-compose 部署方式'), 'warning', 10000);
                        } else if (msg.includes('无法连接') || msg.includes('Watchtower')) {
                            showToast(translateAppTextLocal('无法连接 Watchtower 服务，请确认已使用 docker-compose 方式部署，且 watchtower 容器正常运行'), 'warning', 8000);
                        } else {
                            showToast(translateAppTextLocal('更新失败：') + msg, 'error');
                        }
                    }
                    btn.disabled = false;
                    btn.textContent = translateAppTextLocal('立即更新');
                }
            } catch (e) {
                if (e.name === 'AbortError') {
                    showToast(translateAppTextLocal('更新请求超时，请检查配置和网络连接'), 'error', 8000);
                } else {
                    showToast(translateAppTextLocal('更新请求失败，请检查网络连接'), 'error');
                }
                btn.disabled = false;
                btn.textContent = translateAppTextLocal('立即更新');
            }
        }

        /**
         * 轮询 /healthz 等待容器重启后恢复
         * - 立即开始轮询，每 3 秒一次
         * - 最长等待 90 秒，超时提示用户手动检查
         * - 检测到服务恢复后刷新页面
         */
        async function waitForRestart() {
            // 默认 90 秒（Watchtower 通常更快）；Docker API 更新可能涉及 pull 镜像，适当放宽
            const WATCHTOWER_MAX_WAIT_MS = 90000;  // 90 秒
            const DOCKER_API_MAX_WAIT_MS = 180000;  // 180 秒
            const POLL_INTERVAL_MS = 3000;  // 每 3 秒

            let MAX_WAIT_MS = WATCHTOWER_MAX_WAIT_MS;
            try {
                const method = (window.__lastUpdateMethod || 'watchtower');
                if (method === 'docker_api') {
                    MAX_WAIT_MS = DOCKER_API_MAX_WAIT_MS;
                }
            } catch (e) {
                MAX_WAIT_MS = WATCHTOWER_MAX_WAIT_MS;
            }
            const startAt = Date.now();
            let seenDown = false;
            let initialBootId = null;

            // 先读取一次 boot_id，用于判断是否发生“新进程启动”
            try {
                const firstRes = await fetch('/healthz', { cache: 'no-store' });
                if (firstRes.ok) {
                    const firstData = await firstRes.json();
                    if (firstData && firstData.boot_id) {
                        initialBootId = String(firstData.boot_id);
                    }
                }
            } catch (e) {
                // ignore
            }

            while (Date.now() - startAt < MAX_WAIT_MS) {
                await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL_MS));
                try {
                    const res = await fetch('/healthz', { cache: 'no-store' });
                    if (res.ok) {
                        let bootIdChanged = false;
                        try {
                            const d = await res.json();
                            const bootId = d && d.boot_id ? String(d.boot_id) : null;
                            if (bootId && initialBootId && bootId !== initialBootId) {
                                bootIdChanged = true;
                            }
                        } catch (e) {
                            // ignore json parse
                        }

                        // 以“boot_id 变化”作为更可靠的重启完成信号
                        if (bootIdChanged || seenDown) {
                            showToast(translateAppTextLocal('更新完成，正在刷新页面...'), 'success');
                            setTimeout(() => location.reload(), 1500);
                            return;
                        }
                        // 还没看到重启迹象：可能仍在 pull/重建中，继续等
                    } else {
                        seenDown = true;
                    }
                } catch (e) {
                    // 请求失败通常意味着容器正在重启/网络暂不可用
                    seenDown = true;
                }
            }

            // 超时处理
            try {
                const method = (window.__lastUpdateMethod || 'watchtower');
                if (method === 'docker_api') {
                    if (!seenDown) {
                        showToast(translateAppTextLocal('等待超时：容器未发生重启，可能已是最新版本或更新仍在后台进行'), 'warning', 9000);
                    } else {
                        showToast(translateAppTextLocal('等待超时：容器尚未恢复，请检查容器状态/日志'), 'warning', 9000);
                    }
                } else {
                    if (!seenDown) {
                        showToast(translateAppTextLocal('等待超时：容器未发生重启，请检查 Watchtower 配置/日志'), 'warning', 9000);
                    } else {
                        showToast(translateAppTextLocal('更新超时，请手动检查容器状态'), 'warning', 8000);
                    }
                }
            } catch (e) {
                showToast(translateAppTextLocal('更新超时，请手动检查容器状态'), 'warning', 8000);
            }
            const btn = document.getElementById('btnTriggerUpdate');
            if (btn) {
                btn.disabled = false;
                btn.textContent = translateAppTextLocal('立即更新');
            }
        }

        /**
         * 设置面板中的"手动触发更新"按钮回调
         * 与 triggerUpdate() 类似，但 UI 反馈在设置面板内
         */
        async function manualTriggerUpdate() {
            const btn = document.getElementById('btnManualTriggerUpdate');
            const resultDiv = document.getElementById('manualUpdateResult');
            if (!btn) return;

            btn.disabled = true;
            btn.textContent = translateAppTextLocal('正在触发更新...');
            if (resultDiv) {
                resultDiv.style.display = 'none';
                resultDiv.innerHTML = '';
            }

            // 读取当前选择的更新方式
            const selectedRadio = document.querySelector('input[name="updateMethod"]:checked');
            const updateMethod = selectedRadio ? selectedRadio.value : 'watchtower';

            try {
                const timeout = updateMethod === 'docker_api' ? 120000 : 60000;
                const url = `/api/system/trigger-update?method=${updateMethod}`;

                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), timeout);

                const res = await fetch(url, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': getCSRFToken() },
                    signal: controller.signal
                });
                clearTimeout(timeoutId);

                const data = await res.json();
                if (data.success) {
                    if (resultDiv) {
                        resultDiv.style.display = 'block';
                        const msg = pickApiMessage(data, '更新已触发', 'Update triggered');
                        resultDiv.innerHTML = `<span style="color: var(--clr-success, #28a745);">✅ ${escapeHtml(msg)}</span>`;
                    }
                    // 镜像已是最新，无需等待重启
                    if (data.already_latest) {
                        showToast(pickApiMessage(data, '当前已是最新版本', 'Already up to date'), 'info', 5000);
                        btn.disabled = false;
                        btn.textContent = translateAppTextLocal('立即更新');
                        return;
                    }
                    window.__lastUpdateMethod = updateMethod;
                    btn.textContent = translateAppTextLocal('等待容器重启...');
                    await waitForRestart();
                } else {
                    const msg = data.message || '未知错误';
                    const detail = data.detail ? `\n详情: ${data.detail}` : '';
                    if (resultDiv) {
                        resultDiv.style.display = 'block';
                        resultDiv.innerHTML = `<span style="color: var(--clr-danger, #dc3545);">❌ ${escapeHtml(msg)}</span>${detail ? '<br><small style="color: var(--text-muted);">' + escapeHtml(detail.trim()) + '</small>' : ''}`;
                    }
                    showToast(translateAppTextLocal('更新失败：') + msg, 'error', 8000);
                    btn.disabled = false;
                    btn.textContent = translateAppTextLocal('立即更新');
                }
            } catch (e) {
                const errMsg = e.name === 'AbortError' ? translateAppTextLocal('请求超时') : (e.message || translateAppTextLocal('网络错误'));
                if (resultDiv) {
                    resultDiv.style.display = 'block';
                    resultDiv.innerHTML = `<span style="color: var(--clr-danger, #dc3545);">❌ ${escapeHtml(errMsg)}</span>`;
                }
                showToast(translateAppTextLocal('更新请求失败：') + errMsg, 'error', 8000);
                btn.disabled = false;
                btn.textContent = translateAppTextLocal('立即更新');
            }
        }
