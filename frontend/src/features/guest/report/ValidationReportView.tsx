import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { GuestValidationReport } from '../../../types/validation-report';
import { buildChecklistItems } from '../../../lib/guest/validation-report-adapter';
import { ChecklistItemCard } from '../../../components/ui/ChecklistItemCard';
import { ConfidenceMeter } from '../../../components/ui/ConfidenceMeter';
import { SummaryCards } from '../../../components/ui/SummaryCards';
import { FindingExplainPanel } from './FindingExplainPanel';
import '../guest.css';

type ValidationReportProps = {
  report: GuestValidationReport;
  documentIds: string[];
  onAskFollowUp?: () => void;
};

export function ValidationReportView({ report, documentIds, onAskFollowUp }: ValidationReportProps) {
  const { t } = useTranslation();
  const checklist = useMemo(() => buildChecklistItems(report, t), [report, t]);

  const warningCount = report.findings.filter((f) => f.severity === 'warning').length;
  const issueCount = report.findings.filter((f) => f.severity === 'critical').length;
  const documentsProcessed = report.uploadedDocuments.filter((doc) => doc.uploaded).length;

  const summaryItems: Array<{
    id: string;
    label: string;
    value: string;
    tone?: 'passed' | 'unable' | 'issue' | 'neutral';
  }> = [
    {
      id: 'docs',
      label: t('report.documentsProcessed'),
      value: String(documentsProcessed),
    },
    {
      id: 'passed',
      label: t('report.passedChecks'),
      value: String(report.checksPassedCount),
      tone: 'passed',
    },
    {
      id: 'warnings',
      label: t('report.warnings'),
      value: String(warningCount),
      tone: warningCount > 0 ? 'unable' : undefined,
    },
    {
      id: 'issues',
      label: t('report.issues'),
      value: String(issueCount),
      tone: issueCount > 0 ? 'issue' : undefined,
    },
  ];

  if (report.validationConfidence !== null) {
    summaryItems.push({
      id: 'confidence',
      label: t('report.overallConfidence'),
      value: `${Math.round(report.validationConfidence * 100)}%`,
    });
  }

  return (
    <div className="validation-report">
      <SummaryCards title={t('report.summaryTitle')} items={summaryItems} />

      <section className="validation-report__section">
        <div
          className={`validation-report__status validation-report__status--${
            report.overallResult === 'critical'
              ? 'action-required'
              : report.overallResult === 'warnings'
                ? 'passed-with-warnings'
                : 'passed'
          }`}
        >
          {report.overallStatus}
        </div>
        <p>{report.summary}</p>
        {report.confidenceExplanation && (
          <p className="validation-report__note" role="status">
            {report.confidenceExplanation}
          </p>
        )}
        {report.validationConfidence !== null && (
          <ConfidenceMeter
            value={report.validationConfidence}
            label={t('report.overallConfidence')}
          />
        )}
      </section>

      <section className="validation-report__section" aria-label={t('report.checklistTitle')}>
        <h3>{t('report.checklistTitle')}</h3>
        {checklist.length === 0 ? (
          <p>{t('report.noIssues')}</p>
        ) : (
          <div className="validation-report__checklist">
            {checklist.map((item) => (
              <ChecklistItemCard
                key={item.id}
                item={item}
                details={
                  item.ruleId && item.findingId ? (
                    <FindingExplainPanel
                      findingId={item.findingId}
                      ruleId={item.ruleId}
                      validationRunId={report.runId}
                      documentIds={documentIds}
                      autoLoad
                    />
                  ) : null
                }
              />
            ))}
          </div>
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
