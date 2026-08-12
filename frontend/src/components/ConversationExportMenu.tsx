import React, { useRef, useState } from 'react';
import { useOnClickOutside } from '../hooks/useOnClickOutside';
import { Check, ChevronDown, Download, FileCode, FileText, Share2 } from 'lucide-react';
import { Message } from '../types';
import {
  copyToClipboard,
  downloadFile,
  formatConversationAsMarkdown,
  formatConversationAsText,
} from '../utils/exportUtils';

interface ConversationExportMenuProps {
  messages: Message[];
  repoName: string;
  sessionId: string;
}

type ExportFormat = 'markdown' | 'text';

export const ConversationExportMenu: React.FC<ConversationExportMenuProps> = ({
  messages,
  repoName,
  sessionId,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useOnClickOutside(menuRef, () => setIsOpen(false));

  const getExportContent = (format: ExportFormat) =>
    format === 'markdown'
      ? formatConversationAsMarkdown(messages, repoName, sessionId)
      : formatConversationAsText(messages, repoName, sessionId);

  const handleCopy = async (format: ExportFormat) => {
    const success = await copyToClipboard(getExportContent(format));
    if (success) {
      setFeedback(format === 'markdown' ? 'Copied Markdown!' : 'Copied Text!');
      setTimeout(() => {
        setFeedback(null);
        setIsOpen(false);
      }, 1500);
    }
  };

  const handleDownload = (format: ExportFormat) => {
    const safeRepo = (repoName || 'repo').replace(/[^a-zA-Z0-9_-]/g, '_');
    const timestamp = new Date().toISOString().slice(0, 10);
    const ext = format === 'markdown' ? 'md' : 'txt';
    const mimeType = format === 'markdown' ? 'text/markdown' : 'text/plain';

    downloadFile(`codebase-qa-${safeRepo}-${timestamp}.${ext}`, getExportContent(format), mimeType);
    setIsOpen(false);
  };

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="px-3 py-1.5 rounded card-bg border dark:text-slate-300 text-rose-950 dark:hover:text-white hover:text-rose-950 text-xs flex items-center gap-1.5 font-medium transition-colors cursor-pointer"
        title="Export or copy conversation"
      >
        <Share2 className="w-3.5 h-3.5 dark:text-sienna-400 text-softrose-500" />
        <span>Export</span>
        <ChevronDown className="w-3 h-3 opacity-70" />
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-52 rounded-xl panel-bg border shadow-2xl z-50 py-1 text-xs">
          <div className="px-3 py-1.5 border-b border-slate-700/30 text-[10px] uppercase font-semibold dark:text-slate-400 text-slate-600">
            Export Conversation
          </div>

          <button
            type="button"
            onClick={() => handleCopy('markdown')}
            className="w-full px-3 py-2 text-left hover:bg-slate-800/40 dark:text-slate-200 text-rose-950 flex items-center justify-between transition-colors"
          >
            <div className="flex items-center gap-2">
              <FileCode className="w-3.5 h-3.5 dark:text-sienna-400 text-softrose-500" />
              <span>Copy as Markdown</span>
            </div>
            {feedback === 'Copied Markdown!' && (
              <Check className="w-3.5 h-3.5 dark:text-emerald-400 text-emerald-700" />
            )}
          </button>

          <button
            type="button"
            onClick={() => handleCopy('text')}
            className="w-full px-3 py-2 text-left hover:bg-slate-800/40 dark:text-slate-200 text-rose-950 flex items-center justify-between transition-colors"
          >
            <div className="flex items-center gap-2">
              <FileText className="w-3.5 h-3.5 dark:text-slate-400 text-slate-600" />
              <span>Copy as Plain Text</span>
            </div>
            {feedback === 'Copied Text!' && (
              <Check className="w-3.5 h-3.5 dark:text-emerald-400 text-emerald-700" />
            )}
          </button>

          <div className="my-1 border-t border-slate-700/30" />

          <button
            type="button"
            onClick={() => handleDownload('markdown')}
            className="w-full px-3 py-2 text-left hover:bg-slate-800/40 dark:text-slate-200 text-rose-950 flex items-center gap-2 transition-colors"
          >
            <Download className="w-3.5 h-3.5 dark:text-sienna-400 text-softrose-500" />
            <span>Download Markdown (.md)</span>
          </button>

          <button
            type="button"
            onClick={() => handleDownload('text')}
            className="w-full px-3 py-2 text-left hover:bg-slate-800/40 dark:text-slate-200 text-rose-950 flex items-center gap-2 transition-colors"
          >
            <Download className="w-3.5 h-3.5 dark:text-slate-400 text-slate-600" />
            <span>Download Text (.txt)</span>
          </button>
        </div>
      )}
    </div>
  );
};
