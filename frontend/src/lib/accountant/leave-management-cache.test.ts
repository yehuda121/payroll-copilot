import { afterEach, describe, expect, it } from 'vitest';
import {
  getLeaveListCache,
  invalidateLeaveListCache,
  leaveListCacheKey,
  readLeaveUiSession,
  resetLeaveManagementCacheForTests,
  setLeaveListCache,
  writeLeaveUiSession,
} from './leave-management-cache';
import { LEAVE_DEFAULT_BUCKET } from './leave-management-ui';
import type { VacationRecord, VacationSettings } from '../../services/vacations';

const sampleRow = { id: 'v1' } as VacationRecord;
const sampleSettings = {
  notificationEmailVerified: 'hr@example.com',
  activeMonitoredEmail: 'inbox@example.com',
} as VacationSettings;

afterEach(() => {
  resetLeaveManagementCacheForTests();
});

describe('leave-management-cache', () => {
  it('reuses cached list and settings by filter key', () => {
    const key = leaveListCacheKey('active', '', '');
    setLeaveListCache(key, { items: [sampleRow], settings: sampleSettings });
    expect(getLeaveListCache(key)?.items).toEqual([sampleRow]);
    expect(getLeaveListCache(key)?.settings?.activeMonitoredEmail).toBe('inbox@example.com');
  });

  it('keeps prior cache entry when a different filter key is used', () => {
    const activeKey = leaveListCacheKey('active', '', '');
    const pastKey = leaveListCacheKey('past', '', '');
    setLeaveListCache(activeKey, { items: [sampleRow], settings: sampleSettings });
    setLeaveListCache(pastKey, { items: [], settings: sampleSettings });
    expect(getLeaveListCache(activeKey)?.items).toHaveLength(1);
    expect(getLeaveListCache(pastKey)?.items).toHaveLength(0);
  });

  it('preserves cached rows conceptually when refresh fails (invalidate only on explicit clear)', () => {
    const key = leaveListCacheKey('active', '', '');
    setLeaveListCache(key, { items: [sampleRow], settings: sampleSettings });
    // Failed refresh must not clear cache — only invalidateLeaveListCache does.
    expect(getLeaveListCache(key)?.items).toHaveLength(1);
    invalidateLeaveListCache();
    expect(getLeaveListCache(key)).toBeUndefined();
  });

  it('defaults session filters to active / הכל bucket and preserves session updates', () => {
    expect(readLeaveUiSession().bucket).toBe(LEAVE_DEFAULT_BUCKET);
    writeLeaveUiSession({ bucket: 'past', rangeStart: '2026-01-01', rangeEnd: '2026-01-31' });
    expect(readLeaveUiSession()).toEqual({
      bucket: 'past',
      rangeStart: '2026-01-01',
      rangeEnd: '2026-01-31',
    });
  });
});
