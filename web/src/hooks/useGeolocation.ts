import { useCallback, useEffect, useState } from 'react';
import { Geolocation } from '@capacitor/geolocation';
import { locateByIp, reverseGeocode } from '../api/location';
import { formatLocationPlace } from '../lib/poi';
import { isNative } from '../lib/native';
import type { ChatLocation, LocationInfo } from '../types';

type GeoPermission = 'granted' | 'prompt' | 'denied' | 'unknown';

class GeoPermissionDenied extends Error {}

function isNetworkLocationError(message: string): boolean {
  return /network service|network location/i.test(message);
}

function describeGeoError(err: GeolocationPositionError): string {
  const msg = err.message || '';
  if (isNetworkLocationError(msg)) {
    return 'Windows 定位服务不可用（常见于台式机）。已自动尝试 IP 近似定位…';
  }
  switch (err.code) {
    case err.PERMISSION_DENIED:
      return '未授权定位。将尝试 IP 近似定位；也可在系统/浏览器允许「位置」权限后重试。';
    case err.POSITION_UNAVAILABLE:
      return '无法获取 GPS 位置，正在尝试 IP 近似定位…';
    case err.TIMEOUT:
      return 'GPS 定位超时，正在尝试 IP 近似定位…';
    default:
      return msg || '未知错误';
  }
}

function requestBrowserPosition(
  options: PositionOptions,
): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(resolve, reject, options);
  });
}

/** 浏览器：桌面端先低精度（Wi‑Fi/IP），失败再试高精度，减少超时。 */
async function getBrowserPosition(): Promise<{ lng: number; lat: number }> {
  const attempts: PositionOptions[] = [
    { enableHighAccuracy: false, timeout: 20000, maximumAge: 300000 },
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
  ];
  let lastErr: unknown = null;
  for (const opts of attempts) {
    try {
      const pos = await requestBrowserPosition(opts);
      return { lng: pos.coords.longitude, lat: pos.coords.latitude };
    } catch (e) {
      lastErr = e;
      if (e instanceof GeolocationPositionError && e.code === e.PERMISSION_DENIED) {
        throw e;
      }
    }
  }
  throw lastErr ?? new Error('定位失败');
}

/** 原生（安卓）：用 Capacitor Geolocation 插件取真实 GPS。 */
async function getNativePosition(): Promise<{ lng: number; lat: number }> {
  let perm = await Geolocation.checkPermissions();
  if (perm.location !== 'granted' && perm.coarseLocation !== 'granted') {
    perm = await Geolocation.requestPermissions({ permissions: ['location'] });
  }
  if (perm.location !== 'granted' && perm.coarseLocation !== 'granted') {
    throw new GeoPermissionDenied('定位权限被拒绝');
  }
  const pos = await Geolocation.getCurrentPosition({
    enableHighAccuracy: true,
    timeout: 15000,
    maximumAge: 60000,
  });
  return { lng: pos.coords.longitude, lat: pos.coords.latitude };
}

export function useGeolocation() {
  const [location, setLocation] = useState<ChatLocation | null>(null);
  const [locationInfo, setLocationInfo] = useState<LocationInfo | null>(null);
  const [status, setStatus] = useState<string>('点击「定位」获取当前位置');
  const [permission, setPermission] = useState<GeoPermission>('unknown');
  const [approximate, setApproximate] = useState(false);

  useEffect(() => {
    if (isNative()) {
      void Geolocation.checkPermissions()
        .then((p) => {
          const granted =
            p.location === 'granted' || p.coarseLocation === 'granted';
          setPermission(granted ? 'granted' : 'prompt');
        })
        .catch(() => setPermission('unknown'));
      return;
    }
    if (!navigator.permissions?.query) return;
    void navigator.permissions
      .query({ name: 'geolocation' })
      .then((result) => {
        setPermission(result.state as GeoPermission);
        result.onchange = () => setPermission(result.state as GeoPermission);
      })
      .catch(() => setPermission('unknown'));
  }, []);

  const applyCoords = useCallback(
    async (lng: number, lat: number, isApprox = false) => {
      setLocation({ lng, lat });
      setApproximate(isApprox);
      const info = await reverseGeocode(lng, lat);
      setLocationInfo(info);
      const place = formatLocationPlace(info);
      const prefix = isApprox ? '已定位（IP 近似）' : '已定位';
      setStatus(
        place
          ? `${prefix} · ${place}`
          : `${prefix} · ${lat.toFixed(4)}, ${lng.toFixed(4)}`,
      );
      return place || null;
    },
    [],
  );

  const tryIpLocate = useCallback(
    async (silent: boolean): Promise<string | null> => {
      if (!silent) setStatus('GPS 不可用，正在用 IP 近似定位…');
      const result = await locateByIp();
      if (!result) {
        if (!silent) {
          setStatus('定位失败：GPS 与 IP 定位均不可用，请检查网络或稍后重试');
        }
        return null;
      }
      setLocationInfo(result);
      setApproximate(true);
      setLocation({ lng: result.lng, lat: result.lat });
      const place = formatLocationPlace(result) || result.city || '';
      const label = place || `${result.lat.toFixed(4)}, ${result.lng.toFixed(4)}`;
      setStatus(`已定位（IP 近似） · ${label}`);
      return place || null;
    },
    [],
  );

  const detect = useCallback(
    async (silent = false): Promise<string | null> => {
      if (isNative()) {
        if (!silent) setStatus('定位中…');
        try {
          const { lng, lat } = await getNativePosition();
          return await applyCoords(lng, lat, false);
        } catch (e) {
          if (e instanceof GeoPermissionDenied) {
            if (!silent) setStatus('定位权限被拒绝，尝试 IP 近似定位…');
          } else if (!silent) {
            setStatus('GPS 定位失败，尝试 IP 近似定位…');
          }
          return await tryIpLocate(silent);
        }
      }

      if (permission === 'denied' || !navigator.geolocation) {
        return await tryIpLocate(silent);
      }

      if (!silent) setStatus('定位中…');
      try {
        const { lng, lat } = await getBrowserPosition();
        return await applyCoords(lng, lat, false);
      } catch (e) {
        if (!silent && e instanceof GeolocationPositionError) {
          setStatus(describeGeoError(e));
        }
        return await tryIpLocate(silent);
      }
    },
    [applyCoords, permission, tryIpLocate],
  );

  /** 进入页面时：已授权则取精确位置，否则用 IP 近似定位（无需权限）。 */
  const detectIfGranted = useCallback(() => {
    void (async () => {
      if (isNative()) {
        if (permission === 'granted') {
          try {
            const { lng, lat } = await getNativePosition();
            await applyCoords(lng, lat, false);
            return;
          } catch {
            /* fall through */
          }
        }
        await tryIpLocate(true);
        return;
      }

      if (permission === 'granted' && navigator.geolocation) {
        try {
          const { lng, lat } = await getBrowserPosition();
          await applyCoords(lng, lat, false);
          return;
        } catch {
          /* fall through to IP */
        }
      }
      await tryIpLocate(true);
    })();
  }, [applyCoords, permission, tryIpLocate]);

  return {
    location,
    locationInfo,
    status,
    permission,
    approximate,
    detect,
    detectIfGranted,
  };
}
