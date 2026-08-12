import React, { useEffect } from 'react';
import {
  Folder,
  ChevronRight,
  CornerLeftUp,
  FileCode,
  AlertTriangle,
} from 'lucide-react';
import { GridSpinner } from './GridSpinner';
import { ActivePanelState, TreeItem } from './SidePanel';
import { useWorkspaceFetch } from '../hooks/useWorkspaceFetch';

// Module-level cache map for directory contents per session
const treeSessionCache = new Map<string, TreeItem[]>();

interface TreeViewProps {
  currentPath: string;
  sessionId: string;
  csrfToken: string;
  repoName?: string;
  onNavigate?: (state: ActivePanelState) => void;
  onAuthError?: () => void;
}

export const TreeView: React.FC<TreeViewProps> = ({
  currentPath,
  sessionId,
  csrfToken,
  repoName = 'repo',
  onNavigate,
  onAuthError,
}) => {
  useEffect(() => {
    treeSessionCache.clear();
  }, [sessionId]);

  const { data, isLoading, error } = useWorkspaceFetch<TreeItem[]>({
    endpoint: '/api/tree',
    queryParams: { session_id: sessionId, path: currentPath },
    sessionId,
    csrfToken,
    errorMessagePrefix: 'Unable to load directory structure.',
    cache: treeSessionCache,
    onAuthError,
  });

  const treeItems = data || [];

  const cleanPath = currentPath.replace(/^\/+|\/+$/g, '');
  const parts = cleanPath ? cleanPath.split('/') : [];

  return (
    <div className="space-y-2">
      {/* Breadcrumb Navigation Bar */}
      <div className="flex items-center gap-1 overflow-x-auto pb-2 text-xs font-mono border-b border-slate-700/30">
        <button
          type="button"
          onClick={() => onNavigate?.({ type: 'tree', path: '' })}
          className={`px-1.5 py-0.5 rounded hover:bg-slate-800/40 transition-colors flex items-center gap-1 flex-shrink-0 cursor-pointer ${
            parts.length === 0
              ? 'dark:text-sienna-300 text-softrose-600 font-semibold card-bg border dark:border-sienna-400/30 border-softrose-500/30'
              : 'dark:text-slate-400 text-slate-600 dark:hover:text-slate-200 hover:text-rose-950'
          }`}
          title="Root repository directory"
        >
          <Folder className="w-3.5 h-3.5 dark:text-sienna-400 text-softrose-500" />
          <span className="truncate max-w-[140px]">{repoName}</span>
        </button>

        {parts.map((part, index) => {
          const partPath = parts.slice(0, index + 1).join('/');
          const isLast = index === parts.length - 1;
          return (
            <React.Fragment key={partPath}>
              <ChevronRight className="w-3 h-3 text-slate-500 flex-shrink-0" />
              <button
                type="button"
                onClick={() => onNavigate?.({ type: 'tree', path: partPath })}
                className={`px-1.5 py-0.5 rounded hover:bg-slate-800/40 transition-colors truncate max-w-[120px] flex-shrink-0 cursor-pointer ${
                  isLast
                    ? 'dark:text-sienna-300 text-softrose-600 font-semibold card-bg border dark:border-sienna-400/30 border-softrose-500/30'
                    : 'dark:text-slate-400 text-slate-600 dark:hover:text-slate-200 hover:text-rose-950'
                }`}
                title={partPath}
              >
                {part}
              </button>
            </React.Fragment>
          );
        })}
      </div>

      {/* Directory Title Banner */}
      <div className="dark:text-slate-400 text-slate-600 font-semibold px-1 py-1 text-[11px] uppercase tracking-wider">
        {cleanPath ? `${cleanPath} /` : `${repoName} /`}
      </div>

      {/* Main Directory Tree List */}
      {isLoading ? (
        <div className="p-8 flex flex-col items-center justify-center space-y-3 font-mono text-xs text-slate-400">
          <GridSpinner size="md" />
          <span>Fetching directory items...</span>
        </div>
      ) : error ? (
        <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      ) : (
        <div className="space-y-1">
          {parts.length > 0 && (
            <button
              type="button"
              onClick={() => {
                const parentPath = parts.slice(0, -1).join('/');
                onNavigate?.({ type: 'tree', path: parentPath });
              }}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded card-bg dark:text-slate-400 text-slate-600 dark:hover:text-slate-200 hover:text-rose-950 transition-colors text-left border cursor-pointer"
            >
              <CornerLeftUp className="w-4 h-4 dark:text-sienna-400 text-softrose-500 flex-shrink-0" />
              <span className="font-mono text-xs font-medium">..</span>
            </button>
          )}

          {treeItems.length === 0 ? (
            <div className="p-6 text-center dark:text-slate-500 text-slate-600 italic font-mono text-xs">
              This directory is empty.
            </div>
          ) : (
            treeItems.map((item) => (
              <button
                key={item.path}
                type="button"
                onClick={() =>
                  item.is_dir
                    ? onNavigate?.({ type: 'tree', path: item.path })
                    : onNavigate?.({ type: 'file', path: item.path })
                }
                className={`w-full flex items-center justify-between px-2 py-1.5 rounded transition-all text-left group cursor-pointer ${
                  item.is_dir
                    ? 'card-bg dark:text-sienna-300 text-softrose-600 font-medium border dark:border-sienna-400/30 border-softrose-500/30'
                    : 'hover:bg-slate-800/40 dark:text-slate-300 text-rose-950 dark:hover:text-white hover:text-rose-950 border border-transparent'
                }`}
              >
                <div className="flex items-center gap-2 min-w-0 pr-2">
                  {item.is_dir ? (
                    <Folder className="w-4 h-4 dark:text-sienna-400 text-softrose-500 flex-shrink-0 group-hover:scale-105 transition-transform" />
                  ) : (
                    <FileCode className="w-3.5 h-3.5 dark:text-sienna-400 text-softrose-500 flex-shrink-0 group-hover:scale-105 transition-transform" />
                  )}
                  <span className="font-mono text-xs truncate">{item.name}</span>
                </div>
                <span className="text-[10px] dark:text-slate-500 text-slate-600 font-mono group-hover:text-slate-400">
                  {item.is_dir ? 'folder' : 'file'}
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
};

