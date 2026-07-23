/** Analytics API response types (Phase 1A backend contracts). */

export type SalaryMonthPoint = {
  period_year: number;
  period_month: number;
  net_salary: number | string | null;
  gross_salary: number | string | null;
  currency: string;
  document_id: string | null;
  extraction_id: string | null;
};

export type EmployeeSalaryAnalytics = {
  employee_id: string;
  organization_id: string;
  year: number;
  months: SalaryMonthPoint[];
  available_years: number[];
  documents_missing_period: number;
};

export type OutcomeMonthPoint = {
  period_year: number;
  period_month: number;
  documents_processed: number;
  success: number;
  review_required: number;
  failed: number;
};

export type ValidationFailureMonthPoint = {
  period_year: number;
  period_month: number;
  failure_count: number;
  runs_with_failures: number;
};

export type ErrorTypeBucket = {
  key: string;
  count: number;
  category: string | null;
};

export type ConfidenceMonthPoint = {
  period_year: number;
  period_month: number;
  average_confidence: number | null;
  sample_count: number;
};

export type OrgPayrollAnalytics = {
  organization_id: string;
  year: number;
  documents_by_month: OutcomeMonthPoint[];
  validation_failures_by_month: ValidationFailureMonthPoint[];
  error_type_distribution: ErrorTypeBucket[];
  top_validation_failures: ErrorTypeBucket[];
  average_confidence_by_month: ConfidenceMonthPoint[];
  documents_missing_period: number;
  available_years: number[];
};

export type AccountantCaseload = {
  payroll_accountant_id: string;
  employee_count: number;
};

export type OrganizationCensusSlice = {
  organization_id: string;
  employees_count: number;
  payroll_accountants_count: number;
  employees_without_payroll_accountant: number;
  employees_per_payroll_accountant: AccountantCaseload[];
};

export type AdminOrgCensus = {
  companies_count: number;
  employees_count: number;
  payroll_accountants_count: number;
  employees_without_payroll_accountant: number;
  employees_per_payroll_accountant: AccountantCaseload[];
  organizations: OrganizationCensusSlice[];
};

export type ConfidenceBucket = {
  label: string;
  min_inclusive: number;
  max_exclusive: number;
  count: number;
};

export type QualityMonthPoint = {
  period_year: number;
  period_month: number;
  documents_processed: number;
  extraction_attempted: number;
  extraction_success: number;
  extraction_success_rate: number | null;
  ocr_attempted: number;
  ocr_success: number;
  ocr_failed: number;
  validation_runs: number;
  validation_pass: number;
  validation_success_rate: number | null;
  average_confidence: number | null;
  confidence_sample_count: number;
  manual_review: number;
  manual_review_rate: number | null;
  failed_documents: number;
};

export type OrgQualityAnalytics = {
  organization_id: string;
  year: number;
  months: QualityMonthPoint[];
  confidence_distribution: ConfidenceBucket[];
  totals: QualityMonthPoint | null;
  documents_missing_period: number;
  available_years: number[];
};

export type AdminQualityAnalytics = {
  year: number;
  organizations_count: number;
  months: QualityMonthPoint[];
  confidence_distribution: ConfidenceBucket[];
  totals: QualityMonthPoint | null;
  organizations: OrgQualityAnalytics[];
  available_years: number[];
};
