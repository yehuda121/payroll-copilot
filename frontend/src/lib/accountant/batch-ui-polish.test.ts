import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = join(process.cwd(), 'src');

function read(rel: string): string {
  return readFileSync(join(root, rel), 'utf8');
}

describe('Batch UI polish source contracts', () => {
  it('reserves bulk actions in top chrome and keeps Select All compact', () => {
    const page = read('pages/accountant/BulkPayrollUpload.tsx');
    const he = read('i18n/locales/accountant.he.json');
    expect(page).toContain('accountant-bulk__bulk-bar--reserved');
    expect(page).toContain('accountant-bulk__chrome');
    expect(page).toMatch(/disabled=\{bulkBusy \|\| selectedCount === 0\}/);
    expect(he).toContain('"selectAll": "בחר הכל"');
  });

  it('removes AI Chat, Original Document, and duplicate Search from batch toolbar', () => {
    const page = read('pages/accountant/BatchItemReviewWorkspace.tsx');
    expect(page).not.toContain('employee.upload.tabOriginal');
    expect(page).not.toContain('employee.navigation.chat');
    expect(page).not.toContain('GuestChatPanel');
    expect(page).not.toContain('FileText');
    expect(page).not.toContain('MessageSquare');
    expect(page).toContain('batch-resolution-search__field--integrated');
    expect(page).toContain('batch-review-view-chrome');
    expect(page).toContain('batch-review-rerun');
    expect(page).toContain('employee-review-tabs--product');
    expect(page).toContain("presentation=\"checkRows\"");
  });

  it('keeps exactly three primary batch result tabs', () => {
    const page = read('pages/accountant/BatchItemReviewWorkspace.tsx');
    expect(page).toContain("['digital', 'employee.upload.tabDigital']");
    expect(page).toContain("['employee_checks', 'employee.workspace.tabEmployeeChecks']");
    expect(page).toContain("['law_checks', 'employee.workspace.tabLawChecks']");
    expect(page).not.toMatch(/PrimaryTab = .*original/);
  });
});
