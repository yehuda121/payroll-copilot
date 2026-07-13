"""Parse payslip fields from OCR output via AI (Phase 2A).

Owns one retry on JSON/schema/semantic failure. Does not run payroll validation.
Supports layout-aware OCR context with deterministic evidence validation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from payroll_copilot.application.exceptions import (
    PayslipParserEmptyOcrError,
    PayslipParserError,
    PayslipParserJsonError,
    PayslipParserSchemaError,
    PayslipParserSemanticError,
    PayslipParserTimeoutError,
)
from payroll_copilot.application.ports.ocr import OCRResult, OcrPage
from payroll_copilot.application.ports.payslip_parser import (
    FieldExtractionStatus,
    PayslipParseResult,
    PayslipParser,
)
from payroll_copilot.application.services.parser_evidence import validate_structured_payslip_evidence
from payroll_copilot.application.services.parser_layout_context import (
    BuiltParserContext,
    ParserLayoutConfig,
    build_parser_layout_context,
)
from payroll_copilot.application.services.payslip_field_sanitizer import (
    sanitize_structured_payslip,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ParsePayslipFromOcrCommand:
    raw_text: str
    language: str = "auto"
    pages: tuple[OcrPage, ...] | None = None
    engine: str | None = None
    warnings: tuple[str, ...] = ()


class ParsePayslipFromOcrUseCase:
    """OCR Result → Structured Payslip JSON (AI Parser)."""

    def __init__(
        self,
        parser: PayslipParser,
        *,
        timeout_seconds: float,
        layout_config: ParserLayoutConfig | None = None,
    ) -> None:
        self._parser = parser
        self._timeout_seconds = timeout_seconds
        self._layout_config = layout_config or ParserLayoutConfig()

    async def execute(self, command: ParsePayslipFromOcrCommand) -> PayslipParseResult:
        started = time.perf_counter()
        text = (command.raw_text or "").strip()
        if not text and command.pages:
            text = "\n\n".join(page.text for page in command.pages if page.text).strip()
        if not text:
            raise PayslipParserEmptyOcrError()

        pages_text = [page.text for page in command.pages] if command.pages else None
        language = (command.language or "auto").strip().lower() or "auto"
        layout = self._build_layout(command, language=language)

        try:
            first = await self._invoke(
                ocr_text=text,
                language=language,
                pages_text=pages_text,
                layout_context=layout.payload if self._layout_config.enabled else None,
                retry_hint=None,
            )
            fields = self._post_process(first.fields, ocr_text=text, layout=layout)
            result = first.model_copy(update={"fields": fields, "retry_used": False})
            self._log_summary(result, layout=layout, duration_ms=(time.perf_counter() - started) * 1000)
            return result
        except (PayslipParserJsonError, PayslipParserSchemaError) as first_error:
            first_warnings = _warnings_for_parser_error(first_error)
            try:
                second = await self._invoke(
                    ocr_text=text,
                    language=language,
                    pages_text=pages_text,
                    layout_context=layout.payload if self._layout_config.enabled else None,
                    retry_hint=_retry_hint_for_error(first_error),
                )
                fields = self._post_process(second.fields, ocr_text=text, layout=layout)
                warnings = list(second.warnings)
                warnings.extend(first_warnings)
                if isinstance(first_error, PayslipParserSemanticError):
                    warnings.append("parser_semantic_retry_used")
                warnings.append("Parser retried once after invalid JSON/schema response.")
                result = second.model_copy(
                    update={"fields": fields, "retry_used": True, "warnings": list(dict.fromkeys(warnings))}
                )
                self._log_summary(result, layout=layout, duration_ms=(time.perf_counter() - started) * 1000)
                return result
            except PayslipParserError as second_error:
                if isinstance(second_error, PayslipParserSemanticError):
                    # Controlled safe fallback after one semantic retry: never invent values.
                    from payroll_copilot.application.ports.payslip_parser import StructuredPayslipParse

                    empty = StructuredPayslipParse(language=language)
                    fields = self._post_process(empty, ocr_text=text, layout=layout)
                    warnings = list(dict.fromkeys([
                        *_warnings_for_parser_error(first_error),
                        *_warnings_for_parser_error(second_error),
                        "parser_semantic_retry_used",
                        "parser_semantic_retry_failed",
                        "Parser retried once after invalid JSON/schema response.",
                    ]))
                    result = PayslipParseResult(
                        model="unknown",
                        language=language,
                        fields=fields,
                        raw_model_response=None,
                        warnings=warnings,
                        retry_used=True,
                    )
                    self._log_summary(
                        result, layout=layout, duration_ms=(time.perf_counter() - started) * 1000
                    )
                    return result
                raise
            except Exception as exc:  # noqa: BLE001
                raise PayslipParserSchemaError(
                    f"Payslip parsing failed after retry: {exc}"
                ) from exc

    def _build_layout(self, command: ParsePayslipFromOcrCommand, *, language: str) -> BuiltParserContext:
        return build_parser_layout_context(
            pages=command.pages,
            language=language,
            warnings=list(command.warnings),
            config=self._layout_config,
        )

    def _post_process(self, fields, *, ocr_text: str, layout: BuiltParserContext):
        sanitized = sanitize_structured_payslip(fields, ocr_text=ocr_text)
        if self._layout_config.enabled and layout.evidence_index:
            return validate_structured_payslip_evidence(
                sanitized,
                evidence_index=layout.evidence_index,
                ocr_text=ocr_text,
            )
        return sanitized

    async def _invoke(
        self,
        *,
        ocr_text: str,
        language: str,
        pages_text: list[str] | None,
        layout_context: dict[str, Any] | None,
        retry_hint: str | None,
    ) -> PayslipParseResult:
        try:
            return await asyncio.wait_for(
                self._parser.parse(
                    ocr_text=ocr_text,
                    language=language,
                    pages_text=pages_text,
                    layout_context=layout_context,
                    retry_hint=retry_hint,
                ),
                timeout=self._timeout_seconds,
            )
        except TypeError:
            return await asyncio.wait_for(
                self._parser.parse(
                    ocr_text=ocr_text,
                    language=language,
                    pages_text=pages_text,
                    retry_hint=retry_hint,
                ),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            raise PayslipParserTimeoutError(
                f"Payslip parser timed out after {self._timeout_seconds:.0f}s."
            ) from exc

    @staticmethod
    def _log_summary(
        result: PayslipParseResult,
        *,
        layout: BuiltParserContext,
        duration_ms: float,
    ) -> None:
        counts = {"FOUND": 0, "MISSING": 0, "UNCERTAIN": 0}
        for field in result.fields.field_map().values():
            counts[field.status.value] = counts.get(field.status.value, 0) + 1
        logger.info(
            "payslip_parser_complete model=%s duration_ms=%.2f retry=%s "
            "layout_lines=%s layout_words=%s context_chars=%s found=%s missing=%s "
            "uncertain=%s warning_count=%s",
            result.model,
            duration_ms,
            result.retry_used,
            layout.line_count,
            layout.word_count,
            layout.context_chars,
            counts.get(FieldExtractionStatus.FOUND.value, 0),
            counts.get(FieldExtractionStatus.MISSING.value, 0),
            counts.get(FieldExtractionStatus.UNCERTAIN.value, 0),
            len(result.warnings),
        )


def _warnings_for_parser_error(error: Exception) -> list[str]:
    if isinstance(error, PayslipParserSemanticError) and error.warning_code:
        return [error.warning_code]
    return []


def _retry_hint_for_error(error: Exception) -> str:
    if isinstance(error, PayslipParserSemanticError):
        return f"{error.category}: {error.message}"
    return str(error)


def command_from_ocr_result(result: OCRResult) -> ParsePayslipFromOcrCommand:
    return ParsePayslipFromOcrCommand(
        raw_text=result.raw_text,
        language=result.language_effective or result.language_requested or "auto",
        pages=result.pages,
        engine=result.engine,
        warnings=tuple(result.warnings),
    )
