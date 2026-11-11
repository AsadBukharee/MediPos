import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';

const API_URL = (
  process.env.EXPO_PUBLIC_API_URL ||
  (Constants.expoConfig?.extra?.apiUrl as string | undefined) ||
  'http://10.0.2.2:8000'
).replace(/\/$/, '');
const BASE = `${API_URL}/api/v1`;
const CACHE_PREFIX = 'medipos.cache.';

// Tokens live in the device keystore (Keychain / Android Keystore), never in plain storage.
const KEYS = { access: 'medipos.access', refresh: 'medipos.refresh', branch: 'medipos.branch' };
const memory: { access: string | null; refresh: string | null; branch: string | null; onSignedOut?: () => void } = {
  access: null,
  refresh: null,
  branch: null,
};

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message);
  }
}

export const session = {
  async load() {
    [memory.access, memory.refresh, memory.branch] = await Promise.all([
      SecureStore.getItemAsync(KEYS.access),
      SecureStore.getItemAsync(KEYS.refresh),
      SecureStore.getItemAsync(KEYS.branch),
    ]);
    return Boolean(memory.refresh);
  },
  async save(access: string, refresh?: string) {
    memory.access = access;
    await SecureStore.setItemAsync(KEYS.access, access);
    if (refresh) {
      memory.refresh = refresh;
      await SecureStore.setItemAsync(KEYS.refresh, refresh);
    }
  },
  branchId: () => (memory.branch ? Number(memory.branch) : null),
  async setBranch(id: number) {
    memory.branch = String(id);
    await SecureStore.setItemAsync(KEYS.branch, memory.branch);
  },
  async clear() {
    memory.access = memory.refresh = memory.branch = null;
    await Promise.all(Object.values(KEYS).map((key) => SecureStore.deleteItemAsync(key)));
    const cached = (await AsyncStorage.getAllKeys()).filter((key) => key.startsWith(CACHE_PREFIX));
    await AsyncStorage.multiRemove(cached); // cached data belongs to the signed-out user
  },
  refreshToken: () => memory.refresh,
  onSignedOut(callback: () => void) {
    memory.onSignedOut = callback;
  },
};

function describe(body: unknown): string {
  if (typeof body === 'string') return body;
  if (Array.isArray(body)) return body.map(describe).join(' ');
  if (body && typeof body === 'object') {
    const record = body as Record<string, unknown>;
    if (typeof record.detail === 'string') return record.detail;
    return Object.entries(record)
      .map(([field, value]) => `${field}: ${describe(value)}`)
      .join(' · ');
  }
  return 'Something went wrong.';
}

let refreshing: Promise<boolean> | null = null;

function refreshAccess(): Promise<boolean> {
  if (!memory.refresh) return Promise.resolve(false);
  // One refresh at a time: refresh tokens rotate, so parallel refreshes would invalidate each other.
  refreshing ??= fetch(`${BASE}/auth/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh: memory.refresh }),
  })
    .then(async (response) => {
      if (!response.ok) return false;
      const data = await response.json();
      await session.save(data.access, data.refresh);
      return true;
    })
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

export type Params = Record<string, string | number | boolean | null | undefined>;

export interface RequestOptions {
  method?: string;
  body?: unknown;
  params?: Params;
}

function buildUrl(path: string, params?: Params): string {
  const query = Object.entries(params ?? {})
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
    .join('&');
  return `${BASE}${path}${query ? `?${query}` : ''}`;
}

export async function api<T = unknown>(path: string, options: RequestOptions = {}, retry = true): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (memory.access) headers.Authorization = `Bearer ${memory.access}`;
  if (memory.branch) headers['X-Branch-Id'] = memory.branch;
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.params), {
      method: options.method ?? (options.body !== undefined ? 'POST' : 'GET'),
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new ApiError('No connection to the server.', 0);
  }
  const isLogin = path.startsWith('/auth/login');
  if (response.status === 401 && !isLogin) {
    if (retry && (await refreshAccess())) return api<T>(path, options, false);
    await session.clear();
    memory.onSignedOut?.();
    throw new ApiError('Your session has expired. Please sign in again.', 401);
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let data: unknown = text;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    /* not JSON */
  }
  if (!response.ok) {
    const code = data && typeof data === 'object' ? ((data as Record<string, unknown>).code as string | undefined) : undefined;
    throw new ApiError(describe(data), response.status, code);
  }
  return data as T;
}

/**
 * GET with an offline, read-only fallback: the last good answer is kept on the device and shown
 * (marked as stale) when the server cannot be reached. Writes are never queued offline.
 */
export async function cachedGet<T>(path: string, params?: Params): Promise<{ data: T; stale: boolean; savedAt?: number }> {
  const key = `${CACHE_PREFIX}${memory.branch ?? '-'}.${buildUrl(path, params)}`;
  try {
    const data = await api<T>(path, { params });
    AsyncStorage.setItem(key, JSON.stringify({ savedAt: Date.now(), data })).catch(() => undefined);
    return { data, stale: false };
  } catch (error) {
    if (error instanceof ApiError && error.status === 0) {
      const saved = await AsyncStorage.getItem(key);
      if (saved) {
        const parsed = JSON.parse(saved) as { savedAt: number; data: T };
        return { data: parsed.data, stale: true, savedAt: parsed.savedAt };
      }
    }
    throw error;
  }
}
