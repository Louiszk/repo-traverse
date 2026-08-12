import React from 'react';

interface FooterProps {
  onOpenLegal?: (tab: 'privacy' | 'terms') => void;
}

export const Footer: React.FC<FooterProps> = ({ onOpenLegal }) => {
  return (
    <footer className="panel-bg border-t py-4 px-4 flex-shrink-0 transition-colors">
      <div className="flex items-center justify-end gap-3 text-xs text-slate-400">
        <div className="flex items-center gap-3">
          <span>RepoTraverse</span>
          <span>&bull;</span>
        </div>

        <div className="flex items-center gap-4 text-xs font-medium">
          <a
            href="/impressum.html"
            className="dark:text-slate-400 text-slate-600 hover:dark:text-slate-200 hover:text-slate-900 transition-colors cursor-pointer"
          >
            Impressum
          </a>
          <span>&bull;</span>
          <a
            href="mailto:info@repo-tools.com"
            className="dark:text-slate-400 text-slate-600 hover:dark:text-slate-200 hover:text-slate-900 transition-colors cursor-pointer"
          >
            Contact
          </a>
          {onOpenLegal && (
            <>
              <span>&bull;</span>
              <button
                type="button"
                onClick={() => onOpenLegal('terms')}
                className="dark:text-slate-400 text-slate-600 hover:dark:text-slate-200 hover:text-slate-900 transition-colors cursor-pointer"
              >
                Terms of Service
              </button>
              <span>&bull;</span>
              <button
                type="button"
                onClick={() => onOpenLegal('privacy')}
                className="dark:text-slate-400 text-slate-600 hover:dark:text-slate-200 hover:text-slate-900 transition-colors cursor-pointer"
              >
                Privacy Policy
              </button>
            </>
          )}
        </div>
      </div>
    </footer>
  );
};



