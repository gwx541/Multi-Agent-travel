import { Browser } from '@capacitor/browser';
import { isNative } from './native';

/**
 * 在「外部」打开链接：
 * - Web：新开标签页。
 * - 安卓 App：用系统浏览器（Chrome Custom Tab）打开并「渲染网页」。
 *
 * 为什么不直接交给系统 Intent？因为小红书 / 携程对自家域名做了 App Links，
 * 系统会把链接丢给 App 接管，而 App 解析不了搜索页 / 酒店列表页这类网页路径，
 * 表现为小红书「页面不见了」、携程跳回首页。用 Custom Tab 渲染网页可避免这种接管，
 * 搜索页 / 列表页 / 详情页都能正常显示（用户仍可在浏览器里选择「用 App 打开」）。
 */
export function openExternal(url: string): void {
  if (!url) return;
  if (isNative()) {
    void Browser.open({ url, presentationStyle: 'fullscreen' }).catch(() => {
      window.open(url, '_blank');
    });
    return;
  }
  window.open(url, '_blank', 'noopener');
}

/**
 * 全局拦截聊天区域内的链接点击，统一走外部打开。
 * 在 WebView 内可避免外链把整个 App 页面顶掉。
 */
export function installLinkInterceptor(root: HTMLElement): () => void {
  const handler = (e: MouseEvent) => {
    const target = e.target as HTMLElement | null;
    const anchor = target?.closest('a') as HTMLAnchorElement | null;
    if (!anchor) return;
    const href = anchor.getAttribute('href');
    if (!href || !/^https?:\/\//i.test(href)) return;
    e.preventDefault();
    openExternal(href);
  };
  root.addEventListener('click', handler);
  return () => root.removeEventListener('click', handler);
}
