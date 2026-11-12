"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type RequestOptions } from "./api";
import { useAuth } from "./auth";
import type { Paginated } from "./types";

/** GET a resource; refetches when the path, params or selected branch change. */
export function useApi<T>(path: string | null, params?: RequestOptions["params"]) {
  const { branch } = useAuth();
  const [state, setState] = useState<{ data: T | null; error: string | null; settled: string | null }>({
    data: null,
    error: null,
    settled: null,
  });
  const [version, setVersion] = useState(0);
  const key = JSON.stringify(params ?? {});
  const request = path ? `${path}|${key}|${branch?.id}|${version}` : null;
  const latest = useRef<string | null>(null);

  useEffect(() => {
    latest.current = request;
    if (!path || !request) return;
    api<T>(path, { params: JSON.parse(key) })
      .then((data) => {
        // Ignore answers to requests that a newer one has superseded.
        if (latest.current === request) setState({ data, error: null, settled: request });
      })
      .catch((e: ApiError) => {
        if (latest.current === request) setState((previous) => ({ ...previous, error: e.message, settled: request }));
      });
  }, [path, key, request]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  const active = path !== null;
  return {
    data: active ? state.data : null,
    error: active ? state.error : null,
    loading: active && state.settled !== request,
    reload,
  };
}

export function useList<T>(path: string | null, params?: RequestOptions["params"]) {
  const result = useApi<Paginated<T> | T[]>(path, params);
  const rows = Array.isArray(result.data) ? result.data : (result.data?.results ?? []);
  const count = Array.isArray(result.data) ? result.data.length : (result.data?.count ?? 0);
  return { ...result, rows, count };
}

/**
 * Keyboard shortcuts for the whole page. The handler is kept in a ref, so the listener is
 * registered once and still sees the latest state when a key is actually pressed.
 */
export function useGlobalKeys(handler: (event: KeyboardEvent) => void) {
  const latest = useRef(handler);
  useEffect(() => {
    latest.current = handler;
  });
  useEffect(() => {
    const listener = (event: KeyboardEvent) => latest.current(event);
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);
}

export function useDebounced<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/** Run a mutation with busy and error state. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async <T,>(action: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, run, setError };
}
