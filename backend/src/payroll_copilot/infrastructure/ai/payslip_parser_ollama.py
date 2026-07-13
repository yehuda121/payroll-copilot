"""Ollama-backed payslip parser (layout-aware when context provided).

JSON handling is local to this adapter so other Ollama consumers are unchanged.
Does not use hardcoded overall confidence (no 0.9 invention).
Does not embed Pydantic JSON Schema ($ref/$defs) in the model prompt.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from payroll_copilot.application.exceptions import (
    PayslipParserEmptyOcrError,
    PayslipParserJsonError,
    PayslipParserSchemaError,
    PayslipParserSemanticError,
    PayslipParserUnavailableError,
)
from payroll_copilot.application.ports.payslip_parser import (
    PAYSLIP_FIELD_KEYS,
    ExtractedField,
    FieldExtractionStatus,
    PayslipParseResult,
    StructuredPayslipParse,
)
from payroll_copilot.application.services.parser_semantic import (
    is_invalid_additional_field_key,
    normalize_payslip_parser_payload,
    validate_payslip_parser_payload,
)

logger = logging.getLogger(__name__)

_PROMPT_CANDIDATES = (
    Path(__file__).resolve().parents[4] / "config" / "prompts" / "payslip_extractor" / "system.md",
    Path.cwd() / "config" / "prompts" / "payslip_extractor" / "system.md",
    Path.cwd() / "backend" / "config" / "prompts" / "payslip_extractor" / "system.md",
)

_FALLBACK_SYSTEM_PROMPT = """You are a multilingual payslip field extractor.
Return STRICT JSON instance only using the provided field names.
Do not invent values. Use status MISSING when absent, UNCERTAIN when unsure.
Never return JSON Schema, $ref, or $defs. Never use OCR values as JSON keys.
Never invent confidence. Hebrew/English/Arabic. No payroll validation.
"""

_MISSING_FIELD_INSTANCE: dict[str, Any] = {
    "value": None,
    "confidence": None,
    "source_text": None,
    "status": "MISSING",
    "evidence_ids": [],
    "source_bbox": None,
    "source_page": None,
    "parser_method": "layout_llm",
    "warnings": [],
    "normalized_value": None,
}

_SEMANTIC_RETRY_INSTRUCTION = (
    "Your previous response was valid JSON but semantically invalid because it returned "
    "schema definitions or invalid field keys. Return a JSON instance using only the "
    "required payroll field names. Do not return $ref, $defs, schema metadata, raw OCR "
    "values as keys, or explanatory text."
)


def _load_system_prompt() -> str:
    for path in _PROMPT_CANDIDATES:
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8")
        except OSError:
            continue
    return _FALLBACK_SYSTEM_PROMPT


def build_payslip_instance_template(*, language: str | None = None) -> dict[str, Any]:
    """Compact JSON instance template (no $ref / $defs / schema keywords)."""
    template: dict[str, Any] = {
        key: dict(_MISSING_FIELD_INSTANCE) for key in PAYSLIP_FIELD_KEYS
    }
    template["additional_fields"] = {}
    template["parser_notes"] = None
    template["language"] = language
    return template


def _strip_json_fences(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _parse_json_object(content: str) -> dict[str, Any]:
    cleaned = _strip_json_fences(content)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError as nested:
                raise PayslipParserJsonError(
                    f"Model did not return valid JSON: {exc}"
                ) from nested
        else:
            raise PayslipParserJsonError(f"Model did not return valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise PayslipParserJsonError("Model JSON root must be an object.")
    return payload


def _normalize_field_payload(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict) and ("$ref" in raw or "$defs" in raw):
        raise PayslipParserSemanticError(
            "Field object contains schema $ref/$defs and cannot be coerced.",
            category="schema_stub_field",
            warning_code="parser_schema_copy_detected",
        )
    if raw is None:
        raise PayslipParserSemanticError(
            "Required field is null; expected a field instance object.",
            category="invalid_field_object",
            warning_code="parser_semantic_invalid",
        )
    if not isinstance(raw, dict):
        return {
            "value": raw,
            "confidence": None,
            "source_text": None,
            "status": FieldExtractionStatus.UNCERTAIN.value,
            "evidence_ids": [],
            "source_bbox": None,
            "source_page": None,
            "parser_method": "layout_llm",
            "warnings": [],
            "normalized_value": None,
        }
    if "status" not in raw or "value" not in raw:
        raise PayslipParserSemanticError(
            "Field object missing required value/status keys.",
            category="invalid_field_object",
            warning_code="parser_semantic_invalid",
        )
    status = raw.get("status", FieldExtractionStatus.MISSING.value)
    if isinstance(status, str):
        status = status.strip().upper()
    evidence_ids = raw.get("evidence_ids") or []
    if not isinstance(evidence_ids, list):
        evidence_ids = []
    warnings = raw.get("warnings") or []
    if not isinstance(warnings, list):
        warnings = []
    return {
        "value": raw.get("value"),
        "confidence": raw.get("confidence"),
        "source_text": raw.get("source_text"),
        "status": status,
        "evidence_ids": [str(item) for item in evidence_ids if item is not None],
        "source_bbox": raw.get("source_bbox"),
        "source_page": raw.get("source_page"),
        "parser_method": raw.get("parser_method") or "layout_llm",
        "warnings": [str(item) for item in warnings],
        "normalized_value": raw.get("normalized_value"),
    }


def coerce_structured_payslip(payload: dict[str, Any]) -> StructuredPayslipParse:
    """Normalize validated model JSON into StructuredPayslipParse.

    Assumes semantic validation already ran for the Ollama parse path.
    Still rejects `$ref` stubs and invalid additional_fields keys defensively.
    Does not promote unknown top-level keys into additional_fields.
    """
    if not isinstance(payload, dict):
        raise PayslipParserSchemaError("Payslip payload must be an object.")

    fields: dict[str, Any] = {}
    for key in PAYSLIP_FIELD_KEYS:
        if key not in payload:
            raise PayslipParserSemanticError(
                f"Required field '{key}' missing before coercion.",
                category="missing_required_fields",
                warning_code="parser_missing_required_fields",
            )
        fields[key] = ExtractedField.model_validate(_normalize_field_payload(payload[key]))

    additional_raw = payload.get("additional_fields")
    if additional_raw is None:
        additional_raw = {}
    if not isinstance(additional_raw, dict):
        raise PayslipParserSemanticError(
            "additional_fields must be an object.",
            category="invalid_additional_fields",
            warning_code="parser_invalid_additional_field_key",
        )

    additional: dict[str, ExtractedField] = {}
    for name, value in additional_raw.items():
        if not isinstance(name, str) or not name.strip():
            raise PayslipParserSemanticError(
                "additional_fields key must be a non-empty string.",
                category="invalid_additional_key",
                warning_code="parser_invalid_additional_field_key",
            )
        if name in PAYSLIP_FIELD_KEYS:
            continue
        if is_invalid_additional_field_key(name):
            raise PayslipParserSemanticError(
                "additional_fields contains a non-semantic key.",
                category="invalid_additional_key",
                warning_code="parser_invalid_additional_field_key",
            )
        additional[name] = ExtractedField.model_validate(_normalize_field_payload(value))

    return StructuredPayslipParse(
        **fields,
        additional_fields=additional,
        parser_notes=payload.get("parser_notes") if isinstance(payload.get("parser_notes"), str) else None,
        language=payload.get("language") if isinstance(payload.get("language"), str) else None,
    )


class OllamaPayslipParser:
    """PayslipParser implementation using local Ollama chat API."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 180.0,
        temperature: float = 0.0,
        use_json_format: bool = True,
        layout_enabled: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature
        self._use_json_format = use_json_format
        self._layout_enabled = layout_enabled
        self._system_prompt = _load_system_prompt()

    async def parse(
        self,
        *,
        ocr_text: str,
        language: str = "auto",
        pages_text: list[str] | None = None,
        layout_context: dict[str, object] | None = None,
        retry_hint: str | None = None,
    ) -> PayslipParseResult:
        if not ocr_text or not ocr_text.strip():
            raise PayslipParserEmptyOcrError()

        layout_payload = layout_context if self._layout_enabled else None
        user_content = self._build_user_prompt(
            ocr_text=ocr_text,
            language=language,
            pages_text=pages_text,
            layout_context=layout_payload,
            retry_hint=retry_hint,
        )
        context_chars = (
            len(json.dumps(layout_payload, ensure_ascii=False)) if layout_payload else 0
        )
        logger.debug(
            "payslip_parser_request model=%s language=%s ocr_chars=%s layout=%s "
            "context_chars=%s retry=%s",
            self._model,
            language,
            len(ocr_text),
            bool(layout_payload),
            context_chars,
            bool(retry_hint),
        )

        raw_content, model_name = await self._chat(user_content)
        warnings: list[str] = []
        try:
            payload = _parse_json_object(raw_content)
            payload, normalize_warnings = normalize_payslip_parser_payload(payload)
            warnings.extend(normalize_warnings)
            validate_payslip_parser_payload(
                payload,
                ocr_text=ocr_text,
                layout_context=layout_payload if isinstance(layout_payload, dict) else None,
            )
            fields = coerce_structured_payslip(payload)
        except PayslipParserJsonError:
            raise
        except PayslipParserSemanticError as exc:
            logger.info(
                "payslip_parser_semantic_reject model=%s category=%s warning=%s retry=%s",
                self._model,
                exc.category,
                exc.warning_code,
                bool(retry_hint),
            )
            raise
        except Exception as exc:  # noqa: BLE001 — schema failures
            raise PayslipParserSchemaError(f"Payslip schema validation failed: {exc}") from exc

        if fields.language is None:
            fields = fields.model_copy(update={"language": language})

        return PayslipParseResult(
            model=model_name,
            language=fields.language or language,
            fields=fields,
            raw_model_response=raw_content,
            warnings=warnings,
            retry_used=bool(retry_hint),
        )

    def _build_user_prompt(
        self,
        *,
        ocr_text: str,
        language: str,
        pages_text: list[str] | None,
        layout_context: dict[str, object] | None,
        retry_hint: str | None,
    ) -> str:
        pages_block = ""
        if pages_text:
            chunks = []
            for index, page in enumerate(pages_text, start=1):
                chunks.append(f"--- PAGE {index} ---\n{page}")
            pages_block = "\n\n".join(chunks)

        retry_block = ""
        if retry_hint:
            retry_block = (
                "\n\nPREVIOUS RESPONSE WAS INVALID.\n"
                f"{_SEMANTIC_RETRY_INSTRUCTION}\n"
                f"Error summary: {retry_hint}\n"
                "Return corrected STRICT JSON instance only. No markdown. No commentary.\n"
            )

        layout_block = ""
        if layout_context:
            layout_block = (
                "\nLAYOUT OCR CONTEXT (authoritative evidence; use evidence ids):\n"
                f"{json.dumps(layout_context, ensure_ascii=False)}\n"
            )

        allowed = ", ".join(PAYSLIP_FIELD_KEYS)
        template = build_payslip_instance_template(
            language=language if language != "auto" else None
        )
        template_json = json.dumps(template, ensure_ascii=False, indent=2)

        return (
            f"Document language hint: {language}\n"
            "Extract payslip fields from the OCR evidence below.\n"
            "Use coordinates and nearby labels when layout context is present.\n"
            f"{retry_block}\n"
            f"{layout_block}\n"
            "OCR TEXT (fallback / full page text):\n"
            f"{pages_block or ocr_text}\n\n"
            f"Allowed known field names (return each exactly once as a top-level key): {allowed}\n\n"
            "CRITICAL: Your entire response must be ONE JSON object matching the instance "
            "template below. Do NOT return OCR blocks, layout objects, schema definitions, "
            "$ref, $defs, block_type, pages, lines, or words as the root.\n"
            "Do NOT rename fields (use employee_name, not name). Do NOT add parser_version.\n"
            "The template status MISSING is only the default shape. "
            "When OCR/layout evidence shows a value, you MUST set status FOUND or UNCERTAIN, "
            "copy source_text from OCR, and cite evidence_ids from the layout context. "
            "Returning every field as MISSING while amounts/labels are visible in OCR is invalid.\n"
            "Map visible amounts to the correct semantic fields when labels support it. "
            "Never invent digits, never invent employee names, never invent net from gross.\n"
            f"{template_json}\n"
            "Return the populated JSON instance now. No markdown. No commentary.\n"
        )

    async def _chat(self, user_content: str) -> tuple[str, str]:
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_content},
        ]
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self._temperature,
                "num_predict": 8192,
            },
        }
        if self._use_json_format:
            payload["format"] = "json"

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(f"{self._base_url}/api/chat", json=payload)
                if response.status_code >= 400 and self._use_json_format and "format" in payload:
                    payload.pop("format", None)
                    response = await client.post(f"{self._base_url}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.exception("Ollama payslip parser request failed")
            raise PayslipParserUnavailableError(
                f"Ollama payslip parser unavailable: {exc}"
            ) from exc

        content = data.get("message", {}).get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise PayslipParserJsonError("Ollama returned an empty response.")
        return content, self._model
