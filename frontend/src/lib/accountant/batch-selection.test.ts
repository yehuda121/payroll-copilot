import { describe, expect, it } from 'vitest';
import {
  applySelectAllVisible,
  canBulkDeleteItem,
  canBulkPublishItem,
  computeSelectAllState,
  pruneSelectionToAliveIds,
} from './batch-selection';
import type { BatchExtractedEmployee } from '../../types/api';

function item(
  overrides: Partial<BatchExtractedEmployee> & Pick<BatchExtractedEmployee, 'id'>,
): BatchExtractedEmployee {
  return {
    slip_index: 0,
    status: 'passed',
    warnings: 0,
    critical_issues: 0,
    processing_stage: 'completed',
    document_id: 'doc',
    employee_number: '1',
    ...overrides,
  };
}

describe('batch selection helpers', () => {
  it('select-all is checked / indeterminate / unchecked correctly', () => {
    const visible = ['a', 'b', 'c'];
    expect(computeSelectAllState(visible, new Set()).allSelected).toBe(false);
    expect(computeSelectAllState(visible, new Set()).someSelected).toBe(false);

    const some = computeSelectAllState(visible, new Set(['a']));
    expect(some.allSelected).toBe(false);
    expect(some.someSelected).toBe(true);

    const all = computeSelectAllState(visible, new Set(['a', 'b', 'c']));
    expect(all.allSelected).toBe(true);
    expect(all.someSelected).toBe(false);
  });

  it('select all visible does not clear hidden selections outside the visible set', () => {
    const next = applySelectAllVisible(new Set(['hidden']), ['a', 'b'], true);
    expect(next.has('hidden')).toBe(true);
    expect(next.has('a')).toBe(true);
    expect(next.has('b')).toBe(true);
  });

  it('prunes deleted ids after bulk delete', () => {
    const pruned = pruneSelectionToAliveIds(new Set(['a', 'b', 'c']), new Set(['b']));
    expect([...pruned]).toEqual(['b']);
  });

  it('gates publish and delete eligibility', () => {
    expect(canBulkDeleteItem(item({ id: '1' }))).toBe(true);
    expect(canBulkDeleteItem(item({ id: '2', document_id: null }))).toBe(false);
    expect(canBulkPublishItem(item({ id: '3', status: 'unknown_employee' }))).toBe(false);
    expect(canBulkPublishItem(item({ id: '4', publication_status: 'published' }))).toBe(false);
    expect(canBulkPublishItem(item({ id: '5', status: 'passed' }))).toBe(true);
  });
});
