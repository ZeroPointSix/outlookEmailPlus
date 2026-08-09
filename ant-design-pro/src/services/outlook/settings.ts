import { outlookRequest } from './request';

export type AppSettings = Record<string, any>;

export async function fetchSettings() {
  return outlookRequest<{ success: boolean; settings?: AppSettings; error?: any }>(
    '/api/settings',
    { method: 'GET', skipErrorHandler: true },
  );
}

export async function updateSettings(partial: AppSettings) {
  return outlookRequest<{ success: boolean; message?: string; error?: any }>(
    '/api/settings',
    {
      method: 'PUT',
      data: partial,
      skipErrorHandler: true,
    },
  );
}

export const POLLING_INTERVAL_MIN = 3;
export const POLLING_INTERVAL_MAX = 300;
export const POLLING_COUNT_MIN = 0;
export const POLLING_COUNT_MAX = 100;

export function normalizePollingSettings(interval: number, maxCount: number) {
  const parsedInterval = Math.trunc(Number(interval));
  const parsedMaxCount = Math.trunc(Number(maxCount));
  return {
    polling_interval: Number.isFinite(parsedInterval)
      ? Math.min(POLLING_INTERVAL_MAX, Math.max(POLLING_INTERVAL_MIN, parsedInterval))
      : 10,
    polling_count: Number.isFinite(parsedMaxCount)
      ? Math.min(POLLING_COUNT_MAX, Math.max(POLLING_COUNT_MIN, parsedMaxCount))
      : 5,
  };
}

export async function updatePollingSettings(interval: number, maxCount: number) {
  return updateSettings(normalizePollingSettings(interval, maxCount));
}

export async function fetchHealth() {
  return outlookRequest<{ status?: string; version?: string }>('/healthz', {
    method: 'GET',
    skipErrorHandler: true,
  });
}

export async function testTelegram() {
  return outlookRequest<{ success: boolean; message?: string; error?: any }>(
    '/api/settings/telegram-test',
    { method: 'POST', data: {}, skipErrorHandler: true },
  );
}

export async function testEmailNotification() {
  return outlookRequest<{ success: boolean; message?: string; error?: any }>(
    '/api/settings/email-test',
    { method: 'POST', data: {}, skipErrorHandler: true },
  );
}

export async function testWebhook(body: Record<string, any> = {}) {
  return outlookRequest<{ success: boolean; message?: string; error?: any }>(
    '/api/settings/webhook-test',
    { method: 'POST', data: body, skipErrorHandler: true },
  );
}

export type VerificationAiProbe = {
  ok?: boolean;
  error?: string;
  error_category?: string;
  message?: string;
  hint?: string;
  endpoint?: string;
  model?: string;
  requested_model?: string;
  http_status?: number;
  latency_ms?: number;
  missing_fields?: string[];
  [key: string]: any;
};

export type VerificationAiTestResponse = {
  success: boolean;
  ok?: boolean;
  connectivity_ok?: boolean;
  contract_ok?: boolean;
  message?: string;
  probe?: VerificationAiProbe;
  error?: any;
};

export async function testVerificationAi(body: Record<string, any> = {}) {
  return outlookRequest<VerificationAiTestResponse>(
    '/api/settings/verification-ai-test',
    { method: 'POST', data: body, skipErrorHandler: true },
  );
}

export async function validateCron(cron: string) {
  return outlookRequest<{ success: boolean; message?: string; error?: any }>(
    '/api/settings/validate-cron',
    {
      method: 'POST',
      data: { cron_expression: cron },
      skipErrorHandler: true,
    },
  );
}

export type ExternalApiKeyItem = {
  id?: number;
  name?: string;
  api_key?: string;
  api_key_masked?: string;
  enabled?: boolean;
  pool_access?: boolean;
  allowed_emails?: string[] | string;
  note?: string;
  consumer_key?: string;
  today_total_count?: number;
  today_success_count?: number;
  today_error_count?: number;
  today_last_used_at?: string;
  [key: string]: any;
};

export async function syncCfWorkerDomains() {
  return outlookRequest<{
    success: boolean;
    message?: string;
    data?: any;
    error?: any;
  }>('/api/settings/cf-worker-sync-domains', {
    method: 'POST',
    data: {},
    skipErrorHandler: true,
  });
}

export async function fetchDeploymentInfo() {
  return outlookRequest<{
    success: boolean;
    deployment?: Record<string, any>;
    error?: any;
  }>('/api/system/deployment-info', {
    method: 'GET',
    skipErrorHandler: true,
  });
}

export async function triggerSystemUpdate(method?: string) {
  const qs = method ? `?method=${encodeURIComponent(method)}` : '';
  return outlookRequest<{ success: boolean; message?: string; error?: any }>(
    `/api/system/trigger-update${qs}`,
    { method: 'POST', data: {}, skipErrorHandler: true },
  );
}

export function pickSettingsError(payload: any, fallback = '请求失败'): string {
  if (!payload) return fallback;
  if (typeof payload.error === 'string' && payload.error) return payload.error;
  if (payload.error && typeof payload.error === 'object') {
    return (
      payload.error.message ||
      payload.error.message_en ||
      payload.error.code ||
      fallback
    );
  }
  if (typeof payload.message === 'string' && payload.message) return payload.message;
  return fallback;
}