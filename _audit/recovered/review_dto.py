"""Payslip Review DTO — sole frontend-facing review contract (Phase 2).

Built only from DocumentInstance. Never from storage junk keys or dual entries/fields SoTs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from payroll_copilot.application.services.presentation_safe_keys import (
    is_presentation_safe_field_key,
)
from payroll_copilot.domain.document_model import DocumentInstance


@dataclass(frozen=True, slots=True)
class ReviewLine:
    line_id: str
    display_label: str
    value: Any
    confidence: float | None = None
    section_title: str | None = None
    editable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_id": self.line_id,
            "display_label": self.display_label,
            "value": self.value,
            "confidence": self.confidence,
            "section_title": self.section_title,
            "editable": self.editable,
        }


@dataclass(frozen=True, slots=True)
class PayslipReview:
    document_id: str
    extraction_id: str
    extraction_version: int
    confirmation_status: str
    lines: list[ReviewLine] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    canonical_preview: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "extraction_id": self.extraction_id,
            "extraction_version": self.extraction_version,
            "confirmation_status": self.confirmation_status,
            "lines": [line.to_dict() for line in self.lines],
            "warnings": list(self.warnings),
            "canonical_preview": list(self.canonical_preview),
        }


def _band_to_float(band: str | None) -> float | None:
    if band == "high":
        return 0.9
    if band == "medium":
        return 0.7
    if band == "low":
        return 0.4
    return None


def _display_label_for_slot(label: str | None, slot_id: str) -> str | None:
    """Human label only — never storage / slot ids."""
    text = (label or "").strip()
    if not text:
        return None
    if text.startswith("slot_") or text.startswith("candidate_"):
        return None
    if text == "unknown":
        return None
    if not is_presentation_safe_field_key(text) and text.replace("_", "").isalnum():
        # snake_case storage-like keys are not display labels unless clearly human text
        if "_" in text and text.lower() == text:
            return None
    return text


def review_lines_from_document(instance: DocumentInstance | dict[str, Any] | None) -> list[ReviewLine]:
    if instance is None:
        return []
    doc = (
        instance
        if isinstance(instance, DocumentInstance)
        else DocumentInstance.from_dict(instance)
    )
    lines: list[ReviewLine] = []
    for slot in doc.slots:
        label = _display_label_for_slot(slot.label, slot.id)
        has_value = slot.value not in (None, "")
        if label is None and not has_value:
            continue
        display = label or "—"
        lines.append(
            ReviewLine(
                line_id=slot.id,
                display_label=display,
                value=slot.value,
                confidence=_band_to_float(slot.confidence),
                section_title=slot.layout.section_id,
                editable=True,
            )
        )
    return lines


def build_payslip_review(
    *,
    document_id: UUID | str,
    extraction_id: UUID | str,
    extraction_version: int,
    confirmation_status: str,
    document_model: DocumentInstance | dict[str, Any] | None,
    warnings: list[str] | None = None,
    canonical_preview: list[dict[str, Any]] | None = None,
) -> PayslipReview:
    return PayslipReview(
        document_id=str(document_id),
        extraction_id=str(extraction_id),
        extraction_version=int(extraction_version or 1),
        confirmation_status=confirmation_status or "review_required",
        lines=review_lines_from_document(document_model),
        warnings=list(warnings or []),
        canonical_preview=list(canonical_preview or []),
    )


def review_has_usable_values(review: PayslipReview | list[ReviewLine] | None) -> bool:
    lines = review.lines if isinstance(review, PayslipReview) else (review or [])
    return any(line.value not in (None, "") for line in lines)
