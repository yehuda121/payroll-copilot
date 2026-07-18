export type AssistantSourceType =
  | 'legal_rule'
  | 'validation_report'
  | 'document'
  | 'contract'
  | 'attendance'
  | 'employee_context'
  | 'system';

export type AssistantGuardrailStatus =
  | 'passed'
  | 'answered_from_source'
  | 'limited_in_domain'
  | 'blocked_off_topic'
  | 'blocked_safety'
  | 'blocked'
  | 'limited';

export type AssistantSource = {
  title: string;
  type: AssistantSourceType;
  reference?: string;
};

export type AssistantChatRequest = {
  message: string;
  session_id?: string;
  document_ids?: string[];
  validation_run_id?: string;
  locale?: 'he' | 'en' | 'ar';
};

export type AssistantChatResponse = {
  answer: string;
  session_id: string;
  used_tools: string[];
  sources: AssistantSource[];
  confidence: number;
  requires_human_review: boolean;
  guardrail_status: AssistantGuardrailStatus;
  locale?: 'he' | 'en' | 'ar';
};

export type EmployeeAssistantChatRequest = {
  message: string;
  session_id?: string;
  locale?: 'he' | 'en' | 'ar';
  /** Availability hints only; the backend remains authoritative. */
  available_resource_keys?: string[];
};

export type EmployeeAssistantChatResponse = AssistantChatResponse & {
  context_updates: {
    profile: import('../services/employeePortal').EmployeeMe | null;
    payroll_months: import('../services/employeePortal').PayrollMonthsResponse[];
    payroll_month_details: import('../services/employeePortal').PayrollMonthDetail[];
    document_center: import('../services/employeePortal').EmployeeDocumentCenter | null;
    loaded_resource_keys: string[];
  };
};

export type AccountantEmployeeAssistantChatRequest = EmployeeAssistantChatRequest & {
  employee_number: string;
  /** Exact draft under review; prevents cross-document payroll context. */
  document_id?: string;
};

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
  prompt?: string;
  sources?: AssistantSource[];
  guardrailStatus?: AssistantGuardrailStatus;
};
