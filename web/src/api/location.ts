import { apiFetch } from './client';
import type { LocateResult, LocationInfo } from '../types';

export async function reverseGeocode(
  lng: number,
  lat: number,
): Promise<LocationInfo | null> {
  try {
    return await apiFetch<LocationInfo>(
      `/api/reverse?lng=${lng}&lat=${lat}`,
    );
  } catch {
    return null;
  }
}

/** 服务端 IP 近似定位（浏览器 GPS 不可用时的兜底）。 */
export async function locateByIp(): Promise<LocateResult | null> {
  try {
    return await apiFetch<LocateResult>('/api/locate');
  } catch {
    return null;
  }
}
