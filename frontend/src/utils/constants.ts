export const CSRF_HEADER_NAME = 'X-CSRF-Token';
export const MAX_MESSAGES_PER_SESSION = Number(import.meta.env.VITE_MAX_MESSAGES_PER_SESSION) || 8;
export const MAX_CHAT_MESSAGE_LENGTH = Number(import.meta.env.VITE_MAX_CHAT_MESSAGE_LENGTH) || 1000;

import { ToolDocInfo } from '../types';

export const TOOL_DOCS: Record<string, ToolDocInfo> = {
  get_architecture: {
    summary: 'Repository Architecture Overview',
    description:
      'Explores repository structure, language distribution, entry points, HTTP routes, hotspots, and Leiden community clusters.',
  },
  search_graph: {
    summary: 'Knowledge Graph Symbol Search',
    description:
      'Searches AST graph nodes to locate exact function, class, route, or variable symbol definitions and qualified names.',
  },
  search_code: {
    summary: 'Graph-Enriched Code Search',
    description:
      'Performs grep text pattern matching enriched with knowledge graph metadata and symbol context.',
  },
  trace_call_path: {
    summary: 'Call Graph & Data Flow Tracer',
    description:
      'Traces caller/callee dependencies, data flows, and cross-service HTTP routes up to a specified hop depth.',
  },
  get_code_snippet: {
    summary: 'Source Code & File Snippet Fetcher',
    description:
      'Fetches exact source code implementations via qualified name or raw file contents by filename with line ranges.',
  },
  query_graph: {
    summary: 'openCypher Graph Query',
    description:
      'Executes custom read-only openCypher queries directly against the repository knowledge graph database.',
  },
};
