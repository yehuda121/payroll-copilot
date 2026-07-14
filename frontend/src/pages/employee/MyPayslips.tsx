import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import {
  employeePortalService,
  type EmployeePayslipListItem,
} from '../../services/employeePortal';

export function MyPayslipsPage() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<EmployeePayslipListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const items = await employeePortalService.listMyPayslips();
        if (!cancelled) setRows(items);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t('common.error'));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [t]);

  return (
    <PortalPage title={t('employee.payslips.pageTitle')} description={t('employee.payslips.pageDescription')}>
      <div className="employee-payslips">
        <div className="employee-payslips__actions">
          <Link to="/employee/upload" className="btn btn--primary">
            {t('employee.payslips.uploadCta')}
          </Link>
        </div>
        {loading && <p>{t('common.loading')}</p>}
        {error && <p className="chat-panel__error">{error}</p>}
        {!loading && !error && rows.length === 0 && (
          <p className="employee-payslips__empty">{t('employee.payslips.empty')}</p>
        )}
        {!loading && rows.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>{t('employee.payslips.columns.filename')}</th>
                <th>{t('employee.payslips.columns.period')}</th>
                <th>{t('employee.payslips.columns.status')}</th>
                <th>{t('employee.payslips.columns.uploadedAt')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.document_id}>
                  <td>{row.original_filename}</td>
                  <td>
                    {row.period_month && row.period_year
                      ? `${row.period_month}/${row.period_year}`
                      : '—'}
                  </td>
                  <td>{row.status}</td>
                  <td>{row.uploaded_at ? new Date(row.uploaded_at).toLocaleString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </PortalPage>
  );
}
