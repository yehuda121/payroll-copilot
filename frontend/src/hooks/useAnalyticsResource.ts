import { useCallback, useEffect, useRef, useState } from 'react';
import { getDisplayError } from '../lib/getDisplayError';

export type AnalyticsResourceState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
};

/**
 * Shared fetch lifecycle for analytics dashboards.
 * Dedupes in-flight work via AbortController; callers supply the API fetcher only.
 */
export function useAnalyticsResource<T>(
  fetcher: ((signal: AbortSignal) => Promise<T>) | null,
  deps: readonly unknown[],
  fallbackError = 'Unable to load analytics.',
): AnalyticsResourceState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(Boolean(fetcher));
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const reload = useCallback(() => {
    setTick((value) => value + 1);
  }, []);

  useEffect(() => {
    const activeFetcher = fetcherRef.current;
    if (!activeFetcher) {
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    let cancelled = false;
    setLoading(true);
    setError(null);

    void activeFetcher(controller.signal)
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled || controller.signal.aborted) return;
        setError(getDisplayError(err, fallbackError));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deps provided by caller
  }, [...deps, tick, fallbackError]);

  return { data, loading, error, reload };
}
