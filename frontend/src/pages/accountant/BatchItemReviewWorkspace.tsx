import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../../auth/AuthContext';
import { PortalPage } from '../../components/PortalPage';
import { IconBackButton } from '../../components/ui/IconBackButton';
import { ActionIconButton } from '../../components/ui/ActionIconButton';
import { useConfirmDialog } from '../../components/ui/Dialog';
import {
  FormControl,
  FormField,
  FormInfoPanel,
  FormSection,
  FormShell,
} from '../../components/ui/form/FormPrimitives';
import { SparklesIcon, TrashIcon, UserIcon } from '../../components/ui/icons';
import { EmployeeDigitalForm } from '../../features/employee/EmployeeDigitalForm';
import { EmployeeValidationResults } from '../../features/employee/EmployeeValidationResults';
import { Search, UserPlus } from 'lucide-react';
import type { FieldDraft } from '../../hooks/useEmployeePayslipFlow';
import {
  batchService,
  type BatchItemReview,
  type BatchValidationHistoryRun,
} from '../../services/batch';
import { employeesService } from '../../services/employees';
import type { EmployeeRecord } from '../../types/employee';
import { buildEmployeeFieldValidationMap } from '../../lib/employee/field-validation-status';
import { applyPayrollPeriodPresentation } from '../../lib/employee/payroll-period-presentation';
import { proposedPayrollPeriodValue } from '../../lib/employee/payroll-period-proposal';
import { FIELD_MAX_LENGTH, validatePersonName } from '../../lib/employee/field-text';
import { validateNationalId } from '../../lib/employee/israeli-id';
import {
  EMAIL_MAX_LENGTH,
  FREE_TEXT_MAX_LENGTH,
  clampFreeTextInput,
  validateEmailFormat,
} from '../../lib/validation';
import { reviewFieldsFromExtractionPayload } from '../../lib/guest/extraction-review';
import { getDisplayError } from '../../lib/getDisplayError';
import type { GuestValidationReport } from '../../types/validation-report';
import { TruncatedText } from '../../components/ui/TruncatedText';
import './UnknownEmployeeResolution.css';
import '../employee/PayslipMonthWorkspace.css';
import '../../features/employee/employee-payslip.css';

type PrimaryTab = 'digital' | 'employee_checks' | 'law_checks';
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
  manualApprovals?: Array<Record<string, unknown>> | null,
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
    ruleOutcomes: (latest.rule_outcomes ?? []).map((item) => ({
      rule_id: item.rule_id,
      outcome: item.outcome,
      skip_reason: item.skip_reason ?? null,
      reason_code: item.reason_code ?? null,
      message: item.message ?? null,
    })),
    manualApprovals: (manualApprovals ?? []).map((row) => ({
      finding_id: (row.finding_id as string | null | undefined) ?? null,
      rule_id: (row.rule_id as string | null | undefined) ?? null,
      original_severity: (row.original_severity as string | null | undefined) ?? null,
      original_deterministic_status:
        (row.original_deterministic_status as string | null | undefined) ??
        (row.deterministic_status as string | null | undefined) ??
        null,
      deterministic_status: (row.deterministic_status as string | null | undefined) ?? null,
      review_status: (row.review_status as string | null | undefined) ?? 'manually_approved',
      approved_by: (row.approved_by as string | null | undefined) ?? null,
      approved_at: (row.approved_at as string | null | undefined) ?? null,
      reason: (row.reason as string | null | undefined) ?? null,
      validation_run_id: (row.validation_run_id as string | null | undefined) ?? null,
    })),
  };
}

export function BatchItemReviewWorkspacePage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { confirm } = useConfirmDialog();
  const { session } = useAuth();
  const { jobId = '', itemId = '' } = useParams<{ jobId: string; itemId: string }>();
  const [review, setReview] = useState<BatchItemReview | null>(null);
  const [reviewLoading, setReviewLoading] = useState(true);
  const [drafts, setDrafts] = useState<Record<string, FieldDraft>>({});
  const [tab, setTab] = useState<PrimaryTab>('digital');
  const [resolutionMode, setResolutionMode] = useState<ResolutionMode>('search');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<EmployeeRecord[]>([]);
  const [busy, setBusy] = useState(false);
  const [busyRuleId, setBusyRuleId] = useState<string | null>(null);
  /** Load/refresh failures — page chrome only (not duplicated in Validation). */
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  /** Validate / rerun / approve failures — Validation tab only. */
  const [actionError, setActionError] = useState<string | null>(null);
  const [payPeriodApproved, setPayPeriodApproved] = useState(false);
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
    const reviewFields = reviewFieldsFromExtractionPayload(next);
    const extractedName = fieldText(
      { ...next, fields: reviewFields },
      'employee_name',
      'full_name',
      'שם העובד',
      'שם עובד',
    ).trim();
    const [nameFirst = '', ...nameRest] = extractedName.split(/\s+/);
    setReview({ ...next, fields: reviewFields });
    setDrafts(
      Object.fromEntries(
        reviewFields.map((field) => [
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
      employeeNumber:
        previous.employeeNumber ||
        fieldText({ ...next, fields: reviewFields }, 'employee_number', 'מספר עובד', 'מס עובד'),
      firstName:
        previous.firstName ||
        fieldText({ ...next, fields: reviewFields }, 'first_name', 'employee_first_name') ||
        nameFirst,
      lastName:
        previous.lastName ||
        fieldText({ ...next, fields: reviewFields }, 'last_name', 'employee_last_name') ||
        nameRest.join(' '),
      nationalId:
        previous.nationalId ||
        fieldText(
          { ...next, fields: reviewFields },
          'national_id',
          'employee_id',
          'ת.ז.',
          'תעודת זהות',
        ),
      email: previous.email || fieldText({ ...next, fields: reviewFields }, 'email', 'employee_email'),
      department:
        previous.department ||
        fieldText({ ...next, fields: reviewFields }, 'department', 'department_name', 'מחלקה'),
    }));
  }, []);

  const refresh = useCallback(async () => {
    setWorkspaceError(null);
    setActionError(null);
    setReviewLoading(true);
    try {
      applyReview(await batchService.getItemReview(jobId, itemId));
    } catch (reason) {
      setWorkspaceError(
        getDisplayError(reason, t('common.error'), {
          networkFallback: t('common.networkUnavailable'),
        }),
      );
    } finally {
      setReviewLoading(false);
    }
  }, [applyReview, itemId, jobId, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const latest = review?.validation_history[0] ?? null;
  const needsResolution =
    review?.item.status === 'unknown_employee' || !review?.item.employee_number;
  const dirty = Object.values(drafts).some((draft) => draft.dirty);
  const validationReport = useMemo(
    () =>
      review
        ? reportFromBatchHistory(latest, review.document_id, review.manual_approvals)
        : null,
    [latest, review],
  );

  const baseValidationMap = useMemo(() => {
    if (dirty || !review) return {};
    return buildEmployeeFieldValidationMap(review.fields, validationReport);
  }, [dirty, review, validationReport]);

  const periodPresentation = useMemo(
    () =>
      applyPayrollPeriodPresentation({
        fields: review?.fields,
        drafts,
        validationMap: baseValidationMap,
        periodApproved: payPeriodApproved,
        workspaceYear: review?.item.payroll_year ?? undefined,
        workspaceMonth: review?.item.payroll_month ?? undefined,
        proposedExplanation: t('employee.digitalForm.payrollPeriodProposedExplain', {
          period: proposedPayrollPeriodValue(
            review?.item.payroll_year ?? undefined,
            review?.item.payroll_month ?? undefined,
          ),
        }),
      }),
    [
      baseValidationMap,
      drafts,
      payPeriodApproved,
      review?.fields,
      review?.item.payroll_month,
      review?.item.payroll_year,
      t,
    ],
  );

  const validationMap = periodPresentation.validationMap;
  const digitalFormDrafts = periodPresentation.displayDrafts;

  useEffect(() => {
    setPayPeriodApproved(false);
  }, [itemId]);

  const mapError = (reason: unknown, fallback: string) =>
    getDisplayError(reason, fallback, { networkFallback: t('common.networkUnavailable') });

  const rerunSingleRule = async (ruleId: string) => {
    if (!review) return;
    setBusyRuleId(ruleId);
    setActionError(null);
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
      next = await batchService.validateItemReview(jobId, itemId, {
        rerunScope: 'rules',
        ruleIds: [ruleId],
        locale: i18n.language?.slice(0, 2),
      });
      applyReview(next);
    } catch (reason) {
      setActionError(mapError(reason, t('employee.validation.actions.rerunFailed')));
    } finally {
      setBusyRuleId(null);
    }
  };

  const approveCheck = async (input: { ruleId: string; findingId?: string | null }) => {
    if (!review || !latest) return;
    const accepted = await confirm({
      title: t('employee.validation.actions.approveConfirmTitle'),
      message: t('employee.validation.actions.approveConfirmMessage'),
      confirmLabel: t('employee.validation.actions.approveConfirm'),
      cancelLabel: t('common.cancel'),
      variant: 'warning',
    });
    if (!accepted) return;
    setBusyRuleId(input.ruleId);
    setActionError(null);
    try {
      await batchService.approveCheck({
        documentId: review.document_id,
        validationRunId: latest.validation_run_id,
        ruleId: input.ruleId,
        findingId: input.findingId,
        acknowledgement: true,
        reason: t('employee.validation.actions.approveDefaultReason').slice(0, 500),
      });
      await refresh();
    } catch (reason) {
      setActionError(mapError(reason, t('employee.validation.actions.approveFailed')));
    } finally {
      setBusyRuleId(null);
    }
  };
  const saveAndValidate = async () => {
    if (!review) return;
    setBusy(true);
    setActionError(null);
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
      setTab('employee_checks');
    } catch (reason) {
      setActionError(mapError(reason, t('validate.validationFailed')));
    } finally {
      setBusy(false);
    }
  };

  const attach = async (employee: EmployeeRecord) => {
    setBusy(true);
    setWorkspaceError(null);
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
      setWorkspaceError(mapError(reason, t('common.error')));
    } finally {
      setBusy(false);
    }
  };

  const search = async () => {
    setBusy(true);
    setWorkspaceError(null);
    try {
      setResults(
        await employeesService.list({
          q: query.trim() || undefined,
          includeDisabled: false,
        }),
      );
    } catch (reason) {
      setWorkspaceError(mapError(reason, t('common.error')));
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
      setWorkspaceError(t('accountant.unknown.required'));
      return;
    }
    const first = validatePersonName(createValues.firstName);
    if (!first.ok) {
      setWorkspaceError(
        t(
          first.code === 'digits'
            ? 'common.validation.nameNoDigits'
            : first.code === 'max_length'
              ? 'common.validation.nameMaxLength'
              : 'common.validation.nameInvalid',
        ),
      );
      return;
    }
    const last = validatePersonName(createValues.lastName);
    if (!last.ok) {
      setWorkspaceError(
        t(
          last.code === 'digits'
            ? 'common.validation.nameNoDigits'
            : last.code === 'max_length'
              ? 'common.validation.nameMaxLength'
              : 'common.validation.nameInvalid',
        ),
      );
      return;
    }
    const emailResult = validateEmailFormat(createValues.email, { allowEmpty: true });
    if (!emailResult.ok) {
      setWorkspaceError(t('common.validation.invalidEmail'));
      return;
    }
    const nid = validateNationalId(createValues.nationalId);
    if (!nid.ok) {
      setWorkspaceError(
        t(
          nid.code === 'digits_only'
            ? 'common.validation.nationalIdDigits'
            : nid.code === 'length'
              ? 'common.validation.nationalIdLength'
              : 'common.validation.nationalIdChecksum',
        ),
      );
      return;
    }
    setBusy(true);
    setWorkspaceError(null);
    try {
      const created = await employeesService.create({
        employee_number: clampFreeTextInput(
          createValues.employeeNumber.trim(),
          FREE_TEXT_MAX_LENGTH.identifier,
        ),
        first_name: first.value,
        last_name: last.value,
        national_id: nid.digits,
        email: emailResult.value || undefined,
        employment_type: 'full_time',
        salary_type: 'monthly',
        metadata: {
          company: clampFreeTextInput(createValues.company.trim(), FREE_TEXT_MAX_LENGTH.shortNote),
          department: clampFreeTextInput(
            createValues.department.trim(),
            FREE_TEXT_MAX_LENGTH.shortNote,
          ),
          source: 'batch_unknown_employee_resolution',
        },
      });
      await attach(created);
    } catch (reason) {
      setWorkspaceError(mapError(reason, t('common.error')));
      setBusy(false);
    }
  };

  const ignore = async () => {
    const accepted = await confirm({
      title: t('accountant.bulk.review.deleteTitle'),
      message: t('accountant.bulk.review.deleteWarning'),
      confirmLabel: t('accountant.bulk.review.deleteConfirm'),
      cancelLabel: t('common.cancel'),
      variant: 'danger',
    });
    if (!accepted) return;
    setBusy(true);
    try {
      await batchService.resolveItem(jobId, itemId, { action: 'ignore' });
      navigate('/accountant/bulk-upload');
    } catch (reason) {
      setWorkspaceError(mapError(reason, t('common.error')));
      setBusy(false);
    }
  };

  const primaryTabs: Array<[PrimaryTab, string]> = [
    ['digital', 'employee.upload.tabDigital'],
    ['employee_checks', 'employee.workspace.tabEmployeeChecks'],
    ['law_checks', 'employee.workspace.tabLawChecks'],
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
      <div className="employee-month-workspace batch-item-review">
        <div className="batch-review-toolbar">
          <IconBackButton
            ariaLabel={t('accountant.workspace.backToBatchAria')}
            title={t('accountant.bulk.review.backToBatch')}
            onClick={() => navigate('/accountant/bulk-upload')}
          />
          <span className="status-badge status-badge--batch-unknown_employee">
            {t('accountant.bulk.status.unknown_employee')}
          </span>
          <div className="batch-review-toolbar__actions">
            {needsResolution && (
              <ActionIconButton
                label={t('accountant.unknown.create')}
                icon={<UserPlus size={16} aria-hidden="true" />}
                onClick={() => setResolutionMode('create')}
                className={resolutionMode === 'create' ? 'is-active' : undefined}
              />
            )}
            <ActionIconButton
              label={t('accountant.bulk.review.deleteAction')}
              icon={<TrashIcon size={16} aria-hidden="true" />}
              tone="danger"
              disabled={busy}
              onClick={() => void ignore()}
            />
            <button
              type="button"
              className="btn btn--primary"
              disabled
              title={t('accountant.bulk.review.resolveBeforePublish')}
            >
              {t('accountant.bulk.publish.action')}
            </button>
          </div>
        </div>

        {needsResolution && (
        <section className="unknown-resolution__summary unknown-resolution__resolution-panel batch-resolution-panel">
          <div>
            <strong>{t('accountant.bulk.review.resolutionRequired')}</strong>
            <p>{t('accountant.bulk.review.resolutionDescription')}</p>
          </div>
          {resolutionMode === 'search' ? (
            <div className="batch-resolution-search">
              <div className="batch-resolution-search__integrated">
                <label className="batch-resolution-search__field batch-resolution-search__field--integrated">
                  <span className="visually-hidden">{t('accountant.unknown.searchLabel')}</span>
                  <button
                    type="button"
                    className="batch-resolution-search__icon-btn"
                    disabled={busy}
                    onClick={() => void search()}
                    aria-label={t('common.search')}
                  >
                    <Search size={16} aria-hidden="true" />
                  </button>
                  <input
                    className="pc-form-control"
                    type="search"
                    maxLength={FREE_TEXT_MAX_LENGTH.searchQuery}
                    value={query}
                    onChange={(event) =>
                      setQuery(
                        clampFreeTextInput(event.target.value, FREE_TEXT_MAX_LENGTH.searchQuery),
                      )
                    }
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        void search();
                      }
                    }}
                    placeholder={t('accountant.unknown.searchPlaceholder')}
                    aria-label={t('accountant.unknown.searchLabel')}
                  />
                </label>
              </div>
              <div className="unknown-resolution__results" aria-live="polite">
                {results.length === 0 ? (
                  <p className="employee-workspace-hint">{t('accountant.unknown.noResults', {
                    defaultValue: t('common.emDash'),
                  })}</p>
                ) : (
                  results.map((employee) => (
                    <button
                      key={employee.employeeNumber}
                      type="button"
                      className="unknown-resolution__employee"
                      disabled={busy}
                      onClick={() => void attach(employee)}
                    >
                      <strong>
                        <TruncatedText>{employee.fullName}</TruncatedText>
                      </strong>
                      <span>#{employee.employeeNumber}</span>
                      <span>{employee.nationalIdMasked || t('common.emDash')}</span>
                    </button>
                  ))
                )}
              </div>
            </div>
          ) : (
            <FormShell
              aside={
                <FormInfoPanel
                  tone="tip"
                  eyebrow={t('forms.info.tipEyebrow')}
                  title={t('forms.info.unknownCreateTitle')}
                  icon={<SparklesIcon size={14} aria-hidden="true" />}
                >
                  <p>{t('forms.info.unknownCreateBody')}</p>
                </FormInfoPanel>
              }
            >
              <div className="form-actions">
                <button
                  type="button"
                  className="btn btn--ghost"
                  disabled={busy}
                  onClick={() => setResolutionMode('search')}
                >
                  {t('accountant.unknown.search')}
                </button>
              </div>
              <FormSection
                title={t('forms.sections.identity.title')}
                description={t('forms.sections.identity.description')}
                icon={<UserIcon size={18} />}
              >
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
                  <FormField key={key} label={t(label)} htmlFor={`batch-create-${key}`} required>
                    <FormControl
                      id={`batch-create-${key}`}
                      type={key === 'email' ? 'email' : 'text'}
                      value={createValues[key]}
                      readOnly={key === 'company'}
                      inputMode={key === 'nationalId' ? 'numeric' : undefined}
                      maxLength={
                        key === 'nationalId'
                          ? FIELD_MAX_LENGTH.nationalId
                          : key === 'firstName' || key === 'lastName'
                            ? FIELD_MAX_LENGTH.personName
                            : key === 'email'
                              ? EMAIL_MAX_LENGTH
                              : key === 'employeeNumber'
                                ? FREE_TEXT_MAX_LENGTH.identifier
                                : FREE_TEXT_MAX_LENGTH.shortNote
                      }
                      autoComplete="off"
                      onChange={(event) => {
                        let next = event.target.value;
                        if (key === 'nationalId') {
                          next = next.replace(/\D/g, '').slice(0, FIELD_MAX_LENGTH.nationalId);
                        } else if (key === 'email') {
                          next = next.slice(0, EMAIL_MAX_LENGTH);
                        } else if (key === 'firstName' || key === 'lastName') {
                          next = next.slice(0, FIELD_MAX_LENGTH.personName);
                        } else if (key === 'employeeNumber') {
                          next = clampFreeTextInput(next, FREE_TEXT_MAX_LENGTH.identifier);
                        } else {
                          next = clampFreeTextInput(next, FREE_TEXT_MAX_LENGTH.shortNote);
                        }
                        setCreateValues((previous) => ({
                          ...previous,
                          [key]: next,
                        }));
                      }}
                    />
                  </FormField>
                ))}
              </FormSection>
              <div className="form-actions">
                <button
                  className="btn btn--primary"
                  disabled={busy}
                  onClick={() => void createAndAttach()}
                >
                  {t('accountant.unknown.createAndAttach')}
                </button>
              </div>
            </FormShell>
          )}
        </section>
        )}

        {!reviewLoading && workspaceError && (
          <p className="chat-panel__error" role="alert">
            {workspaceError}
          </p>
        )}
        {!reviewLoading &&
          actionError &&
          tab === 'digital' && (
            <p className="chat-panel__error" role="alert">
              {actionError}
            </p>
          )}

        <div className="batch-review-view-chrome">
          <div
            className="employee-review-tabs employee-review-tabs--product"
            role="tablist"
            aria-label={t('employee.workspace.tabs')}
          >
            {primaryTabs.map(([id, key]) => (
              <button
                key={id}
                type="button"
                role="tab"
                id={`batch-review-tab-${id}`}
                aria-selected={tab === id}
                aria-controls={`batch-review-panel-${id}`}
                tabIndex={tab === id ? 0 : -1}
                className={`employee-review-tabs__tab ${tab === id ? 'is-active' : ''}`}
                onClick={() => setTab(id)}
              >
                {t(key)}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="btn btn--secondary batch-review-rerun"
            disabled={busy || !review}
            onClick={() => void saveAndValidate()}
          >
            {busy
              ? t('employee.upload.validatingPayroll')
              : t('employee.workspace.runValidationAgain')}
          </button>
        </div>

        {tab === 'digital' && (
          <div
            id="batch-review-panel-digital"
            role="tabpanel"
            aria-labelledby="batch-review-tab-digital"
          >
            <EmployeeDigitalForm
              fields={review?.fields}
              drafts={digitalFormDrafts}
              editable
              audience="accountant"
              collapseSecondaryFields
              busy={busy}
              loading={reviewLoading}
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
              onRemoveField={(key) => {
                setReview((previous) =>
                  previous
                    ? {
                        ...previous,
                        fields: previous.fields.filter((field) => field.key !== key),
                      }
                    : previous,
                );
                setDrafts((previous) => ({
                  ...previous,
                  [key]: { value: '', clear: true, dirty: true },
                }));
              }}
              onAddField={({ name, value }) => {
                const label = name.trim();
                const key = label
                  ? `custom_field_${label
                      .toLowerCase()
                      .replace(/[^a-z0-9]+/g, '_')
                      .replace(/^_|_$/g, '')
                      .slice(0, 40)}_${crypto.randomUUID().slice(0, 6)}`
                  : `custom_field_${crypto.randomUUID().slice(0, 8)}`;
                setReview((previous) =>
                  previous
                    ? {
                        ...previous,
                        fields: [
                          ...previous.fields,
                          {
                            key,
                            value,
                            confidence: null,
                            source_text: label || null,
                            status: 'FOUND',
                            edited_by_user: true,
                          },
                        ],
                      }
                    : previous,
                );
                setDrafts((previous) => ({
                  ...previous,
                  [key]: { value, clear: value.trim() === '', dirty: true },
                }));
              }}
              onApproveField={(key) => {
                if (key !== 'pay_period') return;
                const proposed =
                  periodPresentation.proposedValue ||
                  proposedPayrollPeriodValue(
                    review?.item.payroll_year ?? undefined,
                    review?.item.payroll_month ?? undefined,
                  );
                setPayPeriodApproved(true);
                setDrafts((previous) => ({
                  ...previous,
                  pay_period: { value: proposed, clear: false, dirty: true },
                }));
              }}
            />
          </div>
        )}

        {(tab === 'employee_checks' || tab === 'law_checks') && (
          <div
            id={`batch-review-panel-${tab}`}
            role="tabpanel"
            aria-labelledby={`batch-review-tab-${tab}`}
          >
            <EmployeeValidationResults
              report={validationReport}
              identity={null}
              period={null}
              fileName={review?.original_filename}
              checkGroup={tab}
              presentation="checkRows"
              hideRunAction
              validating={busy}
              loading={reviewLoading}
              errorMessage={
                tab === 'employee_checks' || tab === 'law_checks' ? actionError : null
              }
              checkActions={{
                canRerun: true,
                canManualApprove: true,
                busyRuleId,
                onRerunRule: rerunSingleRule,
                onManualApprove: approveCheck,
              }}
            />
            {tab === 'employee_checks' && (
              <ValidationHistory runs={review?.validation_history ?? []} />
            )}
          </div>
        )}
      </div>
    </PortalPage>
  );
}

function ValidationHistory({ runs }: { runs: BatchValidationHistoryRun[] }) {
  const { t, i18n } = useTranslation();
  if (!runs.length) return null;
  const latestRun = runs[0];
  return (
    <details className="employee-validation-history employee-validation-history--secondary">
      <summary>
        {t('accountant.bulk.validationHistory.title')}
        {latestRun.completed_at
          ? ` · ${new Intl.DateTimeFormat(i18n.language, {
              dateStyle: 'medium',
              timeStyle: 'short',
            }).format(new Date(latestRun.completed_at))}`
          : ''}
      </summary>
      {runs.map((run, index) => (
        <article key={run.validation_run_id} className="employee-validation-history__run">
          <header>
            <strong>
              {t('accountant.bulk.validationHistory.run', { value: runs.length - index })}
            </strong>
            <span
              className={`status-badge status-badge--${run.overall_result === 'pass' ? 'passed' : 'warnings'}`}
            >
              {run.overall_result === 'pass'
                ? t('employee.validation.status.passed')
                : run.overall_result || run.status}
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
        </article>
      ))}
    </details>
  );
}
