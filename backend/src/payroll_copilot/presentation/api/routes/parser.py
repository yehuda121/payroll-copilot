"""AI payslip parser API (Phase 2A).

Accepts OCR JSON body → returns structured payslip fields.
Does not run Rule Engine / payroll validation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from payroll_copilot.application.exceptions import (
    PayslipParserEmptyOcrError,
    PayslipParserError,
    PayslipParserJsonError,
    PayslipParserSchemaError,
    PayslipParserTimeoutError,
    PayslipParserUnavailableError,
)
from payroll_copilot.application.ports.ocr import OcrLine, OcrPage
from payroll_copilot.application.ports.payslip_parser import (
    PayslipParseResult,
    StructuredPayslipParse,
)
from payroll_copilot.application.use_cases.parse_payslip import (
    ParsePayslipFromOcrCommand,
    ParsePayslipFromOcrUseCase,
)
from payroll_copilot.presentation.api.dependencies import get_parse_payslip_use_case

router = APIRouter()


class OcrLineIn(BaseModel):
    text: str
    confidence: float | None = None
    bbox: list[float] | None = None


class OcrPageIn(BaseModel):
    page: int
    language: str = "auto"
    text: str = ""
    confidence: float | None = None
    lines: list[OcrLineIn] = Field(default_factory=list)


class ParsePayslipRequest(BaseModel):
    """OCR result payload from Phase 1 (or equivalent)."""

    model_config = ConfigDict(extra="ignore")

    raw_text: str = ""
    language: str | None = None
    language_requested: str | None = None
    language_effective: str | None = None
    engine: str | None = None
    overall_confidence: float | None = None
    warnings: list[str] = Field(default_factory=list)
    pages: list[OcrPageIn] = Field(default_factory=list)


class ParsePayslipResponse(BaseModel):
    model: str
    language: str | None = None
    retry_used: bool = False
    warnings: list[str] = Field(default_factory=list)
    fields: StructuredPayslipParse


_STATUS_BY_CODE: dict[str, int] = {
    "empty_ocr": status.HTTP_400_BAD_REQUEST,
    "invalid_json": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "schema_validation_failed": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "parser_timeout": status.HTTP_504_GATEWAY_TIMEOUT,
    "parser_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
    "parser_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def _map_error(exc: PayslipParserError) -> HTTPException:
    return HTTPException(
        status_code=_STATUS_BY_CODE.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        detail={"code": exc.code, "message": exc.message},
    )


def _to_pages(pages: list[OcrPageIn]) -> tuple[OcrPage, ...]:
    result: list[OcrPage] = []
    for page in pages:
        lines = tuple(
            OcrLine(
                text=line.text,
                confidence=line.confidence,
                bbox=tuple(line.bbox) if line.bbox and len(line.bbox) == 4 else None,
            )
            for line in page.lines
        )
        result.append(
            OcrPage(
                page=page.page,
                language=page.language,
                text=page.text,
                confidence=page.confidence,
                lines=lines,
            )
        )
    return tuple(result)


def _to_response(result: PayslipParseResult) -> ParsePayslipResponse:
    return ParsePayslipResponse(
        model=result.model,
        language=result.language,
        retry_used=result.retry_used,
        warnings=list(result.warnings),
        fields=result.fields,
    )


@router.post("/payslip", response_model=ParsePayslipResponse)
async def parse_payslip_from_ocr(
    body: ParsePayslipRequest,
    use_case: ParsePayslipFromOcrUseCase = Depends(get_parse_payslip_use_case),
) -> ParsePayslipResponse:
    """Parse OCR text into structured payslip fields using the local LLM.

    Phase 2A: extraction only. No legal checks, no Rule Engine, no payroll validation.
    """
    language = (
        body.language
        or body.language_effective
        or body.language_requested
        or "auto"
    )
    command = ParsePayslipFromOcrCommand(
        raw_text=body.raw_text,
        language=language,
        pages=_to_pages(body.pages) if body.pages else None,
        engine=body.engine,
    )

    try:
        result = await use_case.execute(command)
    except (
        PayslipParserEmptyOcrError,
        PayslipParserJsonError,
        PayslipParserSchemaError,
        PayslipParserTimeoutError,
        PayslipParserUnavailableError,
        PayslipParserError,
    ) as exc:
        raise _map_error(exc) from exc

    return _to_response(result)
