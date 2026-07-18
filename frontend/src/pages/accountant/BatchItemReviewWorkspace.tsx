import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../../auth/AuthContext';
import { PortalPage } from '../../components/PortalPage';
import { GuestChatPanel } from '../../components/guest/GuestChatPanel';
import { useConfirmDialog } from '../../components/ui/Dialog';
import { EmployeeDigitalForm } from '../../features/employee/EmployeeDigitalForm';
import type { FieldDraft } from '../../hooks/useEmployeePayslipFlow';
import { employeeAssistantService } from '../../services/assistant';
import {
  batchService,
  type BatchItemReview,
  type BatchValidationHistoryRun,
} from '../../services/batch';
import { employeesService } from '../../services/employees';
import type { EmployeeRecord } from '../../types/employee';
import { buildEmployeeFieldValidationMap } from '../../lib/employee/field-validation-status';
import type { GuestValidationReport } from '../../types/validation-report';
import './UnknownEmployeeResolution.css';
import '../employee/PayslipMonthWorkspace.css';

type ReviewTab = 'digital' | 'validation' | 'original' | 'chat' | 'publishing';
type ResolutionMode = 'search' | 'create';

type CreateValues = {
  employeeNumber: string;
  firstName: string;
  lastName: string;
  nationalId: string;
  email: string;
  company: string;
  department: string;
};

const fieldText = (review: BatchItemReview | null, ...keys: string[]): string => {
  const field = review?.fields.find((row) => keys.includes(row.key));
  return field?.value == null ? '' : String(field.value);
};

function reportFromBatchHistory(
  latest: BatchValidationHistoryRun | null,
  documentId: string,
): GuestValidationReport | null {
  if (!latest) return null;
  const severity = (value: string): 'info' | 'warning' | 'critical' => {
    const normalized = value.toLowerCase();
    if (normalized === 'critical' || normalized === 'error' || normalized === 'failed') {
      return 'critical';
    }
    if (normalized === 'warning' || normalized === 'uncertain') return 'warning';
    return 'info';
  };
  return {
    runId: latest.validation_run_id,
    documentId,
    overallResult: (latest.overall_result as GuestValidationReport['overallResult']) ?? null,
    overallStatus: String(latest.overall_result || latest.status || ''),
    summary: '',
    validationConfidence: latest.confidence,
    confidenceExplanation: null,
    scope: [],
    uploadedDocuments: [],
    checksPassedCount: 0,
    findings: latest.findings.map((finding) => ({
      id: finding.id,
      code: finding.rule_id,
      rule_id: finding.rule_id,
      severity: severity(finding.severity),
      message_key: finding.message_key,
      message: '',
      explanation:
        typeof finding.message_params?.explanation === 'string' &&
        !/^[a-z][a-z0-9_.-]*$/i.test(String(finding.message_params.explanation))
          ? String(finding.message_params.explanation)
          : '',
      expected_value: finding.expected_value,
      actual_value: finding.actual_value,
      confidence: finding.confidence ?? 0,
      legal_reference: null,
    })),
    extractionConnected: true,
  };
}

export function BatchItemReviewWorkspacePage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { confirm } = useConfirmDialog();
  const { session } = useAuth();
  const { jobId = '', itemId = '' } = useParams<{ jobId: string; itemId: string }>();
  const [review, setReview] = useState<BatchItemReview | null>(null);
  const [drafts, setDrafts] = useState<Record<string, FieldDraft>>({});
  const [tab, setTab] = useState<ReviewTab>('digital');
  const [resolutionMode, setResolutionMode] = useState<ResolutionMode>('search');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<EmployeeRecord[]>([]);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createValues, setCreateValues] = useState<CreateValues>({
    employeeNumber: '',
    firstName: '',
    lastName: '',
    nationalId: '',
    email: '',
    company: session?.user.organizationId || '',
    department: '',
  });

  const applyReview = useCallback((next: BatchItemReview) => {
    const extractedName = fieldText(next, 'employee_name', 'full_name').trim();
    const [nameFirst = '', ...nameRest] = extractedName.split(/\s+/);
    setReview(next);
    setDrafts(
      Object.fromEntries(
        next.fields.map((field) => [
          field.key,
          {
            value: field.value == null ? '' : String(field.value),
            clear: false,
            dirty: false,
          },
        ]),
      ),
    );
    setCreateValues((previous) => ({
      ...previous,
      employeeNumber: previous.employeeNumber || fieldText(next, 'employee_number'),
      firstName:
        previous.firstName ||
        fieldText(next, 'first_name', 'employee_first_name') ||
        nameFirst,
      lastName:
        previous.lastName ||
        fieldText(next, 'last_name', 'employee_last_name') ||
        nameRest.join(' '),
      nationalId: previous.nationalId || fieldText(next, 'national_id', 'employee_id'),
      email: previous.email || fieldText(next, 'email', 'employee_email'),
      department: previous.department || fieldText(next, 'department', 'department_name'),
    }));
  }, []);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      applyReview(await batchService.getItemReview(jobId, itemId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('common.error'));
    }
  }, [applyReview, itemId, jobId, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const controller = new AbortController();
    void batchService
      .getItemContent(jobId, itemId, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        setPreviewUrl(URL.createObjectURL(blob));
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : t('common.error'));
        }
      });
    return () => {
      controller.abort();
      setPreviewUrl((value) => {
        if (value) URL.revokeObjectURL(value);
        return null;
      });
    };
  }, [itemId, jobId, t]);

  const latest = review?.validation_history[0] ?? null;
  const needsResolution =
    review?.item.status === 'unknown_employee' || !review?.item.employee_number;
  const dirty = Object.values(drafts).some((draft) => draft.dirty);
  const validationMap = useMemo(() => {
    if (dirty || !review) return {};
    return buildEmployeeFieldValidationMap(
      review.fields,
      reportFromBatchHistory(latest, review.document_id),
    );
  }, [dirty, latest, review]);

  const saveAndValidate = async () => {
    if (!review) return;
    setBusy(true);
    setError(null);
    try {
      let next = review;
      const corrections = Object.entries(drafts)
        .filter(([, draft]) => draft.dirty)
        .map(([key, draft]) => ({
          key,
          value: draft.clear ? null : draft.value,
          clear: draft.clear,
        }));
      if (corrections.length) {
        next = await batchService.correctItemReview(jobId, itemId, corrections);
      }
      next = await batchService.validateItemReview(jobId, itemId);
      applyReview(next);
      setTab('validation');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('common.error'));
    } finally {
      setBusy(false);
    }
  };

  const attach = async (employee: EmployeeRecord) => {
    setBusy(true);
    setError(null);
    try {
      const item = await batchService.resolveItem(jobId, itemId, {
        action: 'attach_employee',
        employee_number: employee.employeeNumber,
      });
      if (!item.payroll_year || !item.payroll_month || !item.document_id) {
        throw new Error(t('common.error'));
      }
      navigate(
        `/accountant/employees/${encodeURIComponent(employee.employeeNumber)}/workspace/payslips/${item.payroll_year}/${item.payroll_month}?batchJobId=${encodeURIComponent(jobId)}&batchItemId=${encodeURIComponent(itemId)}&batchDocumentId=${encodeURIComponent(item.document_id)}`,
        { state: { backTo: '/accountant/bulk-upload' } },
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('common.error'));
    } finally {
      setBusy(false);
    }
  };

  const search = async () => {
    setBusy(true);
    setError(null);
    try {
      setResults(
        await employeesService.list({
          q: query.trim() || undefined,
          includeDisabled: false,
        }),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('common.error'));
    } finally {
      setBusy(false);
    }
  };

  const createAndAttach = async () => {
    if (
      !createValues.employeeNumber.trim() ||
      !createValues.firstName.trim() ||
      !createValues.lastName.trim() ||
      !createValues.nationalId.trim()
    ) {
      setError(t('accountant.unknown.required'));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await employeesService.create({
        employee_number: createValues.employeeNumber.trim(),
        first_name: createValues.firstName.trim(),
        last_name: createValues.lastName.trim(),
        national_id: createValues.nationalId.trim(),
        email: createValues.email.trim() || undefined,
        employment_type: 'full_time',
        salary_type: 'monthly',
        profile_incomplete: true,
        metadata: {
          company: createValues.company.trim(),
          department: createValues.department.trim(),
          source: 'batch_unknown_employee_resolution',
        },
      });
      await attach(created);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('common.error'));
      setBusy(false);
    }
  };

  const ignore = async () => {
    const accepted = await confirm({
      title: t('accountant.bulk.review.ignoreTitle'),
      message: t('accountant.bulk.review.ignoreWarning'),
      confirmLabel: t('accountant.bulk.review.ignoreConfirm'),
      cancelLabel: t('common.cancel'),
      variant: 'danger',
    });
    if (!accepted) return;
    setBusy(true);
    try {
      await batchService.resolveItem(jobId, itemId, { action: 'ignore' });
      navigate('/accountant/bulk-upload');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('common.error'));
      setBusy(false);
    }
  };

  const tabs: Array<[ReviewTab, string]> = [
    ['digital', 'employee.upload.tabDigital'],
    ['validation', 'employee.workspace.tabValidation'],
    ['original', 'employee.upload.tabOriginal'],
    ['chat', 'employee.navigation.chat'],
    ['publishing', 'accountant.bulk.publish.tab'],
  ];
  const monthTitle =
    review?.item.payroll_year && review.item.payroll_month
      ? new Intl.DateTimeFormat(i18n.language, { month: 'long', year: 'numeric' }).format(
          new Date(review.item.payroll_year, review.item.payroll_month - 1, 1),
        )
      : t('common.emDash');

  return (
    <PortalPage
      title={fieldText(review, 'employee_name', 'full_name') || t('accountant.unknown.title')}
      description={monthTitle}
    >
      <div className="employee-month-workspace">
        <div className="employee-month-workspace__top">
          <button className="btn btn--ghost" onClick={() => navigate('/accountant/bulk-upload')}>
            ← {t('accountant.bulk.review.backToBatch')}
          </button>
          <span className="status-badge status-badge--batch-unknown_employee">
            {t('accountant.bulk.status.unknown_employee')}
          </span>
        </div>

        {needsResolution && (
        <section className="unknown-resolution__summary unknown-resolution__resolution-panel">
          <div>
            <strong>{t('accountant.bulk.review.resolutionRequired')}</strong>
            <p>{t('accountant.bulk.review.resolutionDescription')}</p>
          </div>
          <div className="unknown-resolution__actions">
            <button
              className={`btn ${resolutionMode === 'search' ? 'btn--primary' : 'btn--secondary'}`}
              onClick={() => setResolutionMode('search')}
            >
              {t('accountant.unknown.search')}
            </button>
            <button
              className={`btn ${resolutionMode === 'create' ? 'btn--primary' : 'btn--secondary'}`}
              onClick={() => setResolutionMode('create')}
            >
              {t('accountant.unknown.create')}
            </button>
            <button className="btn btn--danger" disabled={busy} onClick={() => void ignore()}>
              {t('accountant.unknown.ignore')}
            </button>
          </div>
          {resolutionMode === 'search' ? (
            <div className="unknown-resolution__panel">
              <label>
                <span>{t('accountant.unknown.searchLabel')}</span>
                <input
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder={t('accountant.unknown.searchPlaceholder')}
                />
              </label>
              <button className="btn btn--primary" disabled={busy} onClick={() => void search()}>
                {t('common.search')}
              </button>
              <div className="unknown-resolution__results">
                {results.map((employee) => (
                  <button
                    key={employee.employeeNumber}
                    className="unknown-resolution__employee"
                    disabled={busy}
                    onClick={() => void attach(employee)}
                  >
                    <strong>{employee.fullName}</strong>
                    <span>#{employee.employeeNumber}</span>
                    <span>{employee.nationalIdMasked || t('common.emDash')}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="unknown-resolution__panel unknown-resolution__form">
              {(
                [
                  ['employeeNumber', 'accountant.unknown.employeeNumber'],
                  ['firstName', 'accountant.unknown.firstName'],
                  ['lastName', 'accountant.unknown.lastName'],
                  ['nationalId', 'accountant.unknown.nationalId'],
                  ['email', 'accountant.unknown.email'],
                  ['company', 'accountant.unknown.company'],
                  ['department', 'accountant.unknown.department'],
                ] as Array<[keyof CreateValues, string]>
              ).map(([key, label]) => (
                <label key={key}>
                  <span>{t(label)}</span>
                  <input
                    type={key === 'email' ? 'email' : 'text'}
                    value={createValues[key]}
                    readOnly={key === 'company'}
                    onChange={(event) =>
                      setCreateValues((previous) => ({
                        ...previous,
                        [key]: event.target.value,
                      }))
                    }
                  />
                </label>
              ))}
              <button
                className="btn btn--primary"
                disabled={busy}
                onClick={() => void createAndAttach()}
              >
                {t('accountant.unknown.createAndAttach')}
              </button>
            </div>
          )}
        </section>
        )}

        {error && <p className="chat-panel__error">{error}</p>}

        <div className="employee-review-tabs" role="tablist">
          {tabs.map(([id, key]) => (
            <button
              key={id}
              role="tab"
              aria-selected={tab === id}
              className={`employee-review-tabs__tab ${tab === id ? 'is-active' : ''}`}
              onClick={() => setTab(id)}
            >
              {t(key)}
            </button>
          ))}
        </div>

        {tab === 'digital' && (
          <>
            <EmployeeDigitalForm
              fields={review?.fields}
              drafts={drafts}
              editable
              busy={busy}
              validationMap={validationMap}
              onChangeField={(key, value) =>
                setDrafts((previous) => ({
                  ...previous,
                  [key]: { value, clear: !value.trim(), dirty: true },
                }))
              }
              onClearField={(key) =>
                setDrafts((previous) => ({
                  ...previous,
                  [key]: { value: '', clear: true, dirty: true },
                }))
              }
            />
            <button
              className="btn btn--primary btn--large"
              disabled={busy || !review}
              onClick={() => void saveAndValidate()}
            >
              {busy
                ? t('employee.upload.validatingPayroll')
                : latest || dirty
                  ? t('employee.workspace.runValidationAgain')
                  : t('employee.upload.runValidation')}
            </button>
          </>
        )}

        {tab === 'validation' && (
          <ValidationHistory runs={review?.validation_history ?? []} />
        )}

        {tab === 'original' && (
          <div className="employee-original-compare">
            <div className="employee-original-compare__document">
              <h3>{t('employee.upload.tabOriginal')}</h3>
              {previewUrl && (
                <iframe
                  className="employee-original-compare__frame"
                  src={previewUrl}
                  title={review?.original_filename || t('employee.upload.tabOriginal')}
                />
              )}
            </div>
            <div className="employee-original-compare__digital">
              <EmployeeDigitalForm
                fields={review?.fields}
                drafts={drafts}
                editable
                busy={busy}
                validationMap={validationMap}
                onChangeField={(key, value) =>
                  setDrafts((previous) => ({
                    ...previous,
                    [key]: { value, clear: !value.trim(), dirty: true },
                  }))
                }
                onClearField={(key) =>
                  setDrafts((previous) => ({
                    ...previous,
                    [key]: { value: '', clear: true, dirty: true },
                  }))
                }
              />
            </div>
          </div>
        )}

        {tab === 'chat' && review && (
          <GuestChatPanel
            chatHandler={(payload) =>
              employeeAssistantService.chatForBatchItem({
                message: payload.message,
                session_id: payload.session_id,
                locale: payload.locale,
                batch_job_id: jobId,
                batch_item_id: itemId,
              })
            }
          />
        )}

        {tab === 'publishing' && (
          <section className="employee-publishing">
            <h3>{t('accountant.bulk.publish.title')}</h3>
            <p>
              {needsResolution
                ? t('accountant.bulk.review.resolveBeforePublish')
                : t('accountant.bulk.publish.requireCurrentValidation')}
            </p>
            <button className="btn btn--primary btn--large" disabled>
              {t('accountant.bulk.publish.action')}
            </button>
          </section>
        )}
      </div>
    </PortalPage>
  );
}

function ValidationHistory({ runs }: { runs: BatchValidationHistoryRun[] }) {
  const { t, i18n } = useTranslation();
  if (!runs.length) return <p>{t('employee.workspace.noValidationYet')}</p>;
  return (
    <section className="employee-validation-history">
      {runs.map((run, index) => (
        <article key={run.validation_run_id} className="employee-validation-history__run">
          <header>
            <strong>
              {t('accountant.bulk.validationHistory.run', { value: runs.length - index })}
            </strong>
            <span className={`status-badge status-badge--${run.overall_result === 'pass' ? 'passed' : 'warnings'}`}>
              {run.overall_result || run.status}
            </span>
            {run.outdated && <span>{t('accountant.bulk.validationHistory.outdated')}</span>}
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
          <div className="employee-validation-history__findings">
            {Object.entries(
              run.findings.reduce<Record<string, typeof run.findings>>((groups, finding) => {
                const category = finding.category || 'employment';
                (groups[category] ||= []).push(finding);
                return groups;
              }, {}),
            ).map(([category, findings]) => (
              <section key={category} className="employee-validation-group">
                <h4>
                  {t(`employee.validation.groups.${category.toLowerCase()}`, {
                    defaultValue: category,
                  })}
                </h4>
                {findings.map((finding) => (
                  <article key={finding.id} className="employee-validation-history__finding">
                    <header>
                      <strong>
                        {String(
                          t(finding.message_key, {
                            ...finding.message_params,
                            defaultValue: finding.rule_id,
                          }),
                        )}
                      </strong>
                      <span className={`status-badge status-badge--${finding.severity === 'critical' ? 'critical' : 'warnings'}`}>
                        {finding.severity}
                      </span>
                    </header>
                    <dl>
                      <div>
                        <dt>{t('employee.validation.actual')}</dt>
                        <dd>{finding.actual_value ?? t('common.emDash')}</dd>
                      </div>
                      <div>
                        <dt>{t('employee.validation.expected')}</dt>
                        <dd>{finding.expected_value ?? t('common.emDash')}</dd>
                      </div>
                      <div>
                        <dt>{t('validate.confidenceLabel')}</dt>
                        <dd>
                          {finding.confidence == null
                            ? t('common.emDash')
                            : `${Math.round(finding.confidence * 100)}%`}
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
              </section>
            ))}
          </div>
        </article>
      ))}
    </section>
  );
}
