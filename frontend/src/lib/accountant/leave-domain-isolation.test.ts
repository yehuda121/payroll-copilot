/** Domain isolation for Vacation vs Sick Leave accountant pages. */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  LEAVE_HARD_ATTENTION_CODES,
  leaveAttentionLabel,
  leaveEmployeeLabel,
  leaveRowSeverityClass,
  leaveStatusBadgeClass,
} from './leave-management-ui';

const here = dirname(fileURLToPath(import.meta.url));
const vacationsSrc = readFileSync(
  join(here, '../../pages/accountant/Vacations.tsx'),
  'utf8',
);
const sickLeavesSrc = readFileSync(
  join(here, '../../pages/accountant/SickLeaves.tsx'),
  'utf8',
);

describe('leave domain page isolation', () => {
  it('Vacations page imports only vacation service/cache and vacation i18n prefixes', () => {
    expect(vacationsSrc).toContain("from '../../services/vacations'");
    expect(vacationsSrc).toContain("from '../../lib/accountant/leave-management-cache'");
    expect(vacationsSrc).toContain("accountant.vacations.");
    expect(vacationsSrc).not.toContain("from '../../services/sickLeaves'");
    expect(vacationsSrc).not.toContain('sick-leave-management-cache');
    expect(vacationsSrc).not.toContain('accountant.sickLeaves.');
    expect(vacationsSrc).not.toMatch(/typeSickLeave|notifyOnNewSickLeave/);
  });

  it('Sick Leaves page imports only sick-leave service/cache and sickLeaves i18n prefixes', () => {
    expect(sickLeavesSrc).toContain("from '../../services/sickLeaves'");
    expect(sickLeavesSrc).toContain("from '../../lib/accountant/sick-leave-management-cache'");
    expect(sickLeavesSrc).toContain('accountant.sickLeaves.');
    expect(sickLeavesSrc).not.toContain("from '../../services/vacations'");
    expect(sickLeavesSrc).not.toContain("from '../../lib/accountant/leave-management-cache'");
    expect(sickLeavesSrc).not.toContain('accountant.vacations.');
    expect(sickLeavesSrc).not.toMatch(/typeVacation|notifyOnNewVacation[^S]/);
  });

  it('shared presentation helpers do not embed domain terminology', () => {
    expect(leaveEmployeeLabel({ extractedEmployeeName: 'Ada', extractedEmployeeEmail: null })).toBe(
      'Ada',
    );
    expect(leaveStatusBadgeClass('approved', [])).toBe('status-badge--passed');
    expect(leaveRowSeverityClass(['EMPLOYEE_NOT_FOUND'])).toBe('leave-row--error');
    expect(LEAVE_HARD_ATTENTION_CODES.has('EMPLOYEE_NOT_FOUND')).toBe(true);
    expect(
      leaveAttentionLabel('OVERLAP', (key) => `translated:${key}`, 'accountant.vacations'),
    ).toBe('translated:accountant.vacations.attention.OVERLAP');
    expect(
      leaveAttentionLabel('OVERLAP', (key) => `translated:${key}`, 'accountant.sickLeaves'),
    ).toBe('translated:accountant.sickLeaves.attention.OVERLAP');
  });
});
