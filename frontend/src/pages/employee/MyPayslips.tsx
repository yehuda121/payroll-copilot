import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { useEmployeeWorkspace } from '../../features/employee/EmployeeWorkspaceContext';
import { mapPresentationStatus } from '../../lib/employee/presentation-status';
import {
  type PayrollMonthsResponse,
} from '../../services/employeePortal';
import { useAppLocale } from '../../hooks/useAppLocale';
import './MyPayslips.css';

function monthLabel(month: number, locale: string): string {
  return new Intl.DateTimeFormat(locale, { month: 'long' }).format(new Date(2020, month - 1, 1));
}

function StatusBadge({ code }: { code: string }) {
  const { t } = useTranslation();
  const visual = mapPresentationStatus(code);
  return (
    <span className={`employee-status-badge ${visual.cssClass}`} title={t(visual.labelKey)}>
      <span className="employee-status-badge__icon" aria-hidden="true">
        {visual.icon}
      </span>
      <span>{t(visual.labelKey)}</span>
    </span>
  );
}

export function MyPayslipsPage() {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const navigate = useNavigate();
  const { api: workspaceApi, basePath } = useEmployeeWorkspace();
  const currentYear = new Date().getFullYear();

  const [year, setYear] = useState(currentYear);
  const [data, setData] = useState<PayrollMonthsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const years = useMemo(() => {
    const fromApi = data?.available_years ?? [];
    return Array.from(new Set([...fromApi, currentYear, year])).sort((a, b) => b - a);
  }, [data, currentYear, year]);

  const loadYear = async (nextYear: number) => {
    setLoading(true);
    setError(null);
    try {
      const response = await workspaceApi.listPayrollMonths(nextYear);
      setData(response);
      setYear(response.year);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.error'));
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadYear(year);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initial load
  }, []);

  return (
    <PortalPage
      title={t('employee.payslips.pageTitle')}
      description={t('employee.payslips.pageDescription')}
    >
      <div className="employee-payslips">
        <div className="employee-payslips__toolbar">
          <label>
            <span>{t('employee.payslips.yearLabel')}</span>
            <select
              value={year}
              onChange={(event) => {
                const next = Number(event.target.value);
                setYear(next);
                void loadYear(next);
              }}
            >
              {years.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
        </div>

        {error && (
          <p className="chat-panel__error" role="alert">
            {error}
          </p>
        )}
        {loading ? (
          <p role="status">{t('common.loading')}</p>
        ) : (
          <div className="employee-payslips__grid" role="list">
            {(data?.months ?? Array.from({ length: 12 }, (_, i) => ({ month: i + 1 }))).map(
              (row) => {
                const month = row.month;
                const status =
                  'presentation_status' in row
                    ? String(row.presentation_status)
                    : 'missing';
                return (
                  <button
                    key={month}
                    type="button"
                    role="listitem"
                    className="employee-month-card"
                    onClick={() => navigate(`${basePath}/payslips/${year}/${month}`)}
                  >
                    <div className="employee-month-card__head">
                      <strong>{monthLabel(month, locale)}</strong>
                      <StatusBadge code={status} />
                    </div>
                    <span className="employee-month-card__meta">
                      {t('employee.workspace.openMonth')}
                    </span>
                  </button>
                );
              },
            )}
          </div>
        )}

        <p className="employee-payslips__footnote">
          <Link to={`${basePath}/documents`}>{t('employee.navigation.documents')}</Link>
        </p>
      </div>
    </PortalPage>
  );
}
