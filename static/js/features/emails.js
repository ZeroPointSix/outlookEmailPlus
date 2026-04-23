        // ==================== 邮件相关 ====================

        // 模块内变量：存储上次获取邮件失败的错误详情
        let lastFetchErrorDetails = {};

        function resolveEmailSortTimestamp(email) {
            const rawDate = email && (email.receivedDateTime || email.date || email.created_at || email.received_at);
            const parsed = Date.parse(String(rawDate || ''));
            return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;
        }

        function sortEmailsByNewestFirst(list) {
            const source = Array.isArray(list) ? list : [];
            return source
                .map((item, index) => ({ item, index, timestamp: resolveEmailSortTimestamp(item) }))
                .sort((a, b) => (b.timestamp - a.timestamp) || (a.index - b.index))
                .map(entry => entry.item);
        }

        if (typeof window !== 'undefined') {
            window.sortEmailsByNewestFirst = sortEmailsByNewestFirst;
        }

        // 加载邮件列表
        async function loadEmails(email, forceRefresh = false) {
            const container = document.getElementById('emailList');

            // 切换账号/刷新时清除选中状态
            selectedEmailIds.clear();
            updateEmailBatchActionBar();

            // 检查缓存
            const cacheKey = `${email}_${currentFolder}`;
            if (!forceRefresh && emailListCache[cacheKey]) {
                const cache = emailListCache[cacheKey];
                currentEmails = sortEmailsByNewestFirst(cache.emails || []);
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
                return;
            }

            // 禁用按钮
            const refreshBtn = document.querySelector('.refresh-btn');
            const folderTabs = document.querySelectorAll('.email-tab');
            if (refreshBtn) {
                refreshBtn.disabled = true;
                refreshBtn.textContent = translateAppTextLocal('获取中...');
            }
            folderTabs.forEach(tab => tab.disabled = true);

            // 重置分页状态
            currentSkip = 0;
            hasMoreEmails = true;

            container.innerHTML = `<div class="loading-overlay"><span class="spinner"></span> ${translateAppTextLocal('获取中…')}</div>`;

            try {
                // 每次只查询20封邮件
                const response = await fetch(
                    `/api/emails/${encodeURIComponent(email)}?method=${currentMethod}&folder=${currentFolder}&skip=0&top=20`
                );
                const data = await response.json();

                if (data.success) {
                    const sortedEmails = sortEmailsByNewestFirst(data.emails || []);
                    currentEmails = sortedEmails;
                    currentMethod = data.method === 'Graph API' ? 'graph' : 'imap';
                    hasMoreEmails = data.has_more;
                    if (typeof syncAccountSummaryToAccountCache === 'function' && data.account_summary) {
                        syncAccountSummaryToAccountCache(email, data.account_summary);
                    }

                    if (typeof syncAccountSummaryToAccountCache === 'function' && data.account_summary) {
                        syncAccountSummaryToAccountCache(email, data.account_summary);
                    }

                    // 保存到缓存
                    emailListCache[cacheKey] = {
                        emails: currentEmails,
                        has_more: hasMoreEmails,
                        skip: currentSkip,
                        method: currentMethod
                    };

                    // 显示使用的方法和邮件数量
                    const methodTag = document.getElementById('methodTag');
                    methodTag.textContent = data.method;
                    methodTag.style.display = 'inline';

                    document.getElementById('emailCount').textContent = `(${data.emails.length})`;

                    document.getElementById('emailCount').textContent = `(${currentEmails.length})`;

                    renderEmailList(currentEmails);
                } else {
                    // 显示详细的多方法失败弹框
                    if (data.details) {
                        showEmailFetchErrorModal(data.details);
                    } else {
                        handleApiError(data, '获取邮件失败');
                    }
                    container.innerHTML = `
                        <div class="empty-state">
                            <span class="empty-icon">⚠️</span><p>${translateAppTextLocal('获取邮件失败，')}<a href="javascript:void(0)" id="showEmailErrorLink" style="color:#409eff;text-decoration:underline;">${translateAppTextLocal('点击查看详情')}</a></p>
                        </div>
                    `;
                    lastFetchErrorDetails = data.details || {};
                    // 绑定事件监听器
                    const errorLink = document.getElementById('showEmailErrorLink');
                    if (errorLink) {
                        errorLink.addEventListener('click', () => showEmailFetchErrorModal(lastFetchErrorDetails));
                    }
                }
            } catch (error) {
                console.error('加载邮件列表失败:', error);
                container.innerHTML = `
                    <div class="empty-state">
                        <span class="empty-icon">⚠️</span><p>${translateAppTextLocal('网络错误，请重试')}</p>
                    </div>
                `;
            } finally {
                // 启用按钮
                if (refreshBtn) {
                    refreshBtn.disabled = false;
                    refreshBtn.textContent = translateAppTextLocal('获取邮件');
                }
                folderTabs.forEach(tab => tab.disabled = false);
            }
        }

        // 渲染邮件列表
        // Selected email IDs
        let selectedEmailIds = new Set();
        let isBatchSelectMode = false;

        function renderEmailList(emails, options = {}) {
            const container = document.getElementById('emailList');
            const actionBar = document.getElementById('emailBatchActionBar');

            if (emails.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <span class="empty-icon">📭</span>
                        <p>${translateAppTextLocal('收件箱为空')}</p>
                    </div>
                `;
                selectedEmailIds.clear();
                updateEmailBatchActionBar();
                if (options.scrollToTop !== false) container.scrollTop = 0;
                return;
            }

            const clickHandler = isTempEmailGroup ? 'getTempEmailDetail' : 'selectEmail';
            // Bug #24 修复：用 currentEmailDetail.id 保留 active 状态
            const currentActiveId = currentEmailDetail ? currentEmailDetail.id : null;

            container.innerHTML = emails.map((email, index) => {
                const isChecked = selectedEmailIds.has(email.id);
                const isActive = currentActiveId && email.id === currentActiveId;
                const initial = (email.from || '?')[0].toUpperCase();
                return `
                <div class="email-item ${email.is_read === false ? 'unread' : ''} ${isActive ? 'active' : ''}"
                     onclick="${clickHandler}('${email.id}', ${index})">
                    <div class="email-checkbox-wrapper" onclick="event.stopPropagation(); toggleEmailSelection('${email.id}')">
                        <input type="checkbox" class="email-checkbox" ${isChecked ? 'checked' : ''} style="pointer-events: none;">
                    </div>
                    <div class="email-avatar">${initial}</div>
                    <div class="email-meta">
                        <div class="email-from">${escapeHtml(email.from)}</div>
                        <div class="email-subject">${escapeHtml(email.subject || '无主题')}</div>
                        <div class="email-preview">${escapeHtml(email.body_preview || '')}</div>
                    </div>
                    <div class="email-time">${formatDate(email.date)}</div>
                </div>
            `}).join('');

            // Issue #52: 加载/刷新后自动回到列表顶部，避免滚动位置乱跑
            if (options.scrollToTop !== false) container.scrollTop = 0;

            updateEmailBatchActionBar();
        }

        function toggleEmailSelection(emailId) {
            if (selectedEmailIds.has(emailId)) {
                selectedEmailIds.delete(emailId);
            } else {
                selectedEmailIds.add(emailId);
            }

            // Re-render to update checkbox UI (or efficiently update DOM)
            // For simplicity, we just find the checkbox and update it
            // implementation below is cheap
            renderEmailList(currentEmails, { scrollToTop: false });
        }

        function updateEmailBatchActionBar() {
            const bar = document.getElementById('emailBatchActionBar');
            if (selectedEmailIds.size > 0) {
                bar.style.display = 'flex';
                document.getElementById('emailSelectedCount').textContent =
                    typeof formatSelectedItemsLabel === 'function'
                        ? formatSelectedItemsLabel(selectedEmailIds.size)
                        : `已选 ${selectedEmailIds.size} 项`;
            } else {
                bar.style.display = 'none';
            }
        }

        function isTempEmailSource(source) {
            const normalizedSource = String(source || '').trim().toLowerCase();
            return normalizedSource === 'temp' || normalizedSource === 'temp-mail' || normalizedSource === 'temp_mail';
        }

        function resolveEmailDetailSource(options = {}) {
            if (isTempEmailSource(options?.source)) {
                return 'temp';
            }
            return isTempEmailGroup || currentPage === 'temp-emails' ? 'temp' : 'mailbox';
        }

        // detail-focus 断点阈值：低于此宽度时切换列表/详情为互斥模式
        // 注意: CSS 平板断点为 1024px，此处 900px 为功能切换阈值而非布局断点
        function isNarrowWorkspaceViewport() {
            return window.innerWidth <= 900;
        }

        // 邮箱列表/详情互斥切换 — 窄视口下点击邮件时隐藏列表、全宽展示详情
        // 被调用方: accounts.js(切换账户重置)、emails.js(点击邮件/返回列表)
        // CSS 配套: #emailListPanel.detail-focus 规则(平板+移动端)
        function setMailboxDetailFocus(active) {
            const panel = document.getElementById('emailListPanel');
            if (!panel) return;
            const shouldFocus = Boolean(active) && isNarrowWorkspaceViewport();
            panel.classList.toggle('detail-focus', shouldFocus);
            // 内联样式作为 CSS 的即时保障，避免布局闪烁
            const listEl = document.getElementById('emailList');
            const detailEl = document.getElementById('emailDetailSection');
            if (shouldFocus) {
                if (listEl) listEl.style.display = 'none';
                if (detailEl) detailEl.style.display = 'flex';
            } else if (isNarrowWorkspaceViewport()) {
                if (listEl) listEl.style.display = '';
                if (detailEl) detailEl.style.display = 'none';
            } else {
                // 桌面端：退回 CSS 控制，清除内联覆盖
                if (listEl) listEl.style.display = '';
                if (detailEl) detailEl.style.display = '';
            }
        }

        // 临时邮箱消息列表/详情互斥切换 — 与 setMailboxDetailFocus 对称设计
        // 被调用方: temp_emails.js(点击消息/刷新列表)、emails.js(切换回邮箱列表)
        // CSS 配套: .workspace.workspace-temp-emails.detail-focus 规则(平板+移动端)
        function setTempDetailFocus(active) {
            const workspace = document.querySelector('.workspace.workspace-temp-emails');
            const messagePanel = document.getElementById('tempEmailMessagePanel');
            const detailPanel = document.getElementById('tempEmailDetailSection');
            if (!workspace) return;

            const shouldFocus = Boolean(active) && isNarrowWorkspaceViewport();
            workspace.classList.toggle('detail-focus', shouldFocus);

            if (shouldFocus) {
                if (messagePanel) messagePanel.style.display = 'none';
                if (detailPanel) detailPanel.style.display = 'flex';
            } else if (isNarrowWorkspaceViewport()) {
                if (messagePanel) messagePanel.style.display = '';
                if (detailPanel) detailPanel.style.display = 'none';
            } else {
                if (messagePanel) messagePanel.style.display = '';
                if (detailPanel) detailPanel.style.display = '';
            }
        }

        function getEmailDetailRefs(options = {}) {
            const source = resolveEmailDetailSource(options);
            if (source === 'temp') {
                return {
                    source,
                    section: document.getElementById('tempEmailDetailSection'),
                    toolbar: document.getElementById('tempEmailDetailToolbar'),
                    container: document.getElementById('tempEmailDetail'),
                    trustCheckbox: document.getElementById('tempEmailTrustCheckbox'),
                    iframeId: 'tempEmailBodyFrame',
                };
            }

            return {
                source,
                section: document.getElementById('emailDetailSection'),
                toolbar: document.getElementById('emailDetailToolbar'),
                container: document.getElementById('emailDetail'),
                trustCheckbox: document.getElementById('trustEmailCheckbox'),
                iframeId: 'emailBodyFrame',
            };
        }

        function showEmailDetailContainer(options = {}) {
            const refs = getEmailDetailRefs(options);
            if (refs.source === 'mailbox') {
                if (typeof showEmailDetailSection === 'function') {
                    showEmailDetailSection();
                }
                return;
            }
            if (refs.section) {
                refs.section.style.display = 'flex';
            }
        }

        function hideEmailDetailContainer(options = {}) {
            const refs = getEmailDetailRefs(options);
            if (refs.source === 'mailbox') {
                if (typeof hideEmailDetailSection === 'function') {
                    hideEmailDetailSection();
                }
                return;
            }
            if (refs.section) {
                refs.section.style.display = 'none';
            }
        }

        function setEmailDetailToolbarVisibility(visible, options = {}) {
            const refs = getEmailDetailRefs(options);
            if (visible) {
                showEmailDetailContainer(options);
            }
            if (refs.toolbar) {
                refs.toolbar.style.display = visible ? 'flex' : 'none';
            }
        }

        function resetEmailDetailState(options = {}) {
            const refs = getEmailDetailRefs(options);
            if (refs.container) {
                refs.container.innerHTML = `
                    <div class="empty-state">
                        <span class="empty-icon">📄</span>
                        <p>${translateAppTextLocal('选择一封邮件查看详情')}</p>
                    </div>
                `;
            }
            if (refs.trustCheckbox) {
                refs.trustCheckbox.checked = false;
            }
            setEmailDetailToolbarVisibility(false, options);
        }

        function buildDetailVerificationOptions(options = {}) {
            return resolveEmailDetailSource(options) === 'temp'
                ? { ...options, source: 'temp' }
                : { ...options, source: 'mailbox' };
        }

        function extractVerificationFallbackFromDetail(options = {}) {
            const refs = getEmailDetailRefs(options);
            const iframe = refs.container ? refs.container.querySelector('.email-body-frame') : null;
            const textBody = refs.container ? refs.container.querySelector('.email-body-text') : null;

            let bodyText = '';
            if (iframe && iframe.contentDocument && iframe.contentDocument.body) {
                bodyText = iframe.contentDocument.body.innerText || iframe.contentDocument.body.textContent || '';
            } else if (textBody) {
                bodyText = textBody.textContent || '';
            }

            if (!bodyText.trim()) {
                return null;
            }

            const codePatterns = [
                /(?:验证码|verification code|code|码|PIN|OTP|密码)[：:\s]*([A-Za-z0-9]{4,8})/i,
                /\b(\d{4,8})\b/,
                /(?:code|码)[：:\s]*([A-Za-z0-9-]{4,12})/i,
            ];
            const urlPattern = /https?:\/\/[^\s<>"')\]]+/gi;
            const urls = bodyText.match(urlPattern) || [];
            const filteredUrls = urls.filter(u => !u.includes('unsubscribe') && !u.includes('privacy') && !u.includes('terms'));

            let code = '';
            for (const pattern of codePatterns) {
                const match = bodyText.match(pattern);
                if (match && match[1]) {
                    code = match[1];
                    break;
                }
            }

            let formatted = '';
            if (code) formatted += `验证码: ${code}`;
            if (filteredUrls.length > 0) {
                if (formatted) formatted += '\n';
                formatted += `链接: ${filteredUrls[0]}`;
            }

            if (!formatted) {
                return null;
            }

            return {
                verification_code: code,
                verification_link: filteredUrls[0] || '',
                formatted,
                copyText: code || filteredUrls[0] || formatted,
                displayValue: code || filteredUrls[0] || formatted,
            };
        }

        async function confirmBatchDeleteEmails() {
            if (selectedEmailIds.size === 0) return;

            if (!confirm(`确定要永久删除选中的 ${selectedEmailIds.size} 封邮件吗？此操作不可恢复！`)) {
                return;
            }

            await deleteEmails(Array.from(selectedEmailIds));
        }

        async function confirmDeleteCurrentEmail() {
            if (!currentEmailDetail || !currentEmailDetail.id) return;

            if (!confirm('确定要永久删除这封邮件吗？此操作不可恢复！')) {
                return;
            }

            if (resolveEmailDetailSource() === 'temp') {
                await deleteCurrentTempEmailMessage();
                return;
            }

            await deleteEmails([currentEmailDetail.id]);
        }

        async function deleteEmails(ids) {
            showToast('正在删除...', 'info');

            try {
                const response = await fetch('/api/emails/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        email: currentAccount,
                        ids: ids
                    })
                });

                const result = await response.json();

                if (result.success) {
                    showToast(`成功删除 ${result.success_count} 封邮件`);

                    // Remove deleted emails from currentEmails
                    const deletedIds = new Set(ids); // Ideally result should return what was deleted
                    currentEmails = currentEmails.filter(e => !deletedIds.has(e.id));
                    selectedEmailIds.clear();

                    renderEmailList(currentEmails, { scrollToTop: false });

                    // If current viewed email was deleted, clear view
                    if (currentEmailDetail && deletedIds.has(currentEmailDetail.id)) {
                        const refs = getEmailDetailRefs({ source: 'mailbox' });
                        refs.container.innerHTML = `
                            <div class="empty-state">
                                <span class="empty-icon">🗑️</span><p>邮件已删除</p>
                            </div>
                        `;
                        setEmailDetailToolbarVisibility(false, { source: 'mailbox' });
                    }

                    // If errors
                    if (result.failed_count > 0) {
                        console.warn('Deletion errors:', result.errors);
                        showToast(`部分删除失败 (${result.failed_count} 封)`, 'warning');
                    }
                } else {
                    const msg = window.resolveApiErrorMessage
                        ? window.resolveApiErrorMessage(result.error || result, '删除失败', 'Delete failed')
                        : (typeof result.error === 'string' ? result.error : (result.error && result.error.message) || '未知错误');
                    showToast(`删除失败: ${msg}`, 'error', result.error && typeof result.error === 'object' ? result.error : null);
                }
            } catch (e) {
                showToast('网络错误', 'error');
                console.error(e);
            }
        }

        async function deleteCurrentTempEmailMessage() {
            if (!currentEmailDetail || !currentEmailDetail.id || !currentAccount) {
                return;
            }

            showToast('正在删除...', 'info');

            try {
                const response = await fetch(
                    `/api/temp-emails/${encodeURIComponent(currentAccount)}/messages/${encodeURIComponent(currentEmailDetail.id)}`,
                    { method: 'DELETE' }
                );
                const result = await response.json();

                if (!result.success) {
                    handleApiError(result, '删除失败');
                    return;
                }

                const deletedId = currentEmailDetail.id;
                currentEmails = currentEmails.filter(email => email.id !== deletedId);
                currentEmailDetail = null;
                renderEmailList(currentEmails, { scrollToTop: false });

                const tempContainer = document.getElementById('tempEmailMessageList');
                if (tempContainer && typeof renderTempEmailMessageList === 'function') {
                    renderTempEmailMessageList(tempContainer, currentEmails);
                }

                const emailCount = document.getElementById('emailCount');
                if (emailCount) {
                    emailCount.textContent = `(${currentEmails.length})`;
                }

                resetEmailDetailState({ source: 'temp' });
                showToast(translateAppTextLocal('邮件已删除'), 'success');
            } catch (error) {
                console.error('删除临时邮件失败:', error);
                showToast(translateAppTextLocal('网络错误，请重试'), 'error');
            }
        }

        // 选择邮件
        async function selectEmail(messageId, index) {
            document.querySelectorAll('.email-item').forEach((item, i) => {
                item.classList.toggle('active', i === index);
            });

            // 这里不重置 currentEmailDetail，等到 fetch 成功后再设置

            // 重置信任模式
            const refs = getEmailDetailRefs({ source: 'mailbox' });
            if (refs.trustCheckbox) {
                refs.trustCheckbox.checked = false;
            }
            isTrustedMode = false;

            // 显示工具栏
            setEmailDetailToolbarVisibility(true, { source: 'mailbox' });
            setMailboxDetailFocus(true);

            // 加载邮件详情
            const container = refs.container;
            container.innerHTML = '<div class="loading-overlay"><span class="spinner"></span></div>';

            try {
                const response = await fetch(`/api/email/${encodeURIComponent(currentAccount)}/${encodeURIComponent(messageId)}?method=${currentMethod}&folder=${currentFolder}`);
                const data = await response.json();

                if (data.success) {
                    currentEmailDetail = data.email;
                    try {
                        renderEmailDetail(data.email, { source: 'mailbox' });
                    } catch (renderError) {
                        console.error('渲染邮件详情失败:', renderError);
                        // 渲染失败时回退为纯文本显示
                        container.innerHTML = `
                            <div class="empty-state">
                                <span class="empty-icon">⚠️</span><p>邮件渲染失败: ${escapeHtml(renderError.message || '未知错误')}</p>
                            </div>
                        `;
                    }
                } else {
                    handleApiError(data, '加载邮件详情失败');
                    container.innerHTML = `
                        <div class="empty-state">
                            <span class="empty-icon">⚠️</span><p>${window.resolveApiErrorMessage ? window.resolveApiErrorMessage(data.error || data, '加载失败', 'Load failed') : (data.error && data.error.message ? data.error.message : '加载失败')}</p>
                        </div>
                    `;
                }
            } catch (error) {
                console.error('加载邮件详情失败:', error);
                container.innerHTML = `
                    <div class="empty-state">
                        <span class="empty-icon">⚠️</span><p>网络错误，请重试 (${escapeHtml(error.message || '')})</p>
                    </div>
                `;
            }
        }

        // 渲染邮件详情
        function normalizeEmailInlineResourceKey(value) {
            if (!value) return '';
            let normalized = String(value).trim();
            if (!normalized) return '';
            if (normalized.toLowerCase().startsWith('cid:')) {
                normalized = normalized.slice(4);
            }
            if (normalized.startsWith('<') && normalized.endsWith('>')) {
                normalized = normalized.slice(1, -1);
            }
            return normalized.trim().toLowerCase();
        }

        function resolveEmailInlineResource(resourceMap, reference) {
            if (!resourceMap || typeof resourceMap !== 'object') return '';
            const normalizedKey = normalizeEmailInlineResourceKey(reference);
            if (!normalizedKey) return '';
            return resourceMap[normalizedKey] || '';
        }

        function rewriteEmailInlineImages(html, email) {
            const sourceHtml = typeof html === 'string' ? html : '';
            const resourceMap = email && email.inline_resources && typeof email.inline_resources === 'object'
                ? email.inline_resources
                : null;

            if (!sourceHtml || !resourceMap || Object.keys(resourceMap).length === 0 || typeof DOMParser === 'undefined') {
                return sourceHtml;
            }

            try {
                const parser = new DOMParser();
                const doc = parser.parseFromString(sourceHtml, 'text/html');
                const images = doc.querySelectorAll('img[src]');

                images.forEach(img => {
                    const originalSrc = img.getAttribute('src') || '';
                    if (!/^cid:/i.test(originalSrc)) return;
                    const resolvedSrc = resolveEmailInlineResource(resourceMap, originalSrc);
                    if (resolvedSrc) {
                        img.setAttribute('src', resolvedSrc);
                    }
                });

                return doc.body ? doc.body.innerHTML : sourceHtml;
            } catch (error) {
                console.warn('重写邮件内联图片失败:', error);
                return sourceHtml;
            }
        }

        function renderEmailDetail(email, options = {}) {
            const refs = getEmailDetailRefs(options);
            const container = refs.container;
            if (!container) {
                return;
            }
            const rawBody = typeof email.body === 'string' ? email.body : '';
            const iframeId = refs.iframeId;

            const isHtml = email.body_type === 'html' ||
                (rawBody && (rawBody.includes('<html') || rawBody.includes('<div') || rawBody.includes('<p>')));

            const bodyContent = isHtml
                ? `<iframe id="${iframeId}" class="email-body-frame" sandbox="allow-same-origin" onload="adjustIframeHeight(this)"></iframe>`
                : `<div class="email-body-text">${escapeHtml(rawBody)}</div>`;

            container.innerHTML = `
                <div class="email-detail-header">
                    <div class="email-detail-subject">${escapeHtml(email.subject || '无主题')}</div>
                    <div class="email-detail-meta">
                        <div class="email-detail-meta-row">
                            <span class="email-detail-meta-label">发件人</span>
                            <span class="email-detail-meta-value">${escapeHtml(email.from)}</span>
                        </div>
                        <div class="email-detail-meta-row">
                            <span class="email-detail-meta-label">收件人</span>
                            <span class="email-detail-meta-value">${escapeHtml(email.to || '-')}</span>
                        </div>
                        ${email.cc ? `
                        <div class="email-detail-meta-row">
                            <span class="email-detail-meta-label">抄送</span>
                            <span class="email-detail-meta-value">${escapeHtml(email.cc)}</span>
                        </div>
                        ` : ''}
                        <div class="email-detail-meta-row">
                            <span class="email-detail-meta-label">时间</span>
                            <span class="email-detail-meta-value">${formatDate(email.date)}</span>
                        </div>
                    </div>
                </div>
                <div class="email-detail-body">
                    ${bodyContent}
                </div>
            `;

            // 如果是 HTML 内容，设置 iframe 内容
            if (isHtml) {
                const iframe = container.querySelector(`#${iframeId}`) || container.querySelector('.email-body-frame');
                if (iframe) {
                    const renderableBody = rewriteEmailInlineImages(rawBody, email);
                    let sanitizedBody;
                    if (isTrustedMode) {
                        sanitizedBody = renderableBody; // 信任模式：不过滤
                    } else if (typeof DOMPurify !== 'undefined') {
                        // 使用 DOMPurify 净化 HTML 内容，防止 XSS 攻击
                        sanitizedBody = DOMPurify.sanitize(renderableBody, {
                            ALLOWED_TAGS: ['a', 'b', 'i', 'u', 'strong', 'em', 'p', 'br', 'div', 'span', 'img', 'table', 'tr', 'td', 'th', 'thead', 'tbody', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'pre', 'code'],
                            ALLOWED_ATTR: ['href', 'src', 'alt', 'title', 'style', 'class', 'width', 'height', 'align', 'border', 'cellpadding', 'cellspacing'],
                            ALLOW_DATA_ATTR: false,
                            ADD_DATA_URI_TAGS: ['img'],
                            ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel|cid):|data:image\/(?:png|gif|jpe?g|webp|bmp|x-icon|vnd\.microsoft\.icon|avif);base64,|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))/i,
                            FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'button'],
                            FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover', 'onfocus', 'onblur']
                        });
                    } else {
                        // DOMPurify 未加载（CDN 不可达），回退为基本过滤
                        console.warn('DOMPurify 未加载，使用基本 HTML 过滤');
                        sanitizedBody = renderableBody
                            .replace(/<script[\s\S]*?<\/script>/gi, '')
                            .replace(/<style[\s\S]*?<\/style>/gi, '')
                            .replace(/on\w+="[^"]*"/gi, '')
                            .replace(/on\w+='[^']*'/gi, '');
                    }

                    const htmlContent = `
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <meta charset="UTF-8">
                            <style>
                                body {
                                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                                    font-size: 15px;
                                    line-height: 1.6;
                                    color: #333;
                                    margin: 0;
                                    padding: 0;
                                    background-color: transparent;
                                }
                                img { max-width: 100%; height: auto; }
                                a { color: var(--clr-primary, #B85C38); }
                            </style>
                        </head>
                        <body>${sanitizedBody}</body>
                        </html>
                    `;
                    iframe.srcdoc = htmlContent;
                }
            }
        }

        // 动态调整 iframe 高度
        function adjustIframeHeight(iframe) {
            try {
                // 多次尝试调整高度，确保内容完全加载
                const adjustHeight = () => {
                    if (iframe.contentDocument && iframe.contentDocument.body) {
                        const body = iframe.contentDocument.body;
                        const html = iframe.contentDocument.documentElement;
                        // 获取实际内容高度（取最大值）
                        const height = Math.max(
                            body.scrollHeight,
                            body.offsetHeight,
                            html.clientHeight,
                            html.scrollHeight,
                            html.offsetHeight
                        );
                        // 设置最小高度为 600px，添加 100px 余量确保长邮件能完整显示
                        iframe.style.height = Math.max(height + 100, 600) + 'px';
                    }
                };

                // 立即调整一次
                adjustHeight();
                // 100ms 后再调整（等待图片等资源加载）
                setTimeout(adjustHeight, 100);
                // 300ms 后再调整
                setTimeout(adjustHeight, 300);
                // 500ms 后再调整（确保所有内容都已加载）
                setTimeout(adjustHeight, 500);
                // 1秒后最后调整一次
                setTimeout(adjustHeight, 1000);
                // 2秒后再次调整（处理延迟加载的内容）
                setTimeout(adjustHeight, 2000);

                // 监听 iframe 内容变化
                if (iframe.contentDocument) {
                    const observer = new MutationObserver(adjustHeight);
                    observer.observe(iframe.contentDocument.body, {
                        childList: true,
                        subtree: true,
                        attributes: true
                    });

                    // 监听图片加载完成事件
                    const images = iframe.contentDocument.querySelectorAll('img');
                    images.forEach(img => {
                        img.addEventListener('load', adjustHeight);
                        img.addEventListener('error', adjustHeight);
                    });
                }
            } catch (e) {
                console.log('Cannot adjust iframe height:', e);
            }
        }

        // 同步邮件列表可见性（新布局简化版）
        function syncEmailListVisibility(visible) {
            // New layout doesn't use the old panel collapse system - no-op
        }

        // 切换邮件列表显示
        function toggleEmailList() {
            const toggleText = document.getElementById('toggleListText');

            isListVisible = !isListVisible;

            if (isListVisible) {
                syncEmailListVisibility(true);
                toggleText.textContent = translateAppTextLocal('隐藏列表');
            } else {
                syncEmailListVisibility(false);
                toggleText.textContent = translateAppTextLocal('显示列表');
            }
        }

        // ==================== 验证码提取（从邮件详情） ====================

        async function extractVerificationFromDetail(buttonElement) {
            if (!currentAccount || typeof copyVerificationInfo !== 'function') {
                showToast('请先选择一个邮箱账号', 'error');
                return false;
            }

            const detailOptions = buildDetailVerificationOptions();
            return copyVerificationInfo(currentAccount, buttonElement, {
                ...detailOptions,
                fallbackExtractor: () => extractVerificationFallbackFromDetail(detailOptions),
            });
        }

        // 全屏查看邮件
        let currentFullscreenEmail = null;

        function openFullscreenEmail() {
            const refs = getEmailDetailRefs();
            const emailDetail = refs.container;
            const modal = document.getElementById('fullscreenEmailModal');
            const content = document.getElementById('fullscreenEmailContent');
            const title = document.getElementById('fullscreenEmailTitle');

            if (!emailDetail) {
                return;
            }

            // 获取当前邮件的标题
            const subjectElement = emailDetail.querySelector('.email-detail-subject');
            if (subjectElement) {
                title.textContent = subjectElement.textContent;
            }

            // 克隆邮件内容
            const emailHeader = emailDetail.querySelector('.email-detail-header');
            const emailBody = emailDetail.querySelector('.email-detail-body');

            if (emailHeader && emailBody) {
                // 清空内容
                content.innerHTML = '';

                // 克隆头部信息
                const headerClone = emailHeader.cloneNode(true);
                content.appendChild(headerClone);

                // 处理邮件正文
                const iframe = emailBody.querySelector('iframe');
                const textContent = emailBody.querySelector('.email-body-text');

                if (iframe) {
                    // 如果是 HTML 邮件，创建新的 iframe
                    const newIframe = document.createElement('iframe');
                    newIframe.id = 'fullscreenEmailBodyFrame';
                    newIframe.style.width = '100%';
                    newIframe.style.border = 'none';
                    newIframe.style.backgroundColor = '#ffffff';

                    // 复制原 iframe 的内容
                    if (iframe.contentDocument) {
                        const htmlContent = iframe.contentDocument.documentElement.outerHTML;
                        newIframe.srcdoc = htmlContent;
                    }

                    content.appendChild(newIframe);

                    // 调整 iframe 高度
                    newIframe.onload = function () {
                        adjustFullscreenIframeHeight(newIframe);
                    };
                } else if (textContent) {
                    // 如果是纯文本邮件，直接克隆
                    const textClone = textContent.cloneNode(true);
                    content.appendChild(textClone);
                }

                // 显示模态框
                modal.classList.add('show');
                document.body.style.overflow = 'hidden';
            }
        }

        // 切换信任模式
        function toggleTrustMode(checkbox) {
            if (checkbox.checked) {
                if (confirm('⚠️ 警告：启用信任模式将直接显示邮件原始内容，不进行任何安全过滤。\n\n这可能包含恶意脚本或不安全的内容。您确定要继续吗？')) {
                    isTrustedMode = true;
                    if (currentEmailDetail) {
                        renderEmailDetail(currentEmailDetail);
                    }
                } else {
                    checkbox.checked = false;
                }
            } else {
                isTrustedMode = false;
                if (currentEmailDetail) {
                    renderEmailDetail(currentEmailDetail);
                }
            }
        }

        function closeFullscreenEmail() {
            const modal = document.getElementById('fullscreenEmailModal');
            modal.classList.remove('show');
            document.body.style.overflow = '';
        }

        function closeFullscreenEmailOnBackdrop(event) {
            // 只有点击背景时才关闭，点击内容区域不关闭
            if (event.target.id === 'fullscreenEmailModal') {
                closeFullscreenEmail();
            }
        }

        function adjustFullscreenIframeHeight(iframe) {
            try {
                const adjustHeight = () => {
                    if (iframe.contentDocument && iframe.contentDocument.body) {
                        const body = iframe.contentDocument.body;
                        const html = iframe.contentDocument.documentElement;
                        const height = Math.max(
                            body.scrollHeight,
                            body.offsetHeight,
                            html.clientHeight,
                            html.scrollHeight,
                            html.offsetHeight
                        );
                        // 全屏模式下设置实际高度，添加余量
                        iframe.style.height = (height + 100) + 'px';
                    }
                };

                // 多次调整高度
                adjustHeight();
                setTimeout(adjustHeight, 100);
                setTimeout(adjustHeight, 300);
                setTimeout(adjustHeight, 500);
                setTimeout(adjustHeight, 1000);

                // 监听内容变化
                if (iframe.contentDocument) {
                    const observer = new MutationObserver(adjustHeight);
                    observer.observe(iframe.contentDocument.body, {
                        childList: true,
                        subtree: true,
                        attributes: true
                    });

                    // 监听图片加载
                    const images = iframe.contentDocument.querySelectorAll('img');
                    images.forEach(img => {
                        img.addEventListener('load', adjustHeight);
                        img.addEventListener('error', adjustHeight);
                    });
                }
            } catch (e) {
                console.log('Cannot adjust fullscreen iframe height:', e);
            }
        }

        // 显示邮件列表（移动端）
        function showEmailList() {
            if (resolveEmailDetailSource() === 'temp') {
                if (typeof setTempDetailFocus === 'function') {
                    setTempDetailFocus(false);
                }
                currentEmailDetail = null;
                isTrustedMode = false;
                resetEmailDetailState({ source: 'temp' });
                hideEmailDetailContainer({ source: 'temp' });
                return;
            }

            setMailboxDetailFocus(false);
            syncEmailListVisibility(true);
            isListVisible = true;
            var t = document.getElementById('toggleListText');
            if (t) t.textContent = translateAppTextLocal('隐藏列表');
            if (typeof hideEmailDetailSection === 'function') {
                hideEmailDetailSection();
            }
        }

        // 刷新邮件
        function refreshEmails() {
            if (currentAccount) {
                if (isTempEmailGroup) {
                    loadTempEmailMessages(currentAccount);
                } else {
                    // 清除当前缓存并强制刷新
                    const cacheKey = `${currentAccount}_${currentFolder}`;
                    delete emailListCache[cacheKey];
                    loadEmails(currentAccount, true);
                }
            } else {
                showToast('请先选择一个邮箱账号', 'error');
            }
        }

        // 复制邮箱地址
        async function copyEmail(email) {
            try {
                if (navigator.clipboard && navigator.clipboard.writeText && window.isSecureContext) {
                    await navigator.clipboard.writeText(email);
                    showToast('邮箱地址已复制', 'success');
                    // 派发 email-copied 事件到 window，供简洁模式轮询引擎监听
                    window.dispatchEvent(new CustomEvent('email-copied', { detail: { email } }));
                    return true;
                }

                const textarea = document.createElement('textarea');
                textarea.value = email;
                textarea.setAttribute('readonly', 'readonly');
                textarea.style.position = 'fixed';
                textarea.style.top = '-9999px';
                textarea.style.left = '-9999px';

                document.body.appendChild(textarea);
                textarea.focus();
                textarea.select();

                const copied = document.execCommand('copy');
                document.body.removeChild(textarea);

                if (!copied) {
                    throw new Error('document.execCommand(copy) returned false');
                }

                showToast('邮箱地址已复制', 'success');
                // 派发 email-copied 事件到 window，供简洁模式轮询引擎监听
                window.dispatchEvent(new CustomEvent('email-copied', { detail: { email } }));
                return true;
            } catch (error) {
                console.error('复制邮箱地址失败:', error);
                showToast('复制失败，请手动复制', 'error');
                return false;
            }
        }

        // 复制当前邮箱
        function copyCurrentEmail() {
            const emailElement = document.getElementById('currentAccountEmail');
            if (emailElement && emailElement.textContent) {
                const email = emailElement.textContent.replace(/\s+\((临时|Temp)\)$/, '').trim();
                copyEmail(email);
            }
        }

        // 退出登录
        function logout() {
            if (confirm('确定要退出登录吗？')) {
                window.location.href = '/logout';
            }
        }

