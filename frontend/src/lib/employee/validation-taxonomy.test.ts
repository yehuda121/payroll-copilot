import { describe, expect, it } from 'vitest';
import {
  boundRuleIdsForField,
  taxonomyForRuleId,
  uiGroupForTaxonomy,
} from './validation-taxonomy';

describe('validation-taxonomy', () => {
  it('maps known rules without changing verdict semantics', () => {
    expect(taxonomyForRuleId('legal.minimum_wage')).toBe('law');
    expect(taxonomyForRuleId('department.lawyers.overtime_cap')).toBe('contract');
    expect(taxonomyForRuleId('historical.salary_drift')).toBe('employee');
    expect(taxonomyForRuleId('sanity.national_id.checksum')).toBe('sanity');
    expect(taxonomyForRuleId('sanity.required.national_id')).toBe('sanity');
  });

  it('surfaces CONTRACT under employee checks for UI', () => {
    expect(uiGroupForTaxonomy('contract')).toBe('employee_checks');
    expect(uiGroupForTaxonomy('law')).toBe('law_checks');
    expect(uiGroupForTaxonomy('sanity')).toBe('digital');
  });

  it('binds SANITY rules explicitly to digital fields', () => {
    expect(boundRuleIdsForField('national_id')).toContain('sanity.national_id.length');
    expect(boundRuleIdsForField('national_id')).toContain('sanity.required.national_id');
    expect(boundRuleIdsForField('net_salary')).toContain('sanity.net_salary.not_exceed_gross');
  });
});
