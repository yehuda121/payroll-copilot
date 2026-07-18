import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { EmptyState } from '../../components/ui/Dialog';
import { UploadPanel } from '../../components/ui/UploadPanel';
import { useBatchNavigationGuard } from '../../features/accountant/BatchNavigationGuard';
import { getAccountantErrorMessage } from '../../i18n/accountantLabels';
import { batchService } from '../../services/batch';
import type { BatchEmployeeStatus, BatchExtractedEmployee } from '../../types/api';
import './BulkPayrollUpload.css';

const FILTERS: Array<{ id: BatchEmployeeStatus | 'all'; labelKey: string }> = [
  { id: 'all', labelKey: 'accountant.bulk.filters.all' },
  { id: 'passed', labelKey: 'accountant.bulk.filters.passed' },
  { id: 'warning', labelKey: 'accountant.bulk.filters.warning' },
  { id: 'failed', labelKey: 'accountant.bulk.filters.failed' },
  { id: 'unknown_employee', labelKey: 'accountant.bulk.filters.unknown' },
  { id: 'processing', labelKey: 'accountant.bulk.filters.processing' },
];

const SUMMARY_STATUSES: BatchEmployeeStatus[] = [
  'passed',
  'warning',
  'failed',
  'unknown_employee',
  'processing',
];

function statusLabelKey(status: string): string {
  return `accountant.bulk.status.${status}`;
}

export function BulkPayrollUploadPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const batch = useBatchNavigationGuard();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    void batch.refreshBatch();
  }, [batch.refreshBatch]);

  useEffect(() => {
    if (batch.savedScrollY > 0) {
      window.requestAnimationFrame(() => window.scrollTo({ top: batch.savedScrollY }));
    }
    return () => batch.setSavedScrollY(window.scrollY);
  }, [batch.savedScrollY, batch.setSavedScrollY]);

  const items = batch.activeJob?.items ?? [];
  const filteredItems = useMemo(
    () =>
      batch.statusFilter === 'all'
        ? items
        : items.filter((item) => item.status === batch.statusFilter),
    [batch.statusFilter, items],
  );

  const counts = useMemo(() => {
    const result: Record<string, number> = {
      passed: 0,
      warning: 0,
      failed: 0,
      unknown_employee: 0,
      processing: 0,
    };
    for (const item of items) {
      result[item.status] = (result[item.status] ?? 0) + 1;
    }
    return result;
  }, [items]);

  const processingItem = items.find((item) => item.status === 'processing');
  const total = batch.activeJob?.total_slips ?? items.length;
  const processed = batch.activeJob?.processed_slips ?? 0;
  const remaining = Math.max(0, total - processed);
  const percentage = total > 0 ? Math.round((processed / total) * 100) : 0;
  const currentPhase =
    processingItem?.processing_stage ||
    (batch.activeJob?.status === 'completed'
      ? 'completed'
      : batch.activeJob?.current_stage || 'split');

  const startUpload = async () => {
    if (!file) {
      setError(t('accountant.batches.selectPdf'));
      return;
    }
    setUploading(true);
    setError(null);
    batch.setBatchLabel(t('accountant.batches.batchActiveLabel'));
    try {
      const result = await batchService.uploadBulkPdf(file);
      batch.trackBatch(result.batch_job_id);
      setFile(null);
    } catch {
      batch.setBatchActive(false);
      setError(getAccountantErrorMessage('uploadFailed', t));
    } finally {
      setUploading(false);
    }
  };

  const openItem = (item: BatchExtractedEmployee) => {
    batch.setSavedScrollY(window.scrollY);
    if (
      batch.activeJobId &&
      (item.status === 'unknown_employee' ||
        !item.employee_number ||
        !item.payroll_year ||
        !item.payroll_month)
    ) {
      navigate(
        `/accountant/bulk-upload/jobs/${encodeURIComponent(batch.activeJobId)}/items/${encodeURIComponent(item.id)}/resolve`,
      );
      return;
    }
    if (!item.employee_number) return;
    const employeeBase = `/accountant/employees/${encodeURIComponent(item.employee_number)}/workspace`;
    const reviewQuery = batch.activeJobId
      ? `?batchJobId=${encodeURIComponent(batch.activeJobId)}&batchItemId=${encodeURIComponent(item.id)}${item.document_id ? `&batchDocumentId=${encodeURIComponent(item.document_id)}` : ''}`
      : '';
    if (item.payroll_year && item.payroll_month) {
      navigate(
        `${employeeBase}/payslips/${item.payroll_year}/${item.payroll_month}${reviewQuery}`,
        {
        state: { backTo: '/accountant/bulk-upload' },
        },
      );
    } else {
      navigate(employeeBase, { state: { backTo: '/accountant/bulk-upload' } });
    }
  };

  return (
    <PortalPage
      title={t('accountant.batches.uploadTitle')}
      description={t('accountant.batches.uploadDescription')}
    >
      <div className="accountant-bulk">
        <div className="employee-review-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={batch.selectedTab === 'upload'}
            className={`employee-review-tabs__tab ${batch.selectedTab === 'upload' ? 'is-active' : ''}`}
            onClick={() => batch.setSelectedTab('upload')}
          >
            {t('accountant.bulk.tabs.upload')}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={batch.selectedTab === 'extracted'}
            className={`employee-review-tabs__tab ${batch.selectedTab === 'extracted' ? 'is-active' : ''}`}
            onClick={() => batch.setSelectedTab('extracted')}
          >
            {t('accountant.bulk.tabs.extracted')}
            {items.length > 0 ? ` (${items.length})` : ''}
          </button>
        </div>

        {(error || batch.batchError) && (
          <p className="chat-panel__error" role="alert">
            {error || batch.batchError}
          </p>
        )}

        {batch.selectedTab === 'upload' ? (
          <section className="accountant-bulk__upload">
            <UploadPanel
              slots={[
                {
                  id: 'bulk_pdf',
                  label: t('accountant.batches.uploadSlotLabel'),
                  accept: '.pdf,application/pdf',
                },
              ]}
              selectedFileName={file?.name}
              errorMessage={error ?? undefined}
              onFilesSelected={(_slot, selected) => {
                setFile(selected);
                setError(null);
              }}
              onRemove={() => setFile(null)}
            />
            <div className="form-actions">
              <button
                type="button"
                className="btn btn--primary btn--large"
                disabled={!file || uploading}
                onClick={() => void startUpload()}
              >
                {uploading
                  ? t('common.saving')
                  : t('accountant.batches.startProcessing')}
              </button>
            </div>
          </section>
        ) : (
          <section className="accountant-bulk__results" aria-live="polite">
            {batch.activeJob && (
              <>
                <div className="accountant-bulk__progress">
                  <div>
                    <span>{t('accountant.bulk.progress.processed')}</span>
                    <strong>
                      {processed} / {total}
                    </strong>
                  </div>
                  <div>
                    <span>{t('accountant.bulk.progress.current')}</span>
                    <strong>
                      {processingItem?.employee_name ||
                        (processingItem
                          ? t('accountant.bulk.progress.slip', {
                              value: processingItem.slip_index + 1,
                            })
                          : t('common.emDash'))}
                    </strong>
                  </div>
                  <div>
                    <span>{t('accountant.bulk.progress.remaining')}</span>
                    <strong>{remaining}</strong>
                  </div>
                  <div>
                    <span>{t('accountant.bulk.progress.percentage')}</span>
                    <strong>{percentage}%</strong>
                  </div>
                  <div>
                    <span>{t('accountant.bulk.progress.phase')}</span>
                    <strong>
                      {t(`accountant.bulk.phases.${currentPhase}`, {
                        defaultValue: currentPhase,
                      })}
                    </strong>
                  </div>
                  <progress max={Math.max(total, 1)} value={processed} />
                </div>

                <div className="accountant-bulk__summary">
                  <article className="accountant-bulk__summary-card">
                    <strong>{total}</strong>
                    <span>{t('accountant.bulk.summary.employees')}</span>
                  </article>
                  {SUMMARY_STATUSES.map((status) => (
                    <article
                      key={status}
                      className={`accountant-bulk__summary-card is-${status}`}
                    >
                      <strong>{counts[status] ?? 0}</strong>
                      <span>{t(statusLabelKey(status))}</span>
                    </article>
                  ))}
                </div>

                <div className="accountant-bulk__filters" aria-label={t('accountant.bulk.filters.label')}>
                  {FILTERS.map((filter) => (
                    <button
                      key={filter.id}
                      type="button"
                      className={`btn ${batch.statusFilter === filter.id ? 'btn--primary' : 'btn--secondary'}`}
                      aria-pressed={batch.statusFilter === filter.id}
                      onClick={() => batch.setStatusFilter(filter.id)}
                    >
                      {t(filter.labelKey)}
                    </button>
                  ))}
                </div>
              </>
            )}

            {!batch.activeJob ? (
              <EmptyState
                title={t('accountant.bulk.empty.title')}
                description={t('accountant.bulk.empty.description')}
                action={
                  <button
                    type="button"
                    className="btn btn--primary"
                    onClick={() => batch.setSelectedTab('upload')}
                  >
                    {t('accountant.bulk.tabs.upload')}
                  </button>
                }
              />
            ) : filteredItems.length === 0 ? (
              <EmptyState
                title={t('accountant.bulk.emptyFilter.title')}
                description={t('accountant.bulk.emptyFilter.description')}
              />
            ) : (
              <div className="accountant-bulk__list" role="list">
                {filteredItems.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    role="listitem"
                    className={`accountant-bulk__employee is-${item.status}`}
                    onClick={() => openItem(item)}
                    disabled={!item.document_id}
                  >
                    <span className={`status-badge status-badge--batch-${item.status}`}>
                      {t(statusLabelKey(item.status), { defaultValue: item.status })}
                    </span>
                    <span className="accountant-bulk__employee-name">
                      <strong>
                        {item.employee_name ||
                          t('accountant.bulk.progress.slip', {
                            value: item.slip_index + 1,
                          })}
                      </strong>
                      <small>
                        {item.employee_number
                          ? `#${item.employee_number}`
                          : item.national_id_masked || t('common.emDash')}
                      </small>
                    </span>
                    <span>
                      {item.error_message ||
                        (item.status === 'processing'
                          ? t(`accountant.bulk.phases.${item.processing_stage}`, {
                              defaultValue: item.processing_stage,
                            })
                          : item.publication_status === 'published'
                            ? t('accountant.bulk.publish.published')
                            : t('accountant.bulk.publish.pendingReview'))}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </section>
        )}
      </div>
    </PortalPage>
  );
}
