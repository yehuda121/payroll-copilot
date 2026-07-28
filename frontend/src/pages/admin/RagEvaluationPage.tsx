import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { useToast } from '../../components/ui/Toast';
import {
  AnalyticsEmptyState,
  AnalyticsErrorState,
  AnalyticsLoadingState,
  LineChartCard,
} from '../../features/analytics';
import { ANALYTICS_CHART_COLORS } from '../../features/analytics/chartColors';
import { useAnalyticsResource } from '../../hooks/useAnalyticsResource';
import {
  ragEvaluationService,
  type EvaluationCaseResult,
  type EvaluationRun,
  type RagEvalMetricValue,
} from '../../services/ragEvaluation';
import { formatDateTime, formatDelta, formatRagMetric, statusBadgeClass } from './adminFormatters';
import './admin-ai.css';

const METRIC_KEYS = [
  { key: 'faithfulness' as const, labelKey: 'admin.rag.metrics.faithfulness' },
  { key: 'context_precision' as const, labelKey: 'admin.rag.metrics.contextPrecision' },
  { key: 'context_recall' as const, labelKey: 'admin.rag.metrics.contextRecall' },
  { key: 'answer_relevancy' as const, labelKey: 'admin.rag.metrics.answerRelevancy' },
  { key: 'temporal_accuracy' as const, labelKey: 'admin.rag.metrics.temporalAccuracy' },
];

function MetricKpi({ label, metric }: { label: string; metric: RagEvalMetricValue | undefined }) {
  const { t } = useTranslation();
  const formatted = formatRagMetric(metric);
  return (
    <div className="admin-ai-kpi">
      <span>{label}</span>
      {formatted.unavailable ? (
        <strong className="admin-ai-metric-unavailable" title={formatted.reason ?? undefined}>
          {t('admin.rag.unavailable')}
        </strong>
      ) : (
        <strong>{formatted.label}</strong>
      )}
    </div>
  );
}

function RunMetrics({ run }: { run: EvaluationRun }) {
  const { t } = useTranslation();
  return (
    <div className="admin-ai-kpis">
      {METRIC_KEYS.map(({ key, labelKey }) => (
        <MetricKpi key={key} label={t(labelKey)} metric={run[key]} />
      ))}
    </div>
  );
}

function trendRowsFromRuns(runs: EvaluationRun[]) {
  return [...runs]
    .filter((run) => run.status === 'COMPLETED')
    .reverse()
    .map((run) => ({
      time: new Date(run.completed_at ?? run.started_at).toLocaleDateString(),
      faithfulness: run.faithfulness.status === 'ok' ? (run.faithfulness.value ?? 0) * 100 : null,
      context_precision:
        run.context_precision.status === 'ok' ? (run.context_precision.value ?? 0) * 100 : null,
      context_recall: run.context_recall.status === 'ok' ? (run.context_recall.value ?? 0) * 100 : null,
      answer_relevancy:
        run.answer_relevancy.status === 'ok' ? (run.answer_relevancy.value ?? 0) * 100 : null,
      temporal_accuracy:
        run.temporal_accuracy.status === 'ok' ? (run.temporal_accuracy.value ?? 0) * 100 : null,
    }));
}

export function RagEvaluationPage() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const summary = useAnalyticsResource(
    useCallback((signal: AbortSignal) => ragEvaluationService.summary(signal), []),
    [],
    t('admin.rag.errors.summary'),
  );
  const runs = useAnalyticsResource(
    useCallback((signal: AbortSignal) => ragEvaluationService.listRuns(50, signal), []),
    [],
    t('admin.rag.errors.runs'),
  );
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [cases, setCases] = useState<EvaluationCaseResult[]>([]);
  const [casesLoading, setCasesLoading] = useState(false);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [compareRunA, setCompareRunA] = useState('');
  const [compareRunB, setCompareRunB] = useState('');
  const [compareResult, setCompareResult] = useState<Awaited<
    ReturnType<typeof ragEvaluationService.compare>
  > | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [running, setRunning] = useState(false);

  const completedRuns = useMemo(
    () => (runs.data ?? []).filter((run) => run.status === 'COMPLETED'),
    [runs.data],
  );
  const trendRows = useMemo(() => trendRowsFromRuns(completedRuns), [completedRuns]);
  const latestRun = summary.data?.latest_run ?? completedRuns[0] ?? null;

  useEffect(() => {
    if (!selectedRunId) {
      setCases([]);
      setSelectedCaseId(null);
      return;
    }
    const controller = new AbortController();
    setCasesLoading(true);
    void ragEvaluationService
      .listCases(selectedRunId, controller.signal)
      .then(setCases)
      .catch(() => setCases([]))
      .finally(() => setCasesLoading(false));
    return () => controller.abort();
  }, [selectedRunId]);

  const selectedCase = cases.find((item) => item.case_id === selectedCaseId) ?? null;

  const startEvaluation = async () => {
    setRunning(true);
    try {
      const run = await ragEvaluationService.startRun();
      showToast({ message: t('admin.rag.toasts.started', { runId: run.run_id }), tone: 'success' });
      runs.reload();
      summary.reload();
      setSelectedRunId(run.run_id);
    } catch (err) {
      showToast({
        message: err instanceof Error ? err.message : t('admin.rag.toasts.startFailed'),
        tone: 'error',
      });
    } finally {
      setRunning(false);
    }
  };

  const runCompare = async () => {
    if (!compareRunA || !compareRunB || compareRunA === compareRunB) {
      showToast({ message: t('admin.rag.toasts.selectTwoRuns'), tone: 'warning' });
      return;
    }
    setCompareLoading(true);
    try {
      const result = await ragEvaluationService.compare(compareRunA, compareRunB);
      setCompareResult(result);
    } catch (err) {
      showToast({
        message: err instanceof Error ? err.message : t('admin.rag.toasts.compareFailed'),
        tone: 'error',
      });
      setCompareResult(null);
    } finally {
      setCompareLoading(false);
    }
  };

  const loading = (summary.loading && !summary.data) || (runs.loading && !runs.data);
  const error = summary.error || runs.error;

  return (
    <PortalPage title={t('admin.rag.title')} description={t('admin.rag.description')}>
      <div className="admin-ai-toolbar">
        <button type="button" className="btn btn--primary" onClick={() => void startEvaluation()} disabled={running}>
          {running ? t('admin.rag.starting') : t('admin.rag.runEvaluation')}
        </button>
        {summary.data ? (
          <p className="admin-ai-muted">
            {summary.data.ragas_available
              ? t('admin.rag.ragasVersion', { version: summary.data.ragas_version ?? '?' })
              : t('admin.rag.ragasUnavailable')}
            {summary.data.ragas_import_error ? ` — ${summary.data.ragas_import_error}` : ''}
          </p>
        ) : null}
      </div>

      {loading ? <AnalyticsLoadingState cards={5} label={t('admin.rag.loading')} /> : null}

      {error ? (
        <AnalyticsErrorState
          title={t('admin.rag.errors.page')}
          message={error}
          onRetry={() => {
            summary.reload();
            runs.reload();
          }}
        />
      ) : null}

      {!loading && !error ? (
        <div className="admin-ai">
          <section className="admin-dashboard-section">
            <header className="admin-dashboard-section__header">
              <h2>{t('admin.rag.sections.latest')}</h2>
              <p>{t('admin.rag.sections.latestDesc')}</p>
            </header>
            {latestRun ? (
              <section className="admin-ai-card">
                <h2>{t('admin.rag.latestRun')}</h2>
                <p className="admin-ai-muted">
                  {t('admin.rag.latestRunSummary', {
                    runId: latestRun.run_id,
                    dataset: latestRun.dataset_version,
                    when: formatDateTime(latestRun.completed_at ?? latestRun.started_at),
                  })}
                </p>
                <RunMetrics run={latestRun} />
              </section>
            ) : (
              <AnalyticsEmptyState
                title={t('admin.rag.empty')}
                description={t('admin.rag.emptyHint')}
              />
            )}
          </section>

          {trendRows.length > 1 ? (
            <section className="admin-dashboard-section">
              <header className="admin-dashboard-section__header">
                <h2>{t('admin.rag.sections.trends')}</h2>
                <p>{t('admin.rag.sections.trendsDesc')}</p>
              </header>
              <LineChartCard
                title={t('admin.rag.metricTrends')}
                data={trendRows}
                xKey="time"
                yLabel="%"
                series={[
                  {
                    dataKey: 'faithfulness',
                    name: t('admin.rag.metrics.faithfulness'),
                    color: ANALYTICS_CHART_COLORS.primary,
                  },
                  {
                    dataKey: 'context_precision',
                    name: t('admin.rag.metrics.contextPrecision'),
                    color: ANALYTICS_CHART_COLORS.secondary,
                  },
                  {
                    dataKey: 'context_recall',
                    name: t('admin.rag.metrics.contextRecall'),
                    color: ANALYTICS_CHART_COLORS.warning,
                  },
                  {
                    dataKey: 'answer_relevancy',
                    name: t('admin.rag.metrics.answerRelevancy'),
                    color: ANALYTICS_CHART_COLORS.danger,
                  },
                  {
                    dataKey: 'temporal_accuracy',
                    name: t('admin.rag.metrics.temporalAccuracy'),
                    color: ANALYTICS_CHART_COLORS.primary,
                  },
                ]}
              />
            </section>
          ) : null}

          <section className="admin-dashboard-section">
            <header className="admin-dashboard-section__header">
              <h2>{t('admin.rag.sections.history')}</h2>
              <p>{t('admin.rag.sections.historyDesc')}</p>
            </header>
            <section className="admin-ai-card">
              <h2>{t('admin.rag.runHistory')}</h2>
              {(runs.data ?? []).length === 0 ? (
                <p className="admin-ai-muted">{t('admin.rag.noRuns')}</p>
              ) : (
                <div className="admin-ai-table-wrap">
                  <table className="admin-ai-table">
                    <thead>
                      <tr>
                        <th>{t('admin.rag.cols.run')}</th>
                        <th>{t('admin.rag.cols.status')}</th>
                        <th>{t('admin.rag.cols.cases')}</th>
                        <th>{t('admin.rag.cols.started')}</th>
                        <th>{t('admin.rag.metrics.faithfulness')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(runs.data ?? []).map((run) => {
                        const faithfulness = formatRagMetric(run.faithfulness);
                        return (
                          <tr
                            key={run.run_id}
                            className={selectedRunId === run.run_id ? 'is-selected' : ''}
                            onClick={() => setSelectedRunId(run.run_id)}
                          >
                            <td>{run.run_id}</td>
                            <td>
                              <span className={statusBadgeClass(run.status)}>{run.status}</span>
                            </td>
                            <td>
                              {run.completed_cases}/{run.case_count}
                            </td>
                            <td>{formatDateTime(run.started_at)}</td>
                            <td className={faithfulness.unavailable ? 'admin-ai-metric-unavailable' : ''}>
                              {faithfulness.unavailable ? t('admin.rag.unavailable') : faithfulness.label}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </section>

          {selectedRunId ? (
            <section className="admin-dashboard-section">
              <header className="admin-dashboard-section__header">
                <h2>{t('admin.rag.sections.cases')}</h2>
                <p>{t('admin.rag.sections.casesDesc')}</p>
              </header>
              <div className="admin-ai-split">
                <section className="admin-ai-card">
                  <h2>{t('admin.rag.casesForRun', { runId: selectedRunId })}</h2>
                  {casesLoading ? <p className="admin-ai-muted">{t('admin.rag.loadingCases')}</p> : null}
                  {!casesLoading && cases.length === 0 ? (
                    <p className="admin-ai-muted">{t('admin.rag.noCases')}</p>
                  ) : null}
                  {cases.length > 0 ? (
                    <div className="admin-ai-table-wrap">
                      <table className="admin-ai-table">
                        <thead>
                          <tr>
                            <th>{t('admin.rag.cols.case')}</th>
                            <th>{t('admin.rag.cols.status')}</th>
                            <th>{t('admin.rag.cols.temporal')}</th>
                            <th>{t('admin.rag.metrics.faithfulness')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {cases.map((item) => {
                            const faithfulness = formatRagMetric(item.faithfulness);
                            return (
                              <tr
                                key={item.case_id}
                                className={selectedCaseId === item.case_id ? 'is-selected' : ''}
                                onClick={() => setSelectedCaseId(item.case_id)}
                              >
                                <td>{item.case_id}</td>
                                <td>{item.status}</td>
                                <td>
                                  {item.temporal_pass == null
                                    ? t('common.emDash')
                                    : item.temporal_pass
                                      ? t('admin.rag.pass')
                                      : t('admin.rag.fail')}
                                </td>
                                <td className={faithfulness.unavailable ? 'admin-ai-metric-unavailable' : ''}>
                                  {faithfulness.unavailable ? t('admin.rag.unavailable') : faithfulness.label}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                </section>
                <aside className="admin-ai-detail">
                  <h3>{t('admin.rag.caseDetail')}</h3>
                  {!selectedCase ? <p className="admin-ai-muted">{t('admin.rag.selectCase')}</p> : null}
                  {selectedCase ? (
                    <>
                      <dl>
                        <div>
                          <dt>{t('admin.rag.fields.question')}</dt>
                          <dd>{selectedCase.question}</dd>
                        </div>
                        <div>
                          <dt>{t('admin.rag.fields.effectiveDate')}</dt>
                          <dd>{selectedCase.effective_date ?? t('common.emDash')}</dd>
                        </div>
                        <div>
                          <dt>{t('admin.rag.fields.expectedRules')}</dt>
                          <dd>{selectedCase.expected_rule_ids.join(', ') || t('common.emDash')}</dd>
                        </div>
                        <div>
                          <dt>{t('admin.rag.fields.retrievedRules')}</dt>
                          <dd>{selectedCase.retrieved_rule_ids.join(', ') || t('common.emDash')}</dd>
                        </div>
                        <div>
                          <dt>{t('admin.rag.fields.retrievalMode')}</dt>
                          <dd>{selectedCase.retrieval_mode ?? t('common.emDash')}</dd>
                        </div>
                      </dl>
                      <h3>{t('admin.rag.fields.generatedAnswer')}</h3>
                      <pre className="admin-ai-pre">
                        {selectedCase.generated_answer || t('common.emDash')}
                      </pre>
                      <h3>{t('admin.rag.fields.referenceAnswer')}</h3>
                      <pre className="admin-ai-pre">
                        {selectedCase.reference_answer || t('common.emDash')}
                      </pre>
                      {selectedCase.error ? (
                        <p className="admin-ai-error">{selectedCase.error}</p>
                      ) : null}
                    </>
                  ) : null}
                </aside>
              </div>
            </section>
          ) : null}

          <section className="admin-dashboard-section">
            <header className="admin-dashboard-section__header">
              <h2>{t('admin.rag.sections.compare')}</h2>
              <p>{t('admin.rag.sections.compareDesc')}</p>
            </header>
            <section className="admin-ai-card">
              <h2>{t('admin.rag.compareRuns')}</h2>
              <div className="admin-ai-toolbar">
                <label className="admin-ai-window">
                  <span>{t('admin.rag.runA')}</span>
                  <select value={compareRunA} onChange={(event) => setCompareRunA(event.target.value)}>
                    <option value="">{t('admin.rag.selectPlaceholder')}</option>
                    {completedRuns.map((run) => (
                      <option key={run.run_id} value={run.run_id}>
                        {run.run_id}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="admin-ai-window">
                  <span>{t('admin.rag.runB')}</span>
                  <select value={compareRunB} onChange={(event) => setCompareRunB(event.target.value)}>
                    <option value="">{t('admin.rag.selectPlaceholder')}</option>
                    {completedRuns.map((run) => (
                      <option key={run.run_id} value={run.run_id}>
                        {run.run_id}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="btn btn--secondary"
                  onClick={() => void runCompare()}
                  disabled={compareLoading}
                >
                  {compareLoading ? t('admin.rag.comparing') : t('admin.rag.compare')}
                </button>
              </div>
              {compareResult ? (
                <>
                  {compareResult.dataset_version_mismatch ? (
                    <p className="admin-ai-muted">{t('admin.rag.datasetMismatch')}</p>
                  ) : null}
                  <div className="admin-ai-kpis">
                    {METRIC_KEYS.map(({ key, labelKey }) => (
                      <div className="admin-ai-kpi" key={key}>
                        <span>{t('admin.rag.deltaLabel', { metric: t(labelKey) })}</span>
                        <strong>{formatDelta(compareResult.deltas[key])}</strong>
                      </div>
                    ))}
                  </div>
                  <p className="admin-ai-muted">
                    {t('admin.rag.compareSummary', {
                      improved: compareResult.improved_cases.length,
                      regressed: compareResult.regressed_cases.length,
                    })}
                  </p>
                </>
              ) : null}
            </section>
          </section>
        </div>
      ) : null}
    </PortalPage>
  );
}
