"""Server-side payslip identity and payroll-period comparison.

Decrypted National IDs are used only in-process for equality checks and are never
returned in API payloads or written to application logs.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from payroll_copilot.infrastructure.security.field_crypto import mask_national_id

# Below this confidence (when status is FOUND), treat as uncertain — never as mismatch alone.
LOW_CONFIDENCE_THRESHOLD = 0.7


@dataclass(frozen=True, slots=True)
class FieldComparison:
    key: str
    status: str  # match | mismatch | uncertain | missing | extracted
    extracted_display: str | None
    expected_display: str | None
    severity: str  # critical | warning | info
    blocks_confirmation: bool = False
    explanation_code: str | None = None


@dataclass(frozen=True, slots=True)
class IdentityCheckResult:
    overall: str  # match | mismatch | incomplete
    blocks_confirmation: bool
    fields: list[FieldComparison] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "blocks_confirmation": self.blocks_confirmation,
            "fields": [
                {
                    "key": f.key,
                    "status": f.status,
                    "extracted_display": f.extracted_display,
                    "expected_display": f.expected_display,
                    "severity": f.severity,
                    "blocks_confirmation": f.blocks_confirmation,
                    "explanation_code": f.explanation_code,
                }
                for f in self.fields
            ],
        }


@dataclass(frozen=True, slots=True)
class PeriodCheckResult:
    status: str  # match | mismatch | uncertain | missing
    blocks_confirmation: bool
    selected_year: int
    selected_month: int
    extracted_year: int | None
    extracted_month: int | None
    explanation_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "blocks_confirmation": self.blocks_confirmation,
            "selected_year": self.selected_year,
            "selected_month": self.selected_month,
            "extracted_year": self.extracted_year,
            "extracted_month": self.extracted_month,
            "explanation_code": self.explanation_code,
        }


@dataclass(frozen=True, slots=True)
class PayslipComparisonResult:
    identity_check: IdentityCheckResult
    period_check: PeriodCheckResult

    @property
    def blocks_confirmation(self) -> bool:
        return self.identity_check.blocks_confirmation or self.period_check.blocks_confirmation


def normalize_national_id_digits(value: Any) -> str | None:
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits or None


def normalize_employee_number(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return "".join(ch for ch in text if ch.isalnum()).upper() or None


def normalize_person_name(value: Any) -> str | None:
    """Conservative name normalization — never fuzzy-match to declare equality."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return text or None


def parse_pay_period(value: Any) -> tuple[int | None, int | None]:
    """Best-effort parse of pay_period into (year, month)."""
    if value is None:
        return None, None
    if isinstance(value, dict):
        year = value.get("year")
        month = value.get("month")
        try:
            y = int(year) if year is not None else None
            m = int(month) if month is not None else None
            if y and m and 1 <= m <= 12:
                return y, m
        except (TypeError, ValueError):
            pass
        value = value.get("value") or value.get("label") or value
    text = str(value).strip()
    if not text:
        return None, None
    # ISO-ish YYYY-MM or YYYY/MM
    m = re.search(r"(20\d{2})[^\d]?(0?[1-9]|1[0-2])", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    # MM/YYYY or MM-YYYY
    m = re.search(r"(0?[1-9]|1[0-2])[^\d](20\d{2})", text)
    if m:
        return int(m.group(2)), int(m.group(1))
    return None, None


def _field_payload(fields: list[Any] | dict[str, Any], key: str) -> dict[str, Any]:
    if isinstance(fields, dict):
        payload = fields.get(key)
        if isinstance(payload, dict):
            return payload
        return {"value": payload, "status": "FOUND" if payload not in (None, "") else "MISSING"}
    for item in fields:
        item_key = getattr(item, "key", None) if not isinstance(item, dict) else item.get("key")
        if item_key != key:
            continue
        if isinstance(item, dict):
            return item
        return {
            "value": getattr(item, "value", None),
            "status": getattr(item, "status", "MISSING"),
            "confidence": getattr(item, "confidence", None),
            "edited_by_user": getattr(item, "edited_by_user", False),
        }
    return {"value": None, "status": "MISSING", "confidence": None}


def _usable_extraction(payload: dict[str, Any]) -> tuple[Any, str, float | None]:
    status = str(payload.get("status") or "MISSING").upper()
    value = payload.get("value")
    conf_raw = payload.get("confidence")
    confidence: float | None
    try:
        confidence = float(conf_raw) if conf_raw is not None and conf_raw != "" else None
    except (TypeError, ValueError):
        confidence = None
    if status in {"MISSING", ""} or value in (None, ""):
        return None, "missing", confidence
    if status == "UNCERTAIN" or (
        confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD and not payload.get("edited_by_user")
    ):
        return value, "uncertain", confidence
    return value, "usable", confidence


class PayslipIdentityComparisonService:
    """Compare extraction against trusted employee context and selected period."""

    def compare(
        self,
        *,
        trusted_full_name: str,
        trusted_employee_number: str,
        trusted_national_id_plaintext: str | None,
        trusted_national_id_masked: str | None,
        selected_year: int,
        selected_month: int,
        extraction_fields: list[Any] | dict[str, Any],
    ) -> PayslipComparisonResult:
        identity_fields: list[FieldComparison] = []

        # --- National ID (critical) ---
        nid_payload = _field_payload(extraction_fields, "employee_id")
        nid_value, nid_state, _ = _usable_extraction(nid_payload)
        extracted_digits = normalize_national_id_digits(nid_value)
        trusted_digits = normalize_national_id_digits(trusted_national_id_plaintext)

        if nid_state == "missing" or extracted_digits is None:
            identity_fields.append(
                FieldComparison(
                    key="national_id",
                    status="missing",
                    extracted_display=None,
                    expected_display=trusted_national_id_masked,
                    severity="info",
                    explanation_code="national_id_missing",
                )
            )
        elif nid_state == "uncertain":
            identity_fields.append(
                FieldComparison(
                    key="national_id",
                    status="uncertain",
                    extracted_display=mask_national_id(extracted_digits),
                    expected_display=trusted_national_id_masked,
                    severity="warning",
                    explanation_code="national_id_uncertain",
                )
            )
        elif trusted_digits is None:
            identity_fields.append(
                FieldComparison(
                    key="national_id",
                    status="extracted",
                    extracted_display=mask_national_id(extracted_digits),
                    expected_display=trusted_national_id_masked,
                    severity="info",
                    explanation_code="national_id_no_profile",
                )
            )
        elif extracted_digits == trusted_digits:
            identity_fields.append(
                FieldComparison(
                    key="national_id",
                    status="match",
                    extracted_display=mask_national_id(extracted_digits),
                    expected_display=trusted_national_id_masked or mask_national_id(trusted_digits),
                    severity="info",
                    explanation_code="national_id_match",
                )
            )
        else:
            identity_fields.append(
                FieldComparison(
                    key="national_id",
                    status="mismatch",
                    extracted_display=mask_national_id(extracted_digits),
                    expected_display=trusted_national_id_masked or mask_national_id(trusted_digits),
                    severity="critical",
                    blocks_confirmation=True,
                    explanation_code="national_id_mismatch",
                )
            )

        # --- Employee number (warning) ---
        num_payload = _field_payload(extraction_fields, "employee_number")
        num_value, num_state, _ = _usable_extraction(num_payload)
        extracted_num = normalize_employee_number(num_value)
        trusted_num = normalize_employee_number(trusted_employee_number)
        if num_state == "missing" or extracted_num is None:
            identity_fields.append(
                FieldComparison(
                    key="employee_number",
                    status="missing",
                    extracted_display=None,
                    expected_display=trusted_employee_number,
                    severity="info",
                    explanation_code="employee_number_missing",
                )
            )
        elif num_state == "uncertain":
            identity_fields.append(
                FieldComparison(
                    key="employee_number",
                    status="uncertain",
                    extracted_display=str(num_value),
                    expected_display=trusted_employee_number,
                    severity="warning",
                    explanation_code="employee_number_uncertain",
                )
            )
        elif extracted_num == trusted_num:
            identity_fields.append(
                FieldComparison(
                    key="employee_number",
                    status="match",
                    extracted_display=str(num_value),
                    expected_display=trusted_employee_number,
                    severity="info",
                    explanation_code="employee_number_match",
                )
            )
        else:
            identity_fields.append(
                FieldComparison(
                    key="employee_number",
                    status="mismatch",
                    extracted_display=str(num_value),
                    expected_display=trusted_employee_number,
                    severity="warning",
                    blocks_confirmation=False,
                    explanation_code="employee_number_mismatch",
                )
            )

        # --- Employee name (warning only) ---
        name_payload = _field_payload(extraction_fields, "employee_name")
        name_value, name_state, _ = _usable_extraction(name_payload)
        extracted_name = normalize_person_name(name_value)
        trusted_name = normalize_person_name(trusted_full_name)
        if name_state == "missing" or extracted_name is None:
            identity_fields.append(
                FieldComparison(
                    key="employee_name",
                    status="missing",
                    extracted_display=None,
                    expected_display=trusted_full_name,
                    severity="info",
                    explanation_code="employee_name_missing",
                )
            )
        elif name_state == "uncertain":
            identity_fields.append(
                FieldComparison(
                    key="employee_name",
                    status="uncertain",
                    extracted_display=str(name_value),
                    expected_display=trusted_full_name,
                    severity="warning",
                    explanation_code="employee_name_uncertain",
                )
            )
        elif extracted_name == trusted_name:
            identity_fields.append(
                FieldComparison(
                    key="employee_name",
                    status="match",
                    extracted_display=str(name_value),
                    expected_display=trusted_full_name,
                    severity="info",
                    explanation_code="employee_name_match",
                )
            )
        else:
            identity_fields.append(
                FieldComparison(
                    key="employee_name",
                    status="mismatch",
                    extracted_display=str(name_value),
                    expected_display=trusted_full_name,
                    severity="warning",
                    blocks_confirmation=False,
                    explanation_code="employee_name_mismatch",
                )
            )

        nid_mismatch = any(
            f.key == "national_id" and f.status == "mismatch" for f in identity_fields
        )
        has_usable_compare = any(f.status in {"match", "mismatch"} for f in identity_fields)
        if nid_mismatch:
            overall = "mismatch"
        elif not has_usable_compare:
            overall = "incomplete"
        elif all(
            f.status in {"match", "missing", "uncertain", "extracted"}
            or (f.key != "national_id" and f.status == "mismatch")
            for f in identity_fields
        ) and any(f.status == "match" for f in identity_fields):
            # Name/number mismatches alone → still "mismatch" at overall? Policy: name only warns.
            # overall mismatch only when national_id mismatches; otherwise match if NID matches,
            # incomplete otherwise.
            nid_field = next(f for f in identity_fields if f.key == "national_id")
            if nid_field.status == "match":
                overall = "match"
            else:
                overall = "incomplete"
        else:
            overall = "incomplete"

        identity = IdentityCheckResult(
            overall=overall,
            blocks_confirmation=nid_mismatch,
            fields=identity_fields,
        )

        # --- Period ---
        period_payload = _field_payload(extraction_fields, "pay_period")
        period_value, period_state, _ = _usable_extraction(period_payload)
        extracted_year, extracted_month = parse_pay_period(period_value)
        if period_state == "missing" or (extracted_year is None or extracted_month is None):
            period = PeriodCheckResult(
                status="missing" if period_state == "missing" else "uncertain",
                blocks_confirmation=False,
                selected_year=selected_year,
                selected_month=selected_month,
                extracted_year=extracted_year,
                extracted_month=extracted_month,
                explanation_code="period_missing"
                if period_state == "missing"
                else "period_uncertain",
            )
        elif period_state == "uncertain":
            period = PeriodCheckResult(
                status="uncertain",
                blocks_confirmation=False,
                selected_year=selected_year,
                selected_month=selected_month,
                extracted_year=extracted_year,
                extracted_month=extracted_month,
                explanation_code="period_uncertain",
            )
        elif extracted_year == selected_year and extracted_month == selected_month:
            period = PeriodCheckResult(
                status="match",
                blocks_confirmation=False,
                selected_year=selected_year,
                selected_month=selected_month,
                extracted_year=extracted_year,
                extracted_month=extracted_month,
                explanation_code="period_match",
            )
        else:
            period = PeriodCheckResult(
                status="mismatch",
                blocks_confirmation=True,
                selected_year=selected_year,
                selected_month=selected_month,
                extracted_year=extracted_year,
                extracted_month=extracted_month,
                explanation_code="period_mismatch",
            )

        return PayslipComparisonResult(identity_check=identity, period_check=period)
