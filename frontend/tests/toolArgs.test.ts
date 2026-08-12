import { describe, it, expect } from 'vitest';
import { filterUserArgs, formatToolArgs, cleanStringArg } from '../src/utils/toolArgs';

describe('cleanStringArg', () => {
  it('strips internal app session directory prefixes from file paths', () => {
    const rawPath = 'app-data-session-12345-repo/src/App.tsx';
    expect(cleanStringArg(rawPath)).toBe('src/App.tsx');
  });

  it('leaves standard relative paths untouched', () => {
    expect(cleanStringArg('src/components/Header.tsx')).toBe('src/components/Header.tsx');
  });
});

describe('filterUserArgs', () => {
  it('filters out system internal keys and underscore prefixed keys', () => {
    const args = {
      session_id: 'sess-123',
      config: { env: 'dev' },
      thread_id: 't-1',
      _internal: 'hidden',
      query: 'search_term',
      limit: 10,
    };

    const filtered = filterUserArgs(args);
    expect(filtered).toEqual([
      ['query', 'search_term'],
      ['limit', 10],
    ]);
  });

  it('handles null, undefined, or empty inputs gracefully', () => {
    expect(filterUserArgs(undefined)).toEqual([]);
    expect(filterUserArgs(null as unknown as Record<string, unknown>)).toEqual([]);
    expect(filterUserArgs({ session_id: '123', _key: 'val' })).toEqual([]);
  });
});

describe('formatToolArgs', () => {
  it('formats short string arguments properly', () => {
    expect(formatToolArgs({ query: 'fastapi' })).toBe('"fastapi"');
  });

  it('truncates long string arguments to 24 characters', () => {
    const longQuery = 'a_very_long_search_query_that_exceeds_twenty_four_chars';
    expect(formatToolArgs({ query: longQuery })).toBe(`"${longQuery.slice(0, 24)}..."`);
  });

  it('formats numeric and boolean arguments as strings', () => {
    expect(formatToolArgs({ limit: 42 })).toBe('42');
    expect(formatToolArgs({ active: true })).toBe('true');
  });

  it('returns empty string when no displayable user arguments are present', () => {
    expect(formatToolArgs({ session_id: 'abc' })).toBe('');
    expect(formatToolArgs(undefined)).toBe('');
  });
});
