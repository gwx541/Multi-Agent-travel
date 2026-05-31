/**
 * 后端 API 基地址解析。
 *
 * Web 开发：留空，走 Vite 代理（相对路径 /api → 127.0.0.1:8000）。
 * 安卓 App：WebView 从应用包内加载，相对路径无法代理，必须用绝对地址指向后端。
 *
 * 优先级：应用内设置（localStorage） > 构建期环境变量 VITE_API_BASE > 空（相对路径）。
 */
const LS_API_BASE = 'travelagent_api_base';

function normalizeBase(base: string): string {
  return base.replace(/\/+$/, '');
}

export function getApiBase(): string {
  const override = localStorage.getItem(LS_API_BASE);
  if (override) return normalizeBase(override);
  const env = import.meta.env.VITE_API_BASE as string | undefined;
  if (env) return normalizeBase(env);
  return '';
}

export function setApiBase(base: string): void {
  const v = base.trim();
  if (v) localStorage.setItem(LS_API_BASE, normalizeBase(v));
  else localStorage.removeItem(LS_API_BASE);
}

/** 把以 /api 开头的相对路径拼成完整请求地址；已是绝对地址则原样返回。 */
export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${getApiBase()}${path}`;
}
