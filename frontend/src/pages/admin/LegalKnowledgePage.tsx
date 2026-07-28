import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { ModalDialog } from '../../components/ui/Dialog';
import {
  FormControl,
  FormField,
  FormInfoPanel,
  FormSection,
  FormShell,
  FormTextarea,
} from '../../components/ui/form/FormPrimitives';
import { CalendarIcon, SparklesIcon } from '../../components/ui/icons';
import { useToast } from '../../components/ui/Toast';
import {
  AnalyticsEmptyState,
  AnalyticsErrorState,
  AnalyticsLoadingState,
} from '../../features/analytics';
import { useAnalyticsResource } from '../../hooks/useAnalyticsResource';
import {
  legalKnowledgeService,
  type LegalChangeProposal,
  type LegalProposalDetail,
  type LegalRuleDetail,
  type LegalRuleRow,
  type LegalSource,
  type LegalSyncRun,
  type VectorIndexHealth,
} from '../../services/legalKnowledge';
import { formatDate, formatDateTime, statusBadgeClass } from './adminFormatters';
import './admin-ai.css';

type TabId =
  | 'overview'
  | 'rules'
  | 'sources'
  | 'proposals'
  | 'sync'
  | 'vector';

const TABS: Array<{ id: TabId; labelKey: string }> = [
  { id: 'overview', labelKey: 'admin.legal.tabs.overview' },
  { id: 'rules', labelKey: 'admin.legal.tabs.rules' },
  { id: 'sources', labelKey: 'admin.legal.tabs.sources' },
  { id: 'proposals', labelKey: 'admin.legal.tabs.proposals' },
  { id: 'sync', labelKey: 'admin.legal.tabs.sync' },
  { id: 'vector', labelKey: 'admin.legal.tabs.vector' },
];

function VectorHealthCard({ health }: { health: VectorIndexHealth }) {
  const { t } = useTranslation();
  return (
    <section className="admin-ai-card">
      <h2>{t('admin.legal.vector.title')}</h2>
      <dl className="admin-ai-detail">
        <div>
          <dt>{t('admin.legal.vector.status')}</dt>
          <dd>
            <span className={statusBadgeClass(health.status)}>{health.status}</span>
          </dd>
        </div>
        <div>
          <dt>{t('admin.legal.vector.backend')}</dt>
          <dd>{health.backend}</dd>
        </div>
        <div>
          <dt>{t('admin.legal.vector.embeddingModel')}</dt>
          <dd>{health.embedding_model ?? t('common.emDash')}</dd>
        </div>
        <div>
          <dt>{t('admin.legal.vector.indexedCounts')}</dt>
          <dd>
            {health.indexed_rules} / {health.indexed_versions} / {health.chunk_count}
          </dd>
        </div>
        <div>
          <dt>{t('admin.legal.vector.lastIndexed')}</dt>
          <dd>{formatDateTime(health.last_indexed_at)}</dd>
        </div>
        {health.last_error ? (
          <div>
            <dt>{t('admin.legal.vector.lastError')}</dt>
            <dd className="admin-ai-error">{health.last_error}</dd>
          </div>
        ) : null}
      </dl>
    </section>
  );
}

function OverviewTab() {
  const { t } = useTranslation();
  const overview = useAnalyticsResource(
    useCallback((signal: AbortSignal) => legalKnowledgeService.overview(signal), []),
    [],
    t('admin.legal.errors.overview'),
  );

  if (overview.loading && !overview.data) {
    return <AnalyticsLoadingState cards={6} label={t('admin.legal.loading.overview')} />;
  }
  if (overview.error) {
    return (
      <AnalyticsErrorState
        title={t('admin.legal.errors.overview')}
        message={overview.error}
        onRetry={overview.reload}
      />
    );
  }
  if (!overview.data) return null;

  const data = overview.data;
  return (
    <div className="admin-ai">
      <div className="admin-ai-kpis">
        <div className="admin-ai-kpi">
          <span>{t('admin.legal.kpi.activeRules')}</span>
          <strong>{data.active_rules.toLocaleString()}</strong>
        </div>
        <div className="admin-ai-kpi">
          <span>{t('admin.legal.kpi.historicalVersions')}</span>
          <strong>{data.historical_versions.toLocaleString()}</strong>
        </div>
        <div className="admin-ai-kpi">
          <span>{t('admin.legal.kpi.watchedSources')}</span>
          <strong>{data.watched_sources.toLocaleString()}</strong>
        </div>
        <div className="admin-ai-kpi">
          <span>{t('admin.legal.kpi.discoverySources')}</span>
          <strong>{data.discovery_sources.toLocaleString()}</strong>
        </div>
        <div className="admin-ai-kpi">
          <span>{t('admin.legal.kpi.pendingChanges')}</span>
          <strong>{data.pending_changes.toLocaleString()}</strong>
        </div>
        <div className="admin-ai-kpi">
          <span>{t('admin.legal.kpi.lastSync')}</span>
          <strong>
            {data.last_sync
              ? formatDateTime(data.last_sync.completed_at ?? data.last_sync.started_at)
              : t('admin.legal.never')}
          </strong>
        </div>
      </div>
      <VectorHealthCard health={data.vector_index} />
      {data.last_sync ? (
        <section className="admin-ai-card">
          <h2>{t('admin.legal.latestSync')}</h2>
          <p className="admin-ai-muted">
            {t('admin.legal.latestSyncSummary', {
              runId: data.last_sync.run_id,
              status: data.last_sync.status,
              checked: data.last_sync.sources_checked,
              material: data.last_sync.material_change_count,
              errors: data.last_sync.error_count,
            })}
          </p>
        </section>
      ) : (
        <AnalyticsEmptyState
          title={t('admin.legal.empty.sync')}
          description={t('admin.legal.empty.syncHint')}
        />
      )}
    </div>
  );
}

function RulesTab() {
  const { t } = useTranslation();
  const rules = useAnalyticsResource(
    useCallback((signal: AbortSignal) => legalKnowledgeService.listRules(signal), []),
    [],
    t('admin.legal.errors.rules'),
  );
  const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null);
  const [detail, setDetail] = useState<LegalRuleDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedRuleId) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    setDetailLoading(true);
    setDetailError(null);
    void legalKnowledgeService
      .getRule(selectedRuleId, controller.signal)
      .then(setDetail)
      .catch((err: Error) => setDetailError(err.message))
      .finally(() => setDetailLoading(false));
    return () => controller.abort();
  }, [selectedRuleId]);

  const rows = rules.data ?? [];
  const unavailable = t('admin.legal.unavailable');

  return (
    <div className="admin-ai">
      {rules.loading && rows.length === 0 ? (
        <AnalyticsLoadingState cards={2} label={t('admin.legal.loading.rules')} />
      ) : null}
      {rules.error ? (
        <AnalyticsErrorState
          title={t('admin.legal.errors.rules')}
          message={rules.error}
          onRetry={rules.reload}
        />
      ) : null}
      {!rules.loading && !rules.error && rows.length === 0 ? (
        <AnalyticsEmptyState
          title={t('admin.legal.empty.rules')}
          description={t('admin.legal.empty.rulesHint')}
        />
      ) : null}
      {rows.length > 0 ? (
        <div className="admin-ai-split">
          <div className="admin-ai-table-wrap">
            <table className="admin-ai-table">
              <thead>
                <tr>
                  <th>{t('admin.legal.cols.rule')}</th>
                  <th>{t('admin.legal.cols.version')}</th>
                  <th>{t('admin.legal.cols.validation')}</th>
                  <th>{t('admin.legal.cols.sourceMonitoring')}</th>
                  <th>{t('admin.legal.cols.vector')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row: LegalRuleRow) => (
                  <tr
                    key={row.rule_id}
                    className={selectedRuleId === row.rule_id ? 'is-selected' : ''}
                    onClick={() => setSelectedRuleId(row.rule_id)}
                  >
                    <td>
                      <strong>{row.rule_id}</strong>
                      <div className="admin-ai-muted">{row.title}</div>
                    </td>
                    <td>{row.current_version}</td>
                    <td>{row.validation_readiness ?? unavailable}</td>
                    <td>{row.source_coverage}</td>
                    <td>{row.index_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <aside className="admin-ai-detail">
            <h3>{t('admin.legal.ruleDetail')}</h3>
            {!selectedRuleId ? (
              <p className="admin-ai-muted">{t('admin.legal.selectRule')}</p>
            ) : null}
            {detailLoading ? <p className="admin-ai-muted">{t('common.loading')}</p> : null}
            {detailError ? <p className="admin-ai-error">{detailError}</p> : null}
            {detail ? (
              <>
                <dl>
                  <div>
                    <dt>{t('admin.legal.fields.validationReadiness')}</dt>
                    <dd>{detail.validation_readiness ?? unavailable}</dd>
                  </div>
                  <div>
                    <dt>{t('admin.legal.fields.readinessReason')}</dt>
                    <dd>{detail.validation_readiness_reason ?? unavailable}</dd>
                  </div>
                  <div>
                    <dt>{t('admin.legal.fields.requiredInputs')}</dt>
                    <dd>
                      {(detail.required_fields && detail.required_fields.length > 0
                        ? detail.required_fields.join(', ')
                        : null) ?? unavailable}
                    </dd>
                  </div>
                  <div>
                    <dt>{t('admin.legal.fields.activeVersion')}</dt>
                    <dd>{detail.active?.version ?? t('common.emDash')}</dd>
                  </div>
                  <div>
                    <dt>{t('admin.legal.fields.validFromTo')}</dt>
                    <dd>
                      {formatDate(detail.active?.valid_from ?? null)} →{' '}
                      {formatDate(detail.active?.valid_to ?? null)}
                    </dd>
                  </div>
                  <div>
                    <dt>{t('admin.legal.fields.sourceMonitoring')}</dt>
                    <dd>{detail.source_monitoring_status ?? unavailable}</dd>
                  </div>
                  <div>
                    <dt>{t('admin.legal.fields.lastSourceSync')}</dt>
                    <dd>{formatDate(detail.last_source_sync ?? null)}</dd>
                  </div>
                  <div>
                    <dt>{t('admin.legal.fields.vectorIndex')}</dt>
                    <dd>{detail.vector_index_status ?? unavailable}</dd>
                  </div>
                </dl>
                <h3>{t('admin.legal.versionTimeline')}</h3>
                <ul className="admin-ai-timeline">
                  {detail.versions.map((version) => (
                    <li key={`${version.rule_id}-${version.version}`}>
                      <strong>v{version.version}</strong>{' '}
                      <span className={statusBadgeClass(version.status)}>{version.status}</span>
                      <div className="admin-ai-muted">
                        {formatDate(version.valid_from)} → {formatDate(version.valid_to)}
                      </div>
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          </aside>
        </div>
      ) : null}
    </div>
  );
}

function SourcesTab() {
  const { t } = useTranslation();
  const sources = useAnalyticsResource(
    useCallback((signal: AbortSignal) => legalKnowledgeService.listSources(signal), []),
    [],
    t('admin.legal.errors.sources'),
  );
  const rows = sources.data ?? [];

  return (
    <div className="admin-ai">
      {sources.loading && rows.length === 0 ? (
        <AnalyticsLoadingState cards={2} label={t('admin.legal.loading.sources')} />
      ) : null}
      {sources.error ? (
        <AnalyticsErrorState
          title={t('admin.legal.errors.sources')}
          message={sources.error}
          onRetry={sources.reload}
        />
      ) : null}
      {!sources.loading && !sources.error && rows.length === 0 ? (
        <AnalyticsEmptyState
          title={t('admin.legal.empty.sources')}
          description={t('admin.legal.empty.sourcesHint')}
        />
      ) : null}
      {rows.length > 0 ? (
        <div className="admin-ai-table-wrap">
          <table className="admin-ai-table">
            <thead>
              <tr>
                <th>{t('admin.legal.cols.source')}</th>
                <th>{t('admin.legal.cols.type')}</th>
                <th>{t('admin.legal.cols.authority')}</th>
                <th>{t('admin.legal.cols.enabled')}</th>
                <th>{t('admin.legal.cols.lastChecked')}</th>
                <th>{t('admin.legal.cols.relatedRules')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((source: LegalSource) => (
                <tr key={source.source_id}>
                  <td>
                    <strong>{source.source_id}</strong>
                    <div className="admin-ai-muted">{source.provider}</div>
                    {source.url ? (
                      <a href={source.url} target="_blank" rel="noreferrer">
                        {source.url}
                      </a>
                    ) : null}
                  </td>
                  <td>{source.source_type}</td>
                  <td>{source.authority_level}</td>
                  <td>{source.enabled ? t('admin.legal.yes') : t('admin.legal.no')}</td>
                  <td>{formatDateTime(source.last_checked_at)}</td>
                  <td>{source.related_rule_ids.join(', ') || t('common.emDash')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

type ProposalDialogMode = 'approve' | 'reject' | null;

function ProposalsTab() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const proposals = useAnalyticsResource(
    useCallback((signal: AbortSignal) => legalKnowledgeService.listProposals('PENDING_REVIEW', signal), []),
    [],
    t('admin.legal.errors.proposals'),
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<LegalProposalDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [dialogMode, setDialogMode] = useState<ProposalDialogMode>(null);
  const [effectiveDate, setEffectiveDate] = useState('');
  const [confirmDate, setConfirmDate] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const rows = proposals.data ?? [];

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    setDetailLoading(true);
    void legalKnowledgeService
      .getProposal(selectedId, controller.signal)
      .then((result) => {
        setDetail(result);
        setEffectiveDate(result.proposal.candidate_effective_date ?? '');
      })
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
    return () => controller.abort();
  }, [selectedId]);

  const closeDialog = () => {
    setDialogMode(null);
    setConfirmDate(false);
    setRejectReason('');
  };

  const submitApprove = async () => {
    if (!selectedId || !effectiveDate) return;
    if (!confirmDate) {
      showToast({ message: t('admin.legal.toasts.confirmDate'), tone: 'warning' });
      return;
    }
    setSubmitting(true);
    try {
      await legalKnowledgeService.approveProposal(selectedId, {
        effective_date: effectiveDate,
        confirm_effective_date: true,
      });
      showToast({ message: t('admin.legal.toasts.approved'), tone: 'success' });
      closeDialog();
      setSelectedId(null);
      proposals.reload();
    } catch (err) {
      showToast({
        message: err instanceof Error ? err.message : t('admin.legal.toasts.approveFailed'),
        tone: 'error',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const submitReject = async () => {
    if (!selectedId) return;
    setSubmitting(true);
    try {
      await legalKnowledgeService.rejectProposal(selectedId, { reason: rejectReason || undefined });
      showToast({ message: t('admin.legal.toasts.rejected'), tone: 'success' });
      closeDialog();
      setSelectedId(null);
      proposals.reload();
    } catch (err) {
      showToast({
        message: err instanceof Error ? err.message : t('admin.legal.toasts.rejectFailed'),
        tone: 'error',
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="admin-ai">
      {proposals.loading && rows.length === 0 ? (
        <AnalyticsLoadingState cards={2} label={t('admin.legal.loading.proposals')} />
      ) : null}
      {proposals.error ? (
        <AnalyticsErrorState
          title={t('admin.legal.errors.proposals')}
          message={proposals.error}
          onRetry={proposals.reload}
        />
      ) : null}
      {!proposals.loading && !proposals.error && rows.length === 0 ? (
        <AnalyticsEmptyState
          title={t('admin.legal.empty.proposals')}
          description={t('admin.legal.empty.proposalsHint')}
        />
      ) : null}
      {rows.length > 0 ? (
        <div className="admin-ai-split">
          <div className="admin-ai-table-wrap">
            <table className="admin-ai-table">
              <thead>
                <tr>
                  <th>{t('admin.legal.cols.proposal')}</th>
                  <th>{t('admin.legal.cols.classification')}</th>
                  <th>{t('admin.legal.cols.rules')}</th>
                  <th>{t('admin.legal.cols.created')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((proposal: LegalChangeProposal) => (
                  <tr
                    key={proposal.proposal_id}
                    className={selectedId === proposal.proposal_id ? 'is-selected' : ''}
                    onClick={() => setSelectedId(proposal.proposal_id)}
                  >
                    <td>
                      <strong>{proposal.proposal_id}</strong>
                      <div className="admin-ai-muted">{proposal.source_id}</div>
                    </td>
                    <td>{proposal.classification}</td>
                    <td>{proposal.affected_rule_ids.join(', ') || t('common.emDash')}</td>
                    <td>{formatDateTime(proposal.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <aside className="admin-ai-detail">
            <h3>{t('admin.legal.proposalDetail')}</h3>
            {!selectedId ? (
              <p className="admin-ai-muted">{t('admin.legal.selectProposal')}</p>
            ) : null}
            {detailLoading ? <p className="admin-ai-muted">{t('common.loading')}</p> : null}
            {detail ? (
              <>
                <dl>
                  <div>
                    <dt>{t('admin.legal.fields.aiSummary')}</dt>
                    <dd>{detail.proposal.ai_summary || t('common.emDash')}</dd>
                  </div>
                  <div>
                    <dt>{t('admin.legal.fields.candidateEffectiveDate')}</dt>
                    <dd>{formatDate(detail.proposal.candidate_effective_date)}</dd>
                  </div>
                  <div>
                    <dt>{t('admin.legal.fields.confidence')}</dt>
                    <dd>
                      {detail.proposal.confidence != null
                        ? `${(detail.proposal.confidence * 100).toFixed(0)}%`
                        : t('common.emDash')}
                    </dd>
                  </div>
                </dl>
                {detail.proposal.diff_text ? (
                  <>
                    <h3>{t('admin.legal.diff')}</h3>
                    <pre className="admin-ai-pre">{detail.proposal.diff_text}</pre>
                  </>
                ) : null}
                <div className="admin-ai-actions">
                  <button type="button" className="btn btn--primary" onClick={() => setDialogMode('approve')}>
                    {t('admin.legal.approve')}
                  </button>
                  <button type="button" className="btn btn--danger" onClick={() => setDialogMode('reject')}>
                    {t('admin.legal.reject')}
                  </button>
                </div>
              </>
            ) : null}
          </aside>
        </div>
      ) : null}

      {dialogMode === 'approve' ? (
        <ModalDialog
          title={t('admin.legal.approveTitle')}
          variant="warning"
          size="md"
          onClose={closeDialog}
          footer={
            <>
              <button type="button" className="btn btn--secondary" onClick={closeDialog} disabled={submitting}>
                {t('admin.legal.cancel')}
              </button>
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => void submitApprove()}
                disabled={submitting}
              >
                {t('admin.legal.approve')}
              </button>
            </>
          }
        >
          <FormShell
            aside={
              <FormInfoPanel
                tone="warning"
                eyebrow={t('admin.legal.approveEyebrow')}
                title={t('admin.legal.approveConfirmTitle')}
                icon={<SparklesIcon size={14} aria-hidden="true" />}
              >
                <p>{t('admin.legal.approveConfirmBody')}</p>
              </FormInfoPanel>
            }
          >
            <FormSection
              title={t('admin.legal.approvalDetails')}
              description={t('admin.legal.approvalDetailsDesc')}
              icon={<CalendarIcon size={18} />}
              columns={1}
            >
              <FormField label={t('admin.legal.effectiveDate')} htmlFor="legal-effective-date" span={2}>
                <FormControl
                  id="legal-effective-date"
                  type="date"
                  value={effectiveDate}
                  onChange={(event) => setEffectiveDate(event.target.value)}
                />
              </FormField>
              <label
                className="form-field form-field--checkbox pc-form-field--span-2"
                htmlFor="legal-confirm-date"
              >
                <input
                  id="legal-confirm-date"
                  type="checkbox"
                  checked={confirmDate}
                  onChange={(event) => setConfirmDate(event.target.checked)}
                />
                <span>{t('admin.legal.confirmDate')}</span>
              </label>
            </FormSection>
          </FormShell>
        </ModalDialog>
      ) : null}

      {dialogMode === 'reject' ? (
        <ModalDialog
          title={t('admin.legal.rejectTitle')}
          variant="danger"
          size="md"
          onClose={closeDialog}
          footer={
            <>
              <button type="button" className="btn btn--secondary" onClick={closeDialog} disabled={submitting}>
                {t('admin.legal.cancel')}
              </button>
              <button
                type="button"
                className="btn btn--danger"
                onClick={() => void submitReject()}
                disabled={submitting}
              >
                {t('admin.legal.reject')}
              </button>
            </>
          }
        >
          <FormShell>
            <FormSection
              title={t('admin.legal.rejectionTitle')}
              description={t('admin.legal.rejectionDesc')}
              columns={1}
            >
              <FormField label={t('admin.legal.reasonOptional')} htmlFor="legal-reject-reason" span={2}>
                <FormTextarea
                  id="legal-reject-reason"
                  rows={4}
                  value={rejectReason}
                  onChange={(event) => setRejectReason(event.target.value)}
                />
              </FormField>
            </FormSection>
          </FormShell>
        </ModalDialog>
      ) : null}
    </div>
  );
}

function SyncHistoryTab() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const syncRuns = useAnalyticsResource(
    useCallback((signal: AbortSignal) => legalKnowledgeService.listSyncRuns(50, signal), []),
    [],
    t('admin.legal.errors.sync'),
  );
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<LegalSyncRun | null>(null);
  const [syncing, setSyncing] = useState(false);

  const rows = syncRuns.data ?? [];

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRun(null);
      return;
    }
    const controller = new AbortController();
    void legalKnowledgeService
      .getSyncRun(selectedRunId, controller.signal)
      .then(setSelectedRun)
      .catch(() => setSelectedRun(null));
    return () => controller.abort();
  }, [selectedRunId]);

  const triggerSync = async () => {
    setSyncing(true);
    try {
      const run = await legalKnowledgeService.triggerSync();
      showToast({ message: t('admin.legal.toasts.syncStarted', { runId: run.run_id }), tone: 'success' });
      syncRuns.reload();
      setSelectedRunId(run.run_id);
    } catch (err) {
      showToast({
        message: err instanceof Error ? err.message : t('admin.legal.toasts.syncFailed'),
        tone: 'error',
      });
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="admin-ai">
      <div className="admin-ai-toolbar">
        <button type="button" className="btn btn--primary" onClick={() => void triggerSync()} disabled={syncing}>
          {syncing ? t('admin.legal.syncing') : t('admin.legal.runSync')}
        </button>
      </div>
      {syncRuns.loading && rows.length === 0 ? (
        <AnalyticsLoadingState cards={2} label={t('admin.legal.loading.sync')} />
      ) : null}
      {syncRuns.error ? (
        <AnalyticsErrorState
          title={t('admin.legal.errors.sync')}
          message={syncRuns.error}
          onRetry={syncRuns.reload}
        />
      ) : null}
      {!syncRuns.loading && !syncRuns.error && rows.length === 0 ? (
        <AnalyticsEmptyState
          title={t('admin.legal.empty.sync')}
          description={t('admin.legal.empty.syncManualHint')}
        />
      ) : null}
      {rows.length > 0 ? (
        <div className="admin-ai-split">
          <div className="admin-ai-table-wrap">
            <table className="admin-ai-table">
              <thead>
                <tr>
                  <th>{t('admin.legal.cols.run')}</th>
                  <th>{t('admin.legal.cols.status')}</th>
                  <th>{t('admin.legal.cols.started')}</th>
                  <th>{t('admin.legal.cols.sourcesCount')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((run) => (
                  <tr
                    key={run.run_id}
                    className={selectedRunId === run.run_id ? 'is-selected' : ''}
                    onClick={() => setSelectedRunId(run.run_id)}
                  >
                    <td>{run.run_id}</td>
                    <td>
                      <span className={statusBadgeClass(run.status)}>{run.status}</span>
                    </td>
                    <td>{formatDateTime(run.started_at)}</td>
                    <td>{run.sources_checked}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <aside className="admin-ai-detail">
            <h3>{t('admin.legal.runDetail')}</h3>
            {!selectedRun ? <p className="admin-ai-muted">{t('admin.legal.selectSyncRun')}</p> : null}
            {selectedRun ? (
              <>
                <dl>
                  <div>
                    <dt>{t('admin.legal.fields.trigger')}</dt>
                    <dd>{selectedRun.trigger}</dd>
                  </div>
                  <div>
                    <dt>{t('admin.legal.fields.completed')}</dt>
                    <dd>{formatDateTime(selectedRun.completed_at)}</dd>
                  </div>
                  <div>
                    <dt>{t('admin.legal.fields.counts')}</dt>
                    <dd>
                      {t('admin.legal.syncCounts', {
                        material: selectedRun.material_change_count,
                        newCount: selectedRun.new_relevant_count,
                        errors: selectedRun.error_count,
                      })}
                    </dd>
                  </div>
                </dl>
                <h3>{t('admin.legal.outcomes')}</h3>
                <ul className="admin-ai-timeline">
                  {selectedRun.outcomes.map((outcome) => (
                    <li key={`${outcome.source_id}-${outcome.classification}`}>
                      <strong>{outcome.source_id}</strong> — {outcome.classification}
                      <div className="admin-ai-muted">
                        {outcome.message || outcome.error || t('common.emDash')}
                      </div>
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          </aside>
        </div>
      ) : null}
    </div>
  );
}

function VectorIndexTab() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const health = useAnalyticsResource(
    useCallback((signal: AbortSignal) => legalKnowledgeService.vectorIndexHealth(signal), []),
    [],
    t('admin.legal.errors.vector'),
  );
  const [rebuilding, setRebuilding] = useState(false);

  const rebuild = async () => {
    setRebuilding(true);
    try {
      await legalKnowledgeService.rebuildVectorIndex();
      showToast({ message: t('admin.legal.toasts.rebuildDone'), tone: 'success' });
      health.reload();
    } catch (err) {
      showToast({
        message: err instanceof Error ? err.message : t('admin.legal.toasts.rebuildFailed'),
        tone: 'error',
      });
    } finally {
      setRebuilding(false);
    }
  };

  if (health.loading && !health.data) {
    return <AnalyticsLoadingState cards={2} label={t('admin.legal.loading.vector')} />;
  }
  if (health.error) {
    return (
      <AnalyticsErrorState
        title={t('admin.legal.errors.vector')}
        message={health.error}
        onRetry={health.reload}
      />
    );
  }
  if (!health.data) return null;

  return (
    <div className="admin-ai">
      <div className="admin-ai-toolbar">
        <button type="button" className="btn btn--primary" onClick={() => void rebuild()} disabled={rebuilding}>
          {rebuilding ? t('admin.legal.rebuilding') : t('admin.legal.rebuildIndex')}
        </button>
      </div>
      <VectorHealthCard health={health.data} />
    </div>
  );
}

export function LegalKnowledgePage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<TabId>('overview');

  const panel = useMemo(() => {
    switch (tab) {
      case 'overview':
        return <OverviewTab />;
      case 'rules':
        return <RulesTab />;
      case 'sources':
        return <SourcesTab />;
      case 'proposals':
        return <ProposalsTab />;
      case 'sync':
        return <SyncHistoryTab />;
      case 'vector':
        return <VectorIndexTab />;
      default:
        return null;
    }
  }, [tab]);

  return (
    <PortalPage title={t('admin.legal.title')} description={t('admin.legal.description')}>
      <div className="admin-ai-tabs" role="tablist" aria-label={t('admin.legal.title')}>
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
          >
            {t(item.labelKey)}
          </button>
        ))}
      </div>
      {panel}
    </PortalPage>
  );
}
