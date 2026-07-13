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
from payroll_copilot.application.ports.ocr import OcrLine, OcrPage, OcrWord
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


class OcrWordIn(BaseModel):
    text: str
    confidence: float | None = None
    bbox: list[float] | None = None
    block_number: int = 0
    paragraph_number: int = 0
    line_number: int = 0
    word_number: int = 0


class OcrLineIn(BaseModel):
    text: str
    confidence: float | None = None
    bbox: list[float] | None = None
    words: list[OcrWordIn] = Field(default_factory=list)


class OcrPageIn(BaseModel):
    page: int
    language: str = "auto"
    text: str = ""
    confidence: float | None = None
    lines: list[OcrLineIn] = Field(default_factory=list)
    words: list[OcrWordIn] = Field(default_factory=list)


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
    "semantic_validation_failed": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "parser_timeout": status.HTTP_504_GATEWAY_TIMEOUT,
    "parser_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
    "parser_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def _map_error(exc: PayslipParserError) -> HTTPException:
    return HTTPException(
        status_code=_STATUS_BY_CODE.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        detail={"code": exc.code, "message": exc.message},
    )


def _to_word(word: OcrWordIn) -> OcrWord | None:
    text = (word.text or "").strip()
    if not text:
        return None
    bbox = tuple(word.bbox) if word.bbox and len(word.bbox) == 4 else None
    if bbox is None:
        return None
    return OcrWord(
        text=text,
        confidence=word.confidence,
        bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
        block_number=word.block_number,
        paragraph_number=word.paragraph_number,
        line_number=word.line_number,
        word_number=word.word_number,
    )


def _to_pages(pages: list[OcrPageIn]) -> tuple[OcrPage, ...]:
    result: list[OcrPage] = []
    for page in pages:
        lines = []
        for line in page.lines:
            words = tuple(w for w in (_to_word(item) for item in line.words) if w is not None)
            lines.append(
                OcrLine(
                    text=line.text,
                    confidence=line.confidence,
                    bbox=tuple(line.bbox) if line.bbox and len(line.bbox) == 4 else None,
                    words=words,
                )
            )
        page_words = tuple(w for w in (_to_word(item) for item in page.words) if w is not None)
        result.append(
            OcrPage(
                page=page.page,
                language=page.language,
                text=page.text,
                confidence=page.confidence,
                lines=tuple(lines),
                words=page_words,
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
        warnings=tuple(body.warnings),
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
