import {
  ApiOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
  SyncOutlined,
  UndoOutlined,
} from '@ant-design/icons';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useIntl } from '@umijs/max';
import {
  Alert,
  App,
  AutoComplete,
  Button,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  theme,
} from 'antd';
import React, { useCallback, useEffect, useState } from 'react';
import {
  type UnsavedChangesDecision,
  useUnsavedChangesGuard,
} from '@/hooks/useUnsavedChangesGuard';
import {
  type ExternalApiKeyItem,
  fetchDeploymentInfo,
  fetchSettings,
  normalizePollingSettings,
  POLLING_COUNT_MAX,
  POLLING_COUNT_MIN,
  POLLING_INTERVAL_MAX,
  POLLING_INTERVAL_MIN,
  pickSettingsError,
  syncCfWorkerDomains,
  testEmailNotification,
  testTelegram,
  testVerificationAi,
  testWebhook,
  triggerSystemUpdate,
  updateSettings,
  type VerificationAiTestResponse,
  validateCron,
} from '@/services/outlook/settings';
import {
  inferVerificationAiProvider,
  normalizeVerificationAiEndpoint,
  OPENAI_VERIFICATION_AI_BASE_URL,
  VERIFICATION_AI_MODEL_OPTIONS,
  type VerificationAiProvider,
} from './aiConfig';

type KeyRow = ExternalApiKeyItem & { _localId: string };

const AI_ERROR_CATEGORY_LABELS: Record<string, string> = {
  authentication: 'API Key / 权限',
  configuration: '配置',
  contract: '返回契约',
  endpoint: 'URL / 路径',
  network: '网络',
  protocol: 'API 类型',
  rate_limit: '限流 / 额度',
  server: '服务端',
};

const newLocalId = () =>
  `local_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

const SettingsPage: React.FC = () => {
  const { message, modal } = App.useApp();
  const intl = useIntl();
  const queryClient = useQueryClient();
  const { token } = theme.useToken();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [keyRows, setKeyRows] = useState<KeyRow[]>([]);
  const [originalKeysCanonical, setOriginalKeysCanonical] = useState('[]');
  const [deployment, setDeployment] = useState<Record<string, any> | null>(
    null,
  );
  const [deploymentLoading, setDeploymentLoading] = useState(false);
  const [updateLoading, setUpdateLoading] = useState(false);
  const [cfSyncLoading, setCfSyncLoading] = useState(false);
  const [aiTestLoading, setAiTestLoading] = useState(false);
  const [aiTestResult, setAiTestResult] =
    useState<VerificationAiTestResponse | null>(null);
  const aiProvider =
    (Form.useWatch('verification_ai_provider', form) as
      | VerificationAiProvider
      | undefined) || 'openai_compatible';
  const aiBaseUrl = String(
    Form.useWatch('verification_ai_base_url', form) || '',
  );
  const aiEnabled = !!Form.useWatch('verification_ai_enabled', form);

  const settingsQuery = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  });

  const confirmUnsavedNavigation = useCallback(
    ({ proceed, stay }: UnsavedChangesDecision) => {
      modal.confirm({
        title: '放弃未保存的更改并离开？',
        content: '离开系统设置会丢失当前表单中尚未保存的修改。',
        okText: '放弃并离开',
        okButtonProps: { danger: true },
        cancelText: '继续编辑',
        onOk: proceed,
        onCancel: stay,
      });
    },
    [modal],
  );
  useUnsavedChangesGuard(dirty, confirmUnsavedNavigation);

  // 后端 GET 返回脱敏占位；PUT 时若值仍等于脱敏串则视为未修改（后端会跳过）
  const [secretMasks, setSecretMasks] = useState<Record<string, string>>({});

  useEffect(() => {
    if (dirty) return;
    const s = settingsQuery.data?.settings;
    if (!s) return;
    const masks: Record<string, string> = {
      telegram_bot_token: String(s.telegram_bot_token || ''),
      webhook_notification_token: String(s.webhook_notification_token || ''),
      verification_ai_api_key: String(s.verification_ai_api_key_masked || ''),
      temp_mail_api_key: String(s.temp_mail_api_key_masked || ''),
      external_api_key: String(s.external_api_key_masked || ''),
      cf_worker_admin_key: String(s.cf_worker_admin_key_masked || ''),
      watchtower_token: String(s.watchtower_token || ''),
    };
    setSecretMasks(masks);

    const keys: KeyRow[] = (
      Array.isArray(s.external_api_keys) ? s.external_api_keys : []
    ).map((item: ExternalApiKeyItem) => ({
      ...item,
      api_key: item.api_key || item.api_key_masked || '',
      allowed_emails: Array.isArray(item.allowed_emails)
        ? item.allowed_emails
        : typeof item.allowed_emails === 'string' && item.allowed_emails
          ? item.allowed_emails
              .split(/[\n,]/)
              .map((x) => x.trim())
              .filter(Boolean)
          : [],
      _localId: item.id != null ? `id_${item.id}` : newLocalId(),
    }));
    setKeyRows(keys);
    setOriginalKeysCanonical(
      JSON.stringify(
        keys.map((k) => ({
          id: k.id,
          name: k.name || '',
          api_key: k.api_key || '',
          enabled: k.enabled !== false,
          pool_access: !!k.pool_access,
          allowed_emails: k.allowed_emails || [],
        })),
      ),
    );

    const whitelist = Array.isArray(s.external_api_ip_whitelist)
      ? s.external_api_ip_whitelist.join('\n')
      : typeof s.external_api_ip_whitelist === 'string'
        ? s.external_api_ip_whitelist
        : '';

    const pollingSettings = normalizePollingSettings(
      Number(s.polling_interval ?? 10),
      Number(s.polling_count ?? 5),
    );

    form.setFieldsValue({
      enable_scheduled_refresh:
        s.enable_scheduled_refresh === 'true' ||
        s.enable_scheduled_refresh === true,
      use_cron_schedule:
        s.use_cron_schedule === 'true' || s.use_cron_schedule === true,
      refresh_cron: s.refresh_cron || '0 2 * * *',
      refresh_interval_days: Number(s.refresh_interval_days || 30),
      refresh_delay_seconds: Number(s.refresh_delay_seconds || 5),
      enable_auto_polling: !!s.enable_auto_polling,
      polling_interval: pollingSettings.polling_interval,
      polling_count: pollingSettings.polling_count,
      email_notification_enabled: !!s.email_notification_enabled,
      email_notification_recipient: s.email_notification_recipient || '',
      webhook_notification_enabled: !!s.webhook_notification_enabled,
      webhook_notification_url: s.webhook_notification_url || '',
      webhook_notification_token: masks.webhook_notification_token,
      telegram_bot_token: masks.telegram_bot_token,
      telegram_chat_id: s.telegram_chat_id || '',
      telegram_poll_interval: Number(s.telegram_poll_interval || 600),
      telegram_proxy_url: s.telegram_proxy_url || '',
      verification_ai_enabled: !!s.verification_ai_enabled,
      verification_ai_provider: inferVerificationAiProvider(
        s.verification_ai_base_url || '',
      ),
      verification_ai_base_url: s.verification_ai_base_url || '',
      verification_ai_model: s.verification_ai_model || '',
      verification_ai_api_key: masks.verification_ai_api_key,
      temp_mail_provider: s.temp_mail_provider || '',
      temp_mail_api_base_url: s.temp_mail_api_base_url || '',
      temp_mail_api_key: masks.temp_mail_api_key,
      cf_worker_base_url: s.cf_worker_base_url || '',
      cf_worker_admin_key: masks.cf_worker_admin_key,
      external_api_public_mode: !!s.external_api_public_mode,
      external_api_rate_limit_per_minute: Number(
        s.external_api_rate_limit_per_minute || 60,
      ),
      external_api_key: masks.external_api_key,
      external_api_ip_whitelist_text: whitelist,
      external_api_disable_raw_content: !!s.external_api_disable_raw_content,
      external_api_disable_wait_message: !!s.external_api_disable_wait_message,
      external_api_disable_pool_claim_random:
        !!s.external_api_disable_pool_claim_random,
      external_api_disable_pool_claim_release:
        !!s.external_api_disable_pool_claim_release,
      external_api_disable_pool_claim_complete:
        !!s.external_api_disable_pool_claim_complete,
      external_api_disable_pool_stats: !!s.external_api_disable_pool_stats,
      pool_external_enabled: !!s.pool_external_enabled,
      watchtower_url: s.watchtower_url || '',
      watchtower_token: masks.watchtower_token,
      update_method: s.update_method || 'watchtower',
      login_password: '',
    });
    setDirty(false);
  }, [dirty, settingsQuery.data, form]);

  const buildKeysPayload = (): ExternalApiKeyItem[] | null => {
    const normalized = keyRows.map((k) => ({
      id: k.id,
      name: String(k.name || '').trim(),
      api_key: String(k.api_key || '').trim(),
      enabled: k.enabled !== false,
      pool_access: !!k.pool_access,
      allowed_emails: Array.isArray(k.allowed_emails)
        ? k.allowed_emails
        : String(k.allowed_emails || '')
            .split(/[\n,]/)
            .map((x) => x.trim())
            .filter(Boolean),
    }));
    const canonical = JSON.stringify(normalized);
    if (canonical === originalKeysCanonical) {
      return null; // 未改动，不提交
    }
    for (const [i, item] of normalized.entries()) {
      if (!item.name) {
        throw new Error(`多 Key 第 ${i + 1} 项 name 不能为空`);
      }
      if (item.id == null && !item.api_key) {
        throw new Error(`多 Key「${item.name}」新建时 api_key 必填`);
      }
    }
    return normalized;
  };

  const onSave = async () => {
    const values = await form.validateFields().catch(() => null);
    if (!values) return;
    setSaving(true);
    try {
      const payload: Record<string, any> = {
        ...values,
        enable_scheduled_refresh: values.enable_scheduled_refresh
          ? 'true'
          : 'false',
        use_cron_schedule: values.use_cron_schedule ? 'true' : 'false',
      };
      delete payload.verification_ai_provider;

      // 敏感字段：空串 / 仍等于脱敏占位 → 不提交，避免误清空
      const secretKeys = [
        'telegram_bot_token',
        'webhook_notification_token',
        'verification_ai_api_key',
        'temp_mail_api_key',
        'external_api_key',
        'cf_worker_admin_key',
        'watchtower_token',
        'login_password',
      ] as const;
      for (const key of secretKeys) {
        const raw = String(values[key] ?? '').trim();
        const mask = String(secretMasks[key] || '');
        if (!raw || (mask && raw === mask)) {
          delete payload[key];
        }
      }

      // IP 白名单：文本 → string[]
      const wlText = String(values.external_api_ip_whitelist_text || '');
      payload.external_api_ip_whitelist = wlText
        .split('\n')
        .map((l: string) => l.trim())
        .filter(Boolean);
      delete payload.external_api_ip_whitelist_text;

      try {
        const keysPayload = buildKeysPayload();
        if (keysPayload) {
          payload.external_api_keys = keysPayload;
        }
      } catch (e: any) {
        message.error(e?.message || '多 Key 配置无效');
        return;
      }

      const res = await updateSettings(payload);
      if (res?.success === false) {
        message.error(pickSettingsError(res, '保存失败'));
        return;
      }
      message.success(res.message || '设置已保存');
      form.setFieldValue('login_password', '');
      await queryClient.invalidateQueries({ queryKey: ['settings'] });
      setDirty(false);
    } catch (error: any) {
      message.error(
        pickSettingsError(
          error?.data || error?.info || error?.response?.data,
          error?.message || '保存失败',
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  const runTest = async (
    fn: () => Promise<any>,
    okText = '测试成功',
    failText = '测试失败',
  ) => {
    try {
      const res = await fn();
      if (res?.success === false) {
        message.error(pickSettingsError(res, failText));
        return;
      }
      message.success(res?.message || okText);
    } catch (error: any) {
      message.error(
        pickSettingsError(
          error?.data || error?.info || error?.response?.data,
          error?.message || failText,
        ),
      );
    }
  };

  const loadDeployment = async () => {
    setDeploymentLoading(true);
    try {
      const res = await fetchDeploymentInfo();
      if (res?.success === false) {
        message.error(pickSettingsError(res, '获取部署信息失败'));
        return;
      }
      setDeployment(res.deployment || null);
    } catch (error: any) {
      message.error(error?.message || '获取部署信息失败');
    } finally {
      setDeploymentLoading(false);
    }
  };

  const onTriggerUpdate = () => {
    const method = form.getFieldValue('update_method') || 'watchtower';
    modal.confirm({
      title: '确认触发系统更新？',
      content: `将使用「${method}」方式触发系统更新`,
      onOk: async () => {
        setUpdateLoading(true);
        try {
          const res = await triggerSystemUpdate(String(method));
          if (res?.success === false) {
            message.error(pickSettingsError(res, '触发更新失败'));
            return;
          }
          message.success(res.message || '已触发更新');
          await loadDeployment();
        } catch (error: any) {
          message.error(error?.message || '触发更新失败');
        } finally {
          setUpdateLoading(false);
        }
      },
    });
  };

  const onSyncCfDomains = async () => {
    setCfSyncLoading(true);
    try {
      const res = await syncCfWorkerDomains();
      if (res?.success === false) {
        message.error(pickSettingsError(res, 'CF 域名同步失败'));
        return;
      }
      message.success(res.message || 'CF 域名同步成功');
      await queryClient.invalidateQueries({ queryKey: ['settings'] });
    } catch (error: any) {
      message.error(error?.message || 'CF 域名同步失败');
    } finally {
      setCfSyncLoading(false);
    }
  };

  const onAiProviderChange = (provider: VerificationAiProvider) => {
    const currentModel = String(
      form.getFieldValue('verification_ai_model') || '',
    ).trim();
    if (provider === 'openai') {
      form.setFieldsValue({
        verification_ai_base_url: OPENAI_VERIFICATION_AI_BASE_URL,
        verification_ai_model: currentModel || 'gpt-4.1-mini',
      });
    } else if (
      inferVerificationAiProvider(
        String(form.getFieldValue('verification_ai_base_url') || ''),
      ) === 'openai'
    ) {
      form.setFieldValue('verification_ai_base_url', '');
    }
    setAiTestResult(null);
    setDirty(true);
  };

  const runVerificationAiTest = async () => {
    const values = await form
      .validateFields([
        'verification_ai_base_url',
        'verification_ai_model',
        'verification_ai_api_key',
      ])
      .catch(() => null);
    if (!values) return;

    setAiTestLoading(true);
    setAiTestResult(null);
    try {
      const result = await testVerificationAi({
        verification_ai_enabled: aiEnabled,
        verification_ai_base_url: values.verification_ai_base_url,
        verification_ai_model: values.verification_ai_model,
        verification_ai_api_key: values.verification_ai_api_key,
      });
      setAiTestResult(result);
      if (result.ok && result.contract_ok) {
        message.success('AI 连接与验证码提取契约均正常');
      } else if (result.connectivity_ok) {
        message.warning('AI 服务可连接，但返回契约需要检查');
      } else {
        message.error(result.probe?.message || 'AI 连接测试失败');
      }
    } catch (error: any) {
      const payload = error?.data || error?.info || error?.response?.data;
      setAiTestResult({
        success: false,
        ok: false,
        message: pickSettingsError(
          payload,
          error?.message || 'AI 连接测试失败',
        ),
        probe: payload?.probe,
      });
      message.error(
        pickSettingsError(payload, error?.message || 'AI 连接测试失败'),
      );
    } finally {
      setAiTestLoading(false);
    }
  };

  const updateKeyRow = (localId: string, patch: Partial<KeyRow>) => {
    setKeyRows((rows) =>
      rows.map((r) => (r._localId === localId ? { ...r, ...patch } : r)),
    );
    setDirty(true);
  };

  const reloadSettings = async () => {
    try {
      const result = await settingsQuery.refetch();
      if (result.error) throw result.error;
      setDirty(false);
      message.success('已重新加载服务器设置');
    } catch (error: any) {
      message.error(error?.message || '重新加载失败');
    }
  };

  const onReload = () => {
    if (!dirty) {
      void reloadSettings();
      return;
    }
    modal.confirm({
      title: '放弃未保存的更改？',
      content: '重新加载会用服务器设置覆盖当前表单，此操作无法撤销。',
      okText: '放弃并重新加载',
      okButtonProps: { danger: true },
      cancelText: '继续编辑',
      onOk: reloadSettings,
    });
  };

  const sMeta = settingsQuery.data?.settings || {};
  const aiProbe = aiTestResult?.probe || {};
  const aiTestAlertType: 'success' | 'warning' | 'error' =
    aiTestResult?.ok && aiTestResult?.contract_ok
      ? 'success'
      : aiTestResult?.connectivity_ok
        ? 'warning'
        : 'error';
  const aiTestAlertMessage =
    aiTestAlertType === 'success'
      ? '连接与返回契约均正常'
      : aiTestAlertType === 'warning'
        ? '服务可连接，但返回契约需要检查'
        : aiProbe.message || aiTestResult?.message || '连接测试失败';
  const resolvedAiEndpoint = normalizeVerificationAiEndpoint(aiBaseUrl);

  return (
    <PageContainer
      title={intl.formatMessage({
        id: 'outlook.settings.title',
        defaultMessage: '系统设置',
      })}
      subTitle={intl.formatMessage({
        id: 'outlook.settings.subtitle',
        defaultMessage: '配置访问密钥、白名单与部署选项',
      })}
      extra={
        <Space>
          <Typography.Text type={dirty ? 'warning' : 'secondary'}>
            {dirty ? '有未保存更改' : '所有更改已保存'}
          </Typography.Text>
          <Button
            icon={<ReloadOutlined />}
            loading={settingsQuery.isFetching}
            onClick={onReload}
          >
            重新加载
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={saving}
            disabled={!dirty}
            onClick={() => void onSave()}
          >
            保存
          </Button>
        </Space>
      }
    >
      <Form
        form={form}
        layout="vertical"
        disabled={settingsQuery.isLoading}
        onValuesChange={() => setDirty(true)}
      >
        {dirty ? (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
            message="当前页面有未保存更改"
            description="切换标签会保留当前输入；离开页面、刷新或重新加载前会提示确认。"
          />
        ) : null}
        <Tabs
          items={[
            {
              key: 'refresh',
              label: 'Token 刷新',
              children: (
                <ProCard variant="outlined">
                  <Form.Item
                    name="enable_scheduled_refresh"
                    label="启用定时刷新"
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                  <Form.Item
                    name="use_cron_schedule"
                    label="使用 Cron 表达式"
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                  <Form.Item
                    noStyle
                    shouldUpdate={(previous, current) =>
                      previous.use_cron_schedule !== current.use_cron_schedule
                    }
                  >
                    {({ getFieldValue }) =>
                      getFieldValue('use_cron_schedule') ? (
                        <Form.Item name="refresh_cron" label="Cron">
                          <Input
                            addonAfter={
                              <Button
                                type="link"
                                size="small"
                                onClick={async () => {
                                  const cron =
                                    form.getFieldValue('refresh_cron');
                                  await runTest(
                                    () => validateCron(String(cron || '')),
                                    'Cron 有效',
                                    'Cron 无效',
                                  );
                                }}
                              >
                                校验
                              </Button>
                            }
                          />
                        </Form.Item>
                      ) : (
                        <Form.Item
                          name="refresh_interval_days"
                          label="刷新间隔（天）"
                        >
                          <InputNumber
                            min={1}
                            max={365}
                            style={{ width: '100%' }}
                          />
                        </Form.Item>
                      )
                    }
                  </Form.Item>
                  <Form.Item
                    name="refresh_delay_seconds"
                    label="账号间延迟（秒）"
                  >
                    <InputNumber min={0} max={3600} style={{ width: '100%' }} />
                  </Form.Item>
                </ProCard>
              ),
            },
            {
              key: 'polling',
              label: '轮询',
              children: (
                <ProCard variant="outlined">
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message="轮询参数使用统一持久化设置"
                    description="本页与邮箱页使用同一组后端设置。邮箱页开始监听前会先保存改动，页面刷新后不会丢失。"
                  />
                  <Form.Item
                    name="enable_auto_polling"
                    label="自动轮询（后端配置）"
                    valuePropName="checked"
                    extra="持久化设置；SPA 侧在邮箱页手动启动监听"
                  >
                    <Switch />
                  </Form.Item>
                  <Form.Item
                    name="polling_interval"
                    label="间隔（秒）"
                    rules={[
                      {
                        type: 'number',
                        min: POLLING_INTERVAL_MIN,
                        max: POLLING_INTERVAL_MAX,
                        message: `请输入 ${POLLING_INTERVAL_MIN}-${POLLING_INTERVAL_MAX} 秒`,
                      },
                    ]}
                  >
                    <InputNumber
                      min={POLLING_INTERVAL_MIN}
                      max={POLLING_INTERVAL_MAX}
                      style={{ width: '100%' }}
                    />
                  </Form.Item>
                  <Form.Item
                    name="polling_count"
                    label="最大次数（0 = 不限）"
                    rules={[
                      {
                        type: 'number',
                        min: POLLING_COUNT_MIN,
                        max: POLLING_COUNT_MAX,
                        message: `请输入 ${POLLING_COUNT_MIN}-${POLLING_COUNT_MAX} 次`,
                      },
                    ]}
                  >
                    <InputNumber
                      min={POLLING_COUNT_MIN}
                      max={POLLING_COUNT_MAX}
                      style={{ width: '100%' }}
                    />
                  </Form.Item>
                </ProCard>
              ),
            },
            {
              key: 'notify',
              label: '通知',
              children: (
                <ProCard variant="outlined">
                  <Typography.Title level={5}>邮件</Typography.Title>
                  <Form.Item
                    name="email_notification_enabled"
                    label="启用邮件通知"
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                  <Form.Item name="email_notification_recipient" label="收件人">
                    <Input />
                  </Form.Item>
                  <Button
                    style={{ marginBottom: 16 }}
                    onClick={() =>
                      void runTest(testEmailNotification, '邮件测试成功')
                    }
                  >
                    测试邮件
                  </Button>

                  <Typography.Title level={5}>Webhook</Typography.Title>
                  <Form.Item
                    name="webhook_notification_enabled"
                    label="启用 Webhook"
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                  <Form.Item
                    name="webhook_notification_url"
                    label="Webhook URL"
                  >
                    <Input />
                  </Form.Item>
                  <Form.Item
                    name="webhook_notification_token"
                    label="Webhook Token"
                    extra="显示脱敏值；改写后保存才会更新，留空不改"
                  >
                    <Input.Password
                      visibilityToggle
                      placeholder="脱敏展示 / 输入新 Token"
                    />
                  </Form.Item>
                  <Button
                    style={{ marginBottom: 16 }}
                    onClick={() =>
                      void runTest(() => testWebhook({}), 'Webhook 测试成功')
                    }
                  >
                    测试 Webhook
                  </Button>

                  <Typography.Title level={5}>Telegram</Typography.Title>
                  <Form.Item
                    name="telegram_bot_token"
                    label="Bot Token"
                    extra="后端返回脱敏值（****后四位）；仅在输入新值时更新"
                  >
                    <Input.Password visibilityToggle placeholder="****xxxx" />
                  </Form.Item>
                  <Form.Item name="telegram_chat_id" label="Chat ID">
                    <Input />
                  </Form.Item>
                  <Form.Item
                    name="telegram_poll_interval"
                    label="轮询间隔（秒）"
                  >
                    <InputNumber
                      min={10}
                      max={86400}
                      style={{ width: '100%' }}
                    />
                  </Form.Item>
                  <Form.Item name="telegram_proxy_url" label="代理 URL">
                    <Input />
                  </Form.Item>
                  <Button
                    onClick={() =>
                      void runTest(testTelegram, 'Telegram 测试成功')
                    }
                  >
                    测试 Telegram
                  </Button>
                </ProCard>
              ),
            },
            {
              key: 'ai',
              label: '验证码 AI',
              children: (
                <ProCard variant="outlined">
                  <Form.Item
                    name="verification_ai_enabled"
                    label="启用 AI 增强"
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                  <Form.Item name="verification_ai_provider" label="Provider">
                    <Select
                      onChange={onAiProviderChange}
                      options={[
                        { value: 'openai', label: 'OpenAI' },
                        {
                          value: 'openai_compatible',
                          label: 'OpenAI Compatible',
                        },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item
                    name="verification_ai_base_url"
                    label="Base URL"
                    rules={[
                      { required: aiEnabled, message: '请填写 Base URL' },
                      {
                        type: 'url',
                        message: '请输入完整的 http:// 或 https:// 地址',
                      },
                    ]}
                    extra={
                      aiProvider === 'openai' ? (
                        'OpenAI 固定使用 https://api.openai.com/v1；系统调用 /chat/completions。'
                      ) : (
                        <Space direction="vertical" size={0}>
                          <Typography.Text type="secondary">
                            填写 API 根路径（建议包含 /v1）或完整
                            /chat/completions；系统只在末尾缺失时补充
                            /chat/completions。
                          </Typography.Text>
                          {resolvedAiEndpoint ? (
                            <Typography.Text type="secondary">
                              实际请求地址：
                              <Typography.Text code>
                                {resolvedAiEndpoint}
                              </Typography.Text>
                            </Typography.Text>
                          ) : null}
                        </Space>
                      )
                    }
                  >
                    <Input
                      disabled={aiProvider === 'openai'}
                      placeholder="https://api.example.com/v1"
                    />
                  </Form.Item>
                  <Form.Item
                    name="verification_ai_model"
                    label="模型"
                    rules={[
                      { required: aiEnabled, message: '请选择或填写模型 ID' },
                    ]}
                  >
                    <AutoComplete
                      options={VERIFICATION_AI_MODEL_OPTIONS}
                      placeholder="选择常用模型或输入兼容服务的模型 ID"
                      filterOption={(input, option) =>
                        String(option?.value || '')
                          .toLowerCase()
                          .includes(input.toLowerCase())
                      }
                    />
                  </Form.Item>
                  <Form.Item
                    name="verification_ai_api_key"
                    label="API Key"
                    rules={[{ required: aiEnabled, message: '请填写 API Key' }]}
                    extra={
                      sMeta.verification_ai_api_key_set
                        ? `已设置：${sMeta.verification_ai_api_key_masked || ''}`
                        : '未设置'
                    }
                  >
                    <Input.Password
                      visibilityToggle
                      placeholder="输入新 Key 以更新"
                    />
                  </Form.Item>
                  <Space
                    direction="vertical"
                    size="middle"
                    style={{ width: '100%' }}
                  >
                    <Button
                      icon={<ApiOutlined />}
                      loading={aiTestLoading}
                      onClick={() => void runVerificationAiTest()}
                    >
                      测试当前配置
                    </Button>
                    {aiTestResult ? (
                      <Alert
                        showIcon
                        type={aiTestAlertType}
                        message={aiTestAlertMessage}
                        description={
                          <Space direction="vertical" size={4}>
                            <Space wrap size={[8, 4]}>
                              {aiProbe.error_category ? (
                                <Tag color="red">
                                  {AI_ERROR_CATEGORY_LABELS[
                                    aiProbe.error_category
                                  ] || aiProbe.error_category}
                                </Tag>
                              ) : null}
                              {aiProbe.model ? (
                                <Tag>模型 {aiProbe.model}</Tag>
                              ) : null}
                              {typeof aiProbe.latency_ms === 'number' ? (
                                <Tag>延迟 {aiProbe.latency_ms} ms</Tag>
                              ) : null}
                              {typeof aiProbe.http_status === 'number' ? (
                                <Tag>HTTP {aiProbe.http_status}</Tag>
                              ) : null}
                            </Space>
                            {aiProbe.endpoint ? (
                              <Typography.Text type="secondary">
                                请求地址：
                                <Typography.Text code>
                                  {aiProbe.endpoint}
                                </Typography.Text>
                              </Typography.Text>
                            ) : null}
                            {aiProbe.hint ? (
                              <Typography.Text>{aiProbe.hint}</Typography.Text>
                            ) : null}
                          </Space>
                        }
                      />
                    ) : null}
                  </Space>
                </ProCard>
              ),
            },
            {
              key: 'external',
              label: '外部 API / 池',
              children: (
                <ProCard variant="outlined">
                  <Form.Item
                    name="external_api_public_mode"
                    label="公网模式"
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                  <Form.Item
                    name="external_api_rate_limit_per_minute"
                    label="每分钟限流"
                  >
                    <InputNumber
                      min={1}
                      max={10000}
                      style={{ width: '100%' }}
                    />
                  </Form.Item>
                  <Form.Item
                    name="external_api_key"
                    label="对外 API Key（单 Key 兼容）"
                    extra={
                      sMeta.external_api_key_set
                        ? `已设置：${sMeta.external_api_key_masked || ''}`
                        : '未设置'
                    }
                  >
                    <Input.Password
                      visibilityToggle
                      placeholder="输入新 Key 以更新"
                    />
                  </Form.Item>

                  <Typography.Title level={5}>
                    多 Key（external_api_keys）
                  </Typography.Title>
                  <Typography.Paragraph
                    type="secondary"
                    style={{ marginTop: 0 }}
                  >
                    保留脱敏 api_key 表示不修改；新建必须填明文
                    Key；保存时若未改动则不提交本字段。
                  </Typography.Paragraph>
                  <Table<KeyRow>
                    size="small"
                    rowKey="_localId"
                    pagination={false}
                    style={{ marginBottom: 12 }}
                    dataSource={keyRows}
                    columns={[
                      {
                        title: '名称',
                        dataIndex: 'name',
                        width: 140,
                        render: (_, row) => (
                          <Input
                            size="small"
                            value={row.name}
                            onChange={(e) =>
                              updateKeyRow(row._localId, {
                                name: e.target.value,
                              })
                            }
                          />
                        ),
                      },
                      {
                        title: 'API Key',
                        dataIndex: 'api_key',
                        render: (_, row) => (
                          <Input.Password
                            size="small"
                            value={row.api_key}
                            placeholder="脱敏保留=不改"
                            onChange={(e) =>
                              updateKeyRow(row._localId, {
                                api_key: e.target.value,
                              })
                            }
                          />
                        ),
                      },
                      {
                        title: '邮箱范围',
                        dataIndex: 'allowed_emails',
                        width: 180,
                        render: (_, row) => (
                          <Input.TextArea
                            size="small"
                            rows={2}
                            value={
                              Array.isArray(row.allowed_emails)
                                ? row.allowed_emails.join('\n')
                                : String(row.allowed_emails || '')
                            }
                            placeholder="每行一个邮箱，空=不限"
                            onChange={(e) =>
                              updateKeyRow(row._localId, {
                                allowed_emails: e.target.value
                                  .split(/[\n,]/)
                                  .map((x) => x.trim())
                                  .filter(Boolean),
                              })
                            }
                          />
                        ),
                      },
                      {
                        title: '池权限',
                        dataIndex: 'pool_access',
                        width: 80,
                        render: (_, row) => (
                          <Switch
                            size="small"
                            checked={!!row.pool_access}
                            onChange={(v) =>
                              updateKeyRow(row._localId, { pool_access: v })
                            }
                          />
                        ),
                      },
                      {
                        title: '启用',
                        dataIndex: 'enabled',
                        width: 70,
                        render: (_, row) => (
                          <Switch
                            size="small"
                            checked={row.enabled !== false}
                            onChange={(v) =>
                              updateKeyRow(row._localId, { enabled: v })
                            }
                          />
                        ),
                      },
                      {
                        title: '',
                        width: 48,
                        render: (_, row) => (
                          <Button
                            type="text"
                            danger
                            size="small"
                            icon={<DeleteOutlined />}
                            onClick={() => {
                              setKeyRows((rows) =>
                                rows.filter((r) => r._localId !== row._localId),
                              );
                              setDirty(true);
                            }}
                          />
                        ),
                      },
                    ]}
                  />
                  <Button
                    type="dashed"
                    icon={<PlusOutlined />}
                    style={{ marginBottom: 16 }}
                    onClick={() => {
                      setKeyRows((rows) => [
                        ...rows,
                        {
                          _localId: newLocalId(),
                          name: '',
                          api_key: '',
                          enabled: true,
                          pool_access: false,
                          allowed_emails: [],
                        },
                      ]);
                      setDirty(true);
                    }}
                  >
                    添加 Key
                  </Button>
                  <Button
                    danger
                    type="link"
                    onClick={() => {
                      setKeyRows([]);
                      setDirty(true);
                    }}
                    disabled={!keyRows.length}
                  >
                    清空全部多 Key
                  </Button>

                  <Form.Item
                    name="external_api_ip_whitelist_text"
                    label="IP 白名单"
                    extra="每行一个 IP / CIDR；空表示不限制"
                  >
                    <Input.TextArea
                      rows={4}
                      placeholder="127.0.0.1&#10;10.0.0.0/8"
                    />
                  </Form.Item>

                  <Typography.Title level={5}>危险端点开关</Typography.Title>
                  <Form.Item
                    name="external_api_disable_raw_content"
                    label="禁用 raw content"
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                  <Form.Item
                    name="external_api_disable_wait_message"
                    label="禁用 wait message"
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                  <Form.Item
                    name="external_api_disable_pool_claim_random"
                    label="禁用 pool claim random"
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                  <Form.Item
                    name="external_api_disable_pool_claim_release"
                    label="禁用 pool claim release"
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                  <Form.Item
                    name="external_api_disable_pool_claim_complete"
                    label="禁用 pool claim complete"
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                  <Form.Item
                    name="external_api_disable_pool_stats"
                    label="禁用 pool stats"
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>

                  <Form.Item
                    name="pool_external_enabled"
                    label="启用外部邮箱池"
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                  <Form.Item name="temp_mail_provider" label="临时邮箱服务商">
                    <Input placeholder="如 gptmail / custom" />
                  </Form.Item>
                  <Form.Item
                    name="temp_mail_api_base_url"
                    label="临时邮箱接口地址"
                  >
                    <Input placeholder="https://..." />
                  </Form.Item>
                  <Form.Item
                    name="temp_mail_api_key"
                    label="临时邮箱接口密钥"
                    extra={
                      sMeta.temp_mail_api_key_set
                        ? `已设置：${sMeta.temp_mail_api_key_masked || ''}`
                        : '未设置'
                    }
                  >
                    <Input.Password
                      visibilityToggle
                      placeholder="输入新密钥以更新"
                    />
                  </Form.Item>
                  <Form.Item
                    name="cf_worker_base_url"
                    label="Cloudflare Worker 地址"
                  >
                    <Input placeholder="https://..." />
                  </Form.Item>
                  <Form.Item
                    name="cf_worker_admin_key"
                    label="Cloudflare Worker 管理密钥"
                    extra={
                      sMeta.cf_worker_admin_key_set
                        ? `已设置：${sMeta.cf_worker_admin_key_masked || ''}`
                        : '未设置'
                    }
                  >
                    <Input.Password
                      visibilityToggle
                      placeholder="输入新管理密钥以更新"
                    />
                  </Form.Item>
                  <Space>
                    <Button
                      icon={<SyncOutlined />}
                      loading={cfSyncLoading}
                      onClick={() => void onSyncCfDomains()}
                    >
                      同步 Cloudflare Worker 域名
                    </Button>
                    {Array.isArray(sMeta.cf_worker_domains) &&
                    sMeta.cf_worker_domains.length ? (
                      <Typography.Text type="secondary">
                        当前域：{sMeta.cf_worker_domains.join(', ')}
                      </Typography.Text>
                    ) : null}
                  </Space>
                </ProCard>
              ),
            },
            {
              key: 'security',
              label: '安全',
              children: (
                <ProCard variant="outlined">
                  <Form.Item
                    name="login_password"
                    label="修改登录密码"
                    extra={
                      sMeta.allow_login_password_change === false
                        ? '当前站点已禁用密码修改（ALLOW_LOGIN_PASSWORD_CHANGE）'
                        : sMeta.login_password_set
                          ? '已设置登录密码；留空表示不修改'
                          : '尚未设置登录密码'
                    }
                  >
                    <Input.Password
                      visibilityToggle
                      disabled={sMeta.allow_login_password_change === false}
                      placeholder="至少 8 位；留空不修改"
                    />
                  </Form.Item>
                </ProCard>
              ),
            },
            {
              key: 'update',
              label: '更新 / 部署',
              children: (
                <ProCard variant="outlined">
                  <Form.Item name="update_method" label="更新方式">
                    <Select
                      options={[
                        { label: 'watchtower', value: 'watchtower' },
                        { label: 'docker_api', value: 'docker_api' },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item name="watchtower_url" label="Watchtower URL">
                    <Input />
                  </Form.Item>
                  <Form.Item
                    name="watchtower_token"
                    label="Watchtower Token"
                    extra="显示脱敏值；改写后保存才会更新"
                  >
                    <Input.Password visibilityToggle placeholder="****xxxx" />
                  </Form.Item>
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Button
                      loading={deploymentLoading}
                      onClick={() => void loadDeployment()}
                    >
                      刷新部署信息
                    </Button>
                    <Button
                      type="primary"
                      danger
                      loading={updateLoading}
                      onClick={onTriggerUpdate}
                    >
                      触发更新
                    </Button>
                  </Space>
                  {deployment ? (
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <div>
                        <Typography.Text type="secondary">
                          镜像：
                        </Typography.Text>{' '}
                        {String(deployment.image || 'unknown')}
                      </div>
                      <div>
                        <Typography.Text type="secondary">
                          可自动更新：
                        </Typography.Text>{' '}
                        {deployment.can_auto_update ? (
                          <Tag color="success">是</Tag>
                        ) : (
                          <Tag>否</Tag>
                        )}
                        <Typography.Text
                          type="secondary"
                          style={{ marginLeft: 12 }}
                        >
                          推荐：
                        </Typography.Text>{' '}
                        {String(deployment.recommended_method || '--')}
                      </div>
                      <div>
                        <Typography.Text type="secondary">
                          Watchtower：
                        </Typography.Text>{' '}
                        {deployment.watchtower_reachable == null
                          ? '--'
                          : deployment.watchtower_reachable
                            ? '可达'
                            : '不可达'}
                        <Typography.Text
                          type="secondary"
                          style={{ marginLeft: 12 }}
                        >
                          Docker API：
                        </Typography.Text>{' '}
                        {deployment.docker_api_available ? '可用' : '不可用'}
                      </div>
                      {Array.isArray(deployment.warnings) &&
                      deployment.warnings.length ? (
                        <Alert
                          type="warning"
                          showIcon
                          message="部署警告"
                          description={
                            <ul style={{ margin: 0, paddingLeft: 18 }}>
                              {deployment.warnings.map((w: any) => (
                                <li key={String(w)}>{String(w)}</li>
                              ))}
                            </ul>
                          }
                        />
                      ) : null}
                    </Space>
                  ) : (
                    <Typography.Text type="secondary">
                      点击「刷新部署信息」获取当前部署状态
                    </Typography.Text>
                  )}
                </ProCard>
              ),
            },
          ]}
        />
        <div
          style={{
            position: 'sticky',
            bottom: 16,
            zIndex: 20,
            marginTop: 16,
            padding: '12px 16px',
            border: `1px solid ${token.colorBorderSecondary}`,
            borderRadius: 8,
            background: token.colorBgContainer,
            boxShadow: token.boxShadowSecondary,
          }}
        >
          <Space
            wrap
            style={{ width: '100%', justifyContent: 'space-between' }}
          >
            <Typography.Text type={dirty ? 'warning' : 'secondary'}>
              {dirty ? '有未保存更改' : '当前设置已保存'}
            </Typography.Text>
            <Space>
              <Button
                icon={<UndoOutlined />}
                disabled={!dirty || saving}
                onClick={onReload}
              >
                放弃更改
              </Button>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                loading={saving}
                disabled={!dirty}
                onClick={() => void onSave()}
              >
                保存更改
              </Button>
            </Space>
          </Space>
        </div>
      </Form>
    </PageContainer>
  );
};

export default SettingsPage;
