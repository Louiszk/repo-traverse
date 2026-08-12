import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw, RotateCcw } from 'lucide-react';

import { syncThemeFromStorage } from '../hooks/useTheme';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidMount() {
    this.syncTheme();
  }

  public componentDidUpdate(_prevProps: Props, prevState: State) {
    if (this.state.hasError && !prevState.hasError) {
      this.syncTheme();
    }
  }

  private syncTheme = () => {
    syncThemeFromStorage();
  };

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Detect stale Vite chunk loading failures (e.g. after new deployments)
    if (/dynamically imported module|Loading chunk|Failed to fetch dynamically/i.test(error.message)) {
      console.warn('Stale build chunk detected. Automatically reloading page...');
      window.location.reload();
      return;
    }

    console.error('Unhandled React Render Error:', error, errorInfo);
  }

  private handleSoftReset = () => {
    this.setState({ hasError: false, error: undefined });
  };

  private handleHardReload = () => {
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center p-6 antialiased font-sans transition-colors duration-200">
          <div className="panel-bg p-8 rounded-xl max-w-md w-full text-center space-y-5 shadow-sm border">
            <div className="w-12 h-12 rounded-xl card-bg border dark:border-sienna-400/30 border-softrose-500/30 dark:text-sienna-400 text-softrose-500 flex items-center justify-center mx-auto shadow-sm">
              <AlertTriangle className="w-6 h-6 animate-pulse" />
            </div>

            <div className="space-y-1">
              <h2 className="text-xl font-bold dark:text-slate-100 text-rose-950 tracking-tight">Something went wrong</h2>
              <p className="text-xs text-slate-400">
                An unexpected rendering error occurred in the application UI.
              </p>
            </div>

            {/* Display raw error detail only in DEV environment */}
            {import.meta.env.DEV && this.state.error && (
              <div className="p-3 rounded subtle-bg border dark:border-sienna-400/30 border-softrose-500/30 text-[11px] font-mono dark:text-sienna-300 text-softrose-600 text-left overflow-x-auto max-h-32">
                {this.state.error.message}
              </div>
            )}

            {/* Action Buttons: Soft Reset vs Hard Reload */}
            <div className="flex flex-col sm:flex-row items-center justify-center gap-2 pt-2">
              <button
                type="button"
                onClick={this.handleSoftReset}
                className="w-full sm:w-auto px-4 py-2 rounded accent-btn font-semibold text-xs transition-colors flex items-center justify-center gap-2 cursor-pointer"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Try Again</span>
              </button>

              <button
                type="button"
                onClick={this.handleHardReload}
                className="w-full sm:w-auto px-4 py-2 rounded accent-btn font-semibold text-xs transition-colors flex items-center justify-center gap-2 cursor-pointer"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Reload App</span>
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}


