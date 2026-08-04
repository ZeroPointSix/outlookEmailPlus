import {
  AppstoreOutlined,
  ColumnWidthOutlined,
  CopyOutlined,
  DeleteOutlined,
  KeyOutlined,
  MailOutlined,
  ReloadOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import { useQuery } from '@tanstack/react-query';
import { history, useIntl, useLocation, useModel } from '@umijs/max';
import {
  Alert,
  App,
  Badge,
  Button,
  Checkbox,
  Collapse,
  Empty,
  Input,
  List,
  Menu,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  theme,
  Tooltip,
  Typography,
} from 'antd';
import type { MenuProps } from 'antd';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import ResizableWorkbench from '@/components/MailboxLayout/ResizableWorkbench';
import { usePollingSettingsDraft } from '@/hooks/usePollingSettingsDraft';
import { type AccountItem, fetchAccounts } from '@/services/outlook/accounts';
import {
  deleteEmails,
  type EmailDetail,
  type EmailFolder,
  type EmailListItem,
  extractEmailVerification,
  fetchEmailDetail,
  fetchEmails,
  normalizeMethodParam,
  pickEmailsErrorMessage,
} from '@/services/outlook/emails';
import {
  fetchGroups,
  type GroupItem,
  isTempMailboxGroup,
} from '@/services/outlook/groups';
import {
  applyPollSettings,
  getPollSettings,
  getPollSnapshot,
  getPollSnapshots,
  isPolling,
  loadPollSettingsFromServer,
  type PollSnapshot,
  startPoll,
  stopPoll,
  subscribePoll,
} from '@/services/outlook/pollEngine';
import {
  normalizePollingSettings,
  pickSettingsError,
  updatePollingSettings,
} from '@/services/outlook/settings';
import { buildEmailSrcDoc, sortEmailsByNewestFirst } from '@/utils/emailHtml';
import {
  loadViewMode,
  type MailboxViewMode,
  saveViewMode,
} from '@/utils/mailboxLayout';

const FOLDERS: Array<{ label: string; value: EmailFolder }> = [
  { label: '收件箱', value: 'inbox' },
  { label: '垃圾邮件', value: 'junkemail' },
  { label: '已删除', value: 'deleteditems' },
];

const PAGE_SIZE = 20;

type ReadFilter = 'all' | 'unread' | 'read';

function useMailboxQuery() {
  const location = useLocation();
  return useMemo(() => {
    const params = new URLSearchParams(location.search || '');
    return {
      account:
        (params.get('account') || params.get('email') || '').trim() ||
        undefined,
      folder: (params.get('folder') || 'inbox') as EmailFolder,
      skip: Math.max(0, Number(params.get('skip') || 0) || 0),
      group: params.get('group') ? Number(params.get('group')) : undefined,
    };
  }, [location.search]);
}

function formatDate(value?: string) {
  if (!value) return '--';
  try {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return d.toLocaleString();
  } catch {
    return value;
  }
}

function syncMailboxUrl(opts: {
  account?: string;
  folder?: string;
  skip?: number;
  group?: number;
}) {
  const params = new URLSearchParams();
  if (opts.account) params.set('account', opts.account);
  if (opts.folder && opts.folder !== 'inbox') params.set('folder', opts.folder);
  if (opts.skip && opts.skip > 0) params.set('skip', String(opts.skip));
  if (opts.group) params.set('group', String(opts.group));
  const qs = params.toString();
  history.replace(qs ? `/mailbox?${qs}` : '/mailbox');
}

const MailboxPage: React.FC = () => {
  const { message, modal } = App.useApp();
  const { token } = theme.useToken();
  const intl = useIntl();
  const query = useMailboxQuery();
  const { initialState } = useModel('@@initialState');
  const layoutUserId =
    (initialState as any)?.currentUser?.userid ||
    (initialState as any)?.currentUser?.name ||
    'guest';

  const [viewMode, setViewMode] = useState<MailboxViewMode>(() =>
    loadViewMode(),
  );
  const [layoutResetToken, setLayoutResetToken] = useState(0);
  const [groupId, setGroupId] = useState<number | undefined>(query.group);
  const [selectedEmail, setSelectedEmail] = useState<string | undefined>(
    query.account,
  );
  const [folder, setFolder] = useState<EmailFolder>(query.folder || 'inbox');
  const [method, setMethod] = useState<string>('graph');
  const [skip, setSkip] = useState(query.skip || 0);
  const [emails, setEmails] = useState<EmailListItem[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [listErrorDetails, setListErrorDetails] = useState<any>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EmailDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [extracting, setExtracting] = useState(false);
  const [extractingEmail, setExtractingEmail] = useState<string | null>(null);
  const [lastVerification, setLastVerification] = useState<string | null>(null);
  const [trusted, setTrusted] = useState(false);
  const [readFilter, setReadFilter] = useState<ReadFilter>('all');
  const [listSearch, setListSearch] = useState('');
  const [pollSnap, setPollSnap] = useState<PollSnapshot | undefined>();
  const [allPollSnaps, setAllPollSnaps] = useState<PollSnapshot[]>([]);
  const {
    interval: pollInterval,
    maxCount: pollMaxCount,
    acceptSettings: acceptPollSettings,
  } = usePollingSettingsDraft(getPollSettings(), loadPollSettingsFromServer);
  const [compactSearch, setCompactSearch] = useState('');
  const [compactSelected, setCompactSelected] = useState<number[]>([]);
  const [pullingEmails, setPullingEmails] = useState<Record<string, boolean>>(
    {},
  );

  const groupsQuery = useQuery({
    queryKey: ['mailbox-groups'],
    queryFn: fetchGroups,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  const accountsQuery = useQuery({
    queryKey: ['mailbox-accounts', groupId],
    queryFn: () =>
      fetchAccounts({
        page: 1,
        page_size: 200,
        group_id: groupId,
        sort_by: 'refresh_time',
        sort_order: 'asc',
      }),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const groups = useMemo(
    () =>
      (groupsQuery.data?.groups || []).filter(
        (g: GroupItem) => !isTempMailboxGroup(g),
      ),
    [groupsQuery.data],
  );

  const accounts = useMemo(
    () => accountsQuery.data?.accounts || [],
    [accountsQuery.data],
  );

  const filteredCompactAccounts = useMemo(() => {
    const q = compactSearch.trim().toLowerCase();
    if (!q) return accounts;
    return accounts.filter((a) => {
      const hay =
        `${a.email || ''} ${a.remark || ''} ${a.group_name || ''}`.toLowerCase();
      return hay.includes(q);
    });
  }, [accounts, compactSearch]);

  useEffect(() => {
    return subscribePoll((snaps) => {
      setAllPollSnaps(snaps);
      if (selectedEmail) setPollSnap(getPollSnapshot(selectedEmail));
    });
  }, [selectedEmail]);

  useEffect(() => {
    if (query.account) setSelectedEmail(query.account);
    if (query.folder) setFolder(query.folder);
    if (query.group) setGroupId(query.group);
  }, [query.account, query.folder, query.group]);

  useEffect(() => {
    if (selectedEmail) return;
    const first = accounts[0]?.email;
    if (first) setSelectedEmail(first);
  }, [accounts, selectedEmail]);

  const loadEmails = useCallback(
    async (opts?: { append?: boolean; nextSkip?: number }) => {
      if (!selectedEmail) return;
      const append = !!opts?.append;
      const nextSkip = opts?.nextSkip ?? 0;
      setListLoading(true);
      setListError(null);
      setListErrorDetails(null);
      try {
        const res = await fetchEmails(selectedEmail, {
          method: normalizeMethodParam(method),
          folder,
          skip: nextSkip,
          top: PAGE_SIZE,
        });
        if (res?.success) {
          const list = sortEmailsByNewestFirst(res.emails || []);
          setEmails((prev) =>
            append ? sortEmailsByNewestFirst([...prev, ...list]) : list,
          );
          setHasMore(!!res.has_more);
          setSkip(nextSkip);
          syncMailboxUrl({
            account: selectedEmail,
            folder,
            skip: nextSkip,
            group: groupId,
          });
          if (res.method) setMethod(normalizeMethodParam(res.method));
          if (!append) {
            setActiveId(null);
            setDetail(null);
            setSelectedIds([]);
            setTrusted(false);
          }
        } else {
          if (!append) {
            setEmails([]);
            setHasMore(false);
          }
          setListError(pickEmailsErrorMessage(res));
          setListErrorDetails(res?.details || res?.error?.details || null);
        }
      } catch (error: any) {
        const data = error?.response?.data || error?.data || error?.info;
        if (!append) {
          setEmails([]);
          setHasMore(false);
        }
        setListError(
          pickEmailsErrorMessage(data, error?.message || '获取邮件失败'),
        );
        setListErrorDetails(data?.details || data?.error?.details || null);
      } finally {
        setListLoading(false);
      }
    },
    [selectedEmail, folder, method, groupId],
  );

  useEffect(() => {
    if (!selectedEmail || viewMode !== 'standard') return;
    void loadEmails({ append: false, nextSkip: 0 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedEmail, folder, viewMode]);

  const filteredEmails = useMemo(() => {
    let list = emails;
    if (readFilter === 'unread') {
      list = list.filter((e) => e.is_read === false);
    } else if (readFilter === 'read') {
      list = list.filter((e) => e.is_read !== false);
    }
    const q = listSearch.trim().toLowerCase();
    if (q) {
      list = list.filter((e) => {
        const hay =
          `${e.subject || ''} ${e.from || ''} ${e.body_preview || ''}`.toLowerCase();
        return hay.includes(q);
      });
    }
    return list;
  }, [emails, readFilter, listSearch]);

  const openDetail = async (item: EmailListItem) => {
    if (!selectedEmail || !item?.id) return;
    setActiveId(item.id);
    setDetailLoading(true);
    setDetail(null);
    setTrusted(false);
    try {
      const res = await fetchEmailDetail(selectedEmail, item.id, {
        method: normalizeMethodParam(method),
        folder,
      });
      if (res?.success && res.email) {
        setDetail(res.email);
      } else {
        message.error(pickEmailsErrorMessage(res, '获取邮件详情失败'));
      }
    } catch (error: any) {
      const data = error?.response?.data;
      message.error(
        pickEmailsErrorMessage(data, error?.message || '获取邮件详情失败'),
      );
    } finally {
      setDetailLoading(false);
    }
  };

  const onAccountChange = (email: string) => {
    setSelectedEmail(email);
    setSkip(0);
    syncMailboxUrl({ account: email, folder, skip: 0, group: groupId });
  };

  const onGroupChange = (gid?: number) => {
    setGroupId(gid);
    setSelectedEmail(undefined);
    setEmails([]);
    setDetail(null);
    syncMailboxUrl({
      account: undefined,
      folder,
      skip: 0,
      group: gid,
    });
  };

  const onFolderChange = (v: EmailFolder) => {
    setFolder(v);
    setSkip(0);
    syncMailboxUrl({
      account: selectedEmail,
      folder: v,
      skip: 0,
      group: groupId,
    });
  };

  const onViewModeChange = (mode: MailboxViewMode | string) => {
    const next: MailboxViewMode = mode === 'compact' ? 'compact' : 'standard';
    setViewMode(next);
    saveViewMode(next);
  };

  const onDeleteSelected = async () => {
    if (!selectedEmail || !selectedIds.length) return;
    try {
      const res = await deleteEmails(selectedEmail, selectedIds);
      if (res?.success === false) {
        message.error(pickEmailsErrorMessage(res, '删除失败'));
        return;
      }
      message.success(`已删除 ${selectedIds.length} 封`);
      setSelectedIds([]);
      setDetail(null);
      setActiveId(null);
      await loadEmails({ append: false, nextSkip: 0 });
    } catch (error: any) {
      const data = error?.response?.data;
      message.error(pickEmailsErrorMessage(data, error?.message || '删除失败'));
    }
  };

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      return false;
    }
  };

  const extractForEmail = async (email: string) => {
    setExtracting(true);
    setExtractingEmail(email);
    try {
      const res = await extractEmailVerification(email);
      if (res?.success && res.data) {
        const text =
          res.data.formatted ||
          res.data.verification_code ||
          res.data.code ||
          res.data.verification_link ||
          '';
        if (!text) {
          message.info(res.message || '未提取到验证码或链接');
          return;
        }
        setLastVerification(String(text));
        const ok = await copyText(String(text));
        message.success(ok ? `已复制: ${text}` : `验证码: ${text}`);
        return;
      }
      message.error(pickEmailsErrorMessage(res, '未找到验证码或链接'));
    } catch (error: any) {
      message.error(
        pickEmailsErrorMessage(
          error?.response?.data,
          error?.message || '提取验证码失败',
        ),
      );
    } finally {
      setExtracting(false);
      setExtractingEmail(null);
    }
  };

  const onExtractVerification = async () => {
    if (!selectedEmail) {
      message.error('请先选择账号');
      return;
    }
    await extractForEmail(selectedEmail);
  };

  const onToggleTrust = (checked: boolean) => {
    if (checked) {
      modal.confirm({
        title: '启用信任模式？',
        content:
          '信任模式将直接显示邮件原始 HTML（仍保留 iframe 沙箱），可能包含不安全内容。确定继续？',
        okText: '启用',
        cancelText: '取消',
        onOk: () => setTrusted(true),
      });
      return;
    }
    setTrusted(false);
  };

  const persistPollSettings = async (announce: boolean) => {
    const current = getPollSettings();
    const normalized = normalizePollingSettings(pollInterval, pollMaxCount);
    const interval = normalized.polling_interval;
    const maxCount = normalized.polling_count;
    const changed =
      current.interval !== interval || current.maxCount !== maxCount;
    if (!changed) {
      if (announce) message.info('监听参数已是最新设置');
      return true;
    }

    try {
      const res = await updatePollingSettings(interval, maxCount);
      if (res?.success === false) {
        message.error(pickSettingsError(res, '保存监听参数失败'));
        return false;
      }
      applyPollSettings({ interval, maxCount });
      acceptPollSettings({ interval, maxCount });
      message.success(
        announce
          ? `已保存并应用：间隔 ${interval}s / 次数 ${maxCount || '不限'}`
          : '监听参数已保存',
      );
      return true;
    } catch (error: any) {
      message.error(
        pickSettingsError(
          error?.data || error?.info || error?.response?.data,
          error?.message || '保存监听参数失败',
        ),
      );
      return false;
    }
  };

  const onTogglePoll = async (email?: string) => {
    const target = email || selectedEmail;
    if (!target) return;
    if (isPolling(target)) {
      stopPoll(target, '已停止监听');
      message.info('已停止监听');
      if (target === selectedEmail) setPollSnap(undefined);
      return;
    }
    if (!(await persistPollSettings(false))) return;
    const savedSettings = getPollSettings();
    await startPoll(target, {
      force: true,
      interval: savedSettings.interval,
      maxCount: savedSettings.maxCount,
    });
    message.success('已开始监听新邮件');
    if (target === selectedEmail) setPollSnap(getPollSnapshot(target));
  };

  const pullAccountSummary = async (account: AccountItem) => {
    const email = account.email;
    if (!email) return;
    setPullingEmails((m) => ({ ...m, [email]: true }));
    try {
      const results = await Promise.allSettled([
        fetchEmails(email, {
          method: 'graph',
          folder: 'inbox',
          skip: 0,
          top: 10,
        }),
        fetchEmails(email, {
          method: 'graph',
          folder: 'junkemail',
          skip: 0,
          top: 10,
        }),
      ]);
      const ok = results.some(
        (r) => r.status === 'fulfilled' && r.value?.success,
      );
      if (ok) {
        message.success(`已拉取 ${email}`);
        // 若当前选中该账号，刷新列表
        if (selectedEmail === email && viewMode === 'standard') {
          await loadEmails({ append: false, nextSkip: 0 });
        }
      } else {
        message.error(`拉取失败：${email}`);
      }
    } catch (error: any) {
      message.error(error?.message || '拉取失败');
    } finally {
      setPullingEmails((m) => {
        const next = { ...m };
        delete next[email];
        return next;
      });
    }
  };

  const bodyHtml = useMemo(() => {
    if (!detail?.body) return '';
    return buildEmailSrcDoc({
      body: detail.body,
      bodyType: detail.body_type,
      inlineResources: detail.inline_resources,
      trusted,
    });
  }, [detail, trusted]);

  const polling = !!(selectedEmail && isPolling(selectedEmail));
  const pollSnapMap = useMemo(() => {
    const m = new Map<string, PollSnapshot>();
    allPollSnaps.forEach((s) => {
      m.set(s.email, s);
    });
    // 保证订阅外也能读到最新
    getPollSnapshots().forEach((s) => {
      m.set(s.email, s);
    });
    return m;
  }, [allPollSnaps]);

  const groupMenuItems = useMemo<MenuProps['items']>(
    () => [
      { key: 'all', label: '全部分组' },
      ...groups.map((g) => ({
        key: String(g.id),
        icon: (
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: g.color || token.colorTextQuaternary,
              display: 'inline-block',
            }}
          />
        ),
        label: (
          <div style={{ lineHeight: 1.35, minWidth: 0 }}>
            <Typography.Text ellipsis>{g.name}</Typography.Text>
            <div>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {g.account_count != null
                  ? `${g.account_count} 个账号`
                  : g.description || ''}
              </Typography.Text>
            </div>
          </div>
        ),
      })),
    ],
    [groups, token.colorTextQuaternary],
  );

  const accountMenuItems = useMemo<MenuProps['items']>(
    () =>
      filteredCompactAccounts.map((a: AccountItem) => ({
        key: a.email,
        label: (
          <Space size={4} style={{ width: '100%' }}>
            <Typography.Text ellipsis style={{ maxWidth: 170 }}>
              {a.email}
            </Typography.Text>
            {isPolling(a.email) ? (
              <Badge status="processing" title="监听中" />
            ) : null}
          </Space>
        ),
      })),
    [filteredCompactAccounts],
  );

  // ── 左栏：分组 ──
  const groupsPane = (
    <Spin spinning={groupsQuery.isLoading}>
      <Menu
        mode="inline"
        selectable
        selectedKeys={[groupId == null ? 'all' : String(groupId)]}
        items={groupMenuItems}
        onClick={({ key }) =>
          onGroupChange(key === 'all' ? undefined : Number(key))
        }
        style={{ borderInlineEnd: 0, background: 'transparent' }}
      />
    </Spin>
  );

  // ── 中栏：账号 ──
  const accountsPane = (
    <div>
      <div style={{ padding: '0 8px 8px' }}>
        <Input.Search
          size="small"
          allowClear
          placeholder="筛选账号"
          onSearch={setCompactSearch}
          onChange={(e) => {
            if (!e.target.value) setCompactSearch('');
          }}
        />
      </div>
      <Spin spinning={accountsQuery.isLoading}>
        {filteredCompactAccounts.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="当前分组暂无账号"
            style={{ margin: '24px 0' }}
          />
        ) : (
          <Menu
            mode="inline"
            selectable
            selectedKeys={selectedEmail ? [selectedEmail] : []}
            items={accountMenuItems}
            onClick={({ key }) => onAccountChange(key)}
            style={{ borderInlineEnd: 0, background: 'transparent' }}
          />
        )}
      </Spin>
    </div>
  );

  // ── 右栏：邮件列表 + 详情 ──
  const emailWorkbench = (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(260px, 360px) 1fr',
        gap: 0,
        height: '100%',
        minHeight: 0,
      }}
    >
      <div
        style={{
          minHeight: 0,
          overflow: 'auto',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <div
          style={{
            padding: '8px 10px',
            borderBottom: '1px solid rgba(5,5,5,0.04)',
            display: 'flex',
            gap: 8,
            flexWrap: 'wrap',
            alignItems: 'center',
          }}
        >
          <MailOutlined />
          <Typography.Text strong>邮件列表</Typography.Text>
          {method ? (
            <Tag color="default" variant="outlined">
              {method}
            </Tag>
          ) : null}
          {polling ? <Badge status="processing" text="监听中" /> : null}
          <Select
            size="small"
            style={{ width: 100 }}
            value={readFilter}
            options={[
              { label: '全部', value: 'all' },
              { label: '未读', value: 'unread' },
              { label: '已读', value: 'read' },
            ]}
            onChange={setReadFilter}
          />
          <Input.Search
            size="small"
            allowClear
            placeholder="箱内搜索"
            style={{ width: 120 }}
            onSearch={setListSearch}
            onChange={(e) => {
              if (!e.target.value) setListSearch('');
            }}
          />
        </div>
        <div style={{ flex: 1, overflow: 'auto' }}>
          {!selectedEmail ? (
            <Empty style={{ margin: 48 }} description="请先选择账号" />
          ) : (
            <Spin spinning={listLoading}>
              {filteredEmails.length === 0 && !listLoading ? (
                <Empty
                  style={{ margin: 48 }}
                  description={listError ? '加载失败' : '没有匹配邮件'}
                />
              ) : (
                <List
                  dataSource={filteredEmails}
                  rowKey={(item) => item.id}
                  renderItem={(item) => {
                    const active = item.id === activeId;
                    const unread = item.is_read === false;
                    return (
                      <List.Item
                        style={{
                          padding: '10px 12px',
                          cursor: 'pointer',
                          background: active ? token.colorPrimaryBg : undefined,
                        }}
                        onClick={() => void openDetail(item)}
                        actions={[
                          <Checkbox
                            key="cb"
                            checked={selectedIds.includes(item.id)}
                            onClick={(e) => e.stopPropagation()}
                            onChange={(e) => {
                              setSelectedIds((prev) =>
                                e.target.checked
                                  ? [...prev, item.id]
                                  : prev.filter((id) => id !== item.id),
                              );
                            }}
                          />,
                        ]}
                      >
                        <List.Item.Meta
                          title={
                            <Typography.Text strong={unread} ellipsis>
                              {item.subject || '无主题'}
                            </Typography.Text>
                          }
                          description={
                            <Space
                              direction="vertical"
                              size={0}
                              style={{ width: '100%' }}
                            >
                              <Typography.Text type="secondary" ellipsis>
                                {item.from || '未知发件人'}
                              </Typography.Text>
                              <Typography.Text
                                type="secondary"
                                style={{ fontSize: 12 }}
                              >
                                {formatDate(item.date)}
                              </Typography.Text>
                            </Space>
                          }
                        />
                      </List.Item>
                    );
                  }}
                />
              )}
              {hasMore ? (
                <div style={{ padding: 12, textAlign: 'center' }}>
                  <Button
                    loading={listLoading}
                    onClick={() =>
                      void loadEmails({
                        append: true,
                        nextSkip: skip + PAGE_SIZE,
                      })
                    }
                  >
                    加载更多
                  </Button>
                </div>
              ) : null}
            </Spin>
          )}
        </div>
      </div>

      <div style={{ minHeight: 0, overflow: 'auto', padding: 12 }}>
        <Spin spinning={detailLoading}>
          {!detail ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="选择一封邮件查看详情"
              style={{ marginTop: 80 }}
            />
          ) : (
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Typography.Title level={5} style={{ margin: 0 }}>
                {detail.subject || '无主题'}
              </Typography.Title>
              <Space wrap>
                <Typography.Text type="secondary">
                  信任原始 HTML
                </Typography.Text>
                <Switch checked={trusted} onChange={onToggleTrust} />
                <Button
                  size="small"
                  icon={<KeyOutlined />}
                  loading={extracting}
                  onClick={() => void onExtractVerification()}
                >
                  提取并复制验证码
                </Button>
                {lastVerification ? (
                  <Button
                    size="small"
                    icon={<CopyOutlined />}
                    onClick={async () => {
                      const ok = await copyText(lastVerification);
                      message.success(
                        ok ? `已复制: ${lastVerification}` : lastVerification,
                      );
                    }}
                  >
                    再次复制
                  </Button>
                ) : null}
              </Space>
              {lastVerification ? (
                <Alert
                  type="success"
                  showIcon
                  message="最近提取结果"
                  description={
                    <Typography.Paragraph copyable style={{ marginBottom: 0 }}>
                      {lastVerification}
                    </Typography.Paragraph>
                  }
                />
              ) : null}
              <div>
                <Typography.Text type="secondary">发件人：</Typography.Text>
                <Typography.Text>{detail.from || '--'}</Typography.Text>
              </div>
              {detail.to ? (
                <div>
                  <Typography.Text type="secondary">收件人：</Typography.Text>
                  <Typography.Text>{detail.to}</Typography.Text>
                </div>
              ) : null}
              <div>
                <Typography.Text type="secondary">时间：</Typography.Text>
                <Typography.Text>{formatDate(detail.date)}</Typography.Text>
              </div>
              <div
                style={{
                  borderTop: '1px solid rgba(0,0,0,0.06)',
                  paddingTop: 12,
                }}
              >
                <iframe
                  title="email-body"
                  sandbox={
                    trusted
                      ? 'allow-same-origin allow-popups allow-popups-to-escape-sandbox'
                      : 'allow-same-origin'
                  }
                  srcDoc={bodyHtml}
                  style={{
                    width: '100%',
                    minHeight: 360,
                    border: 'none',
                    background: '#fff',
                  }}
                />
              </div>
            </Space>
          )}
        </Spin>
      </div>
    </div>
  );

  const compactGroupOptions = useMemo(
    () => [
      { label: '全部', value: 'all' },
      ...groups.map((g) => ({
        label:
          g.account_count != null ? `${g.name} (${g.account_count})` : g.name,
        value: String(g.id),
      })),
    ],
    [groups],
  );

  // ── Compact 视图 ──
  const compactView = (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Space wrap style={{ width: '100%' }} align="center">
        <Typography.Text type="secondary">分组</Typography.Text>
        <Segmented
          size="small"
          value={groupId == null ? 'all' : String(groupId)}
          options={compactGroupOptions}
          onChange={(value) =>
            onGroupChange(value === 'all' ? undefined : Number(value))
          }
        />
        <Input.Search
          allowClear
          placeholder="搜索账号"
          style={{ width: 220, marginLeft: 'auto' }}
          onSearch={setCompactSearch}
          onChange={(e) => {
            if (!e.target.value) setCompactSearch('');
          }}
        />
      </Space>

      <ProCard
        variant="borderless"
        title={
          <Space>
            <span>简洁账号列表</span>
            <Typography.Text type="secondary">
              {filteredCompactAccounts.length} 个账号
              {compactSelected.length
                ? ` · 已选 ${compactSelected.length}`
                : ''}
            </Typography.Text>
          </Space>
        }
        extra={
          <Space>
            <Button
              size="small"
              disabled={!compactSelected.length}
              onClick={() => {
                compactSelected.forEach((id) => {
                  const acc = accounts.find((a) => a.id === id);
                  if (acc?.email) void onTogglePoll(acc.email);
                });
              }}
            >
              批量切换监听
            </Button>
            <Button size="small" onClick={() => setCompactSelected([])}>
              清除选择
            </Button>
          </Space>
        }
        styles={{ body: { padding: 0 } }}
      >
        <Spin spinning={accountsQuery.isLoading}>
          {filteredCompactAccounts.length === 0 ? (
            <Empty style={{ margin: 48 }} description="当前分组暂无账号" />
          ) : (
            <List
              dataSource={filteredCompactAccounts}
              rowKey={(a) => a.id}
              renderItem={(account) => {
                const snap = pollSnapMap.get(account.email);
                const isPoll = isPolling(account.email);
                const checked = compactSelected.includes(account.id);
                const pulling = !!pullingEmails[account.email];
                return (
                  <List.Item
                    style={{
                      padding: '12px 16px',
                      background: checked ? token.colorPrimaryBg : undefined,
                    }}
                    actions={[
                      <Button
                        key="code"
                        size="small"
                        icon={<KeyOutlined />}
                        loading={
                          extracting && extractingEmail === account.email
                        }
                        onClick={() => void extractForEmail(account.email)}
                      >
                        {snap?.verification || '验证码'}
                      </Button>,
                      <Button
                        key="pull"
                        size="small"
                        loading={pulling}
                        onClick={() => void pullAccountSummary(account)}
                      >
                        拉取
                      </Button>,
                      <Button
                        key="poll"
                        size="small"
                        type={isPoll ? 'primary' : 'default'}
                        danger={isPoll}
                        onClick={() => void onTogglePoll(account.email)}
                      >
                        {isPoll
                          ? `停止 ${snap?.remaining != null ? snap.remaining : ''}`.trim()
                          : '监听'}
                      </Button>,
                      <Button
                        key="open"
                        size="small"
                        type="link"
                        onClick={() => {
                          onAccountChange(account.email);
                          onViewModeChange('standard');
                        }}
                      >
                        打开
                      </Button>,
                    ]}
                  >
                    <Space align="start">
                      <Checkbox
                        checked={checked}
                        onChange={(e) => {
                          setCompactSelected((prev) =>
                            e.target.checked
                              ? [...prev, account.id]
                              : prev.filter((id) => id !== account.id),
                          );
                        }}
                      />
                      <List.Item.Meta
                        title={
                          <Space>
                            <Typography.Text
                              copyable={{ text: account.email }}
                              strong
                            >
                              {account.email}
                            </Typography.Text>
                            {isPoll ? (
                              <Badge status="processing" text="监听中" />
                            ) : null}
                            <Tag color="default" variant="outlined">
                              {(
                                account.provider ||
                                account.account_type ||
                                'outlook'
                              ).toUpperCase()}
                            </Tag>
                            <Tag
                              color={
                                String(account.status || '').toLowerCase() ===
                                'active'
                                  ? 'success'
                                  : 'default'
                              }
                              variant="outlined"
                            >
                              {account.status || '--'}
                            </Tag>
                          </Space>
                        }
                        description={
                          <Space direction="vertical" size={0}>
                            <Typography.Text type="secondary">
                              分组：{account.group_name || '--'}
                              {account.remark ? ` · ${account.remark}` : ''}
                            </Typography.Text>
                            {snap?.lastMessage ? (
                              <Typography.Text
                                type={
                                  snap.status === 'found'
                                    ? 'success'
                                    : 'secondary'
                                }
                                style={{ fontSize: 12 }}
                              >
                                {snap.lastMessage}
                                {snap.verification
                                  ? ` · ${snap.verification}`
                                  : ''}
                              </Typography.Text>
                            ) : (
                              <Typography.Text
                                type="secondary"
                                style={{ fontSize: 12 }}
                              >
                                最近刷新：{account.last_refresh_at || '--'}
                              </Typography.Text>
                            )}
                          </Space>
                        }
                      />
                    </Space>
                  </List.Item>
                );
              }}
            />
          )}
        </Spin>
      </ProCard>
    </Space>
  );

  return (
    <PageContainer
      title={intl.formatMessage({
        id: 'outlook.mailbox.title',
        defaultMessage: '邮箱',
      })}
      subTitle={intl.formatMessage({
        id: 'outlook.mailbox.subtitle',
        defaultMessage: '阅读与管理选中账号的邮件',
      })}
      extra={
        <Space wrap>
          <Segmented
            value={viewMode}
            onChange={onViewModeChange}
            options={[
              {
                label: (
                  <Space size={4}>
                    <ColumnWidthOutlined />
                    标准三栏
                  </Space>
                ),
                value: 'standard',
              },
              {
                label: (
                  <Space size={4}>
                    <AppstoreOutlined />
                    简洁
                  </Space>
                ),
                value: 'compact',
              },
            ]}
          />
          {viewMode === 'standard' ? (
            <Tooltip title="恢复默认三栏宽度与折叠状态">
              <Button
                icon={<UnorderedListOutlined />}
                onClick={() => setLayoutResetToken((n) => n + 1)}
              >
                重置布局
              </Button>
            </Tooltip>
          ) : null}
          <Select
            style={{ width: 140 }}
            value={folder}
            options={FOLDERS}
            onChange={onFolderChange}
          />
          <Button
            icon={<ReloadOutlined />}
            loading={listLoading || accountsQuery.isFetching}
            onClick={() => {
              void accountsQuery.refetch();
              if (viewMode === 'standard') {
                void loadEmails({ append: false, nextSkip: 0 });
              }
            }}
          >
            刷新
          </Button>
          {viewMode === 'standard' ? (
            <>
              <Button
                type={polling ? 'default' : 'primary'}
                onClick={() => void onTogglePoll()}
                disabled={!selectedEmail}
              >
                {polling
                  ? `停止监听${
                      pollSnap?.remaining != null
                        ? ` (${pollSnap.remaining})`
                        : ''
                    }`
                  : '开始监听'}
              </Button>
              <Button
                type="primary"
                icon={<KeyOutlined />}
                loading={extracting}
                onClick={() => void onExtractVerification()}
                disabled={!selectedEmail}
              >
                复制验证码
              </Button>
              {selectedIds.length > 0 ? (
                <Popconfirm
                  title={`确认永久删除选中的 ${selectedIds.length} 封邮件？`}
                  onConfirm={() => void onDeleteSelected()}
                >
                  <Button danger icon={<DeleteOutlined />}>
                    删除选中
                  </Button>
                </Popconfirm>
              ) : null}
            </>
          ) : null}
        </Space>
      }
    >
      {listError && viewMode === 'standard' ? (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message={listError}
          description={
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Typography.Text type="secondary">
                请检查账号授权或代理设置，也可前往 Token 工具重新授权。
              </Typography.Text>
              {listErrorDetails ? (
                <Collapse
                  ghost
                  size="small"
                  items={[
                    {
                      key: 'tech',
                      label: '技术详情',
                      children: (
                        <Typography.Paragraph
                          type="secondary"
                          copyable
                          style={{
                            marginBottom: 0,
                            whiteSpace: 'pre-wrap',
                            fontSize: 12,
                            fontFamily: 'monospace',
                          }}
                        >
                          {typeof listErrorDetails === 'string'
                            ? listErrorDetails
                            : JSON.stringify(listErrorDetails, null, 2)}
                        </Typography.Paragraph>
                      ),
                    },
                  ]}
                />
              ) : null}
            </Space>
          }
          action={
            <Button
              size="small"
              onClick={() => void loadEmails({ append: false, nextSkip: 0 })}
            >
              重试
            </Button>
          }
        />
      ) : null}

      {pollSnap?.lastMessage && viewMode === 'standard' ? (
        <Alert
          type={pollSnap.status === 'found' ? 'success' : 'info'}
          showIcon
          closable
          style={{ marginBottom: 16 }}
          message={pollSnap.lastMessage}
          description={
            pollSnap.verification ? (
              <Typography.Text copyable>
                {pollSnap.verification}
              </Typography.Text>
            ) : null
          }
        />
      ) : null}

      {viewMode === 'compact' ? (
        compactView
      ) : (
        <ResizableWorkbench
          userId={String(layoutUserId)}
          resetToken={layoutResetToken}
          groups={groupsPane}
          accounts={accountsPane}
          emails={emailWorkbench}
        />
      )}
    </PageContainer>
  );
};

export default MailboxPage;
