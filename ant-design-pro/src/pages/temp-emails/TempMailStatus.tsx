import { Alert, Space, Tag, Tooltip, Typography } from 'antd';
import type { ReactNode } from 'react';
import type { TempEmailOptions } from '@/services/outlook/tempEmails';
import {
  providerKindLabel,
  type TempMailAvailability,
} from './utils';

type TempMailStatusProps = {
  availability: TempMailAvailability;
  options?: TempEmailOptions;
  actions?: ReactNode;
};

const STATUS_META: Record<
  TempMailAvailability['state'],
  {
    alertType: 'success' | 'info' | 'warning' | 'error';
    tagColor: 'success' | 'processing' | 'warning' | 'error';
    label: string;
  }
> = {
  ready: {
    alertType: 'success',
    tagColor: 'success',
    label: '已启用',
  },
  loading: {
    alertType: 'info',
    tagColor: 'processing',
    label: '检查中',
  },
  disabled: {
    alertType: 'warning',
    tagColor: 'warning',
    label: '未启用',
  },
  not_configured: {
    alertType: 'warning',
    tagColor: 'warning',
    label: '需配置',
  },
  unavailable: {
    alertType: 'error',
    tagColor: 'error',
    label: '不可用',
  },
};

export function TempMailStatus({
  availability,
  options,
  actions,
}: TempMailStatusProps) {
  const meta = STATUS_META[availability.state];
  const providerLabel = options?.provider_label || options?.provider_name;

  return (
    <Alert
      className="temp-mail-status"
      type={meta.alertType}
      showIcon
      message={
        <Space size={[8, 4]} wrap>
          <Typography.Text strong>临时邮箱服务</Typography.Text>
          <Tooltip title={availability.message}>
            <Tag color={meta.tagColor}>{meta.label}</Tag>
          </Tooltip>
          {providerLabel ? <Tag>{providerLabel}</Tag> : null}
          {options?.provider_kind ? (
            <Tag>{providerKindLabel(options.provider_kind)}</Tag>
          ) : null}
          {availability.state !== 'ready' ? (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {availability.message}
            </Typography.Text>
          ) : null}
        </Space>
      }
      action={actions}
      style={{
        display: 'inline-flex',
        maxWidth: '100%',
        marginBottom: 16,
        padding: '6px 12px',
      }}
    />
  );
}
