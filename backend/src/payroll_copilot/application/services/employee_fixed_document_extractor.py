"""Semantic fixed-schema extraction for Employee ID Card and ID Appendix."""

from __future__ import annotations

import json
import re
from typing import Any

from payroll_copilot.application.exceptions import (
    PayslipParserEmptyOcrError,
    PayslipParserJsonError,
    PayslipParserUnavailableError,
)
from payroll_copilot.application.ports import AICapability, Message
from payroll_copilot.application.services.employee_document_form_schemas import (
    empty_fixed_structured,
    fixed_keys_for,
    normalize_children_list,
)
from payroll_copilot.domain.enums import DocumentType
from payroll_copilot.infrastructure.ai.provider_router import AIProviderRouter
from payroll_copilot.infrastructure.config.settings import get_settings

_ID_CARD_SYSTEM = """
You are a semantic mapper, NOT a generator.

The OCR text already contains the values. Your only job is to assign OCR values
to the fixed schema. Never invent, translate, transliterate, or normalize names.

Return ONLY valid JSON with exactly these keys and string values:
{
  "full_name": "",
  "national_id": "",
  "birth_date": ""
}

No other keys. No explanations. No markdown.

Grounding rules:
- Every returned value MUST appear in the OCR text (or be a direct concatenation
  of OCR values such as first name + last name).
- If a value is not explicitly supported by the OCR text, return "".
- Never invent English names. Never translate Hebrew names.
- Never use outside knowledge.

full_name:
- Israeli IDs usually have Family Name / First Name or שם משפחה / שם פרטי.
- Combine them as: "<first name> <family name>" using the OCR spellings exactly.
- Example OCR: שם פרטי יהודה + שם משפחה שמולביץ → "יהודה שמולביץ"

national_id:
- Return the identity number exactly as printed in OCR.
- Do not reformat.

birth_date:
- Israeli IDs often show BOTH a Hebrew calendar date and a Gregorian date.
- Return ONLY the Gregorian date exactly as printed (e.g. 25.11.1994).
- Never return the Hebrew date (e.g. כ"ב בכסלו תשנ"ה).
""".strip()

_ID_APPENDIX_SYSTEM = """
You extract children listed on an Israeli ID appendix (ספח) from OCR text.

Return STRICT JSON only. No markdown. No commentary.

Output shape:
{
  "children": [
    {"name": string, "birth_date": string}
  ]
}

Rules:
- Extract ONLY child full name and Gregorian birth date for each child.
- Ignore marital status, residency, citizenship, addresses, spouse details,
  national IDs, Hebrew calendar dates, and any other appendix information.
- Do NOT return number_of_children or a children count field.
- Use OCR spellings exactly. Never invent children.
- If no children are present, return {"children": []}.
- birth_date must be Gregorian as printed (e.g. 12.03.2015), or "" if unknown.
""".strip()

_HEBREW_LETTER = re.compile(r"[\u0590-\u05FF]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
_HEBREW_DATE_MARKERS = re.compile(
    r"תש[א-ת\"׳']{0,4}"
    r"|בניסן|באייר|בסיון|בתמוז|באב|באלול|בתשרי|בחשון|בכסלו|בטבת|בשבט|באדר"
    r"|למניין|לחודש|בשנת"
)
_GREGORIAN_DATE = re.compile(
    r"^\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}$"
    r"|^\d{4}[./\-]\d{1,2}[./\-]\d{1,2}$"
)
_TOKEN = re.compile(r"[\w\u0590-\u05FF]+", re.UNICODE)


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise PayslipParserJsonError(
                "Fixed document extractor returned non-JSON content."
            ) from None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise PayslipParserJsonError(
                "Fixed document extractor returned invalid JSON."
            ) from exc
    if not isinstance(payload, dict):
        raise PayslipParserJsonError("Fixed document extractor JSON root must be an object.")
    return payload


def _as_confidence(raw: Any) -> float | None:
    try:
        confidence = float(raw) if raw is not None and raw != "" else None
    except (TypeError, ValueError):
        return None
    if confidence is not None and (confidence < 0 or confidence > 1):
        return None
    return confidence


def _scalar_string(payload: Any) -> str:
    value = payload.get("value") if isinstance(payload, dict) and "value" in payload else payload
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _field_payload(value: str, *, source_text: str | None = None) -> dict[str, Any]:
    cleaned = value.strip() if value else ""
    if not cleaned:
        return {
            "value": None,
            "confidence": None,
            "source_text": None,
            "status": "MISSING",
            "edited_by_user": False,
            "original_value": None,
        }
    return {
        "value": cleaned,
        "confidence": 1.0,
        "source_text": source_text,
        "status": "FOUND",
        "edited_by_user": False,
        "original_value": cleaned,
    }


def _normalize_field_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and "value" in payload:
        value = payload.get("value")
        if isinstance(value, str):
            value = value.strip() or None
        status = "FOUND" if value not in (None, "") else "MISSING"
        source = payload.get("source_text")
        return {
            "value": value,
            "confidence": _as_confidence(payload.get("confidence")) if status == "FOUND" else None,
            "source_text": source if isinstance(source, str) else None,
            "status": status,
            "edited_by_user": False,
            "original_value": value,
        }
    if payload is None or (isinstance(payload, str) and not payload.strip()):
        return {
            "value": None,
            "confidence": None,
            "source_text": None,
            "status": "MISSING",
            "edited_by_user": False,
            "original_value": None,
        }
    value = payload.strip() if isinstance(payload, str) else payload
    return {
        "value": value,
        "confidence": None,
        "source_text": None,
        "status": "FOUND",
        "edited_by_user": False,
        "original_value": value,
    }


def _normalize_children_field_payload(payload: Any) -> dict[str, Any]:
    raw = payload.get("value") if isinstance(payload, dict) and "value" in payload else payload
    if raw is None and isinstance(payload, dict) and "children" in payload:
        raw = payload.get("children")
    children = normalize_children_list(raw)
    if not children:
        return {
            "value": [],
            "confidence": None,
            "source_text": None,
            "status": "MISSING",
            "edited_by_user": False,
            "original_value": [],
        }
    confidence = None
    source = None
    if isinstance(payload, dict):
        confidence = _as_confidence(payload.get("confidence"))
        source_raw = payload.get("source_text")
        source = source_raw if isinstance(source_raw, str) else None
    return {
        "value": children,
        "confidence": confidence if confidence is not None else 1.0,
        "source_text": source,
        "status": "FOUND",
        "edited_by_user": False,
        "original_value": children,
    }


def is_valid_israeli_id(raw: str) -> bool:
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


def _ocr_contains(value: str, ocr_text: str) -> bool:
    if not value:
        return False
    if value in ocr_text:
        return True
    compact_value = re.sub(r"\s+", "", value)
    compact_ocr = re.sub(r"\s+", "", ocr_text)
    if compact_value and compact_value in compact_ocr:
        return True
    tokens = [token for token in _TOKEN.findall(value) if len(token) >= 2]
    if not tokens:
        return False
    return all(token in ocr_text for token in tokens)


def ground_id_card_values(
    *,
    full_name: str,
    national_id: str,
    birth_date: str,
    ocr_text: str,
) -> dict[str, str]:
    """Reject hallucinated ID Card values; return empty strings when invalid."""
    grounded = {"full_name": "", "national_id": "", "birth_date": ""}

    name = (full_name or "").strip()
    if name:
        ocr_has_hebrew = bool(_HEBREW_LETTER.search(ocr_text))
        ocr_has_latin = bool(_LATIN_LETTER.search(ocr_text))
        name_has_latin = bool(_LATIN_LETTER.search(name))
        name_has_hebrew = bool(_HEBREW_LETTER.search(name))
        latin_only_hallucination = name_has_latin and ocr_has_hebrew and not ocr_has_latin
        tokens = [token for token in _TOKEN.findall(name) if len(token) >= 2]
        if not latin_only_hallucination and (
            _ocr_contains(name, ocr_text)
            or (name_has_hebrew and tokens and all(token in ocr_text for token in tokens))
        ):
            grounded["full_name"] = name

    identity = (national_id or "").strip()
    if identity and is_valid_israeli_id(identity):
        digits = re.sub(r"\D", "", identity)
        if digits in re.sub(r"\D", "", ocr_text) or identity in ocr_text:
            grounded["national_id"] = identity

    birth = (birth_date or "").strip()
    if birth and not _HEBREW_DATE_MARKERS.search(birth) and _GREGORIAN_DATE.match(birth):
        if birth in ocr_text or re.sub(r"[.\-/]", "", birth) in re.sub(r"[.\-/]", "", ocr_text):
            grounded["birth_date"] = birth
        else:
            # Accept if day/month/year parts are all present nearby in OCR.
            parts = [part for part in re.split(r"[.\-/]", birth) if part]
            if parts and all(part in ocr_text for part in parts):
                grounded["birth_date"] = birth

    return grounded


def structured_from_semantic_payload(
    document_type: DocumentType | str,
    payload: dict[str, Any],
    *,
    ocr_text: str | None = None,
) -> dict[str, Any]:
    """Normalize LLM fixed-schema JSON into persisted structured_data."""
    keys = fixed_keys_for(document_type)
    if keys is None:
        raise ValueError("document_type does not use a fixed semantic schema")
    source = payload.get("fields") if isinstance(payload.get("fields"), dict) else payload
    dtype = document_type.value if hasattr(document_type, "value") else str(document_type)

    if dtype == DocumentType.NATIONAL_ID.value:
        raw_name = _scalar_string(source.get("full_name"))
        raw_id = _scalar_string(source.get("national_id"))
        raw_birth = _scalar_string(
            source.get("birth_date")
            if source.get("birth_date") not in (None, "")
            else source.get("date_of_birth")
        )
        grounded = ground_id_card_values(
            full_name=raw_name,
            national_id=raw_id,
            birth_date=raw_birth,
            ocr_text=ocr_text or "",
        )
        return {
            "additional_fields": {
                "full_name": _field_payload(grounded["full_name"]),
                "national_id": _field_payload(grounded["national_id"]),
                "birth_date": _field_payload(grounded["birth_date"]),
            }
        }

    if dtype == DocumentType.ID_APPENDIX.value:
        children_raw = source.get("children")
        return {
            "additional_fields": {
                "children": _normalize_children_field_payload(children_raw),
            }
        }

    additional: dict[str, Any] = {}
    for key in keys:
        additional[key] = _normalize_field_payload(source.get(key))
    return {"additional_fields": additional}


def fixed_structured_has_usable_values(structured: dict[str, Any]) -> bool:
    additional = structured.get("additional_fields")
    if not isinstance(additional, dict):
        return False
    for payload in additional.values():
        if not isinstance(payload, dict):
            continue
        value = payload.get("value")
        if str(payload.get("status") or "").upper() == "MISSING":
            continue
        if isinstance(value, list) and len(value) > 0:
            return True
        if value not in (None, ""):
            return True
    return False


class EmployeeFixedDocumentExtractor:
    """OCR text → semantic mapping directly into fixed Digital Form schemas."""

    def __init__(self, *, model_provider: Any | None = None) -> None:
        settings = get_settings()
        router = AIProviderRouter(settings)
        self._provider = model_provider or router.provider_for(
            AICapability.DOCUMENT_EXTRACTION
        )
        self._model = router.model_for(AICapability.DOCUMENT_EXTRACTION)

    async def extract(
        self,
        *,
        ocr_text: str,
        language: str,
        document_type: DocumentType | str,
        pages_text: list[str] | None = None,
    ) -> tuple[dict[str, Any], str, list[str]]:
        dtype = document_type.value if hasattr(document_type, "value") else str(document_type)
        if dtype not in {DocumentType.NATIONAL_ID.value, DocumentType.ID_APPENDIX.value}:
            raise ValueError(f"Unsupported fixed extraction type: {dtype}")
        if not (ocr_text or "").strip():
            raise PayslipParserEmptyOcrError()

        pages_block = ""
        if pages_text:
            pages_block = "\n\n".join(
                f"--- PAGE {index} ---\n{text}"
                for index, text in enumerate(pages_text, start=1)
                if text
            )
        document_text = pages_block or ocr_text
        system = _ID_CARD_SYSTEM if dtype == DocumentType.NATIONAL_ID.value else _ID_APPENDIX_SYSTEM
        if dtype == DocumentType.NATIONAL_ID.value:
            user_prompt = (
                f"Document language hint: {language}\n\n"
                f"OCR TEXT:\n{document_text}\n\n"
                "Map OCR values into ONLY:\n"
                '{"full_name":"","national_id":"","birth_date":""}\n'
                "Use OCR values only. Combine first+family name for full_name. "
                "Use Gregorian birth date only. Empty string when unsupported."
            )
        else:
            user_prompt = (
                f"Document language hint: {language}\n\n"
                f"OCR TEXT:\n{document_text}\n\n"
                "Extract ONLY children as:\n"
                '{"children":[{"name":"","birth_date":""}]}\n'
                "Ignore all other appendix fields. Empty list when none found."
            )
        try:
            result = await self._provider.complete(
                [
                    Message(role="system", content=system),
                    Message(role="user", content=user_prompt),
                ],
                temperature=0.0,
                max_tokens=1024 if dtype == DocumentType.NATIONAL_ID.value else 2048,
                json_mode=True,
            )
        except Exception as exc:
            raise PayslipParserUnavailableError(
                f"Fixed document extractor LLM unavailable: {exc}"
            ) from exc

        content = result.content if isinstance(result.content, str) else ""
        if not content.strip():
            raise PayslipParserJsonError("Fixed document extractor returned an empty response.")

        structured = structured_from_semantic_payload(
            dtype,
            _parse_json_object(content),
            ocr_text=document_text,
        )
        warnings: list[str] = []
        if not fixed_structured_has_usable_values(structured):
            warnings.append("fixed_document_extractor_no_usable_entries")
            structured = empty_fixed_structured(dtype)
        return structured, result.model or self._model, warnings
