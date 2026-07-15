"""Application-layer exceptions."""

from __future__ import annotations

from uuid import UUID


class DocumentNotFoundError(Exception):
    def __init__(self, document_id: UUID) -> None:
        self.document_id = document_id
        super().__init__(f"Document {document_id} not found")


class DocumentUploadRejectedError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class OcrError(Exception):
    """Base OCR application error (generic text extraction only)."""

    def __init__(self, message: str, *, code: str = "ocr_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class OcrUnsupportedFileError(OcrError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="unsupported_file")


class OcrEmptyDocumentError(OcrError):
    def __init__(self, message: str = "Document is empty.") -> None:
        super().__init__(message, code="empty_document")


class OcrCorruptedDocumentError(OcrError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="corrupted_document")


class OcrProviderError(OcrError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="ocr_failure")


class OcrTimeoutError(OcrError):
    def __init__(self, message: str = "OCR processing timed out.") -> None:
        super().__init__(message, code="ocr_timeout")


class OcrLanguageNotSupportedError(OcrError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="language_not_supported")


class OcrProviderUnavailableError(OcrError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="provider_unavailable")


class PayslipParserError(Exception):
    """Base AI payslip parser error (extraction only — no validation)."""

    def __init__(self, message: str, *, code: str = "parser_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class PayslipParserEmptyOcrError(PayslipParserError):
    def __init__(self, message: str = "OCR text is empty; nothing to parse.") -> None:
        super().__init__(message, code="empty_ocr")


class PayslipParserUnavailableError(PayslipParserError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="parser_unavailable")


class PayslipParserJsonError(PayslipParserError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="invalid_json")


class PayslipParserSchemaError(PayslipParserError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="schema_validation_failed")


class PayslipParserSemanticError(PayslipParserSchemaError):
    """Valid JSON that is structurally/semantically unusable for payslip fields."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "semantic_invalid",
        warning_code: str | None = None,
    ) -> None:
        PayslipParserError.__init__(self, message, code="semantic_validation_failed")
        self.category = category
        self.warning_code = warning_code or "parser_semantic_invalid"


class PayslipParserTimeoutError(PayslipParserError):
    def __init__(self, message: str = "Payslip parser timed out.") -> None:
        super().__init__(message, code="parser_timeout")


class EmployeeAuthError(Exception):
    """Authenticated employee resolution / authorization failure."""

    def __init__(self, message: str, *, code: str, status_code: int = 403) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class DuplicatePayslipPeriodError(Exception):
    def __init__(
        self,
        *,
        existing_document_id: UUID,
        existing_version: int | None,
        uploaded_at: str | None,
    ) -> None:
        self.code = "duplicate_payslip_period"
        self.existing_document_id = existing_document_id
        self.existing_version = existing_version
        self.uploaded_at = uploaded_at
        super().__init__("A payslip already exists for this employee and payroll period.")


class DocumentNotOwnedError(Exception):
    def __init__(self, document_id: UUID) -> None:
        self.document_id = document_id
        self.code = "document_not_owned"
        super().__init__(f"Document {document_id} is not owned by the authenticated employee")


class CorrectionNotAllowedError(Exception):
    def __init__(self, message: str = "Correction is not allowed for this document.") -> None:
        self.code = "correction_not_allowed"
        self.message = message
        super().__init__(message)


class ConfirmationBlockedError(Exception):
    """Blocks employee confirmation / validation when trusted identity or period fails."""

    def __init__(self, *, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class ExtractionNotConfirmedError(Exception):
    def __init__(self, message: str = "Extraction must be confirmed before validation.") -> None:
        self.code = "extraction_not_confirmed"
        self.message = message
        super().__init__(message)
