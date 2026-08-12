import React, { useState } from 'react';
import { Loader2, ArrowRight, AlertCircle, Info } from 'lucide-react';
import { IndexingProgress } from './IndexingProgress';
import { isValidGithubUrl, normalizeGithubUrl } from '../utils/github';
import { RepoErrorDetail } from '../types';
import githubIcon from '../assets/github.svg';

interface RepoInputProps {
  onIndexRepo: (url: string) => Promise<void>;
  isLoading: boolean;
  stage?: string | null;
  error?: RepoErrorDetail | string | null;
  onOpenLegal?: (tab: 'privacy' | 'terms') => void;
}

const SAMPLE_REPOS = [
  'https://github.com/fastapi/fastapi',
  'https://github.com/pallets/flask',
  'https://github.com/psf/requests',
];

export const RepoInput: React.FC<RepoInputProps> = ({ onIndexRepo, isLoading, stage, error, onOpenLegal }) => {
  const [url, setUrl] = useState<string>('');
  const [localError, setLocalError] = useState<RepoErrorDetail | string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = url.trim();

    if (!trimmed) {
      setLocalError('Please enter a GitHub repository URL.');
      return;
    }

    if (trimmed.length > 1000) {
      setLocalError('GitHub repository URL must not exceed 1000 characters.');
      return;
    }

    if (!isValidGithubUrl(trimmed)) {
      setLocalError({
        message: 'Please provide a valid GitHub repository URL (e.g., github.com/owner/repo or https://github.com/owner/repo).',
        reason: 'URLs for specific branches, commits, or subdirectories are currently not supported.',
      });
      return;
    }

    const normalized = normalizeGithubUrl(trimmed);
    setLocalError(null);
    onIndexRepo(normalized);
  };

  const handleSelectSample = (sampleUrl: string) => {
    setUrl(sampleUrl);
    setLocalError(null);
  };

  const displayObj: RepoErrorDetail | null = localError
    ? typeof localError === 'string'
      ? { message: localError }
      : localError
    : typeof error === 'string'
    ? { message: error }
    : error || null;

  return (
    <div className="w-full flex-1 overflow-y-auto max-w-3xl mx-auto py-12 px-4">
      {/* Hero Title Header */}
      <div className="text-center mb-8 space-y-3">
        <h2 className="text-3xl sm:text-4xl font-bold tracking-tight dark:text-slate-100 text-rose-950">
          Explore Any Repository Architecture
        </h2>
        <p className="text-sm sm:text-base dark:text-slate-400 text-slate-600 max-w-xl mx-auto">
          Paste a public GitHub URL to index module hierarchies and function dependencies,
          then ask targeted questions about the architecture.
        </p>
      </div>

      {/* Main Input Form Card */}
      <div className="panel-bg p-6 sm:p-8 rounded-xl border shadow-sm relative">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="relative flex items-center">
            <div className="absolute left-4 pointer-events-none">
              <img src={githubIcon} className="w-5 h-5 dark:invert" alt="GitHub" />
            </div>

            <input
              type="text"
              name="github-repo-url"
              maxLength={1000}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                if (localError) setLocalError(null);
              }}
              disabled={isLoading}
              placeholder="https://github.com/username/repository"
              className="w-full pl-12 pr-36 py-3.5 rounded subtle-bg border text-sm font-mono dark:text-slate-100 text-rose-950 dark:placeholder-slate-400 placeholder-slate-600 focus:outline-none dark:focus:border-sienna-400 focus:border-softrose-500 transition-colors"
            />

            <button
              type="submit"
              disabled={isLoading}
              className="absolute right-2 px-5 py-2 rounded accent-btn font-semibold text-sm transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Analyzing...</span>
                </>
              ) : (
                <>
                  <span>Analyze</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>

          {/* Legal disclaimer */}
          <p className="text-[11px] text-center dark:text-slate-400 text-slate-600 leading-relaxed">
            By using RepoTraverse, you agree to our{' '}
            <button
              type="button"
              onClick={() => onOpenLegal?.('terms')}
              className="dark:text-sienna-300 text-softrose-600 underline font-medium hover:dark:text-sienna-200 hover:text-softrose-700 transition-colors cursor-pointer"
            >
              Terms of Service
            </button>{' '}
            and{' '}
            <button
              type="button"
              onClick={() => onOpenLegal?.('privacy')}
              className="dark:text-sienna-300 text-softrose-600 underline font-medium hover:dark:text-sienna-200 hover:text-softrose-700 transition-colors cursor-pointer"
            >
              Privacy Policy
            </button>
            .
          </p>

          {/* Validation Error & Explanation Banner */}
          {displayObj && (
            <div className="space-y-2">
              <div className="flex items-center gap-2.5 text-xs px-3.5 py-2.5 rounded-lg bg-rose-500/10 border border-rose-500/20 shadow-sm font-medium dark:text-rose-300 text-rose-800">
                <AlertCircle className="w-4 h-4 flex-shrink-0 text-rose-500" />
                <span>{displayObj.message}</span>
              </div>
              {displayObj.reason && (
                <div className="flex items-start gap-2.5 text-[11px] leading-relaxed px-3.5 py-2 rounded-lg bg-rose-500/5 border border-rose-500/10 font-normal dark:text-rose-300/80 text-rose-900/80">
                  <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-rose-400" />
                  <span>{displayObj.reason}</span>
                </div>
              )}
            </div>
          )}
        </form>

        {/* Loading Progress State Component */}
        {isLoading && <IndexingProgress stage={stage} />}

        {/* Quick Sample Links */}
        {!isLoading && (
          <div className="mt-6 pt-6 border-t border-slate-700/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
            <span className="dark:text-slate-400 text-slate-600 font-medium">Try a sample repository:</span>
            <div className="flex flex-wrap gap-2">
              {SAMPLE_REPOS.map((sample) => (
                <button
                  key={sample}
                  type="button"
                  onClick={() => handleSelectSample(sample)}
                  className="px-2.5 py-1 rounded card-bg dark:text-slate-300 text-rose-950 dark:hover:text-white hover:text-rose-950 border transition-colors font-mono text-[11px] cursor-pointer"
                >
                  {sample.split('/').slice(-1)[0]}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

