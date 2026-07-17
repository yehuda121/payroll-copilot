import { describe, expect, it } from 'vitest';
import {
  FIELD_EXPLAIN_KEYS,
  STATIC_FIELD_TIPS,
  mapFindingSeverityToFieldStatus,
} from './fieldGuidance';

describe('landing field guidance', () => {
  it('keeps AI explanations and static tips as separate maps', () => {
    expect(STATIC_FIELD_TIPS.tax_credits).toBeTruthy();
    expect(FIELD_EXPLAIN_KEYS.base_salary).toBeTruthy();
    expect(STATIC_FIELD_TIPS.base_salary).toBeUndefined();
  });

  it('maps finding severities to visual statuses without inventing pass/fail', () => {
    expect(mapFindingSeverityToFieldStatus('critical')).toBe('failed');
    expect(mapFindingSeverityToFieldStatus('warning')).toBe('uncertain');
    expect(mapFindingSeverityToFieldStatus('pass')).toBe('passed');
    expect(mapFindingSeverityToFieldStatus(undefined)).toBe('unchecked');
  });
});
