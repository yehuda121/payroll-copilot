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


class PayslipParserTimeoutError(PayslipParserError):
    def __init__(self, message: str = "Payslip parser timed out.") -> None:
        super().__init__(message, code="parser_timeout")
