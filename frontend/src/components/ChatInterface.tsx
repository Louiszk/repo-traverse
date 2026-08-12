import React, { useState, useRef, useEffect } from 'react';
import {
  ArrowUp,
  Code,
  AlertTriangle,
  Copy,
  FolderTree,
} from 'lucide-react';
import { Message } from '../types';
import { MarkdownRenderer } from './MarkdownRenderer';
import { ToolCallBadge } from './ToolCallBadge';
import { GridSpinner } from './GridSpinner';
import { SidePanel, ActivePanelState } from './SidePanel';
import { ConversationExportMenu } from './ConversationExportMenu';
import { copyToClipboard } from '../utils/exportUtils';
import { MAX_MESSAGES_PER_SESSION, MAX_CHAT_MESSAGE_LENGTH } from '../utils/constants';

import { useResizablePanel } from '../hooks/useResizablePanel';

interface ChatInterfaceProps {
  sessionId: string;
  csrfToken: string;
  githubUrl: string;
  messages: Message[];
  onSendMessage: (text: string) => Promise<void>;
  isSending: boolean;
  onResetRepo: () => void;
  isContextFull?: boolean;
  onAuthError?: () => void;
}

const SUGGESTED_PROMPTS = [
  "How is the project architecture structured?",
  "Where are the primary API routes defined?",
  "How does error handling and logging work?",
  "Can you explain the repository entrypoint?",
];

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  sessionId,
  csrfToken,
  githubUrl,
  messages,
  onSendMessage,
  isSending,
  onResetRepo,
  isContextFull = false,
  onAuthError,
}) => {
  const [inputText, setInputText] = useState('');
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [activePanel, setActivePanel] = useState<ActivePanelState>(null);

  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const prevMessagesCountRef = useRef(messages.length);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const {
    leftWidthPercent,
    setLeftWidthPercent,
    isResizing,
    isDesktopLayout,
    isSmallViewport,
    handleMouseDown
  } = useResizablePanel(50, containerRef);

  const scrollToBottom = () => {
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTo({
        top: messagesContainerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  };

  useEffect(() => {
    if (messages.length > prevMessagesCountRef.current) {
      scrollToBottom();
    }
    prevMessagesCountRef.current = messages.length;
  }, [messages.length]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = inputText.trim();
    if (!trimmed || isSending) return;

    setInputText('');
    onSendMessage(trimmed);
  };

  const handlePromptClick = (prompt: string) => {
    if (isSending) return;
    onSendMessage(prompt);
  };

  const handleCopyMessage = async (msg: Message) => {
    const content = msg.text || msg.errorMessage || '';
    if (!content) return;
    const success = await copyToClipboard(content);
    if (success) {
      setCopiedMessageId(msg.id);
      setTimeout(() => {
        setCopiedMessageId(null);
      }, 2000);
    }
  };

  const repoName = githubUrl.replace(/^https?:\/\/github\.com\//, '');
  const shortRepoName = repoName.split('/').pop() || repoName;
  const hasActiveStreamingMessage = messages.some((m) => m.sender === 'ai' && m.isStreaming);
  const userMessages = messages.filter((m) => m.sender === 'user').length;
  const isLimitReached = userMessages >= MAX_MESSAGES_PER_SESSION;

  return (
    <div className="w-full flex-1 flex flex-col min-h-0">
      {/* Main Content Area: Resizable Two-Column Layout */}
      <div
        ref={containerRef}
        className={`flex-1 flex w-full min-h-0 overflow-hidden relative ${
          isResizing ? 'select-none' : ''
        }`}
      >
        {/* Left Column: Chat Stream */}
        <div
          style={{ width: activePanel && isDesktopLayout ? `${leftWidthPercent}%` : '100%' }}
          className="flex flex-col h-full min-w-0 transition-none"
        >
          {/* Left Column Header */}
          <div className="px-4 sm:px-6 py-3 border-b subtle-bg flex items-center justify-center sm:justify-between gap-3 text-xs flex-shrink-0">
            <div className="hidden sm:flex items-center gap-2 min-w-0 pr-2">
              <span className="font-semibold dark:text-slate-100 text-rose-950 flex-shrink-0">Workspace Session</span>
              <span className="text-slate-400 flex-shrink-0">&bull;</span>
              <span className="dark:text-sienna-400 text-softrose-500 font-mono truncate">{repoName || 'fastapi/fastapi'}</span>
            </div>
            <div className="flex w-full sm:w-auto flex-wrap items-center justify-center gap-2 sm:gap-3 flex-shrink-0">
              {messages.length > 0 && (
                <ConversationExportMenu
                  messages={messages}
                  repoName={repoName}
                  sessionId={sessionId}
                />
              )}

              <button
                type="button"
                onClick={() => setActivePanel((prev) => (prev ? null : { type: 'tree', path: '' }))}
                className={`px-3 py-1.5 rounded card-bg border text-xs flex items-center gap-1.5 font-medium transition-colors cursor-pointer ${
                  activePanel
                    ? 'dark:text-sienna-400 text-softrose-600 dark:border-sienna-400/50 border-softrose-500/50'
                    : 'dark:text-slate-300 text-rose-950 dark:hover:text-white hover:text-rose-950'
                }`}
              >
                <FolderTree className="w-3.5 h-3.5 dark:text-sienna-400 text-softrose-500" />
                <span>{activePanel ? 'Close Directory' : 'Open Directory'}</span>
              </button>

              <button
                type="button"
                onClick={onResetRepo}
                className="px-3 py-1.5 rounded card-bg dark:text-sienna-300 text-softrose-500 border dark:border-sienna-400/30 border-softrose-500/30 text-xs font-medium transition-colors cursor-pointer"
              >
                Reset Repo
              </button>
            </div>
          </div>

          <div ref={messagesContainerRef} className="flex-1 overflow-y-auto p-6 space-y-6">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-4">
                <div className="space-y-1">
                  <h3 className="text-lg font-bold dark:text-slate-100 text-rose-950">Repository Ready for Architectural QA</h3>
                  <p className="text-xs dark:text-slate-400 text-slate-600 max-w-lg">
                    Ask any question regarding class hierarchies, dependency flow, or system layout.
                  </p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-3xl w-full pt-4">
                  {SUGGESTED_PROMPTS.map((prompt, idx) => (
                    <button
                      key={idx}
                      onClick={() => handlePromptClick(prompt)}
                      className="p-3 text-left rounded-xl card-bg border text-xs dark:text-slate-300 text-rose-950 dark:hover:text-white hover:text-rose-950 transition-all flex items-start gap-2 group cursor-pointer h-full"
                    >
                      <Code className="w-4 h-4 dark:text-sienna-400 text-softrose-500 group-hover:scale-110 transition-transform flex-shrink-0" />
                      <span className="leading-snug">{prompt}</span>
                    </button>
                  ))}
                </div>

                <p className="text-[11px] dark:text-slate-500 text-slate-500 max-w-md pt-2">
                  Please do not enter personal data or sensitive secrets into the chat.
                </p>
              </div>
            ) : (
              messages.map((msg) => {
                const isError = Boolean(
                  msg.isError ||
                    msg.errorMessage ||
                    (msg.text &&
                      (msg.text.startsWith('Error:') ||
                        msg.text.startsWith('Recursion limit reached') ||
                        msg.text.startsWith('An error occurred')))
                );
                const errorContent = msg.errorMessage || (isError ? msg.text : '');

                if (msg.sender === 'user') {
                  return (
                    <div key={msg.id} className="flex flex-col items-end space-y-1 max-w-3xl ml-auto">
                      <div className="px-4 py-3 rounded-xl accent-btn font-semibold text-sm leading-relaxed">
                        {msg.text}
                      </div>
                      <span className="text-[10px] dark:text-slate-400 text-slate-600 font-mono pr-1">{msg.timestamp}</span>
                    </div>
                  );
                }

                return (
                  <div key={msg.id} className="flex flex-col items-start space-y-2 max-w-3xl">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold dark:text-slate-200 text-rose-950">Model</span>
                      <span className="text-[10px] dark:text-slate-400 text-slate-600 font-mono">{msg.timestamp}</span>
                    </div>

                    <div className="panel-bg p-5 rounded-xl border space-y-4 text-sm dark:text-slate-200 text-rose-950 w-full shadow-sm">
                      {/* Tool Call Badges */}
                      {msg.toolCalls && msg.toolCalls.length > 0 && (
                        <div className="flex flex-wrap gap-2 pb-2 border-b border-slate-700/30">
                          {msg.toolCalls.map((tc, index) => (
                            <ToolCallBadge
                              key={tc.id || `${tc.name}-${index}`}
                              toolCall={tc}
                              onClick={() => setActivePanel({ type: 'tool', call: tc })}
                            />
                          ))}
                        </div>
                      )}

                      {/* Single GridSpinner while model is generating response */}
                      {msg.isStreaming && !msg.text && (
                        <div className="flex items-center gap-2.5 text-xs font-mono dark:text-slate-400 text-slate-600 py-1">
                          <GridSpinner size="sm" />
                          <span>Generating response...</span>
                        </div>
                      )}

                      {/* Content rendering */}
                      {isError ? (
                        <div className="space-y-2">
                          {msg.errorMessage && msg.text && (
                            <MarkdownRenderer
                              content={msg.text}
                              onFileClick={(path) => setActivePanel({ type: 'file', path })}
                              onDirClick={(path) => setActivePanel({ type: 'tree', path })}
                              onSymbolClick={(symbol) => setActivePanel({ type: 'symbol', symbol })}
                            />
                          )}
                          <div className="rounded-xl bg-rose-500/10 border border-rose-500/30 p-3.5 text-rose-200 text-xs space-y-1.5 shadow-inner">
                            <div className="flex items-center gap-2 font-semibold text-rose-400">
                              <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0" />
                              <span>Execution Error</span>
                            </div>
                            <p className="font-mono whitespace-pre-wrap leading-relaxed text-rose-200/90">
                              {errorContent}
                            </p>
                          </div>
                        </div>
                      ) : (
                        msg.text ? (
                          <MarkdownRenderer
                            content={msg.text}
                            onFileClick={(path) => setActivePanel({ type: 'file', path })}
                            onDirClick={(path) => setActivePanel({ type: 'tree', path })}
                            onSymbolClick={(symbol) => setActivePanel({ type: 'symbol', symbol })}
                          />
                        ) : null
                      )}

                      {!msg.isStreaming && (
                        <div className="flex items-center justify-end text-[11px] text-slate-400 pt-2 border-t border-slate-700/30">
                          <button
                            type="button"
                            onClick={() => handleCopyMessage(msg)}
                            className="dark:text-slate-400 text-slate-600 dark:hover:text-slate-200 hover:text-rose-950 transition-colors cursor-pointer flex items-center gap-1"
                          >
                            {copiedMessageId === msg.id ? (
                              <span className="dark:text-emerald-400 text-emerald-700 font-semibold">Copied!</span>
                            ) : (
                              <>
                                <Copy className="w-3 h-3" />
                                <span>Copy response</span>
                              </>
                            )}
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })
            )}

            {isSending && !hasActiveStreamingMessage && (
              <div className="flex items-start gap-2 max-w-3xl">
                <div className="panel-bg p-4 rounded-xl border flex items-center gap-3 text-xs font-mono">
                  <GridSpinner size="sm" />
                  <span className="dark:text-slate-400 text-slate-600">Processing query...</span>
                </div>
              </div>
            )}
          </div>

          {/* Bottom Chat Input Form */}
          <div className="p-4 panel-bg border-t flex-shrink-0">
            <form onSubmit={handleSubmit} className="relative flex items-center">
              <input
                ref={inputRef}
                type="text"
                value={inputText}
                maxLength={MAX_CHAT_MESSAGE_LENGTH}
                onChange={(e) => setInputText(e.target.value)}
                disabled={isSending || isLimitReached || isContextFull}
                placeholder={
                  isContextFull
                    ? "Context limit reached. Please start a new repository session."
                    : isLimitReached
                    ? "Session limit reached. Please start a new repository session."
                    : isSmallViewport
                    ? "Ask anything about the codebase structure..."
                    : "Ask anything about the codebase structure or functions..."
                }
                className="w-full pl-4 pr-12 py-3 rounded subtle-bg border text-sm font-sans dark:text-slate-100 text-rose-950 dark:placeholder-slate-400 placeholder-slate-600 focus:outline-none dark:focus:border-sienna-400 focus:border-softrose-500 transition-colors disabled:opacity-50"
              />

              <button
                type="submit"
                disabled={isSending || !inputText.trim() || isLimitReached || isContextFull}
                className="absolute right-2 p-2 rounded accent-btn transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                <ArrowUp className="w-4 h-4" />
              </button>
            </form>

            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center px-1 mt-2 text-[11px] gap-1">
              <div className="flex flex-wrap items-center gap-2 flex-shrink-0">
                <span className="dark:text-slate-400 text-slate-600 font-mono">Messages: {userMessages}/{MAX_MESSAGES_PER_SESSION}</span>
                <span className="dark:text-slate-500 text-slate-400">&bull;</span>
                <span className="dark:text-slate-400 text-slate-600">AI models may make mistakes, so double-check outputs.</span>
                {isContextFull ? (
                  <span className="text-amber-500 font-semibold">&bull; Context full.</span>
                ) : isLimitReached ? (
                  <span className="text-amber-500 font-semibold">&bull; Session limit.</span>
                ) : null}
              </div>
            </div>
          </div>
        </div>

        {/* Resizable Handle Divider */}
        {activePanel && isDesktopLayout && (
          <div
            onMouseDown={handleMouseDown}
            onDoubleClick={() => setLeftWidthPercent(50)}
            className={`w-1.5 hover:w-2 group relative z-20 cursor-col-resize border-x border-slate-700/30 flex items-center justify-center transition-all ${
              isResizing
                ? 'dark:bg-sienna-400 bg-softrose-500 w-2'
                : 'subtle-bg dark:hover:bg-sienna-400/40 hover:bg-softrose-500/40'
            }`}
            title="Drag to resize columns (Double click to reset 50/50)"
          >
            <div className="w-1 h-8 rounded-full dark:bg-sienna-400/60 bg-softrose-500/60 group-hover:scale-125 transition-transform" />
          </div>
        )}

        {/* Right Column: Resizable Explorer / Side Panel View */}
        {activePanel && (
          <aside
            style={isDesktopLayout ? { width: `${100 - leftWidthPercent}%` } : undefined}
            className={`${
              isDesktopLayout
                ? 'relative h-full flex-shrink-0'
                : 'absolute inset-0 z-30 h-full w-full shadow-2xl'
            } flex min-w-0 overflow-hidden`}
          >
            <SidePanel
              activePanel={activePanel}
              sessionId={sessionId}
              csrfToken={csrfToken}
              repoName={shortRepoName}
              onClose={() => setActivePanel(null)}
              onNavigate={(newState) => setActivePanel(newState)}
              onAuthError={onAuthError}
            />
          </aside>
        )}
      </div>
    </div>
  );
};

