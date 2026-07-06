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


class SalaryType(StrEnum):
    HOURLY = "hourly"
    MONTHLY = "monthly"


class EmployeeStatus(StrEnum):
    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    TERMINATED = "terminated"


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
