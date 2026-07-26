import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = join(process.cwd(), 'src');

function read(rel: string): string {
  return readFileSync(join(root, rel), 'utf8');
}

describe('Payslip review polish UI contracts', () => {
  it('Digital Payslip no longer renders pencil edit actions', () => {
    const form = read('features/employee/EmployeeDigitalForm.tsx');
    expect(form).not.toContain('Pencil');
    expect(form).toContain('digital-form__value-btn');
    expect(form).toContain('openEditor(field.key, field.value)');
    expect(form).not.toContain("aria-invalid={meta?.status === 'failed' || missingRequired}");
  });

  it('keeps product tabs and separate rerun chrome', () => {
    const page = read('pages/accountant/BatchItemReviewWorkspace.tsx');
    expect(page).toContain('employee-review-tabs--product');
    expect(page).toContain('batch-review-rerun');
    expect(page).toContain('batch-review-view-chrome');
  });

  it('search uses logical padding so the icon does not overlap text', () => {
    const css = read('pages/employee/PayslipMonthWorkspace.css');
    expect(css).toContain('padding-inline-start: 2.65rem');
    expect(css).toContain('inset-inline-start: 0.4rem');
  });
});
