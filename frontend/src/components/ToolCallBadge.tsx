import React from 'react';
import { Wrench, Search, Code, Layers, GitFork, FileCode, CheckCircle2, Loader2, AlertCircle } from 'lucide-react';
import { ToolCall } from '../types';
import { Tooltip } from './Tooltip';
import { formatToolArgs } from '../utils/toolArgs';

interface ToolCallBadgeProps {
  toolCall: ToolCall;
  onClick?: () => void;
}

const getToolIcon = (name: string) => {
  const lower = (name || '').toLowerCase();
  if (lower.includes('architecture')) return <Layers className="w-3 h-3 dark:text-sienna-400 text-softrose-500" />;
  if (lower.includes('search_code') || lower.includes('code')) return <Code className="w-3 h-3 dark:text-sienna-400 text-softrose-500" />;
  if (lower.includes('search') || lower.includes('query')) return <Search className="w-3 h-3 dark:text-sienna-400 text-softrose-500" />;
  if (lower.includes('trace') || lower.includes('path')) return <GitFork className="w-3 h-3 dark:text-sienna-400 text-softrose-500" />;
  if (lower.includes('snippet')) return <FileCode className="w-3 h-3 dark:text-sienna-400 text-softrose-500" />;
  return <Wrench className="w-3 h-3 dark:text-sienna-400 text-softrose-500" />;
};

export const ToolCallBadge: React.FC<ToolCallBadgeProps> = ({ toolCall, onClick }) => {
  const argSummary = formatToolArgs(toolCall.args);
  const isRunning = toolCall.status === 'running';
  const isError = toolCall.status === 'error';

  return (
    <Tooltip
      toolName={toolCall.name}
      isRunning={isRunning}
      icon={getToolIcon(toolCall.name)}
    >
      <button
        type="button"
        onClick={onClick}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded card-bg border text-[11px] font-mono transition-all cursor-pointer ${
          isRunning
            ? 'dark:text-sienna-300 text-softrose-600 animate-pulse border-amber-500/40'
            : isError
            ? 'text-rose-400 border-rose-500/40'
            : 'dark:text-sienna-300 text-softrose-600 dark:hover:border-sienna-400 hover:border-softrose-500'
        }`}
      >
        {getToolIcon(toolCall.name)}
        <span className="font-semibold">{toolCall.name}</span>
        {argSummary && <span className="opacity-80 font-sans">{argSummary}</span>}

        {isRunning ? (
          <Loader2 className="w-3 h-3 animate-spin dark:text-sienna-400 text-softrose-500 ml-0.5" />
        ) : isError ? (
          <AlertCircle className="w-3 h-3 text-rose-400 ml-0.5" />
        ) : (
          <CheckCircle2 className="w-3 h-3 dark:text-emerald-400 text-emerald-700 ml-0.5" />
        )}
      </button>
    </Tooltip>
  );
};

