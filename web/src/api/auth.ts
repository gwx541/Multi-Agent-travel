import { apiFetch, setToken } from './client';
import type { AppConfig, User } from '../types';

interface TokenResponse {
  access_token: string;
  user: User;
}

interface MeResponse {
  user: User;
}

export async function fetchConfig(): Promise<AppConfig> {
  return apiFetch<AppConfig>('/api/config');
}

export async function login(email: string, password: string): Promise<User> {
  const data = await apiFetch<TokenResponse>('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  setToken(data.access_token);
  return data.user;
}

export async function register(email: string, password: string): Promise<User> {
  const data = await apiFetch<TokenResponse>('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  setToken(data.access_token);
  return data.user;
}

export async function fetchMe(): Promise<User | null> {
  const token = localStorage.getItem('travelagent_access_token');
  if (!token) return null;
  try {
    const data = await apiFetch<MeResponse>('/api/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    });
    return data.user ?? null;
  } catch {
    return null;
  }
}

export function logout(): void {
  setToken('');
}
