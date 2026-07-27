import { useCallback, useEffect, useMemo, useState } from 'react';
import { PortalPage } from '../../components/PortalPage';
import { ModalDialog } from '../../components/ui/Dialog';
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

const TABS: Array<{ id: TabId; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'rules', label: 'Rules' },
  { id: 'sources', label: 'Sources' },
  { id: 'proposals', label: 'Pending Changes' },
  { id: 'sync', label: 'Sync History' },
  { id: 'vector', label: 'Vector Index' },
];

function VectorHealthCard({ health }: { health: VectorIndexHealth }) {
  return (
    <section className="admin-ai-card">
      <h2>Vector index</h2>
      <dl className="admin-ai-detail">
        <div>
          <dt>Status</dt>
          <dd>
            <span className={statusBadgeClass(health.status)}>{health.status}</span>
          </dd>
        </div>
        <div>
          <dt>Backend</dt>
          <dd>{health.backend}</dd>
        </div>
        <div>
          <dt>Embedding model</dt>
          <dd>{health.embedding_model ?? '—'}</dd>
        </div>
        <div>
          <dt>Indexed rules / versions / chunks</dt>
          <dd>
            {health.indexed_rules} / {health.indexed_versions} / {health.chunk_count}
          </dd>
        </div>
        <div>
          <dt>Last indexed</dt>
          <dd>{formatDateTime(health.last_indexed_at)}</dd>
        </div>
        {health.last_error ? (
          <div>
            <dt>Last error</dt>
            <dd className="admin-ai-error">{health.last_error}</dd>
          </div>
        ) : null}
      </dl>
    </section>
  );
}

function OverviewTab() {
  const overview = useAnalyticsResource(
    useCallback((signal: AbortSignal) => legalKnowledgeService.overview(signal), []),
    [],
    'Unable to load legal knowledge overview.',
  );

  if (overview.loading && !overview.data) {
    return <AnalyticsLoadingState cards={6} label="Loading overview" />;
  }
  if (overview.error) {
    return (
      <AnalyticsErrorState
        title="Unable to load overview"
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
          <span>Active rules</span>
          <strong>{data.active_rules.toLocaleString()}</strong>
        </div>
        <div className="admin-ai-kpi">
          <span>Historical versions</span>
          <strong>{data.historical_versions.toLocaleString()}</strong>
        </div>
        <div className="admin-ai-kpi">
          <span>Watched sources</span>
          <strong>{data.watched_sources.toLocaleString()}</strong>
        </div>
        <div className="admin-ai-kpi">
          <span>Discovery sources</span>
          <strong>{data.discovery_sources.toLocaleString()}</strong>
        </div>
        <div className="admin-ai-kpi">
          <span>Pending changes</span>
          <strong>{data.pending_changes.toLocaleString()}</strong>
        </div>
        <div className="admin-ai-kpi">
          <span>Last sync</span>
          <strong>{data.last_sync ? formatDateTime(data.last_sync.completed_at ?? data.last_sync.started_at) : 'Never'}</strong>
        </div>
      </div>
      <VectorHealthCard health={data.vector_index} />
      {data.last_sync ? (
        <section className="admin-ai-card">
          <h2>Latest sync run</h2>
          <p className="admin-ai-muted">
            {data.last_sync.run_id} · {data.last_sync.status} · checked {data.last_sync.sources_checked}{' '}
            sources · {data.last_sync.material_change_count} material · {data.last_sync.error_count} errors
          </p>
        </section>
      ) : (
        <AnalyticsEmptyState
          title="No sync runs yet"
          description="Trigger a manual sync from Sync History or Vector Index tabs."
        />
      )}
    </div>
  );
}

function RulesTab() {
  const rules = useAnalyticsResource(
    useCallback((signal: AbortSignal) => legalKnowledgeService.listRules(signal), []),
    [],
    'Unable to load rules.',
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

  return (
    <div className="admin-ai">
      {rules.loading && rows.length === 0 ? (
        <AnalyticsLoadingState cards={2} label="Loading rules" />
      ) : null}
      {rules.error ? (
        <AnalyticsErrorState title="Unable to load rules" message={rules.error} onRetry={rules.reload} />
      ) : null}
      {!rules.loading && !rules.error && rows.length === 0 ? (
        <AnalyticsEmptyState title="No rules found" description="Rule catalog is empty or not seeded yet." />
      ) : null}
      {rows.length > 0 ? (
        <div className="admin-ai-split">
          <div className="admin-ai-table-wrap">
            <table className="admin-ai-table">
              <thead>
                <tr>
                  <th>Rule</th>
                  <th>Version</th>
                  <th>Validation</th>
                  <th>Source monitoring</th>
                  <th>Vector</th>
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
                    <td>{row.validation_readiness ?? 'Unavailable'}</td>
                    <td>{row.source_coverage}</td>
                    <td>{row.index_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <aside className="admin-ai-detail">
            <h3>Rule detail</h3>
            {!selectedRuleId ? <p className="admin-ai-muted">Select a rule to view version timeline.</p> : null}
            {detailLoading ? <p className="admin-ai-muted">Loading…</p> : null}
            {detailError ? <p className="admin-ai-error">{detailError}</p> : null}
            {detail ? (
              <>
                <dl>
                  <div>
                    <dt>Validation readiness</dt>
                    <dd>{detail.validation_readiness ?? 'Unavailable'}</dd>
                  </div>
                  <div>
                    <dt>Readiness reason</dt>
                    <dd>{detail.validation_readiness_reason ?? 'Unavailable'}</dd>
                  </div>
                  <div>
                    <dt>Required inputs</dt>
                    <dd>
                      {(detail.required_fields && detail.required_fields.length > 0
                        ? detail.required_fields.join(', ')
                        : null) ?? 'Unavailable'}
                    </dd>
                  </div>
                  <div>
                    <dt>Active version</dt>
                    <dd>{detail.active?.version ?? '—'}</dd>
                  </div>
                  <div>
                    <dt>Valid from / to</dt>
                    <dd>
                      {formatDate(detail.active?.valid_from ?? null)} →{' '}
                      {formatDate(detail.active?.valid_to ?? null)}
                    </dd>
                  </div>
                  <div>
                    <dt>Source monitoring</dt>
                    <dd>{detail.source_monitoring_status ?? 'Unavailable'}</dd>
                  </div>
                  <div>
                    <dt>Last source sync</dt>
                    <dd>{formatDate(detail.last_source_sync ?? null)}</dd>
                  </div>
                  <div>
                    <dt>Vector index</dt>
                    <dd>{detail.vector_index_status ?? 'Unavailable'}</dd>
                  </div>
                </dl>
                <h3>Version timeline</h3>
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
  const sources = useAnalyticsResource(
    useCallback((signal: AbortSignal) => legalKnowledgeService.listSources(signal), []),
    [],
    'Unable to load sources.',
  );
  const rows = sources.data ?? [];

  return (
    <div className="admin-ai">
      {sources.loading && rows.length === 0 ? (
        <AnalyticsLoadingState cards={2} label="Loading sources" />
      ) : null}
      {sources.error ? (
        <AnalyticsErrorState title="Unable to load sources" message={sources.error} onRetry={sources.reload} />
      ) : null}
      {!sources.loading && !sources.error && rows.length === 0 ? (
        <AnalyticsEmptyState title="No sources configured" description="Add sources in the legal source registry." />
      ) : null}
      {rows.length > 0 ? (
        <div className="admin-ai-table-wrap">
          <table className="admin-ai-table">
            <thead>
              <tr>
                <th>Source</th>
                <th>Type</th>
                <th>Authority</th>
                <th>Enabled</th>
                <th>Last checked</th>
                <th>Related rules</th>
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
                  <td>{source.enabled ? 'Yes' : 'No'}</td>
                  <td>{formatDateTime(source.last_checked_at)}</td>
                  <td>{source.related_rule_ids.join(', ') || '—'}</td>
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
  const { showToast } = useToast();
  const proposals = useAnalyticsResource(
    useCallback((signal: AbortSignal) => legalKnowledgeService.listProposals('PENDING_REVIEW', signal), []),
    [],
    'Unable to load proposals.',
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
      showToast({ message: 'Confirm the effective date before approving.', tone: 'warning' });
      return;
    }
    setSubmitting(true);
    try {
      await legalKnowledgeService.approveProposal(selectedId, {
        effective_date: effectiveDate,
        confirm_effective_date: true,
      });
      showToast({ message: 'Proposal approved.', tone: 'success' });
      closeDialog();
      setSelectedId(null);
      proposals.reload();
    } catch (err) {
      showToast({ message: err instanceof Error ? err.message : 'Approval failed.', tone: 'error' });
    } finally {
      setSubmitting(false);
    }
  };

  const submitReject = async () => {
    if (!selectedId) return;
    setSubmitting(true);
    try {
      await legalKnowledgeService.rejectProposal(selectedId, { reason: rejectReason || undefined });
      showToast({ message: 'Proposal rejected.', tone: 'success' });
      closeDialog();
      setSelectedId(null);
      proposals.reload();
    } catch (err) {
      showToast({ message: err instanceof Error ? err.message : 'Rejection failed.', tone: 'error' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="admin-ai">
      {proposals.loading && rows.length === 0 ? (
        <AnalyticsLoadingState cards={2} label="Loading proposals" />
      ) : null}
      {proposals.error ? (
        <AnalyticsErrorState
          title="Unable to load proposals"
          message={proposals.error}
          onRetry={proposals.reload}
        />
      ) : null}
      {!proposals.loading && !proposals.error && rows.length === 0 ? (
        <AnalyticsEmptyState title="No pending changes" description="All proposals are reviewed." />
      ) : null}
      {rows.length > 0 ? (
        <div className="admin-ai-split">
          <div className="admin-ai-table-wrap">
            <table className="admin-ai-table">
              <thead>
                <tr>
                  <th>Proposal</th>
                  <th>Classification</th>
                  <th>Rules</th>
                  <th>Created</th>
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
                    <td>{proposal.affected_rule_ids.join(', ') || '—'}</td>
                    <td>{formatDateTime(proposal.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <aside className="admin-ai-detail">
            <h3>Proposal detail</h3>
            {!selectedId ? <p className="admin-ai-muted">Select a proposal to review.</p> : null}
            {detailLoading ? <p className="admin-ai-muted">Loading…</p> : null}
            {detail ? (
              <>
                <dl>
                  <div>
                    <dt>AI summary</dt>
                    <dd>{detail.proposal.ai_summary || '—'}</dd>
                  </div>
                  <div>
                    <dt>Candidate effective date</dt>
                    <dd>{formatDate(detail.proposal.candidate_effective_date)}</dd>
                  </div>
                  <div>
                    <dt>Confidence</dt>
                    <dd>
                      {detail.proposal.confidence != null
                        ? `${(detail.proposal.confidence * 100).toFixed(0)}%`
                        : '—'}
                    </dd>
                  </div>
                </dl>
                {detail.proposal.diff_text ? (
                  <>
                    <h3>Diff</h3>
                    <pre className="admin-ai-pre">{detail.proposal.diff_text}</pre>
                  </>
                ) : null}
                <div className="admin-ai-actions">
                  <button type="button" className="btn btn--primary" onClick={() => setDialogMode('approve')}>
                    Approve
                  </button>
                  <button type="button" className="btn btn--danger" onClick={() => setDialogMode('reject')}>
                    Reject
                  </button>
                </div>
              </>
            ) : null}
          </aside>
        </div>
      ) : null}

      {dialogMode === 'approve' ? (
        <ModalDialog
          title="Approve proposal"
          variant="warning"
          onClose={closeDialog}
          footer={
            <>
              <button type="button" className="btn btn--secondary" onClick={closeDialog} disabled={submitting}>
                Cancel
              </button>
              <button type="button" className="btn btn--primary" onClick={() => void submitApprove()} disabled={submitting}>
                Approve
              </button>
            </>
          }
        >
          <label className="admin-ai-window">
            <span>Effective date</span>
            <input
              type="date"
              value={effectiveDate}
              onChange={(event) => setEffectiveDate(event.target.value)}
            />
          </label>
          <label style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginTop: '0.75rem' }}>
            <input
              type="checkbox"
              checked={confirmDate}
              onChange={(event) => setConfirmDate(event.target.checked)}
            />
            <span>I confirm this effective date is correct for payroll rules.</span>
          </label>
        </ModalDialog>
      ) : null}

      {dialogMode === 'reject' ? (
        <ModalDialog
          title="Reject proposal"
          variant="danger"
          onClose={closeDialog}
          footer={
            <>
              <button type="button" className="btn btn--secondary" onClick={closeDialog} disabled={submitting}>
                Cancel
              </button>
              <button type="button" className="btn btn--danger" onClick={() => void submitReject()} disabled={submitting}>
                Reject
              </button>
            </>
          }
        >
          <label className="admin-ai-window">
            <span>Reason (optional)</span>
            <textarea
              rows={4}
              value={rejectReason}
              onChange={(event) => setRejectReason(event.target.value)}
            />
          </label>
        </ModalDialog>
      ) : null}
    </div>
  );
}

function SyncHistoryTab() {
  const { showToast } = useToast();
  const syncRuns = useAnalyticsResource(
    useCallback((signal: AbortSignal) => legalKnowledgeService.listSyncRuns(50, signal), []),
    [],
    'Unable to load sync history.',
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
      showToast({ message: `Sync started (${run.run_id}).`, tone: 'success' });
      syncRuns.reload();
      setSelectedRunId(run.run_id);
    } catch (err) {
      showToast({ message: err instanceof Error ? err.message : 'Sync failed.', tone: 'error' });
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="admin-ai">
      <div className="admin-ai-toolbar">
        <button type="button" className="btn btn--primary" onClick={() => void triggerSync()} disabled={syncing}>
          {syncing ? 'Syncing…' : 'Run sync now'}
        </button>
      </div>
      {syncRuns.loading && rows.length === 0 ? (
        <AnalyticsLoadingState cards={2} label="Loading sync history" />
      ) : null}
      {syncRuns.error ? (
        <AnalyticsErrorState
          title="Unable to load sync history"
          message={syncRuns.error}
          onRetry={syncRuns.reload}
        />
      ) : null}
      {!syncRuns.loading && !syncRuns.error && rows.length === 0 ? (
        <AnalyticsEmptyState title="No sync runs yet" description="Trigger a manual sync to populate history." />
      ) : null}
      {rows.length > 0 ? (
        <div className="admin-ai-split">
          <div className="admin-ai-table-wrap">
            <table className="admin-ai-table">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Status</th>
                  <th>Started</th>
                  <th>Sources</th>
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
            <h3>Run detail</h3>
            {!selectedRun ? <p className="admin-ai-muted">Select a sync run.</p> : null}
            {selectedRun ? (
              <>
                <dl>
                  <div>
                    <dt>Trigger</dt>
                    <dd>{selectedRun.trigger}</dd>
                  </div>
                  <div>
                    <dt>Completed</dt>
                    <dd>{formatDateTime(selectedRun.completed_at)}</dd>
                  </div>
                  <div>
                    <dt>Counts</dt>
                    <dd>
                      material {selectedRun.material_change_count} · new {selectedRun.new_relevant_count} ·
                      errors {selectedRun.error_count}
                    </dd>
                  </div>
                </dl>
                <h3>Outcomes</h3>
                <ul className="admin-ai-timeline">
                  {selectedRun.outcomes.map((outcome) => (
                    <li key={`${outcome.source_id}-${outcome.classification}`}>
                      <strong>{outcome.source_id}</strong> — {outcome.classification}
                      <div className="admin-ai-muted">{outcome.message || outcome.error || '—'}</div>
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
  const { showToast } = useToast();
  const health = useAnalyticsResource(
    useCallback((signal: AbortSignal) => legalKnowledgeService.vectorIndexHealth(signal), []),
    [],
    'Unable to load vector index health.',
  );
  const [rebuilding, setRebuilding] = useState(false);

  const rebuild = async () => {
    setRebuilding(true);
    try {
      await legalKnowledgeService.rebuildVectorIndex();
      showToast({ message: 'Vector index rebuild completed.', tone: 'success' });
      health.reload();
    } catch (err) {
      showToast({ message: err instanceof Error ? err.message : 'Rebuild failed.', tone: 'error' });
    } finally {
      setRebuilding(false);
    }
  };

  if (health.loading && !health.data) {
    return <AnalyticsLoadingState cards={2} label="Loading vector index" />;
  }
  if (health.error) {
    return (
      <AnalyticsErrorState
        title="Unable to load vector index"
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
          {rebuilding ? 'Rebuilding…' : 'Rebuild index'}
        </button>
      </div>
      <VectorHealthCard health={health.data} />
    </div>
  );
}

export function LegalKnowledgePage() {
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
    <PortalPage
      title="Legal Knowledge"
      description="Versioned legal rules, source sync, change proposals, and vector index health."
    >
      <div className="admin-ai-tabs" role="tablist" aria-label="Legal knowledge sections">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      {panel}
    </PortalPage>
  );
}
