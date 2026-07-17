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
import { EmployeeValidationAiButton } from './EmployeeValidationAiButton';
import '../guest/landing/landing-chat.css';

type ValidationCard = {
  key: string;
  title: string;
  status: EmployeeCardStatus;
  explanation: string | null;
  expected: string | null;
  actual: string | null;
  confidence: number | null;
  findingId?: string | null;
};

type EmployeeValidationResultsProps = {
  report: GuestValidationReport | null;
  identity: IdentityCheck | null;
  period: PeriodCheck | null;
  fileName?: string | null;
  onRunValidation?: () => void;
  canRunValidation?: boolean;
  validating?: boolean;
  validationOutdated?: boolean;
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
}: EmployeeValidationResultsProps) {
  const { t } = useTranslation();

  const cards = useMemo(() => {
    const out: ValidationCard[] = [];

    if (identity) {
      for (const field of identity.fields) {
        out.push(identityFieldCard(field, t));
      }
    }
    if (period) {
      out.push({
        key: 'pay_period',
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
      });
    }

    if (report) {
      for (const scope of report.scope) {
        // Attendance validation is out of scope for the Employee Portal.
        if (scope.key === 'attendance') continue;
        out.push({
          key: `scope-${scope.key}`,
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
        out.push({
          key: `finding-${finding.id}`,
          title: translateFindingTitle(messageKey, t),
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
        });
      }
    }

    return out;
  }, [identity, period, report, t]);

  const statusVisual = (status: EmployeeCardStatus) => {
    switch (status) {
      case 'passed':
        return { icon: '✓', label: t('employee.validation.status.passed'), css: 'is-passed' };
      case 'failed':
        return { icon: '!', label: t('employee.validation.status.failed'), css: 'is-failed' };
      case 'uncertain':
        return { icon: '⚠', label: t('employee.validation.status.uncertain'), css: 'is-uncertain' };
      default:
        return { icon: '–', label: t('employee.validation.status.unchecked'), css: 'is-unchecked' };
    }
  };

  const counts = useMemo(() => {
    const c = { passed: 0, failed: 0, uncertain: 0, unchecked: 0 };
    for (const card of cards) c[card.status] += 1;
    return c;
  }, [cards]);

  const overallLabel = report
    ? translateOverallResult(String(report.overallResult || report.overallStatus), t)
    : null;

  return (
    <div className="employee-validation-results employee-validation-results--compact">
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

      {validationOutdated && (
        <p className="employee-validation-outdated" role="status">
          {t('employee.workspace.validationOutdated')}
        </p>
      )}

      {onRunValidation && (
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

      <section className="employee-validation-cards" aria-label={t('employee.validation.rulesTitle')}>
        {cards.length === 0 ? (
          <p>{t('employee.validation.noRules')}</p>
        ) : (
          cards.map((card) => {
            const visual = statusVisual(card.status);
            const hasDetails =
              Boolean(card.explanation) ||
              card.expected != null ||
              card.actual != null ||
              card.confidence != null;
            return (
              <article key={card.key} className={`employee-validation-card ${visual.css}`}>
                <header className="employee-validation-card__head">
                  <h4>{card.title}</h4>
                  <span className={`employee-field-status ${visual.css}`}>
                    <span aria-hidden="true">{visual.icon}</span>
                    <span>{visual.label}</span>
                  </span>
                </header>
                <div className="employee-validation-card__actions">
                  <EmployeeValidationAiButton
                    cardTitle={card.title}
                    findingId={card.findingId}
                    validationRunId={report?.runId}
                    staticExplanation={card.explanation}
                  />
                </div>
                {hasDetails && (
                  <details className="employee-validation-card__details">
                    <summary>{t('employee.validation.details')}</summary>
                    <div className="employee-validation-card__details-body">
                      {card.explanation && (
                        <p className="employee-validation-card__explain">{card.explanation}</p>
                      )}
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
                  </details>
                )}
              </article>
            );
          })
        )}
      </section>
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
