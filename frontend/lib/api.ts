import type { User } from "./types";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
const BASE = `${API_URL}/api/v1`;
const KEYS = { access: "medipos.access", refresh: "medipos.refresh", branch: "medipos.branch" };

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
    public fields?: Record<string, unknown>,
  ) {
    super(message);
  }
}

const store = {
  get: (key: string) => (typeof window === "undefined" ? null : window.localStorage.getItem(key)),
  set: (key: string, value: string) => window.localStorage.setItem(key, value),
  remove: (key: string) => window.localStorage.removeItem(key),
};

export const session = {
  hasToken: () => Boolean(store.get(KEYS.refresh)),
  branchId: () => store.get(KEYS.branch),
  setBranch: (id: number) => store.set(KEYS.branch, String(id)),
  save(access: string, refresh?: string) {
    store.set(KEYS.access, access);
    if (refresh) store.set(KEYS.refresh, refresh);
  },
  clear() {
    Object.values(KEYS).forEach(store.remove);
  },
};

function describe(body: unknown): string {
  if (typeof body === "string") return body;
  if (Array.isArray(body)) return body.map(describe).join(" ");
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    if (typeof record.detail === "string") return record.detail;
    return Object.entries(record)
      .map(([field, value]) => (field === "non_field_errors" ? describe(value) : `${field}: ${describe(value)}`))
      .join(" · ");
  }
  return "Something went wrong.";
}

let refreshing: Promise<boolean> | null = null;

async function refreshAccess(): Promise<boolean> {
  const refresh = store.get(KEYS.refresh);
  if (!refresh) return false;
  // One refresh at a time: the server rotates refresh tokens, so parallel refreshes would invalidate each other.
  refreshing ??= fetch(`${BASE}/auth/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  })
    .then(async (response) => {
      if (!response.ok) return false;
      const data = await response.json();
      session.save(data.access, data.refresh);
      return true;
    })
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  params?: Record<string, string | number | boolean | null | undefined>;
  idempotencyKey?: string;
  raw?: boolean;
}

export async function api<T = unknown>(path: string, options: RequestOptions = {}, retry = true): Promise<T> {
  const url = new URL(`${BASE}${path}`);
  for (const [key, value] of Object.entries(options.params ?? {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
  }
  const headers: Record<string, string> = {};
  const access = store.get(KEYS.access);
  const branch = store.get(KEYS.branch);
  if (access) headers.Authorization = `Bearer ${access}`;
  if (branch) headers["X-Branch-Id"] = branch;
  if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;
  let body: BodyInit | undefined;
  if (options.body instanceof FormData) body = options.body;
  else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(url, { method: options.method ?? (body ? "POST" : "GET"), headers, body });
  } catch {
    throw new ApiError("Cannot reach the server. Check your connection.", 0);
  }
  if (response.status === 401 && retry && !path.startsWith("/auth/login") && (await refreshAccess())) {
    return api<T>(path, options, false);
  }
  if (response.status === 401 && !path.startsWith("/auth/login")) {
    session.clear();
    // A full page load on purpose: it drops every piece of in-memory state of the signed-out user.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    if (typeof window !== "undefined") window.location.assign("/login");
  }
  if (options.raw && response.ok) return response as T;
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let data: unknown = text;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    /* not JSON */
  }
  if (!response.ok) {
    const record = data && typeof data === "object" ? (data as Record<string, unknown>) : undefined;
    throw new ApiError(describe(data), response.status, record?.code as string | undefined, record);
  }
  return data as T;
}

export async function login(username: string, password: string): Promise<User> {
  const data = await api<{ access: string; refresh: string; user: User }>("/auth/login/", { body: { username, password } });
  session.save(data.access, data.refresh);
  return data.user;
}

export async function logout() {
  const refresh = store.get(KEYS.refresh);
  try {
    if (refresh) await api("/auth/logout/", { body: { refresh } });
  } finally {
    session.clear();
  }
}

/** Download a CSV export through the authenticated client. */
export async function download(path: string, params: RequestOptions["params"], filename: string) {
  const response = await api<Response>(path, { params: { ...params, export: "csv" }, raw: true });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(await response.blob());
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

export const newKey = () => crypto.randomUUID();
