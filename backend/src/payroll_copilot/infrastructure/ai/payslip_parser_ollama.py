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
    expand_simplified_field,
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
    "source_text": None,
    "confidence": None,
}

_SIMPLE_FIELD_INSTANCE: dict[str, Any] = {
    "value": None,
    "source_text": None,
    "confidence": None,
}

_shared_http_client: httpx.AsyncClient | None = None

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


_GUEST_SIMPLE_FIELD_KEYS: tuple[str, ...] = (
    "employee_name",
    "employee_id",
    "national_id",
    "payroll_month",
    "gross_salary",
    "net_salary",
    "total_deductions",
    "total_payments",
    "bank_transfer",
)


def build_payslip_instance_template(
    *,
    language: str | None = None,
    simplified: bool = True,
    field_keys: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Compact JSON instance template (no $ref / $defs / schema keywords)."""
    stub = _SIMPLE_FIELD_INSTANCE if simplified else dict(_SIMPLE_FIELD_INSTANCE)
    keys = field_keys or PAYSLIP_FIELD_KEYS
    template: dict[str, Any] = {key: dict(stub) for key in keys}
    if not simplified:
        for key in keys:
            template[key].update(
                {
                    "status": "MISSING",
                    "evidence_ids": [],
                    "source_bbox": None,
                    "source_page": None,
                    "parser_method": "semantic_llm",
                    "warnings": [],
                    "normalized_value": None,
                }
            )
    if field_keys is None:
        template["additional_fields"] = {}
        template["parser_notes"] = None
    template["language"] = language
    return template


def _get_shared_http_client(timeout_seconds: float) -> httpx.AsyncClient:
    global _shared_http_client
    if _shared_http_client is None or _shared_http_client.is_closed:
        _shared_http_client = httpx.AsyncClient(timeout=timeout_seconds)
    return _shared_http_client


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


def _strip_trailing_commas(text: str) -> str:
    """Remove trailing commas before } or ] — common LLM JSON defect."""
    out: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            continue
        if ch in "}]" and out:
            # Drop whitespace and one trailing comma before closer
            while out and out[-1] in " \t\r\n":
                out.pop()
            if out and out[-1] == ",":
                out.pop()
        out.append(ch)
    return "".join(out)


def _close_truncated_json(text: str) -> str:
    """Best-effort close of truncated JSON objects/arrays outside strings."""
    in_string = False
    escape = False
    stack: list[str] = []
    for ch in text:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack and stack[-1] == ch:
            stack.pop()
    if in_string:
        text += '"'
    return text + "".join(reversed(stack))


def _parse_json_object(content: str) -> dict[str, Any]:
    cleaned = _strip_json_fences(content)
    candidates = [cleaned]
    stripped = cleaned.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        candidates.append(stripped[start : end + 1])
    if start >= 0:
        candidates.append(_close_truncated_json(stripped[start:]))

    last_error: Exception | None = None
    for candidate in candidates:
        for variant in (candidate, _strip_trailing_commas(candidate)):
            try:
                payload = json.loads(variant)
            except json.JSONDecodeError as exc:
                last_error = exc
                continue
            if isinstance(payload, dict):
                return payload
            last_error = PayslipParserJsonError("Model JSON root must be an object.")

    raise PayslipParserJsonError(
        f"Model did not return valid JSON: {last_error}"
    ) from last_error


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
        return expand_simplified_field(
            {"value": raw, "source_text": None, "confidence": None}
        )
    if "status" not in raw:
        return expand_simplified_field(raw)
    if "value" not in raw:
        raise PayslipParserSemanticError(
            "Field object missing required value key.",
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
        "parser_method": raw.get("parser_method") or "semantic_llm",
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


def coerce_partial_structured_payslip(payload: dict[str, Any]) -> StructuredPayslipParse:
    """Coerce valid canonical fields and ignore malformed ones."""
    if not isinstance(payload, dict):
        raise PayslipParserSchemaError("Payslip payload must be an object.")

    fields: dict[str, Any] = {}
    for key in PAYSLIP_FIELD_KEYS:
        if key not in payload:
            fields[key] = ExtractedField(status=FieldExtractionStatus.MISSING)
            continue
        try:
            fields[key] = ExtractedField.model_validate(_normalize_field_payload(payload[key]))
        except (PayslipParserSemanticError, Exception):  # noqa: BLE001
            fields[key] = ExtractedField(status=FieldExtractionStatus.MISSING)

    additional: dict[str, ExtractedField] = {}
    additional_raw = payload.get("additional_fields") or {}
    if isinstance(additional_raw, dict):
        for name, value in additional_raw.items():
            if not isinstance(name, str) or not name.strip() or name in PAYSLIP_FIELD_KEYS:
                continue
            if is_invalid_additional_field_key(name):
                continue
            try:
                additional[name] = ExtractedField.model_validate(_normalize_field_payload(value))
            except (PayslipParserSemanticError, Exception):  # noqa: BLE001
                continue

    return StructuredPayslipParse(
        **fields,
        additional_fields=additional,
        parser_notes=payload.get("parser_notes") if isinstance(payload.get("parser_notes"), str) else None,
        language=payload.get("language") if isinstance(payload.get("language"), str) else None,
    )


class OllamaPayslipParser:
    """PayslipParser implementation via ModelProvider (Bedrock or Ollama).

    Prompts and post-validation are unchanged; only the LLM transport differs.
    """

    def __init__(
        self,
        *,
        model_provider: Any,
        model: str,
        timeout_seconds: float = 45.0,
        temperature: float = 0.0,
        use_json_format: bool = True,
        layout_enabled: bool = True,
        max_predict: int = 4096,
    ) -> None:
        self._provider = model_provider
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature
        self._use_json_format = use_json_format
        self._layout_enabled = layout_enabled
        self._max_predict = max_predict
        self._system_prompt = _load_system_prompt()

    async def parse(
        self,
        *,
        ocr_text: str,
        language: str = "auto",
        pages_text: list[str] | None = None,
        layout_context: dict[str, object] | None = None,
        retry_hint: str | None = None,
        embedded_text_mode: bool = False,
        simple_guest_fields: bool = False,
    ) -> PayslipParseResult:
        if not ocr_text or not ocr_text.strip():
            raise PayslipParserEmptyOcrError()

        layout_payload = layout_context if self._layout_enabled and not embedded_text_mode else None
        user_content = self._build_user_prompt(
            ocr_text=ocr_text,
            language=language,
            pages_text=pages_text,
            layout_context=layout_payload,
            retry_hint=retry_hint,
            embedded_text_mode=embedded_text_mode,
            simple_guest_fields=simple_guest_fields,
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
                embedded_text_mode=embedded_text_mode,
            )
            fields = coerce_structured_payslip(payload)
        except PayslipParserJsonError:
            raise
        except PayslipParserSemanticError as tip_exc:
            logger.info(
                "payslip_parser_semantic_reject model=%s category=%s warning=%s retry=%s",
                self._model,
                tip_exc.category,
                tip_exc.warning_code,
                bool(retry_hint),
            )
            raise PayslipParserSemanticError(
                tip_exc.message,
                category=tip_exc.category,
                warning_code=tip_exc.warning_code,
                partial_payload=payload,
            ) from tip_exc
        except Exception as tip_exc:  # noqa: BLE001 — schema failures
            raise PayslipParserSchemaError(
                f"Payslip schema validation failed: {tip_exc}"
            ) from tip_exc

        if fields.language is None:
            fields = fields.model_copy(update={"language": language})

        return PayslipParseResult(
            model=model_name,
            language=fields.language or language,
            fields=fields,
            raw_model_response=raw_content,
            parsed_payload=payload,
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
        embedded_text_mode: bool = False,
        simple_guest_fields: bool = False,
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
                "\nOPTIONAL LAYOUT OCR CONTEXT (page/line references when helpful):\n"
                f"{json.dumps(layout_context, ensure_ascii=False)}\n"
            )

        if simple_guest_fields:
            field_keys = _GUEST_SIMPLE_FIELD_KEYS
            allowed = ", ".join(field_keys)
            template = build_payslip_instance_template(
                language=language if language != "auto" else None,
                simplified=True,
                field_keys=field_keys,
            )
            mapping_hint = (
                "Map labels by meaning: Employee name; Employee ID / Worker number; "
                "National ID / Teudat Zeut; Payroll month / Period; Gross; Net; "
                "Total deductions; Total payments; Bank transfer / Payment method.\n"
            )
        else:
            field_keys = PAYSLIP_FIELD_KEYS
            allowed = ", ".join(field_keys)
            template = build_payslip_instance_template(
                language=language if language != "auto" else None,
                simplified=True,
            )
            mapping_hint = (
                "Map payslip labels by meaning into canonical field names.\n"
                "Examples: Worker Number / Employee ID / מספר עובד -> employee_id or employee_number; "
                "Gross Salary / Total Payments -> gross_salary.\n"
            )

        template_json = json.dumps(template, ensure_ascii=False, indent=2)
        evidence_rule = (
            "For each non-null value include source_text copied from the document text. "
            "Do not require evidence_ids."
            if embedded_text_mode or simple_guest_fields
            else "Include source_text from OCR. evidence_ids are optional when unsure."
        )

        return (
            f"Document language hint: {language}\n"
            f"{mapping_hint}"
            f"{retry_block}\n"
            f"{layout_block}\n"
            "DOCUMENT TEXT:\n"
            f"{pages_block or ocr_text}\n\n"
            f"Return each of these fields exactly once: {allowed}\n"
            f"{evidence_rule}\n"
            "Use null value when absent. Do not invent digits or names.\n"
            "Preserve every field you can read; do not clear other fields if one is missing.\n"
            "Return ONE JSON object using this simplified per-field shape only:\n"
            '{"field_name": {"value": ..., "source_text": ..., "confidence": 0.0}}\n'
            f"Template:\n{template_json}\n"
            "Return populated JSON only. No markdown.\n"
        )

    async def _chat(self, user_content: str) -> tuple[str, str]:
        from payroll_copilot.application.ports import Message

        messages = [
            Message(role="system", content=self._system_prompt),
            Message(role="user", content=user_content),
        ]
        try:
            result = await self._provider.complete(
                messages,
                temperature=self._temperature,
                max_tokens=self._max_predict,
                json_mode=self._use_json_format,
            )
        except Exception as exc:  # noqa: BLE001 — map provider failures to parser errors
            logger.exception("Payslip parser LLM request failed")
            raise PayslipParserUnavailableError(
                f"Payslip parser LLM unavailable: {exc}"
            ) from exc

        content = result.content if isinstance(result.content, str) else ""
        if not content.strip():
            raise PayslipParserJsonError("Model returned an empty payslip extraction response.")
        return content, result.model or self._model
