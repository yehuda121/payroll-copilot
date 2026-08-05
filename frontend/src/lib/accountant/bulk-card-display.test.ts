import { describe, expect, it, vi } from 'vitest';
import type { BatchExtractedEmployee } from '../../types/api';
import { batchItemSearchHaystack } from './batch-search';
import { bulkCardDisplayName } from './bulk-card-display';

function item(partial: Partial<BatchExtractedEmployee>): BatchExtractedEmployee {
  return {
    id: '1',
    slip_index: 0,
    status: 'unknown_employee',
    warnings: 0,
    critical_issues: 0,
    processing_stage: 'completed',
    ...partial,
  };
}

describe('bulkCardDisplayName', () => {
  it('uses extracted name when unmatched', () => {
    expect(
      bulkCardDisplayName(
        item({
          extracted_employee_name: 'יהודה שמולביץ',
          employee_name: null,
          status: 'unknown_employee',
        }),
        'לא ידוע',
      ),
    ).toBe('יהודה שמולביץ');
  });

  it('falls back to unnamed label when no extracted name', () => {
    expect(
      bulkCardDisplayName(
        item({ extracted_employee_name: null, employee_name: 'Dana Levi' }),
        'לא ידוע',
      ),
    ).toBe('לא ידוע');
  });

  it('does not prefer matched profile name over extracted name', () => {
    expect(
      bulkCardDisplayName(
        item({
          extracted_employee_name: 'שם מהתלוש',
          employee_name: 'Matched Profile',
          status: 'passed',
        }),
        'לא ידוע',
      ),
    ).toBe('שם מהתלוש');
  });
});

describe('batch search includes extracted name', () => {
  it('indexes extracted_employee_name', () => {
    const haystack = batchItemSearchHaystack(
      item({ extracted_employee_name: 'יהודה שמולביץ', employee_name: null }),
    );
    expect(haystack).toContain('יהודה');
  });
});

describe('employee assign confirmation copy', () => {
  it('formats hebrew confirmation with name and id placeholders', () => {
    const template =
      'האם אתה בטוח שברצונך לשייך את התלוש הנוכחי לעובד "{{employee_name}}", ת.ז {{national_id}}?';
    const message = template
      .replace('{{employee_name}}', 'דנה לוי')
      .replace('{{national_id}}', '****6783');
    expect(message).toContain('דנה לוי');
    expect(message).toContain('****6783');
    expect(message).not.toContain('{{');
  });
});

vi.mock('../../components/ui/Dialog', () => ({
  useConfirmDialog: () => ({ confirm: async () => false }),
}));
