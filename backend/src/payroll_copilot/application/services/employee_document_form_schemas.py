"""Fixed Digital Form schemas for Employee ID Card and ID Appendix."""

from __future__ import annotations

from typing import Any

from payroll_copilot.domain.enums import DocumentType

NATIONAL_ID_KEYS = (
    "full_name",
    "national_id",
    "birth_date",
)

ID_APPENDIX_KEYS = (
    "marital_status",
    "number_of_children",
    "residency_status",
    "citizenship",
)


def fixed_keys_for(document_type: DocumentType | str) -> tuple[str, ...] | None:
    value = document_type.value if hasattr(document_type, "value") else str(document_type)
    if value == DocumentType.NATIONAL_ID.value:
        return NATIONAL_ID_KEYS
    if value == DocumentType.ID_APPENDIX.value:
        return ID_APPENDIX_KEYS
    return None


def empty_fixed_structured(document_type: DocumentType | str) -> dict[str, Any]:
    keys = fixed_keys_for(document_type) or ()
    return {
        "additional_fields": {
            key: {
                "value": None,
                "confidence": None,
                "source_text": None,
                "status": "MISSING",
                "edited_by_user": False,
                "original_value": None,
            }
            for key in keys
        }
    }


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
            flat[str(key)] = payload

    # Migrate older national-id extractions that used date_of_birth.
    if "birth_date" not in flat and isinstance(flat.get("date_of_birth"), dict):
        flat["birth_date"] = flat["date_of_birth"]

    out: dict[str, Any] = {}
    for key in keys:
        payload = flat.get(key)
        if not isinstance(payload, dict):
            out[key] = {
                "value": None,
                "confidence": None,
                "source_text": None,
                "status": "MISSING",
                "edited_by_user": False,
                "original_value": None,
            }
            continue
        value = payload.get("value")
        status = str(payload.get("status") or ("FOUND" if value not in (None, "") else "MISSING"))
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
                "confidence": 1.0 if value not in (None, "") else None,
                "source_text": item.get("source_text"),
                "status": "FOUND" if value not in (None, "") else "MISSING",
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
    for key in keys:
        item = by_key.get(key) or {}
        value = item.get("value")
        additional[key] = {
            "value": value,
            "confidence": 1.0 if value not in (None, "") else None,
            "source_text": item.get("source_text"),
            "status": "FOUND" if value not in (None, "") else "MISSING",
            "edited_by_user": True,
            "original_value": item.get("original_value"),
        }
    return {"additional_fields": additional}
