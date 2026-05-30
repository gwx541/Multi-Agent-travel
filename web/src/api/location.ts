import { apiFetch } from './client';
import type { LocationInfo } from '../types';

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
