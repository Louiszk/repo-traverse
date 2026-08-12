import React, { useState } from 'react';
import { Copy, Terminal, Code2 } from 'lucide-react';
import { ToolCall } from '../types';
import { TOOL_DOCS } from '../utils/constants';
import { copyToClipboard } from '../utils/exportUtils';

interface ToolViewProps {
  toolCall: ToolCall;
}

export const ToolView: React.FC<ToolViewProps> = ({ toolCall }) => {
  const [copied, setCopied] = useState<boolean>(false);

  const handleCopy = async (text: string) => {
    const ok = await copyToClipboard(text);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const doc = TOOL_DOCS[toolCall.name] || {
    summary: 'Tool Execution',
    description: `Executes tool '${toolCall.name}'`,
  };
  const isError = toolCall.status === 'error';
  const isRunning = toolCall.status === 'running';

  let argEntries: [string, unknown][] = [];
  if (toolCall.args) {
    let parsedArgs: unknown = toolCall.args;
    if (typeof parsedArgs === 'string') {
      try {
        parsedArgs = JSON.parse(parsedArgs);
      } catch {
        parsedArgs = {};
      }
    }
    if (parsedArgs && typeof parsedArgs === 'object' && !Array.isArray(parsedArgs)) {
      argEntries = Object.entries(parsedArgs).filter(
        ([_, val]) => val !== undefined && val !== null && val !== ''
      );
    }
  }

  return (
    <div className="space-y-4">
      {/* Tool Metadata */}
      <div className="p-3.5 rounded-xl card-bg border space-y-2 font-sans">
        <div className="flex items-center justify-between">
          <span className="font-semibold dark:text-slate-200 text-rose-950 text-xs flex items-center gap-1.5">
            <Code2 className="w-3.5 h-3.5 dark:text-sienna-400 text-softrose-500" />
            {doc.summary}
          </span>
          <span
            className={`text-[10px] font-sans px-1.5 py-0.5 rounded font-medium border ${
              isRunning
                ? 'bg-amber-500/20 text-amber-500 border-amber-500/30'
                : isError
                ? 'bg-rose-500/20 text-rose-500 border-rose-500/30'
                : 'dark:bg-emerald-500/20 bg-emerald-200/90 dark:text-emerald-400 text-emerald-950 dark:border-emerald-500/30 border-emerald-400/80'
            }`}
          >
            {isRunning ? 'Executing' : isError ? 'Failed' : 'Completed'}
          </span>
        </div>
        <p className="dark:text-slate-400 text-slate-600 text-xs leading-relaxed">{doc.description}</p>
      </div>

      {/* Input Arguments */}
      {argEntries.length > 0 && (
        <div className="space-y-2 font-sans">
          <div className="text-[10px] uppercase font-semibold dark:text-slate-400 text-slate-600 tracking-wider flex items-center gap-1.5">
            <Terminal className="w-3 h-3 dark:text-slate-400 text-slate-600" />
            <span>Arguments</span>
          </div>
          <div className="space-y-1.5">
            {argEntries.map(([key, val]) => (
              <div
                key={key}
                className="flex items-baseline gap-1.5 px-3 py-2 rounded subtle-bg border font-mono text-[11px] overflow-hidden"
              >
                <span className="dark:text-slate-400 text-slate-600 font-medium font-sans text-xs flex-shrink-0">
                  {key}:
                </span>
                <span className="dark:text-sienna-300 text-softrose-600 font-mono text-[11px] truncate">
                  {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tool Output */}
      <div className="space-y-1.5 font-sans">
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase font-semibold dark:text-slate-400 text-slate-600 tracking-wider flex items-center gap-1.5">
            <Terminal className="w-3 h-3 dark:text-sienna-400 text-softrose-500" />
            <span>Execution Output</span>
          </span>
          {toolCall.output && (
            <button
              type="button"
              onClick={() => handleCopy(toolCall.output || '')}
              className="flex items-center gap-1 text-[10px] dark:text-slate-400 text-slate-600 dark:hover:text-slate-200 hover:text-rose-950 transition-colors cursor-pointer"
            >
              {copied ? (
                <span className="dark:text-emerald-400 text-emerald-700 font-semibold">Copied</span>
              ) : (
                <>
                  <Copy className="w-3 h-3" />
                  <span>Copy</span>
                </>
              )}
            </button>
          )}
        </div>

        {toolCall.output ? (
          <div
            className={`rounded-lg p-3.5 font-mono text-[11px] whitespace-pre-wrap leading-relaxed border overflow-x-auto subtle-bg ${
              toolCall.status === 'error' || toolCall.output.startsWith('Error:')
                ? 'bg-rose-500/10 text-rose-300 border-rose-500/30'
                : 'dark:text-slate-200 text-rose-950'
            }`}
          >
            {toolCall.output}
          </div>
        ) : (
          <div className="p-4 rounded-lg subtle-bg border text-center dark:text-slate-500 text-slate-600 italic">
            {toolCall.status === 'running'
              ? 'Waiting for tool output...'
              : 'No output string returned.'}
          </div>
        )}
      </div>
    </div>
  );
};

