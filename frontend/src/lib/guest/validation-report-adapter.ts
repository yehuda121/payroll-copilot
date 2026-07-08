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
      return t('report.statusPassed');
    case 'warnings':
      return t('report.statusWarnings');
    case 'critical':
      return t('report.statusCritical');
    default:
      return t('report.statusPending');
  }
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
