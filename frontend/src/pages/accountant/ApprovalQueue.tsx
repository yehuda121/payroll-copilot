import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { DataTable } from '../../components/ui/DataTable';
import { EmptyState, LoadingOverlay, useConfirmDialog } from '../../components/ui/Dialog';
import { getAccountantErrorMessage } from '../../i18n/accountantLabels';
import { useAppLocale } from '../../hooks/useAppLocale';
import { formatDateTime, formatPercent } from '../../lib/formatLocale';
import { manualReviewService, type ManualReviewItem } from '../../services/batch';
import { complianceService } from '../../services/compliance';

export function ApprovalQueuePage() {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const { confirm } = useConfirmDialog();
  const [items, setItems] = useState<ManualReviewItem[]>([]);
  const [diffs, setDiffs] = useState<unknown[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [review, proposals] = await Promise.all([
        manualReviewService.list(true),
        complianceService.listDiffProposals(),
      ]);
      setItems(review);
      setDiffs(proposals);
      setError(null);
    } catch {
      setError(getAccountantErrorMessage('loadFailed', t));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const resolve = async (
    item: ManualReviewItem,
    status: 'resolved_create' | 'resolved_attach' | 'dismissed',
  ) => {
    const messageKey =
      status === 'resolved_create'
        ? 'accountant.reviewQueue.resolveCreate'
        : status === 'resolved_attach'
          ? 'accountant.reviewQueue.resolveAttach'
          : 'accountant.reviewQueue.resolveDismiss';
    const ok = await confirm({
      title: t('accountant.reviewQueue.resolveTitle'),
      message: t(messageKey),
      confirmLabel: t('common.confirm'),
      cancelLabel: t('common.cancel'),
      variant: status === 'dismissed' ? 'warning' : 'default',
    });
    if (!ok) return;
    await manualReviewService.resolve(item.id, status);
    await load();
  };

  return (
    <PortalPage
      title={t('accountant.reviewQueue.title')}
      description={t('accountant.reviewQueue.description')}
    >
      {error && <p className="chat-panel__error">{error}</p>}
      <div className="panel-relative" aria-busy={loading}>
        {loading && items.length === 0 && (
          <LoadingOverlay label={t('accountant.reviewQueue.loading')} />
        )}
        <h3>{t('accountant.reviewQueue.manualHeading')}</h3>
        {!loading && items.length === 0 ? (
          <EmptyState
            title={t('accountant.reviewQueue.emptyTitle')}
            description={t('accountant.reviewQueue.emptyDescription')}
            action={
              <Link to="/accountant/bulk-upload" className="btn btn--secondary">
                {t('accountant.batches.uploadTitle')}
              </Link>
            }
          />
        ) : (
          <DataTable<ManualReviewItem & Record<string, unknown>>
            columns={[
              { key: 'reason', header: t('accountant.reviewQueue.colReason') },
              {
                key: 'confidence',
                header: t('accountant.reviewQueue.colConfidence'),
                render: (row) =>
                  row.confidence == null
                    ? t('common.emDash')
                    : formatPercent(row.confidence, locale),
              },
              {
                key: 'national_id_masked',
                header: t('accountant.reviewQueue.colNationalId'),
                render: (row) => row.national_id_masked ?? t('common.emDash'),
              },
              {
                key: 'created_at',
                header: t('accountant.reviewQueue.colCreated'),
                render: (row) => formatDateTime(row.created_at, locale),
              },
              {
                key: 'actions',
                header: t('common.actions'),
                render: (row) => (
                  <div className="table-actions">
                    <button
                      type="button"
                      className="btn btn--ghost"
                      onClick={() => void resolve(row, 'resolved_create')}
                    >
                      {t('accountant.reviewQueue.actionCreate')}
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost"
                      onClick={() => void resolve(row, 'resolved_attach')}
                    >
                      {t('accountant.reviewQueue.actionAttach')}
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost"
                      onClick={() => void resolve(row, 'dismissed')}
                    >
                      {t('accountant.reviewQueue.actionDismiss')}
                    </button>
                  </div>
                ),
              },
            ]}
            data={items as Array<ManualReviewItem & Record<string, unknown>>}
          />
        )}

        <h3 className="section-heading">{t('accountant.reviewQueue.diffsHeading')}</h3>
        {diffs.length === 0 ? (
          <EmptyState
            title={t('accountant.reviewQueue.diffsEmptyTitle')}
            description={t('accountant.reviewQueue.diffsEmptyDescription')}
          />
        ) : (
          <pre className="code-block" dir="ltr">
            {JSON.stringify(diffs, null, 2)}
          </pre>
        )}
      </div>
    </PortalPage>
  );
}
