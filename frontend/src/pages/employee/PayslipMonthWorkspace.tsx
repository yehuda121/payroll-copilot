import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { DragDropZone } from '../../components/ui/DragDropZone';
import { useConfirmDialog } from '../../components/ui/Dialog';
import { EmployeeDigitalForm } from '../../features/employee/EmployeeDigitalForm';
import { useEmployeeWorkspace } from '../../features/employee/EmployeeWorkspaceContext';
import { EmployeeValidationResults } from '../../features/employee/EmployeeValidationResults';
import {
  useEmployeeMonthWorkspace,
  type WorkspaceTab,
} from '../../hooks/useEmployeeMonthWorkspace';
import { useWorkspacePageCopy } from '../../hooks/useWorkspacePageCopy';
import { buildEmployeeFieldValidationMap } from '../../lib/employee/field-validation-status';
import type { DocumentLanguage } from '../../types/api';
import { batchService } from '../../services/batch';
import { PayrollChatPanel } from './PayrollChat';
import '../../features/employee/employee-payslip.css';
import '../../features/guest/landing/landing-chat.css';
import './PayslipMonthWorkspace.css';

const TIMELINE = [
  { id: 'upload', labelKey: 'employee.upload.timeline.upload' },
  { id: 'extraction', labelKey: 'employee.upload.timeline.extraction' },
  { id: 'review', labelKey: 'employee.upload.timeline.review' },
  { id: 'validation', labelKey: 'employee.upload.timeline.validation' },
  { id: 'completed', labelKey: 'employee.workspace.timeline.completed' },
] as const;

const TABS: Array<{ id: WorkspaceTab; labelKey: string }> = [
  { id: 'upload', labelKey: 'employee.workspace.tabUpload' },
  { id: 'digital', labelKey: 'employee.upload.tabDigital' },
  { id: 'validation', labelKey: 'employee.workspace.tabValidation' },
  { id: 'original', labelKey: 'employee.upload.tabOriginal' },
  { id: 'chat', labelKey: 'employee.navigation.chat' },
  { id: 'publishing', labelKey: 'accountant.bulk.publish.tab' },
];

export function PayslipMonthWorkspacePage() {
  const { t, i18n } = useTranslation();
  const params = useParams();
  const { basePath } = useEmployeeWorkspace();
  const year = Number(params.year);
  const month = Number(params.month);
  const valid = Number.isFinite(year) && Number.isFinite(month) && month >= 1 && month <= 12;

  const monthTitle = useMemo(() => {
    if (!valid) return '';
    return new Intl.DateTimeFormat(i18n.language, { month: 'long', year: 'numeric' }).format(
      new Date(year, month - 1, 1),
    );
  }, [valid, year, month, i18n.language]);

  if (!valid) {
    return (
      <PortalPage title={t('employee.payslips.pageTitle')} description={t('common.error')}>
        <Link to={`${basePath}/payslips`}>{t('employee.workspace.backToMonths')}</Link>
      </PortalPage>
    );
  }

  return <PayslipMonthWorkspace year={year} month={month} monthTitle={monthTitle} />;
}

function PayslipMonthWorkspace({
  year,
  month,
  monthTitle,
}: {
  year: number;
  month: number;
  monthTitle: string;
}) {
  const { t } = useTranslation();
  const copy = useWorkspacePageCopy();
  const { basePath, batchReview } = useEmployeeWorkspace();
  const flow = useEmployeeMonthWorkspace(year, month);
  const { confirm } = useConfirmDialog();
  const [publishBusy, setPublishBusy] = useState(false);
  const [publishError, setPublishError] = useState<string | null>(null);
  const workspaceTabs = batchReview
    ? TABS.filter((item) => item.id !== 'upload')
    : TABS.filter((item) => item.id !== 'chat' && item.id !== 'publishing');
  const published = flow.detail?.extraction?.lifecycle_status === 'published';
  const canPublish =
    Boolean(batchReview && flow.documentId && flow.isConfirmed && flow.report) &&
    !flow.validationOutdated &&
    !flow.isBusy &&
    !publishBusy &&
    !published;

  const publish = async () => {
    if (!batchReview || !canPublish) return;
    const accepted = await confirm({
      title: t('accountant.bulk.publish.title'),
      message: t('accountant.bulk.publish.message'),
      confirmLabel: t('accountant.bulk.publish.action'),
      cancelLabel: t('common.cancel'),
    });
    if (!accepted) return;
    setPublishBusy(true);
    setPublishError(null);
    try {
      await batchService.publishItem(batchReview.jobId, batchReview.itemId);
      await flow.refresh({ force: true });
    } catch (error) {
      setPublishError(error instanceof Error ? error.message : t('common.error'));
    } finally {
      setPublishBusy(false);
    }
  };

  const validationMap = useMemo(() => {
    if (!flow.report) return undefined;
    const map = buildEmployeeFieldValidationMap(flow.fields, flow.report);
    for (const [key, draft] of Object.entries(flow.fieldDrafts)) {
      if (draft.dirty) delete map[key];
    }
    return map;
  }, [flow.report, flow.fields, flow.fieldDrafts]);

  const stepIndex = TIMELINE.findIndex((item) => item.id === flow.timelineStep);

  useEffect(() => {
    if (batchReview && flow.tab === 'upload') {
      flow.setTab('digital');
    }
  }, [batchReview, flow.setTab, flow.tab]);

  return (
    <PortalPage title={monthTitle} description={copy.monthDescription}>
      <div className="employee-month-workspace">
        <div className="employee-month-workspace__top">
          {!batchReview && (
            <Link to={`${basePath}/payslips`} className="btn btn--ghost">
              {t('employee.workspace.backToMonths')}
            </Link>
          )}
          {batchReview && (
            <div className="employee-payslip-wizard__actions">
              <span
                className={`status-badge status-badge--${published ? 'passed' : 'warnings'}`}
              >
                {published
                  ? t('accountant.bulk.publish.published')
                  : t('accountant.bulk.publish.pendingReview')}
              </span>
              <button
                type="button"
                className="btn btn--primary"
                disabled={!canPublish}
                onClick={() => void publish()}
              >
                {publishBusy
                  ? t('common.saving')
                  : t('accountant.bulk.publish.action')}
              </button>
            </div>
          )}
        </div>

        {publishError && (
          <p className="chat-panel__error" role="alert">
            {publishError}
          </p>
        )}
        {batchReview && !published && (!flow.isConfirmed || flow.validationOutdated) && (
          <p className="employee-workspace-hint">
            {t('accountant.bulk.publish.requireCurrentValidation')}
          </p>
        )}

        <ol
          className="employee-timeline employee-timeline--compact"
          aria-label={t('validate.progressLabel')}
        >
          {TIMELINE.map((item, index) => {
            const state =
              index < stepIndex ? 'done' : index === stepIndex ? 'current' : 'upcoming';
            return (
              <li
                key={item.id}
                className={`employee-timeline__step is-${state}`}
                aria-current={state === 'current' ? 'step' : undefined}
              >
                <span className="employee-timeline__marker" aria-hidden="true">
                  {state === 'done' ? '✔' : index + 1}
                </span>
                <span className="employee-timeline__label">{t(item.labelKey)}</span>
              </li>
            );
          })}
        </ol>

        <div className="sr-only" aria-live="polite">
          {flow.statusMessage || flow.error || ''}
        </div>
        {flow.error && (
          <p className="chat-panel__error" role="alert">
            {flow.error}
          </p>
        )}

        {flow.loading ? (
          <p role="status">{t('common.loading')}</p>
        ) : (
          <>
            <div
              className="employee-review-tabs"
              role="tablist"
              aria-label={t('employee.workspace.tabs')}
            >
              {workspaceTabs.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={flow.tab === item.id}
                  className={`employee-review-tabs__tab ${flow.tab === item.id ? 'is-active' : ''}`}
                  onClick={() => flow.setTab(item.id)}
                  disabled={flow.busyPhase === 'confirming'}
                >
                  {t(item.labelKey)}
                </button>
              ))}
            </div>

            {flow.tab === 'upload' && !batchReview && <UploadTab flow={flow} />}

            {flow.tab === 'digital' && (
              <section aria-label={t('employee.upload.tabDigital')}>
                {flow.busyPhase === 'extracting' ? (
                  <div className="employee-extract-loading" aria-busy="true" aria-live="polite">
                    <div className="chat-typing" aria-hidden="true">
                      <span className="chat-typing__dots">
                        <span />
                        <span />
                        <span />
                      </span>
                    </div>
                    <h3>{t('employee.workspace.extractingTitle')}</h3>
                    <p>{t('employee.workspace.extractingStatus')}</p>
                    <div
                      className="employee-progress"
                      role="progressbar"
                      aria-label={t('employee.workspace.extractingTitle')}
                    >
                      <div className="employee-progress__bar" />
                    </div>
                    <button
                      type="button"
                      className="btn btn--secondary"
                      onClick={flow.cancelExtraction}
                    >
                      {t('employee.upload.cancelExtraction')}
                    </button>
                  </div>
                ) : flow.hasExtraction ? (
                  <>
                    <EmployeeDigitalForm
                      fields={flow.fields}
                      drafts={flow.fieldDrafts}
                      editable
                      busy={
                        flow.busyPhase === 'confirming' || flow.busyPhase === 'validating'
                      }
                      validationMap={validationMap}
                      onChangeField={flow.updateFieldDraft}
                      onClearField={flow.clearFieldDraft}
                      onRemoveField={flow.removeField}
                      onAddField={flow.addField}
                    />
                    <div className="employee-payslip-wizard__actions employee-digital-validate">
                      <button
                        type="button"
                        className="btn btn--primary btn--large"
                        disabled={
                          flow.isBusy ||
                          flow.blocksConfirmation ||
                          !flow.documentId
                        }
                        onClick={() => {
                          void flow.confirmAndValidate();
                        }}
                      >
                        {flow.busyPhase === 'confirming' || flow.busyPhase === 'validating'
                          ? t('employee.upload.validatingPayroll')
                          : t('employee.validation.runValidationPrimary')}
                      </button>
                    </div>
                  </>
                ) : (
                  <p>{t('employee.workspace.digitalEmpty')}</p>
                )}
              </section>
            )}

            {flow.tab === 'validation' && (
              <ValidationTab flow={flow} year={year} month={month} />
            )}

            {flow.tab === 'original' && <OriginalTab flow={flow} />}

            {flow.tab === 'chat' && batchReview && (
              <section aria-label={t('employee.navigation.chat')}>
                <PayrollChatPanel />
              </section>
            )}

            {flow.tab === 'publishing' && batchReview && (
              <PublishingTab
                flow={flow}
                published={published}
                canPublish={canPublish}
                publishBusy={publishBusy}
                publishError={publishError}
                onPublish={publish}
              />
            )}
          </>
        )}
      </div>
    </PortalPage>
  );
}

type Flow = ReturnType<typeof useEmployeeMonthWorkspace>;

function UploadTab({ flow }: { flow: Flow }) {
  const { t } = useTranslation();
  const { confirm } = useConfirmDialog();
  const fileReady = Boolean(flow.pendingFile) && !flow.fileError;
  const hasStoredOriginal = Boolean(flow.documentId || flow.hasPayslip);

  const extractEnabled =
    !flow.isBusy &&
    ((fileReady && !flow.hasExtraction) ||
      (Boolean(flow.documentId) && !flow.hasExtraction && !flow.pendingFile) ||
      (fileReady && flow.hasExtraction));

  const onExtract = async () => {
    if (flow.hasExtraction && flow.pendingFile) {
      const ok = await confirm({
        title: t('employee.workspace.replaceConfirmTitle'),
        message: t('employee.workspace.replaceConfirmMessage'),
        confirmLabel: t('employee.workspace.replaceDocument'),
        cancelLabel: t('common.cancel'),
        variant: 'danger',
      });
      if (!ok) return;
      await flow.replaceDocument();
      return;
    }
    await flow.runExtract();
  };

  return (
    <section className="employee-month-empty" aria-label={t('employee.workspace.tabUpload')}>
      {!hasStoredOriginal && !flow.pendingFile ? (
        <>
          <h3>{t('employee.workspace.noPayslipUploaded')}</h3>
          <p>{t('employee.workspace.emptyHint')}</p>
        </>
      ) : hasStoredOriginal && !flow.pendingFile ? (
        <>
          <h3>{t('employee.workspace.originalReadOnly')}</h3>
          <p>{t('employee.workspace.originalReadOnlyHint')}</p>
          <p>
            {t('validate.uploadedDocument')}: {flow.detail?.payslip.original_filename}
          </p>
        </>
      ) : (
        <>
          <h3>
            {flow.hasExtraction
              ? t('employee.workspace.replaceHintTitle')
              : t('employee.workspace.extractTitle')}
          </h3>
          <p>
            {flow.hasExtraction
              ? t('employee.workspace.replaceHint')
              : t('employee.workspace.extractHint')}
          </p>
          {flow.pendingFile && (
            <p>
              {t('validate.uploadedDocument')}: {flow.pendingFile.name}
            </p>
          )}
        </>
      )}

      <div className="document-language">
        <label htmlFor="month-document-language">
          <span>{t('validate.documentLanguage')}</span>
          <select
            id="month-document-language"
            value={flow.documentLanguage}
            disabled={flow.isBusy}
            onChange={(event) =>
              flow.setDocumentLanguage(event.target.value as DocumentLanguage)
            }
          >
            <option value="he">{t('validate.langHe')}</option>
            <option value="en">{t('validate.langEn')}</option>
            <option value="ar">{t('validate.langAr')}</option>
            <option value="auto">{t('validate.langAuto')}</option>
          </select>
        </label>
      </div>

      <div className="employee-month-workspace__upload-shell">
        <DragDropZone
          accept=".pdf,.png,.jpg,.jpeg"
          selectedFileName={flow.pendingFile?.name}
          errorMessage={flow.fileError ?? undefined}
          onFileSelected={(file) => {
            void flow.selectFile(file);
          }}
          onRemove={flow.pendingFile ? flow.deleteSelectedFile : undefined}
        />
      </div>

      <div className="employee-payslip-wizard__actions">
        <button
          type="button"
          className="btn btn--primary btn--large"
          disabled={!extractEnabled}
          onClick={() => {
            void onExtract();
          }}
        >
          {flow.hasExtraction && flow.pendingFile
            ? t('employee.workspace.replaceDocument')
            : t('employee.workspace.extractDocument')}
        </button>
        {flow.pendingFile && (
          <button
            type="button"
            className="btn btn--danger"
            disabled={flow.isBusy}
            onClick={flow.deleteSelectedFile}
          >
            {t('employee.workspace.deleteSelectedOnly')}
          </button>
        )}
      </div>
    </section>
  );
}

function ValidationTab({
  flow,
  year,
  month,
}: {
  flow: Flow;
  year: number;
  month: number;
}) {
  const { t, i18n } = useTranslation();
  const history = flow.detail?.validation_history ?? [];

  return (
    <section aria-label={t('employee.workspace.tabValidation')}>
      {flow.periodPrompt && (
        <div className="identity-period-check__banner is-warning" role="alertdialog">
          <p>
            {t('employee.workspace.periodMismatchPrompt', {
              month: flow.periodPrompt.extracted_month,
              year: flow.periodPrompt.extracted_year,
            })}
          </p>
          <div className="employee-payslip-wizard__actions">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => {
                void flow.resolvePeriod('move');
              }}
            >
              {t('employee.workspace.movePeriod', {
                month: flow.periodPrompt.extracted_month,
                year: flow.periodPrompt.extracted_year,
              })}
            </button>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => {
                void flow.resolvePeriod('keep');
              }}
            >
              {t('employee.workspace.keepPeriod', { month, year })}
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => {
                void flow.resolvePeriod('cancel');
              }}
            >
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}

      {flow.hasExtraction && flow.blocksConfirmation && (
        <p className="employee-payslip-wizard__blocked" role="status">
          {t('employee.upload.confirmBlocked')}
        </p>
      )}

      {flow.busyPhase === 'validating' ? (
        <div className="validation-wizard__prepare-card" aria-busy="true">
          <h3>{t('employee.upload.validatingPayroll')}</h3>
          <div className="employee-progress" role="progressbar">
            <div className="employee-progress__bar" />
          </div>
          <button type="button" className="btn btn--secondary" onClick={flow.cancelValidation}>
            {t('employee.upload.cancelValidation')}
          </button>
        </div>
      ) : (
        <EmployeeValidationResults
          report={flow.report}
          identity={flow.identityCheck}
          period={flow.periodCheck}
          fileName={flow.detail?.payslip.original_filename}
          validationOutdated={flow.validationOutdated}
          canRunValidation={flow.isConfirmed && !flow.isBusy && !flow.blocksConfirmation}
          validating={false}
          onRunValidation={() => {
            void flow.runValidation();
          }}
        />
      )}

      {history.length > 0 && (
        <section
          className="employee-validation-history"
          aria-label={t('accountant.bulk.validationHistory.title')}
        >
          <h3>{t('accountant.bulk.validationHistory.title')}</h3>
          {history.map((run, index) => (
            <article
              key={run.validation_run_id}
              className="employee-validation-history__run"
            >
              <header>
                <strong>
                  {t('accountant.bulk.validationHistory.run', {
                    value: history.length - index,
                  })}
                </strong>
                <span className={`status-badge status-badge--${run.overall_result === 'pass' ? 'passed' : run.overall_result === 'critical' ? 'critical' : 'warnings'}`}>
                  {run.overall_result || run.status}
                </span>
                {run.outdated && (
                  <span>{t('accountant.bulk.validationHistory.outdated')}</span>
                )}
                <time>
                  {run.completed_at
                    ? new Intl.DateTimeFormat(i18n.language, {
                        dateStyle: 'medium',
                        timeStyle: 'short',
                      }).format(new Date(run.completed_at))
                    : t('common.emDash')}
                </time>
              </header>
              {run.evidence_summary && (
                <p className="employee-workspace-hint">
                  {run.evidence_summary.evidence_supported_field_count > 0
                    ? t('explainability.validationTraceSummary', {
                        supported: run.evidence_summary.evidence_supported_field_count,
                        total: run.evidence_summary.extracted_field_count,
                      })
                    : t('explainability.validationTraceUnavailable')}
                </p>
              )}
              {(run.findings ?? []).length > 0 ? (
                <div className="employee-validation-history__findings">
                  {(run.findings ?? []).map((finding) => (
                    <article key={finding.id} className="employee-validation-history__finding">
                      <header>
                        <strong>
                        {String(
                          t(finding.message_key, {
                            ...finding.message_params,
                            defaultValue: finding.code,
                          }),
                        )}
                        </strong>
                        <span
                          className={`status-badge status-badge--${finding.severity === 'critical' ? 'critical' : finding.severity === 'warning' ? 'warnings' : 'passed'}`}
                        >
                          {finding.severity}
                        </span>
                      </header>
                      {Boolean(finding.message_params?.explanation) && (
                        <p>{String(finding.message_params.explanation)}</p>
                      )}
                      <dl>
                        <div>
                          <dt>{t('employee.validation.actual')}</dt>
                          <dd>{finding.actual_value ?? String(t('common.emDash'))}</dd>
                        </div>
                        <div>
                          <dt>{t('employee.validation.expected')}</dt>
                          <dd>{finding.expected_value ?? String(t('common.emDash'))}</dd>
                        </div>
                        <div>
                          <dt>{t('validate.confidenceLabel')}</dt>
                          <dd>
                            {finding.confidence != null
                              ? `${Math.round(finding.confidence * 100)}%`
                              : t('common.emDash')}
                          </dd>
                        </div>
                      </dl>
                      {finding.evidence_explanation && (
                        <details className="validation-evidence">
                          <summary>{t('explainability.whyThisResult')}</summary>
                          {finding.evidence_explanation.available ? (
                            <dl>
                              <div>
                                <dt>{t('explainability.sourcePage')}</dt>
                                <dd>
                                  {finding.evidence_explanation.page ?? t('common.emDash')}
                                </dd>
                              </div>
                              <div>
                                <dt>{t('explainability.detectedLabel')}</dt>
                                <dd>
                                  {finding.evidence_explanation.label ?? t('common.emDash')}
                                </dd>
                              </div>
                              <div>
                                <dt>{t('explainability.detectedValue')}</dt>
                                <dd>
                                  {finding.evidence_explanation.value == null
                                    ? t('common.emDash')
                                    : String(finding.evidence_explanation.value)}
                                </dd>
                              </div>
                              <div>
                                <dt>{t('explainability.strategy')}</dt>
                                <dd>
                                  {finding.evidence_explanation.association_strategy ??
                                    t('common.emDash')}
                                </dd>
                              </div>
                            </dl>
                          ) : (
                            <p>{t('explainability.validationTraceUnavailable')}</p>
                          )}
                        </details>
                      )}
                    </article>
                  ))}
                </div>
              ) : (
                <p>{t('accountant.bulk.validationHistory.noFindings')}</p>
              )}
            </article>
          ))}
        </section>
      )}
    </section>
  );
}

function OriginalTab({ flow }: { flow: Flow }) {
  const { t, i18n } = useTranslation();
  const { confirm } = useConfirmDialog();
  const { batchReview } = useEmployeeWorkspace();
  const payslip = flow.detail?.payslip;
  const fileName = payslip?.original_filename;

  if (!flow.hasPayslip && !flow.documentId) {
    return <p>{t('employee.upload.originalUnavailable')}</p>;
  }

  const uploadedAt = payslip?.uploaded_at
    ? new Intl.DateTimeFormat(i18n.language, {
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(new Date(payslip.uploaded_at))
    : t('common.emDash');

  return (
    <section
      className="employee-original-compare"
      aria-label={t('employee.upload.tabOriginal')}
    >
      <div className="employee-original-compare__document">
        <h3>{t('employee.upload.tabOriginal')}</h3>
        {flow.previewUrl ? (
          <iframe
            className="employee-original-compare__frame"
            src={flow.previewUrl}
            title={fileName || t('employee.upload.tabOriginal')}
          />
        ) : (
          <p>{t('employee.upload.originalUnavailable')}</p>
        )}
      </div>
      <div className="employee-original-compare__digital">
        <EmployeeDigitalForm
          fields={flow.fields}
          drafts={flow.fieldDrafts}
          editable
          busy={flow.isBusy}
          onChangeField={flow.updateFieldDraft}
          onClearField={flow.clearFieldDraft}
          onRemoveField={flow.removeField}
          onAddField={flow.addField}
        />
      </div>
      <dl className="employee-original-meta__list employee-original-compare__meta">
        <div>
          <dt>{t('employee.workspace.originalFilename')}</dt>
          <dd>{fileName || t('common.emDash')}</dd>
        </div>
        <div>
          <dt>{t('employee.workspace.originalUploadedAt')}</dt>
          <dd>{uploadedAt}</dd>
        </div>
        <div>
          <dt>{t('employee.workspace.originalDocumentType')}</dt>
          <dd>{t('employee.documents.types.payslip')}</dd>
        </div>
        <div>
          <dt>{t('employee.workspace.originalStatus')}</dt>
          <dd>{payslip?.status ? t(`employee.lifecycle.${payslip.status}`, { defaultValue: payslip.status }) : t('common.emDash')}</dd>
        </div>
      </dl>
      {flow.documentId && !batchReview && (
        <div className="employee-payslip-wizard__actions">
          <button
            type="button"
            className="btn btn--danger"
            disabled={flow.isBusy}
            onClick={() => {
              void (async () => {
                const ok = await confirm({
                  title: t('employee.workspace.deleteOriginalTitle'),
                  message: t('employee.workspace.deleteOriginalMessage'),
                  confirmLabel: t('employee.workspace.deleteOriginal'),
                  cancelLabel: t('common.cancel'),
                  variant: 'danger',
                });
                if (!ok) return;
                await flow.deleteOwnedDocument();
              })();
            }}
          >
            {t('employee.workspace.deleteOriginal')}
          </button>
        </div>
      )}
    </section>
  );
}

function PublishingTab({
  flow,
  published,
  canPublish,
  publishBusy,
  publishError,
  onPublish,
}: {
  flow: Flow;
  published: boolean;
  canPublish: boolean;
  publishBusy: boolean;
  publishError: string | null;
  onPublish: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const checks = [
    {
      complete: flow.hasExtraction,
      label: t('accountant.bulk.publish.checks.extraction'),
    },
    {
      complete: flow.isConfirmed && !flow.dirty,
      label: t('accountant.bulk.publish.checks.corrections'),
    },
    {
      complete: Boolean(flow.report) && !flow.validationOutdated,
      label: t('accountant.bulk.publish.checks.validation'),
    },
  ];

  return (
    <section className="employee-publishing" aria-label={t('accountant.bulk.publish.tab')}>
      <header>
        <h3>{t('accountant.bulk.publish.title')}</h3>
        <span className={`status-badge status-badge--${published ? 'passed' : 'warnings'}`}>
          {published
            ? t('accountant.bulk.publish.published')
            : t('accountant.bulk.publish.pendingReview')}
        </span>
      </header>
      <p>{t('accountant.bulk.publish.message')}</p>
      <ol>
        {checks.map((check) => (
          <li key={check.label} className={check.complete ? 'is-complete' : 'is-blocked'}>
            <span aria-hidden="true">{check.complete ? '✓' : '!'}</span>
            <span>{check.label}</span>
          </li>
        ))}
      </ol>
      {!published && !canPublish && (
        <p className="employee-workspace-hint">
          {t('accountant.bulk.publish.requireCurrentValidation')}
        </p>
      )}
      {publishError && <p className="chat-panel__error">{publishError}</p>}
      <button
        type="button"
        className="btn btn--primary btn--large"
        disabled={!canPublish}
        onClick={() => void onPublish()}
      >
        {publishBusy ? t('common.saving') : t('accountant.bulk.publish.action')}
      </button>
    </section>
  );
}
