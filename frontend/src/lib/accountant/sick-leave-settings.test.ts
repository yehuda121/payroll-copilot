import { describe, expect, it } from 'vitest';
import {
  isSickLeaveSettingsDirty,
  sickLeaveSettingsBaseline,
} from './leave-management-ui';
import { jsonBody } from '../../services/sickLeaves';

describe('sick leave settings helpers', () => {
  it('detects dirty sick-leave notification prefs', () => {
    const baseline = sickLeaveSettingsBaseline({
      notificationEmailVerified: 'a@example.com',
      notificationEmailPending: null,
      notifyOnNewSickLeave: true,
      notifyOnSickLeaveErrorOrAttention: true,
    });
    expect(isSickLeaveSettingsDirty(baseline, baseline)).toBe(false);
    expect(
      isSickLeaveSettingsDirty(
        { ...baseline, notifyOnNewSickLeave: false },
        baseline,
      ),
    ).toBe(true);
  });
});

describe('sickLeaves jsonBody', () => {
  it('serializes bulk payload with sick_leave_ids', () => {
    const body = JSON.parse(
      jsonBody({ sick_leave_ids: ['a', 'b'], confirm_warnings: true }),
    );
    expect(body).toEqual({
      sick_leave_ids: ['a', 'b'],
      confirm_warnings: true,
    });
  });
});
