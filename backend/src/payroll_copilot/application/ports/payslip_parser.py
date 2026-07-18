"""Payslip AI Parser port — OCR text → structured fields (no validation).

Pipeline:
  Document → OCR → AI Parser (this) → Structured Payslip JSON → (future Validation)

Parser must not feed the Rule Engine directly.
Does not modify domain PayslipData.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FieldExtractionStatus(StrEnum):
    FOUND = "FOUND"
    MISSING = "MISSING"
    UNCERTAIN = "UNCERTAIN"


class ExtractedField(BaseModel):
    """Single extracted payslip field — value + provenance + honesty flags."""

    model_config = ConfigDict(extra="forbid")

    value: str | float | int | bool | dict[str, Any] | list[Any] | None = None
    confidence: float | None = None
    source_text: str | None = None
    status: FieldExtractionStatus = FieldExtractionStatus.MISSING
    edited_by_user: bool = False
    original_value: str | float | int | bool | dict[str, Any] | list[Any] | None = None
    # Additive layout-aware provenance (optional; backward compatible).
    evidence_ids: list[str] = Field(default_factory=list)
    # Phase 3 deterministic association candidates (authoritative when evidence-bound).
    candidate_ids: list[str] = Field(default_factory=list)
    source_bbox: list[float] | None = None
    source_page: int | None = None
    parser_method: str | None = None
    warnings: list[str] = Field(default_factory=list)
    normalized_value: float | None = None

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, value: object) -> float | None:
        if value is None or value == "":
            return None
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        if number < 0.0 or number > 1.0:
            return None
        return number

    @field_validator("source_bbox", mode="before")
    @classmethod
    def coerce_bbox(cls, value: object) -> list[float] | None:
        if value is None or value == "":
            return None
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            return None
        try:
            box = [float(v) for v in value]
        except (TypeError, ValueError):
            return None
        if box[2] <= 0 or box[3] <= 0:
            return None
        return box

    @field_validator("status", mode="before")
    @classmethod
    def coerce_status(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().upper()
        aliases = {
            "EXTRACTED": FieldExtractionStatus.FOUND.value,
            "LOW_CONFIDENCE": FieldExtractionStatus.UNCERTAIN.value,
            "UNABLE_TO_READ": FieldExtractionStatus.UNCERTAIN.value,
            "CONFLICTING_EVIDENCE": FieldExtractionStatus.UNCERTAIN.value,
        }
        return aliases.get(normalized, normalized)


# Canonical field keys for Phase 2A (extendable via additional_fields).
PAYSLIP_FIELD_KEYS: tuple[str, ...] = (
    "employee_name",
    "employee_id",
    "employee_number",
    "pay_period",
    "employment_type",
    "department",
    "hourly_rate",
    "base_salary",
    "travel_expenses",
    "regular_hours",
    "overtime_hours",
    "gross_salary",
    "income_tax",
    "national_insurance",
    "health_tax",
    "pension_employee",
    "pension_employer",
    "severance",
    "training_fund",
    "net_salary",
    "vacation_balance",
    "sick_leave_balance",
    "payment_method",
    "messages",
)


def _default_field() -> ExtractedField:
    return ExtractedField(status=FieldExtractionStatus.MISSING)


class StructuredPayslipParse(BaseModel):
    """Layout-independent structured payslip extraction result.

    Every known field is always present as ExtractedField.
    ``additional_fields`` allows provider-specific extras without schema churn.
    """

    model_config = ConfigDict(extra="forbid")

    employee_name: ExtractedField = Field(default_factory=_default_field)
    employee_id: ExtractedField = Field(default_factory=_default_field)
    employee_number: ExtractedField = Field(default_factory=_default_field)
    pay_period: ExtractedField = Field(default_factory=_default_field)
    employment_type: ExtractedField = Field(default_factory=_default_field)
    department: ExtractedField = Field(default_factory=_default_field)
    hourly_rate: ExtractedField = Field(default_factory=_default_field)
    base_salary: ExtractedField = Field(default_factory=_default_field)
    travel_expenses: ExtractedField = Field(default_factory=_default_field)
    regular_hours: ExtractedField = Field(default_factory=_default_field)
    overtime_hours: ExtractedField = Field(default_factory=_default_field)
    gross_salary: ExtractedField = Field(default_factory=_default_field)
    income_tax: ExtractedField = Field(default_factory=_default_field)
    national_insurance: ExtractedField = Field(default_factory=_default_field)
    health_tax: ExtractedField = Field(default_factory=_default_field)
    pension_employee: ExtractedField = Field(default_factory=_default_field)
    pension_employer: ExtractedField = Field(default_factory=_default_field)
    severance: ExtractedField = Field(default_factory=_default_field)
    training_fund: ExtractedField = Field(default_factory=_default_field)
    net_salary: ExtractedField = Field(default_factory=_default_field)
    vacation_balance: ExtractedField = Field(default_factory=_default_field)
    sick_leave_balance: ExtractedField = Field(default_factory=_default_field)
    payment_method: ExtractedField = Field(default_factory=_default_field)
    messages: ExtractedField = Field(default_factory=_default_field)

    additional_fields: dict[str, ExtractedField] = Field(default_factory=dict)
    parser_notes: str | None = None
    language: str | None = None

    def field_map(self) -> dict[str, ExtractedField]:
        data = self.model_dump()
        known = {key: ExtractedField.model_validate(data[key]) for key in PAYSLIP_FIELD_KEYS}
        known.update(self.additional_fields)
        return known


class PayslipParseResult(BaseModel):
    """Application-level parser result returned to API / future validation mapping."""

    model_config = ConfigDict(extra="forbid")

    model: str
    language: str | None = None
    fields: StructuredPayslipParse
    raw_model_response: str | None = None
    parsed_payload: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    retry_used: bool = False


@runtime_checkable
class PayslipParser(Protocol):
    """Pluggable AI payslip parser (layout-aware when context provided)."""

    async def parse(
        self,
        *,
        ocr_text: str,
        language: str = "auto",
        pages_text: list[str] | None = None,
        layout_context: dict[str, object] | None = None,
        retry_hint: str | None = None,
    ) -> PayslipParseResult:
        """Parse OCR text / layout context into structured payslip fields.

        ``retry_hint`` is set by the use case on a second attempt after JSON failure.
        """
        ...
