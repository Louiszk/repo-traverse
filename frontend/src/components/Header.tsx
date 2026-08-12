import React from 'react';
import { Sun, Moon } from 'lucide-react';
import githubIcon from '../assets/github.svg';

interface HeaderProps {
  currentRepo?: string;
  sessionId?: string;
  onResetRepo?: () => void;
  darkMode: boolean;
  onToggleDarkMode: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  currentRepo,
  sessionId,
  onResetRepo,
  darkMode,
  onToggleDarkMode,
}) => {
  return (
    <header className="panel-bg border-b px-6 py-4 sticky top-0 z-50 transition-colors">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight dark:text-slate-100 text-rose-950">
            Repo<span className="dark:text-sienna-400 text-softrose-500">Traverse</span>
          </h1>
          <p className="text-xs text-slate-400 font-normal">Codebase Knowledge Graph & Agent</p>
        </div>

        <div className="flex items-center gap-4">
          {sessionId && currentRepo && (
            <div className="hidden sm:flex items-center gap-3 px-3 py-1.5 rounded subtle-bg border text-xs">
              <div className="flex items-center gap-1.5 dark:text-slate-300 text-rose-900">
                <img src={githubIcon} className="w-3.5 h-3.5 dark:invert dark:opacity-90 opacity-80" alt="GitHub" />
                <span className="font-mono truncate max-w-[200px]">
                  {currentRepo.replace(/^https?:\/\/github\.com\//, '')}
                </span>
              </div>
              <span className="text-slate-400">|</span>
              <span className="font-mono dark:text-sienna-400 text-softrose-500 font-medium">
                ID: {(sessionId || '').slice(0, 12)}
              </span>
              {onResetRepo && (
                <button
                  type="button"
                  onClick={onResetRepo}
                  className="ml-2 text-slate-400 dark:hover:text-sienna-400 hover:text-softrose-500 transition-colors underline underline-offset-2 text-[11px]"
                >
                  Change Repo
                </button>
              )}
            </div>
          )}

          <button
            type="button"
            onClick={onToggleDarkMode}
            className="px-3 py-1.5 rounded border font-medium flex items-center gap-1.5 transition-all text-xs dark:bg-rose-950/30 dark:border-rose-900/40 dark:text-rose-200 dark:hover:bg-rose-900/40 bg-rose-100/70 border-rose-300/80 text-rose-950 hover:bg-rose-200/70 cursor-pointer"
            title={darkMode ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
          >
            {darkMode ? (
              <>
                <Sun className="w-3.5 h-3.5 text-amber-400" />
                <span>Light Mode</span>
              </>
            ) : (
              <>
                <Moon className="w-3.5 h-3.5 text-softrose-600" />
                <span>Dark Mode</span>
              </>
            )}
          </button>
        </div>
      </div>
    </header>
  );
};

