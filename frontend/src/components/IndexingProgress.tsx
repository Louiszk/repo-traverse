import React from 'react';
import { Loader2, CheckCircle2, Code2 } from 'lucide-react';

interface IndexingProgressProps {
  stage?: string | null;
}

export const IndexingProgress: React.FC<IndexingProgressProps> = ({ stage }) => {
  const currentStage = stage || 'cloning';

  return (
    <div className="mt-8 pt-6 border-t border-slate-700/30 space-y-4">
      <div>
        <h4 className="text-sm font-semibold dark:text-slate-100 text-rose-950">
          Indexing Repository Codebase
        </h4>
          <p className="text-xs dark:text-sienna-400 text-softrose-500 font-mono">
            {currentStage === 'cloning' && 'Cloning Repository via Git...'}
            {currentStage === 'indexing' && 'Parsing module AST nodes & dependencies...'}
            {currentStage === 'finalizing' && 'Finalizing session graph artifacts...'}
            {currentStage !== 'cloning' && currentStage !== 'indexing' && currentStage !== 'finalizing' && 'Processing codebase structure...'}
          </p>
        </div>

      <div className="w-full card-bg rounded-full h-2 overflow-hidden border">
        <div
          className="dark:bg-sienna-400 bg-softrose-500 h-full rounded-full transition-all duration-500"
          style={{
            width:
              currentStage === 'cloning'
                ? '33%'
                : currentStage === 'indexing'
                ? '66%'
                : '95%',
          }}
        />
      </div>

      <div className="grid grid-cols-3 gap-2 pt-1 text-[11px]">
        <div
          className={`flex items-center gap-1.5 ${
            currentStage === 'cloning'
              ? 'dark:text-sienna-300 text-softrose-600 font-medium animate-pulse'
              : 'dark:text-emerald-400 text-emerald-700'
          }`}
        >
          {currentStage === 'cloning' ? (
            <Loader2 className="w-3 h-3 animate-spin dark:text-sienna-400 text-softrose-500" />
          ) : (
            <CheckCircle2 className="w-3 h-3 dark:text-emerald-400 text-emerald-700" />
          )}
          <span>1. Git Clone</span>
        </div>
        <div
          className={`flex items-center gap-1.5 ${
            currentStage === 'indexing'
              ? 'dark:text-sienna-300 text-softrose-600 font-medium animate-pulse'
              : currentStage === 'finalizing'
              ? 'dark:text-emerald-400 text-emerald-700'
              : 'dark:text-slate-400 text-slate-600'
          }`}
        >
          {currentStage === 'indexing' ? (
            <Loader2 className="w-3 h-3 animate-spin dark:text-sienna-400 text-softrose-500" />
          ) : currentStage === 'finalizing' ? (
            <CheckCircle2 className="w-3 h-3 dark:text-emerald-400 text-emerald-700" />
          ) : (
            <Code2 className="w-3 h-3 dark:text-slate-400 text-slate-600" />
          )}
          <span>2. CBM Indexing</span>
        </div>
        <div
          className={`flex items-center gap-1.5 ${
            currentStage === 'finalizing'
              ? 'dark:text-sienna-300 text-softrose-600 font-medium animate-pulse'
              : 'text-slate-400'
          }`}
        >
          {currentStage === 'finalizing' ? (
            <Loader2 className="w-3 h-3 animate-spin dark:text-sienna-400 text-softrose-500" />
          ) : (
            <Code2 className="w-3 h-3 text-slate-400" />
          )}
          <span>3. Finalize</span>
        </div>
      </div>
    </div>
  );
};

