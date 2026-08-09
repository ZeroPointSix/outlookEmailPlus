import {
  AppstoreOutlined,
  MailOutlined,
  PlusOutlined,
  ReloadOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  App,
  Button,
  Empty,
  Form,
  Input,
  List,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';
import React, { useEffect, useMemo, useState } from 'react';
import {
  clearTempEmailMessages,
  deleteTempEmail,
  extractTempEmailVerification,
  fetchTempEmailMessageDetail,
  fetchTempEmailMessages,
  fetchTempEmailOptions,
  fetchTempEmails,
  generateTempEmail,
  pickTempErrorMessage,
  type TempEmailDetail,
  type TempEmailItem,
  type TempEmailMessage,
} from '@/services/outlook/tempEmails';
import { MailboxActions } from './MailboxActions';
import { TempMailStatus } from './TempMailStatus';
import {
  getMailboxProviderPresentation,
  providerKindLabel,
  resolveTempMailAvailability,
} from './utils';
import { history, useIntl } from '@umijs/max';

function formatDate(value?: string | number) {
  if (value === undefined || value === null || value === '') return '--';
  try {
    if (typeof value === 'number') {
      const ms = value > 1e12 ? value : value * 1000;
      return new Date(ms).toLocaleString();
    }
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return d.toLocaleString();
  } catch {
    return String(value);
  }
}

const TempEmailsPage: React.FC = () => {
  const { message } = App.useApp();
  const intl = useIntl();
  const queryClient = useQueryClient();
  const [form] = Form.useForm();

  const [providerName, setProviderName] = useState<string | undefined>();
  const [selectedEmail, setSelectedEmail] = useState<string | undefined>();
  const [messages, setMessages] = useState<TempEmailMessage[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [messagesError, setMessagesError] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [detail, setDetail] = useState<TempEmailDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [generating, setGenerating] = useState(false);

  const listQuery = useQuery({
    queryKey: ['temp-emails'],
    queryFn: fetchTempEmails,
  });

  const optionsQuery = useQuery({
    queryKey: ['temp-email-options', providerName || ''],
    queryFn: () => fetchTempEmailOptions(providerName),
  });

  const mailboxes: TempEmailItem[] = listQuery.data?.emails || [];
  const tempOptions = optionsQuery.data?.options;
  const providerCatalog = tempOptions?.providers || [];
  const optionsErrorMessage = pickTempErrorMessage(
    (optionsQuery.error as any)?.response?.data || optionsQuery.data,
    '临时邮箱服务当前不可用',
  );
  const availability = useMemo(
    () =>
      resolveTempMailAvailability(tempOptions, {
        loading: optionsQuery.isLoading,
        failed: optionsQuery.isError || optionsQuery.data?.success === false,
        errorMessage: optionsErrorMessage,
      }),
    [
      optionsErrorMessage,
      optionsQuery.data?.success,
      optionsQuery.isError,
      optionsQuery.isLoading,
      tempOptions,
    ],
  );

  const domainOptions = useMemo(() => {
    const domains = optionsQuery.data?.options?.domains || [];
    return domains
      .filter((d) => d && d.enabled !== false)
      .map((d) => {
        const name = d.name || d.domain || '';
        return { label: name, value: name };
      })
      .filter((d) => d.value);
  }, [optionsQuery.data]);

  const providerOptions = useMemo(() => {
    return providerCatalog
      .map((p) => {
        const kindSuffix = p.kind === 'plugin' ? ' · 插件' : '';
        const activeSuffix = p.active ? ' · 当前' : '';
        return {
          label: `${p.label || p.name || ''}${kindSuffix}${activeSuffix}`,
          value: p.name || '',
        };
      })
      .filter((p) => p.value);
  }, [providerCatalog]);

  useEffect(() => {
    const resolvedProvider = tempOptions?.provider_name;
    if (!providerName && resolvedProvider && !form.getFieldValue('provider_name')) {
      form.setFieldValue('provider_name', resolvedProvider);
    }
  }, [form, providerName, tempOptions?.provider_name]);

  const reloadList = async () => {
    await queryClient.invalidateQueries({ queryKey: ['temp-emails'] });
  };

  const loadMessages = async (email: string) => {
    setMessagesLoading(true);
    setMessagesError(null);
    try {
      const res = await fetchTempEmailMessages(email);
      if (res?.success) {
        setMessages(res.emails || []);
      } else {
        setMessages([]);
        setMessagesError(pickTempErrorMessage(res, '加载邮件失败'));
      }
    } catch (error: any) {
      const data = error?.response?.data;
      setMessages([]);
      setMessagesError(pickTempErrorMessage(data, error?.message || '加载邮件失败'));
    } finally {
      setMessagesLoading(false);
    }
  };

  useEffect(() => {
    if (!selectedEmail) {
      setMessages([]);
      setDetail(null);
      setActiveId(null);
      return;
    }
    setDetail(null);
    setActiveId(null);
    void loadMessages(selectedEmail);
  }, [selectedEmail]);

  const onGenerate = async () => {
    if (!availability.canGenerate) {
      message.warning(availability.message);
      return;
    }
    const values = await form.validateFields().catch(() => null);
    if (!values) return;
    setGenerating(true);
    try {
      const res = await generateTempEmail({
        prefix: values.prefix?.trim() || undefined,
        domain: values.domain || undefined,
        provider_name: values.provider_name || providerName || undefined,
      });
      if (res?.success && res.email) {
        message.success(res.message || `已生成: ${res.email}`);
        form.setFieldValue('prefix', undefined);
        await reloadList();
        setSelectedEmail(res.email);
      } else {
        message.error(pickTempErrorMessage(res, '生成失败'));
      }
    } catch (error: any) {
      message.error(
        pickTempErrorMessage(error?.response?.data, error?.message || '生成失败'),
      );
    } finally {
      setGenerating(false);
    }
  };

  const onDeleteMailbox = async (email: string) => {
    try {
      const res = await deleteTempEmail(email);
      if (res?.success === false) {
        message.error(pickTempErrorMessage(res, '删除失败'));
        return;
      }
      message.success('已删除');
      if (selectedEmail === email) {
        setSelectedEmail(undefined);
      }
      await reloadList();
    } catch (error: any) {
      message.error(
        pickTempErrorMessage(error?.response?.data, error?.message || '删除失败'),
      );
    }
  };

  const onClearMessages = async (email: string) => {
    try {
      const res = await clearTempEmailMessages(email);
      if (res?.success === false) {
        message.error(pickTempErrorMessage(res, '清空失败'));
        return;
      }
      message.success('邮件已清空');
      setDetail(null);
      setActiveId(null);
      await loadMessages(email);
    } catch (error: any) {
      message.error(
        pickTempErrorMessage(error?.response?.data, error?.message || '清空失败'),
      );
    }
  };

  const onExtractCode = async (email: string) => {
    try {
      const res = await extractTempEmailVerification(email);
      if (res?.success) {
        const text =
          res.data?.formatted ||
          res.data?.verification_code ||
          res.data?.code ||
          res.data?.verificationCode ||
          res.data?.verification_link;
        if (text) {
          try {
            await navigator.clipboard.writeText(String(text));
            message.success(`已复制: ${text}`);
          } catch {
            message.success(`验证码: ${text}`);
          }
        } else {
          message.info(res.message || '未提取到验证码');
        }
      } else {
        message.error(pickTempErrorMessage(res, '提取失败'));
      }
    } catch (error: any) {
      message.error(
        pickTempErrorMessage(error?.response?.data, error?.message || '提取失败'),
      );
    }
  };

  const openDetail = async (item: TempEmailMessage) => {
    if (!selectedEmail || !item?.id) return;
    setActiveId(item.id);
    setDetailLoading(true);
    setDetail(null);
    try {
      const res = await fetchTempEmailMessageDetail(selectedEmail, item.id);
      if (res?.success && res.email) {
        setDetail(res.email);
      } else {
        message.error(pickTempErrorMessage(res, '获取详情失败'));
      }
    } catch (error: any) {
      message.error(
        pickTempErrorMessage(error?.response?.data, error?.message || '获取详情失败'),
      );
    } finally {
      setDetailLoading(false);
    }
  };

  const bodyHtml = useMemo(() => {
    if (!detail?.body) return '';
    if (String(detail.body_type || '').toLowerCase() === 'text') {
      const escaped = String(detail.body)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
      return `<pre style="white-space:pre-wrap;font-family:inherit;margin:0">${escaped}</pre>`;
    }
    return detail.body;
  }, [detail]);

  const tempMailActionButtons = (
    <Space wrap>
      <Button
        size="small"
        icon={<SettingOutlined />}
        onClick={() => history.push('/settings')}
      >
        临时邮箱设置
      </Button>
      <Button
        size="small"
        icon={<AppstoreOutlined />}
        onClick={() => history.push('/plugins')}
      >
        插件管理
      </Button>
    </Space>
  );

  return (
    <PageContainer
      title={intl.formatMessage({
        id: 'outlook.tempEmails.title',
        defaultMessage: '临时邮箱',
      })}
      subTitle={intl.formatMessage({
        id: 'outlook.tempEmails.subtitle',
        defaultMessage: '管理临时邮箱地址',
      })}
      extra={
        <Button
          icon={<ReloadOutlined />}
          loading={listQuery.isFetching}
          onClick={() => void reloadList()}
        >
          刷新列表
        </Button>
      }
    >
      <TempMailStatus
        availability={availability}
        options={tempOptions}
        actions={tempMailActionButtons}
      />

      <ProCard
        title="生成临时邮箱"
        variant="outlined"
        style={{ marginBottom: 16 }}
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            loading={generating}
            disabled={!availability.canGenerate}
            onClick={() => void onGenerate()}
          >
            生成
          </Button>
        }
      >
        <Form form={form} layout="inline" style={{ rowGap: 12 }}>
          {providerOptions.length > 0 ? (
            <Form.Item name="provider_name" label="服务商">
              <Select
                allowClear
                placeholder="默认服务商"
                style={{ width: 180 }}
                options={providerOptions}
                onChange={(v) => {
                  setProviderName(v || undefined);
                  form.setFieldValue('domain', undefined);
                }}
              />
            </Form.Item>
          ) : null}
          <Form.Item name="prefix" label="前缀">
            <Input placeholder="可选前缀" style={{ width: 160 }} allowClear />
          </Form.Item>
          <Form.Item name="domain" label="域名">
            <Select
              allowClear
              placeholder={
                optionsQuery.isLoading
                  ? '加载中…'
                  : domainOptions.length
                    ? '选择域名'
                    : '无可用域名'
              }
              style={{ width: 200 }}
              options={domainOptions}
              loading={optionsQuery.isLoading}
              disabled={!domainOptions.length}
            />
          </Form.Item>
        </Form>
        {optionsQuery.isError || optionsQuery.data?.success === false ? (
          <Alert
            type="warning"
            showIcon
            style={{ marginTop: 12 }}
            message={optionsErrorMessage}
          />
        ) : null}
      </ProCard>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 300px), 1fr))',
          gap: 16,
          minHeight: 480,
        }}
      >
        <ProCard
          title={`邮箱 (${mailboxes.length})`}
          variant="outlined"
          styles={{ body: { padding: 0, maxHeight: 620, overflow: 'auto' } }}
        >
          <Spin spinning={listQuery.isLoading || listQuery.isFetching}>
            {mailboxes.length === 0 ? (
              <Empty style={{ margin: 40 }} description="暂无临时邮箱" />
            ) : (
              <List
                dataSource={mailboxes}
                rowKey={(item) => item.email}
                renderItem={(item) => {
                  const active = item.email === selectedEmail;
                  const providerPresentation = getMailboxProviderPresentation(
                    item,
                    providerCatalog,
                  );
                  return (
                    <List.Item
                      style={{
                        padding: '10px 14px',
                        cursor: 'pointer',
                        background: active ? 'rgba(184, 92, 56, 0.08)' : undefined,
                        borderLeft: active
                          ? '3px solid #B85C38'
                          : '3px solid transparent',
                      }}
                      onClick={() => setSelectedEmail(item.email)}
                      actions={[
                        <MailboxActions
                          key="actions"
                          capabilities={providerPresentation.capabilities}
                          onExtractVerification={() =>
                            void onExtractCode(item.email)
                          }
                          onClearMessages={() =>
                            void onClearMessages(item.email)
                          }
                          onDeleteMailbox={() =>
                            void onDeleteMailbox(item.email)
                          }
                        />,
                      ]}
                    >
                      <List.Item.Meta
                        title={
                          <Typography.Text copyable ellipsis style={{ maxWidth: 160 }}>
                            {item.email}
                          </Typography.Text>
                        }
                        description={
                          <Space wrap size={[4, 4]}>
                            <Tag
                              color={
                                providerPresentation.kind === 'legacy'
                                  ? 'warning'
                                  : providerPresentation.kind === 'plugin'
                                    ? 'processing'
                                    : undefined
                              }
                            >
                              {providerKindLabel(providerPresentation.kind)}
                            </Tag>
                            <Typography.Text
                              type="secondary"
                              ellipsis
                              title={providerPresentation.label}
                              style={{ fontSize: 12, maxWidth: 170 }}
                            >
                              {providerPresentation.label}
                            </Typography.Text>
                          </Space>
                        }
                      />
                    </List.Item>
                  );
                }}
              />
            )}
          </Spin>
        </ProCard>

        <ProCard
          title={
            <Space>
              <MailOutlined />
              <span>邮件</span>
              {selectedEmail ? (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {selectedEmail}
                </Typography.Text>
              ) : null}
            </Space>
          }
          variant="outlined"
          extra={
            selectedEmail ? (
              <Button
                size="small"
                icon={<ReloadOutlined />}
                loading={messagesLoading}
                onClick={() => void loadMessages(selectedEmail)}
              >
                刷新
              </Button>
            ) : null
          }
          styles={{ body: { padding: 0, maxHeight: 620, overflow: 'auto' } }}
        >
          {!selectedEmail ? (
            <Empty style={{ margin: 48 }} description="选择左侧邮箱" />
          ) : (
            <Spin spinning={messagesLoading}>
              {messagesError ? (
                <Alert
                  type="error"
                  showIcon
                  style={{ margin: 12 }}
                  message={messagesError}
                />
              ) : null}
              {messages.length === 0 && !messagesLoading ? (
                <Empty style={{ margin: 48 }} description="暂无邮件" />
              ) : (
                <List
                  dataSource={messages}
                  rowKey={(item) => item.id}
                  renderItem={(item) => {
                    const active = item.id === activeId;
                    return (
                      <List.Item
                        style={{
                          padding: '12px 14px',
                          cursor: 'pointer',
                          background: active
                            ? 'rgba(184, 92, 56, 0.08)'
                            : undefined,
                        }}
                        onClick={() => void openDetail(item)}
                      >
                        <List.Item.Meta
                          title={
                            <Typography.Text ellipsis>
                              {item.subject || '无主题'}
                            </Typography.Text>
                          }
                          description={
                            <Space direction="vertical" size={0} style={{ width: '100%' }}>
                              <Typography.Text type="secondary" ellipsis>
                                {item.from || '未知'}
                              </Typography.Text>
                              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                {formatDate(item.date || item.timestamp)}
                              </Typography.Text>
                            </Space>
                          }
                        />
                      </List.Item>
                    );
                  }}
                />
              )}
            </Spin>
          )}
        </ProCard>

        <ProCard
          title={detail?.subject || '邮件详情'}
          variant="outlined"
          styles={{ body: { minHeight: 480 } }}
        >
          <Spin spinning={detailLoading}>
            {!detail ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="选择一封邮件查看详情"
              />
            ) : (
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                <div>
                  <Typography.Text type="secondary">发件人：</Typography.Text>
                  <Typography.Text>{detail.from || '--'}</Typography.Text>
                </div>
                <div>
                  <Typography.Text type="secondary">收件人：</Typography.Text>
                  <Typography.Text>{detail.to || selectedEmail || '--'}</Typography.Text>
                </div>
                <div>
                  <Typography.Text type="secondary">时间：</Typography.Text>
                  <Typography.Text>
                    {formatDate(detail.date || detail.timestamp)}
                  </Typography.Text>
                </div>
                <div
                  style={{
                    borderTop: '1px solid rgba(0,0,0,0.06)',
                    paddingTop: 12,
                  }}
                >
                  <iframe
                    title="temp-email-body"
                    sandbox=""
                    srcDoc={bodyHtml}
                    style={{
                      width: '100%',
                      minHeight: 320,
                      border: 'none',
                      background: '#fff',
                    }}
                  />
                </div>
              </Space>
            )}
          </Spin>
        </ProCard>
      </div>
    </PageContainer>
  );
};

export default TempEmailsPage;
