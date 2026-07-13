import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
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
  const { confirm } = useConfirmDialog();
  const [rows, setRows] = useState<EmployeeRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<string>('');

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await employeesService.list({
        q: query || undefined,
        status: status || undefined,
        includeDisabled: true,
      });
      setRows(data);
    } catch {
      setError(getAccountantErrorMessage('loadFailed', t));
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
    try {
      await employeesService.disable(employeeNumber);
      await load();
    } catch {
      setError(getAccountantErrorMessage('saveFailed', t));
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
          <button type="button" className="btn btn--secondary" onClick={() => void load()}>
            {t('common.apply')}
          </button>
        </div>
        <Link to="/accountant/employees/add" className="btn btn--primary">
          {t('accountant.employees.add')}
        </Link>
      </div>

      {error && <p className="chat-panel__error">{error}</p>}

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
            columns={[
              { key: 'employeeNumber', header: t('accountant.employees.colNumber') },
              { key: 'fullName', header: t('accountant.employees.colFullName') },
              { key: 'email', header: t('accountant.employees.colEmail') },
              { key: 'department', header: t('accountant.employees.colDepartment') },
              {
                key: 'employmentType',
                header: t('accountant.employees.colEmployment'),
                render: (row) => getEmploymentTypeLabel(row.employmentType, t),
              },
              {
                key: 'baseSalaryOrRate',
                header: t('accountant.employees.colBaseRate'),
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
                render: (row) => (
                  <StatusPill status={row.status} incomplete={row.profileIncomplete} />
                ),
              },
              {
                key: 'actions',
                header: t('common.actions'),
                render: (row) => (
                  <div className="table-actions">
                    <Link
                      to={`/accountant/employees/${row.employeeNumber}`}
                      className="btn btn--ghost"
                    >
                      {t('accountant.employees.profile')}
                    </Link>
                    <Link
                      to={`/accountant/employees/${row.employeeNumber}/edit`}
                      className="btn btn--ghost"
                    >
                      {t('common.edit')}
                    </Link>
                    {row.status !== 'disabled' && (
                      <button
                        type="button"
                        className="btn btn--ghost"
                        onClick={() => void disableEmployee(row.employeeNumber)}
                      >
                        {t('common.disable')}
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
