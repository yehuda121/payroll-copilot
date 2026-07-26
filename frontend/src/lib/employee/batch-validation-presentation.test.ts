import { describe, expect, it } from 'vitest';
import type { TFunction } from 'i18next';
import { translateFindingTitle } from './validation-display';

const t = ((key: string) => key) as TFunction;

describe('validation check titles for batch review', () => {
  it('prefers rule_id mapped check titles over Validation Run style labels', () => {
    expect(translateFindingTitle('validation.employee.national_id.mismatch', t, 'employee.national_id.match')).toBe(
      'employee.validation.checkTitles.national_id',
    );
    expect(translateFindingTitle('validation.minimum_wage.below_threshold', t, 'legal.minimum_wage')).toBe(
      'employee.validation.checkTitles.minimumWage',
    );
  });
});
