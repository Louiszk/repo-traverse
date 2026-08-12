import { describe, it, expect } from 'vitest';
import { TOOL_DOCS } from '../src/utils/constants';

describe('TOOL_DOCS Registry', () => {
  const expectedTools = [
    'get_architecture',
    'search_graph',
    'search_code',
    'trace_call_path',
    'get_code_snippet',
    'query_graph',
  ];

  it('contains documentation entries for all expected core tools', () => {
    for (const toolName of expectedTools) {
      expect(TOOL_DOCS).toHaveProperty(toolName);
      expect(TOOL_DOCS[toolName].summary).toBeDefined();
      expect(TOOL_DOCS[toolName].summary.length).toBeGreaterThan(0);
      expect(TOOL_DOCS[toolName].description).toBeDefined();
      expect(TOOL_DOCS[toolName].description.length).toBeGreaterThan(0);
    }
  });
});
