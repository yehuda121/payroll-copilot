import type { BatchExtractedEmployee } from '../../types/api';

/** Visible Select All applies only to currently filtered/visible deletable rows. */
export function canBulkDeleteItem(item: BatchExtractedEmployee): boolean {
  return Boolean(item.document_id) && item.review_status !== 'ignored';
}

export function canBulkPublishItem(item: BatchExtractedEmployee): boolean {
  if (!item.document_id || !item.employee_number) return false;
  if (item.publication_status === 'published') return false;
  if (item.status === 'processing' || item.status === 'unknown_employee') return false;
  if (item.review_status === 'ignored') return false;
  return item.status === 'passed' || item.status === 'warning' || item.status === 'failed';
}

export function computeSelectAllState(
  visibleSelectableIds: string[],
  selectedIds: ReadonlySet<string>,
): { allSelected: boolean; someSelected: boolean; selectedVisibleCount: number } {
  const selectedVisibleCount = visibleSelectableIds.filter((id) => selectedIds.has(id)).length;
  const allSelected =
    visibleSelectableIds.length > 0 && selectedVisibleCount === visibleSelectableIds.length;
  const someSelected =
    selectedVisibleCount > 0 && selectedVisibleCount < visibleSelectableIds.length;
  return { allSelected, someSelected, selectedVisibleCount };
}

export function applySelectAllVisible(
  selectedIds: ReadonlySet<string>,
  visibleSelectableIds: string[],
  checked: boolean,
): Set<string> {
  const next = new Set(selectedIds);
  for (const id of visibleSelectableIds) {
    if (checked) next.add(id);
    else next.delete(id);
  }
  return next;
}

export function pruneSelectionToAliveIds(
  selectedIds: ReadonlySet<string>,
  aliveIds: ReadonlySet<string>,
): Set<string> {
  const next = new Set<string>();
  for (const id of selectedIds) {
    if (aliveIds.has(id)) next.add(id);
  }
  return next;
}
