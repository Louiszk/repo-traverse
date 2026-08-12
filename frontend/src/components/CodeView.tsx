import React, { useState } from 'react';
import { AlertTriangle, FileCode, Code2, Folder } from 'lucide-react';
import { GridSpinner } from './GridSpinner';
import { copyToClipboard } from '../utils/exportUtils';
import { ActivePanelState } from './SidePanel';

import { useWorkspaceFetch } from '../hooks/useWorkspaceFetch';

interface CodeViewProps {
  mode: 'file' | 'symbol';
  target: string; // file_path or symbol name
  sessionId: string;
  csrfToken: string;
  onNavigate?: (state: ActivePanelState) => void;
  onAuthError?: () => void;
}

export const CodeView: React.FC<CodeViewProps> = ({
  mode,
  target,
  sessionId,
  csrfToken,
  onNavigate,
  onAuthError,
}) => {
  const [copied, setCopied] = useState<boolean>(false);

  const { data, isLoading, error } = useWorkspaceFetch<{ content: string }>({
    endpoint: mode === 'file' ? '/api/file' : '/api/symbol',
    queryParams: { session_id: sessionId, [mode === 'file' ? 'file_path' : 'symbol']: target },
    sessionId,
    csrfToken,
    errorMessagePrefix: `Unable to load ${mode === 'file' ? 'file content' : 'symbol definition'}.`,
    onAuthError,
  });

  const content = data?.content ?? null;

  const handleCopy = async () => {
    if (!content) return;
    const ok = await copyToClipboard(content);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const isFile = mode === 'file';

  return (
    <div className="space-y-3 flex-1 flex flex-col font-mono text-xs min-h-0">
      {isLoading ? (
        <div className="py-12 flex flex-col items-center justify-center space-y-3 text-slate-400">
          <GridSpinner size="md" />
          <span className="text-xs font-mono">
            {isFile ? 'Loading repository file...' : 'Retrieving symbol definition...'}
          </span>
        </div>
      ) : error ? (
        <div className="p-4 rounded-xl card-bg border dark:border-rose-900/40 border-rose-300/80 text-rose-300 space-y-2 font-sans">
          <div className="flex items-center gap-2 font-semibold text-rose-400">
            <AlertTriangle className="w-4 h-4" />
            <span>{isFile ? 'Unable to read file' : 'Unable to read symbol'}</span>
          </div>
          <p className="text-xs leading-relaxed opacity-90">{error}</p>
        </div>
      ) : content !== null ? (
        <div className="rounded-lg overflow-hidden border subtle-bg flex-1 flex flex-col min-h-0">
          <div className="px-4 py-2 card-bg border-b flex items-center justify-between text-xs text-slate-400 font-mono flex-shrink-0">
            <span className="flex items-center gap-1.5 dark:text-sienna-300 text-softrose-600 truncate max-w-[220px]">
              {isFile ? (
                <FileCode className="w-3.5 h-3.5 dark:text-sienna-400 text-softrose-500 flex-shrink-0" />
              ) : (
                <Code2 className="w-3.5 h-3.5 dark:text-sienna-400 text-softrose-500 flex-shrink-0" />
              )}
              <span className="truncate">{target}</span>
            </span>

            <div className="flex items-center gap-2">
              {isFile && (
                <button
                  type="button"
                  onClick={() => {
                    const parts = target.replace(/^\/+|\/+$/g, '').split('/');
                    const parentPath = parts.slice(0, -1).join('/');
                    onNavigate?.({ type: 'tree', path: parentPath });
                  }}
                  className="flex items-center gap-1 text-[11px] text-slate-400 dark:hover:text-slate-200 hover:text-slate-900 transition-colors cursor-pointer"
                  title="Open containing directory in tree explorer"
                >
                  <Folder className="w-3 h-3 dark:text-sienna-400 text-softrose-500 flex-shrink-0" />
                  <span>Reveal</span>
                </button>
              )}

              <button
                type="button"
                onClick={handleCopy}
                className="dark:text-slate-400 text-slate-600 dark:hover:text-slate-200 hover:text-rose-950 transition-colors cursor-pointer text-[11px]"
              >
                {copied ? (
                  <span className="dark:text-emerald-400 text-emerald-700 font-semibold">Copied</span>
                ) : (
                  'Copy'
                )}
              </button>
            </div>
          </div>

          <pre className="p-4 font-mono text-xs dark:text-slate-200 text-rose-950 overflow-auto flex-1 min-h-0 leading-relaxed">
            <code>{content}</code>
          </pre>
        </div>
      ) : null}
    </div>
  );
};

