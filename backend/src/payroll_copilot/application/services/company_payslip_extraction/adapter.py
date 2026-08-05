"""Adapt company-registry payslip extraction into Payroll Copilot Document Model types."""

from __future__ import annotations

import logging
from typing import Any

from payroll_copilot.application.services.company_payslip_extraction.registry import (
    extract as registry_extract,
)
from payroll_copilot.application.services.deterministic_pdf.types import (
    DeterministicExtractionErrorCode,
    DeterministicExtractionResult,
    DeterministicExtractionStatus,
    NormalizedExtractedField,
)
from payroll_copilot.application.services.dynamic_document import (
    DynamicDocumentEntry,
    new_entry,
    resolve_canonical_key,
)
from payroll_copilot.domain.enums import DocumentType

logger = logging.getLogger(__name__)

DEFAULT_COMPANY_KEY = "primary_company"
COMPANY_PAYSLIP_EXTRACTOR_VERSION = "company_payslip_v1"
COMPANY_PAYSLIP_ENGINE = "company_payslip_pdfplumber"

_CONFIDENCE_MAP: dict[str, float] = {
    "high": 0.92,
    "medium": 0.75,
    "low": 0.45,
    "unknown": 0.30,
    "ok": 0.85,
}


def _confidence_to_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
        return value if 0.0 <= value <= 1.0 else None
    text = str(raw).strip().lower()
    return _CONFIDENCE_MAP.get(text)


def _entry_usable(entry: dict[str, Any]) -> bool:
    name = str(entry.get("name") or "").strip()
    value = entry.get("value")
    if not name:
        return False
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    status = str(entry.get("status") or "").strip().lower()
    if status and status not in {"ok", "partial", ""}:
        # Keep ok/partial/blank; drop explicit rejects.
        if status in {"reject", "rejected", "error", "bad"}:
            return False
    return True


def paystub_entries_to_dynamic_entries(
    paystubs: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    source: str = COMPANY_PAYSLIP_ENGINE,
) -> list[DynamicDocumentEntry]:
    """Convert company extractor paystub entries into DynamicDocumentEntry rows."""
    out: list[DynamicDocumentEntry] = []
    for stub in paystubs:
        index = stub.get("paystub_index")
        section = f"paystub_{index}" if index is not None else None
        for raw in stub.get("entries") or []:
            if not isinstance(raw, dict) or not _entry_usable(raw):
                continue
            name = str(raw.get("name") or "").strip()
            value = raw.get("value")
            conf = _confidence_to_float(raw.get("confidence"))
            source_text = raw.get("raw") if isinstance(raw.get("raw"), str) else None
            bbox = raw.get("bbox")
            page = None
            if isinstance(bbox, (list, tuple)) and len(bbox) >= 1:
                # bbox is page-local; page index is not always present — leave None.
                page = None
            out.append(
                new_entry(
                    key=name,
                    value=value,
                    confidence=conf,
                    page=page,
                    source=source,
                    source_text=source_text,
                    section=section,
                    kind="document_field",
                )
            )
    return out


def paystub_entries_to_normalized_fields(
    paystubs: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    paystub_index: int = 0,
) -> list[NormalizedExtractedField]:
    """Map Hebrew/English document labels onto canonical NormalizedExtractedField keys.

    Canonical fields are built from exactly one paystub (default index 0 for
    single-document review). Labels from other paystubs are never merged in —
    a missing field on the selected stub stays missing.

    Within that stub, first matching label wins per canonical key.
    """
    if not paystubs:
        return []
    if paystub_index < 0 or paystub_index >= len(paystubs):
        return []

    stub = paystubs[paystub_index]
    seen: set[str] = set()
    fields: list[NormalizedExtractedField] = []
    for raw in stub.get("entries") or []:
        if not isinstance(raw, dict) or not _entry_usable(raw):
            continue
        label = str(raw.get("name") or "").strip()
        canonical = resolve_canonical_key(label)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        fields.append(
            NormalizedExtractedField(
                key=canonical,
                value=raw.get("value"),
                confidence=_confidence_to_float(raw.get("confidence")),
                source_text=raw.get("raw") if isinstance(raw.get("raw"), str) else label,
                page=None,
                status="FOUND",
            )
        )
    return fields


def extract_payslip_document(
    content: bytes,
    *,
    company_key: str = DEFAULT_COMPANY_KEY,
    document_type: DocumentType | str = DocumentType.PAYSLIP,
    filename: str | None = None,
    mime_type: str | None = None,
) -> DeterministicExtractionResult:
    """Run company-registry extraction and adapt into DeterministicExtractionResult."""
    _ = filename, mime_type
    dtype = (
        document_type.value
        if isinstance(document_type, DocumentType)
        else str(document_type).strip().lower()
    )
    try:
        payload = registry_extract(content, company_key=company_key, debug_layout=False)
    except Exception as exc:  # noqa: BLE001 — surface as FAILED with message
        logger.warning("Company payslip extraction failed: %s", exc, exc_info=True)
        message = str(exc).lower()
        if "encrypted" in message or "password" in message:
            return DeterministicExtractionResult(
                status=DeterministicExtractionStatus.REJECTED,
                document_type=dtype,
                page_count=0,
                page_texts=(),
                raw_text="",
                fields=(),
                warnings=(),
                error_code=DeterministicExtractionErrorCode.ENCRYPTED_PDF.value,
                error_message="PDF is encrypted and cannot be extracted.",
                structured={},
                extractor_version=COMPANY_PAYSLIP_EXTRACTOR_VERSION,
                engine=COMPANY_PAYSLIP_ENGINE,
            )
        return DeterministicExtractionResult(
            status=DeterministicExtractionStatus.FAILED,
            document_type=dtype,
            page_count=0,
            page_texts=(),
            raw_text="",
            fields=(),
            warnings=("company_extractor_error",),
            error_code=DeterministicExtractionErrorCode.NO_USABLE_FIELDS.value,
            error_message=f"Company payslip extraction failed: {exc}",
            structured={
                "extractor_meta": {
                    "extractor_version": COMPANY_PAYSLIP_EXTRACTOR_VERSION,
                    "engine": COMPANY_PAYSLIP_ENGINE,
                    "company_key": company_key,
                }
            },
            extractor_version=COMPANY_PAYSLIP_EXTRACTOR_VERSION,
            engine=COMPANY_PAYSLIP_ENGINE,
        )

    raw_text = str(payload.get("raw_text") or "")
    paystubs = list(payload.get("paystubs") or [])
    page_texts = tuple(
        part.strip() for part in raw_text.split("\n\n") if part.strip()
    ) or ((raw_text,) if raw_text.strip() else ())
    page_count = len(page_texts)

    dynamic_entries = paystub_entries_to_dynamic_entries(paystubs)
    # Single-document review: canonical field_map from paystub 0 only.
    # All stubs remain in structured.paystubs / dynamic_entries.
    canonical_paystub_index = 0
    fields = paystub_entries_to_normalized_fields(
        paystubs, paystub_index=canonical_paystub_index
    )
    extractor_meta = {
        "extractor_version": COMPANY_PAYSLIP_EXTRACTOR_VERSION,
        "engine": COMPANY_PAYSLIP_ENGINE,
        "company_key": company_key,
        "extraction_mode": payload.get("extraction_mode"),
        "paystub_count": len(paystubs),
        "canonical_paystub_index": canonical_paystub_index,
        "field_count": len(fields),
        "diagnostics": payload.get("diagnostics") or {},
    }

    if not dynamic_entries and not fields:
        # Empty text layer with no layout → OCR may be required.
        if not raw_text.strip():
            return DeterministicExtractionResult(
                status=DeterministicExtractionStatus.OCR_REQUIRED,
                document_type=dtype,
                page_count=page_count,
                page_texts=page_texts,
                raw_text=raw_text,
                fields=(),
                warnings=("no_usable_word_coordinates", "empty_text_layer"),
                error_code=DeterministicExtractionErrorCode.OCR_REQUIRED.value,
                error_message="PDF has no usable text layer for deterministic extraction.",
                structured={"extractor_meta": extractor_meta},
                extractor_version=COMPANY_PAYSLIP_EXTRACTOR_VERSION,
                engine=COMPANY_PAYSLIP_ENGINE,
            )
        return DeterministicExtractionResult(
            status=DeterministicExtractionStatus.FAILED,
            document_type=dtype,
            page_count=page_count,
            page_texts=page_texts,
            raw_text=raw_text,
            fields=(),
            warnings=("no_fields_matched",),
            error_code=DeterministicExtractionErrorCode.NO_USABLE_FIELDS.value,
            error_message="No usable fields could be extracted from the payslip PDF.",
            structured={
                "dynamic_entries": [],
                "extractor_meta": extractor_meta,
                "paystubs": paystubs,
            },
            extractor_version=COMPANY_PAYSLIP_EXTRACTOR_VERSION,
            engine=COMPANY_PAYSLIP_ENGINE,
        )

    structured: dict[str, Any] = {
        "dynamic_entries": [entry.to_dict() for entry in dynamic_entries],
        "extractor_meta": extractor_meta,
        "paystubs": [
            {
                "paystub_index": stub.get("paystub_index"),
                "employee_name": stub.get("employee_name"),
                "fields": stub.get("fields") or {},
            }
            for stub in paystubs
        ],
    }

    warnings: tuple[str, ...] = ()
    if len(paystubs) > 1:
        warnings = (
            f"multi_payslip_count:{len(paystubs)}",
            (
                "canonical_fields_from_paystub_index:"
                f"{canonical_paystub_index};other_paystubs_not_merged"
            ),
        )

    return DeterministicExtractionResult(
        status=DeterministicExtractionStatus.COMPLETED,
        document_type=dtype,
        page_count=page_count,
        page_texts=page_texts,
        raw_text=raw_text,
        fields=tuple(fields),
        warnings=warnings,
        error_code=None,
        error_message=None,
        structured=structured,
        extractor_version=COMPANY_PAYSLIP_EXTRACTOR_VERSION,
        engine=COMPANY_PAYSLIP_ENGINE,
    )
