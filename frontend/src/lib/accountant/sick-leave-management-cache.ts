/** In-memory Leave Management cache — UX only; backend remains SoT. */

import { LEAVE_DEFAULT_BUCKET } from './leave-management-ui';
import type { SickLeaveRecord, SickLeaveSettings } from '../../services/sickLeaves';

export type LeaveListCacheEntry = {
  items: SickLeaveRecord[];
  settings: SickLeaveSettings | null;
};

export type LeaveUiSession = {
  bucket: string;
  rangeStart: string;
  rangeEnd: string;
};

const listCache = new Map<string, LeaveListCacheEntry>();

let uiSession: LeaveUiSession = {
  bucket: LEAVE_DEFAULT_BUCKET,
  rangeStart: '',
  rangeEnd: '',
};

export function leaveListCacheKey(
  bucket: string,
  rangeStart: string,
  rangeEnd: string,
): string {
  return `${bucket}\u0000${rangeStart}\u0000${rangeEnd}`;
}

export function getLeaveListCache(key: string): LeaveListCacheEntry | undefined {
  return listCache.get(key);
}

export function setLeaveListCache(key: string, entry: LeaveListCacheEntry): void {
  listCache.set(key, entry);
}

/** Drop all Leave Management list/settings cache entries. */
export function invalidateSickLeaveListCache(): void {
  listCache.clear();
}

export function readLeaveUiSession(): LeaveUiSession {
  return { ...uiSession };
}

export function writeLeaveUiSession(next: Partial<LeaveUiSession>): LeaveUiSession {
  uiSession = { ...uiSession, ...next };
  return { ...uiSession };
}

/** Test helper — reset module state. */
export function resetLeaveManagementCacheForTests(): void {
  listCache.clear();
  uiSession = {
    bucket: LEAVE_DEFAULT_BUCKET,
    rangeStart: '',
    rangeEnd: '',
  };
}
