"""Developer-only Document Lab API (manual debugging)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from payroll_copilot.application.services.document_lab import DocumentLabService
from payroll_copilot.application.services.fixture_document_loader import (
    FixtureAccessError,
    list_fixture_documents,
    read_fixture_bytes,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import ExtractGuestPayslipUseCase
from payroll_copilot.application.use_cases.ocr_extract import ExtractDocumentTextUseCase
from payroll_copilot.application.use_cases.parse_payslip import ParsePayslipFromOcrUseCase
from payroll_copilot.application.use_cases.payroll_assistant import PayrollAssistantChatUseCase
from payroll_copilot.application.use_cases.persisted_validation import RunPersistedValidationUseCase
from payroll_copilot.infrastructure.ai.agents.approved_labor_law_search import YamlApprovedLaborLawSearch
from payroll_copilot.infrastructure.ai.agents.payroll_assistant_graph import PayrollAssistantGraph
from payroll_copilot.infrastructure.ai.agents.payroll_assistant_tools import (
    InMemoryDocumentSummaryStore,
    PayrollAssistantTools,
)
from payroll_copilot.infrastructure.ai.agents.validation_report_store import InMemoryValidationReportStore
from payroll_copilot.infrastructure.ai.ollama_provider import create_model_provider
from payroll_copilot.infrastructure.config.settings import Settings, get_settings
from payroll_copilot.presentation.api.dependencies import (
    get_extract_document_text_use_case,
    get_extract_guest_payslip_use_case,
    get_parse_payslip_use_case,
    get_run_persisted_validation_use_case,
)

router = APIRouter()


class FixtureItemResponse(BaseModel):
    id: str
    filename: str
    group: str
    size_bytes: int
    media_type: str


class FixtureListResponse(BaseModel):
    valid: list[FixtureItemResponse] = Field(default_factory=list)
    invalid: list[FixtureItemResponse] = Field(default_factory=list)


class ParserRunRequest(BaseModel):
    ocr: dict[str, Any]


def _require_dev_lab(settings: Settings = Depends(get_settings)) -> None:
    if settings.app_env.lower() not in {"development", "dev", "local"} and not settings.debug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


@lru_cache
def _get_assistant_use_case() -> PayrollAssistantChatUseCase | None:
    settings = get_settings()
    labor_law_search = YamlApprovedLaborLawSearch(settings.legal_rules_path)
    tools = PayrollAssistantTools(
        labor_law_search=labor_law_search,
        validation_reports=InMemoryValidationReportStore(),
        document_summaries=InMemoryDocumentSummaryStore(),
    )
    try:
        model_provider = create_model_provider(settings.model_provider, settings)
    except Exception:
        model_provider = None
    graph = PayrollAssistantGraph(tools=tools, model_provider=model_provider)
    return PayrollAssistantChatUseCase(runner=graph)


def get_document_lab_service(
    ocr_use_case: ExtractDocumentTextUseCase = Depends(get_extract_document_text_use_case),
    parse_use_case: ParsePayslipFromOcrUseCase = Depends(get_parse_payslip_use_case),
    extract_guest_use_case: ExtractGuestPayslipUseCase = Depends(get_extract_guest_payslip_use_case),
    validation_use_case: RunPersistedValidationUseCase = Depends(get_run_persisted_validation_use_case),
) -> DocumentLabService:
    return DocumentLabService(
        ocr_use_case=ocr_use_case,
        parse_use_case=parse_use_case,
        extract_guest_use_case=extract_guest_use_case,
        validation_use_case=validation_use_case,
        assistant_use_case=_get_assistant_use_case(),
    )


def _fixture_response(grouped) -> FixtureListResponse:  # noqa: ANN001
    return FixtureListResponse(
        valid=[
            FixtureItemResponse(
                id=item.id,
                filename=item.filename,
                group=item.group,
                size_bytes=item.size_bytes,
                media_type=item.media_type,
            )
            for item in grouped.get("valid", [])
        ],
        invalid=[
            FixtureItemResponse(
                id=item.id,
                filename=item.filename,
                group=item.group,
                size_bytes=item.size_bytes,
                media_type=item.media_type,
            )
            for item in grouped.get("invalid", [])
        ],
    )


def _map_fixture_error(exc: FixtureAccessError) -> HTTPException:
    status_code = status.HTTP_404_NOT_FOUND if exc.code == "fixture_not_found" else status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=status_code, detail={"code": exc.code, "message": exc.message})


async def _load_input(
    *,
    fixture_id: str | None,
    upload: UploadFile | None,
    settings: Settings,
) -> tuple[bytes, str, str, str | None]:
    if fixture_id and upload is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "ambiguous_input", "message": "Provide fixture_id or file, not both."},
        )
    if fixture_id:
        try:
            fixture, content = read_fixture_bytes(fixture_id)
        except FixtureAccessError as exc:
            raise _map_fixture_error(exc) from exc
        return content, fixture.filename, fixture.media_type, fixture.id
    if upload is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "missing_input", "message": "fixture_id or file is required."},
        )
    content = await upload.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "empty_document", "message": "Uploaded file is empty."},
        )
    max_size = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "file_too_large", "message": f"File exceeds {settings.max_upload_size_mb}MB."},
        )
    filename = upload.filename or "upload"
    media_type = upload.content_type or "application/octet-stream"
    return content, filename, media_type, None


@router.get("/fixtures", response_model=FixtureListResponse)
async def list_fixtures(_: None = Depends(_require_dev_lab)) -> FixtureListResponse:
    try:
        grouped = list_fixture_documents()
    except FixtureAccessError as exc:
        raise _map_fixture_error(exc) from exc
    return _fixture_response(grouped)


@router.post("/run/ocr")
async def run_ocr(
    fixture_id: str | None = Form(default=None),
    language: str = Form("auto"),
    file: UploadFile | None = File(default=None),
    service: DocumentLabService = Depends(get_document_lab_service),
    settings: Settings = Depends(get_settings),
    _: None = Depends(_require_dev_lab),
) -> dict[str, Any]:
    content, filename, media_type, resolved_fixture_id = await _load_input(
        fixture_id=fixture_id,
        upload=file,
        settings=settings,
    )
    from payroll_copilot.application.services.document_lab import DocumentLabSource

    return await service.run_ocr(
        content=content,
        filename=filename,
        media_type=media_type,
        language=language,
        source=DocumentLabSource(
            filename=filename,
            media_type=media_type,
            source_type="fixture" if resolved_fixture_id else "upload",
            fixture_id=resolved_fixture_id,
        ),
    )


@router.post("/run/parser")
async def run_parser(
    body: ParserRunRequest,
    service: DocumentLabService = Depends(get_document_lab_service),
    _: None = Depends(_require_dev_lab),
) -> dict[str, Any]:
    return await service.run_parser(ocr_payload=body.ocr)


@router.post("/run/ocr-parser")
async def run_ocr_parser(
    fixture_id: str | None = Form(default=None),
    language: str = Form("auto"),
    file: UploadFile | None = File(default=None),
    service: DocumentLabService = Depends(get_document_lab_service),
    settings: Settings = Depends(get_settings),
    _: None = Depends(_require_dev_lab),
) -> dict[str, Any]:
    content, filename, media_type, resolved_fixture_id = await _load_input(
        fixture_id=fixture_id,
        upload=file,
        settings=settings,
    )
    from payroll_copilot.application.services.document_lab import DocumentLabSource

    return await service.run_ocr_parser(
        content=content,
        filename=filename,
        media_type=media_type,
        language=language,
        source=DocumentLabSource(
            filename=filename,
            media_type=media_type,
            source_type="fixture" if resolved_fixture_id else "upload",
            fixture_id=resolved_fixture_id,
        ),
    )


@router.post("/run/pipeline")
async def run_pipeline(
    fixture_id: str | None = Form(default=None),
    language: str = Form("auto"),
    locale: str | None = Form(default=None),
    include_explanation: bool = Form(default=True),
    file: UploadFile | None = File(default=None),
    service: DocumentLabService = Depends(get_document_lab_service),
    settings: Settings = Depends(get_settings),
    _: None = Depends(_require_dev_lab),
) -> dict[str, Any]:
    content, filename, media_type, resolved_fixture_id = await _load_input(
        fixture_id=fixture_id,
        upload=file,
        settings=settings,
    )
    from payroll_copilot.application.services.document_lab import DocumentLabSource

    return await service.run_full_pipeline(
        content=content,
        filename=filename,
        media_type=media_type,
        language=language,
        source=DocumentLabSource(
            filename=filename,
            media_type=media_type,
            source_type="fixture" if resolved_fixture_id else "upload",
            fixture_id=resolved_fixture_id,
        ),
        locale=locale,
        include_explanation=include_explanation,
    )
