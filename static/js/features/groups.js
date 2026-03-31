        // ==================== 分组相关 ====================

        // 加载分组列表
        async function loadGroups() {
            const container = document.getElementById('groupList');
            container.innerHTML = `<div class="loading-overlay"><span class="spinner"></span> ${translateAppTextLocal('加载中…')}</div>`;

            try {
                const response = await fetch('/api/groups');
                const data = await response.json();

                if (data.success) {
                    groups = data.groups;

                    // 找到临时邮箱分组
                    const tempGroup = groups.find(g => g.name === '临时邮箱');
                    if (tempGroup) {
                        tempEmailGroupId = tempGroup.id;
                    }

                    renderGroupList(data.groups);
                    if (typeof renderCompactGroupStrip === 'function') {
                        renderCompactGroupStrip(data.groups, currentGroupId);
                    }
                    updateGroupSelects();

                    // 如果之前选中了分组，保持选中状态并刷新邮箱列表
                    if (currentGroupId) {
                        const group = groups.find(g => g.id === currentGroupId);
                        if (group) {
                            // 刷新当前分组的邮箱列表
                            if (currentGroupId === tempEmailGroupId) {
                                loadTempEmails(true);
                            } else {
                                loadAccountsByGroup(currentGroupId, true);
                            }
                        }
                    } else {
                        // 首次进入：自动选中第一个非临时邮箱分组
                        const firstNormalGroup = groups.find(g => !isTempMailboxGroup(g));
                        if (firstNormalGroup) {
                            selectGroup(firstNormalGroup.id);
                        }
                    }
                }
            } catch (error) {
                container.innerHTML = `<div class="empty-state"><p>${translateAppTextLocal('加载失败')}</p></div>`;
                showToast(translateAppTextLocal('加载分组失败'), 'error');
            }
        }

        // 渲染分组列表
        function renderGroupList(groups) {
            const container = document.getElementById('groupList');

            // 过滤掉临时邮箱分组（已有独立页面管理）
            const filteredGroups = groups.filter(g => !isTempMailboxGroup(g));

            if (filteredGroups.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <span class="empty-icon">📁</span>
                        <p>${translateAppTextLocal('暂无分组')}</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = filteredGroups.map(group => {
                const isSystem = group.is_system === 1;
                const isDefault = group.id === 1;

                return `
                    <div class="group-item ${currentGroupId === group.id ? 'active' : ''}"
                         data-group-id="${group.id}"
                         onclick="selectGroup(${group.id})">
                        <span class="group-color-dot" style="background-color: ${group.color || '#666'}"></span>
                        <span class="group-name">${escapeHtml(group.name)}</span>
                        <span class="badge-count">${group.account_count || 0}</span>
                        <div class="group-actions">
                            ${!isSystem ? `<button class="btn-icon" onclick="event.stopPropagation(); editGroup(${group.id})" title="编辑">✏️</button>` : ''}
                            ${!isDefault && !isSystem ? `<button class="btn-icon" onclick="event.stopPropagation(); deleteGroup(${group.id})" title="删除">🗑️</button>` : ''}
                        </div>
                    </div>
                `;
            }).join('');
        }

        // 选择分组
        async function selectGroup(groupId) {
            currentGroupId = groupId;
            currentAccountPage = 1;  // 切换分组时重置到第 1 页

            // 切换分组时停止所有正在运行的轮询（避免跨分组轮询堆积）
            if (typeof stopAllPolls === 'function') {
                stopAllPolls();
            }

            // 清空搜索框
            const searchInput = document.getElementById('globalSearch');
            if (searchInput) {
                searchInput.value = '';
            }

            // 重置右侧邮件列 UI（清除上一个分组的残留状态）
            currentAccount = null;
            const accountBar = document.getElementById('currentAccountBar');
            if (accountBar) accountBar.style.display = 'none';
            const emailListEl = document.getElementById('emailList');
            if (emailListEl) emailListEl.innerHTML = '<div class="empty-state"><span class="empty-icon">📬</span><p>请从左侧选择一个邮箱账号</p></div>';
            const detailSection = document.getElementById('emailDetailSection');
            if (detailSection) detailSection.style.display = 'none';
            const folderTabs = document.getElementById('folderTabs');
            if (folderTabs) folderTabs.style.display = 'none';
            const emailCount = document.getElementById('emailCount');
            if (emailCount) emailCount.textContent = '';
            const methodTag = document.getElementById('methodTag');
            if (methodTag) methodTag.style.display = 'none';

            // 检查是否是临时邮箱分组
            const group = groups.find(g => g.id === groupId);
            isTempEmailGroup = Boolean(group && isTempMailboxGroup(group));

            // 更新分组列表 UI
            document.querySelectorAll('.group-item').forEach(item => {
                item.classList.toggle('active', parseInt(item.dataset.groupId) === groupId);
            });
            if (typeof renderCompactGroupStrip === 'function') {
                renderCompactGroupStrip(groups, groupId);
            }

            // 更新邮箱面板标题
            if (group) {
                document.getElementById('currentGroupName').textContent = formatGroupDisplayName(group.name);
                document.getElementById('currentGroupColor').style.backgroundColor = group.color || '#666';

                // 更新导入邮箱时的默认分组
                const importSelect = document.getElementById('importGroupSelect');
                if (importSelect) {
                    importSelect.value = groupId;
                }
            }

            // 显示「注册Outlook账号」按钮（仅在非临时邮箱分组时）
            const registerBtn = document.getElementById('registerOutlookBtn');
            if (registerBtn) {
                registerBtn.style.display = isTempEmailGroup ? 'none' : '';
            }

            // 更新底部按钮
            updateAccountPanelFooter();

            // 加载该分组的邮箱
            if (isTempEmailGroup) {
                // 临时邮箱已有独立页面，跳转到专属页面管理
                navigate('temp-emails');
                return;
            } else {
                await loadAccountsByGroup(groupId);
            }
        }

        // 更新账号面板底部按钮（新布局无独立footer，通过topbar按钮实现）
        function updateAccountPanelFooter() {
            // No-op: new layout uses topbar action buttons instead
        }

        // 加载分组下的账号
        async function loadAccountsByGroup(groupId, forceRefresh = false) {
            const container = document.getElementById('accountList');

            // 保存当前滚动位置（forceRefresh 时恢复）
            const savedScrollTop = forceRefresh ? container.scrollTop : 0;

            // 如果有缓存且不强制刷新，直接使用缓存
            if (!forceRefresh && accountsCache[groupId]) {
                renderAccountList(accountsCache[groupId]);
                if (typeof renderCompactAccountList === 'function') {
                    renderCompactAccountList(accountsCache[groupId]);
                }
                // 标准模式：为缓存中的所有账号启动轮询（跳过已在轮询中的）
                var viewC = typeof mailboxViewMode !== 'undefined' ? mailboxViewMode : 'standard';
                if (viewC !== 'compact' && typeof pollEnabled !== 'undefined' && pollEnabled && typeof startPoll === 'function') {
                    var pollCount = 0;
                    var hasPollMap = typeof pollMap !== 'undefined';
                    (accountsCache[groupId] || []).forEach(function(acc) {
                        if (acc && acc.email && !(hasPollMap && pollMap.has(acc.email))) {
                            startPoll(acc.email, { silent: true }); pollCount++;
                        }
                    });
                    if (pollCount > 0 && typeof showToast === 'function') {
                        showToast(translateAppTextLocal('已为 ' + pollCount + ' 个账号启动轮询监听'), 'info');
                    }
                }
                return;
            }

            // forceRefresh 时不显示 loading（保持旧内容，静默刷新）
            if (!forceRefresh) {
                container.innerHTML = `<div class="loading-overlay"><span class="spinner"></span> ${translateAppTextLocal('加载中…')}</div>`;
                if (typeof renderCompactLoadingState === 'function') {
                    renderCompactLoadingState(translateAppTextLocal('加载中…'));
                }
            }

            try {
                const response = await fetch(`/api/accounts?group_id=${groupId}`);
                const data = await response.json();

                if (data.success) {
                    // 缓存数据
                    accountsCache[groupId] = data.accounts;
                    renderAccountList(data.accounts);
                    if (typeof renderCompactAccountList === 'function') {
                        renderCompactAccountList(data.accounts);
                    }
                    // 恢复滚动位置
                    if (forceRefresh) {
                        requestAnimationFrame(() => { container.scrollTop = savedScrollTop; });
                    }
                    // 标准模式：加载分组后，为所有账号启动轮询（跳过已在轮询中的）
                    var view = typeof mailboxViewMode !== 'undefined' ? mailboxViewMode : 'standard';
                    if (view !== 'compact' && typeof pollEnabled !== 'undefined' && pollEnabled && typeof startPoll === 'function') {
                        var pollCount2 = 0;
                        var hasPollMap2 = typeof pollMap !== 'undefined';
                        (data.accounts || []).forEach(function(acc) {
                            if (acc && acc.email && !(hasPollMap2 && pollMap.has(acc.email))) {
                                startPoll(acc.email, { silent: true }); pollCount2++;
                            }
                        });
                        if (pollCount2 > 0 && typeof showToast === 'function') {
                            showToast(translateAppTextLocal('已为 ' + pollCount2 + ' 个账号启动轮询监听'), 'info');
                        }
                    }
                }
            } catch (error) {
                container.innerHTML = `<div class="empty-state"><p>${translateAppTextLocal('加载失败')}</p></div>`;
                if (typeof renderCompactErrorState === 'function') {
                    renderCompactErrorState(translateAppTextLocal('加载失败'));
                }
            }
        }

        // 获取 provider 的中文展示名（账号卡片 tag）
        function getProviderLabel(provider) {
            const key = (provider || 'outlook').toString().toLowerCase();
            const labels = {
                outlook: 'Outlook',
                gmail: 'Gmail',
                qq: 'QQ 邮箱',
                '163': '163 邮箱',
                '126': '126 邮箱',
                yahoo: 'Yahoo 邮箱',
                aliyun: '阿里邮箱',
                custom: '自定义 IMAP'
            };
            return translateAppTextLocal(labels[key] || provider || '未知');
        }

        // 渲染邮箱列表
        function renderAccountList(accounts) {
            const container = document.getElementById('accountList');

            if (accounts.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <span class="empty-icon">📭</span>
                        <p>${translateAppTextLocal('该分组暂无邮箱')}</p>
                    </div>
                `;
                const selectAllCheckbox = document.getElementById('selectAllCheckbox');
                if (selectAllCheckbox) {
                    selectAllCheckbox.checked = false;
                    selectAllCheckbox.indeterminate = selectedAccountIds.size > 0;
                }
                updateBatchActionBar();
                return;
            }

            // ===== 分页计算 =====
            const totalAccounts = accounts.length;
            const totalPages = Math.ceil(totalAccounts / ACCOUNT_PAGE_SIZE);
            if (currentAccountPage > totalPages) currentAccountPage = totalPages;
            if (currentAccountPage < 1) currentAccountPage = 1;
            const startIdx = (currentAccountPage - 1) * ACCOUNT_PAGE_SIZE;
            // 只渲染当前页的账号，大幅减少 DOM 节点数
            const pageAccounts = accounts.slice(startIdx, startIdx + ACCOUNT_PAGE_SIZE);
            const avatarGradients = [
                ['#B85C38', '#E8734A'],  // 砖红→珊瑚
                ['#3A7D44', '#5BAF6A'],  // 翠绿→嫩绿
                ['#2E6B8A', '#4BA3CC'],  // 海蓝→天蓝
                ['#8B5E3C', '#C8963E'],  // 棕→琥珀金
                ['#7B4F9B', '#B77FD8'],  // 紫罗兰→薰衣草
                ['#C75050', '#E88080'],  // 朱红→浅红
                ['#2C7A7B', '#4DC9C9'],  // 青绿→薄荷
                ['#9B6B3E', '#D4A65A'],  // 赭石→沙金
            ];

            container.innerHTML = pageAccounts.map((acc, index) => {
                const isChecked = selectedAccountIds.has(acc.id);
                const initial = (acc.email || '?')[0].toUpperCase();
                const supportsTokenRefresh = isRefreshableOutlookAccount(acc);
                const isFailed = supportsTokenRefresh && acc.last_refresh_status === 'failed';
                const defaultMethodLabel = supportsTokenRefresh ? 'Graph' : 'IMAP';
                const gradient = avatarGradients[index % avatarGradients.length];
                const providerLabel = getProviderLabel(acc.provider || acc.account_type || 'outlook');
                const providerTagHtml = `<span class="account-provider-tag">${escapeHtml(providerLabel)}</span>`;
                const notificationEnabled = acc.notification_enabled !== undefined
                    ? !!acc.notification_enabled
                    : !!acc.telegram_push_enabled;

                let tokenBadge = `<span class="badge badge-gray">IMAP</span>`;
                if (supportsTokenRefresh) {
                    tokenBadge = `<span class="badge badge-gray">– ${translateAppTextLocal('未知')}</span>`;
                    if (acc.token_status === 'valid') {
                        tokenBadge = `<span class="badge badge-green">✓ ${translateAppTextLocal('有效')}</span>`;
                    } else if (acc.token_status === 'invalid' || acc.token_status === 'expired') {
                        tokenBadge = `<span class="badge badge-red">✗ ${translateAppTextLocal('过期')}</span>`;
                    } else if (acc.token_status === 'expiring') {
                        tokenBadge = `<span class="badge badge-gold">⚠ ${translateAppTextLocal('即将过期')}</span>`;
                    }
                }

                return `
                <div class="account-card ${currentAccount === acc.email ? 'active' : ''}"
                     onclick="selectAccount('${escapeJs(acc.email)}')">
                    <div class="account-token-badge">${tokenBadge}</div>
                    <div class="account-card-top">
                        <input type="checkbox" class="account-select-checkbox" value="${acc.id}"
                               ${isChecked ? 'checked' : ''}
                               onclick="event.stopPropagation()"
                               onchange="event.stopPropagation(); handleAccountSelectionChange(${acc.id}, this.checked)">
                        <div class="account-avatar" style="background: linear-gradient(135deg, ${gradient[0]}, ${gradient[1]})">${initial}</div>
                        <div class="account-info">
                            <div class="account-email"
                                 onclick="event.stopPropagation(); copyEmail('${escapeJs(acc.email)}')"
                                 title="${escapeHtml(translateAppTextLocal('点击复制邮箱地址'))}"
                                 style="${isFailed ? 'color:var(--clr-danger);' : ''}cursor:pointer;">
                                ${escapeHtml(acc.email)}
                            </div>
                            ${acc.remark && acc.remark.trim() ? `<div style="font-size:0.72rem;color:var(--text-muted);margin-top:2px;">📝 ${escapeHtml(translateAppTextLocal('备注'))}: ${escapeHtml(acc.remark)}</div>` : ''}
                            <div style="display:flex;flex-wrap:wrap;gap:3px;margin-top:3px;">
                                ${providerTagHtml}
                                ${(acc.tags || []).map(tag => `<span class="tag" style="background-color:${tag.color};color:white;">${escapeHtml(tag.name)}</span>`).join('')}
                                ${notificationEnabled ? `<span class="tag tg-push-tag" onclick="event.stopPropagation(); toggleTelegramPush(${acc.id}, false)" title="${escapeHtml(translateAppTextLocal('点击关闭该邮箱通知参与'))}">🔔 ${escapeHtml(translateAppTextLocal('通知'))}</span>` : ''}
                            </div>
                        </div>
                    </div>
                    <div class="account-card-bottom">
                        <div class="account-meta">
                            <span class="account-api-tag">${acc.method || defaultMethodLabel}</span>
                            <span>🕐 ${formatRelativeTime(acc.last_refresh_at)}</span>
                            ${isFailed ? `<button class="btn btn-sm btn-danger" onclick="event.stopPropagation(); showRefreshError(${acc.id}, '${escapeJs(acc.last_refresh_error || '未知错误')}', '${escapeJs(acc.email)}', '${escapeJs(acc.account_type || 'outlook')}', '${escapeJs(acc.provider || 'outlook')}')" style="padding:1px 6px;font-size:0.65rem;">${escapeHtml(translateAppTextLocal('查看错误'))}</button>` : ''}
                        </div>
                        <div class="account-actions">
                            <button class="btn-icon ${notificationEnabled ? 'tg-push-active' : ''}" onclick="event.stopPropagation(); toggleTelegramPush(${acc.id}, ${!notificationEnabled})" title="${escapeHtml(translateAppTextLocal(notificationEnabled ? '该邮箱通知参与（已开启）' : '开启该邮箱通知参与'))}">🔔</button>
                            <button class="btn btn-sm btn-accent" onclick="event.stopPropagation(); copyVerificationInfo('${escapeJs(acc.email)}', this)" title="${escapeHtml(translateAppTextLocal('验证码'))}" style="font-size:0.72rem;padding:2px 8px;">🔑 ${escapeHtml(translateAppTextLocal('验证码'))}</button>
                            <button class="btn-icon" onclick="event.stopPropagation(); copyEmail('${escapeJs(acc.email)}')" title="${escapeHtml(translateAppTextLocal('复制'))}">📋</button>
                            <button class="btn-icon" onclick="event.stopPropagation(); showEditAccountModal(${acc.id})" title="${escapeHtml(translateAppTextLocal('编辑'))}">✏️</button>
                            <button class="btn-icon" onclick="event.stopPropagation(); deleteAccount(${acc.id}, '${escapeJs(acc.email)}')" title="${escapeHtml(translateAppTextLocal('删除'))}" style="color:var(--clr-danger);">🗑️</button>
                        </div>
                    </div>
                </div>
            `}).join('');

            // ===== 分页控件：总账号数超过一页时显示 =====
            if (totalPages > 1) {
                const paginationEl = document.createElement('div');
                paginationEl.className = 'account-pagination';
                paginationEl.innerHTML = `
                    <button class="page-btn page-btn-prev"
                            onclick="goToAccountPage(${currentAccountPage - 1})"
                            ${currentAccountPage <= 1 ? 'disabled' : ''}>
                        ◀
                    </button>
                    <span class="page-info">
                        ${currentAccountPage} / ${totalPages} ${translateAppTextLocal('页')} &nbsp;·&nbsp; ${translateAppTextLocal('共')} ${totalAccounts} ${translateAppTextLocal('个账号')}
                    </span>
                    <button class="page-btn page-btn-next"
                            onclick="goToAccountPage(${currentAccountPage + 1})"
                            ${currentAccountPage >= totalPages ? 'disabled' : ''}>
                        ▶
                    </button>
                `;
                container.appendChild(paginationEl);
            }

            updateSelectAllCheckbox();
            updateBatchActionBar();
            // 如果有正在运行的轮询，重新显示轮询指示器（账号列表重渲染后会丢失绿点）
            if (typeof reapplyAllPollUI === 'function') {
                reapplyAllPollUI();
            }
        }

        // 跳转到指定账号分页
        function goToAccountPage(page) {
            if (!accountsCache[currentGroupId]) return;
            const accounts = applyFiltersAndSort(accountsCache[currentGroupId]);
            const totalPages = Math.ceil(accounts.length / ACCOUNT_PAGE_SIZE);
            if (page < 1 || page > totalPages) return;
            currentAccountPage = page;
            renderAccountList(accounts);
            // 滚动到账号列表顶部
            const container = document.getElementById('accountList');
            if (container) container.scrollTop = 0;
        }

        // 排序相关变量
        let currentSortBy = 'refresh_time';
        let currentSortOrder = 'asc';

        // 账号列表分页状态
        let currentAccountPage = 1;
        const ACCOUNT_PAGE_SIZE = 50;

        // 排序账号列表
        function sortAccounts(sortBy) {
            // 如果点击同一个排序按钮，切换排序顺序
            if (currentSortBy === sortBy) {
                currentSortOrder = currentSortOrder === 'asc' ? 'desc' : 'asc';
            } else {
                currentSortBy = sortBy;
                currentSortOrder = sortBy === 'refresh_time' ? 'asc' : 'asc';
            }

            // 更新按钮状态
            document.querySelectorAll('.sort-btn').forEach(btn => {
                btn.classList.remove('active');
            });

            const activeBtn = document.querySelector(`[data-sort="${sortBy}"]`);
            if (activeBtn) {
                activeBtn.classList.add('active');
            }

            // 重新加载并排序账号列表
            if (accountsCache[currentGroupId]) {
                currentAccountPage = 1;  // 排序时重置到第 1 页
                const sortedAccounts = applyFiltersAndSort(accountsCache[currentGroupId]);
                renderAccountList(sortedAccounts);
            }
        }

        // 应用筛选和排序
        function applyFiltersAndSort(accounts) {
            let result = [...accounts];

            // 1. Tag 筛选
            // Get checked tags
            const checkedBoxes = document.querySelectorAll('.tag-filter-checkbox:checked');
            const selectedTagIds = Array.from(checkedBoxes).map(cb => parseInt(cb.value));

            if (selectedTagIds.length > 0) {
                result = result.filter(acc => {
                    if (!acc.tags) return false;
                    // Check if account has ANY of the selected tags (OR logic)
                    // If you want AND logic, use every() instead of some()
                    return acc.tags.some(t => selectedTagIds.includes(t.id));
                });
            }

            // 2. 排序
            return result.sort((a, b) => {
                if (currentSortBy === 'refresh_time') {
                    const timeA = a.last_refresh_at ? new Date(a.last_refresh_at) : new Date(0);
                    const timeB = b.last_refresh_at ? new Date(b.last_refresh_at) : new Date(0);
                    return currentSortOrder === 'asc' ? timeA - timeB : timeB - timeA;
                } else {
                    const emailA = a.email.toLowerCase();
                    const emailB = b.email.toLowerCase();
                    return currentSortOrder === 'asc'
                        ? emailA.localeCompare(emailB)
                        : emailB.localeCompare(emailA);
                }
            });
        }

        // Tag Filter Change Handler
        function handleTagFilterChange() {
            if (accountsCache[currentGroupId]) {
                currentAccountPage = 1;  // 标签过滤时重置到第 1 页
                const filteredAccounts = applyFiltersAndSort(accountsCache[currentGroupId]);
                renderAccountList(filteredAccounts);
            }
        }

        // 防抖函数
        function debounce(func, wait) {
            let timeout;
            return function (...args) {
                clearTimeout(timeout);
                timeout = setTimeout(() => func.apply(this, args), wait);
            };
        }

        // 全局搜索函数
        async function searchAccounts(query) {
            const container = document.getElementById('accountList');
            const titleElement = document.getElementById('currentGroupName');

            if (!query.trim()) {
                currentAccountPage = 1;  // 清空搜索时重置页码
                loadAccountsByGroup(currentGroupId);
                return;
            }

            container.innerHTML = '<div class="loading-overlay"><span class="spinner"></span> 搜索中…</div>';

            try {
                const response = await fetch(`/api/accounts/search?q=${encodeURIComponent(query)}`);
                const data = await response.json();

                if (data.success) {
                    currentAccountPage = 1;  // 搜索结果重置到第 1 页
                    titleElement.textContent = `搜索结果 (${data.accounts.length})`;
                    renderAccountList(data.accounts);
                } else {
                    container.innerHTML = '<div class="empty-state"><p>搜索失败</p></div>';
                }
            } catch (error) {
                console.error('搜索失败:', error);
                container.innerHTML = '<div class="empty-state"><p>搜索失败，请重试</p></div>';
            }
        }

        // 更新分组下拉选择框
        function updateGroupSelects() {
            const selects = ['importGroupSelect', 'editGroupSelect'];
            selects.forEach(selectId => {
                const select = document.getElementById(selectId);
                if (select) {
                    const currentValue = select.value;
                    // 过滤掉临时邮箱分组（导入邮箱时不能选择临时邮箱分组）
                    const filteredGroups = selectId === 'importGroupSelect'
                        ? groups.filter(g => g.name !== '临时邮箱')
                        : groups;

                    select.innerHTML = filteredGroups.map(g =>
                        `<option value="${g.id}">${escapeHtml(g.name)}</option>`
                    ).join('');
                    // 恢复之前的选择
                    if (currentValue && filteredGroups.find(g => g.id === parseInt(currentValue))) {
                        select.value = currentValue;
                    } else if (currentGroupId && filteredGroups.find(g => g.id === currentGroupId)) {
                        select.value = currentGroupId;
                    }
                }
            });
        }

        // 显示添加分组模态框
        function showAddGroupModal() {
            editingGroupId = null;
            document.getElementById('groupModalTitle').textContent = translateAppTextLocal('添加分组');
            document.getElementById('groupName').value = '';
            document.getElementById('groupDescription').value = '';
            selectedColor = '#B85C38';
            document.querySelectorAll('.color-option').forEach(o => {
                o.classList.toggle('selected', o.dataset.color === selectedColor);
            });
            document.getElementById('customColorInput').value = selectedColor;
            document.getElementById('customColorHex').value = selectedColor;
            document.getElementById('groupProxyUrl').value = '';
            document.getElementById('addGroupModal').classList.add('show');
        }

        // 隐藏添加分组模态框
        function hideAddGroupModal() {
            document.getElementById('addGroupModal').classList.remove('show');
        }

        // 编辑分组
        async function editGroup(groupId) {
            try {
                const response = await fetch(`/api/groups/${groupId}`);
                const data = await response.json();

                if (data.success) {
                    editingGroupId = groupId;
                    document.getElementById('groupModalTitle').textContent = translateAppTextLocal('编辑分组');
                    document.getElementById('groupName').value = data.group.name;
                    document.getElementById('groupDescription').value = data.group.description || '';
                    selectedColor = data.group.color || '#B85C38';

                    // 检查是否是预设颜色
                    let isPresetColor = false;
                    document.querySelectorAll('.color-option').forEach(o => {
                        if (o.dataset.color === selectedColor) {
                            o.classList.add('selected');
                            isPresetColor = true;
                        } else {
                            o.classList.remove('selected');
                        }
                    });

                    // 更新自定义颜色输入框
                    document.getElementById('customColorInput').value = selectedColor;
                    document.getElementById('customColorHex').value = selectedColor;

                    // 填充代理设置
                    document.getElementById('groupProxyUrl').value = data.group.proxy_url || '';

                    document.getElementById('addGroupModal').classList.add('show');
                }
            } catch (error) {
                showToast(translateAppTextLocal('加载分组信息失败'), 'error');
            }
        }

        // 保存分组
        async function saveGroup() {
            const name = document.getElementById('groupName').value.trim();
            const description = document.getElementById('groupDescription').value.trim();

            if (!name) {
                showToast(translateAppTextLocal('请输入分组名称'), 'error');
                return;
            }

            try {
                const url = editingGroupId ? `/api/groups/${editingGroupId}` : '/api/groups';
                const method = editingGroupId ? 'PUT' : 'POST';

                const response = await fetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name,
                        description,
                        color: selectedColor,
                        proxy_url: document.getElementById('groupProxyUrl').value.trim()
                    })
                });

                const data = await response.json();

                if (data.success) {
                    showToast(pickApiMessage(data, data.message, 'Group saved successfully'), 'success');
                    hideAddGroupModal();
                    loadGroups();
                } else {
                    handleApiError(data, '保存分组失败');
                }
            } catch (error) {
                showToast(translateAppTextLocal('保存失败'), 'error');
            }
        }

        // 删除分组
        async function deleteGroup(groupId) {
            if (!confirm('确定要删除该分组吗？分组下的邮箱将移至默认分组。')) {
                return;
            }

            try {
                const response = await fetch(`/api/groups/${groupId}`, { method: 'DELETE' });
                const data = await response.json();

                if (data.success) {
                    showToast(pickApiMessage(data, data.message, 'Group deleted successfully'), 'success');
                    // 清除缓存
                    delete accountsCache[groupId];
                    // 如果删除的是当前选中的分组，切换到默认分组
                    if (currentGroupId === groupId) {
                        currentGroupId = 1;
                    }
                    loadGroups();
                } else {
                    handleApiError(data, '删除分组失败');
                }
            } catch (error) {
                showToast(translateAppTextLocal('删除失败'), 'error');
            }
        }

        // ==================== 全选功能 ====================

        // 全选/取消全选账号（当前分组）
        function toggleSelectAll() {
            const selectAllCheckbox = mailboxViewMode === 'compact'
                ? document.getElementById('compactSelectAllCheckbox')
                : document.getElementById('selectAllCheckbox');

            if (selectAllCheckbox.checked) {
                selectAllAccounts();
            } else {
                unselectAllAccounts();
            }
        }

        // 全选当前分组所有账号
        function selectAllAccounts() {
            const checkboxes = getActiveAccountCheckboxes();
            checkboxes.forEach(cb => {
                cb.checked = true;
                selectedAccountIds.add(parseInt(cb.value));
            });
            updateBatchActionBar();
            updateSelectAllCheckbox();
        }

        // 取消全选当前分组
        function unselectAllAccounts() {
            const checkboxes = getActiveAccountCheckboxes();
            checkboxes.forEach(cb => {
                cb.checked = false;
                selectedAccountIds.delete(parseInt(cb.value));
            });
            updateBatchActionBar();
            updateSelectAllCheckbox();
        }

        // 更新全选复选框状态（基于当前分组）
        function updateSelectAllCheckbox() {
            const checkboxes = getActiveAccountCheckboxes();
            const checkedCount = checkboxes.filter(cb => cb.checked).length;
            const selectAllCheckboxes = [
                document.getElementById('selectAllCheckbox'),
                document.getElementById('compactSelectAllCheckbox')
            ].filter(Boolean);

            selectAllCheckboxes.forEach(selectAllCheckbox => {
                if (checkboxes.length === 0) {
                    selectAllCheckbox.checked = false;
                    selectAllCheckbox.indeterminate = selectedAccountIds.size > 0;
                } else if (checkedCount === 0) {
                    selectAllCheckbox.checked = false;
                    selectAllCheckbox.indeterminate = selectedAccountIds.size > 0;
                } else if (checkedCount === checkboxes.length) {
                    selectAllCheckbox.checked = true;
                    selectAllCheckbox.indeterminate = false;
                } else {
                    selectAllCheckbox.checked = false;
                    selectAllCheckbox.indeterminate = true;
                }
            });
        }

        // ==================== 验证码复制功能 ====================

        function rerenderAccountCaches() {
            if (!Array.isArray(accountsCache[currentGroupId])) {
                return;
            }

            renderAccountList(applyFiltersAndSort(accountsCache[currentGroupId]));
            if (typeof renderCompactAccountList === 'function') {
                renderCompactAccountList(accountsCache[currentGroupId]);
            }
            if (typeof renderCompactGroupStrip === 'function') {
                renderCompactGroupStrip(groups, currentGroupId);
            }
            updateSelectAllCheckbox();
            updateBatchActionBar();
        }

        function syncAccountSummaryToAccountCache(email, accountSummary) {
            const normalizedEmail = String(email || '').trim().toLowerCase();
            if (!normalizedEmail || !accountSummary || typeof accountSummary !== 'object') {
                return false;
            }

            let updated = false;
            Object.values(accountsCache).forEach(accounts => {
                if (!Array.isArray(accounts)) {
                    return;
                }

                accounts.forEach(account => {
                    if (!account || String(account.email || '').trim().toLowerCase() !== normalizedEmail) {
                        return;
                    }

                    account.latest_email_subject = String(accountSummary.latest_email_subject || '');
                    account.latest_email_from = String(accountSummary.latest_email_from || '');
                    account.latest_email_folder = String(accountSummary.latest_email_folder || '');
                    account.latest_email_received_at = String(accountSummary.latest_email_received_at || '');
                    account.latest_verification_code = String(accountSummary.latest_verification_code || '');
                    account.latest_verification_folder = String(accountSummary.latest_verification_folder || '');
                    account.latest_verification_received_at = String(accountSummary.latest_verification_received_at || '');
                    updated = true;
                });
            });

            if (updated) {
                rerenderAccountCaches();
            }

            return updated;
        }

        function syncExtractedVerificationToAccountCache(email, verificationData, accountSummary = null) {
            if (syncAccountSummaryToAccountCache(email, accountSummary)) {
                return true;
            }

            const normalizedEmail = String(email || '').trim().toLowerCase();
            const verificationCode = String(
                verificationData?.verification_code || verificationData?.verificationCode || ''
            ).trim();

            if (!normalizedEmail || !verificationCode) {
                return false;
            }

            let updated = false;
            Object.values(accountsCache).forEach(accounts => {
                if (!Array.isArray(accounts)) {
                    return;
                }

                accounts.forEach(account => {
                    if (!account || String(account.email || '').trim().toLowerCase() !== normalizedEmail) {
                        return;
                    }

                    account.latest_verification_code = verificationCode;
                    if (verificationData?.folder) {
                        account.latest_verification_folder = String(verificationData.folder);
                    }
                    if (verificationData?.received_at) {
                        account.latest_verification_received_at = String(verificationData.received_at);
                    }
                    if (verificationData?.subject && !account.latest_email_subject) {
                        account.latest_email_subject = String(verificationData.subject);
                    }
                    updated = true;
                });
            });

            if (!updated) {
                return false;
            }
            rerenderAccountCaches();

            return true;
        }

        // 复制验证信息到剪贴板
        const verificationCopyInFlight = new Set();

        function buildVerificationExtractEndpoint(email, options = {}) {
            const normalizedSource = String(options?.source || '').trim().toLowerCase();
            if (normalizedSource === 'temp' || normalizedSource === 'temp-mail' || normalizedSource === 'temp_mail') {
                return `/api/temp-emails/${encodeURIComponent(email)}/extract-verification`;
            }
            return `/api/emails/${encodeURIComponent(email)}/extract-verification`;
        }

        async function tryFallbackVerificationExtraction(options = {}) {
            if (typeof options.fallbackExtractor !== 'function') {
                return null;
            }

            try {
                const fallbackResult = await options.fallbackExtractor();
                if (!fallbackResult || !fallbackResult.formatted) {
                    return null;
                }
                return fallbackResult;
            } catch (fallbackError) {
                console.error('本地兜底提取失败:', fallbackError);
                return null;
            }
        }

        async function copyVerificationInfo(email, buttonElement, options = {}) {
            const requestKey = String(email || '').trim().toLowerCase();
            if (!requestKey || verificationCopyInFlight.has(requestKey)) {
                return false;
            }
            verificationCopyInFlight.add(requestKey);

            // 禁用按钮并显示加载状态
            const originalContent = buttonElement.innerHTML;
            buttonElement.disabled = true;
            buttonElement.innerHTML = '⏳';
            buttonElement.style.opacity = '0.6';
            buttonElement.style.cursor = 'wait';

            try {
                const response = await fetch(buildVerificationExtractEndpoint(email, options));
                const data = await response.json();

                if (data.success && data.data && data.data.formatted) {
                    await copyToClipboard(data.data.formatted);
                    syncExtractedVerificationToAccountCache(email, data.data, data.account_summary || null);
                    showToast(
                        getUiLanguage() === 'en'
                            ? `Copied: ${data.data.formatted}`
                            : `已复制: ${data.data.formatted}`,
                        'success'
                    );
                    // 成功状态
                    buttonElement.innerHTML = '✅';
                    buttonElement.style.opacity = '1';
                    return true;
                } else {
                    const fallbackResult = await tryFallbackVerificationExtraction(options);
                    if (fallbackResult) {
                        await copyToClipboard(
                            fallbackResult.copyText || fallbackResult.verification_code || fallbackResult.verification_link || fallbackResult.formatted
                        );
                        const copiedValue = fallbackResult.displayValue || fallbackResult.verification_code || fallbackResult.verification_link || fallbackResult.formatted;
                        showToast(
                            getUiLanguage() === 'en'
                                ? `Copied from current email: ${copiedValue}`
                                : `已从当前邮件兜底复制: ${copiedValue}`,
                            'warning'
                        );
                        buttonElement.innerHTML = '✅';
                        buttonElement.style.opacity = '1';
                        return true;
                    }

                    const errorMsg = window.resolveApiErrorMessage
                        ? window.resolveApiErrorMessage(data.error || data, '未找到验证码或链接', 'No verification code or link was found')
                        : (data.error?.message || data.error || '未找到验证码或链接');
                    showToast(errorMsg, 'error');
                    // 失败状态
                    buttonElement.innerHTML = '❌';
                    buttonElement.style.opacity = '1';
                    return false;
                }
            } catch (error) {
                console.error('提取验证码失败:', error);
                const fallbackResult = await tryFallbackVerificationExtraction(options);
                if (fallbackResult) {
                    await copyToClipboard(
                        fallbackResult.copyText || fallbackResult.verification_code || fallbackResult.verification_link || fallbackResult.formatted
                    );
                    const copiedValue = fallbackResult.displayValue || fallbackResult.verification_code || fallbackResult.verification_link || fallbackResult.formatted;
                    showToast(
                        getUiLanguage() === 'en'
                            ? `Copied from current email: ${copiedValue}`
                            : `已从当前邮件兜底复制: ${copiedValue}`,
                        'warning'
                    );
                    buttonElement.innerHTML = '✅';
                    buttonElement.style.opacity = '1';
                    return true;
                }
                showToast(translateAppTextLocal('网络错误，请重试'), 'error');
                // 失败状态
                buttonElement.innerHTML = '❌';
                buttonElement.style.opacity = '1';
                return false;
            } finally {
                verificationCopyInFlight.delete(requestKey);
                // 延迟恢复按钮状态
                setTimeout(() => {
                    buttonElement.disabled = false;
                    buttonElement.innerHTML = originalContent;
                    buttonElement.style.cursor = 'pointer';
                }, 1500);
            }
        }

        // 复制文本到剪贴板
        async function copyToClipboard(text) {
            try {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    await navigator.clipboard.writeText(text);
                } else {
                    // 降级方案：使用 textarea
                    const textarea = document.createElement('textarea');
                    textarea.value = text;
                    textarea.style.position = 'fixed';
                    textarea.style.left = '-9999px';
                    document.body.appendChild(textarea);
                    textarea.select();
                    document.execCommand('copy');
                    document.body.removeChild(textarea);
                }
            } catch (error) {
                console.error('复制失败:', error);
                throw error;
            }
        }

