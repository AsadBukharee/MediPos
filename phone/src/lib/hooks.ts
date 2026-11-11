import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError, cachedGet, type Params } from './api';
import { useAuth } from './auth';

interface Resource<T> {
  data: T | null;
  error: string | null;
  stale: boolean;
  savedAt?: number;
  settled: string | null;
}

/** Load a GET resource, falling back to the offline copy when the server is unreachable. */
export function useResource<T>(path: string | null, params?: Params) {
  const { branch } = useAuth();
  const [state, setState] = useState<Resource<T>>({ data: null, error: null, stale: false, settled: null });
  const [version, setVersion] = useState(0);
  const key = JSON.stringify(params ?? {});
  const request = path ? `${path}|${key}|${branch?.id}|${version}` : null;
  const latest = useRef<string | null>(null);

  useEffect(() => {
    latest.current = request;
    if (!path || !request) return;
    cachedGet<T>(path, JSON.parse(key))
      .then((result) => {
        if (latest.current === request) setState({ ...result, error: null, settled: request });
      })
      .catch((error: ApiError) => {
        if (latest.current === request) setState((previous) => ({ ...previous, error: error.message, settled: request }));
      });
  }, [path, key, request]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { ...state, loading: path !== null && state.settled !== request, reload };
}

export function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async <T,>(action: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.');
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, run };
}

export const formatMoney = (value: string | number | null | undefined) =>
  Number(value ?? 0).toLocaleString('en-PK', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function formatDate(value: string | null | undefined) {
  if (!value) return '—';
  return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

export function daysUntil(value: string) {
  return Math.ceil((new Date(value).getTime() - Date.now()) / 86_400_000);
}
