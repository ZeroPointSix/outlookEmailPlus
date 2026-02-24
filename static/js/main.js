// 全局状态
        let csrfToken = null;
        let currentAccount = null;
        let currentGroupId = null;
        let currentEmails = [];
        let currentMethod = 'graph';
        let currentFolder = 'inbox'; // 当前文件夹：inbox 或 deleteditems
        let isListVisible = true;
        let groups = [];
        let accountsCache = {}; // 缓存各分组的邮箱列表
        let editingGroupId = null;
        let selectedColor = '#1a1a1a';
        let isTempEmailGroup = false; // 是否是临时邮箱分组
        let tempEmailGroupId = null; // 临时邮箱分组 ID
        let isLoadingMore = false; // 是否正在加载更多邮件
        let hasMoreEmails = true; // 是否还有更多邮件
        let currentSkip = 0; // 当前分页偏移量
        let lastRefreshTime = null; // 上次刷新时间（模块内变量，不再使用window.lastRefreshTime）

        // 缓存与信任模式
        let emailListCache = {}; // 结构: { "account_folder": { emails: [], hasMore: bool, skip: int, method: str, count: int } }
        let currentEmailDetail = null; // 当前查看的邮件详细数据
        let isTrustedMode = false; // 是否处于信任模式（不过滤 HTML）

        // 轮询相关
        let pollingTimer = null; // 轮询定时器
        let pollingCount = 0; // 当前轮询次数
        let maxPollingCount = 5; // 最大轮询次数
        let pollingInterval = 10; // 轮询间隔（秒）
        let isPolling = false; // 是否正在轮询
        let knownEmailIds = new Set(); // 已知的邮件ID集合

        // ==================== CSRF 防护 ====================

        // 初始化 CSRF Token
        async function initCSRFToken() {
            try {
                const response = await fetch('/api/csrf-token');
                const data = await response.json();
                csrfToken = data.csrf_token;
                if (data.csrf_disabled) {
                    console.warn('CSRF protection is disabled. Install flask-wtf for better security.');
                }
            } catch (error) {
                console.error('Failed to initialize CSRF token:', error);
            }
        }

        // 包装 fetch 请求，自动添加 CSRF Token
        const originalFetch = window.fetch;
        window.fetch = function (url, options = {}) {
            // 只对非 GET 请求添加 CSRF Token
            if (options.method && options.method.toUpperCase() !== 'GET' && csrfToken) {
                options.headers = options.headers || {};
                if (options.headers instanceof Headers) {
                    options.headers.append('X-CSRFToken', csrfToken);
                } else {
                    options.headers['X-CSRFToken'] = csrfToken;
                }
            }
            return originalFetch(url, options);
        };

        // 初始化
        document.addEventListener('DOMContentLoaded', async function () {
            // 初始化 CSRF Token
            await initCSRFToken();

            closeAllModals(); // 修复：应用启动时关闭所有模态框，防止浏览器缓存导致残留的模态框背景层
            loadGroups();
            if (typeof loadTags === 'function') {
                loadTags();
            }
            initColorPicker();
            initColorPicker();
            initEmailListScroll();

            // 初始化轮询设置
            initPollingSettings();

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
            loadingDiv.className = 'loading loading-small';
            loadingDiv.id = 'loadingMore';
            loadingDiv.innerHTML = '<div class="loading-spinner"></div>';
            emailList.appendChild(loadingDiv);

            // 禁用按钮
            const refreshBtn = document.querySelector('.refresh-btn');
            const folderTabs = document.querySelectorAll('.folder-tab');
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
                    currentEmails = currentEmails.concat(data.emails);
                    hasMoreEmails = data.has_more;

                    // 移除加载状态
                    const loadingEl = document.getElementById('loadingMore');
                    if (loadingEl) loadingEl.remove();

                    // 重新渲染邮件列表
                    renderEmailList(currentEmails);

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
                        loadingEl.innerHTML = '<div style="text-align:center;padding:20px;color:#999;font-size:13px;">没有更多邮件了</div>';
                    }
                }
            } catch (error) {
                const loadingEl = document.getElementById('loadingMore');
                if (loadingEl) loadingEl.remove();
                showToast('加载失败', 'error');
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
            document.querySelectorAll('.folder-tab').forEach(tab => {
                tab.classList.toggle('active', tab.dataset.folder === folder);
            });

            const cacheKey = `${currentAccount}_${folder}`;

            // 检查是否有缓存
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
                // 清空邮件列表，显示提示
                document.getElementById('emailList').innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">📬</div>
                        <div class="empty-state-text">点击"获取邮件"按钮获取${folder === 'inbox' ? '收件箱' : '垃圾邮件'}</div>
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
                showToast('请输入有效的十六进制颜色（如 #FF5500）', 'error');
            }
        }

        // 显示消息提示
        function showToast(message, type = 'info', errorDetail = null) {
            const toast = document.getElementById('toast');
            toast.innerHTML = '';

            // Message span
            const messageSpan = document.createElement('span');
            messageSpan.textContent = message;
            toast.appendChild(messageSpan);

            if (errorDetail && type === 'error') {
                const detailLink = document.createElement('a');
                detailLink.href = 'javascript:void(0)';
                detailLink.textContent = ' [详情]';
                detailLink.style.color = '#ffdddd';
                detailLink.style.textDecoration = 'underline';
                detailLink.style.marginLeft = '8px';
                detailLink.onclick = function (e) {
                    e.stopPropagation();
                    showErrorDetailModal(errorDetail);
                };
                toast.appendChild(detailLink);

                // Ensure the toast remains visible long enough for the user to click the link
                clearTimeout(toast.timer);
                toast.timer = setTimeout(() => {
                    toast.className = 'toast';
                }, 8000); // 8 seconds for errors with details
            } else {
                clearTimeout(toast.timer);
                toast.timer = setTimeout(() => {
                    toast.className = 'toast';
                }, 3000); // 3 seconds for regular messages
            }
            toast.className = 'toast show ' + type;
        }

        // 显示刷新错误信息
        function showRefreshError(accountId, errorMessage, accountEmail) {
            document.getElementById('refreshErrorModal').classList.add('show');
            document.getElementById('refreshErrorEmail').textContent = `账号：${accountEmail || '未知'}`;
            document.getElementById('refreshErrorMessage').textContent = errorMessage;
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
            document.getElementById('errorModalUserMessage').textContent = error.message || '发生未知错误';
            document.getElementById('errorModalCode').textContent = error.code || '-';
            document.getElementById('errorModalType').textContent = error.type || '-';
            document.getElementById('errorModalStatus').textContent = error.status || '-';
            document.getElementById('errorModalTraceId').textContent = error.trace_id || '-';

            const detailsEl = document.getElementById('errorModalDetails');
            const detailsContainer = document.getElementById('errorModalDetailsContainer');
            const toggleBtn = document.getElementById('toggleTraceBtn');

            detailsEl.textContent = error.details || '暂无详细技术堆栈信息';

            // 重置堆栈显示状态
            detailsContainer.style.display = 'none';
            toggleBtn.textContent = '显示堆栈/细节';
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
                btn.textContent = '隐藏堆栈/细节';
            } else {
                container.style.display = 'none';
                btn.textContent = '显示堆栈/细节';
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

            const fullErrorText = `
【用户错误信息】
${userMessage}

【错误详情】
Code: ${code}
Type: ${type}
Status: ${status}
Trace ID: ${traceId}

【技术堆栈/细节】
${details}
            `.trim();

            navigator.clipboard.writeText(fullErrorText).then(() => {
                showToast('错误详情已复制', 'success');
            }).catch(() => {
                // 降级方案
                const textarea = document.createElement('textarea');
                textarea.value = fullErrorText;
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
                showToast('错误详情已复制', 'success');
            });
        }

        // 统一处理 API 响应错误
        function handleApiError(data, defaultMessage = '请求失败') {
            if (!data.success) {
                // 检查是否是统一错误格式
                if (data.error && data.error.message) {
                    const error = data.error;
                    // 使用后端提供的 message 作为用户友好信息
                    const userMessage = error.message;

                    // 调用 showToast 携带完整的错误对象
                    showToast(userMessage, 'error', error);
                } else {
                    // 兼容旧的或非标准错误格式
                    const errorMessage = data.error || defaultMessage;
                    showToast(errorMessage, 'error');
                }
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
            if (!dateStr) return '';
            try {
                const date = new Date(dateStr);
                if (isNaN(date.getTime())) return dateStr;

                const now = new Date();
                const isToday = date.toDateString() === now.toDateString();

                if (isToday) {
                    return '今天 ' + date.toLocaleTimeString('zh-CN', {
                        timeZone: 'Asia/Shanghai',
                        hour: '2-digit',
                        minute: '2-digit'
                    });
                } else {
                    return date.toLocaleDateString('zh-CN', {
                        timeZone: 'Asia/Shanghai',
                        year: 'numeric',
                        month: 'long',
                        day: 'numeric'
                    }) + ' ' + date.toLocaleTimeString('zh-CN', {
                        timeZone: 'Asia/Shanghai',
                        hour: '2-digit',
                        minute: '2-digit'
                    });
                }
            } catch (e) {
                return dateStr;
            }
        }

        // ==================== OAuth Refresh Token 相关 ====================

        // 显示获取 Refresh Token 模态框
        async function showGetRefreshTokenModal() {
            document.getElementById('getRefreshTokenModal').classList.add('show');

            // 重置表单
            document.getElementById('redirectUrlInput').value = '';
            document.getElementById('refreshTokenResult').style.display = 'none';
            document.getElementById('refreshTokenOutput').value = '';

            // 重置按钮状态
            const btn = document.getElementById('exchangeTokenBtn');
            btn.disabled = false;
            btn.textContent = '换取 Token';
            btn.style.display = '';

            // 获取授权 URL
            try {
                const response = await fetch('/api/oauth/auth-url');
                const data = await response.json();

                if (data.success) {
                    document.getElementById('authUrlInput').value = data.auth_url;
                } else {
                    showToast('获取授权链接失败', 'error');
                }
            } catch (error) {
                showToast('获取授权链接失败', 'error');
            }
        }

        // 隐藏获取 Refresh Token 模态框
        function hideGetRefreshTokenModal() {
            document.getElementById('getRefreshTokenModal').classList.remove('show');
        }

        // 复制授权 URL
        function copyAuthUrl() {
            const input = document.getElementById('authUrlInput');
            input.select();
            document.execCommand('copy');
            showToast('授权链接已复制到剪贴板', 'success');
        }

        // 打开授权 URL
        function openAuthUrl() {
            const url = document.getElementById('authUrlInput').value;
            if (url) {
                window.open(url, '_blank');
                showToast('已在新窗口打开授权页面', 'info');
            }
        }

        // 换取 Token
        async function exchangeToken() {
            const redirectUrl = document.getElementById('redirectUrlInput').value.trim();

            if (!redirectUrl) {
                showToast('请先粘贴授权后的完整 URL', 'error');
                return;
            }

            const btn = document.getElementById('exchangeTokenBtn');
            btn.disabled = true;
            btn.textContent = '⏳ 换取中...';

            try {
                const response = await fetch('/api/oauth/exchange-token', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        redirected_url: redirectUrl
                    })
                });

                const data = await response.json();

                if (data.success) {
                    // 生成完整的导入格式
                    const importFormat = `your@outlook.com----yourpassword----${data.client_id}----${data.refresh_token}`;

                    // 显示结果
                    document.getElementById('refreshTokenOutput').value = importFormat;
                    document.getElementById('refreshTokenResult').style.display = 'block';

                    showToast('✅ Refresh Token 获取成功！', 'success');

                    // 重置按钮状态（不隐藏，允许重复使用）
                    btn.disabled = false;
                    btn.textContent = '换取 Token';
                } else {
                    handleApiError(data, '换取 Token 失败');
                    btn.disabled = false;
                    btn.textContent = '换取 Token';
                }
            } catch (error) {
                showToast('换取 Token 失败: ' + error.message, 'error');
                btn.disabled = false;
                btn.textContent = '换取 Token';
            }
        }

        // ==================== 设置相关 ====================

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

        // 加载设置
        async function loadSettings() {
            try {
                const response = await fetch('/api/settings');
                const data = await response.json();

                if (data.success) {
                    // 密码不显示，只显示 API Key
                    document.getElementById('settingsApiKey').value = data.settings.gptmail_api_key || '';
                    // 密码框留空
                    document.getElementById('settingsPassword').value = '';

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
                    const enablePolling = data.settings.enable_auto_polling === true || data.settings.enable_auto_polling === 'true';
                    document.getElementById('enableAutoPolling').checked = enablePolling;
                    document.getElementById('pollingInterval').value = data.settings.polling_interval || '10';
                    document.getElementById('pollingCount').value = data.settings.polling_count || '5';
                }
            } catch (error) {
                showToast('加载设置失败', 'error');
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
                    const nextRun = new Date(data.next_run).toLocaleString('zh-CN');
                    resultEl.innerHTML = `
                        <div style="color: #28a745;">
                            ✓ 表达式有效<br>
                            下次执行: ${nextRun}
                        </div>
                    `;
                } else {
                    resultEl.innerHTML = `
                        <div style="color: #dc3545;">
                            ✗ ${data.error && data.error.message ? data.error.message : (data.error || '表达式无效')}
                        </div>
                    `;
                }
            } catch (error) {
                resultEl.innerHTML = `
                    <div style="color: #dc3545;">
                        ✗ 验证失败: ${error.message}
                    </div>
                `;
            }
        }

        // 保存设置
        async function saveSettings() {
            const password = document.getElementById('settingsPassword').value;
            const apiKey = document.getElementById('settingsApiKey').value.trim();
            const refreshDays = document.getElementById('refreshIntervalDays').value;
            const refreshDelay = document.getElementById('refreshDelaySeconds').value;
            const refreshCron = document.getElementById('refreshCron').value.trim();
            const strategy = document.querySelector('input[name="refreshStrategy"]:checked').value;
            const enableScheduled = document.getElementById('enableScheduledRefresh').checked;

            // 轮询设置
            const enablePolling = document.getElementById('enableAutoPolling').checked;
            const pollingInterval = document.getElementById('pollingInterval').value;
            const pollingCount = document.getElementById('pollingCount').value;

            const settings = {};

            // 只有输入了密码才更新密码
            if (password) {
                settings.login_password = password;
            }

            // API Key 可以为空（清除）
            settings.gptmail_api_key = apiKey;

            // 刷新配置
            const days = parseInt(refreshDays);
            const delay = parseInt(refreshDelay);

            if (isNaN(days) || days < 1 || days > 90) {
                showToast('刷新周期必须在 1-90 天之间', 'error');
                return;
            }

            if (isNaN(delay) || delay < 0 || delay > 60) {
                showToast('刷新间隔必须在 0-60 秒之间', 'error');
                return;
            }

            settings.refresh_interval_days = days;
            settings.refresh_delay_seconds = delay;
            settings.use_cron_schedule = strategy === 'cron';
            settings.enable_scheduled_refresh = enableScheduled;

            if (strategy === 'cron') {
                if (!refreshCron) {
                    showToast('请输入 Cron 表达式', 'error');
                    return;
                }
                settings.refresh_cron = refreshCron;
            }

            // 轮询配置验证
            const pInterval = parseInt(pollingInterval);
            const pCount = parseInt(pollingCount);

            if (isNaN(pInterval) || pInterval < 5 || pInterval > 300) {
                showToast('轮询间隔必须在 5-300 秒之间', 'error');
                return;
            }

            // 0 表示持续轮询，1-100 表示有限次数
            if (isNaN(pCount) || pCount < 0 || pCount > 100) {
                showToast('轮询次数必须在 0-100 次之间（0 表示持续轮询）', 'error');
                return;
            }

            settings.enable_auto_polling = enablePolling;
            settings.polling_interval = pInterval;
            settings.polling_count = pCount;

            try {
                const response = await fetch('/api/settings', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(settings)
                });

                const data = await response.json();

                if (data.success) {
                    showToast('设置已保存，重启应用后生效', 'success');
                    hideSettingsModal();
                } else {
                    handleApiError(data, '保存设置失败');
                }
            } catch (error) {
                showToast('保存设置失败', 'error');
            }
        }

        // ==================== 自动轮询功能 ====================

        // 初始化轮询设置
        async function initPollingSettings() {
            try {
                const response = await fetch('/api/settings');
                const data = await response.json();

                if (data.success) {
                    pollingInterval = parseInt(data.settings.polling_interval) || 10;
                    maxPollingCount = parseInt(data.settings.polling_count) || 5;

                    // 如果启用了自动轮询，则开始轮询（后端返回 boolean，兼容处理）
                    const enablePolling = data.settings.enable_auto_polling === true || data.settings.enable_auto_polling === 'true';
                    if (enablePolling && currentAccount) {
                        startPolling();
                    }
                }
            } catch (error) {
                console.error('初始化轮询设置失败:', error);
            }
        }

        // 开始轮询
        function startPolling() {
            if (isPolling || !currentAccount) {
                console.log('[轮询] 无法启动: isPolling=', isPolling, ', currentAccount=', currentAccount);
                return;
            }

            isPolling = true;
            pollingCount = 0;
            pollingErrorCount = 0; // 重置错误计数

            // 初始化已知邮件ID集合
            knownEmailIds = new Set(currentEmails.map(email => email.id));

            console.log('[轮询] 已启动，间隔:', pollingInterval, '秒，最大次数:', maxPollingCount);

            // 显示轮询状态指示器
            showPollingStatusIndicator();

            // 立即执行一次
            pollForNewEmails();

            // 设置定时器
            pollingTimer = setInterval(pollForNewEmails, pollingInterval * 1000);
        }

        // 显示轮询状态指示器
        function showPollingStatusIndicator() {
            let indicator = document.getElementById('pollingStatusIndicator');
            if (!indicator) {
                indicator = document.createElement('div');
                indicator.id = 'pollingStatusIndicator';
                indicator.style.cssText = `
                    position: fixed;
                    bottom: 24px;
                    right: 24px;
                    background-color: #28a745;
                    color: white;
                    padding: 8px 16px;
                    border-radius: 20px;
                    font-size: 12px;
                    font-weight: 500;
                    box-shadow: 0 2px 8px rgba(40, 167, 69, 0.3);
                    z-index: 1000;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    cursor: pointer;
                `;
                indicator.innerHTML = `<span style="animation: pulse 1.5s infinite;">🔄</span> 轮询中`;
                indicator.onclick = () => {
                    if (confirm('是否停止轮询？')) {
                        stopPolling(false);
                    }
                };
                document.body.appendChild(indicator);
            }
            indicator.style.display = 'flex';
        }

        // 隐藏轮询状态指示器
        function hidePollingStatusIndicator() {
            const indicator = document.getElementById('pollingStatusIndicator');
            if (indicator) {
                indicator.style.display = 'none';
            }
        }

        // 停止轮询
        function stopPolling(silent = false) {
            console.log('[轮询] 停止轮询, silent=', silent);
            if (pollingTimer) {
                clearInterval(pollingTimer);
                pollingTimer = null;
            }
            isPolling = false;
            pollingCount = 0;
            pollingErrorCount = 0;
            hideNewEmailIndicator();
            hideAccountNewEmailDot();
            hidePollingStatusIndicator();
            // 用户主动停止时显示提示
            if (!silent) {
                showToast('已停止轮询', 'info');
            }
        }

        // 轮询检查新邮件
        let pollingErrorCount = 0; // 连续错误计数
        const MAX_POLLING_ERRORS = 3; // 最大连续错误次数

        async function pollForNewEmails() {
            if (!currentAccount) {
                stopPolling(true);
                return;
            }

            pollingCount++;

            try {
                const response = await fetch(`/api/emails/${encodeURIComponent(currentAccount)}?skip=0&limit=10&folder=${currentFolder}`);
                const data = await response.json();

                if (data.success && data.emails) {
                    pollingErrorCount = 0; // 重置错误计数
                    const newEmails = data.emails.filter(email => !knownEmailIds.has(email.id));

                    if (newEmails.length > 0) {
                        // 发现新邮件
                        showNewEmailNotification(newEmails);

                        // 更新已知邮件ID集合
                        newEmails.forEach(email => knownEmailIds.add(email.id));

                        // 更新邮件列表（在现有列表前面插入新邮件）
                        currentEmails = [...newEmails, ...currentEmails];
                        renderEmailList(currentEmails);
                        document.getElementById('emailCount').textContent = `(${currentEmails.length})`;

                        // 显示新邮件指示器（账号列表项红点）
                        showAccountNewEmailDot(newEmails.length);
                    }
                } else {
                    pollingErrorCount++;
                }
            } catch (error) {
                console.error('轮询新邮件失败:', error);
                pollingErrorCount++;
            }

            // 连续错误超过阈值，停止轮询并提示
            if (pollingErrorCount >= MAX_POLLING_ERRORS) {
                stopPolling(true);
                showToast('轮询连续失败，已自动停止', 'error');
                return;
            }

            // 检查是否达到最大轮询次数（0 表示持续轮询，不检查次数）
            if (maxPollingCount > 0 && pollingCount >= maxPollingCount) {
                stopPolling(true);
            }
        }

        // 显示新邮件通知（包含邮箱地址和邮件主题）
        function showNewEmailNotification(newEmails) {
            const count = newEmails.length;
            const firstEmail = newEmails[0];
            const subject = firstEmail?.subject || '无主题';

            // 请求浏览器通知权限
            if ('Notification' in window && Notification.permission === 'granted') {
                const title = count === 1 ? `新邮件 - ${currentAccount}` : `新邮件 (${count}封) - ${currentAccount}`;
                const body = count === 1 ? subject : `${subject} 等 ${count} 封新邮件`;
                new Notification(title, {
                    body: body,
                    icon: '/static/favicon.ico'
                });
            } else if ('Notification' in window && Notification.permission !== 'denied') {
                Notification.requestPermission();
            }

            // 显示页面内通知（包含邮箱和主题）
            const message = count === 1
                ? `📬 ${currentAccount}: ${subject}`
                : `📬 ${currentAccount}: ${subject} 等 ${count} 封新邮件`;
            showToast(message, 'success');
        }

        // 显示账号列表项上的红点
        function showAccountNewEmailDot(count) {
            // 在当前选中的账号项上显示红点
            const activeItem = document.querySelector('.account-item.active');
            if (activeItem) {
                let dot = activeItem.querySelector('.new-email-badge');
                if (!dot) {
                    dot = document.createElement('span');
                    dot.className = 'new-email-badge';
                    dot.style.cssText = `
                        position: absolute;
                        top: 8px;
                        right: 8px;
                        background-color: #dc3545;
                        color: white;
                        padding: 2px 6px;
                        border-radius: 10px;
                        font-size: 11px;
                        font-weight: 500;
                        min-width: 18px;
                        text-align: center;
                    `;
                    activeItem.style.position = 'relative';
                    activeItem.appendChild(dot);
                }
                dot.textContent = count;
                dot.style.display = 'block';
            }

            // 同时保留右上角指示器（作为备用）
            showNewEmailIndicator(count);
        }

        // 隐藏账号列表项上的红点
        function hideAccountNewEmailDot() {
            const dots = document.querySelectorAll('.new-email-badge');
            dots.forEach(dot => dot.style.display = 'none');
        }

        // 显示新邮件指示器（红点）- 移到右下角
        function showNewEmailIndicator(count) {
            let indicator = document.getElementById('newEmailIndicator');
            if (!indicator) {
                indicator = document.createElement('div');
                indicator.id = 'newEmailIndicator';
                indicator.style.cssText = `
                    position: fixed;
                    bottom: 70px;
                    right: 24px;
                    background-color: #dc3545;
                    color: white;
                    padding: 8px 16px;
                    border-radius: 20px;
                    font-size: 13px;
                    font-weight: 500;
                    box-shadow: 0 2px 8px rgba(220, 53, 69, 0.3);
                    z-index: 1000;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    animation: slideIn 0.3s ease;
                `;
                indicator.innerHTML = `<span class="new-email-dot"></span> 新邮件 (${count})`;
                indicator.onclick = () => {
                    hideNewEmailIndicator();
                    hideAccountNewEmailDot();
                    // 滚动到邮件列表顶部
                    document.getElementById('emailList').scrollTop = 0;
                };
                document.body.appendChild(indicator);

                // 添加动画样式
                if (!document.getElementById('newEmailIndicatorStyles')) {
                    const style = document.createElement('style');
                    style.id = 'newEmailIndicatorStyles';
                    style.textContent = `
                        @keyframes slideIn {
                            from { transform: translateX(100%); opacity: 0; }
                            to { transform: translateX(0); opacity: 1; }
                        }
                        .new-email-dot {
                            width: 8px;
                            height: 8px;
                            background-color: white;
                            border-radius: 50%;
                            animation: pulse 1.5s infinite;
                        }
                        @keyframes pulse {
                            0%, 100% { opacity: 1; }
                            50% { opacity: 0.5; }
                        }
                    `;
                    document.head.appendChild(style);
                }
            } else {
                indicator.innerHTML = `<span class="new-email-dot"></span> 新邮件 (${count})`;
                indicator.style.display = 'flex';
            }
        }

        // 隐藏新邮件指示器
        function hideNewEmailIndicator() {
            const indicator = document.getElementById('newEmailIndicator');
            if (indicator) {
                indicator.style.display = 'none';
            }
        }

        // 切换轮询状态
        function togglePolling() {
            if (isPolling) {
                stopPolling();
            } else {
                startPolling();
            }
        }

        // ==================== 工具函数 ====================

        // 相对时间格式化
        function formatRelativeTime(timestamp) {
            if (!timestamp) return '从未刷新';

            const now = new Date();
            // 如果时间戳不包含时区信息，假定为 UTC 时间并添加 Z
            let dateStr = timestamp;
            if (typeof dateStr === 'string' && !dateStr.includes('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
                dateStr = dateStr + 'Z';
            }
            const past = new Date(dateStr);
            const diffMs = now - past;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMs / 3600000);
            const diffDays = Math.floor(diffMs / 86400000);

            if (diffMins < 1) return '刚刚';
            if (diffMins < 60) return `${diffMins} 分钟前`;
            if (diffHours < 24) return `${diffHours} 小时前`;
            if (diffDays < 30) return `${diffDays} 天前`;
            return `${Math.floor(diffDays / 30)} 月前`;
        }

        // ==================== Token 刷新管理 ====================

        // 显示刷新模态框
        async function showRefreshModal() {
            document.getElementById('refreshModal').classList.add('show');
            // 加载统计数据
            await loadRefreshStats();
            // 自动加载失败列表（如果有失败记录）
            await autoLoadFailedListIfNeeded();
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

            // 重置按钮状态
            const refreshAllBtn = document.getElementById('refreshAllBtn');
            if (refreshAllBtn) {
                refreshAllBtn.disabled = false;
                refreshAllBtn.textContent = '🔄 全量刷新';
            }

            const retryFailedBtn = document.getElementById('retryFailedBtn');
            if (retryFailedBtn) {
                retryFailedBtn.disabled = false;
                retryFailedBtn.textContent = '🔁 重试失败';
            }
        }

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
            btn.textContent = '刷新中...';
            progress.style.display = 'block';
            progressText.innerHTML = '正在初始化...';

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
                            progressText.innerHTML = `总共 <strong>${totalCount}</strong> 个账号${delayInfo}，准备开始刷新...`;
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
                                正在处理: <strong>${data.email}</strong><br>
                                进度: <strong>${data.current}/${data.total}</strong> |
                                成功: <strong style="color: #28a745;">${successCount}</strong> |
                                失败: <strong style="color: #dc3545;">${failedCount}</strong>
                            `;
                        } else if (data.type === 'delay') {
                            progressText.innerHTML += `<br><span style="color: #999;">等待 ${data.seconds} 秒后继续...</span>`;
                        } else if (data.type === 'complete') {
                            eventSource.close();
                            progress.style.display = 'none';
                            btn.disabled = false;
                            btn.textContent = '🔄 全量刷新';

                            // 直接更新统计数据，使用本地时间
                            const now = new Date();
                            lastRefreshTime = now; // 保存刷新时间
                            document.getElementById('lastRefreshTime').textContent = '刚刚';
                            document.getElementById('totalRefreshCount').textContent = data.total;
                            document.getElementById('successRefreshCount').textContent = data.success_count;
                            document.getElementById('failedRefreshCount').textContent = data.failed_count;

                            showToast(`刷新完成！成功: ${data.success_count}, 失败: ${data.failed_count}`,
                                data.failed_count > 0 ? 'warning' : 'success');

                            // 如果有失败的，显示失败列表
                            if (data.failed_count > 0) {
                                showFailedListFromData(data.failed_list);
                            }

                            // 刷新账号列表以更新刷新时间
                            if (currentGroupId) {
                                loadAccountsByGroup(currentGroupId, true);
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
                    btn.textContent = '🔄 全量刷新';
                    showToast('刷新过程中出现错误', 'error');
                };

            } catch (error) {
                progress.style.display = 'none';
                btn.disabled = false;
                btn.textContent = '🔄 全量刷新';
                showToast('刷新请求失败', 'error');
            }
        }

        // 重试失败的账号
        async function retryFailedAccounts() {
            const btn = document.getElementById('retryFailedBtn');
            const progress = document.getElementById('refreshProgress');
            const progressText = document.getElementById('refreshProgressText');

            if (btn.disabled) return;

            btn.disabled = true;
            btn.textContent = '重试中...';
            progress.style.display = 'block';
            progressText.textContent = '正在重试失败的账号...';

            try {
                const response = await fetch('/api/accounts/refresh-failed', {
                    method: 'POST'
                });
                const data = await response.json();

                progress.style.display = 'none';
                btn.disabled = false;
                btn.textContent = '🔁 重试失败';

                if (data.success) {
                    if (data.total === 0) {
                        showToast('没有需要重试的失败账号', 'info');
                    } else {
                        showToast(`重试完成！成功: ${data.success_count}, 失败: ${data.failed_count}`,
                            data.failed_count > 0 ? 'warning' : 'success');

                        // 刷新统计
                        loadRefreshStats();

                        // 如果还有失败的，显示失败列表
                        if (data.failed_count > 0) {
                            showFailedListFromData(data.failed_list);
                        } else {
                            hideFailedList();
                        }
                    }
                } else {
                    handleApiError(data, '重试失败');
                }
            } catch (error) {
                progress.style.display = 'none';
                btn.disabled = false;
                btn.textContent = '🔁 重试失败';
                showToast('重试请求失败', 'error');
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
                    showToast(`${accountEmail} 刷新成功`, 'success');
                    loadRefreshStats();

                    // 刷新失败列表
                    loadFailedLogs();
                } else {
                    handleApiError(data, `${accountEmail} 刷新失败`);
                }
            } catch (error) {
                handleApiError({ success: false, error: { message: '刷新请求失败', details: error.message, code: 'NETWORK_ERROR', type: 'Frontend' } });
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
                showToast('加载失败邮箱列表失败', 'error');
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
                            const typeText = log.refresh_type === 'manual' ? '手动' : '自动';
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
                showToast('加载刷新历史失败', 'error');
            }
        }

        // 隐藏刷新历史
        function hideRefreshLogs() {
            document.getElementById('refreshLogsContainer').style.display = 'none';
        }

        // 格式化日期时间
        function formatDateTime(dateStr) {
            if (!dateStr) return '-';

            let date;
            if (dateStr instanceof Date) {
                date = dateStr;
            } else {
                // 如果字符串不包含时区信息，假定为 UTC 时间
                if (!dateStr.includes('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
                    dateStr = dateStr + 'Z';
                }
                date = new Date(dateStr);
            }

            const now = new Date();
            const diff = now - date;
            const minutes = Math.floor(diff / 60000);
            const hours = Math.floor(diff / 3600000);
            const days = Math.floor(diff / 86400000);

            if (minutes < 1) return '刚刚';
            if (minutes < 60) return `${minutes}分钟前`;
            if (hours < 24) return `${hours}小时前`;
            if (days < 7) return `${days}天前`;

            return date.toLocaleString('zh-CN', {
                timeZone: 'Asia/Shanghai',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
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
            hideGetRefreshTokenModal();
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
                hideGetRefreshTokenModal();
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
                showToast('加载标签失败', 'error');
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
                listEl.innerHTML = '<div style="text-align: center; color: #999; padding: 20px;">暂无标签</div>';
                return;
            }

            let html = '';
            allTags.forEach(tag => {
                html += `
                    <div style="display: flex; align-items: center; justify-content: space-between; padding: 8px; border-bottom: 1px solid #f0f0f0;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span class="tag-badge" style="background-color: ${tag.color};">${escapeHtml(tag.name)}</span>
                        </div>
                        <button class="btn btn-sm btn-danger" onclick="deleteTag(${tag.id})">删除</button>
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
                showToast('请输入标签名称', 'error');
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
                    showToast('标签创建成功', 'success');
                    await loadTags();
                    // 刷新账号列表以重新加载标签（如果是在查看列表时添加标签，可能不需要立即刷新列表，但为了保持一致性可以刷新）
                    // 但通常添加标签不影响当前列表显示，除非是给账号打标
                } else {
                    showToast(data.error || '创建失败', 'error');
                }
            } catch (error) {
                showToast('创建标签失败', 'error');
            }
        }

        // 删除标签
        async function deleteTag(id) {
            if (!confirm('确定要删除这个标签吗？')) return;

            try {
                const response = await fetch(`/api/tags/${id}`, { method: 'DELETE' });
                const data = await response.json();

                if (data.success) {
                    showToast('标签已删除', 'success');
                    await loadTags();
                    // 刷新账号列表以更新标签显示
                    if (currentGroupId) {
                        loadAccountsByGroup(currentGroupId, true);
                    }
                } else {
                    showToast(data.error || '删除失败', 'error');
                }
            } catch (error) {
                showToast('删除标签失败', 'error');
            }
        }

        // ==================== 批量操作 ====================

        // 全局选中的账号 ID 集合（跨分组保持）
        let selectedAccountIds = new Set();

        // 更新批量操作栏状态
        function updateBatchActionBar() {
            // 同步 DOM 复选框状态到全局 Set
            const allCheckboxes = document.querySelectorAll('.account-select-checkbox');
            allCheckboxes.forEach(cb => {
                const id = parseInt(cb.value);
                if (cb.checked) {
                    selectedAccountIds.add(id);
                } else {
                    selectedAccountIds.delete(id);
                }
            });

            const bar = document.getElementById('batchActionBar');
            const countSpan = document.getElementById('selectedCount');

            if (selectedAccountIds.size > 0) {
                bar.style.display = 'flex';
                countSpan.textContent = `已选 ${selectedAccountIds.size} 项`;
            } else {
                bar.style.display = 'none';
            }
        }

        // 显示批量删除确认
        function showBatchDeleteConfirm() {
            if (selectedAccountIds.size === 0) {
                showToast('请选择要删除的账号', 'error');
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
                    showToast(data.message, 'success');
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
                    showToast(data.error || '删除失败', 'error');
                }
            } catch (error) {
                showToast('删除失败', 'error');
            }
        }

        let batchActionType = ''; // 'add' or 'remove'

        // 显示批量打标模态框
        async function showBatchTagModal(type) {
            batchActionType = type;
            document.getElementById('batchTagTitle').textContent = type === 'add' ? '批量添加标签' : '批量移除标签';
            document.getElementById('batchTagModal').classList.add('show');

            // 加载标签选项
            await loadTagsForSelect();
        }

        function hideBatchTagModal() {
            document.getElementById('batchTagModal').classList.remove('show');
        }

        // 加载标签到下拉框
        async function loadTagsForSelect() {
            const select = document.getElementById('batchTagSelect');
            select.innerHTML = '<option value="">加载中...</option>';

            try {
                const response = await fetch('/api/tags');
                const data = await response.json();
                if (data.success) {
                    let html = '<option value="">请选择标签...</option>';
                    data.tags.forEach(tag => {
                        html += `<option value="${tag.id}">${escapeHtml(tag.name)}</option>`;
                    });
                    select.innerHTML = html;
                }
            } catch (error) {
                select.innerHTML = '<option value="">加载失败</option>';
            }
        }

        // 确认批量打标
        async function confirmBatchTag() {
            const tagId = document.getElementById('batchTagSelect').value;
            if (!tagId) {
                showToast('请选择标签', 'error');
                return;
            }

            const accountIds = Array.from(selectedAccountIds);

            if (accountIds.length === 0) return;

            try {
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
                    showToast(data.message, 'success');
                    hideBatchTagModal();
                    // 清空选中状态
                    selectedAccountIds.clear();
                    // 刷新列表
                    loadGroups();
                    if (currentGroupId) {
                        delete accountsCache[currentGroupId];
                        loadAccountsByGroup(currentGroupId, true);
                    }
                    updateBatchActionBar();
                } else {
                    showToast(data.error || '操作失败', 'error');
                }
            } catch (error) {
                showToast('请求失败', 'error');
            }
        }

        // ==================== 批量移动分组 ====================

        // 显示批量移动分组模态框
        async function showBatchMoveGroupModal() {
            document.getElementById('batchMoveGroupModal').classList.add('show');
            await loadGroupsForBatchMove();
        }

        function hideBatchMoveGroupModal() {
            document.getElementById('batchMoveGroupModal').classList.remove('show');
        }

        // 加载分组到下拉框
        async function loadGroupsForBatchMove() {
            const select = document.getElementById('batchMoveGroupSelect');
            select.innerHTML = '<option value="">加载中...</option>';

            try {
                const response = await fetch('/api/groups');
                const data = await response.json();
                if (data.success) {
                    let html = '<option value="">请选择分组...</option>';
                    data.groups.filter(g => !g.is_system).forEach(group => {
                        html += `<option value="${group.id}">${escapeHtml(group.name)}</option>`;
                    });
                    select.innerHTML = html;
                }
            } catch (error) {
                select.innerHTML = '<option value="">加载失败</option>';
            }
        }

        // 确认批量移动分组
        async function confirmBatchMoveGroup() {
            const groupId = document.getElementById('batchMoveGroupSelect').value;
            if (!groupId) {
                showToast('请选择目标分组', 'error');
                return;
            }

            const accountIds = Array.from(selectedAccountIds);

            if (accountIds.length === 0) return;

            try {
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
                    showToast(data.message, 'success');
                    hideBatchMoveGroupModal();
                    // 清空选中状态
                    selectedAccountIds.clear();
                    // 刷新分组列表
                    loadGroups();
                    // 刷新当前分组的邮箱列表
                    if (currentGroupId) {
                        delete accountsCache[currentGroupId];
                        loadAccountsByGroup(currentGroupId, true);
                    }
                    updateBatchActionBar();
                } else {
                    showToast(data.error || '操作失败', 'error');
                }
            } catch (error) {
                showToast('请求失败', 'error');
            }
        }
