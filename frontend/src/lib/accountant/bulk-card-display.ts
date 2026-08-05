import type { BatchExtractedEmployee } from '../../types/api';

/** Card title: always the payslip-extracted name; never status or matched profile. */
export function bulkCardDisplayName(
  item: BatchExtractedEmployee,
  unnamedLabel: string,
): string {
  const extracted = item.extracted_employee_name?.trim();
  if (extracted) return extracted;
  return unnamedLabel;
}

export function identifierMatchWarningKey(
  code: string | null | undefined,
): string | null {
  if (!code) return null;
  return `accountant.bulk.identifierWarnings.${code}`;
}
