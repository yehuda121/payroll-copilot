import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { DataTable } from '../../components/ui/DataTable';
import { EmptyState, LoadingOverlay } from '../../components/ui/Dialog';
import {
  getAccountantErrorMessage,
  getEmployeeStatusLabel,
  getEmploymentTypeLabel,
} from '../../i18n/accountantLabels';
import { useAppLocale } from '../../hooks/useAppLocale';
import { formatCurrencyILS } from '../../lib/formatLocale';
import { ApiClientError } from '../../services/api';
import { employeesService } from '../../services/employees';
import type { EmployeeRecord, EmployeeStatus } from '../../types';

/** In-memory list cache so the Employees page can remount without a blank reload. */
const employeesListCache = new Map<string, EmployeeRecord[]>();

export function invalidateEmployeesListCache(): void {
  employeesListCache.clear();
}

function employeesListCacheKey(query: string, status: string): string {
  return `${query}\u0000${status}`;
}

function StatusPill({ status }: { status: EmployeeStatus }) {
  const { t } = useTranslation();
  return (
    <span className={`status-badge status-badge--${status}`}>
      {getEmployeeStatusLabel(status, t)}
    </span>
  );
}

export function EmployeeManagementPage() {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<string>('');
  const initialCacheKey = employeesListCacheKey('', '');
  const [rows, setRows] = useState<EmployeeRecord[]>(
    () => employeesListCache.get(initialCacheKey) ?? [],
  );
  const [loading, setLoading] = useState(() => !employeesListCache.has(initialCacheKey));
  const [error, setError] = useState<string | null>(null);
  const requestSequence = useRef(0);

  const load = useCallback(async (nextQuery: string, nextStatus: string) => {
    const cacheKey = employeesListCacheKey(nextQuery, nextStatus);
    const cached = employeesListCache.get(cacheKey);
    if (cached) {
      setRows(cached);
    }

    const requestId = ++requestSequence.current;
    setError(null);
    if (!cached) {
      setLoading(true);
    }
    try {
      const data = await employeesService.list({
        q: nextQuery || undefined,
        status: nextStatus || undefined,
        // Default "all" hides disabled; explicit status=disabled still returns them.
        includeDisabled: false,
      });
      if (requestId !== requestSequence.current) return;
      employeesListCache.set(cacheKey, data);
      setRows(data);
    } catch (err) {
      if (requestId !== requestSequence.current) return;
      const message =
        err instanceof ApiClientError ? err.message : getAccountantErrorMessage('loadFailed', t);
      setError(message);
    } finally {
      if (requestId === requestSequence.current) setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(query.trim(), status), 250);
    return () => window.clearTimeout(timer);
  }, [load, query, status]);

  const filteredHint = useMemo(() => {
    if (!rows.length) return t('accountant.employees.noMatch');
    return undefined;
  }, [rows.length, t]);

  return (
    <PortalPage
      title={t('accountant.employees.title')}
      description={t('accountant.employees.description')}
    >
      <div className="accountant-toolbar">
        <div className="accountant-toolbar__filters">
          <input
            type="search"
            placeholder={t('accountant.employees.searchPlaceholder')}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label={t('accountant.employees.searchAria')}
          />
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            aria-label={t('accountant.employees.filterStatusAria')}
          >
            <option value="">{t('accountant.employees.allStatuses')}</option>
            <option value="active">{getEmployeeStatusLabel('active', t)}</option>
            <option value="on_leave">{getEmployeeStatusLabel('on_leave', t)}</option>
            <option value="disabled">{getEmployeeStatusLabel('disabled', t)}</option>
          </select>
          <button
            type="button"
            className="btn btn--secondary"
            onClick={() => void load(query.trim(), status)}
          >
            {t('common.refresh')}
          </button>
        </div>
        <Link to="/accountant/employees/add" className="btn btn--primary">
          {t('accountant.employees.add')}
        </Link>
      </div>

      {error && (
        <p className="chat-panel__error" role="alert">
          {error}
        </p>
      )}

      <div className="panel-relative" aria-busy={loading}>
        {loading && rows.length === 0 && (
          <LoadingOverlay label={t('accountant.employees.loading')} />
        )}
        {!loading && rows.length === 0 ? (
          <EmptyState
            title={t('accountant.employees.emptyTitle')}
            description={t('accountant.employees.emptyDescription')}
            action={
              <Link to="/accountant/employees/add" className="btn btn--primary">
                {t('accountant.employees.emptyAddFirst')}
              </Link>
            }
          />
        ) : (
          <DataTable<EmployeeRecord & Record<string, unknown>>
            sortable
            ariaLabel={t('accountant.employees.title')}
            getRowKey={(row) => row.employeeNumber}
            onRowClick={(row) =>
              navigate(`/accountant/employees/${row.employeeNumber}/workspace`)
            }
            columns={[
              { key: 'employeeNumber', header: t('accountant.employees.colNumber') },
              { key: 'fullName', header: t('accountant.employees.colFullName') },
              { key: 'email', header: t('accountant.employees.colEmail') },
              { key: 'department', header: t('accountant.employees.colDepartment') },
              {
                key: 'employmentType',
                header: t('accountant.employees.colEmployment'),
                sortValue: (row) => row.employmentType,
                render: (row) => getEmploymentTypeLabel(row.employmentType, t),
              },
              {
                key: 'baseSalaryOrRate',
                header: t('accountant.employees.colBaseRate'),
                sortValue: (row) => Number(row.baseSalaryOrRate || 0),
                render: (row) =>
                  row.salaryType === 'monthly'
                    ? formatCurrencyILS(Number(row.baseSalaryOrRate || 0), locale)
                    : t('accountant.employees.hourlyRate', {
                        amount: formatCurrencyILS(Number(row.baseSalaryOrRate || 0), locale),
                      }),
              },
              {
                key: 'status',
                header: t('accountant.employees.colStatus'),
                sortValue: (row) => row.status,
                render: (row) => <StatusPill status={row.status} />,
              },
            ]}
            data={rows as Array<EmployeeRecord & Record<string, unknown>>}
            emptyMessage={filteredHint}
          />
        )}
      </div>
    </PortalPage>
  );
}
