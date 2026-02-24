        // ==================== 账号相关 ====================

        // 选择账号
        function selectAccount(email) {
            // 静默停止之前的轮询
            if (typeof stopPolling === 'function') {
                stopPolling(true); // silent = true
            }

            currentAccount = email;
            isTempEmailGroup = false;
            currentFolder = 'inbox'; // 重置为收件箱

            document.getElementById('currentAccount').classList.add('show');
            document.getElementById('currentAccountEmail').textContent = email;

            document.querySelectorAll('.account-item').forEach(item => {
                item.classList.remove('active');
                const emailEl = item.querySelector('.account-email');
                if (emailEl && emailEl.textContent.includes(email)) {
                    item.classList.add('active');
                }
            });

            // 显示文件夹切换按钮
            const folderTabs = document.getElementById('folderTabs');
            if (folderTabs) {
                folderTabs.style.display = 'flex';
                // 重置为收件箱
                document.querySelectorAll('.folder-tab').forEach(tab => {
                    tab.classList.toggle('active', tab.dataset.folder === 'inbox');
                });
            }

            const cacheKey = `${email}_inbox`;

            // 检查缓存
            if (emailListCache[cacheKey]) {
                const cache = emailListCache[cacheKey];
                currentEmails = cache.emails;
                hasMoreEmails = cache.has_more;
                currentSkip = cache.skip;
                currentMethod = cache.method || 'graph';

                // 恢复 UI
                const methodTag = document.getElementById('methodTag');
                methodTag.textContent = currentMethod;
                methodTag.style.display = 'inline';
                document.getElementById('emailCount').textContent = `(${currentEmails.length})`;

                renderEmailList(currentEmails);
            } else {
                document.getElementById('emailList').innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">📬</div>
                        <div class="empty-state-text">点击"获取邮件"按钮获取邮件</div>
                    </div>
                `;
                document.getElementById('emailCount').textContent = '';
                document.getElementById('methodTag').style.display = 'none';
                currentEmails = [];
            }

            document.getElementById('emailDetail').innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📄</div>
                    <div class="empty-state-text">选择一封邮件查看详情</div>
                </div>
            `;
            document.getElementById('emailDetailToolbar').style.display = 'none';
        }

        // 显示添加账号模态框
        function showAddAccountModal() {
            document.getElementById('accountInput').value = '';
            // 设置默认分组为当前选中的分组
            if (currentGroupId) {
                document.getElementById('importGroupSelect').value = currentGroupId;
            }
            document.getElementById('addAccountModal').classList.add('show');
        }

        // 隐藏添加账号模态框
        function hideAddAccountModal() {
            document.getElementById('addAccountModal').classList.remove('show');
        }

        // 添加账号
        async function addAccount() {
            const input = document.getElementById('accountInput').value.trim();
            const groupId = parseInt(document.getElementById('importGroupSelect').value);

            if (!input) {
                showToast('请输入账号信息', 'error');
                return;
            }

            try {
                const response = await fetch('/api/accounts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ account_string: input, group_id: groupId })
                });

                const data = await response.json();

                if (data.success) {
                    showToast(data.message, 'success');
                    hideAddAccountModal();

                    // 清除该分组的缓存
                    delete accountsCache[groupId];

                    // 刷新分组列表（更新数量）
                    loadGroups();

                    // 如果当前选中的就是这个分组，刷新邮箱列表
                    if (currentGroupId === groupId) {
                        loadAccountsByGroup(groupId, true);
                    }
                } else {
                    handleApiError(data, '导入邮箱失败');
                }
            } catch (error) {
                showToast('添加失败', 'error');
            }
        }

        // 显示编辑账号模态框
        async function showEditAccountModal(accountId) {
            try {
                const response = await fetch(`/api/accounts/${accountId}`);
                const data = await response.json();

                if (data.success) {
                    const acc = data.account;
                    document.getElementById('editAccountId').value = acc.id;
                    document.getElementById('editEmail').value = acc.email;
                    document.getElementById('editPassword').value = acc.password || '';
                    document.getElementById('editClientId').value = acc.client_id;
                    document.getElementById('editRefreshToken').value = acc.refresh_token;
                    document.getElementById('editGroupSelect').value = acc.group_id || 1;
                    document.getElementById('editRemark').value = acc.remark || '';
                    document.getElementById('editStatus').value = acc.status || 'active';
                    document.getElementById('editAccountModal').classList.add('show');
                }
            } catch (error) {
                showToast('加载账号信息失败', 'error');
            }
        }

        // 隐藏编辑账号模态框
        function hideEditAccountModal() {
            document.getElementById('editAccountModal').classList.remove('show');
        }

        // 更新账号
        async function updateAccount() {
            const accountId = document.getElementById('editAccountId').value;
            const oldGroupId = currentGroupId;
            const newGroupId = parseInt(document.getElementById('editGroupSelect').value);

            const data = {
                email: document.getElementById('editEmail').value.trim(),
                password: document.getElementById('editPassword').value,
                client_id: document.getElementById('editClientId').value.trim(),
                refresh_token: document.getElementById('editRefreshToken').value.trim(),
                group_id: newGroupId,
                remark: document.getElementById('editRemark').value.trim(),
                status: document.getElementById('editStatus').value
            };

            if (!data.email || !data.client_id || !data.refresh_token) {
                showToast('邮箱、Client ID 和 Refresh Token 不能为空', 'error');
                return;
            }

            try {
                const response = await fetch(`/api/accounts/${accountId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                const result = await response.json();

                if (result.success) {
                    showToast(result.message, 'success');
                    hideEditAccountModal();

                    // 清除相关分组的缓存
                    delete accountsCache[oldGroupId];
                    if (oldGroupId !== newGroupId) {
                        delete accountsCache[newGroupId];
                    }

                    // 刷新分组列表
                    loadGroups();

                    // 刷新当前分组的邮箱列表
                    if (currentGroupId) {
                        loadAccountsByGroup(currentGroupId, true);
                    }
                } else {
                    showToast(result.error, 'error');
                }
            } catch (error) {
                showToast('更新失败', 'error');
            }
        }

        // 删除当前编辑的账号
        async function deleteCurrentAccount() {
            const accountId = document.getElementById('editAccountId').value;
            const email = document.getElementById('editEmail').value;
            const groupId = parseInt(document.getElementById('editGroupSelect').value);

            if (!confirm(`确定要删除账号 ${email} 吗？`)) {
                return;
            }

            try {
                const response = await fetch(`/api/accounts/${accountId}`, { method: 'DELETE' });
                const data = await response.json();

                if (data.success) {
                    showToast('删除成功', 'success');
                    hideEditAccountModal();

                    // 清除缓存
                    delete accountsCache[groupId];

                    if (currentAccount === email) {
                        currentAccount = null;
                        document.getElementById('currentAccount').classList.remove('show');
                        document.getElementById('emailList').innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">📬</div>
                                <div class="empty-state-text">请从左侧选择一个邮箱账号</div>
                            </div>
                        `;
                        document.getElementById('emailDetail').innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">📄</div>
                                <div class="empty-state-text">选择一封邮件查看详情</div>
                            </div>
                        `;
                    }

                    // 刷新分组列表
                    loadGroups();

                    // 刷新当前分组的邮箱列表
                    if (currentGroupId) {
                        loadAccountsByGroup(currentGroupId, true);
                    }
                }
            } catch (error) {
                showToast('删除失败', 'error');
            }
        }

        // 切换账号状态（启用/停用）
        async function toggleAccountStatus(accountId, currentStatus) {
            const newStatus = currentStatus === 'inactive' ? 'active' : 'inactive';
            const action = newStatus === 'inactive' ? '停用' : '启用';

            try {
                const response = await fetch(`/api/accounts/${accountId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: newStatus })
                });

                const data = await response.json();

                if (data.success) {
                    showToast(`${action}成功`, 'success');

                    // 清除当前分组的缓存
                    if (currentGroupId) {
                        delete accountsCache[currentGroupId];
                        loadAccountsByGroup(currentGroupId, true);
                    }
                } else {
                    handleApiError(data, `${action}账号失败`);
                }
            } catch (error) {
                showToast(`${action}失败`, 'error');
            }
        }

        // 删除账号（快捷方式）
        async function deleteAccount(accountId, email) {
            if (!confirm(`确定要删除账号 ${email} 吗？`)) {
                return;
            }

            try {
                const response = await fetch(`/api/accounts/${accountId}`, { method: 'DELETE' });
                const data = await response.json();

                if (data.success) {
                    showToast('删除成功', 'success');

                    // 清除当前分组的缓存
                    if (currentGroupId) {
                        delete accountsCache[currentGroupId];
                    }

                    if (currentAccount === email) {
                        currentAccount = null;
                        document.getElementById('currentAccount').classList.remove('show');
                        document.getElementById('emailList').innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">📬</div>
                                <div class="empty-state-text">请从左侧选择一个邮箱账号</div>
                            </div>
                        `;
                        document.getElementById('emailDetail').innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">📄</div>
                                <div class="empty-state-text">选择一封邮件查看详情</div>
                            </div>
                        `;
                    }

                    // 刷新分组列表
                    loadGroups();

                    // 刷新当前分组的邮箱列表
                    if (currentGroupId) {
                        loadAccountsByGroup(currentGroupId, true);
                    }
                } else {
                    handleApiError(data, '删除账号失败');
                }
            } catch (error) {
                showToast('删除失败', 'error');
            }
        }

        // 显示导出邮箱模态框
        async function showExportModal() {
            document.getElementById('exportModal').classList.add('show');
            await loadExportGroupList();
        }

        // 隐藏导出邮箱模态框
        function hideExportModal() {
            document.getElementById('exportModal').classList.remove('show');
        }

        // 加载导出分组列表
        async function loadExportGroupList() {
            const container = document.getElementById('exportGroupList');
            container.innerHTML = '<div class="loading loading-small"><div class="loading-spinner"></div></div>';

            try {
                // 使用已加载的分组数据
                if (groups.length === 0) {
                    container.innerHTML = '<div style="padding: 20px; text-align: center; color: #999;">暂无分组</div>';
                } else {
                    container.innerHTML = groups.map(group => `
                        <label style="display: flex; align-items: center; gap: 10px; padding: 10px 12px; cursor: pointer; border-radius: 6px; transition: background-color 0.15s;"
                               onmouseover="this.style.backgroundColor='#f5f5f5'"
                               onmouseout="this.style.backgroundColor='transparent'">
                            <input type="checkbox" class="export-group-checkbox" value="${group.id}" style="width: 16px; height: 16px;">
                            <span style="display: flex; align-items: center; gap: 8px; flex: 1;">
                                <span style="width: 12px; height: 12px; border-radius: 3px; background-color: ${group.color || '#666'}"></span>
                                <span style="font-size: 14px; color: #1a1a1a;">${escapeHtml(group.name)}</span>
                            </span>
                            <span style="font-size: 12px; color: #999; background-color: #f0f0f0; padding: 2px 8px; border-radius: 10px;">${group.account_count || 0}</span>
                        </label>
                    `).join('');
                }
            } catch (error) {
                container.innerHTML = '<div style="padding: 20px; text-align: center; color: #dc3545;">加载失败</div>';
            }

            // 重置全选复选框
            document.getElementById('selectAllGroups').checked = false;
        }

        // 全选/取消全选分组
        function toggleSelectAllGroups() {
            const selectAll = document.getElementById('selectAllGroups').checked;
            document.querySelectorAll('.export-group-checkbox').forEach(cb => {
                cb.checked = selectAll;
            });
        }

        // 存储待导出的分组ID
        let pendingExportGroupIds = [];

        // 导出选中的分组
        async function exportSelectedGroups() {
            const checkboxes = document.querySelectorAll('.export-group-checkbox:checked');
            const groupIds = Array.from(checkboxes).map(cb => parseInt(cb.value));

            if (groupIds.length === 0) {
                showToast('请选择要导出的分组', 'error');
                return;
            }

            // 保存待导出的分组ID
            pendingExportGroupIds = groupIds;

            // 显示密码确认对话框
            hideExportModal();
            showExportVerifyModal();
        }

        // 显示导出密码确认对话框
        function showExportVerifyModal() {
            document.getElementById('exportVerifyModal').classList.add('show');
            document.getElementById('exportVerifyPassword').value = '';
            document.getElementById('exportVerifyPassword').focus();
        }

        // 隐藏导出密码确认对话框
        function hideExportVerifyModal() {
            document.getElementById('exportVerifyModal').classList.remove('show');
            document.getElementById('exportVerifyPassword').value = '';
        }

        // 确认导出验证
        async function confirmExportVerify() {
            const password = document.getElementById('exportVerifyPassword').value;

            if (!password) {
                showToast('请输入密码', 'error');
                return;
            }

            try {
                // 获取验证token
                const verifyResponse = await fetch('/api/export/verify', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password })
                });

                const verifyData = await verifyResponse.json();

                if (!verifyData.success) {
                    showToast(verifyData.error || '密码错误', 'error');
                    return;
                }

                const verifyToken = verifyData.verify_token;

                // 执行导出
                const response = await fetch('/api/accounts/export-selected', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        group_ids: pendingExportGroupIds,
                        verify_token: verifyToken
                    })
                });

                if (response.ok) {
                    // 获取文件名
                    const contentDisposition = response.headers.get('Content-Disposition');
                    let filename = 'accounts.txt';
                    if (contentDisposition) {
                        const match = contentDisposition.match(/filename\*?=(?:UTF-8'')?([^;\n]+)/i);
                        if (match) {
                            filename = decodeURIComponent(match[1]);
                        }
                    }

                    // 下载文件
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    document.body.removeChild(a);

                    showToast('导出成功', 'success');
                    hideExportVerifyModal();
                } else {
                    const data = await response.json();
                    handleApiError(data, '导出失败');
                }
            } catch (error) {
                showToast('导出失败', 'error');
            }
        }

