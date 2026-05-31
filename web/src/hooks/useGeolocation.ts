import { useCallback, useEffect, useState } from 'react';
import { locateByIp, reverseGeocode } from '../api/location';
import { formatLocationPlace } from '../lib/poi';
import type { ChatLocation, LocationInfo } from '../types';

type GeoPermission = 'granted' | 'prompt' | 'denied' | 'unknown';

function isNetworkLocationError(message: string): boolean {
  return /network service|network location/i.test(message);
}

function describeGeoError(err: GeolocationPositionError): string {
  const msg = err.message || '';
  if (isNetworkLocationError(msg)) {
    return (
      'Windows 定位服务不可用（常见于台式机）。已自动尝试 IP 近似定位…'
    );
  }
  switch (err.code) {
    case err.PERMISSION_DENIED:
      return (
        '浏览器未授权定位。将尝试 IP 近似定位；也可在地址栏允许「位置」权限后重试。'
      );
    case err.POSITION_UNAVAILABLE:
      return '无法获取 GPS 位置，正在尝试 IP 近似定位…';
    case err.TIMEOUT:
      return 'GPS 定位超时，正在尝试 IP 近似定位…';
    default:
      return msg || '未知错误';
  }
}

function requestPosition(options: PositionOptions): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(resolve, reject, options);
  });
}

async function getPositionWithFallback(): Promise<GeolocationPosition> {
  const attempts: PositionOptions[] = [
    { enableHighAccuracy: false, timeout: 20000, maximumAge: 300000 },
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
  ];
  let lastErr: GeolocationPositionError | null = null;
  for (const opts of attempts) {
    try {
      return await requestPosition(opts);
    } catch (e) {
      if (e instanceof GeolocationPositionError) {
        lastErr = e;
        if (e.code === e.PERMISSION_DENIED) throw e;
      }
    }
  }
  throw lastErr ?? new DOMException('定位失败', 'NotSupportedError');
}

export function useGeolocation() {
  const [location, setLocation] = useState<ChatLocation | null>(null);
  const [locationInfo, setLocationInfo] = useState<LocationInfo | null>(null);
  const [status, setStatus] = useState<string>('点击「定位」获取当前位置');
  const [permission, setPermission] = useState<GeoPermission>('unknown');
  const [approximate, setApproximate] = useState(false);

  useEffect(() => {
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
      const loc = { lng, lat };
      setLocation(loc);
      setApproximate(isApprox);
      const info = await reverseGeocode(lng, lat);
      setLocationInfo(info);
      const place = formatLocationPlace(info);
      const prefix = isApprox ? '已定位（IP 近似）' : '已定位';
      if (place) {
        setStatus(`${prefix} · ${place}`);
      } else {
        setStatus(`${prefix} · ${lat.toFixed(4)}, ${lng.toFixed(4)}`);
      }
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
          setStatus(
            '定位失败：GPS 与 IP 定位均不可用，请检查网络或稍后重试',
          );
        }
        return null;
      }
      setLocationInfo(result);
      setApproximate(true);
      setLocation({ lng: result.lng, lat: result.lat });
      const place = formatLocationPlace(result) || `${result.city || ''}`;
      const label = place || `${result.lat.toFixed(4)}, ${result.lng.toFixed(4)}`;
      setStatus(`已定位（IP 近似） · ${label}`);
      return place || null;
    },
    [],
  );

  const detect = useCallback(
    (silent = false): Promise<string | null> => {
      return new Promise((resolve) => {
        if (permission === 'denied') {
          void tryIpLocate(silent).then(resolve);
          return;
        }

        if (!navigator.geolocation) {
          void tryIpLocate(silent).then(resolve);
          return;
        }

        if (!silent) setStatus('定位中…');

        void (async () => {
          try {
            const pos = await getPositionWithFallback();
            const place = await applyCoords(
              pos.coords.longitude,
              pos.coords.latitude,
              false,
            );
            resolve(place);
          } catch (e) {
            if (!silent && e instanceof GeolocationPositionError) {
              setStatus(describeGeoError(e));
            }
            const ipPlace = await tryIpLocate(silent);
            resolve(ipPlace);
          }
        })();
      });
    },
    [applyCoords, permission, tryIpLocate],
  );

  /** 进入页面时优先 IP 近似定位（无需浏览器权限）；已授权 GPS 时再尝试精确位置。 */
  const detectIfGranted = useCallback(() => {
    void (async () => {
      if (permission === 'granted' && navigator.geolocation) {
        try {
          const pos = await getPositionWithFallback();
          await applyCoords(pos.coords.longitude, pos.coords.latitude, false);
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
