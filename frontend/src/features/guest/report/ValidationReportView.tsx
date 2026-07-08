import { useTranslation } from 'react-i18next';
import type { GuestValidationReport } from '../../../types/validation-report';
import { findingRecommendation, findingTitle } from '../../../lib/guest/validation-report-adapter';
import { FindingExplainPanel } from './FindingExplainPanel';
import '../guest.css';

type ValidationReportProps = {
  report: GuestValidationReport;
  documentIds: string[];
  onAskFollowUp?: () => void;
};

export function ValidationReportView({ report, documentIds, onAskFollowUp }: ValidationReportProps) {
  const { t } = useTranslation();
  const grouped = {
    critical: report.findings.filter((f) => f.severity === 'critical'),
    warning: report.findings.filter((f) => f.severity === 'warning'),
    info: report.findings.filter((f) => f.severity === 'info'),
  };

  const unableItems = report.scope.filter((item) => item.status === 'not_available');

  const scopeStatusLabel = (status: string): string => {
    switch (status) {
      case 'completed':
        return t('report.scopeCompleted');
      case 'partial':
        return t('report.scopePartial');
      default:
        return t('report.scopeNotAvailable');
    }
  };

  const severityLabel = (severity: 'critical' | 'warning' | 'info'): string => {
    switch (severity) {
      case 'critical':
        return t('report.severityCritical');
      case 'warning':
        return t('report.severityWarning');
      default:
        return t('report.severityInfo');
    }
  };

  return (
    <div className="validation-report">
      <section className="validation-report__section">
        <h3>{t('report.overallStatus')}</h3>
        <div
          className={`validation-report__status validation-report__status--${report.overallStatus.replaceAll(' ', '-').toLowerCase()}`}
        >
          {report.overallStatus}
        </div>
      </section>

      <section className="validation-report__section">
        <h3>{t('report.scope')}</h3>
        <ul className="validation-report__scope-list">
          {report.scope.map((item) => (
            <li key={item.key}>
              <div className="validation-report__scope-row">
                <strong>{item.label}</strong>
                <span>{scopeStatusLabel(item.status)}</span>
              </div>
              {item.reason && <p>{item.reason}</p>}
            </li>
          ))}
        </ul>
      </section>

      <section className="validation-report__section">
        <h3>{t('report.uploadedDocuments')}</h3>
        <ul className="validation-report__docs-list">
          {report.uploadedDocuments.map((doc) => (
            <li key={doc.document_type}>
              <span>{doc.uploaded ? '✓' : '✗'}</span>
              <span>{doc.document_type.replaceAll('_', ' ')}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="validation-report__section">
        <h3>{t('report.summary')}</h3>
        <p>{report.summary}</p>
      </section>

      {report.validationConfidence !== null && (
        <section className="validation-report__section">
          <h3>{t('report.confidence')}</h3>
          <p className="validation-report__confidence">
            {Math.round(report.validationConfidence * 100)}%
          </p>
          {report.confidenceExplanation && <p>{report.confidenceExplanation}</p>}
        </section>
      )}

      <section className="validation-report__section">
        <h3>{t('report.successfullyValidated')}</h3>
        <p>{t('report.checksPassed', { count: report.checksPassedCount })}</p>
      </section>

      <section className="validation-report__section">
        <h3>{t('report.potentialIssues')}</h3>
        {report.findings.length === 0 ? (
          <p>{t('report.noIssues')}</p>
        ) : (
          <>
            {(['critical', 'warning', 'info'] as const).map((severity) =>
              grouped[severity].length > 0 ? (
                <div key={severity} className="validation-report__finding-group">
                  <h4>{severityLabel(severity)}</h4>
                  {grouped[severity].map((finding) => (
                    <article key={finding.id} className="validation-report__finding">
                      <header>
                        <strong>{findingTitle(finding)}</strong>
                      </header>
                      <p>{finding.explanation || finding.message}</p>
                      <p>
                        <strong>{t('common.recommendation')}:</strong>{' '}
                        {findingRecommendation(finding, t)}
                      </p>
                      {finding.legal_reference && (
                        <p>
                          <strong>{t('common.legalReference')}:</strong> {finding.legal_reference}
                        </p>
                      )}
                      <FindingExplainPanel
                        findingId={finding.id}
                        ruleId={finding.rule_id}
                        validationRunId={report.runId}
                        documentIds={documentIds}
                      />
                    </article>
                  ))}
                </div>
              ) : null,
            )}
          </>
        )}
      </section>

      <section className="validation-report__section">
        <h3>{t('report.unableToValidate')}</h3>
        {unableItems.length === 0 ? (
          <p>{t('report.allAreasEvaluated')}</p>
        ) : (
          <ul className="validation-report__unable-list">
            {unableItems.map((item) => (
              <li key={item.key}>
                <strong>{item.label}</strong>
                <p>{item.reason}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      {onAskFollowUp && (
        <div className="validation-report__actions">
          <button type="button" className="btn btn--secondary" onClick={onAskFollowUp}>
            {t('report.askFollowUp')}
          </button>
        </div>
      )}
    </div>
  );
}
