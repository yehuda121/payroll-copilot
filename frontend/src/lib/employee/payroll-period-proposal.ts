/**
 * Payroll period proposal helpers (presentation + publish confirmation).
 * Does not change extraction — only proposes a default when period is missing.
 */

/** Format: 01/MM/YYYY for a payroll workspace period (not "today" unless omitted). */
export function proposedPayrollPeriodValue(
  yearOrNow?: number | Date,
  month?: number,
): string {
  if (typeof yearOrNow === 'number' && typeof month === 'number') {
    const day = '01';
    const mm = String(month).padStart(2, '0');
    const yyyy = String(yearOrNow);
    return `${day}/${mm}/${yyyy}`;
  }
  const now = yearOrNow instanceof Date ? yearOrNow : new Date();
  const day = '01';
  const mm = String(now.getMonth() + 1).padStart(2, '0');
  const yyyy = String(now.getFullYear());
  return `${day}/${mm}/${yyyy}`;
}

export function parseProposedPayrollPeriod(value: string): { year: number; month: number } | null {
  const match = value.trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!match) return null;
  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);
  if (day !== 1 || month < 1 || month > 12 || year < 2000 || year > 2100) return null;
  return { year, month };
}

/** True when payslip has no usable extracted pay_period value. */
export function isPayPeriodMissing(value: unknown): boolean {
  if (value == null) return true;
  return String(value).trim() === '';
}
