"""Synchronous OCR text extraction API (Phase 1).

Returns generic document text + confidence only.
Does not perform payroll field parsing or validation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from payroll_copilot.application.exceptions import (
    OcrCorruptedDocumentError,
    OcrEmptyDocumentError,
    OcrError,
    OcrLanguageNotSupportedError,
    OcrProviderError,
    OcrProviderUnavailableError,
    OcrTimeoutError,
    OcrUnsupportedFileError,
)
from payroll_copilot.application.ports.ocr import OCRResult
from payroll_copilot.application.use_cases.ocr_extract import (
    ExtractDocumentTextCommand,
    ExtractDocumentTextUseCase,
)
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.presentation.api.dependencies import get_extract_document_text_use_case

router = APIRouter()


class OcrWordResponse(BaseModel):
    text: str
    confidence: float | None = None
    bbox: list[float]
    block_number: int = 0
    paragraph_number: int = 0
    line_number: int = 0
    word_number: int = 0


class OcrLineResponse(BaseModel):
    text: str
    confidence: float | None = None
    bbox: list[float] | None = None
    words: list[OcrWordResponse] = Field(default_factory=list)


class OcrPageResponse(BaseModel):
    page: int
    language: str
    text: str
    confidence: float | None = None
    lines: list[OcrLineResponse] = Field(default_factory=list)
    words: list[OcrWordResponse] = Field(default_factory=list)


class OcrExtractResponse(BaseModel):
    engine: str
    language_requested: str
    language_effective: str
    overall_confidence: float | None = None
    raw_text: str
    warnings: list[str] = Field(default_factory=list)
    pages: list[OcrPageResponse]


_STATUS_BY_CODE: dict[str, int] = {
    "unsupported_file": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    "empty_document": status.HTTP_400_BAD_REQUEST,
    "corrupted_document": status.HTTP_400_BAD_REQUEST,
    "language_not_supported": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "ocr_timeout": status.HTTP_504_GATEWAY_TIMEOUT,
    "provider_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
    "ocr_failure": status.HTTP_500_INTERNAL_SERVER_ERROR,
    "ocr_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def _map_ocr_error(exc: OcrError) -> HTTPException:
    status_code = _STATUS_BY_CODE.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.message},
    )


def _to_response(result: OCRResult) -> OcrExtractResponse:
    return OcrExtractResponse(
        engine=result.engine,
        language_requested=result.language_requested,
        language_effective=result.language_effective,
        overall_confidence=result.overall_confidence,
        raw_text=result.raw_text,
        warnings=list(result.warnings),
        pages=[
            OcrPageResponse(
                page=page.page,
                language=page.language,
                text=page.text,
                confidence=page.confidence,
                lines=[
                    OcrLineResponse(
                        text=line.text,
                        confidence=line.confidence,
                        bbox=list(line.bbox) if line.bbox else None,
                        words=[
                            OcrWordResponse(
                                text=word.text,
                                confidence=word.confidence,
                                bbox=list(word.bbox),
                                block_number=word.block_number,
                                paragraph_number=word.paragraph_number,
                                line_number=word.line_number,
                                word_number=word.word_number,
                            )
                            for word in line.words
                        ],
                    )
                    for line in page.lines
                ],
                words=[
                    OcrWordResponse(
                        text=word.text,
                        confidence=word.confidence,
                        bbox=list(word.bbox),
                        block_number=word.block_number,
                        paragraph_number=word.paragraph_number,
                        line_number=word.line_number,
                        word_number=word.word_number,
                    )
                    for word in page.words
                ],
            )
            for page in result.pages
        ],
    )


@router.post("/extract", response_model=OcrExtractResponse)
async def extract_document_text(
    file: UploadFile = File(...),
    language: str = Form("auto"),
    use_case: ExtractDocumentTextUseCase = Depends(get_extract_document_text_use_case),
) -> OcrExtractResponse:
    """Extract text from PDF/PNG/JPG/JPEG via the configured OCR provider.

    Phase 1 scope: text + confidence only. No payroll field extraction.
    Hebrew requests may report ``engine=tesseract`` when PaddleOCR is primary
    (intentional H1 fallback).
    """
    settings = get_settings()
    max_size = settings.max_upload_size_mb * 1024 * 1024
    content = await file.read()

    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "file_too_large",
                "message": f"File exceeds maximum size of {settings.max_upload_size_mb}MB",
            },
        )

    command = ExtractDocumentTextCommand(
        content=content,
        filename=file.filename,
        content_type=file.content_type,
        language=language,
    )

    try:
        result = await use_case.execute(command)
    except (
        OcrUnsupportedFileError,
        OcrEmptyDocumentError,
        OcrCorruptedDocumentError,
        OcrLanguageNotSupportedError,
        OcrTimeoutError,
        OcrProviderUnavailableError,
        OcrProviderError,
        OcrError,
    ) as exc:
        raise _map_ocr_error(exc) from exc

    return _to_response(result)
