import { useCallback } from 'react';
import type { User } from '../types';

/**
 * 本地单用户模式：记忆全部保存在手机本地，不再需要服务端账号/登录。
 * 保留与原来一致的返回结构，便于上层组件无感切换。
 */
export function useAuth() {
  const noop = useCallback(async () => {
    throw new Error('本地模式无需登录');
  }, []);

  return {
    authRequired: false,
    user: null as User | null,
    loading: false,
    showOverlay: false,
    login: noop as (email: string, password: string) => Promise<User>,
    register: noop as (email: string, password: string) => Promise<User>,
    logout: () => {},
    handleSessionExpired: () => {},
    refresh: async () => {},
  };
}
