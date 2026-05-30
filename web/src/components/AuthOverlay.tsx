import { useState } from 'react';
import './AuthOverlay.css';

interface Props {
  onLogin: (email: string, password: string) => Promise<void>;
  onRegister: (email: string, password: string) => Promise<void>;
}

export function AuthOverlay({ onLogin, onRegister }: Props) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function submit(mode: 'login' | 'register') {
    setError('');
    const e = email.trim();
    if (!e || !password) {
      setError('请填写邮箱和密码');
      return;
    }
    setSubmitting(true);
    try {
      if (mode === 'login') await onLogin(e, password);
      else await onRegister(e, password);
      setPassword('');
    } catch (err) {
      setError(err instanceof Error ? err.message : '请求失败');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-overlay">
      <div className="auth-card">
        <h2>登录 / 注册</h2>
        <p className="auth-hint">登录后记忆与行程将绑定当前账户</p>
        <input
          type="email"
          placeholder="邮箱"
          value={email}
          onChange={(ev) => setEmail(ev.target.value)}
          autoComplete="email"
        />
        <input
          type="password"
          placeholder="密码（至少 8 位）"
          value={password}
          onChange={(ev) => setPassword(ev.target.value)}
          autoComplete="current-password"
        />
        {error && <p className="auth-error">{error}</p>}
        <div className="auth-actions">
          <button
            type="button"
            disabled={submitting}
            onClick={() => void submit('login')}
          >
            登录
          </button>
          <button
            type="button"
            className="secondary"
            disabled={submitting}
            onClick={() => void submit('register')}
          >
            注册
          </button>
        </div>
      </div>
    </div>
  );
}
