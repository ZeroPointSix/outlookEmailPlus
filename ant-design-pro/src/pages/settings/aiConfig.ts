export type VerificationAiProvider = 'openai' | 'openai_compatible';

export const OPENAI_VERIFICATION_AI_BASE_URL = 'https://api.openai.com/v1';

export const VERIFICATION_AI_MODEL_OPTIONS = [
  { value: 'gpt-4.1-mini', label: 'gpt-4.1-mini' },
  { value: 'gpt-4.1', label: 'gpt-4.1' },
  { value: 'gpt-4o-mini', label: 'gpt-4o-mini' },
];

export function normalizeVerificationAiEndpoint(baseUrl: string): string {
  const value = String(baseUrl || '').trim();
  if (!value) return '';
  if (value.toLowerCase().endsWith('/chat/completions')) return value;
  return `${value.replace(/\/+$/, '')}/chat/completions`;
}

export function inferVerificationAiProvider(
  baseUrl: string,
): VerificationAiProvider {
  const normalized = String(baseUrl || '')
    .trim()
    .replace(/\/+$/, '')
    .toLowerCase();
  if (
    normalized === OPENAI_VERIFICATION_AI_BASE_URL.toLowerCase() ||
    normalized ===
      `${OPENAI_VERIFICATION_AI_BASE_URL}/chat/completions`.toLowerCase()
  ) {
    return 'openai';
  }
  return 'openai_compatible';
}