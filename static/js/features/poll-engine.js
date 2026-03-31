        // ==================== 统一轮询引擎 ====================
        //
        // 从 mailbox_compact.js 提取的核心轮询逻辑。
        // 支持多账号并行、按次数停止、验证码自动提取、后台暂停/前台恢复。
        // UI 更新通过回调注入，各视图模式注册自己的 UI 更新函数。

        // ── 常量 ────────────────────────────────────────────────────

        var POLL_TOAST_DURATION = 5000;
        var POLL_INITIAL_DELAY_MS = 150;

        // ── 核心状态 ────────────────────────────────────────────────

        var pollMap = new Map();
        var pollCountdownTimer = null;

        // ── 全局设置变量（由 main.js 通过 applyPollSettings 更新） ──

        var pollEnabled  = false;
        var pollInterval = 10;
        var pollMaxCount = 5;

        // ── UI 回调注册 ─────────────────────────────────────────────

        var _pollUICallbacks = {
            onPollStart:   null,   // function(email, maxCount)
            onPollStop:    null,   // function(email)
            onPollTick:    null,   // function(email, remainingCount)
            onNewEmail:    null,   // function(email, summary)
            onAccountCheck: null   // function(email) → boolean, 检查账号是否还存在
        };

        function registerPollUICallbacks(callbacks) {
            if (!callbacks) return;
            if (callbacks.onPollStart)   _pollUICallbacks.onPollStart   = callbacks.onPollStart;
            if (callbacks.onPollStop)    _pollUICallbacks.onPollStop    = callbacks.onPollStop;
            if (callbacks.onPollTick)    _pollUICallbacks.onPollTick    = callbacks.onPollTick;
            if (callbacks.onNewEmail)    _pollUICallbacks.onNewEmail    = callbacks.onNewEmail;
            if (callbacks.onAccountCheck) _pollUICallbacks.onAccountCheck = callbacks.onAccountCheck;
        }

        // ── 内部辅助函数 ────────────────────────────────────────────

        function pollT(key) {
            return typeof translateCompactText === 'function' ? translateCompactText(key) : key;
        }

        function _handlePollError(email, state) {
            state.isPolling = false;
            if (!pollMap.has(email)) return;
            state.pollCount = (state.pollCount || 0) + 1;
            state.errorCount = (state.errorCount || 0) + 1;
            if (state.errorCount >= 3) {
                stopPoll(email, pollT('拉取失败，已停止监听'), 'info');
            }
        }

        function _notifyNewEmailAndStop(email, state) {
            state.isPolling = false;
            if (typeof showToast === 'function') {
                showToast(pollT('发现新邮件'), 'success', null, POLL_TOAST_DURATION);
            }
            stopPoll(email, null);
        }

        // ── 轮询生命周期 ────────────────────────────────────────────

        function stopPoll(email, toastMsg, toastType) {
            var state = pollMap.get(email);
            if (!state) return;
            if (state.timer) {
                clearInterval(state.timer);
                state.timer = null;
            }
            if (state.countdownTimer) {
                clearTimeout(state.countdownTimer);
                state.countdownTimer = null;
            }
            pollMap.delete(email);

            if (toastMsg !== null && toastMsg !== undefined) {
                if (typeof showToast === 'function') {
                    showToast(toastMsg, toastType || 'info', null, POLL_TOAST_DURATION);
                }
            }

            if (_pollUICallbacks.onPollStop) {
                _pollUICallbacks.onPollStop(email);
            }
        }

        function stopAllPolls() {
            var keys = [];
            pollMap.forEach(function(s, e) { keys.push(e); });
            keys.forEach(function(email) { stopPoll(email, null); });
            if (pollCountdownTimer) {
                clearInterval(pollCountdownTimer);
                pollCountdownTimer = null;
            }
        }

        function startGlobalCountdown() {
            if (pollCountdownTimer) return;
            pollCountdownTimer = setInterval(function() {
                if (pollMap.size === 0) {
                    clearInterval(pollCountdownTimer);
                    pollCountdownTimer = null;
                    return;
                }
                pollMap.forEach(function(state, email) {
                    if (!state) return;
                    if (state.maxCount > 0 && state.pollCount >= state.maxCount) {
                        stopPoll(email, pollT('监听超时，未检测到新邮件'), 'info');
                        return;
                    }
                    var remaining = state.maxCount > 0 ? Math.max(0, state.maxCount - state.pollCount) : 0;
                    if (_pollUICallbacks.onPollTick) {
                        _pollUICallbacks.onPollTick(email, remaining);
                    }
                });
            }, 1000);
        }

        function pollSingleEmail(email, state) {
            if (!pollMap.has(email)) return;

            if (state.isPolling) return;

            if (state.maxCount > 0 && state.pollCount >= state.maxCount) {
                stopPoll(email, pollT('监听超时，未检测到新邮件'), 'info');
                return;
            }

            // 账号存在性检查
            if (_pollUICallbacks.onAccountCheck) {
                if (!_pollUICallbacks.onAccountCheck(email)) {
                    stopPoll(email, pollT('账号已被删除，已停止监听'), 'error');
                    return;
                }
            }

            state.isPolling = true;

            Promise.allSettled([
                fetch('/api/emails/' + encodeURIComponent(email) + '?folder=inbox'),
                fetch('/api/emails/' + encodeURIComponent(email) + '?folder=sentitems')
            ]).then(function(results) {
                if (!pollMap.has(email)) { state.isPolling = false; return; }

                if (results.some(function(r) { return r.status === 'fulfilled' && r.value && r.value.status === 404; })) {
                    state.isPolling = false;
                    stopPoll(email, pollT('账号已被删除，已停止监听'), 'error');
                    return;
                }

                Promise.all(results.map(function(r) {
                    return (r.status === 'fulfilled' && r.value && r.value.ok)
                        ? r.value.json().catch(function() { return null; })
                        : Promise.resolve(null);
                })).then(function(dataArray) {
                    if (!pollMap.has(email)) { state.isPolling = false; return; }

                    var hasSuccess = false;
                    var allIds = new Set();
                    var firstSummary = null;

                    dataArray.forEach(function(data) {
                        if (!data) return;
                        hasSuccess = true;
                        if (data.emails && Array.isArray(data.emails)) {
                            data.emails.forEach(function(e) { if (e && e.id) allIds.add(e.id); });
                        }
                        var summary = data.account_summary || data.summary;
                        if (summary) {
                            if (!firstSummary) firstSummary = summary;
                            if (typeof syncAccountSummaryToAccountCache === 'function') {
                                syncAccountSummaryToAccountCache(email, summary);
                            }
                        }
                    });

                    if (!hasSuccess) {
                        _handlePollError(email, state);
                        return;
                    }

                    state.errorCount = 0;
                    state.pollCount = (state.pollCount || 0) + 1;
                    if (firstSummary && _pollUICallbacks.onNewEmail) {
                        _pollUICallbacks.onNewEmail(email, firstSummary);
                    }

                    var baseline = state.baselineIds || new Set();
                    var hasNew = false;
                    allIds.forEach(function(id) { if (!baseline.has(id)) hasNew = true; });

                    if (!hasNew) {
                        state.isPolling = false;
                        return;
                    }

                    fetch('/api/extract-verification?email=' + encodeURIComponent(email) + '&latest=1')
                        .then(function(r) { return r.ok ? r.json() : null; })
                        .then(function(res) {
                            if (res && res.success && res.data && res.data.verification_code) {
                                var code = res.data.verification_code;
                                state.isPolling = false;
                                if (typeof copyToClipboard === 'function') copyToClipboard(code);
                                stopPoll(email, pollT('检测到验证码') + '：' + code, 'success');
                            } else {
                                _notifyNewEmailAndStop(email, state);
                            }
                        })
                        .catch(function() { _notifyNewEmailAndStop(email, state); });

                }).catch(function() { _handlePollError(email, state); });

            }).catch(function() { _handlePollError(email, state); });
        }

        function startPoll(email, opts) {
            if (!email) return;
            console.debug('[poll-engine] startPoll called for:', email, 'pollEnabled:', pollEnabled);

            if (pollMap.has(email)) {
                stopPoll(email, null);
            }

            var intervalSec = (opts && opts.interval) || pollInterval || 10;
            var maxCount    = (opts && opts.maxCount  !== undefined ? opts.maxCount : undefined);
            if (maxCount === undefined) maxCount = pollMaxCount || 5;

            var state = {
                timer:       null,
                startTime:   Date.now(),
                baselineIds: new Set(),
                errorCount:  0,
                pollCount:   0,
                isPolling:   false,
                intervalSec: intervalSec,
                maxCount:    maxCount,
                countdownTimer: null
            };

            pollMap.set(email, state);

            Promise.allSettled([
                fetch('/api/emails/' + encodeURIComponent(email) + '?folder=inbox'),
                fetch('/api/emails/' + encodeURIComponent(email) + '?folder=sentitems')
            ]).then(function(results) {
                results.forEach(function(r) {
                    if (r.status === 'fulfilled' && r.value && r.value.ok) {
                        r.value.json().then(function(payload) {
                            if (payload && payload.emails && Array.isArray(payload.emails)) {
                                payload.emails.forEach(function(e) { if (e && e.id) state.baselineIds.add(e.id); });
                            }
                            if (payload && payload.account_summary && typeof syncAccountSummaryToAccountCache === 'function') {
                                syncAccountSummaryToAccountCache(email, payload.account_summary);
                            }
                        }).catch(function() {});
                    }
                });

                if (!pollMap.has(email)) return;

                // 触发 UI 回调和倒计时（先于首次轮询，让用户立即看到状态变化）
                if (_pollUICallbacks.onPollStart) {
                    _pollUICallbacks.onPollStart(email, state.maxCount, { reapply: false, silent: !!(opts && opts.silent) });
                }
                startGlobalCountdown();

                // 立即执行首次轮询（150ms 延迟，确保 baseline 微任务完成），后续按间隔继续
                setTimeout(function() {
                    if (pollMap.has(email)) pollSingleEmail(email, state);
                }, POLL_INITIAL_DELAY_MS);

                state.timer = setInterval(function() { pollSingleEmail(email, state); }, state.intervalSec * 1000);
            });
        }

        // ── 设置管理 ────────────────────────────────────────────────

        function applyPollSettingsToRunning(newSettings) {
            if (!newSettings) return;
            var ni = newSettings.interval;
            var nm = newSettings.maxCount;
            pollMap.forEach(function(state, email) {
                if (!state) return;
                if (ni && ni !== state.intervalSec) {
                    if (state.timer) clearInterval(state.timer);
                    state.intervalSec = ni;
                    state.timer = setInterval(function() { pollSingleEmail(email, state); }, ni * 1000);
                }
                if (nm !== undefined && nm !== null) state.maxCount = nm;
            });
        }

        function applyPollSettings(settings) {
            if (!settings) return;
            pollEnabled  = settings.enabled  !== undefined ? settings.enabled  : pollEnabled;
            pollInterval = settings.interval || pollInterval;
            pollMaxCount = settings.maxCount !== undefined ? settings.maxCount : pollMaxCount;
            if (settings.enabled === false) {
                stopAllPolls();
                return;
            }
            applyPollSettingsToRunning(settings);
        }

        function reapplyAllPollUI() {
            pollMap.forEach(function(state, email) {
                if (!state) return;
                // 调用 onPollStart 重新绘制 UI（兼容标准模式绿点和简洁模式拉取按钮）
                var remaining = state.maxCount > 0 ? Math.max(0, state.maxCount - state.pollCount) : 0;
                if (_pollUICallbacks.onPollStart) {
                    _pollUICallbacks.onPollStart(email, remaining, { reapply: true });
                }
            });
        }

        // ── 页面可见性 ──────────────────────────────────────────────

        document.addEventListener('visibilitychange', function() {
            if (document.hidden) {
                pollMap.forEach(function(state) {
                    if (state && state.timer) {
                        clearInterval(state.timer);
                        state.timer = null;
                    }
                });
                if (pollCountdownTimer) {
                    clearInterval(pollCountdownTimer);
                    pollCountdownTimer = null;
                }
            } else {
                pollMap.forEach(function(state, email) {
                    if (state && !state.timer) {
                        state.timer = setInterval(function() { pollSingleEmail(email, state); }, state.intervalSec * 1000);
                    }
                });
                if (pollMap.size > 0) {
                    startGlobalCountdown();
                    reapplyAllPollUI();
                }
            }
        });
