import { describe, expect, it } from 'vitest';
import type { BatchExtractedEmployee } from '../../types/api';
import {
  batchItemSearchHaystack,
  matchesBatchSearchQuery,
  normalizeBatchSearchText,
} from './batch-search';

function item(partial: Partial<BatchExtractedEmployee>): BatchExtractedEmployee {
  return {
    id: '1',
    slip_index: 11,
    status: 'passed',
    warnings: 0,
    critical_issues: 0,
    processing_stage: 'completed',
    ...partial,
  };
}

describe('normalizeBatchSearchText', () => {
  it('trims, collapses spaces, and casefolds', () => {
    expect(normalizeBatchSearchText('  Yehuda   SHMUL  ')).toBe('yehuda shmul');
  });
});

describe('matchesBatchSearchQuery', () => {
  it('matches employee name substring', () => {
    const row = item({ employee_name: 'יהודה שמולביץ' });
    expect(matchesBatchSearchQuery(row, 'שמול')).toBe(true);
    expect(matchesBatchSearchQuery(row, 'לא קיים')).toBe(false);
  });

  it('matches employee number and masked id', () => {
    const row = item({
      employee_number: 'EMP-104',
      national_id_masked: '123****89',
    });
    expect(matchesBatchSearchQuery(row, 'emp-104')).toBe(true);
    expect(matchesBatchSearchQuery(row, '123**')).toBe(true);
  });

  it('matches tokens in any order', () => {
    const row = item({
      employee_name: 'Yehuda Shmulovitz',
      employee_number: '104',
    });
    expect(matchesBatchSearchQuery(row, '104 yehuda')).toBe(true);
  });

  it('includes immutable slip serial in haystack', () => {
    const row = item({ slip_index: 11, employee_name: null });
    expect(batchItemSearchHaystack(row)).toContain('12');
    expect(matchesBatchSearchQuery(row, '12')).toBe(true);
  });

  it('empty query matches all', () => {
    expect(matchesBatchSearchQuery(item({}), '   ')).toBe(true);
  });
});
