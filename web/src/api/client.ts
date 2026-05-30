const LS_TOKEN = 'travelagent_access_token';

export function getToken(): string {
  return localStorage.getItem(LS_TOKEN) || '';
}

export function setToken(token: string): void {
  if (token) localStorage.setItem(LS_TOKEN, token);
  else localStorage.removeItem(LS_TOKEN);
}

export function authHeaders(extra?: HeadersInit): HeadersInit {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) h['Authorization'] = `Bearer ${token}`;
  return { ...h, ...(extra as Record<string, string> | undefined) };
}

export class ApiError extends Error {
  status: number;
  detail?: string;

  constructor(status: number, detail?: string) {
    super(detail || `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({} as T));
  if (!res.ok) {
    const detail =
      typeof (data as { detail?: unknown }).detail === 'string'
        ? (data as { detail: string }).detail
        : undefined;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}
