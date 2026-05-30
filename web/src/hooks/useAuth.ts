import { useCallback, useEffect, useState } from 'react';
import {
  fetchConfig,
  fetchMe,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
} from '../api/auth';
import { setToken } from '../api/client';
import type { User } from '../types';

export function useAuth() {
  const [authRequired, setAuthRequired] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [showOverlay, setShowOverlay] = useState(false);

  const init = useCallback(async () => {
    setLoading(true);
    try {
      const cfg = await fetchConfig();
      setAuthRequired(cfg.auth_required);
      if (!cfg.auth_required) {
        setUser(null);
        setShowOverlay(false);
        return;
      }
      setShowOverlay(true);
      const me = await fetchMe();
      if (me) {
        setUser(me);
        setShowOverlay(false);
      } else {
        setToken('');
        setUser(null);
      }
    } catch {
      setAuthRequired(false);
      setShowOverlay(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void init();
  }, [init]);

  const login = useCallback(async (email: string, password: string) => {
    const u = await apiLogin(email, password);
    setUser(u);
    setShowOverlay(false);
    return u;
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const u = await apiRegister(email, password);
    setUser(u);
    setShowOverlay(false);
    return u;
  }, []);

  const logout = useCallback(() => {
    apiLogout();
    setUser(null);
    if (authRequired) setShowOverlay(true);
  }, [authRequired]);

  const handleSessionExpired = useCallback(() => {
    setToken('');
    setUser(null);
    if (authRequired) setShowOverlay(true);
  }, [authRequired]);

  return {
    authRequired,
    user,
    loading,
    showOverlay,
    login,
    register,
    logout,
    handleSessionExpired,
    refresh: init,
  };
}
