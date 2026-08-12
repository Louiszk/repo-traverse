import { useState } from 'react';
import { Message, ToolCall } from '../types';
import { CSRF_HEADER_NAME } from '../utils/constants';

interface UseChatStreamProps {
  sessionId: string;
  csrfToken: string;
  onContextFull: () => void;
  onAuthError: () => void;
}

export const useChatStream = ({ sessionId, csrfToken, onContextFull, onAuthError }: UseChatStreamProps) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isSendingChat, setIsSendingChat] = useState<boolean>(false);

  const handleSendMessage = async (text: string) => {
    if (!sessionId || !text.trim()) return;

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      sender: 'user',
      text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    const aiMessageId = `ai-${Date.now()}`;
    const initialAiMessage: Message = {
      id: aiMessageId,
      sender: 'ai',
      text: '',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      toolCalls: [],
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMessage, initialAiMessage]);
    setIsSendingChat(true);

    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          [CSRF_HEADER_NAME]: csrfToken,
        },
        body: JSON.stringify({
          session_id: sessionId,
          message: text,
        }),
      });

      if (response.status === 401 || response.status === 403 || response.status === 404) {
        const errorData = await response.json().catch(() => ({}));
        if (response.status === 403 && typeof errorData?.detail === 'string' && errorData.detail.includes('Context full')) {
          onContextFull();
          throw new Error('Context full, start a new session');
        }
        onAuthError();
        throw new Error(
          errorData?.detail ||
            (response.status === 404
              ? 'Session expired due to inactivity. Please index the repository again.'
              : 'Session authentication failed. Please re-index the repository.')
        );
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData?.detail || 'Failed to start chat stream.');
      }

      if (!response.body) {
        throw new Error('Streaming response was unavailable.');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith('data: ')) {
            try {
              const event = JSON.parse(trimmed.slice(6));
              if (event.type === 'tool_start') {
                const newToolCall: ToolCall = {
                  name: event.tool,
                  args: event.args,
                  status: 'running',
                };
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === aiMessageId
                      ? { ...msg, toolCalls: [...(msg.toolCalls || []), newToolCall] }
                      : msg
                  )
                );
              } else if (event.type === 'tool_end') {
                const toolStatus = event.status === 'error' ? 'error' : 'done';
                setMessages((prev) =>
                  prev.map((msg) => {
                    if (msg.id !== aiMessageId) return msg;
                    const updatedCalls = [...(msg.toolCalls || [])];
                    const runningIdx = updatedCalls
                      .map((c) => c.name === event.tool && c.status === 'running')
                      .lastIndexOf(true);
                    if (runningIdx !== -1) {
                      updatedCalls[runningIdx] = {
                        ...updatedCalls[runningIdx],
                        status: toolStatus,
                        output: event.output !== undefined ? event.output : updatedCalls[runningIdx].output,
                      };
                    } else {
                      const nameIdx = updatedCalls.map((c) => c.name === event.tool).lastIndexOf(true);
                      if (nameIdx !== -1) {
                        updatedCalls[nameIdx] = {
                          ...updatedCalls[nameIdx],
                          status: toolStatus,
                          output: event.output !== undefined ? event.output : updatedCalls[nameIdx].output,
                        };
                      }
                    }
                    return { ...msg, toolCalls: updatedCalls };
                  })
                );
              } else if (event.type === 'token') {
                const tokenText = event.delta || event.content || '';
                if (tokenText) {
                  setMessages((prev) =>
                    prev.map((msg) =>
                      msg.id === aiMessageId
                        ? { ...msg, text: (msg.text || '') + tokenText }
                        : msg
                    )
                  );
                }
              } else if (event.type === 'final_reply') {
                if (event.is_context_full) {
                  onContextFull();
                }
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === aiMessageId
                      ? {
                          ...msg,
                          text: event.reply || msg.text || '',
                          isStreaming: false,
                          toolCalls: (msg.toolCalls || []).map((tc) => ({
                            ...tc,
                            status: tc.status === 'running' ? ('done' as const) : tc.status,
                          })),
                        }
                      : msg
                  )
                );
              } else if (event.type === 'error') {
                const errorMsg = event.detail || 'Streaming error';
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === aiMessageId
                      ? {
                          ...msg,
                          text: msg.text ? `${msg.text}\n\n[${errorMsg}]` : errorMsg,
                          isStreaming: false,
                          toolCalls: (msg.toolCalls || []).map((tc) => ({
                            ...tc,
                            status: tc.status === 'running' ? ('error' as const) : tc.status,
                          })),
                        }
                      : msg
                  )
                );
                return;
              }
            } catch (parseErr) {
              console.error('SSE parse error:', parseErr);
            }
          }
        }
      }
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Unable to connect to chat API.';
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === aiMessageId
            ? {
                ...msg,
                text: msg.text ? `${msg.text}\n\n[Error: ${errMsg}]` : `Error: ${errMsg}`,
                isStreaming: false,
                toolCalls: (msg.toolCalls || []).map((tc) => ({
                  ...tc,
                  status: tc.status === 'running' ? ('error' as const) : tc.status,
                })),
              }
            : msg
        )
      );
    } finally {
      setIsSendingChat(false);
    }
  };

  return { messages, setMessages, isSendingChat, handleSendMessage };
};
