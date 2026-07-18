import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { DataTable } from '../../components/ui/DataTable';
import { EmptyState, LoadingOverlay, useConfirmDialog } from '../../components/ui/Dialog';
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

function StatusPill({
  status,
  incomplete,
}: {
  status: EmployeeStatus;
  incomplete?: boolean;
}) {
  const { t } = useTranslation();
  if (incomplete) {
    return <span className="status-badge status-badge--incomplete">{t('accountant.employees.incomplete')}</span>;
  }
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
  const { confirm } = useConfirmDialog();
  const [rows, setRows] = useState<EmployeeRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<string>('');
  const [disablingNumber, setDisablingNumber] = useState<string | null>(null);
  const requestSequence = useRef(0);

  const load = useCallback(async (nextQuery: string, nextStatus: string) => {
    const requestId = ++requestSequence.current;
    setLoading(true);
    setError(null);
    try {
      const data = await employeesService.list({
        q: nextQuery || undefined,
        status: nextStatus || undefined,
        includeDisabled: true,
      });
      if (requestId !== requestSequence.current) return;
      setRows(data);
    } catch (err) {
      if (requestId !== requestSequence.current) return;
      const message =
        err instanceof ApiClientError ? err.message : getAccountantErrorMessage('loadFailed', t);
      setError(message);
      setRows([]);
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

  const disableEmployee = async (employeeNumber: string) => {
    const ok = await confirm({
      title: t('accountant.employees.disableTitle'),
      message: t('accountant.employees.disableMessage'),
      confirmLabel: t('accountant.employees.disableConfirm'),
      cancelLabel: t('common.cancel'),
      variant: 'danger',
    });
    if (!ok) return;
    setDisablingNumber(employeeNumber);
    setError(null);
    try {
      await employeesService.disable(employeeNumber);
      await load(query.trim(), status);
    } catch (err) {
      const message =
        err instanceof ApiClientError
          ? err.message
          : getAccountantErrorMessage('disableFailed', t);
      setError(message);
      console.error('Disable employee failed', err);
    } finally {
      setDisablingNumber(null);
    }
  };

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
            <option value="terminated">{getEmployeeStatusLabel('terminated', t)}</option>
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

      <div className="panel-relative">
        {loading && <LoadingOverlay label={t('accountant.employees.loading')} />}
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
                render: (row) => (
                  <StatusPill status={row.status} incomplete={row.profileIncomplete} />
                ),
              },
              {
                key: 'actions',
                header: t('common.actions'),
                sortable: false,
                render: (row) => (
                  <div className="table-actions">
                    <Link
                      to={`/accountant/employees/${row.employeeNumber}/edit`}
                      className="btn btn--ghost"
                      onClick={(event) => event.stopPropagation()}
                    >
                      {t('common.edit')}
                    </Link>
                    {row.status !== 'disabled' && (
                      <button
                        type="button"
                        className="btn btn--ghost"
                        disabled={disablingNumber === row.employeeNumber}
                        onClick={(event) => {
                          event.stopPropagation();
                          void disableEmployee(row.employeeNumber);
                        }}
                      >
                        {disablingNumber === row.employeeNumber
                          ? t('common.saving')
                          : t('common.disable')}
                      </button>
                    )}
                  </div>
                ),
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
