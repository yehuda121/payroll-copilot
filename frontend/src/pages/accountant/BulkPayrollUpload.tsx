import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { DragDropZone } from '../../components/ui/DragDropZone';
import { EmptyState, useConfirmDialog } from '../../components/ui/Dialog';
import { TrashIcon } from '../../components/ui/icons';
import { useBatchNavigationGuard } from '../../features/accountant/BatchNavigationGuard';
import { getAccountantErrorMessage } from '../../i18n/accountantLabels';
import { matchesBatchSearchQuery } from '../../lib/accountant/batch-search';
import { FREE_TEXT_MAX_LENGTH, clampFreeTextInput } from '../../lib/validation';
import { batchService } from '../../services/batch';
import type { BatchEmployeeStatus, BatchExtractedEmployee } from '../../types/api';
import {
  applySelectAllVisible,
  canBulkDeleteItem,
  canBulkPublishItem,
  computeSelectAllState,
  pruneSelectionToAliveIds,
} from '../../lib/accountant/batch-selection';
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

function periodMeta(item: BatchExtractedEmployee, locale: string): string | null {
  if (item.payroll_year == null || item.payroll_month == null) return null;
  return new Intl.DateTimeFormat(locale, { month: 'short', year: 'numeric' }).format(
    new Date(item.payroll_year, item.payroll_month - 1, 1),
  );
}

export function BulkPayrollUploadPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { confirm } = useConfirmDialog();
  const batch = useBatchNavigationGuard();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkMessage, setBulkMessage] = useState<string | null>(null);
  const selectAllRef = useRef<HTMLInputElement | null>(null);

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
  const filteredItems = useMemo(() => {
    const byStatus =
      batch.statusFilter === 'all'
        ? items
        : items.filter((item) => item.status === batch.statusFilter);
    return byStatus.filter((item) => matchesBatchSearchQuery(item, searchQuery));
  }, [batch.statusFilter, items, searchQuery]);

  const selectableVisible = useMemo(
    () => filteredItems.filter((item) => canBulkDeleteItem(item)),
    [filteredItems],
  );
  const selectableVisibleIds = useMemo(
    () => selectableVisible.map((item) => item.id),
    [selectableVisible],
  );
  const selectAllState = useMemo(
    () => computeSelectAllState(selectableVisibleIds, selectedIds),
    [selectableVisibleIds, selectedIds],
  );
  const allVisibleSelected = selectAllState.allSelected;
  const someVisibleSelected = selectAllState.someSelected;

  useEffect(() => {
    const el = selectAllRef.current;
    if (el) el.indeterminate = someVisibleSelected;
  }, [someVisibleSelected]);

  // Drop selection for items removed from the job after refresh/delete.
  useEffect(() => {
    const alive = new Set(items.map((item) => item.id));
    setSelectedIds((prev) => {
      const next = pruneSelectionToAliveIds(prev, alive);
      return next.size === prev.size && [...next].every((id) => prev.has(id)) ? prev : next;
    });
  }, [items]);

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

  const selectedCount = selectedIds.size;
  const selectedPublishable = useMemo(
    () => items.filter((item) => selectedIds.has(item.id) && canBulkPublishItem(item)),
    [items, selectedIds],
  );

  const selectPdf = (selected: File) => {
    const isPdf =
      selected.type === 'application/pdf' || selected.name.toLowerCase().endsWith('.pdf');
    if (!isPdf) {
      setFile(null);
      setError(t('accountant.batches.pdfOnly'));
      return;
    }
    setFile(selected);
    setError(null);
  };

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
      setSelectedIds(new Set());
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

  const toggleOne = (itemId: string, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(itemId);
      else next.delete(itemId);
      return next;
    });
  };

  const toggleSelectAllVisible = (checked: boolean) => {
    setSelectedIds((prev) => applySelectAllVisible(prev, selectableVisibleIds, checked));
  };

  const bulkDelete = async () => {
    if (!batch.activeJobId || selectedCount === 0) return;
    const targets = items.filter((item) => selectedIds.has(item.id) && canBulkDeleteItem(item));
    if (!targets.length) return;
    const accepted = await confirm({
      title: t('accountant.bulk.selection.deleteTitle', { count: targets.length }),
      message: t('accountant.bulk.selection.deleteMessage', { count: targets.length }),
      confirmLabel: t('accountant.bulk.selection.deleteConfirm'),
      cancelLabel: t('common.cancel'),
      variant: 'danger',
    });
    if (!accepted) return;

    setBulkBusy(true);
    setBulkMessage(null);
    setError(null);
    let ok = 0;
    const failed: string[] = [];
    for (const item of targets) {
      try {
        await batchService.resolveItem(batch.activeJobId, item.id, { action: 'ignore' });
        ok += 1;
      } catch {
        failed.push(item.id);
      }
    }
    await batch.refreshBatch();
    setSelectedIds((prev) => {
      const next = new Set(prev);
      for (const item of targets) {
        if (!failed.includes(item.id)) next.delete(item.id);
      }
      return next;
    });
    setBulkBusy(false);
    if (failed.length) {
      setBulkMessage(
        t('accountant.bulk.selection.partialDelete', {
          ok,
          fail: failed.length,
        }),
      );
    } else {
      setBulkMessage(t('accountant.bulk.selection.deleteSuccess', { count: ok }));
    }
  };

  const bulkPublish = async () => {
    if (!batch.activeJobId || !selectedPublishable.length) return;
    const accepted = await confirm({
      title: t('accountant.bulk.selection.publishTitle', {
        count: selectedPublishable.length,
      }),
      message: t('accountant.bulk.selection.publishMessage', {
        count: selectedPublishable.length,
      }),
      confirmLabel: t('accountant.bulk.publish.action'),
      cancelLabel: t('common.cancel'),
    });
    if (!accepted) return;

    setBulkBusy(true);
    setBulkMessage(null);
    setError(null);
    let ok = 0;
    const failed: string[] = [];
    for (const item of selectedPublishable) {
      try {
        await batchService.publishItem(batch.activeJobId, item.id);
        ok += 1;
      } catch {
        failed.push(item.id);
      }
    }
    await batch.refreshBatch();
    setBulkBusy(false);
    if (failed.length) {
      setBulkMessage(
        t('accountant.bulk.selection.partialPublish', {
          ok,
          fail: failed.length,
        }),
      );
    } else {
      setBulkMessage(t('accountant.bulk.selection.publishSuccess', { count: ok }));
    }
  };

  return (
    <PortalPage
      title={t('accountant.batches.uploadTitle')}
      description={t('accountant.batches.uploadDescription')}
    >
      <div className="accountant-bulk">
        <div className="accountant-bulk__chrome">
          <div
            className="app-segmented-nav"
            role="tablist"
            aria-label={t('accountant.bulk.tabs.label')}
          >
            <button
              type="button"
              role="tab"
              aria-selected={batch.selectedTab === 'upload'}
              className={`app-segmented-nav__tab ${batch.selectedTab === 'upload' ? 'is-active' : ''}`}
              onClick={() => batch.setSelectedTab('upload')}
            >
              {t('accountant.bulk.tabs.upload')}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={batch.selectedTab === 'extracted'}
              className={`app-segmented-nav__tab ${batch.selectedTab === 'extracted' ? 'is-active' : ''}`}
              onClick={() => batch.setSelectedTab('extracted')}
            >
              {t('accountant.bulk.tabs.extracted')}
              {items.length > 0 ? ` (${items.length})` : ''}
            </button>
          </div>

          <div className="accountant-bulk__chrome-actions">
            {batch.selectedTab === 'upload' && (
              <button
                type="button"
                className="btn btn--primary accountant-bulk__process-action"
                disabled={!file || uploading}
                onClick={() => void startUpload()}
              >
                {uploading
                  ? t('common.saving')
                  : t('accountant.batches.startProcessing')}
              </button>
            )}
            {batch.selectedTab === 'extracted' && (
              <div
                className="accountant-bulk__bulk-bar accountant-bulk__bulk-bar--reserved"
                role="region"
                aria-label={t('accountant.bulk.selection.bulkActionsLabel')}
                aria-live="polite"
              >
                <span className="accountant-bulk__bulk-count">
                  {selectedCount > 0
                    ? t('accountant.bulk.selection.selectedCount', { count: selectedCount })
                    : t('accountant.bulk.selection.noneSelected')}
                </span>
                <div className="accountant-bulk__bulk-actions">
                  <button
                    type="button"
                    className="btn btn--danger"
                    disabled={bulkBusy || selectedCount === 0}
                    onClick={() => void bulkDelete()}
                  >
                    <TrashIcon size={16} aria-hidden="true" />
                    {t('accountant.bulk.selection.delete')}
                  </button>
                  <button
                    type="button"
                    className="btn btn--primary"
                    disabled={bulkBusy || selectedPublishable.length === 0}
                    title={
                      selectedPublishable.length === 0
                        ? t('accountant.bulk.selection.publishDisabledHint')
                        : undefined
                    }
                    onClick={() => void bulkPublish()}
                  >
                    {t('accountant.bulk.selection.publish', {
                      count: selectedPublishable.length,
                    })}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {(error || batch.batchError) && (
          <p className="chat-panel__error" role="alert">
            {error || batch.batchError}
          </p>
        )}
        {bulkMessage && (
          <p className="accountant-bulk__bulk-message" role="status">
            {bulkMessage}
          </p>
        )}

        {batch.selectedTab === 'upload' ? (
          <section className="accountant-bulk__upload">
            <div className="accountant-bulk__upload-workspace">
              <header className="accountant-bulk__upload-header">
                <h2 className="accountant-bulk__upload-title">
                  {t('accountant.bulk.uploadWorkspace.title')}
                </h2>
                <p className="accountant-bulk__upload-lede">
                  {t('accountant.bulk.uploadWorkspace.description')}
                </p>
              </header>
              <div className="accountant-bulk__upload-shell">
                <DragDropZone
                  accept=".pdf,application/pdf"
                  selectedFileName={file?.name}
                  errorMessage={error ?? undefined}
                  title={t('accountant.batches.uploadSlotLabel')}
                  hint={t('accountant.batches.dragHint')}
                  onFileSelected={selectPdf}
                  onRemove={() => {
                    setFile(null);
                    setError(null);
                  }}
                />
              </div>
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

                <div className="accountant-bulk__toolbar">
                  <label className="accountant-bulk__search">
                    <span className="visually-hidden">{t('accountant.bulk.searchLabel')}</span>
                    <input
                      type="search"
                      value={searchQuery}
                      maxLength={FREE_TEXT_MAX_LENGTH.searchQuery}
                      onChange={(event) =>
                        setSearchQuery(
                          clampFreeTextInput(event.target.value, FREE_TEXT_MAX_LENGTH.searchQuery),
                        )
                      }
                      placeholder={t('accountant.bulk.searchPlaceholder')}
                      aria-label={t('accountant.bulk.searchLabel')}
                    />
                  </label>
                  <div
                    className="accountant-bulk__filters"
                    aria-label={t('accountant.bulk.filters.label')}
                    role="group"
                  >
                    {FILTERS.map((filter) => (
                      <button
                        key={filter.id}
                        type="button"
                        className={`accountant-bulk__filter-pill is-${filter.id} ${
                          batch.statusFilter === filter.id ? 'is-active' : ''
                        }`}
                        aria-pressed={batch.statusFilter === filter.id}
                        aria-label={t(filter.labelKey)}
                        onClick={() => batch.setStatusFilter(filter.id)}
                      >
                        {t(filter.labelKey)}
                      </button>
                    ))}
                  </div>
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
                title={
                  searchQuery.trim()
                    ? t('accountant.bulk.emptySearch.title')
                    : t('accountant.bulk.emptyFilter.title')
                }
                description={
                  searchQuery.trim()
                    ? t('accountant.bulk.emptySearch.description', { query: searchQuery.trim() })
                    : t('accountant.bulk.emptyFilter.description')
                }
              />
            ) : (
              <>
                <div className="accountant-bulk__select-all">
                  <label className="accountant-bulk__select-all-label">
                    <input
                      ref={selectAllRef}
                      type="checkbox"
                      className="accountant-bulk__checkbox accountant-bulk__checkbox--select-all"
                      checked={allVisibleSelected}
                      disabled={selectableVisible.length === 0 || bulkBusy}
                      onChange={(event) => toggleSelectAllVisible(event.target.checked)}
                      aria-label={t('accountant.bulk.selection.selectAll')}
                    />
                    <span>{t('accountant.bulk.selection.selectAll')}</span>
                  </label>
                </div>
                <div className="accountant-bulk__list" role="list">
                  {filteredItems.map((item) => {
                    const serial = item.slip_index + 1;
                    const displayName =
                      item.employee_name?.trim() || t('accountant.bulk.unnamedSlip');
                    const period = periodMeta(item, i18n.language);
                    const selectable = canBulkDeleteItem(item);
                    const checked = selectedIds.has(item.id);
                    return (
                      <div
                        key={item.id}
                        role="listitem"
                        className={`accountant-bulk__employee is-${item.status} ${checked ? 'is-selected' : ''}`}
                      >
                        <label className="accountant-bulk__row-check">
                          <input
                            type="checkbox"
                            className="accountant-bulk__checkbox"
                            checked={checked}
                            disabled={!selectable || bulkBusy}
                            aria-label={t('accountant.bulk.selection.selectRow', {
                              name: displayName,
                            })}
                            onChange={(event) => toggleOne(item.id, event.target.checked)}
                            onClick={(event) => event.stopPropagation()}
                          />
                        </label>
                        <button
                          type="button"
                          className="accountant-bulk__employee-main"
                          onClick={() => openItem(item)}
                          disabled={!item.document_id}
                        >
                          <span
                            className="accountant-bulk__serial"
                            title={t('accountant.bulk.serialLabel', { value: serial })}
                          >
                            #{serial}
                          </span>
                          <span className="accountant-bulk__employee-name">
                            <strong>{displayName}</strong>
                            <small>
                              {[
                                item.employee_number ? `#${item.employee_number}` : null,
                                item.national_id_masked || null,
                                period,
                              ]
                                .filter(Boolean)
                                .join(' · ') || t('common.emDash')}
                            </small>
                          </span>
                          <span
                            className={`status-badge status-badge--batch-${item.status} accountant-bulk__status-pill`}
                          >
                            {t(statusLabelKey(item.status), { defaultValue: item.status })}
                          </span>
                          <span className="accountant-bulk__employee-meta">
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
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </section>
        )}
      </div>
    </PortalPage>
  );
}
