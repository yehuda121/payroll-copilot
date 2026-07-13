import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { DataTable } from '../../components/ui/DataTable';
import { EmptyState, LoadingOverlay } from '../../components/ui/Dialog';
import { getAccountantErrorMessage } from '../../i18n/accountantLabels';
import { useAppLocale } from '../../hooks/useAppLocale';
import { formatDateTime } from '../../lib/formatLocale';
import { auditLogsService } from '../../services/employees';
import type { AuditLogItem } from '../../types/employee';

export function AccountantAuditLogsPage() {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const [rows, setRows] = useState<AuditLogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        setRows(await auditLogsService.list(200));
        setError(null);
      } catch {
        setError(getAccountantErrorMessage('loadFailed', t));
      } finally {
        setLoading(false);
      }
    })();
  }, [t]);

  return (
    <PortalPage
      title={t('accountant.auditLogs.title')}
      description={t('accountant.auditLogs.description')}
    >
      {error && <p className="chat-panel__error">{error}</p>}
      <div className="panel-relative">
        {loading && <LoadingOverlay label={t('accountant.auditLogs.loading')} />}
        {!loading && rows.length === 0 ? (
          <EmptyState
            title={t('accountant.auditLogs.emptyTitle')}
            description={t('accountant.auditLogs.emptyDescription')}
          />
        ) : (
          <DataTable<AuditLogItem & Record<string, unknown>>
            columns={[
              {
                key: 'created_at',
                header: t('accountant.auditLogs.colWhen'),
                render: (row) => formatDateTime(row.created_at, locale),
              },
              { key: 'action', header: t('accountant.auditLogs.colAction') },
              { key: 'resource_type', header: t('accountant.auditLogs.colResource') },
              {
                key: 'resource_id',
                header: t('accountant.auditLogs.colResourceId'),
                render: (row) => row.resource_id ?? t('common.emDash'),
              },
              {
                key: 'details',
                header: t('accountant.auditLogs.colDetails'),
                render: (row) => (
                  <code className="audit-details" dir="ltr">
                    {JSON.stringify(row.details)}
                  </code>
                ),
              },
            ]}
            data={rows as Array<AuditLogItem & Record<string, unknown>>}
          />
        )}
      </div>
    </PortalPage>
  );
}
