export interface ToolCall {
  id?: string;
  name: string;
  args?: Record<string, unknown>;
  status?: 'running' | 'done' | 'error';
  output?: string;
}

export interface Message {
  id: string;
  sender: 'user' | 'ai';
  text: string;
  timestamp: string;
  toolCalls?: ToolCall[];
  isStreaming?: boolean;
  isError?: boolean;
  errorMessage?: string;
}

export interface RepoErrorDetail {
  message: string;
  reason?: string;
}

export interface IndexRepoRequest {
  github_url: string;
}

export interface IndexRepoResponse {
  task_id: string;
  session_id: string;
  message: string;
  github_url: string;
  csrf_token?: string;
}

export interface IndexStatusResponse {
  status: 'PENDING' | 'PROCESSING' | 'SUCCESS' | 'FAILURE';
  task_id: string;
  stage?: string | null;
  detail?: string | RepoErrorDetail | null;
  session_id?: string | null;
  github_url?: string | null;
}

export interface ChatRequest {
  session_id: string;
  message: string;
}

export interface ClearSessionRequest {
  session_id: string;
}

export interface SSEFinalReplyEvent {
  type: 'final_reply';
  reply: string;
  tool_calls?: ToolCall[];
  is_context_full?: boolean;
}

export interface ToolDocInfo {
  summary: string;
  description: string;
}
