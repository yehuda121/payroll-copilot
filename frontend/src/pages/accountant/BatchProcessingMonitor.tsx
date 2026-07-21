import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { DataTable } from '../../components/ui/DataTable';
import { EmptyState, LoadingOverlay } from '../../components/ui/Dialog';
import { useBatchNavigationGuard } from '../../features/accountant/BatchNavigationGuard';
import {
  getAccountantErrorMessage,
  getBatchStageLabel,
  getBatchStatusLabel,
  getStageStatusLabel,
} from '../../i18n/accountantLabels';
import { batchService } from '../../services/batch';
import type { BatchJobStatus } from '../../types/api';

export function BatchProcessingMonitorPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const focusJob = params.get('job');
  const { setBatchActive, setBatchLabel } = useBatchNavigationGuard();
  const [jobs, setJobs] = useState<BatchJobStatus[]>([]);
  const [selected, setSelected] = useState<BatchJobStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const list = await batchService.listJobs();
      setJobs(list);
      const active = list.some((job) => job.status === 'queued' || job.status === 'running');
      setBatchActive(active);
      if (active) setBatchLabel(t('accountant.batches.batchActiveLabel'));
      if (focusJob) {
        const detail = await batchService.getJobStatus(focusJob);
        setSelected(detail);
      } else if (list[0]) {
        setSelected(list[0]);
      }
      setError(null);
    } catch {
      setError(getAccountantErrorMessage('loadFailed', t));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 2500);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusJob, t]);

  const stages = useMemo(() => selected?.stages ?? [], [selected]);

  return (
    <PortalPage
      title={t('accountant.batches.monitorTitle')}
      description={t('accountant.batches.monitorDescription')}
    >
      <div className="accountant-toolbar">
        <button type="button" className="btn btn--secondary" onClick={() => void load()}>
          {t('common.refresh')}
        </button>
        <Link to="/accountant/bulk-upload" className="btn btn--primary">
          {t('accountant.batches.newUpload')}
        </Link>
      </div>

      {error && <p className="chat-panel__error">{error}</p>}

      <div className="panel-relative" aria-busy={loading}>
        {loading && jobs.length === 0 && (
          <LoadingOverlay label={t('accountant.batches.loadingJobs')} />
        )}
        {!loading && jobs.length === 0 ? (
          <EmptyState
            title={t('accountant.batches.emptyJobsTitle')}
            description={t('accountant.batches.emptyJobsDescription')}
            action={
              <Link to="/accountant/bulk-upload" className="btn btn--primary">
                {t('accountant.batches.uploadTitle')}
              </Link>
            }
          />
        ) : (
          <DataTable<BatchJobStatus & Record<string, unknown>>
            columns={[
              {
                key: 'id',
                header: t('accountant.batches.colJobId'),
                render: (row) => row.id.slice(0, 8),
              },
              {
                key: 'source_filename',
                header: t('accountant.batches.colFile'),
                render: (row) => row.source_filename || t('common.emDash'),
              },
              {
                key: 'status',
                header: t('accountant.batches.colStatus'),
                render: (row) => getBatchStatusLabel(row.status, t),
              },
              {
                key: 'current_stage',
                header: t('accountant.batches.colStage'),
                render: (row) => getBatchStageLabel(row.current_stage, t),
              },
              {
                key: 'progress_percent',
                header: t('accountant.batches.colProgress'),
                render: (row) =>
                  t('accountant.batches.progressPercent', { value: row.progress_percent }),
              },
              {
                key: 'total_slips',
                header: t('accountant.batches.colSlips'),
                render: (row) =>
                  t('accountant.batches.slipsProgress', {
                    processed: row.processed_slips,
                    total: row.total_slips,
                  }),
              },
              {
                key: 'actions',
                header: t('common.actions'),
                render: (row) => (
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => setSelected(row)}
                  >
                    {t('common.details')}
                  </button>
                ),
              },
            ]}
            data={jobs as Array<BatchJobStatus & Record<string, unknown>>}
          />
        )}
      </div>

      {selected && (
        <section className="profile-section pipeline-panel">
          <div className="profile-section__header">
            <strong>
              {t('accountant.batches.pipelineTitle', { id: selected.id.slice(0, 8) })}
            </strong>
            <span className={`status-badge status-badge--${selected.status}`}>
              {getBatchStatusLabel(selected.status, t)}
            </span>
          </div>
          <div className="profile-section__body">
            <div className="pipeline-stages">
              {stages.map((stage) => (
                <div key={stage.key} className={`pipeline-stage pipeline-stage--${stage.status}`}>
                  <div className="pipeline-stage__head">
                    <strong>{getBatchStageLabel(stage.key, t)}</strong>
                    <span>{getStageStatusLabel(stage.status, t)}</span>
                  </div>
                  {stage.detail && <p>{stage.detail}</p>}
                </div>
              ))}
            </div>
            {selected.error_message && (
              <p className="chat-panel__error">{selected.error_message}</p>
            )}
            {selected.report_summary && (
              <p className="month-card__meta report-summary">
                {t('accountant.batches.reportSummary', {
                  summary: Object.entries(selected.report_summary)
                    .map(([k, v]) => `${k}=${v}`)
                    .join(' · '),
                })}
              </p>
            )}
          </div>
        </section>
      )}
    </PortalPage>
  );
}
