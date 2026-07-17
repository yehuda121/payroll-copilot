"""Guest confirm + validation stay ephemeral (no permanent DB/S3)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from payroll_copilot.application.services.guest_ephemeral_store import (
    GuestEphemeralSession,
    get_guest_ephemeral_store,
    reset_guest_ephemeral_store_for_tests,
)
from payroll_copilot.application.use_cases.correct_guest_extraction import (
    CorrectGuestExtractionUseCase,
    FieldCorrection,
)
from payroll_copilot.application.use_cases.persisted_validation import (
    RunPersistedValidationCommand,
    RunPersistedValidationUseCase,
)
from payroll_copilot.application.validation.guest_extraction_context_builder import (
    GuestExtractionValidationContextBuilder,
)
from payroll_copilot.domain.enums import DocumentType
from payroll_copilot.domain.value_objects import ConfidenceScore, ValidationReport


@pytest.fixture(autouse=True)
def _clean_store() -> None:
    reset_guest_ephemeral_store_for_tests()
    yield
    reset_guest_ephemeral_store_for_tests()


def _seed_session(**overrides):  # noqa: ANN003
    store = get_guest_ephemeral_store()
    doc_id = uuid4()
    session = GuestEphemeralSession(
        document_id=doc_id,
        extraction_id=uuid4(),
        content=b"pdf",
        original_filename="slip.pdf",
        mime_type="application/pdf",
        language="auto",
        ocr_status="completed",
        parser_status="completed",
        ocr_engine="tesseract",
        parser_model="fake",
        raw_text="Base 12000",
        structured_data={
            "base_salary": {
                "value": 12000,
                "confidence": 0.9,
                "source_text": "12000",
                "status": "FOUND",
            },
            "gross_salary": {
                "value": 12000,
                "confidence": 0.9,
                "source_text": "12000",
                "status": "FOUND",
            },
        },
        ocr_result={},
        warnings=[],
        error_message=None,
        field_confidences={},
        created_at=datetime.utcnow(),
    )
    for key, value in overrides.items():
        setattr(session, key, value)
    store.save(session)
    return session


@pytest.mark.asyncio
async def test_ephemeral_corrections_do_not_touch_db() -> None:
    session = _seed_session()
    docs = MagicMock()
    extractions = MagicMock()
    docs.get_by_id = AsyncMock(return_value=None)
    extractions.get_latest_for_document = AsyncMock(return_value=None)
    extractions.save = AsyncMock()
    docs.save = AsyncMock()

    use_case = CorrectGuestExtractionUseCase(
        document_repository=docs,
        extraction_repository=extractions,
    )
    result = await use_case.execute(
        document_id=session.document_id,
        corrections=[FieldCorrection(key="base_salary", value=13000)],
    )
    assert result.structured_data["base_salary"]["value"] == 13000
    docs.save.assert_not_awaited()
    extractions.save.assert_not_awaited()
    updated = get_guest_ephemeral_store().get(session.document_id)
    assert updated is not None
    assert updated.structured_data["base_salary"]["value"] == 13000


@pytest.mark.asyncio
async def test_guest_validation_from_confirmed_ephemeral_skips_persist() -> None:
    session = _seed_session()
    store = get_guest_ephemeral_store()
    store.confirm(session.document_id)
    support = store.save_supporting(
        document_type=DocumentType.NATIONAL_ID,
        content=b"id",
        original_filename="id.pdf",
        mime_type="application/pdf",
        payslip_document_id=session.document_id,
    )

    fake_report = ValidationReport(
        validation_run_id=uuid4(),
        overall_result="pass",
        overall_confidence=ConfidenceScore.certain(),
        rules_evaluated=1,
        rules_failed=0,
        findings=(),
    )
    run_validation = MagicMock()
    run_validation.execute.return_value = fake_report

    run_repo = MagicMock()
    run_repo.save = AsyncMock()
    finding_repo = MagicMock()
    finding_repo.save_all = AsyncMock()
    doc_repo = MagicMock()
    doc_repo.get_by_id = AsyncMock(return_value=None)
    bootstrap = MagicMock()
    bootstrap.ensure_demo_organization = AsyncMock()

    use_case = RunPersistedValidationUseCase(
        run_validation=run_validation,
        guest_context_builder=GuestExtractionValidationContextBuilder(extraction_repository=MagicMock()),
        document_repository=doc_repo,
        validation_run_repository=run_repo,
        validation_finding_repository=finding_repo,
        organization_bootstrap=bootstrap,
    )
    record = await use_case.execute(
        RunPersistedValidationCommand(
            document_id=session.document_id,
            supporting_document_ids=(support.document_id,),
            locale="en",
        )
    )
    assert record.document_id == session.document_id
    assert record.findings is not None
    run_repo.save.assert_not_awaited()
    finding_repo.save_all.assert_not_awaited()
    bootstrap.ensure_demo_organization.assert_not_awaited()
    doc_repo.get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_guest_validation_requires_confirm() -> None:
    session = _seed_session()
    fake_report = ValidationReport(
        validation_run_id=uuid4(),
        overall_result="pass",
        overall_confidence=ConfidenceScore.certain(),
        rules_evaluated=0,
        rules_failed=0,
        findings=(),
    )
    use_case = RunPersistedValidationUseCase(
        run_validation=MagicMock(execute=MagicMock(return_value=fake_report)),
        guest_context_builder=GuestExtractionValidationContextBuilder(extraction_repository=MagicMock()),
        document_repository=MagicMock(get_by_id=AsyncMock(return_value=None)),
        validation_run_repository=MagicMock(save=AsyncMock()),
        validation_finding_repository=MagicMock(save_all=AsyncMock()),
        organization_bootstrap=MagicMock(ensure_demo_organization=AsyncMock()),
    )
    from payroll_copilot.application.validation.guest_extraction_context_builder import (
        ExtractionRequiredError,
    )

    with pytest.raises(ExtractionRequiredError):
        await use_case.execute(RunPersistedValidationCommand(document_id=session.document_id))
