import { useState, useRef, useEffect } from 'react';
import { RepoErrorDetail, IndexStatusResponse } from '../types';

interface UseRepoIndexerProps {
  onSuccess: (url: string, sessionId: string, csrfToken: string) => void;
  onContextFullReset: () => void;
}

export const useRepoIndexer = ({ onSuccess, onContextFullReset }: UseRepoIndexerProps) => {
  const [isLoadingRepo, setIsLoadingRepo] = useState<boolean>(false);
  const [indexingStage, setIndexingStage] = useState<string | null>(null);
  const [repoError, setRepoError] = useState<RepoErrorDetail | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  };

  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, []);

  const handleIndexRepo = async (url: string) => {
    setIsLoadingRepo(true);
    setRepoError(null);
    setIndexingStage('cloning');
    onContextFullReset();
    stopPolling();

    try {
      const response = await fetch('/api/index-repo', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ github_url: url }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        if (typeof errorData?.detail === 'object' && errorData?.detail !== null) {
          setRepoError({
            message: errorData.detail.message || 'Failed to index repository.',
            reason: errorData.detail.reason || undefined,
          });
        } else if (typeof errorData?.detail === 'string') {
          setRepoError({ message: errorData.detail });
        } else {
          setRepoError({ message: `HTTP error! status: ${response.status}` });
        }
        return;
      }

      const data = await response.json();
      const taskId = data?.task_id;
      const newSessionId = data?.session_id;
      const receivedCsrfToken = data?.csrf_token || '';

      if (!taskId || !newSessionId) {
        setRepoError({ message: 'Invalid server response: missing task ID or session ID.' });
        return;
      }

      await new Promise<void>((resolve, reject) => {
        pollIntervalRef.current = setInterval(async () => {
          try {
            const statusRes = await fetch(`/api/index-status/${taskId}`, {
              credentials: 'same-origin',
            });
            if (!statusRes.ok) {
              const errBody = await statusRes.json().catch(() => ({}));
              stopPolling();
              if (typeof errBody?.detail === 'object' && errBody?.detail !== null) {
                setRepoError({
                  message: errBody.detail.message || `Status check failed (${statusRes.status})`,
                  reason: errBody.detail.reason || undefined,
                });
              } else {
                setRepoError({
                  message: typeof errBody?.detail === 'string' ? errBody.detail : `Status check failed (${statusRes.status})`,
                });
              }
              resolve();
              return;
            }

            const statusData: IndexStatusResponse = await statusRes.json();

            if (statusData.stage) {
              setIndexingStage(statusData.stage);
            }

            if (statusData.status === 'SUCCESS') {
              stopPolling();
              onSuccess(url, statusData.session_id || newSessionId, receivedCsrfToken);
              resolve();
            } else if (statusData.status === 'FAILURE') {
              stopPolling();
              if (typeof statusData.detail === 'object' && statusData.detail !== null) {
                const detailObj = statusData.detail as RepoErrorDetail;
                setRepoError({
                  message: detailObj.message || 'Indexing task failed on worker.',
                  reason: detailObj.reason || undefined,
                });
              } else {
                setRepoError({
                  message: statusData.detail || 'Indexing task failed on worker.',
                });
              }
              resolve();
            }
          } catch (pollErr) {
            stopPolling();
            reject(pollErr);
          }
        }, 1500);
      });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Failed to index repository. Please check backend status.';
      setRepoError({ message: errMsg });
    } finally {
      setIsLoadingRepo(false);
      setIndexingStage(null);
    }
  };

  const resetIndexer = () => {
    stopPolling();
    setIsLoadingRepo(false);
    setIndexingStage(null);
    setRepoError(null);
  };

  return { handleIndexRepo, isLoadingRepo, indexingStage, repoError, setRepoError, stopPolling, resetIndexer };
};
