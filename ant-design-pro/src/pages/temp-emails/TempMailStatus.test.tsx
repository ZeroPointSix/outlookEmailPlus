import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TempMailStatus } from './TempMailStatus';

describe('TempMailStatus', () => {
  it('keeps the ready state compact while retaining provider context', () => {
    render(
      <TempMailStatus
        availability={{
          state: 'ready',
          enabled: true,
          canGenerate: true,
          message: '临时邮箱服务已启用',
        }}
        options={{
          provider_label: 'Cloudflare Worker',
          provider_kind: 'builtin',
        }}
        actions={<button type="button">设置</button>}
      />,
    );

    expect(screen.getByText('临时邮箱服务')).toBeInTheDocument();
    expect(screen.getByText('已启用')).toBeInTheDocument();
    expect(screen.getByText('Cloudflare Worker')).toBeInTheDocument();
    expect(screen.getByText('内置')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '设置' })).toBeInTheDocument();
    expect(screen.queryByText('生成邮箱')).not.toBeInTheDocument();

    expect(screen.getByRole('alert')).toHaveStyle({
      display: 'inline-flex',
      padding: '6px 12px',
    });
  });

  it('shows the reason when the service needs attention', () => {
    render(
      <TempMailStatus
        availability={{
          state: 'not_configured',
          enabled: true,
          canGenerate: false,
          message: '请先配置临时邮箱接口',
        }}
      />,
    );

    expect(screen.getByText('需配置')).toBeInTheDocument();
    expect(screen.getByText('请先配置临时邮箱接口')).toBeInTheDocument();
  });
});
