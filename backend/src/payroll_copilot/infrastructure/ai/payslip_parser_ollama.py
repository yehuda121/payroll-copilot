"""Ollama-backed payslip parser (layout-independent).

JSON handling is local to this adapter so other Ollama consumers are unchanged.
Does not use hardcoded overall confidence (no 0.9 invention).
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
    PayslipParserUnavailableError,
)
from payroll_copilot.application.ports.payslip_parser import (
    PAYSLIP_FIELD_KEYS,
    ExtractedField,
    FieldExtractionStatus,
    PayslipParseResult,
    StructuredPayslipParse,
)

logger = logging.getLogger(__name__)

_PROMPT_CANDIDATES = (
    Path(__file__).resolve().parents[4] / "config" / "prompts" / "payslip_extractor" / "system.md",
    Path.cwd() / "config" / "prompts" / "payslip_extractor" / "system.md",
    Path.cwd() / "backend" / "config" / "prompts" / "payslip_extractor" / "system.md",
)

_FALLBACK_SYSTEM_PROMPT = """You are a multilingual payslip field extractor.
Return STRICT JSON only matching the provided schema.
Do not invent values. Use status MISSING when absent, UNCERTAIN when unsure.
For FOUND/UNCERTAIN fields include source_text copied from OCR and confidence in [0,1] only when justified.
Never invent confidence. Layout-independent. Hebrew/English/Arabic.
No payroll validation or calculations.
"""


def _load_system_prompt() -> str:
    for path in _PROMPT_CANDIDATES:
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8")
        except OSError:
            continue
    return _FALLBACK_SYSTEM_PROMPT


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
        # Attempt to salvage outermost object.
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
    if raw is None:
        return {
            "value": None,
            "confidence": None,
            "source_text": None,
            "status": FieldExtractionStatus.MISSING.value,
        }
    if not isinstance(raw, dict):
        return {
            "value": raw,
            "confidence": None,
            "source_text": None,
            "status": FieldExtractionStatus.UNCERTAIN.value,
        }
    status = raw.get("status", FieldExtractionStatus.MISSING.value)
    if isinstance(status, str):
        status = status.strip().upper()
    return {
        "value": raw.get("value"),
        "confidence": raw.get("confidence"),
        "source_text": raw.get("source_text"),
        "status": status,
    }


def coerce_structured_payslip(payload: dict[str, Any]) -> StructuredPayslipParse:
    """Normalize loose model JSON into StructuredPayslipParse."""
    fields: dict[str, Any] = {}
    for key in PAYSLIP_FIELD_KEYS:
        fields[key] = ExtractedField.model_validate(_normalize_field_payload(payload.get(key)))

    additional_raw = payload.get("additional_fields") or {}
    additional: dict[str, ExtractedField] = {}
    if isinstance(additional_raw, dict):
        for name, value in additional_raw.items():
            if not isinstance(name, str) or not name.strip():
                continue
            if name in PAYSLIP_FIELD_KEYS:
                continue
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
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature
        self._use_json_format = use_json_format
        self._system_prompt = _load_system_prompt()

    async def parse(
        self,
        *,
        ocr_text: str,
        language: str = "auto",
        pages_text: list[str] | None = None,
        retry_hint: str | None = None,
    ) -> PayslipParseResult:
        if not ocr_text or not ocr_text.strip():
            raise PayslipParserEmptyOcrError()

        schema_json = json.dumps(StructuredPayslipParse.model_json_schema(), indent=2)
        user_content = self._build_user_prompt(
            ocr_text=ocr_text,
            language=language,
            pages_text=pages_text,
            schema_json=schema_json,
            retry_hint=retry_hint,
        )

        raw_content, model_name = await self._chat(user_content)
        try:
            payload = _parse_json_object(raw_content)
            fields = coerce_structured_payslip(payload)
        except PayslipParserJsonError:
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
            warnings=[],
            retry_used=bool(retry_hint),
        )

    def _build_user_prompt(
        self,
        *,
        ocr_text: str,
        language: str,
        pages_text: list[str] | None,
        schema_json: str,
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
                f"Error: {retry_hint}\n"
                "Return corrected STRICT JSON only. No markdown. No commentary.\n"
            )

        return (
            f"{self._system_prompt}\n\n"
            f"Document language hint: {language}\n"
            "Extract fields from the OCR text below. "
            "Do not assume a fixed layout or employer template.\n"
            f"{retry_block}\n"
            "JSON schema (all listed fields must appear; each is an object with "
            "value, confidence, source_text, status):\n"
            f"{schema_json}\n\n"
            "OCR TEXT:\n"
            f"{pages_block or ocr_text}\n"
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
            # Local to this parser path only (decision 5A optional hardening).
            payload["format"] = "json"

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(f"{self._base_url}/api/chat", json=payload)
                if response.status_code >= 400 and self._use_json_format and "format" in payload:
                    # Some Ollama builds/models reject format=json — retry once without it.
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
