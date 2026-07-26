"""Domain enumerations."""

from enum import StrEnum


class UserRole(StrEnum):
    GUEST = "guest"
    EMPLOYEE = "employee"
    ACCOUNTANT = "accountant"
    ADMIN = "admin"
    SYSTEM = "system"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    INTERN = "intern"
    PRE_INTERN = "pre_intern"
    CONTRACTOR = "contractor"
    # Synthetic / extraction: present-but-unrecognized or missing on payslip mapping.
    # Never treat as equivalent to FULL_TIME. Not a persistence migration target.
    UNKNOWN = "unknown"


class SalaryType(StrEnum):
    HOURLY = "hourly"
    MONTHLY = "monthly"


class EmployeeStatus(StrEnum):
    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    TERMINATED = "terminated"
    DISABLED = "disabled"


class DocumentType(StrEnum):
    PAYSLIP = "payslip"
    ATTENDANCE = "attendance"
    CONTRACT = "contract"
    NATIONAL_ID = "national_id"
    ID_APPENDIX = "id_appendix"
    EMPLOYEE_EXCEL = "employee_excel"
    BULK_PAYSLIP_PDF = "bulk_payslip_pdf"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class RuleCategory(StrEnum):
    LEGAL = "legal"
    TAX = "tax"
    PENSION = "pension"
    OVERTIME = "overtime"
    VACATION = "vacation"
    TRANSPORTATION = "transportation"
    HOLIDAY = "holiday"
    DEPARTMENT = "department"
    CONTRACT = "contract"
    HISTORICAL = "historical"
    COMPANY = "company"
    SANITY = "sanity"


class FindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ValidationResult(StrEnum):
    PASS = "pass"
    WARNINGS = "warnings"
    CRITICAL = "critical"


class ValidationRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BatchJobStatus(StrEnum):
    QUEUED = "queued"
    SPLITTING = "splitting"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"


class AttendanceRecordType(StrEnum):
    VACATION = "vacation"
    SICK_LEAVE = "sick_leave"
    HOLIDAY = "holiday"
    WORK_DAY = "work_day"


class AttendanceSource(StrEnum):
    MANUAL = "manual"
    EMAIL_AGENT = "email_agent"
    ATTENDANCE_REPORT = "attendance_report"


class ReviewStatus(StrEnum):
    APPROVED = "approved"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"


class ConfidenceSource(StrEnum):
    OCR = "ocr"
    LLM = "llm"
    RULE = "rule"
    IDENTITY_MATCH = "identity_match"
    CONTRACT_RAG = "contract_rag"
    HISTORICAL = "historical"


class DiffProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SupportedLocale(StrEnum):
    HEBREW = "he"
    ENGLISH = "en"
    ARABIC = "ar"


class VacationSource(StrEnum):
    EMAIL = "email"
    MANUAL = "manual"


class VacationIntent(StrEnum):
    NEW = "new"
    UPDATE = "update"
    CANCEL = "cancel"
    UNKNOWN = "unknown"


class VacationReviewStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    REQUIRES_ATTENTION = "requires_attention"


class VacationAttentionCode(StrEnum):
    MISSING_EMPLOYEE_EMAIL = "MISSING_EMPLOYEE_EMAIL"
    MISSING_START_DATE = "MISSING_START_DATE"
    MISSING_END_DATE = "MISSING_END_DATE"
    INVALID_DATE = "INVALID_DATE"
    END_BEFORE_START = "END_BEFORE_START"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    EMPLOYEE_NOT_FOUND = "EMPLOYEE_NOT_FOUND"
    EMPLOYEE_AMBIGUOUS = "EMPLOYEE_AMBIGUOUS"
    OVERLAP = "OVERLAP"
    DUPLICATE_CONTENT = "DUPLICATE_CONTENT"
    AMBIGUOUS_UPDATE = "AMBIGUOUS_UPDATE"
    AMBIGUOUS_CANCEL = "AMBIGUOUS_CANCEL"
    UPDATE_PROPOSED = "UPDATE_PROPOSED"
    CANCEL_PROPOSED = "CANCEL_PROPOSED"


class LeaveStatusSource(StrEnum):
    MANUAL = "manual"
    VACATION_SYSTEM = "vacation_system"
    UNKNOWN = "unknown"


class EmailAutomationStatus(StrEnum):
    """Derived V1 status for org email vacation automation."""

    NOT_CONFIGURED = "not_configured"
    ACTIVE = "active"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class VacationPipelineEventType(StrEnum):
    EMAIL_OBSERVED = "EMAIL_OBSERVED"
    CLASSIFIED_VACATION = "CLASSIFIED_VACATION"
    CLASSIFIED_SICK_LEAVE = "CLASSIFIED_SICK_LEAVE"
    CLASSIFIED_OTHER = "CLASSIFIED_OTHER"
    CLASSIFIED_UNCERTAIN = "CLASSIFIED_UNCERTAIN"
    GUARDRAIL_REJECTED = "GUARDRAIL_REJECTED"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    VACATION_PERSISTED = "VACATION_PERSISTED"
    VACATION_REQUIRES_ATTENTION = "VACATION_REQUIRES_ATTENTION"
    SICK_LEAVE_PERSISTED = "SICK_LEAVE_PERSISTED"
    SICK_LEAVE_REQUIRES_ATTENTION = "SICK_LEAVE_REQUIRES_ATTENTION"
    MISSING_EMPLOYEE_EMAIL = "MISSING_EMPLOYEE_EMAIL"
    MISSING_START_DATE = "MISSING_START_DATE"
    MISSING_END_DATE = "MISSING_END_DATE"
    INVALID_DATE = "INVALID_DATE"
    EMPLOYEE_NOT_FOUND = "EMPLOYEE_NOT_FOUND"
    EMPLOYEE_AMBIGUOUS = "EMPLOYEE_AMBIGUOUS"
    OVERLAP_DETECTED = "OVERLAP_DETECTED"
    DUPLICATE_PROVIDER_MESSAGE = "DUPLICATE_PROVIDER_MESSAGE"
    DUPLICATE_CONTENT = "DUPLICATE_CONTENT"
    BACKEND_DELIVERY_FAILURE = "BACKEND_DELIVERY_FAILURE"
    NOTIFICATION_SUCCESS = "NOTIFICATION_SUCCESS"
    NOTIFICATION_FAILURE = "NOTIFICATION_FAILURE"


class SickLeaveSource(StrEnum):
    EMAIL = "email"
    MANUAL = "manual"


class SickLeaveIntent(StrEnum):
    NEW = "new"
    UPDATE = "update"
    CANCEL = "cancel"
    UNKNOWN = "unknown"


class SickLeaveReviewStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    REQUIRES_ATTENTION = "requires_attention"


class SickLeaveAttentionCode(StrEnum):
    MISSING_EMPLOYEE_EMAIL = "MISSING_EMPLOYEE_EMAIL"
    MISSING_START_DATE = "MISSING_START_DATE"
    MISSING_END_DATE = "MISSING_END_DATE"
    INVALID_DATE = "INVALID_DATE"
    END_BEFORE_START = "END_BEFORE_START"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    EMPLOYEE_NOT_FOUND = "EMPLOYEE_NOT_FOUND"
    EMPLOYEE_AMBIGUOUS = "EMPLOYEE_AMBIGUOUS"
    OVERLAP = "OVERLAP"
    DUPLICATE_CONTENT = "DUPLICATE_CONTENT"
    AMBIGUOUS_UPDATE = "AMBIGUOUS_UPDATE"
    AMBIGUOUS_CANCEL = "AMBIGUOUS_CANCEL"
    UPDATE_PROPOSED = "UPDATE_PROPOSED"
    CANCEL_PROPOSED = "CANCEL_PROPOSED"
