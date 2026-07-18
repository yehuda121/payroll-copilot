"""Parse payslip fields from OCR output via AI (Phase 2A).

Owns one retry on JSON/schema/semantic failure. Does not run payroll validation.
Supports layout-aware OCR context with deterministic evidence validation.
Phase 3: optional evidence-bound mapping from layout_analysis candidates.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from payroll_copilot.application.exceptions import (
    ExtractionCancelledError,
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
    StructuredPayslipParse,
)
from payroll_copilot.application.services.candidate_evidence_validator import (
    hydrate_and_validate_candidate_fields,
)
from payroll_copilot.application.services.evidence_binder import bind_evidence_candidates
from payroll_copilot.application.services.extraction_engine import is_embedded_text_engine
from payroll_copilot.application.services.parser_evidence import validate_structured_payslip_evidence
from payroll_copilot.application.services.parser_layout_context import (
    BuiltParserContext,
    ParserLayoutConfig,
    build_parser_layout_context,
)
from payroll_copilot.application.services.payslip_field_sanitizer import (
    sanitize_structured_payslip,
)
from payroll_copilot.infrastructure.ocr.text_normalize import normalize_extracted_text

logger = logging.getLogger(__name__)

CancelCheck = Callable[[], bool] | None


@dataclass(frozen=True, slots=True)
class ParsePayslipFromOcrCommand:
    raw_text: str
    language: str = "auto"
    pages: tuple[OcrPage, ...] | None = None
    engine: str | None = None
    warnings: tuple[str, ...] = ()
    cancel_check: CancelCheck = None
    """When True, ask the model for the small guest landing field set only."""
    simple_guest_fields: bool = False
    """Phase 2 layout_analysis used by Phase 3 evidence-bound mapping."""
    layout_analysis: dict[str, Any] = field(default_factory=dict)


class ParsePayslipFromOcrUseCase:
    """OCR Result → Structured Payslip JSON (AI Parser)."""

    def __init__(
        self,
        parser: PayslipParser,
        *,
        timeout_seconds: float,
        total_budget_seconds: float | None = None,
        layout_config: ParserLayoutConfig | None = None,
        evidence_bound_enabled: bool = False,
    ) -> None:
        self._parser = parser
        self._timeout_seconds = timeout_seconds
        self._total_budget_seconds = total_budget_seconds or min(timeout_seconds * 1.5, 90.0)
        self._layout_config = layout_config or ParserLayoutConfig()
        self._evidence_bound_enabled = evidence_bound_enabled

    async def execute(self, command: ParsePayslipFromOcrCommand) -> PayslipParseResult:
        started = time.perf_counter()
        self._check_cancelled(command.cancel_check)

        text = normalize_extracted_text(command.raw_text or "")
        if not text and command.pages:
            text = normalize_extracted_text(
                "\n\n".join(page.text for page in command.pages if page.text)
            )
        if not text:
            raise PayslipParserEmptyOcrError()

        pages_text = [page.text for page in command.pages] if command.pages else None
        language = (command.language or "auto").strip().lower() or "auto"
        embedded_mode = is_embedded_text_engine(command.engine)
        layout = self._build_layout(command, language=language)

        evidence_bundle: dict[str, Any] = {}
        evidence_bound = False
        if self._evidence_bound_enabled:
            evidence_bundle = bind_evidence_candidates(command.layout_analysis or {})
            evidence_bound = bool(evidence_bundle.get("llm_candidates"))
            if not evidence_bound:
                logger.info("evidence_bound_fallback_no_candidates")

        layout_context = None
        if not evidence_bound:
            layout_context = layout.payload if self._layout_config.enabled and not embedded_mode else None

        first_error: Exception | None = None
        first_warnings: list[str] = []
        last_payload: dict[str, Any] | None = None
        if evidence_bound:
            first_warnings.extend(list(evidence_bundle.get("warnings") or []))
            first_warnings.append("parser_evidence_bound_enabled")

        for attempt in range(2):
            self._check_cancelled(command.cancel_check)
            remaining = self._remaining_budget(started)
            if remaining <= 0:
                raise PayslipParserTimeoutError(
                    f"Payslip parser exceeded total budget of {self._total_budget_seconds:.0f}s."
                )
            attempt_timeout = min(self._timeout_seconds, remaining)
            retry_hint = _retry_hint_for_error(first_error) if attempt == 1 and first_error else None
            try:
                result = await self._invoke(
                    ocr_text=text,
                    language=language,
                    pages_text=pages_text,
                    layout_context=layout_context,
                    evidence_candidates=evidence_bundle if evidence_bound else None,
                    retry_hint=retry_hint,
                    embedded_text_mode=embedded_mode and not evidence_bound,
                    simple_guest_fields=command.simple_guest_fields,
                    timeout_seconds=attempt_timeout,
                    cancel_check=command.cancel_check,
                )
                last_payload = getattr(result, "parsed_payload", None)
                fields = self._post_process(
                    result.fields,
                    ocr_text=text,
                    layout=layout,
                    embedded_mode=embedded_mode,
                    evidence_bundle=evidence_bundle if evidence_bound else None,
                )
                merged_warnings = list(dict.fromkeys([*result.warnings, *first_warnings]))
                if attempt == 1:
                    merged_warnings.append("parser_retry_used")
                final = result.model_copy(
                    update={
                        "fields": fields,
                        "retry_used": attempt == 1,
                        "warnings": merged_warnings,
                    }
                )
                self._log_summary(final, layout=layout, duration_ms=(time.perf_counter() - started) * 1000)
                return final
            except (PayslipParserJsonError, PayslipParserSchemaError, PayslipParserSemanticError) as tip_exc:
                first_error = tip_exc
                first_warnings.extend(_warnings_for_parser_error(tip_exc))
                partial_payload = getattr(tip_exc, "partial_payload", None)
                if isinstance(partial_payload, dict):
                    last_payload = partial_payload
                if attempt == 1:
                    partial = self._coerce_partial_if_any(
                        last_payload,
                        ocr_text=text,
                        layout=layout,
                        embedded_mode=embedded_mode,
                        evidence_bundle=evidence_bundle if evidence_bound else None,
                    )
                    if partial is not None and _has_usable_fields(partial):
                        warnings = list(dict.fromkeys([
                            *first_warnings,
                            "parser_partial_result_preserved",
                            "parser_retry_failed",
                        ]))
                        partial_result = PayslipParseResult(
                            model="partial",
                            language=language,
                            fields=partial,
                            raw_model_response=None,
                            warnings=warnings,
                            retry_used=True,
                        )
                        self._log_summary(
                            partial_result,
                            layout=layout,
                            duration_ms=(time.perf_counter() - started) * 1000,
                        )
                        return partial_result
                    raise PayslipParserSemanticError(
                        f"Payslip parsing failed after one retry: {tip_exc.message if hasattr(tip_exc, 'message') else tip_exc}",
                        category=getattr(tip_exc, "category", "parser_retry_failed"),
                        warning_code=getattr(tip_exc, "warning_code", "parser_retry_failed"),
                        partial_payload=last_payload if isinstance(last_payload, dict) else None,
                    ) from tip_exc
            except PayslipParserError:
                raise

        raise PayslipParserError("Payslip parsing failed.")

    def _remaining_budget(self, started: float) -> float:
        elapsed = time.perf_counter() - started
        return max(0.0, self._total_budget_seconds - elapsed)

    @staticmethod
    def _check_cancelled(cancel_check: CancelCheck) -> None:
        if cancel_check is not None and cancel_check():
            raise ExtractionCancelledError()

    def _build_layout(self, command: ParsePayslipFromOcrCommand, *, language: str) -> BuiltParserContext:
        return build_parser_layout_context(
            pages=command.pages,
            language=language,
            warnings=list(command.warnings),
            config=self._layout_config,
        )

    def _post_process(
        self,
        fields: StructuredPayslipParse,
        *,
        ocr_text: str,
        layout: BuiltParserContext,
        embedded_mode: bool,
        evidence_bundle: dict[str, Any] | None = None,
    ) -> StructuredPayslipParse:
        if evidence_bundle and evidence_bundle.get("candidate_index"):
            # Candidate hydration is authoritative — skip OCR-text sanitizer downgrades.
            return hydrate_and_validate_candidate_fields(
                fields,
                candidate_index=dict(evidence_bundle.get("candidate_index") or {}),
            )

        sanitized = sanitize_structured_payslip(fields, ocr_text=ocr_text)
        if embedded_mode:
            return validate_structured_payslip_evidence(
                sanitized,
                evidence_index=layout.evidence_index,
                ocr_text=ocr_text,
                require_evidence_ids=False,
            )
        if self._layout_config.enabled and layout.evidence_index:
            return validate_structured_payslip_evidence(
                sanitized,
                evidence_index=layout.evidence_index,
                ocr_text=ocr_text,
                require_evidence_ids=True,
            )
        return sanitized

    def _coerce_partial_if_any(
        self,
        payload: dict[str, Any] | None,
        *,
        ocr_text: str,
        layout: BuiltParserContext,
        embedded_mode: bool,
        evidence_bundle: dict[str, Any] | None = None,
    ) -> StructuredPayslipParse | None:
        if not payload:
            return None
        from payroll_copilot.infrastructure.ai.payslip_parser_ollama import coerce_partial_structured_payslip

        try:
            partial = coerce_partial_structured_payslip(payload)
            return self._post_process(
                partial,
                ocr_text=ocr_text,
                layout=layout,
                embedded_mode=embedded_mode,
                evidence_bundle=evidence_bundle,
            )
        except Exception:  # noqa: BLE001
            return None

    async def _invoke(
        self,
        *,
        ocr_text: str,
        language: str,
        pages_text: list[str] | None,
        layout_context: dict[str, Any] | None,
        evidence_candidates: dict[str, Any] | None,
        retry_hint: str | None,
        embedded_text_mode: bool,
        simple_guest_fields: bool,
        timeout_seconds: float,
        cancel_check: CancelCheck,
    ) -> PayslipParseResult:
        self._check_cancelled(cancel_check)
        try:
            parse_kwargs: dict[str, Any] = {
                "ocr_text": ocr_text,
                "language": language,
                "pages_text": pages_text,
                "layout_context": layout_context,
                "retry_hint": retry_hint,
                "embedded_text_mode": embedded_text_mode,
                "simple_guest_fields": simple_guest_fields,
                "evidence_candidates": evidence_candidates,
            }
            try:
                coro = self._parser.parse(**parse_kwargs)
            except TypeError:
                parse_kwargs.pop("evidence_candidates", None)
                try:
                    coro = self._parser.parse(**parse_kwargs)
                except TypeError:
                    parse_kwargs.pop("simple_guest_fields", None)
                    try:
                        coro = self._parser.parse(**parse_kwargs)
                    except TypeError:
                        parse_kwargs.pop("embedded_text_mode", None)
                        coro = self._parser.parse(**parse_kwargs)
            return await asyncio.wait_for(coro, timeout=timeout_seconds)
        except TimeoutError as exc:
            raise PayslipParserTimeoutError(
                f"Payslip parser timed out after {timeout_seconds:.0f}s."
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


def _has_usable_fields(parsed: StructuredPayslipParse) -> bool:
    for field in parsed.field_map().values():
        if field.status in {FieldExtractionStatus.FOUND, FieldExtractionStatus.UNCERTAIN}:
            if field.value not in (None, ""):
                return True
    return False


def _warnings_for_parser_error(error: Exception) -> list[str]:
    if isinstance(error, PayslipParserSemanticError) and error.warning_code:
        return [error.warning_code]
    return []


def _retry_hint_for_error(error: Exception | None) -> str:
    if error is None:
        return ""
    if isinstance(error, PayslipParserSemanticError):
        return f"{error.category}: {error.message}"
    return str(error)


def command_from_ocr_result(
    result: OCRResult,
    *,
    cancel_check: CancelCheck = None,
    simple_guest_fields: bool = False,
    layout_analysis: dict[str, Any] | None = None,
) -> ParsePayslipFromOcrCommand:
    return ParsePayslipFromOcrCommand(
        raw_text=result.raw_text,
        language=result.language_effective or result.language_requested or "auto",
        pages=result.pages,
        engine=result.engine,
        warnings=tuple(result.warnings),
        cancel_check=cancel_check,
        simple_guest_fields=simple_guest_fields,
        layout_analysis=dict(layout_analysis or {}),
    )
