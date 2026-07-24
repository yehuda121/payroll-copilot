"""Fixed Digital Form schemas for Employee ID Card and ID Appendix."""

from __future__ import annotations

import re
from typing import Any

from payroll_copilot.domain.enums import DocumentType

NATIONAL_ID_KEYS = (
    "full_name",
    "national_id",
    "birth_date",
)

# Appendix stores only a children collection. Count is derived from len(children).
ID_APPENDIX_KEYS = ("children",)

PERSON_NAME_MAX_LENGTH = 120
NATIONAL_ID_LENGTH = 9

_LEGACY_APPENDIX_KEYS = frozenset(
    {
        "marital_status",
        "number_of_children",
        "residency_status",
        "citizenship",
    }
)

_HAS_DIGIT = re.compile(r"\d")
_BIRTH_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_BIRTH_DMY = re.compile(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$")
_BIRTH_YMD = re.compile(r"^(\d{4})[./-](\d{1,2})[./-](\d{1,2})$")


class FixedDocumentFormValidationError(ValueError):
    """Raised when manual fixed-form values fail domain validation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _is_valid_israeli_id(raw: str) -> bool:
    """Same checksum as employee_fixed_document_extractor.is_valid_israeli_id."""
    digits = re.sub(r"\D", "", raw or "")
    if not digits or len(digits) > 9:
        return False
    digits = digits.zfill(9)
    if digits == "000000000":
        return False
    total = 0
    for index, char in enumerate(digits):
        product = int(char) * (1 if index % 2 == 0 else 2)
        total += product if product < 10 else product - 9
    return total % 10 == 0


def fixed_keys_for(document_type: DocumentType | str) -> tuple[str, ...] | None:
    value = document_type.value if hasattr(document_type, "value") else str(document_type)
    if value == DocumentType.NATIONAL_ID.value:
        return NATIONAL_ID_KEYS
    if value == DocumentType.ID_APPENDIX.value:
        return ID_APPENDIX_KEYS
    return None


def _empty_field(*, value: Any = None) -> dict[str, Any]:
    return {
        "value": value,
        "confidence": None,
        "source_text": None,
        "status": "MISSING",
        "edited_by_user": False,
        "original_value": value,
    }


def normalize_human_text(raw: str) -> str:
    text = re.sub(r"[\t\n\r\f\v]+", " ", raw or "")
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _is_valid_ymd(year: int, month: int, day: int) -> bool:
    if year < 1900 or year > 2100 or month < 1 or month > 12 or day < 1 or day > 31:
        return False
    try:
        from datetime import date

        date(year, month, day)
    except ValueError:
        return False
    return True


def normalize_birth_date(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    match = _BIRTH_ISO.match(text) or _BIRTH_YMD.match(text)
    if match:
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if _is_valid_ymd(year, month, day):
            return f"{year:04d}-{month:02d}-{day:02d}"
        return None
    match = _BIRTH_DMY.match(text)
    if match:
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if _is_valid_ymd(year, month, day):
            return f"{year:04d}-{month:02d}-{day:02d}"
        return None
    return None


def validate_person_name(raw: str) -> str:
    value = normalize_human_text(raw)
    if not value:
        return ""
    if len(value) > PERSON_NAME_MAX_LENGTH:
        raise FixedDocumentFormValidationError(
            "name_max_length",
            f"Name exceeds maximum length of {PERSON_NAME_MAX_LENGTH}.",
        )
    if _HAS_DIGIT.search(value):
        raise FixedDocumentFormValidationError(
            "name_digits",
            "Names cannot contain digits.",
        )
    # Strip digits-from-\w by rejecting any remaining non letter/mark/sep chars loosely:
    # Require at least one letter-like character and no digits (already checked).
    letters = re.sub(r"[\s'\u2019-]+", "", value)
    if not letters or not re.search(r"[^\W\d_]", letters, re.UNICODE):
        raise FixedDocumentFormValidationError("name_invalid", "Enter a valid person name.")
    return value


def validate_national_id_value(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if re.search(r"\D", text):
        raise FixedDocumentFormValidationError(
            "national_id_digits",
            "National ID must contain digits only.",
        )
    if len(text) != NATIONAL_ID_LENGTH:
        raise FixedDocumentFormValidationError(
            "national_id_length",
            "National ID must be exactly 9 digits.",
        )
    if not _is_valid_israeli_id(text):
        raise FixedDocumentFormValidationError(
            "national_id_checksum",
            "National ID checksum is invalid.",
        )
    return text


def normalize_children_list(raw: Any, *, validate: bool = False) -> list[dict[str, str]]:
    """Keep only {name, birth_date} child rows. Drop unrelated / legacy data."""
    if isinstance(raw, dict) and "children" in raw:
        raw = raw.get("children")
    if not isinstance(raw, list):
        return []
    children: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name_raw = item.get("name")
        if name_raw in (None, ""):
            name_raw = item.get("child_name")
        birth_raw = item.get("birth_date")
        if birth_raw in (None, ""):
            birth_raw = item.get("date_of_birth")
        name = normalize_human_text(str(name_raw)) if name_raw not in (None, "") else ""
        birth = str(birth_raw).strip() if birth_raw not in (None, "") else ""
        if not name and not birth:
            continue
        if validate:
            if not name or not birth:
                raise FixedDocumentFormValidationError(
                    "child_incomplete",
                    "All fields are required for each child.",
                )
            name = validate_person_name(name)
            normalized_birth = normalize_birth_date(birth)
            if not normalized_birth:
                raise FixedDocumentFormValidationError(
                    "birth_date_invalid",
                    "Enter a valid birth date.",
                )
            birth = normalized_birth
        children.append({"name": name, "birth_date": birth})
    return children


def empty_fixed_structured(document_type: DocumentType | str) -> dict[str, Any]:
    keys = fixed_keys_for(document_type) or ()
    additional: dict[str, Any] = {}
    for key in keys:
        if key == "children":
            additional[key] = _empty_field(value=[])
        else:
            additional[key] = _empty_field()
    return {"additional_fields": additional}


def _value_present(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, list):
        return len(value) > 0
    return True


def project_fixed_structured(
    document_type: DocumentType | str,
    structured: dict[str, Any] | None,
) -> dict[str, Any]:
    """Keep only canonical fixed-schema keys already produced by semantic extraction/save."""
    keys = fixed_keys_for(document_type)
    if keys is None:
        return structured or {}
    source = dict(structured or {})
    additional = source.get("additional_fields")
    flat: dict[str, Any] = {}
    for key, payload in source.items():
        if key in {"additional_fields", "parser_notes", "language"}:
            continue
        flat[str(key)] = payload
    if isinstance(additional, dict):
        for key, payload in additional.items():
            # Drop legacy appendix scalars; do not invent children from counts.
            if str(key) in _LEGACY_APPENDIX_KEYS:
                continue
            flat[str(key)] = payload

    # Migrate older national-id extractions that used date_of_birth.
    if "birth_date" not in flat and isinstance(flat.get("date_of_birth"), dict):
        flat["birth_date"] = flat["date_of_birth"]

    out: dict[str, Any] = {}
    for key in keys:
        payload = flat.get(key)
        if key == "children":
            if not isinstance(payload, dict):
                out[key] = _empty_field(value=[])
                continue
            children = normalize_children_list(payload.get("value"))
            status = str(
                payload.get("status")
                or ("FOUND" if children else "MISSING")
            )
            out[key] = {
                "value": children,
                "confidence": payload.get("confidence") if children else None,
                "source_text": payload.get("source_text"),
                "status": status if children else "MISSING",
                "edited_by_user": bool(payload.get("edited_by_user", False)),
                "original_value": payload.get("original_value", children),
            }
            continue

        if not isinstance(payload, dict):
            out[key] = _empty_field()
            continue
        value = payload.get("value")
        status = str(
            payload.get("status") or ("FOUND" if _value_present(value) else "MISSING")
        )
        out[key] = {
            "value": value,
            "confidence": payload.get("confidence"),
            "source_text": payload.get("source_text"),
            "status": status,
            "edited_by_user": bool(payload.get("edited_by_user", False)),
            "original_value": payload.get("original_value", value),
        }
    return {"additional_fields": out}


def structured_from_fixed_fields(
    document_type: DocumentType | str,
    fields: list[dict[str, Any]],
) -> dict[str, Any]:
    keys = fixed_keys_for(document_type)
    if keys is None:
        additional: dict[str, Any] = {}
        for item in fields:
            key = str(item.get("key") or "").strip()
            if not key:
                continue
            value = item.get("value")
            additional[key] = {
                "value": value,
                "confidence": 1.0 if _value_present(value) else None,
                "source_text": item.get("source_text"),
                "status": "FOUND" if _value_present(value) else "MISSING",
                "edited_by_user": True,
                "original_value": item.get("original_value"),
            }
        return {"additional_fields": additional}

    by_key = {
        str(item.get("key") or "").strip(): item
        for item in fields
        if str(item.get("key") or "").strip()
    }
    additional = {}
    dtype = document_type.value if hasattr(document_type, "value") else str(document_type)
    for key in keys:
        item = by_key.get(key) or {}
        value = item.get("value")
        if key == "children":
            value = normalize_children_list(value, validate=True)
        elif key == "full_name" and isinstance(value, str):
            value = validate_person_name(value)
        elif key == "national_id" and isinstance(value, str):
            value = validate_national_id_value(value)
        elif key == "birth_date" and isinstance(value, str) and value.strip():
            normalized = normalize_birth_date(value)
            if not normalized:
                raise FixedDocumentFormValidationError(
                    "birth_date_invalid",
                    "Enter a valid birth date.",
                )
            value = normalized
        elif key == "birth_date" and isinstance(value, str):
            value = ""
        additional[key] = {
            "value": value if key != "children" else value,
            "confidence": 1.0 if _value_present(value) else None,
            "source_text": item.get("source_text"),
            "status": "FOUND" if _value_present(value) else "MISSING",
            "edited_by_user": True,
            "original_value": item.get("original_value"),
        }
    # dtype unused except for clarity in future extensions
    _ = dtype
    return {"additional_fields": additional}
