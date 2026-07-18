"""Server-side upload guardrails for guest documents."""

from __future__ import annotations

from payroll_copilot.application.exceptions import DocumentUploadRejectedError
from payroll_copilot.application.use_cases.documents import UploadDocumentCommand
from payroll_copilot.domain.enums import DocumentType
from payroll_copilot.infrastructure.config.settings import Settings

_ALLOWED_MIME_TYPES: dict[DocumentType, frozenset[str]] = {
    DocumentType.PAYSLIP: frozenset({"application/pdf", "image/png", "image/jpeg"}),
    DocumentType.ATTENDANCE: frozenset(
        {
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "text/csv",
            "application/csv",
        }
    ),
    DocumentType.CONTRACT: frozenset({"application/pdf"}),
    DocumentType.NATIONAL_ID: frozenset({"application/pdf", "image/png", "image/jpeg"}),
    DocumentType.ID_APPENDIX: frozenset({"application/pdf", "image/png", "image/jpeg"}),
    DocumentType.EMPLOYEE_EXCEL: frozenset(
        {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    ),
    DocumentType.BULK_PAYSLIP_PDF: frozenset({"application/pdf"}),
}

_INJECTION_PATTERNS = (
    b"ignore previous instructions",
    b"ignore all previous instructions",
    b"system prompt",
    b"jailbreak",
)


class DocumentUploadGuardrailService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def validate(self, command: UploadDocumentCommand) -> None:
        if not command.content:
            raise DocumentUploadRejectedError("Empty files cannot be uploaded.")

        max_size = self._settings.max_upload_size_mb * 1024 * 1024
        if command.document_type == DocumentType.BULK_PAYSLIP_PDF:
            max_size = self._settings.max_bulk_pdf_size_mb * 1024 * 1024
        if len(command.content) > max_size:
            raise DocumentUploadRejectedError(
                f"File exceeds the maximum allowed size of {max_size // (1024 * 1024)}MB."
            )

        allowed = _ALLOWED_MIME_TYPES.get(command.document_type)
        if allowed is not None and command.mime_type not in allowed:
            raise DocumentUploadRejectedError(
                f"Unsupported file type '{command.mime_type}' for {command.document_type.value}."
            )

        if command.mime_type == "application/pdf":
            self._validate_pdf(command.content)

        if command.mime_type in {"text/csv", "application/csv"}:
            self._validate_text_content(command.content)

    def _validate_pdf(self, content: bytes) -> None:
        if not content.startswith(b"%PDF"):
            raise DocumentUploadRejectedError("The uploaded PDF appears to be corrupted or invalid.")

        if b"/Encrypt" in content[:4096]:
            raise DocumentUploadRejectedError("Password-protected PDF files are not supported.")

    def _validate_text_content(self, content: bytes) -> None:
        lowered = content[:8000].lower()
        for pattern in _INJECTION_PATTERNS:
            if pattern in lowered:
                raise DocumentUploadRejectedError(
                    "The uploaded file contains unsupported instruction-like content."
                )
