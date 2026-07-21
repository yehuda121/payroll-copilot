import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useEmployeeSession } from '../../auth/EmployeeSessionContext';
import { PortalPage } from '../../components/PortalPage';
import { Skeleton } from '../../components/ui/Skeleton';
import { useEmployeeWorkspace } from '../../features/employee/EmployeeWorkspaceContext';
import { useWorkspacePageCopy } from '../../hooks/useWorkspacePageCopy';
import { mapPresentationStatus } from '../../lib/employee/presentation-status';
import { formatMonthName } from '../../lib/formatLocale';
import { getDisplayError } from '../../lib/getDisplayError';
import { type PayrollMonthsResponse } from '../../services/employeePortal';
import { useAppLocale } from '../../hooks/useAppLocale';
import './MyPayslips.css';

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

function MonthCardSkeleton() {
  return (
    <div className="employee-month-card employee-month-card--skeleton" aria-hidden="true">
      <div className="employee-month-card__head">
        <Skeleton height={18} width="45%" />
        <Skeleton height={18} width={72} rounded />
      </div>
      <Skeleton height={12} width="55%" />
    </div>
  );
}

export function MyPayslipsPage() {
  const { t } = useTranslation();
  const copy = useWorkspacePageCopy();
  const { locale } = useAppLocale();
  const navigate = useNavigate();
  const { api: workspaceApi, basePath } = useEmployeeWorkspace();
  const session = useEmployeeSession();
  const currentYear = new Date().getFullYear();

  const [year, setYear] = useState(currentYear);
  const [data, setData] = useState<PayrollMonthsResponse | null>(
    () => session.getPayrollMonths(currentYear) ?? null,
  );
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const years = useMemo(() => {
    const fromApi = data?.available_years ?? [];
    return Array.from(new Set([...fromApi, currentYear, year])).sort((a, b) => b - a);
  }, [data, currentYear, year]);

  const loadYear = useCallback(
    async (nextYear: number) => {
      const cached = session.getPayrollMonths(nextYear);
      if (cached) {
        setData(cached);
        setYear(cached.year);
      }
      // Keep previous grid visible while refreshing; skeletons only when nothing to show.
      setRefreshing(true);
      setError(null);
      try {
        const response = await workspaceApi.listPayrollMonths(nextYear);
        session.setPayrollMonths(response);
        setData(response);
        setYear(response.year);
      } catch (err) {
        setError(getDisplayError(err, t('common.error')));
        if (!cached && !session.getPayrollMonths(nextYear)) {
          // Only clear when we never had anything for this year.
          setData((prev) => (prev?.year === nextYear ? null : prev));
        }
      } finally {
        setRefreshing(false);
      }
    },
    [session, t, workspaceApi],
  );

  useEffect(() => {
    void loadYear(year);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount + session-scoped cache
  }, []);

  const showSkeletons = !data && refreshing;
  const months =
    data?.months ??
    Array.from({ length: 12 }, (_, index) => ({
      month: index + 1,
      presentation_status: 'missing',
    }));

  return (
    <PortalPage title={copy.payslipsTitle} description={copy.payslipsDescription}>
      <div className="employee-payslips">
        <div className="employee-payslips__toolbar">
          <label>
            <span>{t('employee.payslips.yearLabel')}</span>
            <select
              value={year}
              onChange={(event) => {
                const next = Number(event.target.value);
                setYear(next);
                const cached = session.getPayrollMonths(next);
                if (cached) setData(cached);
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
          {refreshing && data ? (
            <span className="employee-payslips__refresh" role="status">
              {t('common.loading')}
            </span>
          ) : null}
        </div>

        {error && (
          <p className="chat-panel__error" role="alert">
            {error}
          </p>
        )}

        <div
          className={`employee-payslips__grid${showSkeletons ? ' employee-payslips__skeleton' : ''}`}
          role="list"
          aria-busy={refreshing}
        >
          {showSkeletons
            ? Array.from({ length: 12 }, (_, index) => <MonthCardSkeleton key={index} />)
            : months.map((row) => {
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
                      <strong>{formatMonthName(month, locale)}</strong>
                      <StatusBadge code={status} />
                    </div>
                    <span className="employee-month-card__meta">
                      {t('employee.workspace.openMonth')}
                    </span>
                  </button>
                );
              })}
        </div>

        <p className="employee-payslips__footnote">
          <Link to={`${basePath}/documents`}>{t('employee.navigation.documents')}</Link>
        </p>
      </div>
    </PortalPage>
  );
}
