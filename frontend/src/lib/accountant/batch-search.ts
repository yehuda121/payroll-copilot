import type { BatchExtractedEmployee } from '../../types/api';

/** Normalize text for client-side batch item search (HE/EN/AR safe). */
export function normalizeBatchSearchText(value: string): string {
  return value
    .normalize('NFKC')
    .trim()
    .toLocaleLowerCase()
    .replace(/\s+/g, ' ');
}

function periodLabel(item: BatchExtractedEmployee): string {
  if (item.payroll_year == null || item.payroll_month == null) return '';
  return `${item.payroll_year}-${String(item.payroll_month).padStart(2, '0')} ${item.payroll_month}/${item.payroll_year}`;
}

/** Haystack fields used by the extracted-batch search box. */
export function batchItemSearchHaystack(item: BatchExtractedEmployee): string {
  return normalizeBatchSearchText(
    [
      item.employee_name ?? '',
      item.employee_number ?? '',
      item.national_id_masked ?? '',
      periodLabel(item),
      String(item.slip_index + 1),
    ].join(' '),
  );
}

/**
 * Substring match after normalization. Multi-token queries require every
 * token to appear somewhere in the haystack (order-independent).
 */
export function matchesBatchSearchQuery(item: BatchExtractedEmployee, query: string): boolean {
  const normalizedQuery = normalizeBatchSearchText(query);
  if (!normalizedQuery) return true;
  const haystack = batchItemSearchHaystack(item);
  const tokens = normalizedQuery.split(' ').filter(Boolean);
  if (tokens.length <= 1) {
    return haystack.includes(normalizedQuery);
  }
  return tokens.every((token) => haystack.includes(token));
}
