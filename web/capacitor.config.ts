import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.travelagent.app',
  appName: '智能旅行助手',
  webDir: 'dist',
  server: {
    androidScheme: 'https',
    // 允许 WebView 内的 XHR 访问 http 的局域网后端（开发期）。
    // 生产建议后端走 https 并移除该项。
    cleartext: true,
  },
  android: {
    allowMixedContent: true,
  },
  plugins: {
    Geolocation: {},
  },
};

export default config;
