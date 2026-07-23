"""Fixed Digital Form schemas for Employee ID Card and ID Appendix."""

from __future__ import annotations

from typing import Any

from payroll_copilot.domain.enums import DocumentType

NATIONAL_ID_KEYS = (
    "full_name",
    "national_id",
    "birth_date",
)

# Appendix stores only a children collection. Count is derived from len(children).
ID_APPENDIX_KEYS = ("children",)

_LEGACY_APPENDIX_KEYS = frozenset(
    {
        "marital_status",
        "number_of_children",
        "residency_status",
        "citizenship",
    }
)


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


def normalize_children_list(raw: Any) -> list[dict[str, str]]:
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
        name = str(name_raw).strip() if name_raw not in (None, "") else ""
        birth = str(birth_raw).strip() if birth_raw not in (None, "") else ""
        if not name and not birth:
            continue
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
    for key in keys:
        item = by_key.get(key) or {}
        value = item.get("value")
        if key == "children":
            value = normalize_children_list(value)
        additional[key] = {
            "value": value if key != "children" else value,
            "confidence": 1.0 if _value_present(value) else None,
            "source_text": item.get("source_text"),
            "status": "FOUND" if _value_present(value) else "MISSING",
            "edited_by_user": True,
            "original_value": item.get("original_value"),
        }
    return {"additional_fields": additional}
