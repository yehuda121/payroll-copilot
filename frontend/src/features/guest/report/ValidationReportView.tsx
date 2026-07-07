import type { GuestValidationReport } from '../../../types/validation-report';
import { findingRecommendation, findingTitle } from '../../../lib/guest/validation-report-adapter';
import { FindingExplainPanel } from './FindingExplainPanel';
import '../guest.css';

type ValidationReportProps = {
  report: GuestValidationReport;
  documentIds: string[];
  onAskFollowUp?: () => void;
};

function scopeStatusLabel(status: string): string {
  switch (status) {
    case 'completed':
      return 'Completed';
    case 'partial':
      return 'Partial';
    default:
      return 'Not available';
  }
}

export function ValidationReportView({ report, documentIds, onAskFollowUp }: ValidationReportProps) {
  const grouped = {
    critical: report.findings.filter((f) => f.severity === 'critical'),
    warning: report.findings.filter((f) => f.severity === 'warning'),
    info: report.findings.filter((f) => f.severity === 'info'),
  };

  const unableItems = report.scope.filter((item) => item.status === 'not_available');

  return (
    <div className="validation-report">
      <section className="validation-report__section">
        <h3>Overall Status</h3>
        <div className={`validation-report__status validation-report__status--${report.overallStatus.replaceAll(' ', '-').toLowerCase()}`}>
          {report.overallStatus}
        </div>
      </section>

      <section className="validation-report__section">
        <h3>Validation Scope</h3>
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
        <h3>Uploaded Documents</h3>
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
        <h3>Validation Summary</h3>
        <p>{report.summary}</p>
      </section>

      {report.validationConfidence !== null && (
        <section className="validation-report__section">
          <h3>Validation Confidence</h3>
          <p className="validation-report__confidence">
            {Math.round(report.validationConfidence * 100)}%
          </p>
          {report.confidenceExplanation && <p>{report.confidenceExplanation}</p>}
        </section>
      )}

      <section className="validation-report__section">
        <h3>Successfully Validated</h3>
        <p>
          {report.checksPassedCount} payroll rule check
          {report.checksPassedCount === 1 ? '' : 's'} completed with no potential issue
          {report.checksPassedCount === 1 ? '' : 's'}.
        </p>
      </section>

      <section className="validation-report__section">
        <h3>Potential Issues</h3>
        {report.findings.length === 0 ? (
          <p>No potential issues were identified in the completed rule checks.</p>
        ) : (
          <>
            {(['critical', 'warning', 'info'] as const).map((severity) =>
              grouped[severity].length > 0 ? (
                <div key={severity} className="validation-report__finding-group">
                  <h4>{severity.toUpperCase()}</h4>
                  {grouped[severity].map((finding) => (
                    <article key={finding.id} className="validation-report__finding">
                      <header>
                        <strong>{findingTitle(finding.message_key, finding.rule_id)}</strong>
                      </header>
                      <p>{finding.message_key.replaceAll('.', ' ')}</p>
                      <p>
                        <strong>Recommendation:</strong> {findingRecommendation(finding)}
                      </p>
                      {finding.legal_reference && (
                        <p>
                          <strong>Legal reference:</strong> {finding.legal_reference}
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
        <h3>Unable to Validate</h3>
        {unableItems.length === 0 ? (
          <p>All currently supported validation areas were evaluated.</p>
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
            Ask a follow-up question
          </button>
        </div>
      )}
    </div>
  );
}
