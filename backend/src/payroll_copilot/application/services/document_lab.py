"""Developer Document Lab orchestration — reuses existing OCR/parser/validation use cases."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from payroll_copilot.application.ports.ocr import OCRResult, OcrLine, OcrPage, OcrWord
from payroll_copilot.application.ports.payslip_parser import StructuredPayslipParse
from payroll_copilot.application.use_cases.extract_guest_payslip import (
    ExtractGuestPayslipUseCase,
    GuestPayslipExtractionCommand,
)
from payroll_copilot.application.use_cases.ocr_extract import (
    ExtractDocumentTextCommand,
    ExtractDocumentTextUseCase,
)
from payroll_copilot.application.use_cases.parse_payslip import (
    ParsePayslipFromOcrUseCase,
    command_from_ocr_result,
)
from payroll_copilot.application.use_cases.persisted_validation import (
    RunPersistedValidationCommand,
    RunPersistedValidationUseCase,
)
from payroll_copilot.application.use_cases.payroll_assistant import (
    AssistantChatCommand,
    PayrollAssistantChatUseCase,
)
from payroll_copilot.application.validation.structured_payslip_mapper import (
    MappedValidationInputs,
    map_structured_payslip_to_validation_inputs,
)
from payroll_copilot.domain.value_objects import Money


def _words_from_payload(raw_words: object) -> tuple[OcrWord, ...]:
    """Rebuild OCR words from Document Lab OCR JSON without inventing geometry."""
    if not isinstance(raw_words, list):
        return ()
    words: list[OcrWord] = []
    for item in raw_words:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        bbox = item.get("bbox")
        if not text or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        try:
            box = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        except (TypeError, ValueError):
            continue
        if box[2] <= 0 or box[3] <= 0:
            continue
        words.append(
            OcrWord(
                text=text,
                confidence=item.get("confidence"),
                bbox=box,
                block_number=int(item.get("block_number") or 0),
                paragraph_number=int(item.get("paragraph_number") or 0),
                line_number=int(item.get("line_number") or 0),
                word_number=int(item.get("word_number") or 0),
            )
        )
    return tuple(words)


def ocr_result_to_dict(result: OCRResult) -> dict[str, Any]:
    return {
        "engine": result.engine,
        "language_requested": result.language_requested,
        "language_effective": result.language_effective,
        "overall_confidence": result.overall_confidence,
        "raw_text": result.raw_text,
        "warnings": list(result.warnings),
        "pages": [
            {
                "page": page.page,
                "language": page.language,
                "text": page.text,
                "confidence": page.confidence,
                "lines": [
                    {
                        "text": line.text,
                        "confidence": line.confidence,
                        "bbox": list(line.bbox) if line.bbox else None,
                        "words": [
                            {
                                "text": word.text,
                                "confidence": word.confidence,
                                "bbox": list(word.bbox),
                                "block_number": word.block_number,
                                "paragraph_number": word.paragraph_number,
                                "line_number": word.line_number,
                                "word_number": word.word_number,
                            }
                            for word in line.words
                        ],
                    }
                    for line in page.lines
                ],
                "words": [
                    {
                        "text": word.text,
                        "confidence": word.confidence,
                        "bbox": list(word.bbox),
                        "block_number": word.block_number,
                        "paragraph_number": word.paragraph_number,
                        "line_number": word.line_number,
                        "word_number": word.word_number,
                    }
                    for word in page.words
                ],
            }
            for page in result.pages
        ],
    }


def parser_fields_to_dict(fields: StructuredPayslipParse) -> dict[str, Any]:
    payload = fields.model_dump(mode="json")
    additional = payload.pop("additional_fields", {})
    rows: list[dict[str, Any]] = []
    for key, value in payload.items():
        if key in {"parser_notes", "language"}:
            continue
        if isinstance(value, dict):
            rows.append({"key": key, **value})
    if isinstance(additional, dict):
        for key, value in additional.items():
            if isinstance(value, dict):
                rows.append({"key": str(key), **value})
    return {
        "structured": payload | {"additional_fields": additional},
        "fields": rows,
    }


def _money(value: Money | None) -> str | None:
    if value is None:
        return None
    return f"{value.amount} {value.currency}"


def validation_context_summary(mapped: MappedValidationInputs) -> dict[str, Any]:
    cmd = mapped.command
    payslip = cmd.payslip
    employee = cmd.employee
    department = cmd.department
    return {
        "extraction_connected": mapped.extraction_connected,
        "core_fields_usable": mapped.core_fields_usable,
        "mapping_warnings": list(mapped.mapping_warnings),
        "unused_fields": list(mapped.unused_fields),
        "employee": {
            "employee_number": employee.employee_number,
            "name": employee.full_name,
            "employment_type": employee.employment_type.value,
            "salary_type": employee.salary_type.value,
            "hourly_rate": str(employee.hourly_rate) if employee.hourly_rate is not None else None,
            "rule_profile": department.rule_profile,
        },
        "payslip": {
            "employee_name": payslip.employee_name,
            "employee_number": payslip.employee_number,
            "period": (
                {"year": payslip.period.year, "month": payslip.period.month}
                if payslip.period is not None
                else None
            ),
            "gross_salary": _money(payslip.gross_salary),
            "net_salary": _money(payslip.net_salary),
            "base_salary": _money(payslip.base_salary),
            "tax_deducted": _money(payslip.tax_deducted),
            "pension_employee": _money(payslip.pension_employee),
            "transportation_allowance": _money(payslip.transportation_allowance),
            "work_hours": str(payslip.work_hours) if payslip.work_hours is not None else None,
            "overtime_hours": str(payslip.overtime_hours) if payslip.overtime_hours is not None else None,
            "additional_fields": payslip.additional_fields,
        },
        "field_confidences": cmd.field_confidences,
    }


def validation_run_to_dict(record) -> dict[str, Any]:  # noqa: ANN001
    findings = [
        {
            "id": str(finding.id),
            "rule_id": finding.rule_id,
            "severity": finding.severity.value,
            "message_key": finding.message_key,
            "expected_value": finding.expected_value,
            "actual_value": finding.actual_value,
            "confidence": float(finding.confidence),
            "legal_reference": finding.legal_reference,
        }
        for finding in record.findings
    ]
    enrichment = record.enrichment
    return {
        "id": str(record.id),
        "document_id": str(record.document_id),
        "status": record.status.value,
        "overall_result": record.overall_result.value if record.overall_result else None,
        "rules_evaluated": record.rules_evaluated,
        "rules_failed": record.rules_failed,
        "extraction_connected": enrichment.extraction_connected if enrichment else False,
        "validation_scope": [
            {
                "key": item.key,
                "status": item.status,
                "reason": item.reason,
            }
            for item in (enrichment.validation_scope if enrichment else [])
        ],
        "findings": findings,
    }


@dataclass(frozen=True, slots=True)
class DocumentLabSource:
    filename: str
    media_type: str
    source_type: str
    fixture_id: str | None = None


def serialize_document_lab_source(source: DocumentLabSource) -> dict[str, Any]:
    return asdict(source)


class DocumentLabService:
    """Step-by-step document pipeline debugger for developers."""

    def __init__(
        self,
        *,
        ocr_use_case: ExtractDocumentTextUseCase,
        parse_use_case: ParsePayslipFromOcrUseCase,
        extract_guest_use_case: ExtractGuestPayslipUseCase,
        validation_use_case: RunPersistedValidationUseCase,
        assistant_use_case: PayrollAssistantChatUseCase | None = None,
    ) -> None:
        self._ocr = ocr_use_case
        self._parse = parse_use_case
        self._extract_guest = extract_guest_use_case
        self._validation = validation_use_case
        self._assistant = assistant_use_case

    async def run_ocr(
        self,
        *,
        content: bytes,
        filename: str,
        media_type: str,
        language: str,
        source: DocumentLabSource,
    ) -> dict[str, Any]:
        result = await self._ocr.execute(
            ExtractDocumentTextCommand(
                content=content,
                filename=filename,
                content_type=media_type,
                language=language,
            )
        )
        return {
            "source": serialize_document_lab_source(source),
            "ocr": ocr_result_to_dict(result),
        }

    async def run_parser(self, *, ocr_payload: dict[str, Any]) -> dict[str, Any]:
        pages: list[OcrPage] = []
        for page in ocr_payload.get("pages") or []:
            lines = tuple(
                OcrLine(
                    text=str(line.get("text") or ""),
                    confidence=line.get("confidence"),
                    bbox=tuple(line["bbox"]) if line.get("bbox") else None,
                    words=_words_from_payload(line.get("words")),
                )
                for line in page.get("lines") or []
            )
            pages.append(
                OcrPage(
                    page=int(page.get("page") or 1),
                    language=str(page.get("language") or "auto"),
                    text=str(page.get("text") or ""),
                    confidence=page.get("confidence"),
                    lines=lines,
                    words=_words_from_payload(page.get("words")),
                )
            )
        ocr_result = OCRResult(
            pages=tuple(pages),
            engine=ocr_payload.get("engine") or "unknown",
            language_requested=ocr_payload.get("language_requested") or "auto",
            language_effective=ocr_payload.get("language_effective") or "auto",
            overall_confidence=ocr_payload.get("overall_confidence"),
            raw_text=ocr_payload.get("raw_text") or "",
            warnings=tuple(ocr_payload.get("warnings") or []),
        )
        command = command_from_ocr_result(ocr_result)
        parse_result = await self._parse.execute(command)
        structured = parse_result.fields.model_dump(mode="json")
        mapped = map_structured_payslip_to_validation_inputs(
            document_id=uuid4(),
            structured_data=structured,
            parser_completed=True,
        )
        return {
            "parser": {
                "model": parse_result.model,
                "language": parse_result.language,
                "retry_used": parse_result.retry_used,
                "warnings": list(parse_result.warnings),
                **parser_fields_to_dict(parse_result.fields),
            },
            "validation_context_summary": validation_context_summary(mapped),
        }

    async def run_ocr_parser(
        self,
        *,
        content: bytes,
        filename: str,
        media_type: str,
        language: str,
        source: DocumentLabSource,
    ) -> dict[str, Any]:
        ocr_step = await self.run_ocr(
            content=content,
            filename=filename,
            media_type=media_type,
            language=language,
            source=source,
        )
        parser_step = await self.run_parser(ocr_payload=ocr_step["ocr"])
        return {**ocr_step, **parser_step}

    async def run_full_pipeline(
        self,
        *,
        content: bytes,
        filename: str,
        media_type: str,
        language: str,
        source: DocumentLabSource,
        locale: str | None,
        include_explanation: bool,
    ) -> dict[str, Any]:
        extraction = await self._extract_guest.execute(
            GuestPayslipExtractionCommand(
                content=content,
                original_filename=filename,
                mime_type=media_type,
                language=language,
            )
        )
        validation_record = await self._validation.execute(
            RunPersistedValidationCommand(
                document_id=extraction.document_id,
                locale=locale,
            )
        )
        explanation: str | None = None
        if include_explanation and self._assistant is not None and validation_record.findings:
            first = validation_record.findings[0]
            try:
                assistant = await self._assistant.execute(
                    AssistantChatCommand(
                        message=(
                            f"Explain the existing validation finding with rule_id {first.rule_id}. "
                            "Do not create new findings."
                        ),
                        validation_run_id=validation_record.id,
                        document_ids=[extraction.document_id],
                        locale=locale,
                    )
                )
                explanation = assistant.answer
            except Exception:
                explanation = None

        structured_data: dict[str, Any] = {}
        for field in extraction.fields:
            structured_data[field.key] = {
                "value": field.value,
                "confidence": field.confidence,
                "source_text": field.source_text,
                "status": field.status,
            }
        mapped = map_structured_payslip_to_validation_inputs(
            document_id=extraction.document_id,
            structured_data=structured_data,
            parser_completed=extraction.parser_status == "completed",
        )

        return {
            "source": serialize_document_lab_source(source),
            "extraction": {
                "document_id": str(extraction.document_id),
                "extraction_id": str(extraction.extraction_id),
                "ocr_status": extraction.ocr_status,
                "parser_status": extraction.parser_status,
                "ocr_engine": extraction.ocr_engine,
                "parser_model": extraction.parser_model,
                "warnings": extraction.warnings,
                "fields": [
                    {
                        "key": field.key,
                        "value": field.value,
                        "confidence": field.confidence,
                        "source_text": field.source_text,
                        "status": field.status,
                    }
                    for field in extraction.fields
                ],
                "raw_text": extraction.raw_text,
            },
            "validation_context_summary": validation_context_summary(mapped),
            "validation": validation_run_to_dict(validation_record),
            "ai_explanation": explanation,
        }
