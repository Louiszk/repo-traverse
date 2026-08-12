const IGNORED_KEYS = new Set([
  'config',
  'session_id',
  'thread_id',
  'configurable',
  'project',
  'project_name',
  'session',
]);

export const cleanStringArg = (val: string): string => {
  return val.replace(/^(?:.*?[/\\])?(?:app-data-session|session)-[a-fA-F0-9-]+-repo[/.]?/i, '');
};

export const filterUserArgs = (args?: Record<string, unknown>): Array<[string, unknown]> => {
  if (!args || typeof args !== 'object') return [];

  const entries: Array<[string, unknown]> = [];
  for (const [key, val] of Object.entries(args)) {
    if (IGNORED_KEYS.has(key) || key.startsWith('_')) continue;
    if (val === undefined || val === null || val === '') continue;

    let cleanedVal = val;
    if (typeof val === 'string') {
      cleanedVal = cleanStringArg(val);
      if (!cleanedVal && (val.includes('app-data-session') || val.includes('session-'))) {
        continue;
      }
    }
    entries.push([key, cleanedVal]);
  }
  return entries;
};

export const formatToolArgs = (args?: Record<string, unknown>): string => {
  const userEntries = filterUserArgs(args);
  if (userEntries.length === 0) return '';

  const [_, firstVal] = userEntries[0];
  if (typeof firstVal === 'string') {
    return firstVal.length > 24 ? `"${firstVal.slice(0, 24)}..."` : `"${firstVal}"`;
  }
  if (typeof firstVal === 'number' || typeof firstVal === 'boolean') {
    return String(firstVal);
  }
  return '';
};
