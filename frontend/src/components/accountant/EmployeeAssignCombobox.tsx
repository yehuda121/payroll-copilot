/** Searchable employee assign combobox for bulk unknown-employee resolution. */

import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Search } from 'lucide-react';
import { useConfirmDialog } from '../ui/Dialog';
import { FREE_TEXT_MAX_LENGTH, clampFreeTextInput } from '../../lib/validation';
import { employeesService } from '../../services/employees';
import type { EmployeeRecord } from '../../types/employee';
import './EmployeeAssignCombobox.css';

function optionLabel(employee: EmployeeRecord, t: (key: string) => string): string {
  const idPart = employee.nationalIdMasked
    ? `${t('accountant.bulk.assign.idLabel')}: ${employee.nationalIdMasked}`
    : `${t('accountant.bulk.assign.idLabel')}: ${t('common.emDash')}`;
  return `${employee.fullName} — ${idPart} — ${t('accountant.bulk.assign.numberLabel')}: ${employee.employeeNumber}`;
}

export type EmployeeAssignComboboxProps = {
  disabled?: boolean;
  onAssigned: (employee: EmployeeRecord) => Promise<void> | void;
};

export function EmployeeAssignCombobox({
  disabled = false,
  onAssigned,
}: EmployeeAssignComboboxProps) {
  const { t } = useTranslation();
  const { confirm } = useConfirmDialog();
  const listId = useId();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [options, setOptions] = useState<EmployeeRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const handle = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void (async () => {
        setLoading(true);
        setError(null);
        try {
          const q = query.trim();
          const rows = await employeesService.list({
            q: q || undefined,
            includeDisabled: false,
          });
          // Digits-only queries: also try exact national-ID match (org-scoped).
          const digits = q.replace(/\D/g, '');
          if (digits.length >= 5) {
            try {
              const matched = await employeesService.matchNationalId(digits);
              if (
                matched.matched &&
                matched.employee &&
                !rows.some((row) => row.id === matched.employee!.id)
              ) {
                rows.unshift(matched.employee);
              }
            } catch {
              // Match endpoint is optional enrichment; list results still usable.
            }
          }
          if (!cancelled) setOptions(rows);
        } catch {
          if (!cancelled) {
            setOptions([]);
            setError(t('common.error'));
          }
        } finally {
          if (!cancelled) setLoading(false);
        }
      })();
    }, 220);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, t]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const digits = needle.replace(/\D/g, '');
    if (!needle) return options;
    return options.filter((employee) => {
      const hay = [
        employee.fullName,
        employee.employeeNumber,
        employee.nationalIdMasked ?? '',
        employee.firstName,
        employee.lastName,
      ]
        .join(' ')
        .toLowerCase();
      if (hay.includes(needle)) return true;
      if (digits && (employee.nationalIdMasked ?? '').replace(/\D/g, '').includes(digits)) {
        return true;
      }
      return false;
    });
  }, [options, query]);

  const pick = async (employee: EmployeeRecord) => {
    const accepted = await confirm({
      title: t('accountant.bulk.assign.confirmTitle'),
      message: t('accountant.bulk.assign.confirmMessage', {
        employee_name: employee.fullName,
        national_id: employee.nationalIdMasked || t('common.emDash'),
      }),
      confirmLabel: t('accountant.bulk.assign.confirmAction'),
      cancelLabel: t('common.cancel'),
      variant: 'warning',
    });
    if (!accepted) return;
    setBusy(true);
    setError(null);
    try {
      await onAssigned(employee);
      setOpen(false);
      setQuery('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('common.error'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="employee-assign-combobox" ref={rootRef}>
      <label className="employee-assign-combobox__field">
        <span className="visually-hidden">{t('accountant.bulk.assign.searchLabel')}</span>
        <span className="employee-assign-combobox__icon" aria-hidden="true">
          <Search size={16} />
        </span>
        <input
          className="pc-form-control employee-assign-combobox__input"
          type="search"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          disabled={disabled || busy}
          maxLength={FREE_TEXT_MAX_LENGTH.searchQuery}
          value={query}
          placeholder={t('accountant.bulk.assign.searchPlaceholder')}
          onChange={(event) => {
            setQuery(
              clampFreeTextInput(event.target.value, FREE_TEXT_MAX_LENGTH.searchQuery),
            );
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
        />
      </label>
      {open && (
        <ul
          id={listId}
          className="employee-assign-combobox__list"
          role="listbox"
          aria-label={t('accountant.bulk.assign.searchLabel')}
        >
          {loading && (
            <li className="employee-assign-combobox__empty">{t('common.loading')}</li>
          )}
          {!loading && filtered.length === 0 && (
            <li className="employee-assign-combobox__empty">
              {t('accountant.unknown.noResults', { defaultValue: t('common.emDash') })}
            </li>
          )}
          {!loading &&
            filtered.map((employee) => (
              <li key={employee.id} role="option">
                <button
                  type="button"
                  className="employee-assign-combobox__option"
                  disabled={disabled || busy}
                  onClick={() => void pick(employee)}
                >
                  {optionLabel(employee, t)}
                </button>
              </li>
            ))}
        </ul>
      )}
      {error && (
        <p className="chat-panel__error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
