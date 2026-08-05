"""Deterministic PDF extraction — shared SoT for all document upload/extract flows.

No OpenAI, LLM, agent, RAG, n8n, or OCR participates in this path.
"""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.services.deterministic_pdf.pdf_text_extractor import (
    extract_pdf_text_layer,
    is_pdf_bytes,
)
from payroll_copilot.application.services.deterministic_pdf.types import (
    DeterministicExtractionErrorCode,
    DeterministicExtractionResult,
    DeterministicExtractionStatus,
    EXTRACTOR_VERSION,
    ENGINE_NAME,
    NormalizedExtractedField,
)

__all__ = [
    "DeterministicExtractionErrorCode",
    "DeterministicExtractionResult",
    "DeterministicExtractionStatus",
    "DeterministicPdfDocumentExtractor",
    "ENGINE_NAME",
    "EXTRACTOR_VERSION",
    "NormalizedExtractedField",
    "extract_document_from_pdf",
    "extract_pdf_text_layer",
    "fields_to_dynamic_entries",
    "fields_to_fixed_structured",
    "is_pdf_bytes",
]

_SERVICE_EXPORTS = frozenset(
    {
        "DeterministicPdfDocumentExtractor",
        "extract_document_from_pdf",
        "fields_to_dynamic_entries",
        "fields_to_fixed_structured",
    }
)


def __getattr__(name: str) -> Any:
    if name in _SERVICE_EXPORTS:
        from payroll_copilot.application.services.deterministic_pdf import service as _service

        return getattr(_service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
