"""Canonical Projector — DocumentInstance (L1) → StructuredPayslipParse (L2).

Single projection implementation for guest confirm, employee/batch extract,
template apply, and AI-teacher enrichment. Reuses ``resolve_canonical_key``;
does not redefine synonym tables.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from payroll_copilot.application.ports.payslip_parser import (
    PAYSLIP_FIELD_KEYS,
    ExtractedField,
    FieldExtractionStatus,
    StructuredPayslipParse,
)
from payroll_copilot.application.services.dynamic_document import (
    DynamicDocumentEntry,
    is_document_origin_entry,
    resolve_canonical_key,
)
from payroll_copilot.domain.document_model import (
    DOCUMENT_BUILDER_ID,
    DOCUMENT_MODEL_SCHEMA_VERSION,
    DocumentEvidenceRef,
    DocumentInstance,
    DocumentLayoutRef,
    DocumentSlot,
    empty_document_instance,
)

_CONFIDENCE_BAND: dict[str, float] = {
    "high": 0.9,
    "medium": 0.7,
    "low": 0.4,
}

_SAFE_KEY_RE = re.compile(r"[^\w\u0590-\u05FF\u0600-\u06FF]+")


def project_document_to_structured(
    instance: DocumentInstance | dict[str, Any] | None,
    *,
    parser_method: str = "document_projector_v1",
) -> tuple[StructuredPayslipParse, list[str]]:
    """Project L1 DocumentInstance into L2 StructuredPayslipParse.

    Slot → canonical routing:
    1. ``slot.metadata["canonical_key"]`` when set (template / AI stamped)
    2. else ``resolve_canonical_key(slot.label)``
    3. else ``additional_fields`` under a safe key

    Evidence (``candidate_ids``, bbox, page) is preserved on ExtractedField.
    """
    doc = _as_instance(instance)
    structured: dict[str, Any] = {}
    additional: dict[str, ExtractedField] = {}
    warnings: list[str] = []
    seen_canonical: set[str] = set()

    for slot in doc.slots:
        if not _slot_usable(slot):
            continue
        label = (slot.label or "").strip()
        stamped = slot.metadata.get("canonical_key") if isinstance(slot.metadata, dict) else None
        canonical: str | None = None
        if isinstance(stamped, str) and stamped.strip():
            canonical = stamped.strip()
        elif label:
            canonical = resolve_canonical_key(label)

        field = _slot_to_extracted_field(slot, parser_method=parser_method)

        if canonical and canonical in PAYSLIP_FIELD_KEYS:
            if canonical in seen_canonical:
                warnings.append(f"duplicate_canonical:{canonical}")
                continue
            seen_canonical.add(canonical)
            structured[canonical] = field
        elif canonical in {"national_id", "total_deductions"}:
            additional[canonical] = field
        else:
            display = label or "unknown"
            safe_key = _SAFE_KEY_RE.sub("_", display).strip("_") or "unknown"
            if safe_key in additional:
                safe_key = f"{safe_key}_{slot.id[:8]}"
            additional[safe_key] = field
            if label:
                warnings.append(f"unmapped_label:{label}")
            else:
                warnings.append("unmapped_unlabeled_value")

    for key in PAYSLIP_FIELD_KEYS:
        if key not in structured:
            structured[key] = ExtractedField(status=FieldExtractionStatus.MISSING)

    structured["additional_fields"] = additional
    parsed = StructuredPayslipParse.model_validate(structured)
    return parsed, list(dict.fromkeys(warnings))


def project_document_dict_to_structured_data(
    document_model: dict[str, Any] | None,
    *,
    parser_method: str = "document_projector_v1",
) -> tuple[dict[str, Any], list[str]]:
    """Project and return JSON-serializable structured_data dict."""
    parsed, warnings = project_document_to_structured(
        document_model, parser_method=parser_method
    )
    return parsed.model_dump(mode="json"), warnings


def document_instance_from_dynamic_entries(
    entries: list[DynamicDocumentEntry],
) -> DocumentInstance:
    """Bridge guest review entries into a DocumentInstance for shared projection."""
    slots: list[DocumentSlot] = []
    for entry in entries:
        if not is_document_origin_entry(entry):
            continue
        conf = entry.confidence
        band: str | None = None
        if conf is not None:
            if conf >= 0.85:
                band = "high"
            elif conf >= 0.6:
                band = "medium"
            elif conf >= 0.0:
                band = "low"
        slots.append(
            DocumentSlot(
                id=str(entry.id),
                kind=entry.kind or "field",
                label=entry.key.strip() or None,
                value=entry.value,
                confidence=band,
                layout=DocumentLayoutRef(
                    page=entry.page,
                    section_id=entry.section,
                    table_id=entry.table_id,
                    column_index=None,
                    reading_index=entry.row_index,
                ),
                evidence=DocumentEvidenceRef(),
                metadata={"source": entry.source, "guest_entry": True},
            )
        )
    return DocumentInstance(
        schema_version=DOCUMENT_MODEL_SCHEMA_VERSION,
        builder="guest_entries_bridge_v1",
        slots=slots,
        slot_count=len(slots),
        layout_metadata={"bridge": "dynamic_entries"},
    )


def dynamic_entries_from_document(
    instance: DocumentInstance | dict[str, Any] | None,
) -> list[DynamicDocumentEntry]:
    """Optional UI bridge: DocumentInstance slots → guest DynamicDocumentEntry list."""
    doc = _as_instance(instance)
    out: list[DynamicDocumentEntry] = []
    for slot in doc.slots:
        if not _slot_usable(slot) and not (slot.label and slot.kind == "unresolved_label"):
            if not (slot.label or "").strip() and slot.value in (None, ""):
                continue
        key = (slot.label or "").strip() or f"slot_{slot.id[:8]}"
        out.append(
            DynamicDocumentEntry(
                id=slot.id,
                key=key,
                value=slot.value,
                confidence=_band_to_float(slot.confidence),
                page=slot.layout.page,
                source="document_model",
                source_text=slot.label,
                section=slot.layout.section_id,
                kind=slot.kind,
                table_id=slot.layout.table_id,
                row_index=slot.layout.reading_index,
                column=str(slot.layout.column_index)
                if slot.layout.column_index is not None
                else None,
            )
        )
    return out


def enrich_document_from_structured(
    instance: DocumentInstance,
    parsed: StructuredPayslipParse,
    *,
    candidate_index: dict[str, dict[str, Any]] | None = None,
) -> DocumentInstance:
    """Stamp AI/template canonical bindings onto document slots (selectors + values).

    Does not discard existing slots. For each FOUND/UNCERTAIN canonical field with
    ``candidate_ids``, matching slots receive ``metadata.canonical_key``. Missing
    slots are created from the candidate_index when available.
    """
    doc = deepcopy(instance)
    index = candidate_index or {}
    slots_by_cand: dict[str, list[DocumentSlot]] = {}
    for slot in doc.slots:
        for cid in slot.evidence.candidate_ids:
            slots_by_cand.setdefault(str(cid), []).append(slot)

    for key in PAYSLIP_FIELD_KEYS:
        field: ExtractedField = getattr(parsed, key)
        if field.status not in {
            FieldExtractionStatus.FOUND,
            FieldExtractionStatus.UNCERTAIN,
        }:
            continue
        if not field.candidate_ids:
            continue
        matched = False
        for cid in field.candidate_ids:
            for slot in slots_by_cand.get(str(cid), []):
                slot.metadata = {**dict(slot.metadata), "canonical_key": key}
                if field.value not in (None, "") and slot.value in (None, ""):
                    slot.value = field.value
                matched = True
        if matched:
            continue
        # Create slots from candidates so DocumentInstance remains complete.
        for cid in field.candidate_ids:
            cand = index.get(str(cid))
            if not cand:
                continue
            new_slot = DocumentSlot(
                id=f"slot_{cid}",
                kind="field",
                label=str(cand.get("label_text") or "").strip() or None,
                value=field.value if field.value not in (None, "") else cand.get("value_text"),
                confidence=_conf_str(cand.get("confidence")),
                layout=DocumentLayoutRef(
                    page=_optional_int(cand.get("page")),
                    section_id=_optional_str(cand.get("section_id")),
                    row_id=_optional_str(cand.get("row_id")),
                    column_index=_optional_int(cand.get("column_index")),
                    bbox=_bbox(cand.get("bbox")),
                ),
                evidence=DocumentEvidenceRef(
                    candidate_ids=[str(cid)],
                    association_id=_optional_str(cand.get("association_id")),
                    label_cell_id=_optional_str(cand.get("label_cell_id")),
                    value_cell_id=_optional_str(cand.get("value_cell_id")),
                    source_line_ids=[str(x) for x in (cand.get("source_line_ids") or []) if x],
                    source_word_ids=[str(x) for x in (cand.get("source_word_ids") or []) if x],
                    relation=_optional_str(cand.get("relation")),
                    conflict=bool(cand.get("conflict") or False),
                ),
                metadata={"canonical_key": key, "source": "structured_enrichment"},
            )
            doc.slots.append(new_slot)
            slots_by_cand.setdefault(str(cid), []).append(new_slot)

    doc.slot_count = len(doc.slots)
    return doc


def _slot_to_extracted_field(
    slot: DocumentSlot,
    *,
    parser_method: str,
) -> ExtractedField:
    has_value = slot.value not in (None, "")
    return ExtractedField(
        value=slot.value if has_value else None,
        confidence=_band_to_float(slot.confidence),
        source_text=slot.label,
        status=FieldExtractionStatus.FOUND if has_value else FieldExtractionStatus.MISSING,
        candidate_ids=list(slot.evidence.candidate_ids),
        source_bbox=list(slot.layout.bbox) if slot.layout.bbox else None,
        source_page=slot.layout.page,
        parser_method=parser_method,
        warnings=["slot_conflict"] if slot.evidence.conflict else [],
    )


def _slot_usable(slot: DocumentSlot) -> bool:
    if (slot.label or "").strip():
        return True
    if slot.value not in (None, ""):
        return True
    return False


def _as_instance(raw: DocumentInstance | dict[str, Any] | None) -> DocumentInstance:
    if isinstance(raw, DocumentInstance):
        return raw
    if isinstance(raw, dict) and raw:
        return DocumentInstance.from_dict(raw)
    return empty_document_instance()


def _band_to_float(band: str | None) -> float | None:
    if band is None:
        return None
    return _CONFIDENCE_BAND.get(str(band).strip().lower())


def _conf_str(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bbox(raw: Any) -> list[float] | None:
    if not isinstance(raw, list) or len(raw) < 4:
        return None
    try:
        return [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])]
    except (TypeError, ValueError):
        return None
