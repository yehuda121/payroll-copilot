"""LLM complete-document extraction (shared Stage-1 for Guest / Employee / Batch).

Reconstructs the uploaded document into a structured Document Model.
Does not select a sparse payroll subset — completeness over filtering.
Canonical payroll mapping happens only after this stage.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from payroll_copilot.application.exceptions import (
    PayslipParserEmptyOcrError,
    PayslipParserJsonError,
    PayslipParserUnavailableError,
)
from payroll_copilot.application.ports import AICapability, Message
from payroll_copilot.application.services.dynamic_document import (
    DynamicDocumentEntry,
    entries_have_usable_values,
    is_document_origin_entry,
    new_entry,
)
from payroll_copilot.infrastructure.ai.provider_router import AIProviderRouter
from payroll_copilot.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)

# Completeness-first generation needs more tokens than sparse payroll field extraction.
_DEFAULT_MAX_PREDICT = 12288
_MIN_TIMEOUT_SECONDS = 90.0

_SYSTEM_PROMPT = """You reconstruct an uploaded payroll / payslip document into structured data.
Return STRICT JSON only. No markdown. No commentary.

Your job is NOT to pick "important payroll fields".
Your job is to reconstruct the document as completely and faithfully as possible.

Output shape (preferred):
{
  "sections": [
    {
      "title": "section title exactly as on the document when possible",
      "entries": [
        {
          "key": "label exactly as on the document",
          "value": "extracted value or null",
          "confidence": 0.0,
          "page": 1,
          "source_text": "short supporting quote"
        }
      ],
      "tables": [
        {
          "id": "stable_table_id",
          "title": "optional table title",
          "columns": ["Column A", "Column B"],
          "rows": [
            ["row1-colA", "row1-colB"],
            {"Column A": "row2-colA", "Column B": "row2-colB"}
          ],
          "page": 1
        }
      ]
    }
  ],
  "entries": []
}

You may also return a flat "entries" array. Prefer sections when the document has them.

Rules:
- Completeness first: include every meaningful label/value, payment row, benefit row, deduction row, total, bank detail, message, and note you can identify.
- Do NOT summarize. Do NOT filter to "important" fields only. Do NOT invent values.
- Do NOT invent empty fields from a fixed payroll schema.
- Prefer the document's own wording for keys and section titles (Hebrew/English/Arabic as printed).
- Preserve logical sections when possible (Personal Information, Bank Details, Payments, Benefits, Deductions, Totals, Unknown Section, etc.).
- Tables: do NOT flatten into meaningless prose. Preserve columns and row relationships via the tables array.
- Values may be numbers, strings, or null when the label exists but the value is unreadable.
- If a value is clear but its label is unknown, set "key" to "" (empty string) and still include the value.
- confidence is 0..1.
"""


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
            raise PayslipParserJsonError("Dynamic extractor returned non-JSON content.")
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise PayslipParserJsonError("Dynamic extractor returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise PayslipParserJsonError("Dynamic extractor JSON root must be an object.")
    return payload


def _as_confidence(raw: Any) -> float | None:
    try:
        confidence = float(raw) if raw is not None and raw != "" else None
    except (TypeError, ValueError):
        return None
    if confidence is not None and (confidence < 0 or confidence > 1):
        return None
    return confidence


def _as_int(raw: Any) -> int | None:
    try:
        return int(raw) if raw is not None and raw != "" else None
    except (TypeError, ValueError):
        return None


def _as_page(raw: Any) -> int | None:
    return _as_int(raw)


def _normalize_key(raw_key: Any) -> str:
    key = str(raw_key or "").strip()
    if key.casefold() in {"unknown", "(unknown)", "n/a", "none", "null"}:
        return ""
    return key


def _entry_from_item(
    item: dict[str, Any],
    *,
    section: str | None = None,
    kind: str | None = None,
    table_id: str | None = None,
    row_index: int | None = None,
    column: str | None = None,
) -> DynamicDocumentEntry | None:
    key = _normalize_key(item.get("key") or item.get("label"))
    value = item.get("value")
    has_value = value is not None and not (isinstance(value, str) and not str(value).strip())
    if isinstance(value, (list, dict)) and len(value) == 0:
        has_value = False
    if not key and not has_value:
        return None

    # Nested table object on a field — expand later via caller; keep as opaque if columns missing.
    return new_entry(
        key=key,
        value=value,
        confidence=_as_confidence(item.get("confidence")),
        page=_as_page(item.get("page")),
        source="ocr",
        source_text=item.get("source_text") if isinstance(item.get("source_text"), str) else None,
        section=section or (str(item["section"]).strip() if isinstance(item.get("section"), str) else None),
        kind=kind or (str(item["kind"]).strip() if isinstance(item.get("kind"), str) else None) or "field",
        table_id=table_id
        or (str(item["table_id"]).strip() if isinstance(item.get("table_id"), str) else None),
        row_index=row_index if row_index is not None else _as_int(item.get("row_index")),
        column=column or (str(item["column"]).strip() if isinstance(item.get("column"), str) else None),
    )


def _is_table_value(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if "columns" in value and "rows" in value:
        return True
    return str(value.get("type") or "").lower() == "table" and "rows" in value


def _expand_table(
    table: dict[str, Any],
    *,
    section: str | None,
    default_page: int | None = None,
) -> list[DynamicDocumentEntry]:
    table_id = str(table.get("id") or table.get("title") or "table").strip() or "table"
    page = _as_page(table.get("page")) or default_page
    columns_raw = table.get("columns")
    columns: list[str] = []
    if isinstance(columns_raw, list):
        columns = [str(c).strip() for c in columns_raw if str(c).strip()]

    rows = table.get("rows")
    if not isinstance(rows, list):
        return []

    out: list[DynamicDocumentEntry] = []
    # Table title is represented by section / table_id metadata on cells — avoid empty title rows.

    for row_index, row in enumerate(rows):
        cells: list[tuple[str, Any]] = []
        if isinstance(row, dict):
            if "cells" in row and isinstance(row["cells"], dict):
                cells = [(str(k), v) for k, v in row["cells"].items()]
            else:
                # Skip metadata-only keys if present
                cells = [
                    (str(k), v)
                    for k, v in row.items()
                    if str(k) not in {"page", "confidence", "source_text"}
                ]
        elif isinstance(row, list):
            if columns:
                for col_i, col_name in enumerate(columns):
                    cells.append((col_name, row[col_i] if col_i < len(row) else None))
            else:
                for col_i, cell in enumerate(row):
                    cells.append((f"Column {col_i + 1}", cell))
        else:
            cells = [("Value", row)]

        # Prefer a human label from the first descriptive column when present.
        label_hint = ""
        desc_columns = {
            "description",
            "desc",
            "name",
            "item",
            "component",
            "רכיב",
            "תיאור",
            "שם",
        }
        if cells:
            for col_name, col_val in cells:
                if col_name.casefold() in desc_columns and col_val is not None and str(col_val).strip():
                    label_hint = str(col_val).strip()
                    break
            if not label_hint:
                first_key, first_val = cells[0]
                if first_val is not None and str(first_val).strip() and first_key.casefold() in desc_columns:
                    label_hint = str(first_val).strip()

        for column_name, cell_value in cells:
            # Description columns provide the row label; don't emit a redundant cell.
            if column_name.casefold() in desc_columns:
                continue
            if label_hint:
                key = (
                    label_hint
                    if len([c for c in cells if c[0].casefold() not in desc_columns]) == 1
                    else f"{label_hint} / {column_name}"
                )
            else:
                key = column_name

            entry = new_entry(
                key=key,
                value=cell_value,
                confidence=_as_confidence(table.get("confidence")),
                page=page,
                source="ocr",
                section=section,
                kind="table_cell",
                table_id=table_id,
                row_index=row_index,
                column=column_name,
            )
            if is_document_origin_entry(entry):
                out.append(entry)

        # Description-only row (no other columns): keep the label with empty/null value skip;
        # if the only cell was descriptive and we skipped it, emit one labeled row with that text as value.
        non_desc = [c for c in cells if c[0].casefold() not in desc_columns]
        if not non_desc and label_hint:
            entry = new_entry(
                key=label_hint,
                value=label_hint,
                confidence=_as_confidence(table.get("confidence")),
                page=page,
                source="ocr",
                section=section,
                kind="table_cell",
                table_id=table_id,
                row_index=row_index,
                column=cells[0][0] if cells else None,
            )
            if is_document_origin_entry(entry):
                out.append(entry)
    return out


def _collect_entries_from_list(
    raw_entries: list[Any],
    *,
    section: str | None = None,
) -> list[DynamicDocumentEntry]:
    out: list[DynamicDocumentEntry] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        if _is_table_value(value):
            out.extend(_expand_table(value, section=section or item.get("section")))
            continue
        entry = _entry_from_item(item, section=section)
        if entry is None:
            continue
        out.append(entry)
    return out


def document_model_from_payload(payload: dict[str, Any]) -> list[DynamicDocumentEntry]:
    """Normalize LLM JSON (sections/tables/entries) into a flat Document Model list."""
    entries: list[DynamicDocumentEntry] = []

    sections = payload.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            title = str(section.get("title") or section.get("name") or "").strip() or None
            section_entries = section.get("entries") or section.get("fields")
            if isinstance(section_entries, list):
                entries.extend(_collect_entries_from_list(section_entries, section=title))
            tables = section.get("tables")
            if isinstance(tables, list):
                for table in tables:
                    if isinstance(table, dict):
                        entries.extend(_expand_table(table, section=title))

    top_entries = payload.get("entries")
    if top_entries is None and isinstance(payload.get("fields"), list):
        top_entries = payload["fields"]
    if isinstance(top_entries, list):
        entries.extend(_collect_entries_from_list(top_entries))

    top_tables = payload.get("tables")
    if isinstance(top_tables, list):
        for table in top_tables:
            if isinstance(table, dict):
                entries.extend(_expand_table(table, section=None))

    if entries:
        return [e for e in entries if is_document_origin_entry(e)]

    # Last-resort: flat object of label→value
    fallback: list[DynamicDocumentEntry] = []
    for key, value in payload.items():
        if key in {"entries", "fields", "sections", "tables", "language", "warnings"}:
            continue
        if isinstance(value, dict) and "value" in value:
            entry = _entry_from_item({**value, "key": key})
        else:
            entry = new_entry(key=str(key), value=value, source="ocr", kind="field")
        if entry is not None and is_document_origin_entry(entry):
            fallback.append(entry)
    return fallback


class GuestDynamicDocumentExtractor:
    """Document-first LLM extractor: OCR text → complete Document Model entries."""

    def __init__(
        self,
        *,
        model_provider: Any | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        max_predict: int | None = None,
    ) -> None:
        settings = get_settings()
        router = AIProviderRouter(settings)
        self._provider = model_provider or router.provider_for(
            AICapability.DOCUMENT_EXTRACTION
        )
        self._model = model or router.model_for(AICapability.DOCUMENT_EXTRACTION)
        configured_timeout = float(
            timeout_seconds
            if timeout_seconds is not None
            else getattr(settings, "payslip_parser_timeout_seconds", 45.0)
        )
        # Complete reconstruction needs more wall time than sparse field extraction.
        self._timeout_seconds = max(configured_timeout, _MIN_TIMEOUT_SECONDS)
        configured_predict = int(
            max_predict
            if max_predict is not None
            else getattr(settings, "payslip_parser_max_predict", 4096)
        )
        self._max_predict = max(configured_predict, _DEFAULT_MAX_PREDICT)

    async def extract(
        self,
        *,
        ocr_text: str,
        language: str = "auto",
        pages_text: list[str] | None = None,
    ) -> tuple[list[DynamicDocumentEntry], str, list[str]]:
        if not (ocr_text or "").strip():
            raise PayslipParserEmptyOcrError()

        pages_block = ""
        if pages_text:
            chunks = [f"--- PAGE {i} ---\n{page}" for i, page in enumerate(pages_text, start=1) if page]
            pages_block = "\n\n".join(chunks)

        user_content = (
            f"Document language hint: {language}\n\n"
            "DOCUMENT TEXT:\n"
            f"{pages_block or ocr_text}\n\n"
            "Reconstruct this entire document into the JSON Document Model.\n"
            "Include every meaningful field, table row, total, and note you can identify.\n"
            "Do not summarize. Do not keep only payroll-header fields.\n"
            "Use the document's own labels and section titles.\n"
        )

        raw_content, model_name = await self._chat(user_content)
        payload = _parse_json_object(raw_content)
        entries = document_model_from_payload(payload)
        warnings: list[str] = []
        if not entries_have_usable_values(entries):
            warnings.append("dynamic_extractor_no_usable_entries")
        elif len(entries) < 8:
            # Soft signal only — short slips exist; useful for observability.
            warnings.append("dynamic_extractor_sparse_document_model")
        return entries, model_name, warnings

    async def _chat(self, user_content: str) -> tuple[str, str]:
        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ]
        try:
            result = await self._provider.complete(
                messages,
                temperature=0.0,
                max_tokens=self._max_predict,
                json_mode=True,
            )
        except Exception as exc:  # noqa: BLE001 — map provider failures
            logger.exception("Dynamic document extractor LLM request failed")
            raise PayslipParserUnavailableError(
                f"Dynamic extractor LLM unavailable: {exc}"
            ) from exc

        content = result.content if isinstance(result.content, str) else ""
        if not content.strip():
            raise PayslipParserJsonError("Model returned an empty dynamic extraction response.")
        return content, result.model or self._model
