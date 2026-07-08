"""Parse payslip fields from OCR output via AI (Phase 2A).

Owns one retry on JSON/schema failure. Does not run payroll validation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from payroll_copilot.application.exceptions import (
    PayslipParserEmptyOcrError,
    PayslipParserError,
    PayslipParserJsonError,
    PayslipParserSchemaError,
    PayslipParserTimeoutError,
)
from payroll_copilot.application.ports.ocr import OCRResult, OcrPage
from payroll_copilot.application.ports.payslip_parser import (
    PayslipParseResult,
    PayslipParser,
)
from payroll_copilot.application.services.payslip_field_sanitizer import (
    sanitize_structured_payslip,
)


@dataclass(frozen=True, slots=True)
class ParsePayslipFromOcrCommand:
    raw_text: str
    language: str = "auto"
    pages: tuple[OcrPage, ...] | None = None
    engine: str | None = None


class ParsePayslipFromOcrUseCase:
    """OCR Result → Structured Payslip JSON (AI Parser)."""

    def __init__(self, parser: PayslipParser, *, timeout_seconds: float) -> None:
        self._parser = parser
        self._timeout_seconds = timeout_seconds

    async def execute(self, command: ParsePayslipFromOcrCommand) -> PayslipParseResult:
        text = (command.raw_text or "").strip()
        if not text and command.pages:
            text = "\n\n".join(page.text for page in command.pages if page.text).strip()
        if not text:
            raise PayslipParserEmptyOcrError()

        pages_text = [page.text for page in command.pages] if command.pages else None
        language = (command.language or "auto").strip().lower() or "auto"

        try:
            first = await self._invoke(
                ocr_text=text,
                language=language,
                pages_text=pages_text,
                retry_hint=None,
            )
            sanitized = sanitize_structured_payslip(first.fields, ocr_text=text)
            return first.model_copy(update={"fields": sanitized, "retry_used": False})
        except (PayslipParserJsonError, PayslipParserSchemaError) as first_error:
            try:
                second = await self._invoke(
                    ocr_text=text,
                    language=language,
                    pages_text=pages_text,
                    retry_hint=str(first_error),
                )
                sanitized = sanitize_structured_payslip(second.fields, ocr_text=text)
                warnings = list(second.warnings)
                warnings.append("Parser retried once after invalid JSON/schema response.")
                return second.model_copy(
                    update={"fields": sanitized, "retry_used": True, "warnings": warnings}
                )
            except PayslipParserError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise PayslipParserSchemaError(
                    f"Payslip parsing failed after retry: {exc}"
                ) from exc

    async def _invoke(
        self,
        *,
        ocr_text: str,
        language: str,
        pages_text: list[str] | None,
        retry_hint: str | None,
    ) -> PayslipParseResult:
        try:
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


def command_from_ocr_result(result: OCRResult) -> ParsePayslipFromOcrCommand:
    return ParsePayslipFromOcrCommand(
        raw_text=result.raw_text,
        language=result.language_effective or result.language_requested or "auto",
        pages=result.pages,
        engine=result.engine,
    )
