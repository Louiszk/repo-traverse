import React, { useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Info } from 'lucide-react';
import { ToolDocInfo } from '../types';
import { TOOL_DOCS } from '../utils/constants';

interface TooltipProps {
  toolName: string;
  isRunning?: boolean;
  args?: Record<string, unknown>;
  icon?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}

export const Tooltip: React.FC<TooltipProps> = ({
  toolName,
  isRunning = false,
  icon,
  className = '',
  children,
}) => {
  const [isHovered, setIsHovered] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number; positionAbove: boolean } | null>(null);
  const triggerRef = useRef<HTMLDivElement>(null);

  const docInfo: ToolDocInfo = TOOL_DOCS[toolName] || {
    summary: 'System Tool Execution',
    description: `Executes the codebase tool '${toolName}' with parameter arguments.`,
  };

  const handleMouseEnter = () => {
    if (triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      const tooltipWidth = 320;
      const positionAbove = rect.top > 220;

      const left = Math.max(16, Math.min(rect.left, window.innerWidth - tooltipWidth - 16));
      const top = positionAbove ? rect.top - 8 : rect.bottom + 8;

      setCoords({ top, left, positionAbove });
    }
    setIsHovered(true);
  };

  const handleMouseLeave = () => {
    setIsHovered(false);
  };

  return (
    <div
      ref={triggerRef}
      className={`inline-block ${className}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {children}

      {isHovered &&
        coords &&
        createPortal(
          <div
            style={{
              position: 'fixed',
              left: `${coords.left}px`,
              top: `${coords.top}px`,
              transform: coords.positionAbove ? 'translateY(-100%)' : 'none',
              zIndex: 99999,
            }}
            className="w-80 p-3.5 rounded-xl panel-bg border shadow-2xl text-xs pointer-events-none animate-in fade-in zoom-in-95 duration-150"
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-slate-700/30 pb-2 mb-2">
              <div className="flex items-center gap-2 font-mono font-semibold dark:text-slate-100 text-rose-950">
                {icon}
                <span>{toolName}</span>
              </div>
              <span
                className={`text-[10px] font-sans px-1.5 py-0.5 rounded font-medium border ${
                  isRunning
                    ? 'bg-amber-500/20 text-amber-500 border-amber-500/30'
                    : 'dark:bg-emerald-500/20 bg-emerald-200/90 dark:text-emerald-400 text-emerald-950 dark:border-emerald-500/30 border-emerald-400/80'
                }`}
              >
                {isRunning ? 'Executing' : 'Completed'}
              </span>
            </div>

            {/* Docstring Summary & Description */}
            <div className="space-y-1">
              <div className="dark:text-slate-200 text-rose-900 font-medium text-[11px] flex items-center gap-1">
                <Info className="w-3 h-3 dark:text-sienna-400 text-softrose-500 flex-shrink-0" />
                <span>{docInfo.summary}</span>
              </div>
              <p className="text-slate-400 text-[11px] leading-relaxed font-sans pl-4">
                {docInfo.description}
              </p>
            </div>

            {/* Footer Prompt */}
            <div className="mt-2.5 pt-2 border-t border-slate-700/30 text-[10px] text-slate-400 font-sans italic text-center">
              Click to view execution details & output.
            </div>
          </div>,
          document.body
        )}
    </div>
  );
};

