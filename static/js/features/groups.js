        // ==================== 分组相关 ====================

        // 加载分组列表
        async function loadGroups() {
            const container = document.getElementById('groupList');
            container.innerHTML = '<div class="loading loading-small"><div class="loading-spinner"></div></div>';

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
                    }
                }
            } catch (error) {
                container.innerHTML = '<div class="empty-state"><div class="empty-state-text">加载失败</div></div>';
                showToast('加载分组失败', 'error');
            }
        }

        // 渲染分组列表
        function renderGroupList(groups) {
            const container = document.getElementById('groupList');

            if (groups.length === 0) {
                container.innerHTML = `
                    <div class="empty-state" style="padding: 40px 20px;">
                        <div class="empty-state-text">暂无分组</div>
                    </div>
                `;
                return;
            }

            container.innerHTML = groups.map(group => {
                const isSystem = group.is_system === 1 || group.name === '临时邮箱';
                const isTempGroup = group.name === '临时邮箱';
                const isDefault = group.id === 1;

                return `
                    <div class="group-item ${currentGroupId === group.id ? 'active' : ''} ${isTempGroup ? 'temp-email-group' : ''}"
                         data-group-id="${group.id}"
                         onclick="selectGroup(${group.id})">
                        <div class="group-row-1">
                            <div class="group-color" style="background-color: ${group.color || '#666'}"></div>
                            <span class="group-name">${escapeHtml(group.name)}${isTempGroup ? ' ⚡' : ''}</span>
                        </div>
                        <div class="group-row-2">
                            <span class="group-count">${group.account_count || 0} 个邮箱</span>
                            <div class="group-actions">
                                ${!isSystem ? `<button class="group-action-btn" onclick="event.stopPropagation(); editGroup(${group.id})" title="编辑">✏️</button>` : ''}
                                ${!isDefault && !isSystem ? `<button class="group-action-btn" onclick="event.stopPropagation(); deleteGroup(${group.id})" title="删除">🗑️</button>` : ''}
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        // 选择分组
        async function selectGroup(groupId) {
            currentGroupId = groupId;

            // 清空搜索框
            const searchInput = document.getElementById('globalSearch');
            if (searchInput) {
                searchInput.value = '';
            }

            // 检查是否是临时邮箱分组
            const group = groups.find(g => g.id === groupId);
            isTempEmailGroup = group && group.name === '临时邮箱';

            // 更新分组列表 UI
            document.querySelectorAll('.group-item').forEach(item => {
                item.classList.toggle('active', parseInt(item.dataset.groupId) === groupId);
            });

            // 更新邮箱面板标题
            if (group) {
                document.getElementById('currentGroupName').textContent = group.name;
                document.getElementById('currentGroupColor').style.backgroundColor = group.color || '#666';

                // 更新导入邮箱时的默认分组
                const importSelect = document.getElementById('importGroupSelect');
                if (importSelect) {
                    importSelect.value = groupId;
                }
            }

            // 更新底部按钮
            updateAccountPanelFooter();

            // 加载该分组的邮箱
            if (isTempEmailGroup) {
                await loadTempEmails();
            } else {
                await loadAccountsByGroup(groupId);
            }
        }

        // 更新账号面板底部按钮
        function updateAccountPanelFooter() {
            const footer = document.querySelector('.account-panel-footer');
            if (isTempEmailGroup) {
                footer.innerHTML = `
                    <button class="add-account-btn" onclick="generateTempEmail()">+ 生成临时邮箱</button>
                `;
            } else {
                footer.innerHTML = `
                    <button class="add-account-btn" onclick="showGetRefreshTokenModal()" style="background-color: #0078d4; margin-bottom: 8px;">🔑 获取 Refresh Token</button>
                    <button class="add-account-btn" onclick="showAddAccountModal()">+ 导入邮箱</button>
                `;
            }
        }

        // 加载分组下的账号
        async function loadAccountsByGroup(groupId, forceRefresh = false) {
            const container = document.getElementById('accountList');

            // 如果有缓存且不强制刷新，直接使用缓存
            if (!forceRefresh && accountsCache[groupId]) {
                renderAccountList(accountsCache[groupId]);
                return;
            }

            container.innerHTML = '<div class="loading loading-small"><div class="loading-spinner"></div></div>';

            try {
                const response = await fetch(`/api/accounts?group_id=${groupId}`);
                const data = await response.json();

                if (data.success) {
                    // 缓存数据
                    accountsCache[groupId] = data.accounts;
                    renderAccountList(data.accounts);
                }
            } catch (error) {
                container.innerHTML = '<div class="empty-state"><div class="empty-state-text">加载失败</div></div>';
            }
        }

        // 渲染邮箱列表
        function renderAccountList(accounts) {
            const container = document.getElementById('accountList');

            if (accounts.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">📭</div>
                        <div class="empty-state-text">该分组暂无邮箱</div>
                    </div>
                `;
                // ���置全选复选框（但不清空已选中的其他分组账号）
                const selectAllCheckbox = document.getElementById('selectAllCheckbox');
                if (selectAllCheckbox) {
                    selectAllCheckbox.checked = false;
                    selectAllCheckbox.indeterminate = selectedAccountIds.size > 0;
                }
                // 更新批量操作栏显示
                updateBatchActionBar();
                return;
            }

            container.innerHTML = accounts.map((acc, index) => {
                // 根据全局 Set 设置复选框状态
                const isChecked = selectedAccountIds.has(acc.id);
                return `
                <div class="account-item ${currentAccount === acc.email ? 'active' : ''} ${acc.status === 'inactive' ? 'inactive' : ''}"
                     onclick="selectAccount('${escapeJs(acc.email)}')">
                    <div style="display: flex; align-items: flex-start; gap: 10px;">
                        <input type="checkbox" class="account-select-checkbox" value="${acc.id}"
                               ${isChecked ? 'checked' : ''}
                               onclick="event.stopPropagation(); updateBatchActionBar(); updateSelectAllCheckbox()"
                               style="margin-top: 6px; cursor: pointer;">
                        <div style="flex: 1; min-width: 0;">
                            <div class="account-email" title="${escapeHtml(acc.email)}" style="display: flex; align-items: center; gap: 6px; overflow: hidden; ${acc.last_refresh_status === 'failed' ? 'color: #dc3545; font-weight: 700;' : ''}">
                                <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                                    <span class="account-number">${index + 1}.</span> ${escapeHtml(acc.email)}
                                </span>
                                <button class="copy-verification-btn" onclick="event.stopPropagation(); copyVerificationInfo('${escapeJs(acc.email)}', this)" title="提取验证码并复制">📋</button>
                                ${acc.status === 'inactive' ? '<span class="account-status-tag">已停用</span>' : ''}
                            </div>
                            ${acc.remark && acc.remark.trim() ? `<div class="account-remark" title="${escapeHtml(acc.remark)}">📝 ${escapeHtml(acc.remark)}</div>` : ''}

                            <div class="account-tags">
                                ${(acc.tags || []).map(tag => `
                                    <span class="tag-badge" style="background-color: ${tag.color}">
                                        ${escapeHtml(tag.name)}
                                    </span>
                                `).join('')}
                            </div>

                            <div class="account-refresh-time" style="font-size: 11px; color: ${acc.last_refresh_status === 'failed' ? '#dc3545' : '#999'}; margin-top: 4px; padding-left: 0; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                                <span>🕐 ${formatRelativeTime(acc.last_refresh_at)}</span>
                                ${acc.last_refresh_status === 'failed' ? '<button class="account-action-btn" onclick="event.stopPropagation(); showRefreshError(' + acc.id + ', \'' + escapeJs(acc.last_refresh_error || '未知错误') + '\', \'' + escapeJs(acc.email) + '\')" style="padding: 2px 6px; font-size: 10px; background-color: #dc3545; color: white; border: none; border-radius: 3px; cursor: pointer;">查看错误</button>' : ''}
                            </div>
                        </div>
                    </div>
                    <div class="account-actions">
                        <button class="account-action-btn" onclick="event.stopPropagation(); copyEmail('${escapeJs(acc.email)}')" title="复制邮箱">复制</button>
                        <button class="account-action-btn" onclick="event.stopPropagation(); toggleAccountStatus(${acc.id}, '${escapeJs(acc.status || 'active')}')" title="${acc.status === 'inactive' ? '启用' : '停用'}">${acc.status === 'inactive' ? '启用' : '停用'}</button>
                        <button class="account-action-btn" onclick="event.stopPropagation(); showEditAccountModal(${acc.id})" title="编辑">编辑</button>
                        <button class="account-action-btn delete" onclick="event.stopPropagation(); deleteAccount(${acc.id}, '${escapeJs(acc.email)}')" title="删除">删除</button>
                    </div>
                </div>
            `}).join('');

            // 更新全选复选框状态
            updateSelectAllCheckbox();
            // 更新批量操作栏显示
            updateBatchActionBar();
        }

        // 排序相关变量
        let currentSortBy = 'refresh_time';
        let currentSortOrder = 'asc';

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
                btn.style.backgroundColor = '#ffffff';
                btn.style.color = '#666';
                btn.style.borderColor = '#e5e5e5';
            });

            const activeBtn = document.querySelector(`[data-sort="${sortBy}"]`);
            if (activeBtn) {
                activeBtn.classList.add('active');
                activeBtn.style.backgroundColor = '#1a1a1a';
                activeBtn.style.color = '#ffffff';
                activeBtn.style.borderColor = '#1a1a1a';
            }

            // 重新加载并排序账号列表
            if (accountsCache[currentGroupId]) {
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
                loadAccountsByGroup(currentGroupId);
                return;
            }

            container.innerHTML = '<div class="loading loading-small"><div class="loading-spinner"></div></div>';

            try {
                const response = await fetch(`/api/accounts/search?q=${encodeURIComponent(query)}`);
                const data = await response.json();

                if (data.success) {
                    titleElement.textContent = `搜索结果 (${data.accounts.length})`;
                    renderAccountList(data.accounts);
                } else {
                    container.innerHTML = '<div class="empty-state"><div class="empty-state-text">搜索失败</div></div>';
                }
            } catch (error) {
                console.error('搜索失败:', error);
                container.innerHTML = '<div class="empty-state"><div class="empty-state-text">搜索失败，请重试</div></div>';
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
            document.getElementById('groupModalTitle').textContent = '添加分组';
            document.getElementById('groupName').value = '';
            document.getElementById('groupDescription').value = '';
            selectedColor = '#1a1a1a';
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
                    document.getElementById('groupModalTitle').textContent = '编辑分组';
                    document.getElementById('groupName').value = data.group.name;
                    document.getElementById('groupDescription').value = data.group.description || '';
                    selectedColor = data.group.color || '#1a1a1a';

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
                showToast('加载分组信息失败', 'error');
            }
        }

        // 保存分组
        async function saveGroup() {
            const name = document.getElementById('groupName').value.trim();
            const description = document.getElementById('groupDescription').value.trim();

            if (!name) {
                showToast('请输入分组名称', 'error');
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
                    showToast(data.message, 'success');
                    hideAddGroupModal();
                    loadGroups();
                } else {
                    handleApiError(data, '保存分组失败');
                }
            } catch (error) {
                showToast('保存失败', 'error');
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
                    showToast(data.message, 'success');
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
                showToast('删除失败', 'error');
            }
        }

        // ==================== 全选功能 ====================

        // 全选/取消全选账号（当前分组）
        function toggleSelectAll() {
            const selectAllCheckbox = document.getElementById('selectAllCheckbox');

            if (selectAllCheckbox.checked) {
                selectAllAccounts();
            } else {
                unselectAllAccounts();
            }
        }

        // 全选当前分组所有账号
        function selectAllAccounts() {
            const checkboxes = document.querySelectorAll('.account-select-checkbox');
            checkboxes.forEach(cb => {
                cb.checked = true;
                selectedAccountIds.add(parseInt(cb.value));
            });
            updateBatchActionBar();
            updateSelectAllCheckbox();
        }

        // 取消全选当前分组
        function unselectAllAccounts() {
            const checkboxes = document.querySelectorAll('.account-select-checkbox');
            checkboxes.forEach(cb => {
                cb.checked = false;
                selectedAccountIds.delete(parseInt(cb.value));
            });
            updateBatchActionBar();
            updateSelectAllCheckbox();
        }

        // 更新全选复选框状态（基于当前分组）
        function updateSelectAllCheckbox() {
            const selectAllCheckbox = document.getElementById('selectAllCheckbox');
            const checkboxes = document.querySelectorAll('.account-select-checkbox');
            const checkedCount = document.querySelectorAll('.account-select-checkbox:checked').length;

            if (checkboxes.length === 0) {
                // 当前分组没有账号，但如果其他分组有选中则显示半选
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
        }

        // ==================== 验证码复制功能 ====================

        // 复制验证信息到剪贴板
        let copyVerificationInProgress = false; // 防重复点击

        async function copyVerificationInfo(email, buttonElement) {
            // 防止重复点击
            if (copyVerificationInProgress) {
                return;
            }
            copyVerificationInProgress = true;

            // 禁用按钮并显示加载状态
            const originalContent = buttonElement.innerHTML;
            buttonElement.disabled = true;
            buttonElement.innerHTML = '⏳';
            buttonElement.style.opacity = '0.6';
            buttonElement.style.cursor = 'wait';

            try {
                const response = await fetch(`/api/emails/${encodeURIComponent(email)}/extract-verification`);
                const data = await response.json();

                if (data.success && data.data && data.data.formatted) {
                    await copyToClipboard(data.data.formatted);
                    showToast(`已复制: ${data.data.formatted}`, 'success');
                    // 成功状态
                    buttonElement.innerHTML = '✅';
                    buttonElement.style.opacity = '1';
                } else {
                    const errorMsg = data.error?.message || data.error || '未找到验证码或链接';
                    showToast(errorMsg, 'error');
                    // 失败状态
                    buttonElement.innerHTML = '❌';
                    buttonElement.style.opacity = '1';
                }
            } catch (error) {
                console.error('提取验证码失败:', error);
                showToast('网络错误，请重试', 'error');
                // 失败状态
                buttonElement.innerHTML = '❌';
                buttonElement.style.opacity = '1';
            } finally {
                copyVerificationInProgress = false;
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

