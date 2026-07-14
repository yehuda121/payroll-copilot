import { useMemo, useState, type KeyboardEvent, type ReactNode } from 'react';
import './ui.css';

export type SortDirection = 'asc' | 'desc';

export type DataTableColumn<T> = {
  key: keyof T | string;
  header: string;
  /** When false, column cannot be sorted (e.g. Actions). Default true if sortable table. */
  sortable?: boolean;
  /** Value used for sorting when render is custom. */
  sortValue?: (row: T) => string | number | boolean | null | undefined;
  render?: (row: T) => ReactNode;
  className?: string;
};

export type DataTableProps<T> = {
  columns: DataTableColumn<T>[];
  data: T[];
  emptyMessage?: string;
  /** Row identity for React keys. */
  getRowKey?: (row: T, index: number) => string;
  /** Enable interactive sorting on sortable columns. */
  sortable?: boolean;
  /** Initial sort; null means natural/default order. */
  defaultSort?: { key: string; direction: SortDirection } | null;
  onRowClick?: (row: T) => void;
  /** Accessible name for the table. */
  ariaLabel?: string;
};

type ActiveSort = { key: string; direction: SortDirection } | null;

function compareValues(a: unknown, b: unknown): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  if (typeof a === 'boolean' && typeof b === 'boolean') return Number(a) - Number(b);
  return String(a).localeCompare(String(b), undefined, { sensitivity: 'base', numeric: true });
}

function resolveSortValue<T extends Record<string, unknown>>(
  row: T,
  column: DataTableColumn<T>,
): unknown {
  if (column.sortValue) return column.sortValue(row);
  return row[column.key as keyof T];
}

export function DataTable<T extends Record<string, unknown>>({
  columns,
  data,
  emptyMessage = 'No records found.',
  getRowKey,
  sortable = false,
  defaultSort = null,
  onRowClick,
  ariaLabel,
}: DataTableProps<T>) {
  const [sort, setSort] = useState<ActiveSort>(defaultSort);

  const sortedData = useMemo(() => {
    if (!sortable || !sort) return data;
    const column = columns.find((col) => String(col.key) === sort.key);
    if (!column || column.sortable === false) return data;

    // Stable sort: decorate with original index.
    return data
      .map((row, index) => ({ row, index }))
      .sort((left, right) => {
        const cmp = compareValues(
          resolveSortValue(left.row, column),
          resolveSortValue(right.row, column),
        );
        if (cmp !== 0) return sort.direction === 'asc' ? cmp : -cmp;
        return left.index - right.index;
      })
      .map((entry) => entry.row);
  }, [columns, data, sort, sortable]);

  const cycleSort = (key: string) => {
    setSort((current) => {
      if (!current || current.key !== key) return { key, direction: 'asc' };
      if (current.direction === 'asc') return { key, direction: 'desc' };
      return null;
    });
  };

  const onRowKeyDown = (event: KeyboardEvent<HTMLTableRowElement>, row: T) => {
    if (!onRowClick) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onRowClick(row);
    }
  };

  return (
    <div className="data-table-wrapper">
      <table className="data-table" aria-label={ariaLabel}>
        <thead>
          <tr>
            {columns.map((col) => {
              const key = String(col.key);
              const canSort = sortable && col.sortable !== false;
              const isActive = sort?.key === key;
              const ariaSort = !canSort
                ? undefined
                : isActive
                  ? sort.direction === 'asc'
                    ? 'ascending'
                    : 'descending'
                  : 'none';

              if (!canSort) {
                return (
                  <th key={key} className={col.className} scope="col">
                    {col.header}
                  </th>
                );
              }

              return (
                <th
                  key={key}
                  className={`data-table__th--sortable${isActive ? ' data-table__th--sorted' : ''} ${col.className ?? ''}`.trim()}
                  scope="col"
                  aria-sort={ariaSort}
                >
                  <button
                    type="button"
                    className="data-table__sort-btn"
                    onClick={() => cycleSort(key)}
                  >
                    <span>{col.header}</span>
                    <span className="data-table__sort-icon" aria-hidden="true">
                      {!isActive ? '↕' : sort.direction === 'asc' ? '↑' : '↓'}
                    </span>
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sortedData.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="data-table__empty">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            sortedData.map((row, index) => (
              <tr
                key={getRowKey ? getRowKey(row, index) : index}
                className={onRowClick ? 'data-table__row--clickable' : undefined}
                onClick={
                  onRowClick
                    ? () => {
                        // Avoid navigating when the user is selecting cell text.
                        const selection = window.getSelection();
                        if (selection && selection.toString().length > 0) return;
                        onRowClick(row);
                      }
                    : undefined
                }
                onKeyDown={onRowClick ? (event) => onRowKeyDown(event, row) : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                role={onRowClick ? 'link' : undefined}
              >
                {columns.map((col) => (
                  <td
                    key={String(col.key)}
                    className={col.className}
                    onClick={
                      String(col.key) === 'actions'
                        ? (event) => event.stopPropagation()
                        : undefined
                    }
                  >
                    {col.render ? col.render(row) : String(row[col.key as keyof T] ?? '')}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
