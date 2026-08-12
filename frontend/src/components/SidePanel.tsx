import React, { useState, useEffect, useRef } from 'react';
import { X, FileCode, Wrench, FolderTree, Code2, ArrowLeft } from 'lucide-react';
import { ToolCall } from '../types';
import { CodeView } from './CodeView';
import { TreeView } from './TreeView';
import { ToolView } from './ToolView';

export interface TreeItem {
  name: string;
  path: string;
  is_dir: boolean;
}

export type ActivePanelState =
  | { type: 'file'; path: string }
  | { type: 'tool'; call: ToolCall }
  | { type: 'tree'; path: string }
  | { type: 'symbol'; symbol: string }
  | null;

interface SidePanelProps {
  activePanel: ActivePanelState;
  sessionId: string;
  csrfToken: string;
  repoName?: string;
  onClose: () => void;
  onNavigate?: (state: ActivePanelState) => void;
  onAuthError?: () => void;
}

export const SidePanel: React.FC<SidePanelProps> = ({
  activePanel,
  sessionId,
  csrfToken,
  repoName,
  onClose,
  onNavigate,
  onAuthError,
}) => {
  const [history, setHistory] = useState<ActivePanelState[]>([]);
  const prevPanelRef = useRef<ActivePanelState>(activePanel);

  // Maintain stack history when panel state transitions
  useEffect(() => {
    if (!activePanel) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setHistory([]);
      prevPanelRef.current = null;
      return;
    }

    if (
      prevPanelRef.current &&
      JSON.stringify(prevPanelRef.current) !== JSON.stringify(activePanel)
    ) {
      setHistory((prev) => [...prev, prevPanelRef.current!]);
    }
    prevPanelRef.current = activePanel;
  }, [activePanel]);

  if (!activePanel) return null;

  const handleBack = () => {
    if (history.length === 0) return;
    const previousState = history[history.length - 1];
    setHistory((prev) => prev.slice(0, -1));
    prevPanelRef.current = previousState;
    if (onNavigate) onNavigate(previousState);
  };

  const getHeaderInfo = () => {
    switch (activePanel.type) {
      case 'file':
        return {
          icon: <FileCode className="w-4 h-4 dark:text-sienna-400 text-softrose-500" />,
          title: activePanel.path,
          subtitle: 'File Viewer',
        };
      case 'tool':
        return {
          icon: <Wrench className="w-4 h-4 dark:text-sienna-400 text-softrose-500" />,
          title: activePanel.call.name,
          subtitle: 'Tool Inspector',
        };
      case 'tree':
        return {
          icon: <FolderTree className="w-4 h-4 dark:text-sienna-400 text-softrose-500" />,
          title: activePanel.path.replace(/^\/+|\/+$/g, '') || repoName || 'repo',
          subtitle: 'Directory Explorer',
        };
      case 'symbol':
        return {
          icon: <Code2 className="w-4 h-4 dark:text-sienna-400 text-softrose-500" />,
          title: activePanel.symbol,
          subtitle: 'Symbol Inspector',
        };
    }
  };

  const header = getHeaderInfo();

  return (
    <div className="h-full flex-1 flex flex-col panel-bg border-0 lg:border-l min-h-0 overflow-hidden transition-colors">
      {/* Side Panel Header */}
      <div className="px-6 py-3 subtle-bg border-b flex items-center justify-between flex-shrink-0 text-xs">
        <div className="flex items-center gap-3 min-w-0 pr-2">
          {header.icon}
          <div className="flex flex-col min-w-0">
            <div className="flex items-center gap-2 min-w-0">
              <span className="font-semibold dark:text-slate-100 text-rose-950 flex-shrink-0">
                {header.subtitle}
              </span>
              {header.title && (
                <>
                  <span className="text-slate-400 flex-shrink-0">&bull;</span>
                  <span className="font-mono text-[11px] dark:text-sienna-400 text-softrose-500 truncate">
                    {header.title}
                  </span>
                </>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            type="button"
            onClick={handleBack}
            disabled={history.length === 0}
            className="px-2.5 py-1 rounded card-bg dark:text-slate-300 text-rose-950 dark:hover:text-white hover:text-rose-950 border transition-colors flex items-center gap-1 text-[11px] cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            title={history.length > 0 ? "Back to previous view" : "No previous view"}
          >
            <ArrowLeft className="w-3 h-3" />
            <span>Back</span>
          </button>

          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded card-bg dark:text-slate-400 text-slate-600 dark:hover:text-slate-200 hover:text-rose-950 transition-colors border cursor-pointer"
            title="Close side panel"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Content Body */}
      <div className="flex-1 overflow-y-auto p-4 font-mono text-xs min-h-0">
        {activePanel.type === 'tool' && <ToolView toolCall={activePanel.call} />}
        {activePanel.type === 'file' && (
          <CodeView
            mode="file"
            target={activePanel.path}
            sessionId={sessionId}
            csrfToken={csrfToken}
            onNavigate={onNavigate}
            onAuthError={onAuthError}
          />
        )}
        {activePanel.type === 'symbol' && (
          <CodeView
            mode="symbol"
            target={activePanel.symbol}
            sessionId={sessionId}
            csrfToken={csrfToken}
            onNavigate={onNavigate}
            onAuthError={onAuthError}
          />
        )}
        {activePanel.type === 'tree' && (
          <TreeView
            currentPath={activePanel.path}
            sessionId={sessionId}
            csrfToken={csrfToken}
            repoName={repoName}
            onNavigate={onNavigate}
            onAuthError={onAuthError}
          />
        )}
      </div>
    </div>
  );
};

