import { describe, expect, it } from 'vitest';
import {
  taxonomyForRuleId,
  uiGroupForTaxonomy,
} from './validation-taxonomy';

describe('validation-taxonomy', () => {
  it('maps known rules without changing verdict semantics', () => {
    expect(taxonomyForRuleId('legal.minimum_wage')).toBe('law');
    expect(taxonomyForRuleId('department.lawyers.overtime_cap')).toBe('contract');
    expect(taxonomyForRuleId('historical.salary_drift')).toBe('employee');
  });

  it('surfaces CONTRACT under employee checks for UI', () => {
    expect(uiGroupForTaxonomy('contract')).toBe('employee_checks');
    expect(uiGroupForTaxonomy('law')).toBe('law_checks');
  });
});
