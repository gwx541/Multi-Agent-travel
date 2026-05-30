import { useCallback, useState } from 'react';
import { reverseGeocode } from '../api/location';
import { formatLocationPlace } from '../lib/poi';
import type { ChatLocation, LocationInfo } from '../types';

export function useGeolocation() {
  const [location, setLocation] = useState<ChatLocation | null>(null);
  const [locationInfo, setLocationInfo] = useState<LocationInfo | null>(null);
  const [status, setStatus] = useState<string>('未定位');

  const detect = useCallback((silent = false): Promise<string | null> => {
    return new Promise((resolve) => {
      if (!navigator.geolocation) {
        const msg = '浏览器不支持定位';
        if (!silent) setStatus(msg);
        resolve(null);
        return;
      }
      if (!silent) setStatus('定位中…');
      navigator.geolocation.getCurrentPosition(
        async (pos) => {
          const lng = pos.coords.longitude;
          const lat = pos.coords.latitude;
          const loc = { lng, lat };
          setLocation(loc);
          const info = await reverseGeocode(lng, lat);
          setLocationInfo(info);
          const place = formatLocationPlace(info) || '位置已获取';
          setStatus(`已定位 · ${place}`);
          resolve(place);
        },
        (err) => {
          const msg = `定位失败：${err.message || '已拒绝授权'}`;
          if (!silent) setStatus(msg);
          resolve(null);
        },
        { enableHighAccuracy: true, timeout: 12000 },
      );
    });
  }, []);

  return { location, locationInfo, status, detect };
}
