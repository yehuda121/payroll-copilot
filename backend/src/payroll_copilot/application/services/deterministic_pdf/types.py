"""Typed results for deterministic PDF document extraction (no AI / no OCR)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


EXTRACTOR_VERSION = "deterministic_pdf_v1"
ENGINE_NAME = "pymupdf_text"


class DeterministicExtractionStatus(StrEnum):
    COMPLETED = "completed"
    OCR_REQUIRED = "ocr_required"
    REJECTED = "rejected"
    FAILED = "failed"


class DeterministicExtractionErrorCode(StrEnum):
    NOT_PDF = "NOT_PDF"
    EMPTY_PDF = "EMPTY_PDF"
    ENCRYPTED_PDF = "ENCRYPTED_PDF"
    MALFORMED_PDF = "MALFORMED_PDF"
    OCR_REQUIRED = "OCR_REQUIRED"
    NO_USABLE_FIELDS = "NO_USABLE_FIELDS"
    UNSUPPORTED_DOCUMENT_TYPE = "UNSUPPORTED_DOCUMENT_TYPE"


@dataclass(frozen=True, slots=True)
class NormalizedExtractedField:
    key: str
    value: Any
    confidence: float | None = None
    source_text: str | None = None
    page: int | None = None
    status: str = "FOUND"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "source_text": self.source_text,
            "page": self.page,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class DeterministicExtractionResult:
    """Normalized extraction result — identical for identical PDF bytes."""

    status: DeterministicExtractionStatus
    document_type: str
    page_count: int
    page_texts: tuple[str, ...]
    raw_text: str
    fields: tuple[NormalizedExtractedField, ...]
    warnings: tuple[str, ...] = ()
    error_code: str | None = None
    error_message: str | None = None
    extractor_version: str = EXTRACTOR_VERSION
    engine: str = ENGINE_NAME
    structured: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status is DeterministicExtractionStatus.COMPLETED

    def field_map(self) -> dict[str, Any]:
        return {item.key: item.value for item in self.fields if item.value not in (None, "")}

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "document_type": self.document_type,
            "page_count": self.page_count,
            "raw_text": self.raw_text,
            "fields": [item.to_dict() for item in self.fields],
            "warnings": list(self.warnings),
            "error_code": self.error_code,
            "error_message": self.error_message,
            "extractor_version": self.extractor_version,
            "engine": self.engine,
            "structured": self.structured,
        }
