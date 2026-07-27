import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import type { GuestValidationReport } from '../../types/validation-report';
import type { ComparisonField, IdentityCheck, PeriodCheck } from '../../services/employeePortal';
import {
  mapCompareToCardStatus,
  mapFindingToCardStatus,
  mapScopeToCardStatus,
  translateFindingMessage,
  translateFindingTitle,
  translateOverallResult,
  translateScopeReason,
  translateScopeTitle,
  type EmployeeCardStatus,
} from '../../lib/employee/validation-display';
import {
  taxonomyForRuleId,
  uiGroupForTaxonomy,
  type ValidationTaxonomy,
} from '../../lib/employee/validation-taxonomy';
import {
  buildCheckCatalogRows,
  checkRowStatusVisual,
  summarizeCheckRows,
  type CheckCatalogRow,
} from '../../lib/employee/check-catalog';
import { EmployeeValidationAiButton } from './EmployeeValidationAiButton';
import '../guest/landing/landing-chat.css';

type ValidationCard = {
  key: string;
  category: 'identity' | 'employment' | 'salary' | 'taxes' | 'benefits' | 'dates';
  /** UI group: employee checks (incl. contract) vs law checks. */
  uiGroup: 'employee_checks' | 'law_checks';
  taxonomy: ValidationTaxonomy | null;
  title: string;
  status: EmployeeCardStatus;
  explanation: string | null;
  expected: string | null;
  actual: string | null;
  confidence: number | null;
  findingId?: string | null;
  ruleId?: string | null;
};

export type ValidationResultsGroup = 'all' | 'employee_checks' | 'law_checks';

type EmployeeValidationResultsProps = {
  report: GuestValidationReport | null;
  identity: IdentityCheck | null;
  period: PeriodCheck | null;
  fileName?: string | null;
  onRunValidation?: () => void;
  canRunValidation?: boolean;
  validating?: boolean;
  validationOutdated?: boolean;
  /** Filter cards for Employee Checks / Law Checks tabs. */
  checkGroup?: ValidationResultsGroup;
  /**
   * checkRows — Batch polish: checks are primary; summary/history metadata secondary.
   * default — legacy compact summary-first layout.
   */
  presentation?: 'default' | 'checkRows';
  /** When true, hide the embedded Run/Rerun control (parent owns top chrome). */
  hideRunAction?: boolean;
};

export function EmployeeValidationResults({
  report,
  identity,
  period,
  fileName,
  onRunValidation,
  canRunValidation = false,
  validating = false,
  validationOutdated = false,
  checkGroup = 'all',
  presentation = 'default',
  hideRunAction = false,
}: EmployeeValidationResultsProps) {
  const { t } = useTranslation();
  const checkFocused = presentation === 'checkRows';

  const catalogRows = useMemo(() => {
    if (!checkFocused) return [] as CheckCatalogRow[];
    return buildCheckCatalogRows(
      report,
      t,
      checkGroup === 'all' ? 'all' : checkGroup,
    );
  }, [checkFocused, checkGroup, report, t]);

  const cards = useMemo(() => {
    if (checkFocused) return [] as ValidationCard[];
    const out: ValidationCard[] = [];

    if (identity) {
      for (const field of identity.fields) {
        out.push(identityFieldCard(field, t));
      }
    }
    if (period) {
      out.push({
        key: 'pay_period',
        category: 'dates',
        uiGroup: 'employee_checks',
        taxonomy: 'employee',
        title: t('employee.validation.checkTitles.pay_period'),
        status: mapCompareToCardStatus(period.status),
        explanation:
          period.status === 'mismatch'
            ? t('employee.compare.periodMismatch', {
                selected: `${period.selected_month}/${period.selected_year}`,
                extracted:
                  period.extracted_month && period.extracted_year
                    ? `${period.extracted_month}/${period.extracted_year}`
                    : t('common.emDash'),
              })
            : t(`employee.compare.status.${period.status}`, {
                defaultValue: t('employee.validation.status.unchecked'),
              }),
        expected: `${period.selected_month}/${period.selected_year}`,
        actual:
          period.extracted_month && period.extracted_year
            ? `${period.extracted_month}/${period.extracted_year}`
            : null,
        confidence: null,
        ruleId: 'employee.pay_period.match',
      });
    }

    if (report) {
      for (const scope of report.scope) {
        // Attendance validation is out of scope for the Employee Portal.
        if (scope.key === 'attendance') continue;
        out.push({
          key: `scope-${scope.key}`,
          category: categoryForRule(scope.key),
          uiGroup: uiGroupForScope(scope.key),
          taxonomy: null,
          title: translateScopeTitle(scope.key, scope.label, t),
          status: mapScopeToCardStatus(scope.status, scope.reason),
          explanation: translateScopeReason(scope.reason, t),
          expected: null,
          actual: null,
          confidence: null,
        });
      }
      for (const finding of report.findings) {
        const messageKey = finding.message_key || finding.code || finding.rule_id;
        if (/attendance/i.test(`${messageKey} ${finding.rule_id || ''}`)) continue;
        const taxonomy = taxonomyForRuleId(finding.rule_id, null);
        // SANITY → Digital Payslip field state only (skip validation tabs).
        if (taxonomy === 'sanity') continue;
        const uiGroup =
          taxonomy != null ? uiGroupForTaxonomy(taxonomy) : inferUiGroupFromFinding(finding.rule_id);
        if (uiGroup === 'digital') continue;
        out.push({
          key: `finding-${finding.id}`,
          category: categoryForRule(
            `${finding.rule_id || ''} ${finding.message_key || ''} ${finding.code || ''}`,
          ),
          uiGroup: uiGroup as 'employee_checks' | 'law_checks',
          taxonomy,
          title: translateFindingTitle(messageKey, t, finding.rule_id),
          status: mapFindingToCardStatus(finding),
          explanation:
            (finding.explanation && !looksLikeI18nKey(finding.explanation)
              ? finding.explanation
              : null) || translateFindingMessage(messageKey, t),
          expected: finding.expected_value,
          actual: finding.actual_value,
          confidence:
            finding.confidence != null && !Number.isNaN(finding.confidence)
              ? Math.round(finding.confidence * 100)
              : null,
          findingId: finding.id,
          ruleId: finding.rule_id,
        });
      }
    }

    if (checkGroup === 'all') return out;
    return out.filter((card) => card.uiGroup === checkGroup);
  }, [checkFocused, checkGroup, identity, period, report, t]);

  const statusVisual = (status: EmployeeCardStatus) => {
    switch (status) {
      case 'passed':
        return { icon: '✓', label: t('employee.validation.status.passed'), css: 'is-passed' };
      case 'failed':
        return { icon: '✕', label: t('employee.validation.status.failed'), css: 'is-failed' };
      case 'uncertain':
        return { icon: '⚠', label: t('employee.validation.status.uncertain'), css: 'is-uncertain' };
      default:
        return { icon: '–', label: t('employee.validation.status.unchecked'), css: 'is-unchecked' };
    }
  };

  const counts = useMemo(() => {
    if (checkFocused) {
      const summary = summarizeCheckRows(catalogRows);
      return {
        passed: summary.passed,
        failed: summary.failed,
        uncertain: summary.uncertain,
        unchecked: summary.not_run,
        executed: summary.executed,
        total: summary.total,
      };
    }
    const c = { passed: 0, failed: 0, uncertain: 0, unchecked: 0, executed: 0, total: 0 };
    for (const card of cards) {
      c[card.status] += 1;
      c.total += 1;
      if (card.status !== 'unchecked') c.executed += 1;
    }
    return c;
  }, [cards, catalogRows, checkFocused]);

  const catalogGroups = useMemo(() => {
    if (!checkFocused || checkGroup !== 'employee_checks') return null;
    const employeeRows = catalogRows.filter((row) => row.taxonomy !== 'contract');
    const contractRows = catalogRows.filter((row) => row.taxonomy === 'contract');
    return [
      { id: 'employeeProfile' as const, rows: employeeRows },
      { id: 'employmentContract' as const, rows: contractRows },
    ].filter((group) => group.rows.length > 0);
  }, [catalogRows, checkFocused, checkGroup]);

  const categoryGroups = useMemo(
    () =>
      (['identity', 'employment', 'salary', 'taxes', 'benefits', 'dates'] as const)
        .map((category) => ({
          category,
          cards: cards.filter((card) => card.category === category),
        }))
        .filter((group) => group.cards.length > 0),
    [cards],
  );

  const overallLabel = report
    ? translateOverallResult(String(report.overallResult || report.overallStatus), t)
    : null;

  const renderCatalogRow = (row: CheckCatalogRow) => {
    const visual = checkRowStatusVisual(row.status, t);
    const support =
      row.status === 'not_run'
        ? row.explanation ||
          (row.skipReasonKey
            ? t(`employee.validation.notRunReasons.${row.skipReasonKey}`)
            : t('employee.validation.status.notRun'))
        : row.explanation;
    return (
      <article
        key={row.key}
        className={`employee-validation-card employee-validation-check ${visual.css}`}
        data-check-status={row.status}
        aria-invalid={row.status === 'failed' ? true : undefined}
      >
        <header className="employee-validation-card__head">
          <h4>{row.title}</h4>
          <span className={`employee-field-status ${visual.css}`}>
            <span aria-hidden="true">{visual.icon}</span>
            <span>{visual.label}</span>
          </span>
        </header>
        {support && <p className="employee-validation-card__explain">{support}</p>}
        {row.findingId && (
          <div className="employee-validation-card__actions">
            <EmployeeValidationAiButton
              cardTitle={row.title}
              findingId={row.findingId}
              validationRunId={report?.runId}
              staticExplanation={row.explanation}
            />
          </div>
        )}
      </article>
    );
  };

  const renderCard = (card: ValidationCard) => {
    const visual = statusVisual(card.status);
    const hasDetails =
      Boolean(card.explanation) ||
      card.expected != null ||
      card.actual != null ||
      card.confidence != null;
    return (
      <article
        key={card.key}
        className={`employee-validation-card employee-validation-check ${visual.css}`}
      >
        <header className="employee-validation-card__head">
          <h4>{card.title}</h4>
          <span className={`employee-field-status ${visual.css}`}>
            <span aria-hidden="true">{visual.icon}</span>
            <span>{visual.label}</span>
          </span>
        </header>
        {card.explanation && (
          <p className="employee-validation-card__explain">{card.explanation}</p>
        )}
        <div className="employee-validation-card__actions">
          <EmployeeValidationAiButton
            cardTitle={card.title}
            findingId={card.findingId}
            validationRunId={report?.runId}
            staticExplanation={card.explanation}
          />
        </div>
        {hasDetails && (card.expected != null || card.actual != null || card.confidence != null) && (
          <div className="employee-validation-card__details">
            <div className="employee-validation-card__details-body">
              {card.expected != null && (
                <p>
                  <strong>{t('employee.validation.expected')}:</strong> {card.expected}
                </p>
              )}
              {card.actual != null && (
                <p>
                  <strong>{t('employee.validation.actual')}:</strong> {card.actual}
                </p>
              )}
              {card.confidence != null && (
                <p>
                  <strong>{t('validate.confidenceLabel')}:</strong> {card.confidence}%
                </p>
              )}
            </div>
          </div>
        )}
      </article>
    );
  };

  return (
    <div
      className={`employee-validation-results employee-validation-results--compact${
        checkFocused ? ' employee-validation-results--check-rows' : ''
      }`}
    >
      {!checkFocused && (
        <section
          className="employee-validation-summary employee-validation-summary--compact"
          aria-label={t('employee.validation.summaryTitle')}
        >
          <header>
            <h3>{t('employee.validation.summaryTitle')}</h3>
            {overallLabel && (
              <p className="employee-validation-summary__overall">{overallLabel}</p>
            )}
            {report && <p>{report.summary}</p>}
            {!report && <p>{t('employee.workspace.noValidationYet')}</p>}
            {fileName && (
              <p className="landing-doc-card__file">
                {t('validate.uploadedDocument')}: {fileName}
              </p>
            )}
          </header>

          <ul className="employee-validation-summary__counts" aria-label={t('employee.validation.legend')}>
            <li className="is-passed">
              <span aria-hidden="true">✔</span>
              <span>{t('employee.validation.status.passed')}</span>
              <strong>{counts.passed}</strong>
            </li>
            <li className="is-failed">
              <span aria-hidden="true">❌</span>
              <span>{t('employee.validation.status.failed')}</span>
              <strong>{counts.failed}</strong>
            </li>
            <li className="is-uncertain">
              <span aria-hidden="true">⚠</span>
              <span>{t('employee.validation.status.uncertain')}</span>
              <strong>{counts.uncertain}</strong>
            </li>
            <li className="is-unchecked">
              <span aria-hidden="true">➖</span>
              <span>{t('employee.validation.status.unchecked')}</span>
              <strong>{counts.unchecked}</strong>
            </li>
          </ul>
        </section>
      )}

      {validationOutdated && (
        <p className="employee-validation-outdated" role="status">
          {t('employee.workspace.validationOutdated')}
        </p>
      )}

      {!hideRunAction && onRunValidation && (
        <div className="employee-payslip-wizard__actions">
          <button
            type="button"
            className="btn btn--primary"
            disabled={!canRunValidation || validating}
            onClick={onRunValidation}
          >
            {validating
              ? t('employee.upload.validatingPayroll')
              : report
                ? t('employee.workspace.runValidationAgain')
                : t('employee.upload.runValidation')}
          </button>
        </div>
      )}

      {validating && (
        <p className="employee-workspace-hint" role="status">
          {t('employee.upload.validatingPayroll')}
        </p>
      )}

      <section
        className="employee-validation-cards"
        aria-label={t('employee.validation.rulesTitle')}
      >
        {checkFocused ? (
          catalogRows.length === 0 ? (
            <p>{t('employee.validation.noRules')}</p>
          ) : catalogGroups ? (
            catalogGroups.map((group) => (
              <section key={group.id} className="employee-validation-group">
                <h4>{t(`employee.validation.groups.${group.id}`)}</h4>
                {group.rows.map(renderCatalogRow)}
              </section>
            ))
          ) : (
            catalogRows.map(renderCatalogRow)
          )
        ) : cards.length === 0 ? (
          <p>{t('employee.validation.noRules')}</p>
        ) : (
          categoryGroups.map((group) => (
            <section key={group.category} className="employee-validation-group">
              <h4>
                {t(`employee.validation.groups.${group.category}`, {
                  defaultValue: group.category,
                })}
              </h4>
              {group.cards.map(renderCard)}
            </section>
          ))
        )}
      </section>

      {checkFocused && (
        <footer
          className="employee-validation-summary employee-validation-summary--secondary"
          aria-label={t('employee.validation.summaryTitle')}
        >
          {overallLabel && (
            <p className="employee-validation-summary__overall">{overallLabel}</p>
          )}
          {report && counts.total > 0 && (
            <p className="employee-workspace-hint">
              {t('employee.validation.coverageSummary', {
                executed: counts.executed,
                total: counts.total,
              })}
            </p>
          )}
          {report?.summary && <p className="employee-workspace-hint">{report.summary}</p>}
          {!report && <p className="employee-workspace-hint">{t('employee.workspace.noValidationYet')}</p>}
          <ul className="employee-validation-summary__counts" aria-label={t('employee.validation.legend')}>
            <li className="is-passed">
              <span aria-hidden="true">✔</span>
              <span>{t('employee.validation.status.passed')}</span>
              <strong>{counts.passed}</strong>
            </li>
            <li className="is-failed">
              <span aria-hidden="true">❌</span>
              <span>{t('employee.validation.status.failed')}</span>
              <strong>{counts.failed}</strong>
            </li>
            <li className="is-uncertain">
              <span aria-hidden="true">⚠</span>
              <span>{t('employee.validation.status.uncertain')}</span>
              <strong>{counts.uncertain}</strong>
            </li>
            <li className="is-not-run">
              <span aria-hidden="true">➖</span>
              <span>{t('employee.validation.status.notRun')}</span>
              <strong>{counts.unchecked}</strong>
            </li>
          </ul>
        </footer>
      )}
    </div>
  );
}

function looksLikeI18nKey(value: string): boolean {
  return /^[a-z][a-z0-9_.-]*$/i.test(value.trim()) && value.includes('.');
}

function identityFieldCard(field: ComparisonField, t: TFunction): ValidationCard {
  let explanation: string | null = t(`employee.compare.status.${field.status}`, {
    defaultValue: t('employee.validation.status.unchecked'),
  });
  if (field.explanation_code === 'employee_name_language_mismatch') {
    explanation = t('employee.compare.nameLanguageMismatch');
  } else if (field.key === 'national_id' && field.status === 'mismatch') {
    explanation = t('employee.compare.nationalIdMismatch');
  } else if (field.key === 'employee_name' && field.status === 'mismatch') {
    explanation = t('employee.compare.nameMismatchWarning');
  } else if (field.status === 'missing' || field.status === 'cannot_validate') {
    explanation = t('employee.validation.cannotValidateReason');
  }
  return {
    key: `identity-${field.key}`,
    category: 'identity',
    uiGroup: 'employee_checks',
    taxonomy: 'employee',
    title: t(`employee.validation.checkTitles.${field.key}`, {
      defaultValue: t('employee.validation.checkTitles.identity'),
    }),
    status: mapCompareToCardStatus(field.status),
    explanation,
    expected: field.expected_display,
    actual: field.extracted_display,
    confidence: null,
  };
}

function categoryForRule(value: string): ValidationCard['category'] {
  const normalized = value.toLowerCase();
  if (/identity|employee|national|name/.test(normalized)) return 'identity';
  if (/tax|income|credit|withhold/.test(normalized)) return 'taxes';
  if (/benefit|pension|provident|insurance|fund/.test(normalized)) return 'benefits';
  if (/date|period|month|year/.test(normalized)) return 'dates';
  if (/salary|gross|net|wage|pay|hour|overtime/.test(normalized)) return 'salary';
  return 'employment';
}

function uiGroupForScope(scopeKey: string): 'employee_checks' | 'law_checks' {
  const key = scopeKey.toLowerCase();
  if (key.includes('payroll') || key.includes('tax') || key.includes('legal')) {
    return 'law_checks';
  }
  return 'employee_checks';
}

function inferUiGroupFromFinding(ruleId: string | null | undefined): 'employee_checks' | 'law_checks' {
  const taxonomy = taxonomyForRuleId(ruleId, null);
  if (taxonomy) {
    const group = uiGroupForTaxonomy(taxonomy);
    if (group === 'digital') return 'employee_checks';
    return group;
  }
  // Ambiguous → keep visible under Employee Checks (safer than hiding).
  return 'employee_checks';
}
