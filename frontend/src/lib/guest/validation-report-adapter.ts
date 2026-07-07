import type { ValidationRunResponse } from '../../types/api';
import type { GuestValidationReport, OverallStatusLabel } from '../../types/validation-report';

const MESSAGE_LABELS: Record<string, string> = {
  'overtime.exceeds_limit': 'Overtime exceeds allowed limit',
  'overtime.rate_mismatch': 'Overtime rate mismatch',
  'minimum_wage.below_threshold': 'Below minimum wage threshold',
  'pension.contribution_low': 'Pension contribution below expected level',
};

export function findingTitle(messageKey: string, _ruleId: string): string {
  return MESSAGE_LABELS[messageKey] ?? messageKey.replaceAll('.', ' ').replaceAll('_', ' ');
}

export function mapOverallStatus(result: ValidationRunResponse['overall_result']): OverallStatusLabel {
  switch (result) {
    case 'pass':
      return 'Passed';
    case 'warnings':
      return 'Passed with Warnings';
    case 'critical':
      return 'Action Required';
    default:
      return 'Pending';
  }
}

export function buildValidationSummary(report: ValidationRunResponse): string {
  const passed = report.checks_passed_count;
  const issues = report.findings.length;
  if (issues === 0) {
    return `${passed} payroll rule checks completed with no potential issues identified.`;
  }
  return `${passed} payroll rule checks completed. ${issues} potential issue${issues === 1 ? '' : 's'} require review.`;
}

export function adaptValidationReport(response: ValidationRunResponse): GuestValidationReport {
  return {
    runId: response.id,
    documentId: response.document_id,
    overallStatus: mapOverallStatus(response.overall_result),
    summary: buildValidationSummary(response),
    validationConfidence: response.validation_confidence,
    confidenceExplanation: response.confidence_explanation,
    scope: response.validation_scope,
    uploadedDocuments: response.uploaded_documents,
    checksPassedCount: response.checks_passed_count,
    findings: response.findings,
    extractionConnected: response.extraction_connected,
  };
}

export function findingRecommendation(finding: ValidationRunResponse['findings'][number]): string {
  if (finding.severity === 'critical') {
    return 'Review this item with your payroll administrator before approving payment.';
  }
  if (finding.severity === 'warning') {
    return 'Verify the payslip detail and supporting records for this line item.';
  }
  return 'Review for completeness and keep supporting records on file.';
}
