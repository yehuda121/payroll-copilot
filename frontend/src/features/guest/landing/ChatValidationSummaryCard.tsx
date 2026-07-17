import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { GuestValidationReport } from '../../../types/validation-report';
import { FieldAiPopover } from './FieldAiPopover';
import { FIELD_EXPLAIN_KEYS, STATIC_FIELD_TIPS, mapFindingSeverityToFieldStatus } from './fieldGuidance';
import './landing-chat.css';

type ChatValidationSummaryCardProps = {
  report: GuestValidationReport;
  fileName?: string | null;
};

type ScopeRow = {
  key: string;
  label: string;
  status: 'passed' | 'failed' | 'uncertain' | 'unchecked';
  reason?: string | null;
  explanation?: string | null;
  tipKey?: string;
};

export function ChatValidationSummaryCard({ report, fileName }: ChatValidationSummaryCardProps) {
  const { t } = useTranslation();

  const rows = useMemo(() => {
    const out: ScopeRow[] = [];

    for (const scope of report.scope) {
      let status: ScopeRow['status'] = 'unchecked';
      if (scope.status === 'completed') status = 'passed';
      else if (scope.status === 'not_available' || scope.status === 'partial') status = 'unchecked';
      out.push({
        key: scope.key,
        label: scope.label || scope.key,
        status,
        reason: scope.reason,
      });
    }

    for (const finding of report.findings) {
      const status = mapFindingSeverityToFieldStatus(finding.severity);
      const fieldHint =
        finding.rule_id?.split('.').pop() ||
        finding.message_key?.split('.').pop() ||
        finding.id;
      out.push({
        key: `finding-${finding.id}`,
        label: finding.message || finding.message_key,
        status,
        reason: finding.explanation || null,
        explanation:
          status === 'unchecked'
            ? null
            : finding.explanation ||
              (FIELD_EXPLAIN_KEYS[fieldHint || '']
                ? t(FIELD_EXPLAIN_KEYS[fieldHint || ''])
                : null),
        tipKey: fieldHint ? STATIC_FIELD_TIPS[fieldHint] : undefined,
      });
    }

    if (out.length === 0) {
      out.push({
        key: 'overall',
        label: report.overallStatus,
        status:
          report.overallResult === 'pass'
            ? 'passed'
            : report.overallResult === 'critical'
              ? 'failed'
              : report.overallResult === 'warnings'
                ? 'uncertain'
                : 'unchecked',
        reason: report.summary,
      });
    }

    return out;
  }, [report, t]);

  const validated = rows.filter((r) => r.status === 'passed' || r.status === 'failed' || r.status === 'uncertain');
  const notValidated = rows.filter((r) => r.status === 'unchecked');

  const statusIcon = (status: ScopeRow['status']) => {
    switch (status) {
      case 'passed':
        return { icon: '✓', label: t('landingChat.status.passed'), css: 'is-passed' };
      case 'failed':
        return { icon: '!', label: t('landingChat.status.failed'), css: 'is-failed' };
      case 'uncertain':
        return { icon: '⚠', label: t('landingChat.status.uncertain'), css: 'is-uncertain' };
      default:
        return { icon: '–', label: t('landingChat.status.unchecked'), css: 'is-unchecked' };
    }
  };

  return (
    <div className="landing-validation-card" role="region" aria-label={t('landingChat.validationTitle')}>
      <header className="landing-validation-card__head">
        <h3>{t('landingChat.validationTitle')}</h3>
        {fileName && (
          <p className="landing-doc-card__file">
            {t('landingChat.uploadedFile')}: {fileName}
          </p>
        )}
        <p className="landing-validation-card__overall">{report.overallStatus}</p>
        <p>{report.summary}</p>
      </header>

      <section>
        <h4>{t('landingChat.validatedHeading')}</h4>
        {validated.length === 0 ? (
          <p className="landing-validation-card__empty">{t('landingChat.noneValidated')}</p>
        ) : (
          <ul className="landing-validation-card__list">
            {validated.map((row) => {
              const visual = statusIcon(row.status);
              return (
                <li key={row.key} className={`landing-validation-row ${visual.css}`}>
                  <span className="landing-validation-row__icon" aria-hidden="true">
                    {visual.icon}
                  </span>
                  <div className="landing-validation-row__body">
                    <div className="landing-validation-row__title">
                      <strong>{row.label}</strong>
                      <span className="landing-validation-row__status">{visual.label}</span>
                      {row.explanation && (
                        <FieldAiPopover label={row.label} explanation={row.explanation} />
                      )}
                    </div>
                    {row.reason && <p>{row.reason}</p>}
                    {row.tipKey && (
                      <p className="landing-doc-card__tip">{t(row.tipKey)}</p>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section>
        <h4>{t('landingChat.notValidatedHeading')}</h4>
        {notValidated.length === 0 ? (
          <p className="landing-validation-card__empty">{t('landingChat.noneSkipped')}</p>
        ) : (
          <ul className="landing-validation-card__list">
            {notValidated.map((row) => {
              const visual = statusIcon('unchecked');
              return (
                <li key={row.key} className={`landing-validation-row ${visual.css}`}>
                  <span className="landing-validation-row__icon" aria-hidden="true">
                    {visual.icon}
                  </span>
                  <div className="landing-validation-row__body">
                    <div className="landing-validation-row__title">
                      <strong>{row.label}</strong>
                      <span className="landing-validation-row__status">{visual.label}</span>
                    </div>
                    <p>
                      {row.reason ||
                        t('landingChat.unavailableReason', {
                          defaultValue:
                            'This check could not run because required documents or data are missing.',
                        })}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <p className="landing-validation-card__disclaimer">{t('landingChat.aiDoesNotDecide')}</p>
    </div>
  );
}
