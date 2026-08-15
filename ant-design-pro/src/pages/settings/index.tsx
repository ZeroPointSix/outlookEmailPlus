import {
  CopyOutlined,
  KeyOutlined,
  MoreOutlined,
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
  Collapse,
  Descriptions,
  Divider,
  Dropdown,
  Form,
  Input,
  InputNumber,
  Modal,
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
  createExternalApiKey,
  type CreateExternalApiKeyResponse,
  type ExternalApiKeyItem,
  fetchDeploymentInfo,
  fetchSettings,
  fetchVerificationAiModels,
  type VerificationAiTestResponse,
  type WebhookTestResponse,
  normalizePollingSettings,
  POLLING_COUNT_MAX,
  POLLING_COUNT_MIN,
  POLLING_INTERVAL_MAX,
  POLLING_INTERVAL_MIN,
  pickSettingsError,
  syncCfWorkerDomains,
  testEmailNotification,
  testTelegram,
  testTelegramProxy,
  type TelegramProxyTestResponse,
  testVerificationAi,
  testWebhook,
  triggerSystemUpdate,
  updateSettings,
  validateCron,
} from '@/services/outlook/settings';
import {
  API_KEY_EXPIRY_OPTIONS,
  getApiKeyExpiryLabel,
  getApiKeyStatus,
  getInvalidEmailScope,
  parseEmailScope,
} from '@/utils/apiKey';

type KeyRow = ExternalApiKeyItem & { _localId: string };

const newLocalId = () =>
  `local_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

const describeAiError = (error?: string) =>
  ({
    config_incomplete: '配置不完整，请检查 Base URL、API Key 和模型。',
    request_failed: '网络、DNS 或超时失败，请确认服务地址可从服务器访问。',
    http_error: '服务返回错误，请检查 API Key、模型名称、额度和 URL。',
    invalid_response_format: '服务可访问，但响应格式不是兼容的 OpenAI 格式。',
    invalid_ai_output: '服务可访问，但验证码解析结果不符合固定契约。',
  })[error || ''] || '连接失败，请根据下方状态与端点信息排查。';

const isAiProbeSuccessful = (result?: VerificationAiTestResponse | null) =>
  Boolean(result?.ok && result?.contract_ok !== false);

const buildAiTestFailureResult = (error: any): VerificationAiTestResponse => {
  const payload =
    error?.data ||
    error?.info ||
    error?.response?.data ||
    {};
  const serverError = payload?.error;
  const message =
    (typeof serverError === 'object' && serverError?.message) ||
    (typeof serverError === 'string' && serverError) ||
    payload?.message ||
    error?.message ||
    'AI 连通性测试失败';
  const model = String(payload?.model || '').trim();
  const endpoint = String(payload?.endpoint || '').trim();

  return {
    success: false,
    ok: false,
    connectivity_ok: false,
    contract_ok: false,
    probe: {
      error: 'request_failed',
      message,
      model,
      endpoint,
      http_status: Number(payload?.status || error?.status || 0) || undefined,
    },
  };
};

const SettingsPage: React.FC = () => {
  const { message, modal } = App.useApp();
  const intl = useIntl();
  const queryClient = useQueryClient();
  const { token } = theme.useToken();
  const [form] = Form.useForm();
  const [keyForm] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [creatingKey, setCreatingKey] = useState(false);
  const [createKeyOpen, setCreateKeyOpen] = useState(false);
  const [createdKey, setCreatedKey] =
    useState<CreateExternalApiKeyResponse | null>(null);
  const [dirty, setDirty] = useState(false);
  const [keyRows, setKeyRows] = useState<KeyRow[]>([]);
  const [keyDetail, setKeyDetail] = useState<KeyRow | null>(null);
  const [originalKeysCanonical, setOriginalKeysCanonical] = useState('[]');
  const [deployment, setDeployment] = useState<Record<string, any> | null>(
    null,
  );
  const [deploymentLoading, setDeploymentLoading] = useState(false);
  const [updateLoading, setUpdateLoading] = useState(false);
  const [cfSyncLoading, setCfSyncLoading] = useState(false);
  const [aiModels, setAiModels] = useState<string[]>([]);
  const [aiModelsLoading, setAiModelsLoading] = useState(false);
  const [aiTestLoading, setAiTestLoading] = useState(false);
  const [aiTestResult, setAiTestResult] =
    useState<VerificationAiTestResponse | null>(null);
  const [webhookTestLoading, setWebhookTestLoading] = useState(false);
  const [webhookTestResult, setWebhookTestResult] =
    useState<WebhookTestResponse | null>(null);
  const [telegramProxyTestLoading, setTelegramProxyTestLoading] =
    useState(false);
  const [telegramProxyTestResult, setTelegramProxyTestResult] =
    useState<TelegramProxyTestResponse | null>(null);

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
          expires_at: k.expires_at || '',
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
      expires_at: k.expires_at || '',
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
        throw new Error(`第 ${i + 1} 个 Key 的名称不能为空`);
      }
      if (item.id == null && !item.api_key) {
        throw new Error(`请通过「创建 Key」流程新增「${item.name}」`);
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

      // 敏感字段：仍等于脱敏占位时不提交；Webhook Token 留空表示清空
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
        if (key === 'webhook_notification_token' && !raw) {
          payload[key] = '';
        } else if (!raw || (mask && raw === mask)) {
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
        message.error(e?.message || 'API Key 配置无效');
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

  const getVerificationAiPayload = () => ({
    enabled: form.getFieldValue('verification_ai_enabled'),
    base_url: String(
      form.getFieldValue('verification_ai_base_url') || '',
    ).trim(),
    model: String(form.getFieldValue('verification_ai_model') || '').trim(),
    api_key: String(
      form.getFieldValue('verification_ai_api_key') || '',
    ).trim(),
  });

  const loadVerificationAiModels = async () => {
    const payload = getVerificationAiPayload();
    if (!payload.base_url || !payload.api_key) {
      message.error('请先填写 Base URL 和 API Key');
      return;
    }
    setAiModelsLoading(true);
    try {
      const res = await fetchVerificationAiModels(payload);
      if (!res?.ok) {
        message.error(res?.message || '模型列表加载失败');
        return;
      }
      setAiModels(res.models || []);
      message.success(res.message || '模型列表已加载');
    } catch (error: any) {
      message.error(error?.message || '模型列表加载失败');
    } finally {
      setAiModelsLoading(false);
    }
  };

  const testVerificationAiConnection = async () => {
    const payload = getVerificationAiPayload();
    if (!payload.base_url || !payload.api_key || !payload.model) {
      message.error('请先填写 Base URL、API Key 和模型');
      return;
    }
    setAiTestLoading(true);
    setAiTestResult(null);
    try {
      const res = await testVerificationAi(payload);
      setAiTestResult(res);
      if (isAiProbeSuccessful(res)) {
        message.success('AI 连通性正常');
      } else if (res?.connectivity_ok) {
        message.warning(
          res?.probe?.message || describeAiError(res?.probe?.error),
        );
      } else {
        message.error(res?.probe?.message || describeAiError(res?.probe?.error));
      }
    } catch (error: any) {
      const failure = buildAiTestFailureResult(error);
      setAiTestResult(failure);
      message.error(
        failure.probe?.message || describeAiError(failure.probe?.error),
      );
    } finally {
      setAiTestLoading(false);
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

  const testSavedWebhook = async () => {
    if (dirty) {
      message.warning('请先保存当前 Webhook 配置，再测试已保存配置');
      return;
    }
    if (!form.getFieldValue('webhook_notification_enabled')) {
      message.warning('请先启用 Webhook 并保存配置，再进行测试');
      return;
    }
    setWebhookTestLoading(true);
    setWebhookTestResult(null);
    try {
      const result = await testWebhook({});
      setWebhookTestResult(result);
      if (result?.success === false) {
        message.error(pickSettingsError(result, 'Webhook 测试失败'));
      } else {
        message.success(result?.message || 'Webhook 测试成功');
      }
    } catch (error: any) {
      const payload =
        error?.data ||
        error?.info ||
        error?.response?.data || {
          error: error?.message || 'Webhook 测试失败',
        };
      const diagnostics = {
        status_code: payload?.status_code,
        duration_ms: payload?.duration_ms,
        attempts: payload?.attempts,
      };
      const normalized: WebhookTestResponse = {
        success: false,
        ...diagnostics,
        error:
          payload?.error && typeof payload.error === 'object'
            ? { ...payload.error, ...diagnostics }
            : {
                message: payload?.error || payload?.message || 'Webhook 测试失败',
                ...diagnostics,
              },
      };
      setWebhookTestResult(normalized);
      message.error(pickSettingsError(normalized, 'Webhook 测试失败'));
    } finally {
      setWebhookTestLoading(false);
    }
  };

  const testTelegramProxyUrl = async () => {
    const proxyUrl = String(
      form.getFieldValue('telegram_proxy_url') || '',
    ).trim();
    if (dirty) {
      message.warning('请先保存当前 Telegram 配置，再测试代理连通性');
      return;
    }
    setTelegramProxyTestLoading(true);
    setTelegramProxyTestResult(null);
    try {
      const result = await testTelegramProxy(proxyUrl);
      setTelegramProxyTestResult(result);
      if (result?.success === false) {
        message.error(pickSettingsError(result, '代理连通性测试失败'));
      } else if (result?.ok === false) {
        message.warning(result?.message || '代理可达但 Telegram 连接异常');
      } else {
        message.success(result?.message || '代理连通性测试成功');
      }
    } catch (error: any) {
      const payload =
        error?.data ||
        error?.info ||
        error?.response?.data || {
          success: false,
          message: error?.message || '代理连通性测试失败',
          error,
        };
      setTelegramProxyTestResult(payload);
      message.error(pickSettingsError(payload, '代理连通性测试失败'));
    } finally {
      setTelegramProxyTestLoading(false);
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

  const updateKeyRow = (localId: string, patch: Partial<KeyRow>) => {
    setKeyRows((rows) =>
      rows.map((r) => (r._localId === localId ? { ...r, ...patch } : r)),
    );
    setDirty(true);
  };

  const toggleKeyStatus = (row: KeyRow) => {
    const status = getApiKeyStatus(row);
    if (status === 'expired') {
      message.warning('已过期的 Key 不能直接启用，请重新创建');
      return;
    }
    const enabled = row.enabled === false;
    updateKeyRow(row._localId, { enabled });
    setKeyDetail((current) =>
      current?._localId === row._localId ? { ...current, enabled } : current,
    );
  };

  const deleteKeyRow = (row: KeyRow) => {
    modal.confirm({
      title: '删除「' + (row.name || '未命名 Key') + '」？',
      content: '删除后该 Key 将无法继续调用，保存设置后立即生效。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => {
        setKeyRows((rows) =>
          rows.filter((item) => item._localId !== row._localId),
        );
        setKeyDetail((current) =>
          current?._localId === row._localId ? null : current,
        );
        setDirty(true);
      },
    });
  };

  const openCreateKey = () => {
    if (dirty) {
      message.warning('请先保存或放弃当前更改，再创建 API Key');
      return;
    }
    keyForm.resetFields();
    keyForm.setFieldsValue({
      expires_in_days: 90,
      allowed_emails_text: '',
      pool_access: false,
      enabled: true,
    });
    setCreateKeyOpen(true);
  };

  const onCreateKey = async () => {
    const values = await keyForm.validateFields().catch(() => null);
    if (!values) return;

    setCreatingKey(true);
    try {
      const result = await createExternalApiKey({
        name: String(values.name || '').trim(),
        expires_in_days:
          Number(values.expires_in_days) > 0
            ? Number(values.expires_in_days)
            : null,
        allowed_emails: parseEmailScope(values.allowed_emails_text),
        pool_access: !!values.pool_access,
        enabled: values.enabled !== false,
      });
      if (result?.success === false || !result?.api_key || !result?.item) {
        message.error(pickSettingsError(result, '创建 API Key 失败'));
        return;
      }
      setCreateKeyOpen(false);
      setCreatedKey(result);
      await settingsQuery.refetch();
    } catch (error: any) {
      message.error(
        pickSettingsError(
          error?.data || error?.info || error?.response?.data,
          error?.message || '创建 API Key 失败',
        ),
      );
    } finally {
      setCreatingKey(false);
    }
  };

  const copyCreatedKey = async () => {
    if (!createdKey?.api_key) return;
    try {
      await navigator.clipboard.writeText(createdKey.api_key);
      message.success('API Key 已复制');
    } catch {
      message.error('复制失败，请手动选择并复制');
    }
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
  const aiTestSuccessful = isAiProbeSuccessful(aiTestResult);

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
                    extra="持久化设置；开启后邮箱页选中账号自动开始监听，复制邮箱地址也会触发监听"
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
                    extra="显示脱敏值；改写后保存才会更新，留空会清空 Token"
                  >
                    <Input.Password
                      visibilityToggle
                      placeholder="脱敏展示 / 输入新 Token"
                    />
                  </Form.Item>
                  <Button
                    style={{ marginBottom: 16 }}
                    loading={webhookTestLoading}
                    onClick={() => void testSavedWebhook()}
                  >
                    测试已保存配置
                  </Button>
                  <Typography.Paragraph
                    type="secondary"
                    style={{ margin: '-8px 0 16px' }}
                  >
                    测试只会调用服务器已保存的 URL 和 Token；如修改过上方字段，请先点击页面顶部或底部的「保存」。
                  </Typography.Paragraph>
                  {webhookTestResult && (
                    <Alert
                      showIcon
                      style={{ marginBottom: 16 }}
                      type={webhookTestResult.success ? 'success' : 'error'}
                      message={
                        webhookTestResult.success
                          ? 'Webhook 测试已发送'
                          : pickSettingsError(
                              { error: webhookTestResult.error },
                              'Webhook 测试失败',
                            )
                      }
                      description={
                        webhookTestResult.success ? (
                          <Space direction="vertical" size={2}>
                            <Typography.Text>
                              目标：{webhookTestResult.url || '服务端未返回'}
                            </Typography.Text>
                            <Typography.Text>
                              上游 HTTP：
                              {webhookTestResult.status_code ?? '未返回'}
                            </Typography.Text>
                            <Typography.Text>
                              耗时：
                              {webhookTestResult.duration_ms != null
                                ? webhookTestResult.duration_ms + ' ms'
                                : '服务端未返回投递耗时'}
                            </Typography.Text>
                            <Typography.Text>
                              尝试次数：
                              {webhookTestResult.attempts ?? '服务端未返回'}
                            </Typography.Text>
                          </Space>
                        ) : (
                          <Space direction="vertical" size={2}>
                            <Typography.Text>
                              上游 HTTP：
                              {webhookTestResult.status_code ??
                                webhookTestResult.error?.status_code ??
                                '未返回'}
                            </Typography.Text>
                            <Typography.Text>
                              耗时：
                              {(webhookTestResult.duration_ms ??
                                webhookTestResult.error?.duration_ms) != null
                                ? `${webhookTestResult.duration_ms ?? webhookTestResult.error.duration_ms} ms`
                                : '未返回'}
                            </Typography.Text>
                            <Typography.Text>
                              尝试次数：
                              {webhookTestResult.attempts ??
                                webhookTestResult.error?.attempts ??
                                '未返回'}
                            </Typography.Text>
                            <Typography.Text>
                              错误码：
                              {webhookTestResult.error?.code || '未返回'}
                            </Typography.Text>
                            {webhookTestResult.error?.details && (
                              <Typography.Text type="secondary">
                                服务端细节：
                                {String(webhookTestResult.error.details)}
                              </Typography.Text>
                            )}
                          </Space>
                        )
                      }
                    />
                  )}

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
                  <Form.Item
                    name="telegram_proxy_url"
                    label="代理 URL"
                    extra="留空则直连（用已保存配置）。格式：socks5://host:port 或 http://host:port"
                  >
                    <Input placeholder="socks5://user:pass@host:port 或 http://host:port" />
                  </Form.Item>
                  <Space wrap style={{ marginBottom: telegramProxyTestResult ? 16 : 0 }}>
                    <Button
                      onClick={() =>
                        void runTest(testTelegram, 'Telegram 测试成功')
                      }
                    >
                      测试 Telegram
                    </Button>
                    <Button
                      loading={telegramProxyTestLoading}
                      onClick={() => void testTelegramProxyUrl()}
                    >
                      测试代理连通性
                    </Button>
                  </Space>
                  {telegramProxyTestResult && (
                    <Alert
                      showIcon
                      style={{ marginBottom: 16 }}
                      type={
                        telegramProxyTestResult.success &&
                        telegramProxyTestResult.ok !== false
                          ? 'success'
                          : 'error'
                      }
                      message={
                        telegramProxyTestResult.success &&
                        telegramProxyTestResult.ok !== false
                          ? '代理连通性测试完成'
                          : pickSettingsError(
                              { error: telegramProxyTestResult.error },
                              telegramProxyTestResult.message ||
                                '代理连通性测试失败',
                            )
                      }
                      description={
                        <Space direction="vertical" size={2}>
                          <Typography.Text>
                            状态：
                            {telegramProxyTestResult.ok === false
                              ? `代理可达但 Telegram 返回异常（网络不可用/被拦截）`
                              : telegramProxyTestResult.success
                                ? '代理连通成功'
                                : '代理连接失败'}
                          </Typography.Text>
                          {telegramProxyTestResult.message && (
                            <Typography.Text>
                              服务端返回：
                              {telegramProxyTestResult.message}
                            </Typography.Text>
                          )}
                          {telegramProxyTestResult.latency_ms != null && (
                            <Typography.Text>
                              耗时：
                              {telegramProxyTestResult.latency_ms} ms
                            </Typography.Text>
                          )}
                          {telegramProxyTestResult.error?.code && (
                            <Typography.Text>
                              错误码：
                              {String(telegramProxyTestResult.error.code)}
                            </Typography.Text>
                          )}
                        </Space>
                      }
                    />
                  )}
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
                  <Form.Item
                    name="verification_ai_base_url"
                    label="Base URL"
                    extra="填写兼容 API 根地址（如 https://api.openai.com/v1）；系统会自动使用 /models 和 /chat/completions。也可直接填写完整 /chat/completions 地址。"
                  >
                    <Input placeholder="https://api.openai.com/v1" />
                  </Form.Item>
                  <Form.Item name="verification_ai_model" label="模型">
                    <AutoComplete
                      options={aiModels.map((model) => ({
                        label: model,
                        value: model,
                      }))}
                      placeholder="输入模型名，或加载服务端模型列表"
                      filterOption={(inputValue, option) =>
                        String(option?.value || '')
                          .toLowerCase()
                          .includes(inputValue.toLowerCase())
                      }
                    />
                  </Form.Item>
                  <Form.Item
                    name="verification_ai_api_key"
                    label="API Key"
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
                  <Space wrap>
                    <Button
                      icon={<ReloadOutlined />}
                      loading={aiModelsLoading}
                      onClick={() => void loadVerificationAiModels()}
                    >
                      加载模型
                    </Button>
                    <Button
                      type="primary"
                      loading={aiTestLoading}
                      onClick={() => void testVerificationAiConnection()}
                    >
                      测试 AI
                    </Button>
                  </Space>
                  {aiTestResult && (
                    <Alert
                      showIcon
                      style={{ marginTop: 16 }}
                      type={aiTestSuccessful ? 'success' : 'error'}
                      message={
                        aiTestSuccessful
                          ? '连接成功'
                          : aiTestResult.probe?.message ||
                            describeAiError(aiTestResult.probe?.error)
                      }
                      description={
                        <Space direction="vertical" size={2}>
                          {!aiTestSuccessful && (
                            <Typography.Text>
                              {describeAiError(aiTestResult.probe?.error)}
                            </Typography.Text>
                          )}
                          <Typography.Text>
                            连通性：
                            {aiTestResult.connectivity_ok ? '正常' : '失败'}
                            {'；'}契约：
                            {aiTestResult.contract_ok ? '通过' : '失败'}
                          </Typography.Text>
                          <Typography.Text>
                            模型：{aiTestResult.probe?.model || '未返回'}
                          </Typography.Text>
                          <Typography.Text>
                            延迟：
                            {aiTestResult.probe?.latency_ms != null
                              ? `${aiTestResult.probe.latency_ms} ms`
                              : '未返回'}
                          </Typography.Text>
                          <Typography.Text>
                            HTTP：
                            {aiTestResult.probe?.http_status ?? '未返回'}
                          </Typography.Text>
                          <Typography.Text code>
                            {aiTestResult.probe?.endpoint || '未生成请求端点'}
                          </Typography.Text>
                        </Space>
                      }
                    />
                  )}
                </ProCard>
              ),
            },
            {
              key: 'external',
              label: '外部 API / 池',
              children: (
                <div>
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
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      gap: 16,
                      marginBottom: 16,
                    }}
                  >
                    <div>
                      <Typography.Title level={4} style={{ margin: 0 }}>
                        API Keys
                      </Typography.Title>
                      <Typography.Paragraph
                        type="secondary"
                        style={{ margin: '4px 0 0' }}
                      >
                        列表保持简洁；权限与邮箱范围只在创建时选择，后续变更请重新创建 Key。
                      </Typography.Paragraph>
                    </div>
                    <Button
                      type="primary"
                      icon={<KeyOutlined />}
                      onClick={openCreateKey}
                    >
                      创建 Key
                    </Button>
                  </div>

                  {keyRows.length ? (
                    <Table<KeyRow>
                      rowKey="_localId"
                      size="small"
                      dataSource={keyRows}
                      pagination={false}
                      style={{ marginBottom: 20 }}
                      columns={[
                        {
                          title: '名称',
                          key: 'name',
                          render: (_: unknown, row: KeyRow) => (
                            <Space size={8}>
                              <KeyOutlined />
                              <Typography.Text strong>
                                {row.name || '未命名 Key'}
                              </Typography.Text>
                            </Space>
                          ),
                        },
                        {
                          title: '状态',
                          key: 'status',
                          render: (_: unknown, row: KeyRow) => {
                            const status = getApiKeyStatus(row);
                            const statusLabel =
                              status === 'active'
                                ? '启用'
                                : status === 'expired'
                                  ? '已过期'
                                  : '停用';
                            const statusColor =
                              status === 'active'
                                ? 'success'
                                : status === 'expired'
                                  ? 'error'
                                  : 'default';
                            return <Tag color={statusColor}>{statusLabel}</Tag>;
                          },
                        },
                        {
                          title: 'Token',
                          key: 'token',
                          render: (_: unknown, row: KeyRow) => (
                            <Typography.Text code>
                              {row.api_key_masked || row.api_key || '••••••••'}
                            </Typography.Text>
                          ),
                        },
                        {
                          title: '操作',
                          key: 'actions',
                          align: 'right' as const,
                          render: (_: unknown, row: KeyRow) => {
                            const status = getApiKeyStatus(row);
                            return (
                              <Dropdown
                                trigger={['click']}
                                menu={{
                                  items: [
                                    { key: 'detail', label: '查看详情' },
                                    status === 'expired'
                                      ? {
                                          key: 'toggle',
                                          label: '已过期，需重新创建',
                                          disabled: true,
                                        }
                                      : {
                                          key: 'toggle',
                                          label:
                                            status === 'active'
                                              ? '停用 Key'
                                              : '启用 Key',
                                        },
                                    { type: 'divider' },
                                    {
                                      key: 'delete',
                                      label: '删除 Key',
                                      danger: true,
                                    },
                                  ],
                                  onClick: ({ key }) => {
                                    if (key === 'detail') {
                                      setKeyDetail(row);
                                    } else if (key === 'toggle') {
                                      toggleKeyStatus(row);
                                    } else if (key === 'delete') {
                                      deleteKeyRow(row);
                                    }
                                  },
                                }}
                              >
                                <Button
                                  type="text"
                                  icon={<MoreOutlined />}
                                  aria-label={'操作 ' + (row.name || '未命名 Key')}
                                />
                              </Dropdown>
                            );
                          },
                        },
                      ]}
                    />
                  ) : (
                    <Alert
                      type="info"
                      showIcon
                      message="尚未创建 API Key"
                      description="列表只展示名称、状态和脱敏 Token；权限与邮箱范围在创建时选择，后续变更请重新创建 Key。"
                      style={{ marginBottom: 20 }}
                    />
                  )}

                  <Form.Item
                    name="external_api_key"
                    label="旧版兼容 Key"
                    extra={
                      sMeta.external_api_key_set
                        ? `仅供旧客户端使用，当前值：${sMeta.external_api_key_masked || ''}`
                        : '仅供仍使用单 Key 配置的旧客户端；新接入请使用上方创建流程。'
                    }
                  >
                    <Input.Password
                      visibilityToggle
                      placeholder="输入新值以更新旧版兼容 Key"
                    />
                  </Form.Item>

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
                </div>
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

      <Modal
        title="API Key 详情"
        open={!!keyDetail}
        destroyOnHidden
        footer={<Button onClick={() => setKeyDetail(null)}>关闭</Button>}
        onCancel={() => setKeyDetail(null)}
      >
        {keyDetail && (
          <>
            <Descriptions size="small" column={1}>
              <Descriptions.Item label="名称">
                {keyDetail.name || '未命名 Key'}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag
                  color={
                    getApiKeyStatus(keyDetail) === 'active'
                      ? 'success'
                      : getApiKeyStatus(keyDetail) === 'expired'
                        ? 'error'
                        : 'default'
                  }
                >
                  {getApiKeyStatus(keyDetail) === 'active'
                    ? '启用'
                    : getApiKeyStatus(keyDetail) === 'expired'
                      ? '已过期'
                      : '停用'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Token">
                <Typography.Text code>
                  {keyDetail.api_key_masked ||
                    keyDetail.api_key ||
                    '••••••••'}
                </Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="过期时间">
                {getApiKeyExpiryLabel(keyDetail)}
              </Descriptions.Item>
              <Descriptions.Item label="最后使用">
                {keyDetail.last_used_at
                  ? String(keyDetail.last_used_at).slice(0, 10)
                  : '尚未使用'}
              </Descriptions.Item>
              <Descriptions.Item label="权限">
                {keyDetail.pool_access ? 'API + 邮箱池' : '仅 API'}
              </Descriptions.Item>
              <Descriptions.Item label="邮箱范围">
                {parseEmailScope(keyDetail.allowed_emails).length
                  ? parseEmailScope(keyDetail.allowed_emails).join(', ')
                  : '全部邮箱'}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {keyDetail.created_at
                  ? String(keyDetail.created_at).slice(0, 10)
                  : '—'}
              </Descriptions.Item>
            </Descriptions>
            <Alert
              type="info"
              showIcon
              message="权限在创建时固定"
              description="如需变更权限或邮箱范围，请重新创建一个 API Key；列表仅保留最必要的信息。"
              style={{ marginTop: 16 }}
            />
          </>
        )}
      </Modal>

      <Modal
        title="创建 API Key"
        open={createKeyOpen}
        okText="创建 Key"
        cancelText="取消"
        confirmLoading={creatingKey}
        destroyOnHidden
        onOk={() => void onCreateKey()}
        onCancel={() => setCreateKeyOpen(false)}
      >
        <Typography.Paragraph type="secondary">
          提供名称和过期时间即可。Key 将由系统安全生成，并在创建后显示一次。
        </Typography.Paragraph>
        <Form form={keyForm} layout="vertical" requiredMark="optional">
          <Form.Item
            name="name"
            label="Key 名称"
            rules={[
              { required: true, whitespace: true, message: '请输入 Key 名称' },
              { max: 100, message: 'Key 名称不能超过 100 个字符' },
            ]}
          >
            <Input autoFocus placeholder="例如：生产自动化" />
          </Form.Item>
          <Form.Item
            name="expires_in_days"
            label="过期时间"
            rules={[{ required: true, message: '请选择过期时间' }]}
          >
            <Select options={API_KEY_EXPIRY_OPTIONS} />
          </Form.Item>
          <Collapse
            ghost
            items={[
              {
                key: 'scope',
                label: '访问范围（可选）',
                children: (
                  <>
                    <Form.Item
                      name="allowed_emails_text"
                      label="邮箱范围"
                      extra="每行一个邮箱；留空表示全部邮箱"
                      rules={[
                        {
                          validator: async (_, value) => {
                            const invalid = getInvalidEmailScope(value);
                            if (invalid.length) {
                              throw new Error(`邮箱地址无效：${invalid[0]}`);
                            }
                          },
                        },
                      ]}
                    >
                      <Input.TextArea
                        rows={3}
                        placeholder="user@example.com"
                      />
                    </Form.Item>
                    <Space size="large">
                      <Form.Item
                        name="pool_access"
                        label="邮箱池权限"
                        valuePropName="checked"
                      >
                        <Switch />
                      </Form.Item>
                      <Form.Item
                        name="enabled"
                        label="创建后启用"
                        valuePropName="checked"
                      >
                        <Switch />
                      </Form.Item>
                    </Space>
                  </>
                ),
              },
            ]}
          />
        </Form>
      </Modal>

      <Modal
        title="API Key 已创建"
        open={!!createdKey}
        maskClosable={false}
        destroyOnHidden
        onCancel={() => setCreatedKey(null)}
        footer={[
          <Button
            key="copy"
            type="primary"
            icon={<CopyOutlined />}
            onClick={() => void copyCreatedKey()}
          >
            复制 Key
          </Button>,
          <Button key="done" onClick={() => setCreatedKey(null)}>
            完成
          </Button>,
        ]}
      >
        <Alert
          type="warning"
          showIcon
          message="请立即复制并妥善保存"
          description="关闭后将无法再次查看完整 Key；列表中只会保留脱敏值。"
          style={{ marginBottom: 16 }}
        />
        <ProCard variant="outlined">
          <Descriptions size="small" column={1}>
            <Descriptions.Item label="名称">
              {createdKey?.item?.name || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="过期时间">
              {getApiKeyExpiryLabel(createdKey?.item || {})}
            </Descriptions.Item>
            <Descriptions.Item label="权限">
              {createdKey?.item?.pool_access ? 'API + 邮箱池' : '仅 API'}
            </Descriptions.Item>
            <Descriptions.Item label="邮箱范围">
              {Array.isArray(createdKey?.item?.allowed_emails) &&
              createdKey.item.allowed_emails.length
                ? createdKey.item.allowed_emails.join(', ')
                : '全部邮箱'}
            </Descriptions.Item>
          </Descriptions>
          <Divider style={{ margin: '12px 0' }} />
          <Input.Password
            value={createdKey?.api_key || ''}
            readOnly
            visibilityToggle
          />
        </ProCard>
      </Modal>
    </PageContainer>
  );
};

export default SettingsPage;
