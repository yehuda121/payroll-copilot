"""Semantic validation for payslip parser model JSON (pre-coercion).

Rejects schema-copy responses, invalid keys, and unusable all-MISSING payloads
when OCR evidence exists. Does not invent field values.
"""

from __future__ import annotations

import re
from typing import Any

from payroll_copilot.application.exceptions import PayslipParserSemanticError
from payroll_copilot.application.ports.payslip_parser import PAYSLIP_FIELD_KEYS

_ALLOWED_TOP_LEVEL = frozenset({*PAYSLIP_FIELD_KEYS, "additional_fields", "parser_notes", "language"})
_STRIP_TOP_LEVEL = frozenset(
    {
        "parser_version",
        "schema_version",
        "model",
        "version",
        "schema",
        "$schema",
        "type",
        "title",
        "description",
    }
)
_FIELD_ALIASES = {
    "name": "employee_name",
    "employee": "employee_name",
    "full_name": "employee_name",
    "worker_name": "employee_name",
    "period": "pay_period",
    "salary_period": "pay_period",
    "pay_month": "pay_period",
    "payroll_month": "pay_period",
    "base": "base_salary",
    "gross": "gross_salary",
    "total_payment": "gross_salary",
    "gross_pay": "gross_salary",
    "net": "net_salary",
    "net_pay": "net_salary",
    "worker_number": "employee_number",
    "worker_id": "employee_id",
    "employee_no": "employee_number",
    "id_number": "employee_id",
    "bank_transfer": "payment_method",
    "payment": "payment_method",
}

# Guest landing simple field names that are not canonical top-level keys.
_GUEST_ADDITIONAL_KEYS = frozenset(
    {"national_id", "payroll_month", "total_deductions", "total_payments", "bank_transfer"}
)
_SCHEMA_STRUCTURAL_KEYS = frozenset(
    {"$ref", "$defs", "definitions", "properties", "required", "title"}
)
_OCR_ECHO_ROOT_KEYS = frozenset(
    {"block_type", "pages", "lines", "words", "bbox", "evidence_index"}
)
_NUMERIC_KEY_RE = re.compile(
    r"^[\d]+([.,]\d+)?$|^[\d]{1,3}(,\d{3})+(\.\d+)?$|^[\d]{1,3}(\.\d{3})+(,\d+)?$"
)
_DATE_KEY_RE = re.compile(
    r"^(\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?|\d{4}-\d{2}(-\d{2})?|\d{1,2}/\d{2})$"
)
_SEMANTIC_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_FIELD_CONTRACT_KEYS = frozenset(
    {
        "value",
        "confidence",
        "source_text",
        "status",
        "evidence_ids",
        "candidate_ids",
        "source_bbox",
        "source_page",
        "parser_method",
        "warnings",
        "normalized_value",
        "edited_by_user",
        "original_value",
    }
)


def _layout_evidence_ids(layout_context: dict[str, Any] | None) -> set[str]:
    ids: set[str] = set()
    if not layout_context:
        return ids
    for page in layout_context.get("pages") or []:
        if not isinstance(page, dict):
            continue
        for line in page.get("lines") or []:
            if not isinstance(line, dict):
                continue
            lid = line.get("id")
            if isinstance(lid, str) and lid.strip():
                ids.add(lid.strip())
            for word in line.get("words") or []:
                if not isinstance(word, dict):
                    continue
                wid = word.get("id")
                if isinstance(wid, str) and wid.strip():
                    ids.add(wid.strip())
    return ids


_MISSING_FIELD_STUB: dict[str, Any] = {
    "value": None,
    "confidence": None,
    "source_text": None,
    "status": "MISSING",
    "evidence_ids": [],
    "candidate_ids": [],
    "source_bbox": None,
    "source_page": None,
    "parser_method": "layout_llm",
    "warnings": [],
    "normalized_value": None,
}


def normalize_payslip_parser_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalize near-miss keys without inventing field values.

    - Maps common aliases (e.g. name → employee_name) when the canonical key is absent
    - Drops known noise metadata keys
    - Promotes guest-simple extras into additional_fields
    - Fills absent required keys with explicit MISSING stubs (structure only)
    """
    if not isinstance(payload, dict):
        return payload, []

    warnings: list[str] = []
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _STRIP_TOP_LEVEL:
            warnings.append("parser_unknown_top_level_stripped")
            continue
        target = _FIELD_ALIASES.get(key, key)
        if target != key:
            if target in payload or target in normalized:
                warnings.append("parser_unknown_top_level_stripped")
                continue
            warnings.append("parser_field_alias_normalized")
            normalized[target] = value
            continue
        normalized[key] = value

    additional = normalized.get("additional_fields")
    if not isinstance(additional, dict):
        additional = {}
    for key in list(normalized.keys()):
        if key in PAYSLIP_FIELD_KEYS or key in {"additional_fields", "parser_notes", "language"}:
            continue
        # Preserve guest extras (national_id, total_deductions, …) instead of failing.
        if key in _GUEST_ADDITIONAL_KEYS or _SEMANTIC_KEY_RE.match(key or ""):
            if key not in additional:
                additional[key] = normalized.pop(key)
                warnings.append("parser_guest_field_promoted")
            else:
                normalized.pop(key, None)
                warnings.append("parser_unknown_top_level_stripped")
            continue
        normalized.pop(key, None)
        warnings.append("parser_unknown_top_level_stripped")
    normalized["additional_fields"] = additional

    for key in PAYSLIP_FIELD_KEYS:
        if key not in normalized:
            normalized[key] = dict(_MISSING_FIELD_STUB)
            warnings.append("parser_missing_required_fields")

    return normalized, list(dict.fromkeys(warnings))


def ocr_context_has_usable_evidence(
    *,
    ocr_text: str,
    layout_context: dict[str, Any] | None,
) -> bool:
    """True when OCR/layout contains non-empty extractable text evidence."""
    if layout_context:
        for page in layout_context.get("pages") or []:
            if not isinstance(page, dict):
                continue
            for line in page.get("lines") or []:
                if isinstance(line, dict) and str(line.get("text") or "").strip():
                    return True
            for word in page.get("words") or []:
                if isinstance(word, dict) and str(word.get("text") or "").strip():
                    return True
    stripped = (ocr_text or "").strip()
    if not stripped:
        return False
    return bool(re.search(r"[\w\u0590-\u05FF\u0600-\u06FF]", stripped, re.UNICODE))


def _raise(category: str, warning_code: str, message: str) -> None:
    raise PayslipParserSemanticError(
        message,
        category=category,
        warning_code=warning_code,
    )


def _walk_schema_keys(node: Any, *, path: str = "$") -> str | None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _SCHEMA_STRUCTURAL_KEYS:
                return f"{path}.{key}"
            found = _walk_schema_keys(value, path=f"{path}.{key}")
            if found:
                return found
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found = _walk_schema_keys(item, path=f"{path}[{index}]")
            if found:
                return found
    return None


def is_invalid_additional_field_key(name: str) -> bool:
    text = (name or "").strip()
    if not text:
        return True
    if text in PAYSLIP_FIELD_KEYS:
        return True
    if _NUMERIC_KEY_RE.match(text):
        return True
    if _DATE_KEY_RE.match(text):
        return True
    if not _SEMANTIC_KEY_RE.match(text):
        return True
    return False


def _is_schema_stub_field(raw: object) -> bool:
    if not isinstance(raw, dict):
        return False
    if "$ref" in raw or "$defs" in raw:
        return True
    keys = set(raw.keys())
    if keys and keys.issubset({"$ref", "$defs", "type", "title", "description", "items"}):
        return True
    return False


def _is_field_object(raw: object) -> bool:
    if not isinstance(raw, dict):
        return False
    if _is_schema_stub_field(raw):
        return False
    # Simplified parser contract: {value, source_text, confidence}
    if "value" in raw and "status" not in raw:
        return True
    if "status" not in raw or "value" not in raw:
        return False
    # Disallow pure schema fragments mixed into field objects.
    foreign = set(raw.keys()) - _FIELD_CONTRACT_KEYS
    if foreign & _SCHEMA_STRUCTURAL_KEYS:
        return False
    return True


def expand_simplified_field(raw: dict[str, Any]) -> dict[str, Any]:
    """Expand minimal LLM field objects into the full server field contract."""
    if "status" in raw:
        expanded = dict(raw)
        if "candidate_ids" not in expanded:
            expanded["candidate_ids"] = list(raw.get("candidate_ids") or [])
        return expanded
    value = raw.get("value")
    source_text = raw.get("source_text")
    confidence = raw.get("confidence")
    candidate_ids = raw.get("candidate_ids") or []
    if not isinstance(candidate_ids, list):
        candidate_ids = []
    if value in (None, "") and not candidate_ids:
        status = "MISSING"
    elif candidate_ids or (isinstance(source_text, str) and source_text.strip()):
        status = "FOUND"
    else:
        status = "UNCERTAIN"
    expanded = dict(_MISSING_FIELD_STUB)
    expanded.update(raw)
    expanded["candidate_ids"] = [str(item) for item in candidate_ids if item is not None]
    expanded["status"] = status
    expanded["parser_method"] = raw.get("parser_method") or "semantic_llm"
    if status == "MISSING":
        expanded["confidence"] = None
    elif confidence is not None:
        expanded["confidence"] = confidence
    return expanded


def _status_of(raw: dict[str, Any]) -> str:
    status = raw.get("status")
    if isinstance(status, str):
        return status.strip().upper()
    candidate_ids = raw.get("candidate_ids") or []
    if isinstance(candidate_ids, list) and candidate_ids:
        return "FOUND"
    if raw.get("value") in (None, ""):
        return "MISSING"
    if isinstance(raw.get("source_text"), str) and str(raw.get("source_text")).strip():
        return "FOUND"
    return "UNCERTAIN"


def validate_payslip_parser_payload(
    payload: dict[str, Any],
    *,
    ocr_text: str,
    layout_context: dict[str, Any] | None = None,
    require_evidence_ids: bool | None = None,
    embedded_text_mode: bool = False,
    evidence_bound: bool = False,
    known_candidate_ids: set[str] | None = None,
) -> list[str]:
    """Validate model JSON before coercion.

    Returns warning codes describing issues that were accepted only when
    OCR evidence is unusable (currently unused — failures raise).

    Raises:
        PayslipParserSemanticError: when the payload is structurally unusable.
    """
    if not isinstance(payload, dict):
        _raise("not_object", "parser_semantic_invalid", "Parser JSON root must be an object.")

    root_keys = set(payload.keys())
    if root_keys & _OCR_ECHO_ROOT_KEYS or root_keys <= {"id", "text", "block_type", "confidence"}:
        _raise(
            "ocr_echo",
            "parser_schema_copy_detected",
            "Parser response echoed OCR layout instead of payroll field instances.",
        )

    schema_hit = _walk_schema_keys(payload)
    if schema_hit:
        code = (
            "parser_schema_copy_detected"
            if ("$ref" in schema_hit or "$defs" in schema_hit)
            else "parser_schema_copy_detected"
        )
        _raise(
            "schema_copy",
            code,
            "Parser response contains schema metadata instead of field instances.",
        )

    unknown = [key for key in payload.keys() if key not in _ALLOWED_TOP_LEVEL]
    if unknown:
        _raise(
            "unknown_top_level",
            "parser_missing_required_fields",
            "Parser response contains unsupported top-level fields.",
        )

    missing_required = [key for key in PAYSLIP_FIELD_KEYS if key not in payload]
    if missing_required:
        _raise(
            "missing_required_fields",
            "parser_missing_required_fields",
            f"Parser response missing {len(missing_required)} required field(s).",
        )

    known_evidence_ids = _layout_evidence_ids(layout_context)
    if evidence_bound:
        evidence_required = False
    elif embedded_text_mode:
        evidence_required = False
    else:
        evidence_required = (
            require_evidence_ids
            if require_evidence_ids is not None
            else bool(known_evidence_ids)
        )
    candidate_ids_known = known_candidate_ids or set()

    for key in PAYSLIP_FIELD_KEYS:
        raw = payload[key]
        if _is_schema_stub_field(raw):
            _raise(
                "schema_stub_field",
                "parser_schema_copy_detected",
                "Parser response contains schema stub field objects.",
            )
        if not _is_field_object(raw):
            _raise(
                "invalid_field_object",
                "parser_semantic_invalid",
                "Parser response field is not a valid field instance.",
            )
        assert isinstance(raw, dict)
        field_obj = expand_simplified_field(raw)
        value = field_obj.get("value")
        candidate_ids = field_obj.get("candidate_ids") or []
        mapped = value not in (None, "") or (
            isinstance(candidate_ids, list) and bool(candidate_ids)
        )
        if mapped and evidence_bound:
            _validate_candidate_ids(field_obj, known_ids=candidate_ids_known)
        elif value not in (None, "") and evidence_required:
            evidence_ids = field_obj.get("evidence_ids") or []
            if not isinstance(evidence_ids, list) or not evidence_ids:
                _raise(
                    "missing_evidence_ids",
                    "parser_semantic_invalid",
                    "Non-null parser field is missing evidence_ids.",
                )
            if known_evidence_ids and any(
                str(item) not in known_evidence_ids for item in evidence_ids if item is not None
            ):
                _raise(
                    "invalid_evidence_ids",
                    "parser_semantic_invalid",
                    "Parser field cites evidence_ids that are not in the OCR layout context.",
                )

    additional = payload.get("additional_fields", {})
    if additional is None:
        additional = {}
    if not isinstance(additional, dict):
        _raise(
            "invalid_additional_fields",
            "parser_invalid_additional_field_key",
            "additional_fields must be an object.",
        )
    for name, raw in additional.items():
        if not isinstance(name, str) or is_invalid_additional_field_key(name):
            _raise(
                "invalid_additional_key",
                "parser_invalid_additional_field_key",
                "additional_fields contains a non-semantic key.",
            )
        if _is_schema_stub_field(raw) or not _is_field_object(raw):
            _raise(
                "invalid_additional_field_object",
                "parser_semantic_invalid",
                "additional_fields entry is not a valid field instance.",
            )
        assert isinstance(raw, dict)
        if raw.get("value") not in (None, "") and evidence_bound:
            _validate_candidate_ids(expand_simplified_field(raw), known_ids=candidate_ids_known)
        elif raw.get("value") not in (None, "") and evidence_required:
            evidence_ids = raw.get("evidence_ids") or []
            if not isinstance(evidence_ids, list) or not evidence_ids:
                _raise(
                    "missing_evidence_ids",
                    "parser_semantic_invalid",
                    "Non-null additional field is missing evidence_ids.",
                )
            if known_evidence_ids and any(
                str(item) not in known_evidence_ids for item in evidence_ids if item is not None
            ):
                _raise(
                    "invalid_evidence_ids",
                    "parser_semantic_invalid",
                    "additional_fields cites evidence_ids that are not in the OCR layout context.",
                )

    if ocr_context_has_usable_evidence(ocr_text=ocr_text, layout_context=layout_context):
        if _all_known_fields_missing(payload) and not _has_any_additional_value(payload):
            # Evidence-bound mode may legitimately map nothing when candidates lack matches.
            if not evidence_bound:
                _raise(
                    "all_fields_missing",
                    "parser_all_fields_missing_with_ocr_evidence",
                    "All known fields are MISSING despite usable OCR evidence.",
                )

    return []


def _validate_candidate_ids(field_obj: dict[str, Any], *, known_ids: set[str]) -> None:
    candidate_ids = field_obj.get("candidate_ids") or []
    if not isinstance(candidate_ids, list) or not candidate_ids:
        _raise(
            "missing_candidate_ids",
            "parser_semantic_invalid",
            "Evidence-bound field mapping is missing candidate_ids.",
        )
    if known_ids and any(str(item) not in known_ids for item in candidate_ids if item is not None):
        _raise(
            "invalid_candidate_ids",
            "parser_semantic_invalid",
            "Parser field cites candidate_ids that are not in the evidence bundle.",
        )


def _all_known_fields_missing(payload: dict[str, Any]) -> bool:
    for key in PAYSLIP_FIELD_KEYS:
        raw = payload.get(key)
        if not isinstance(raw, dict):
            return False
        status = _status_of(raw)
        if status != "MISSING":
            return False
        if raw.get("value") not in (None, ""):
            return False
        candidate_ids = raw.get("candidate_ids") or []
        if isinstance(candidate_ids, list) and candidate_ids:
            return False
    return True


def _has_any_additional_value(payload: dict[str, Any]) -> bool:
    additional = payload.get("additional_fields")
    if not isinstance(additional, dict):
        return False
    for raw in additional.values():
        if not isinstance(raw, dict):
            continue
        expanded = expand_simplified_field(raw)
        if expanded.get("value") not in (None, ""):
            return True
    return False
