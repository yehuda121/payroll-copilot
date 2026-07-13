export type EmploymentType = 'full_time' | 'part_time' | 'contractor' | 'intern' | 'pre_intern';
export type SalaryType = 'monthly' | 'hourly';
export type EmployeeStatus = 'active' | 'on_leave' | 'terminated' | 'disabled';

/** Shape aligned with backend employee master data. */
export type EmployeeRecord = {
  id?: string;
  employeeNumber: string;
  fullName: string;
  firstName?: string;
  lastName?: string;
  email: string;
  department: string;
  departmentId?: string;
  employmentType: EmploymentType;
  salaryType: SalaryType;
  baseSalaryOrRate: number;
  status: EmployeeStatus;
  profileIncomplete?: boolean;
  nationalIdMasked?: string | null;
  contractStartDate?: string;
  contractEndDate?: string | null;
  metadata?: Record<string, unknown>;
};

export type EmployeeWritePayload = {
  employee_number?: string;
  first_name: string;
  last_name: string;
  employment_type: EmploymentType;
  salary_type: SalaryType;
  email?: string;
  national_id?: string;
  hourly_rate?: number | null;
  monthly_salary?: number | null;
  contract_start_date?: string;
  contract_end_date?: string | null;
  profile_incomplete?: boolean;
  status?: EmployeeStatus;
  metadata?: Record<string, unknown>;
};

export type DocumentTypeCatalogItem = {
  key: string;
  label: string;
  category: string;
  supports_period: boolean;
  supports_ocr: boolean;
  supports_parser: boolean;
  supports_validation_modules: string[];
  collection_key: string;
  sort_order: number;
};

export type ValidationModuleCatalogItem = {
  key: string;
  label: string;
  description: string;
  supported_document_types: string[];
  rule_categories: string[];
  enabled: boolean;
};

export type ExpectedDocumentAvailability =
  | 'available'
  | 'missing'
  | 'processing'
  | 'failed'
  | 'needs_review'
  | 'versioned';

export type EmployeeDocumentSlot = {
  typeKey: string;
  label: string;
  availability: ExpectedDocumentAvailability;
  periodYear?: number;
  periodMonth?: number;
};

export type EmployeeMonthSummary = {
  year: number;
  month: number;
  payslip: ExpectedDocumentAvailability;
  attendance: ExpectedDocumentAvailability;
  validationStatus: 'not_run' | 'passed' | 'warnings' | 'critical' | 'processing' | 'failed';
  missingDocuments: string[];
  warnings: string[];
};

export type AuditLogItem = {
  id: number;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: Record<string, unknown>;
  created_at: string | null;
};
