import { useState, useEffect } from 'react';
import { CSRF_HEADER_NAME } from '../utils/constants';

interface UseWorkspaceFetchProps {
  endpoint: string;
  queryParams: Record<string, string>;
  sessionId: string;
  csrfToken: string;
  errorMessagePrefix?: string;
  cache?: Map<string, unknown>;
  onAuthError?: () => void;
}

export const useWorkspaceFetch = <T,>({
  endpoint,
  queryParams,
  sessionId,
  csrfToken,
  errorMessagePrefix = 'Failed to fetch',
  cache,
  onAuthError,
}: UseWorkspaceFetchProps) => {
  const [fetchedData, setFetchedData] = useState<T | null>(null);
  const [isFetching, setIsFetching] = useState<boolean>(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const queryParamsString = new URLSearchParams(queryParams).toString();
  const cacheKey = `${sessionId}:${queryParams.path || queryParamsString}`;
  const isCached = cache ? cache.has(cacheKey) : false;

  useEffect(() => {
    if (isCached) return;

    const controller = new AbortController();

    const fetchData = async () => {
      setIsFetching(true);
      setFetchError(null);
      setFetchedData(null);

      try {
        const res = await fetch(`${endpoint}?${queryParamsString}`, {
          method: 'GET',
          credentials: 'same-origin',
          signal: controller.signal,
          headers: {
            [CSRF_HEADER_NAME]: csrfToken,
          },
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          if (res.status === 401 || res.status === 403 || res.status === 404) {
            onAuthError?.();
          }
          throw new Error(errData?.detail || `${errorMessagePrefix} (${res.status})`);
        }

        const json = await res.json();
        if (cache) {
          cache.set(cacheKey, json);
        }
        setFetchedData(json);
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') return;
        setFetchError(
          (err instanceof Error ? err.message : undefined) || errorMessagePrefix
        );
      } finally {
        if (!controller.signal.aborted) {
          setIsFetching(false);
        }
      }
    };

    fetchData();
    return () => controller.abort();
  }, [endpoint, queryParamsString, cacheKey, csrfToken, sessionId, errorMessagePrefix, cache, isCached, onAuthError]);

  const data = isCached ? (cache!.get(cacheKey) as T) : fetchedData;
  const isLoading = isCached ? false : isFetching;
  const error = isCached ? null : fetchError;

  return { data, isLoading, error };
};
