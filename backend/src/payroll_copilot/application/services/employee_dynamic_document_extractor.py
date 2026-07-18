"""Generic document-model extraction for employee identity and contract documents."""

from __future__ import annotations

import json
import re
from typing import Any

from payroll_copilot.application.exceptions import (
    PayslipParserEmptyOcrError,
    PayslipParserJsonError,
    PayslipParserUnavailableError,
)
from payroll_copilot.application.ports import Message
from payroll_copilot.application.services.dynamic_document import (
    DynamicDocumentEntry,
    entries_have_usable_values,
)
from payroll_copilot.application.services.guest_dynamic_extractor import (
    document_model_from_payload,
)
from payroll_copilot.infrastructure.ai.ollama_provider import create_model_provider
from payroll_copilot.infrastructure.config.settings import get_settings

_SYSTEM_PROMPT = """You reconstruct an uploaded document into structured data.
Return STRICT JSON only. No markdown. No commentary.

Output:
{
  "sections": [
    {
      "title": "section title",
      "entries": [
        {
          "key": "label exactly as printed",
          "value": "extracted value or null",
          "confidence": 0.0,
          "page": 1,
          "source_text": "short supporting quote"
        }
      ],
      "tables": []
    }
  ],
  "entries": []
}

Rules:
- Reconstruct every meaningful label/value faithfully.
- Preserve the document's language and wording.
- Do not summarize, infer missing facts, or invent values.
- Preserve tables when present.
- confidence must be between 0 and 1.
"""


def _parse_payload(raw: str) -> dict[str, Any]:
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
                "Document extractor returned non-JSON content."
            ) from None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise PayslipParserJsonError("Document extractor returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise PayslipParserJsonError("Document extractor JSON root must be an object.")
    return payload


class EmployeeDynamicDocumentExtractor:
    """OCR text → generic editable Document Model for Employee Documents."""

    def __init__(self, *, model_provider: Any | None = None) -> None:
        settings = get_settings()
        self._provider = model_provider or create_model_provider(settings.model_provider, settings)
        self._model = (
            settings.bedrock_model_id
            if settings.model_provider.strip().lower() == "bedrock"
            else settings.ollama_default_model
        )

    async def extract(
        self,
        *,
        ocr_text: str,
        language: str,
        document_type: str,
        pages_text: list[str] | None = None,
    ) -> tuple[list[DynamicDocumentEntry], str, list[str]]:
        if not (ocr_text or "").strip():
            raise PayslipParserEmptyOcrError()

        pages_block = ""
        if pages_text:
            pages_block = "\n\n".join(
                f"--- PAGE {index} ---\n{text}"
                for index, text in enumerate(pages_text, start=1)
                if text
            )
        prompt = (
            f"Document type: {document_type}\n"
            f"Document language hint: {language}\n\n"
            f"DOCUMENT TEXT:\n{pages_block or ocr_text}\n\n"
            "Reconstruct this document into the JSON Document Model."
        )
        try:
            result = await self._provider.complete(
                [
                    Message(role="system", content=_SYSTEM_PROMPT),
                    Message(role="user", content=prompt),
                ],
                temperature=0.0,
                max_tokens=12288,
                json_mode=True,
            )
        except Exception as exc:
            raise PayslipParserUnavailableError(
                f"Document extractor LLM unavailable: {exc}"
            ) from exc

        content = result.content if isinstance(result.content, str) else ""
        if not content.strip():
            raise PayslipParserJsonError("Document extractor returned an empty response.")
        entries = document_model_from_payload(_parse_payload(content))
        warnings: list[str] = []
        if not entries_have_usable_values(entries):
            warnings.append("document_extractor_no_usable_entries")
        return entries, result.model or self._model, warnings
