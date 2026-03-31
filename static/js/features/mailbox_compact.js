        function getCompactVisibleAccounts() {
            return Array.isArray(accountsCache[currentGroupId]) ? accountsCache[currentGroupId] : [];
        }

        function getCompactAccountById(accountId) {
            return getCompactVisibleAccounts().find(account => account.id === accountId) || null;
        }

        function closeCompactMenu(element) {
            const details = element && typeof element.closest === 'function' ? element.closest('details') : null;
            if (details) {
                details.removeAttribute('open');
            }
        }

        function translateCompactText(text) {
            return typeof translateAppTextLocal === 'function' ? translateAppTextLocal(text) : text;
        }

        function formatCompactSelectedCount(count) {
            if (typeof formatSelectedItemsLabel === 'function') {
                return formatSelectedItemsLabel(count);
            }
            return getUiLanguage() === 'en' ? `${count} selected` : `已选 ${count} 项`;
        }

        function formatCompactAccountCount(count) {
            const safeCount = Number(count || 0);
            if (getUiLanguage() === 'en') {
                return `${safeCount} account${safeCount === 1 ? '' : 's'}`;
            }
            return `${safeCount} 个账号`;
        }

        function renderCompactLoadingState(message = '加载中…') {
            const container = document.getElementById('compactAccountList');
            if (!container) return;
            container.innerHTML = `
                <div class="loading-overlay compact-state-block">
                    <span class="spinner"></span> ${escapeHtml(translateCompactText(message))}
                </div>
            `;
        }

        function renderCompactErrorState(message = '加载失败，请重试') {
            const container = document.getElementById('compactAccountList');
            if (!container) return;
            container.innerHTML = `
                <div class="empty-state compact-state-block">
                    <span class="empty-icon">⚠️</span>
                    <p>${escapeHtml(translateCompactText(message))}</p>
                </div>
            `;
        }

        function switchMailboxViewMode(mode) {
            var prevMode = mailboxViewMode;
            mailboxViewMode = mode === 'compact' ? 'compact' : 'standard';
            localStorage.setItem('ol_mailbox_view_mode', mailboxViewMode);

            // 视图切换时不停止轮询——统一引擎持续运行，UI 回调根据 mailboxViewMode 分发。
            // 只需在切换后清理旧模式 UI 残留，然后重新应用新模式 UI。
            if (prevMode === 'compact' && mailboxViewMode !== 'compact') {
                // 从简洁模式切走：清理简洁模式的轮询 UI（绿点、按钮文字），但不停止轮询
                if (typeof pollMap !== 'undefined') {
                    pollMap.forEach(function(state, email) {
                        updateCompactPollUI(email, 'stopped', null);
                    });
                }
            } else if (prevMode !== 'compact' && mailboxViewMode === 'compact') {
                // 从标准模式切走：清理标准模式的轮询 UI
                if (typeof hideStandardPollDot === 'function') {
                    hideStandardPollDot(); // 无参数 = 清除所有
                }
            }

            const standardLayout = document.getElementById('mailboxStandardLayout');
            const compactLayout = document.getElementById('mailboxCompactLayout');

            if (standardLayout) {
                standardLayout.style.display = mailboxViewMode === 'standard' ? '' : 'none';
            }
            if (compactLayout) {
                compactLayout.style.display = mailboxViewMode === 'compact' ? 'block' : 'none';
            }
            if (currentPage === 'mailbox' && typeof updateTopbar === 'function') {
                updateTopbar('mailbox');
            }

            if (currentGroupId && Array.isArray(accountsCache[currentGroupId])) {
                renderAccountList(accountsCache[currentGroupId]);
            }
            renderCompactGroupStrip(groups, currentGroupId);
            renderCompactAccountList(getCompactVisibleAccounts());
            updateBatchActionBar();
            updateSelectAllCheckbox();

            // 切换完成后重新应用当前模式的轮询 UI（renderAccountList/renderCompactAccountList
            // 内部已调用 reapplyAllPollUI/reapplyAllCompactPollUI，但模式切换可能需要额外刷新）
            if (typeof reapplyAllPollUI === 'function') {
                reapplyAllPollUI();
            }
        }

        function renderCompactGroupStrip(groupItems, activeGroupId) {
            const container = document.getElementById('compactGroupStrip');
            const summary = document.getElementById('compactModeSummary');
            if (!container) return;

            const visibleGroups = (groupItems || []).filter(group => !isTempMailboxGroup(group));
            if (visibleGroups.length === 0) {
                container.innerHTML = `<div class="compact-empty-inline">${escapeHtml(translateCompactText('暂无分组'))}</div>`;
                if (summary) {
                    summary.textContent = translateCompactText('暂无可用分组');
                }
                return;
            }

            const currentGroup = visibleGroups.find(group => group.id === activeGroupId) || visibleGroups[0];
            if (summary && currentGroup) {
                const selectedCount = selectedAccountIds.size > 0 ? ` · ${formatCompactSelectedCount(selectedAccountIds.size)}` : '';
                summary.textContent = `${formatGroupDisplayName(currentGroup.name)} · ${formatCompactAccountCount(currentGroup.account_count)}${selectedCount}`;
            }

            container.innerHTML = visibleGroups.map(group => `
                <button
                    class="group-chip ${group.id === activeGroupId ? 'active' : ''}"
                    onclick="selectGroup(${group.id})"
                >
                    <span>
                        <span class="group-chip-name">${escapeHtml(formatGroupDisplayName(group.name))}</span>
                        <span class="group-chip-meta">${escapeHtml(formatGroupDescription(group.description, '未填写说明'))} · ${escapeHtml(formatCompactAccountCount(group.account_count))}</span>
                    </span>
                </button>
            `).join('');
        }

        function syncCompactSelectionState(accountId, checked) {
            handleAccountSelectionChange(accountId, checked);
            renderCompactGroupStrip(groups, currentGroupId);
        }

        async function copyCompactVerification(account, buttonElement) {
            if (!account) {
                showToast(translateCompactText('未找到账号摘要'), 'error');
                return;
            }

            if (account.latest_verification_code) {
                try {
                    await copyToClipboard(account.latest_verification_code);
                    showToast(
                        getUiLanguage() === 'en'
                            ? `Copied: ${account.latest_verification_code}`
                            : `已复制: ${account.latest_verification_code}`,
                        'success'
                    );
                    return;
                } catch (error) {
                    showToast(translateCompactText('复制验证码失败'), 'error');
                    return;
                }
            }

            if (buttonElement) {
                copyVerificationInfo(account.email, buttonElement);
            }
        }

        function openCompactSingleTagModal(accountId) {
            showBatchTagModal('add', { scopedAccountIds: [accountId] });
        }

        function openCompactSingleMoveGroupModal(accountId) {
            showBatchMoveGroupModal({ scopedAccountIds: [accountId] });
        }

        async function refreshCompactAccount(accountId, buttonElement) {
            const account = getCompactAccountById(accountId);
            if (!account) {
                showToast(translateCompactText('未找到账号'), 'error');
                return;
            }

            const originalText = buttonElement ? buttonElement.textContent : '';
            if (buttonElement) {
                buttonElement.disabled = true;
                buttonElement.textContent = translateCompactText('拉取中...');
            }

            try {
                const requests = [
                    fetch(`/api/emails/${encodeURIComponent(account.email)}?folder=inbox&skip=0&top=10`),
                    fetch(`/api/emails/${encodeURIComponent(account.email)}?folder=junkemail&skip=0&top=10`)
                ];
                const results = await Promise.allSettled(requests);
                let hasSuccess = false;
                for (const result of results) {
                    if (result.status !== 'fulfilled' || !result.value.ok) {
                        continue;
                    }
                    const payload = await result.value.json();
                    if (!payload.success) {
                        continue;
                    }
                    hasSuccess = true;
                    if (typeof syncAccountSummaryToAccountCache === 'function' && payload.account_summary) {
                        syncAccountSummaryToAccountCache(account.email, payload.account_summary);
                    }
                }
                if (!hasSuccess) {
                    throw new Error('refresh_failed');
                }
                const hasPartialFailure = results.some(result => result.status === 'rejected' || (result.status === 'fulfilled' && !result.value.ok));
                showToast(
                    translateCompactText(hasPartialFailure ? '部分拉取完成，账号摘要已刷新' : '账号摘要已刷新'),
                    'success'
                );
            } catch (error) {
                showToast(translateCompactText('刷新账号摘要失败'), 'error');
            } finally {
                if (buttonElement) {
                    buttonElement.disabled = false;
                    buttonElement.textContent = originalText || translateCompactText('拉取');
                }
            }
        }

        function renderCompactAccountList(accounts) {
            const container = document.getElementById('compactAccountList');
            if (!container) return;

            if (!accounts || accounts.length === 0) {
                container.innerHTML = `
                    <div class="empty-state-lite compact-state-block">
                        ${escapeHtml(translateCompactText('当前分组暂无账号'))}
                    </div>
                `;
                updateSelectAllCheckbox();
                updateBatchActionBar();
                return;
            }

            container.innerHTML = (accounts || []).map(account => {
                const latestEmailSubject = account.latest_email_subject || translateCompactText('暂无邮件');
                const latestEmailFrom = account.latest_email_from || translateCompactText('未知发件人');
                const latestEmailFolder = account.latest_email_folder || '';
                const latestEmailReceivedAt = account.latest_email_received_at || '';
                const latestVerificationCode = account.latest_verification_code || '';
                const isChecked = selectedAccountIds.has(account.id);
                const tagHtml = (account.tags || []).map(tag => `
                    <span class="tag-chip">${escapeHtml(tag.name)}</span>
                `).join('');
                const providerText = (account.provider || account.account_type || 'outlook').toUpperCase();
                const statusText = formatAccountStatusLabel(account.status);
                const latestEmailMeta = [
                    latestEmailFrom || translateCompactText('未知发件人'),
                    latestEmailFolder || '',
                    latestEmailReceivedAt || ''
                ].filter(Boolean).join(' · ');

                return `
                    <div class="mail-row ${isChecked ? 'is-selected' : ''}" data-email="${escapeHtml(account.email || '')}">
                        <div class="select-cell" data-label="${escapeHtml(translateCompactText('选择'))}">
                            <input
                                type="checkbox"
                                class="account-select-checkbox"
                                value="${account.id}"
                                ${isChecked ? 'checked' : ''}
                                onchange="syncCompactSelectionState(${account.id}, this.checked)"
                            >
                        </div>
                        <div class="mail-card" data-label="${escapeHtml(translateCompactText('邮箱'))}">
                            <button
                                class="mail-card-button"
                                onclick="copyEmail('${escapeJs(account.email)}')"
                                title="${escapeHtml(translateCompactText('点击复制邮箱地址'))}"
                            >
                                <span class="mail-address">${escapeHtml(account.email || '')}</span>
                                <div class="mail-meta" title="${escapeHtml(`${providerText} · ${statusText}`)}">
                                    ${escapeHtml(providerText)} · ${escapeHtml(statusText)}
                                </div>
                            </button>
                        </div>
                        <div class="mail-code" data-label="${escapeHtml(translateCompactText('验证码'))}">
                            <button
                                class="code-button ${latestVerificationCode ? '' : 'empty'}"
                                onclick="copyCompactVerification(getCompactAccountById(${account.id}), this)"
                                title="${escapeHtml(translateCompactText(latestVerificationCode ? '复制当前摘要验证码' : '无摘要码时兜底提取验证码'))}"
                            >${escapeHtml(latestVerificationCode || translateCompactText('暂无'))}</button>
                        </div>
                        <div class="mail-snippet" data-label="${escapeHtml(translateCompactText('最新邮件'))}">
                            <div class="snippet-subject" title="${escapeHtml(latestEmailSubject)}">${escapeHtml(latestEmailSubject)}</div>
                            <div class="snippet-meta" title="${escapeHtml(latestEmailMeta)}">${escapeHtml(latestEmailMeta || translateCompactText('暂无邮件摘要'))}</div>
                        </div>
                        <div data-label="${escapeHtml(translateCompactText('标签'))}">
                            <div class="tag-list">
                                ${tagHtml || `<span class="tag-chip muted">${escapeHtml(translateCompactText('暂无标签'))}</span>`}
                            </div>
                        </div>
                        <div class="action-cell" data-label="${escapeHtml(translateCompactText('操作'))}">
                            <div class="compact-actions">
                                <button class="pull-button" onclick="refreshCompactAccount(${account.id}, this)">${escapeHtml(translateCompactText('拉取'))}</button>
                                <details class="action-menu">
                                    <summary class="menu-button" aria-label="${escapeHtml(translateCompactText('更多操作'))}" title="${escapeHtml(translateCompactText('更多操作'))}">⋯</summary>
                                    <div class="menu-panel">
                                        <button class="menu-item" onclick="event.preventDefault(); event.stopPropagation(); closeCompactMenu(this); showEditAccountModal(${account.id})">${escapeHtml(translateCompactText('编辑账号'))}</button>
                                        <button class="menu-item" onclick="event.preventDefault(); event.stopPropagation(); closeCompactMenu(this); showEditRemarkOnly(${account.id})">${escapeHtml(translateCompactText('编辑备注'))}</button>
                                        <button class="menu-item" onclick="event.preventDefault(); event.stopPropagation(); closeCompactMenu(this); openCompactSingleTagModal(${account.id})">${escapeHtml(translateCompactText('打标签'))}</button>
                                        <button class="menu-item" onclick="event.preventDefault(); event.stopPropagation(); closeCompactMenu(this); openCompactSingleMoveGroupModal(${account.id})">${escapeHtml(translateCompactText('移动分组'))}</button>
                                        <button class="menu-item danger" onclick="event.preventDefault(); event.stopPropagation(); closeCompactMenu(this); deleteAccount(${account.id}, '${escapeJs(account.email)}')">${escapeHtml(translateCompactText('删除账号'))}</button>
                                    </div>
                                </details>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');

            updateSelectAllCheckbox();
            updateBatchActionBar();
            // 重新应用所有轮询 UI 状态（在列表刷新后恢复激活态圆点和按钮样式）
            if (typeof reapplyAllCompactPollUI === 'function') {
                reapplyAllCompactPollUI();
            }
        }

        window.addEventListener('ui-language-changed', () => {
            renderCompactGroupStrip(groups, currentGroupId);
            renderCompactAccountList(getCompactVisibleAccounts());
        });

        // ==================== 简洁模式轮询 UI 适配层 ====================
        //
        // 核心轮询引擎已迁移至 poll-engine.js。
        // 本文件保留简洁模式特有的 DOM 查找、UI 更新和事件监听。

        // ── 向后兼容别名（测试和 main.js 可能引用旧名称） ──
        var COMPACT_POLL_TOAST_DURATION   = typeof POLL_TOAST_DURATION !== 'undefined' ? POLL_TOAST_DURATION : 5000;
        var COMPACT_POLL_INITIAL_DELAY_MS = typeof POLL_INITIAL_DELAY_MS !== 'undefined' ? POLL_INITIAL_DELAY_MS : 150;
        var compactPollMap                = typeof pollMap !== 'undefined' ? pollMap : new Map();
        var compactPollCountdownTimer     = null; // 仅供测试 setup.js 重置用

        // ── 简洁模式 DOM 操作 ──

        function findCompactAccountRow(email) {
            if (!email) return null;
            try {
                var esc = String(email).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
                var el = document.querySelector('.mail-row[data-email="' + esc + '"]');
                if (el) return el;
            } catch (e) {}
            var rows = document.querySelectorAll('.mail-row');
            for (var i = 0; i < rows.length; i++) {
                if (rows[i].getAttribute && rows[i].getAttribute('data-email') === email) return rows[i];
            }
            return null;
        }

        function updateCompactPollUI(email, status, remainingSeconds) {
            var row = findCompactAccountRow(email);
            if (!row) return;
            var pull = row.querySelector('.pull-button');
            var card = row.querySelector('.mail-card');

            var oldDot = card ? card.querySelector('.compact-poll-dot') : null;
            if (oldDot) oldDot.remove();

            if (status === 'polling') {
                if (card) {
                    var dot = document.createElement('span');
                    dot.className = 'compact-poll-dot';
                    card.appendChild(dot);
                }
                if (pull) {
                    pull.classList.add('compact-poll-active');
                    pull.setAttribute('data-poll-email', email);
                    var tFn = typeof translateCompactText === 'function' ? translateCompactText : function(k) { return k; };
                    pull.textContent = tFn('停止监听') + ' ' + (Number(remainingSeconds) || 0) + 's';
                }
            } else if (status === 'stopped') {
                if (pull) {
                    pull.classList.remove('compact-poll-active');
                    pull.removeAttribute('data-poll-email');
                    var tFn2 = typeof translateCompactText === 'function' ? translateCompactText : function(k) { return k; };
                    pull.textContent = tFn2('拉取');
                }
            }
        }

        function updateSingleRowFromCache(email, summary) {
            if (!email || !summary) return;
            var row = findCompactAccountRow(email);
            if (!row) return;

            var codeBtn = row.querySelector('.code-button');
            if (codeBtn && summary.latest_verification_code !== undefined) {
                var code = summary.latest_verification_code || '';
                var tFn = typeof translateCompactText === 'function' ? translateCompactText : function(k) { return k; };
                codeBtn.textContent = code || tFn('暂无');
                if (code) codeBtn.classList.remove('empty'); else codeBtn.classList.add('empty');
            }

            var snippetSubject = row.querySelector('.snippet-subject');
            var snippetMeta = row.querySelector('.snippet-meta');
            if (snippetSubject && summary.latest_email_subject !== undefined) {
                snippetSubject.textContent = summary.latest_email_subject || '';
                snippetSubject.title = summary.latest_email_subject || '';
            }
            if (snippetMeta) {
                var meta = [summary.latest_email_from || '', summary.latest_email_folder || '', summary.latest_email_received_at || ''].filter(Boolean).join(' · ');
                var tFn2 = typeof translateCompactText === 'function' ? translateCompactText : function(k) { return k; };
                snippetMeta.textContent = meta || tFn2('暂无邮件摘要');
                snippetMeta.title = meta;
            }
        }

        function reapplyAllCompactPollUI() {
            if (typeof pollMap === 'undefined') return;
            pollMap.forEach(function(state, email) {
                if (!state) return;
                var remaining = state.maxCount > 0 ? Math.max(0, state.maxCount - state.pollCount) : 0;
                updateCompactPollUI(email, 'polling', remaining);
            });
        }

        // ── 注册统一 UI 回调到统一引擎（支持标准模式和简洁模式） ──

        if (typeof registerPollUICallbacks === 'function') {
            registerPollUICallbacks({
                onPollStart: function(email, maxCount, opts) {
                    var view = typeof mailboxViewMode !== 'undefined' ? mailboxViewMode : '';
                    if (view === 'compact') {
                        updateCompactPollUI(email, 'polling', maxCount);
                    } else {
                        if (typeof showStandardPollDot === 'function') showStandardPollDot(email);
                        // 标准模式：仅首次启动且非静默时 Toast 提示
                        // reapply=true 表示 UI 刷新重绘，silent=true 表示批量启动（不弹单条 Toast）
                        if (!opts || (!opts.reapply && !opts.silent)) {
                            var countText = maxCount > 0 ? ('，最多 ' + maxCount + ' 次') : '';
                            if (typeof showToast === 'function') showToast(translateCompactText('开始监听') + ' ' + email + ' ' + translateCompactText('的新邮件') + countText, 'info');
                        }
                    }
                },
                onPollStop: function(email) {
                    var view = typeof mailboxViewMode !== 'undefined' ? mailboxViewMode : '';
                    if (view === 'compact') {
                        updateCompactPollUI(email, 'stopped', null);
                    } else {
                        if (typeof hideStandardPollDot === 'function') hideStandardPollDot(email);
                    }
                },
                onPollTick: function(email, remainingCount) {
                    var view = typeof mailboxViewMode !== 'undefined' ? mailboxViewMode : '';
                    if (view === 'compact') {
                        updateCompactPollUI(email, 'polling', remainingCount);
                    }
                    // 标准模式不需要倒计时文字
                },
                onNewEmail: function(email, summary) {
                    var view = typeof mailboxViewMode !== 'undefined' ? mailboxViewMode : '';
                    if (view === 'compact') {
                        updateSingleRowFromCache(email, summary);
                    }
                    // 标准模式：引擎已自动处理验证码提取+复制
                },
                onAccountCheck: function(email) {
                    var accounts = typeof getCompactVisibleAccounts === 'function' ? getCompactVisibleAccounts() : [];
                    if (!accounts.some(function(a) { return a.email === email; })) return false;
                    var view = typeof mailboxViewMode !== 'undefined' ? mailboxViewMode : '';
                    if (view === 'compact') {
                        // DOM 检查（软检查：找不到只跳过，不停止）
                        return !!findCompactAccountRow(email);
                    }
                    // 标准模式：账号存在于缓存即可，不需要 DOM 检查
                    return true;
                }
            });
        }

        // ── 向后兼容函数别名（供 main.js 和旧代码调用） ──

        function startCompactAutoPoll(email, opts) {
            if (typeof startPoll === 'function') return startPoll(email, opts);
        }

        function stopCompactAutoPoll(email, toastMsg, toastType) {
            if (typeof stopPoll === 'function') return stopPoll(email, toastMsg, toastType);
        }

        function stopAllCompactAutoPolls() {
            if (typeof stopAllPolls === 'function') return stopAllPolls();
        }

        function applyCompactPollSettingsToRunningPolls(newSettings) {
            if (typeof applyPollSettingsToRunning === 'function') return applyPollSettingsToRunning(newSettings);
        }

        function applyCompactPollSettings(settings) {
            if (typeof applyPollSettings === 'function') return applyPollSettings(settings);
        }

        // ── 统一事件监听（标准模式和简洁模式共用） ──

        window.addEventListener('email-copied', function(e) {
            var email = e && e.detail && e.detail.email;
            if (!email) return;
            var enabled = typeof pollEnabled !== 'undefined' ? pollEnabled : false;
            console.debug('[email-copied] email:', email, 'pollEnabled:', enabled, 'mailboxViewMode:', typeof mailboxViewMode !== 'undefined' ? mailboxViewMode : 'undefined');
            if (!enabled) return;
            // 不限制视图模式：标准模式和简洁模式均触发轮询
            var isTemp = typeof isTempEmailGroup !== 'undefined' ? isTempEmailGroup : false;
            if (isTemp) return;
            var accounts = typeof getCompactVisibleAccounts === 'function' ? getCompactVisibleAccounts() : [];
            var found = accounts.some(function(a) { return a.email === email; });
            if (!found) return;
            if (typeof startPoll === 'function') startPoll(email);
        });
