import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import {
  getCurrentEvaluationStatus,
  getLatestImprovement,
  getPromptById,
  listPromptCatalog,
  resolveDefaultVersionNumber,
  selectPromptVersion,
  type PromptDefinition,
  type PromptStatus,
  type PromptTestCaseResult,
} from '../../lib/admin/prompt-engineering';
import { formatDateTime, statusBadgeClass } from './adminFormatters';
import './admin-ai.css';

function promptStatusClass(status: PromptStatus): string {
  if (status === 'Production') return statusBadgeClass('ACTIVE');
  if (status === 'Experimental') return statusBadgeClass('PENDING_REVIEW');
  return statusBadgeClass('REJECTED');
}

function evaluationStatusClass(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized === 'pass') return statusBadgeClass('OK');
  if (normalized === 'warning' || normalized === 'pending') return statusBadgeClass('UNCERTAIN');
  if (normalized === 'fail') return statusBadgeClass('FAILED');
  return statusBadgeClass(status);
}

function testCaseClass(result: PromptTestCaseResult): string {
  if (result === 'PASS') return statusBadgeClass('OK');
  if (result === 'WARNING') return statusBadgeClass('UNCERTAIN');
  return statusBadgeClass('FAILED');
}

function PromptCatalogList({
  prompts,
  selectedId,
  onSelect,
}: {
  prompts: PromptDefinition[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <section className="admin-ai-card" aria-label={t('admin.promptEngineering.catalogTitle')}>
      <h2>{t('admin.promptEngineering.catalogTitle')}</h2>
      <p className="admin-ai-muted">{t('admin.promptEngineering.catalogHint')}</p>
      <div className="admin-ai-table-wrap">
        <table className="admin-ai-table">
          <thead>
            <tr>
              <th scope="col">{t('admin.promptEngineering.cols.name')}</th>
              <th scope="col">{t('admin.promptEngineering.cols.category')}</th>
              <th scope="col">{t('admin.promptEngineering.cols.status')}</th>
            </tr>
          </thead>
          <tbody>
            {prompts.map((prompt) => (
              <tr
                key={prompt.id}
                className={selectedId === prompt.id ? 'is-selected' : ''}
                onClick={() => onSelect(prompt.id)}
              >
                <td>
                  <strong>{prompt.name}</strong>
                  <div className="admin-ai-muted">{prompt.current_version}</div>
                </td>
                <td>{prompt.category}</td>
                <td>
                  <span className={promptStatusClass(prompt.status)}>{prompt.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PromptDetailsPanel({
  prompt,
  selectedVersionNumber,
  onSelectVersion,
}: {
  prompt: PromptDefinition;
  selectedVersionNumber: string;
  onSelectVersion: (version: string) => void;
}) {
  const { t } = useTranslation();
  const selectedVersion = selectPromptVersion(prompt, selectedVersionNumber);
  const currentEval = getCurrentEvaluationStatus(prompt);

  return (
    <div className="admin-ai">
      <section className="admin-ai-card">
        <h2>{t('admin.promptEngineering.detailsTitle')}</h2>
        <dl className="admin-ai-detail">
          <div>
            <dt>{t('admin.promptEngineering.fields.name')}</dt>
            <dd>{prompt.name}</dd>
          </div>
          <div>
            <dt>{t('admin.promptEngineering.fields.purpose')}</dt>
            <dd>{prompt.purpose}</dd>
          </div>
          <div>
            <dt>{t('admin.promptEngineering.fields.model')}</dt>
            <dd>{prompt.model}</dd>
          </div>
          <div>
            <dt>{t('admin.promptEngineering.fields.owner')}</dt>
            <dd>{prompt.owner}</dd>
          </div>
          <div>
            <dt>{t('admin.promptEngineering.fields.status')}</dt>
            <dd>
              <span className={promptStatusClass(prompt.status)}>{prompt.status}</span>
            </dd>
          </div>
          <div>
            <dt>{t('admin.promptEngineering.fields.currentVersion')}</dt>
            <dd>
              <span className={statusBadgeClass('ACTIVE')}>{prompt.current_version}</span>
            </dd>
          </div>
          <div>
            <dt>{t('admin.promptEngineering.fields.latestImprovement')}</dt>
            <dd>{getLatestImprovement(prompt) || t('common.emDash')}</dd>
          </div>
          <div>
            <dt>{t('admin.promptEngineering.fields.lastUpdated')}</dt>
            <dd>{formatDateTime(prompt.last_updated)}</dd>
          </div>
          <div>
            <dt>{t('admin.promptEngineering.fields.evaluationStatus')}</dt>
            <dd>
              {currentEval ? (
                <span className={evaluationStatusClass(currentEval)}>{currentEval}</span>
              ) : (
                t('common.emDash')
              )}
            </dd>
          </div>
        </dl>
      </section>

      <section className="admin-ai-card">
        <h2>{t('admin.promptEngineering.versionHistoryTitle')}</h2>
        <div className="admin-ai-table-wrap">
          <table className="admin-ai-table">
            <thead>
              <tr>
                <th scope="col">{t('admin.promptEngineering.cols.version')}</th>
                <th scope="col">{t('admin.promptEngineering.cols.date')}</th>
                <th scope="col">{t('admin.promptEngineering.cols.author')}</th>
                <th scope="col">{t('admin.promptEngineering.cols.summary')}</th>
                <th scope="col">{t('admin.promptEngineering.cols.evalStatus')}</th>
                <th scope="col">{t('admin.promptEngineering.cols.current')}</th>
              </tr>
            </thead>
            <tbody>
              {[...prompt.versions].reverse().map((item) => {
                const isCurrent = item.version_number === prompt.current_version;
                return (
                  <tr
                    key={item.version_number}
                    className={selectedVersionNumber === item.version_number ? 'is-selected' : ''}
                    onClick={() => onSelectVersion(item.version_number)}
                  >
                    <td>{item.version_number}</td>
                    <td>{formatDateTime(item.created_at)}</td>
                    <td>{item.author}</td>
                    <td>{item.summary}</td>
                    <td>
                      <span className={evaluationStatusClass(item.evaluation_status)}>
                        {item.evaluation_status}
                      </span>
                    </td>
                    <td>
                      {isCurrent ? (
                        <span className={statusBadgeClass('ACTIVE')}>
                          {t('admin.promptEngineering.currentBadge')}
                        </span>
                      ) : (
                        t('common.emDash')
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {selectedVersion ? (
        <section className="admin-ai-card">
          <h2>
            {t('admin.promptEngineering.changeDetailsTitle', {
              version: selectedVersion.version_number,
            })}
          </h2>
          <dl className="admin-ai-detail">
            <div>
              <dt>{t('admin.promptEngineering.fields.problem')}</dt>
              <dd>{selectedVersion.problem}</dd>
            </div>
            <div>
              <dt>{t('admin.promptEngineering.fields.change')}</dt>
              <dd>{selectedVersion.change}</dd>
            </div>
            <div>
              <dt>{t('admin.promptEngineering.fields.expectedResult')}</dt>
              <dd>{selectedVersion.expected_result}</dd>
            </div>
            <div>
              <dt>{t('admin.promptEngineering.fields.engineeringNotes')}</dt>
              <dd>{selectedVersion.notes || t('common.emDash')}</dd>
            </div>
            <div>
              <dt>{t('admin.promptEngineering.fields.evaluation')}</dt>
              <dd>
                <span className={evaluationStatusClass(selectedVersion.evaluation_status)}>
                  {selectedVersion.evaluation_status}
                </span>
              </dd>
            </div>
          </dl>
        </section>
      ) : null}

      <section className="admin-ai-card">
        <h2>{t('admin.promptEngineering.evaluationTitle')}</h2>
        <p className="admin-ai-muted">{t('admin.promptEngineering.evaluationHint')}</p>
        <div className="admin-ai-table-wrap">
          <table className="admin-ai-table">
            <thead>
              <tr>
                <th scope="col">{t('admin.promptEngineering.cols.testCase')}</th>
                <th scope="col">{t('admin.promptEngineering.cols.result')}</th>
                <th scope="col">{t('admin.promptEngineering.cols.notes')}</th>
              </tr>
            </thead>
            <tbody>
              {prompt.evaluation_cases.map((item) => (
                <tr key={item.id}>
                  <td>{item.name}</td>
                  <td>
                    <span className={testCaseClass(item.result)}>{item.result}</span>
                  </td>
                  <td>{item.notes || t('common.emDash')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="admin-ai-card">
        <h2>{t('admin.promptEngineering.metricsTitle')}</h2>
        <p className="admin-ai-muted">{t('admin.promptEngineering.metricsHint')}</p>
        <div className="admin-ai-kpis">
          <div className="admin-ai-kpi">
            <span>{t('admin.promptEngineering.metrics.successRate')}</span>
            <strong>{prompt.metrics.success_rate}</strong>
          </div>
          <div className="admin-ai-kpi">
            <span>{t('admin.promptEngineering.metrics.avgResponseTime')}</span>
            <strong>{prompt.metrics.average_response_time}</strong>
          </div>
          <div className="admin-ai-kpi">
            <span>{t('admin.promptEngineering.metrics.lastEvaluation')}</span>
            <strong>{prompt.metrics.last_evaluation}</strong>
          </div>
          <div className="admin-ai-kpi">
            <span>{t('admin.promptEngineering.metrics.telemetrySource')}</span>
            <strong>{prompt.metrics.telemetry_source}</strong>
          </div>
        </div>
      </section>
    </div>
  );
}

export function PromptEngineeringPage() {
  const { t } = useTranslation();
  const prompts = useMemo(() => listPromptCatalog(), []);
  const [selectedId, setSelectedId] = useState<string | null>(prompts[0]?.id ?? null);
  const selectedPrompt = selectedId ? getPromptById(selectedId) : undefined;
  const [selectedVersionNumber, setSelectedVersionNumber] = useState<string>(
    selectedPrompt ? resolveDefaultVersionNumber(selectedPrompt) : '',
  );

  const handleSelectPrompt = (id: string) => {
    setSelectedId(id);
    const next = getPromptById(id);
    setSelectedVersionNumber(next ? resolveDefaultVersionNumber(next) : '');
  };

  return (
    <PortalPage
      title={t('admin.promptEngineering.title')}
      description={t('admin.promptEngineering.description')}
    >
      <aside className="admin-ai-banner" role="note">
        <strong>{t('admin.promptEngineering.governanceBannerTitle')}</strong>
        <p>{t('admin.promptEngineering.governanceBannerBody')}</p>
      </aside>

      <div className="admin-ai-split">
        <PromptCatalogList
          prompts={prompts}
          selectedId={selectedId}
          onSelect={handleSelectPrompt}
        />
        <aside className="admin-ai-detail">
          {selectedPrompt ? (
            <PromptDetailsPanel
              prompt={selectedPrompt}
              selectedVersionNumber={selectedVersionNumber}
              onSelectVersion={setSelectedVersionNumber}
            />
          ) : (
            <p className="admin-ai-muted">{t('admin.promptEngineering.selectPrompt')}</p>
          )}
        </aside>
      </div>
    </PortalPage>
  );
}
