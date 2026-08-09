import { describe, expect, it } from 'vitest';
import {
  inferVerificationAiProvider,
  normalizeVerificationAiEndpoint,
  OPENAI_VERIFICATION_AI_BASE_URL,
} from './aiConfig';

describe('verification AI configuration helpers', () => {
  it('appends chat/completions to an API base URL', () => {
    expect(normalizeVerificationAiEndpoint('https://api.example.com/v1/')).toBe(
      'https://api.example.com/v1/chat/completions',
    );
  });

  it('keeps a complete chat/completions endpoint unchanged', () => {
    const endpoint = 'https://api.example.com/v1/chat/completions';
    expect(normalizeVerificationAiEndpoint(endpoint)).toBe(endpoint);
  });

  it('infers the official OpenAI provider from its base URL', () => {
    expect(inferVerificationAiProvider(OPENAI_VERIFICATION_AI_BASE_URL)).toBe(
      'openai',
    );
    expect(inferVerificationAiProvider('https://gateway.example.com/v1')).toBe(
      'openai_compatible',
    );
  });
});