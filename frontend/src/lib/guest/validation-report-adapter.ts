import type { OverallStatusLabel } from '../../types/validation-report';
import type { ValidationFinding, ValidationRunResponse } from '../../types/api';
import type { TFunction } from 'i18next';

export function findingTitle(finding: ValidationFinding): string {
  return finding.message || finding.message_key.replaceAll('.', ' ').replaceAll('_', ' ');
}

export function mapOverallStatus(
  result: ValidationRunResponse['overall_result'],
  t: TFunction,
): OverallStatusLabel {
  switch (result) {
    case 'pass':
      return t('report.overallPassed');
    case 'warnings':
      return t('report.overallWarnings');
    case 'critical':
      return t('report.overallCritical');
    default:
      return t('report.overallPending');
  }
}

export type ChecklistTone = 'passed' | 'unable' | 'issue' | 'neutral';

export type ChecklistEvidence = {
  verified: string[];
  missing: string[];
  unableBecause?: string;
};

export type GuestChecklistItem = {
  id: string;
  tone: ChecklistTone;
  title: string;
  explanation: string;
  confidence: number | null;
  recommendation: string;
  legalReference: string | null;
  evidence: ChecklistEvidence;
  findingId?: string;
  ruleId?: string;
};

function documentTypeLabel(documentType: string, t: TFunction): string {
  switch (documentType) {
    case 'payslip':
      return t('report.docPayslip');
    case 'attendance':
      return t('report.docAttendance');
    case 'contract':
      return t('report.docContract');
    case 'national_id':
      return t('report.docNationalId');
    default:
      return t('report.docUnknown');
  }
}

function evidenceFromUploads(
  uploadedDocuments: ValidationRunResponse['uploaded_documents'],
  t: TFunction,
  unableBecause?: string | null,
): ChecklistEvidence {
  const verified = uploadedDocuments
    .filter((doc) => doc.uploaded)
    .map((doc) => documentTypeLabel(doc.document_type, t));
  const missing = uploadedDocuments
    .filter((doc) => !doc.uploaded)
    .map((doc) => documentTypeLabel(doc.document_type, t));
  return {
    verified,
    missing,
    unableBecause: unableBecause ?? undefined,
  };
}

export function buildChecklistItems(
  report: import('../../types/validation-report').GuestValidationReport,
  t: TFunction,
): GuestChecklistItem[] {
  const baseEvidence = evidenceFromUploads(report.uploadedDocuments, t);
  const items: GuestChecklistItem[] = [];

  for (const finding of report.findings) {
    const isMissingData =
      finding.message_key === 'validation.missing_data' || finding.severity === 'info';
    items.push({
      id: finding.id,
      tone: isMissingData
        ? 'unable'
        : finding.severity === 'critical'
          ? 'issue'
          : finding.severity === 'warning'
            ? 'unable'
            : 'unable',
      title: isMissingData ? t('report.statusUnable') : findingTitle(finding),
      explanation: finding.explanation || finding.message,
      confidence:
        typeof finding.confidence === 'number' && !Number.isNaN(finding.confidence)
          ? finding.confidence
          : null,
      recommendation: findingRecommendation(finding, t),
      legalReference: finding.legal_reference,
      evidence: evidenceFromUploads(
        report.uploadedDocuments,
        t,
        isMissingData ? finding.message || finding.explanation : undefined,
      ),
      findingId: finding.id,
      ruleId: finding.rule_id,
    });
  }

  for (const scopeItem of report.scope) {
    if (scopeItem.status === 'completed') {
      items.push({
        id: `scope-${scopeItem.key}`,
        tone: 'passed',
        title: scopeItem.label,
        explanation: scopeItem.reason || t('report.noIssues'),
        confidence: null,
        recommendation: '',
        legalReference: null,
        evidence: baseEvidence,
      });
      continue;
    }

    if (scopeItem.status === 'not_available' || scopeItem.status === 'partial') {
      items.push({
        id: `scope-${scopeItem.key}`,
        tone: 'unable',
        title: scopeItem.label,
        explanation: scopeItem.reason || t('report.statusUnable'),
        confidence: null,
        recommendation: '',
        legalReference: null,
        evidence: evidenceFromUploads(report.uploadedDocuments, t, scopeItem.reason),
      });
    }
  }

  return items;
}

export function buildValidationSummary(report: ValidationRunResponse, t: TFunction): string {
  const passed = report.checks_passed_count;
  const issues = report.findings.length;
  if (issues === 0) {
    return t('report.summaryClean', { count: passed });
  }
  return t('report.summaryIssues', { passed, issues, count: issues });
}

export function adaptValidationReport(
  response: ValidationRunResponse,
  t: TFunction,
): import('../../types/validation-report').GuestValidationReport {
  return {
    runId: response.id,
    documentId: response.document_id,
    overallResult: response.overall_result,
    overallStatus: mapOverallStatus(response.overall_result, t),
    summary: buildValidationSummary(response, t),
    validationConfidence: response.validation_confidence,
    confidenceExplanation: response.confidence_explanation,
    scope: response.validation_scope,
    uploadedDocuments: response.uploaded_documents,
    checksPassedCount: response.checks_passed_count,
    findings: response.findings,
    extractionConnected: response.extraction_connected,
  };
}

export function findingRecommendation(finding: ValidationFinding, t: TFunction): string {
  if (finding.severity === 'critical') {
    return t('report.recCritical');
  }
  if (finding.severity === 'warning') {
    return t('report.recWarning');
  }
  return t('report.recInfo');
}
