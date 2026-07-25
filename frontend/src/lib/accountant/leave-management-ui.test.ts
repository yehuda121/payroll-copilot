import { describe, expect, it } from 'vitest';
import heAccountant from '../../i18n/locales/accountant.he.json';
import {
  formatLeaveConfidence,
  formatLeaveDateTime,
  isBasicLeaveNotificationEmail,
  isLeaveEditDirty,
  isLeaveSettingsDirty,
  LEAVE_DEFAULT_BUCKET,
  leaveEditBaseline,
  leaveSettingsBaseline,
  mapLeaveActionError,
  normalizeLeaveNotificationEmail,
} from './leave-management-ui';

describe('leave-management-ui helpers', () => {
  it('defaults filter to active and labels it as הכל in Hebrew', () => {
    expect(LEAVE_DEFAULT_BUCKET).toBe('active');
    expect(heAccountant.accountant.vacations.buckets.active).toBe('הכל');
  });

  it('detects dirty editable fields', () => {
    const baseline = leaveEditBaseline({
      extractedEmployeeEmail: 'a@example.com',
      extractedEmployeeName: 'Ada',
      startDate: '2026-11-01',
      endDate: '2026-11-05',
    });
    expect(isLeaveEditDirty(baseline, baseline)).toBe(false);
    expect(
      isLeaveEditDirty({ ...baseline, employeeEmail: '  a@example.com  ' }, baseline),
    ).toBe(false);
    expect(isLeaveEditDirty({ ...baseline, employeeName: 'Augusta' }, baseline)).toBe(true);
  });

  it('formats confidence as percent', () => {
    expect(formatLeaveConfidence(0.95)).toBe('95%');
    expect(formatLeaveConfidence(null)).toBe('—');
  });

  it('formats received datetime without raw ISO dump', () => {
    const formatted = formatLeaveDateTime('2026-07-24T20:42:13+00:00', 'he-IL');
    expect(formatted).not.toContain('T20:42');
    expect(formatted).not.toBe('—');
  });

  it('maps blocked approval errors to friendly copy', () => {
    const msg = mapLeaveActionError(
      { status: 422, message: 'API request failed: 422 Unprocessable Entity', code: 'blocked' },
      'generic',
      { blockedApproval: 'fix fields' },
    );
    expect(msg).toBe('fix fields');
    expect(msg).not.toMatch(/422|Unprocessable|API request failed/i);
  });

  it('validates and normalizes notification email', () => {
    expect(normalizeLeaveNotificationEmail('  Ada@Example.COM ')).toBe('ada@example.com');
    expect(isBasicLeaveNotificationEmail('')).toBe(true);
    expect(isBasicLeaveNotificationEmail('ada@example.com')).toBe(true);
    expect(isBasicLeaveNotificationEmail('not-an-email')).toBe(false);
    expect(isBasicLeaveNotificationEmail('a@b')).toBe(false);
  });

  it('tracks settings dirty state and displays verified/pending notification email', () => {
    const baseline = leaveSettingsBaseline({
      notificationEmailVerified: 'hr@example.com',
      notificationEmailPending: null,
      notifyOnNewVacation: true,
      notifyOnErrorOrAttention: false,
    });
    expect(baseline.notificationEmail).toBe('hr@example.com');
    expect(isLeaveSettingsDirty(baseline, baseline)).toBe(false);
    expect(
      isLeaveSettingsDirty({ ...baseline, notificationEmail: '  hr@example.com ' }, baseline),
    ).toBe(false);
    expect(isLeaveSettingsDirty({ ...baseline, notifyOnNewVacation: false }, baseline)).toBe(true);
    expect(
      leaveSettingsBaseline({
        notificationEmailVerified: null,
        notificationEmailPending: 'pending@example.com',
        notifyOnNewVacation: true,
        notifyOnErrorOrAttention: true,
      }).notificationEmail,
    ).toBe('pending@example.com');
  });

  it('uses simplified Hebrew notifications settings copy', () => {
    const vacations = heAccountant.accountant.vacations;
    expect(vacations.notificationsSection).toBe('התראות');
    expect(vacations.notificationEmailField).toBe('מייל לקבלת התראות');
    expect(vacations.notificationEmailHelp).toContain('בקשות חופשה');
    expect(vacations.refresh).toBe('רענון');
  });
});
