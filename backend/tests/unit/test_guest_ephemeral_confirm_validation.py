"""Guest confirm + validation stay ephemeral (no permanent DB/S3)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
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
    """Corrections update Document Model (dynamic_entries), not durable DB/S3.

    structured_data remains the pre-confirm extraction snapshot until confirm
    projects dynamic_entries into canonical structured_data.
    """
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
    # Authoritative review state: fields / dynamic_entries carry the correction.
    assert any(
        row.get("key") == "base_salary" and row.get("value") == 13000 for row in result.fields
    )
    assert any(
        row.get("key") == "base_salary" and row.get("value") == 13000 for row in result.entries
    )
    docs.save.assert_not_awaited()
    extractions.save.assert_not_awaited()
    updated = get_guest_ephemeral_store().get(session.document_id)
    assert updated is not None
    assert any(
        row.get("key") == "base_salary" and row.get("value") == 13000
        for row in updated.dynamic_entries
    )
    # Pre-confirm snapshot is intentionally unchanged (not dual-written).
    assert updated.structured_data["base_salary"]["value"] == 12000
    assert result.structured_data["base_salary"]["value"] == 12000


@pytest.mark.asyncio
async def test_ephemeral_correction_survives_confirm_into_canonical_structured() -> None:
    """review → confirm → projection must validate the corrected value, not stale extract."""
    from payroll_copilot.application.use_cases.extract_guest_payslip import (
        ExtractGuestPayslipUseCase,
    )

    # Mirror production extract: Document Model rows exist before correction.
    session = _seed_session(
        dynamic_entries=[
            {
                "key": "base_salary",
                "value": 12000,
                "confidence": 0.9,
                "source_text": "12000",
                "source": "extractor",
            },
            {
                "key": "gross_salary",
                "value": 12000,
                "confidence": 0.9,
                "source_text": "12000",
                "source": "extractor",
            },
        ]
    )
    correct = CorrectGuestExtractionUseCase(
        document_repository=MagicMock(),
        extraction_repository=MagicMock(),
    )
    await correct.execute(
        document_id=session.document_id,
        corrections=[FieldCorrection(key="base_salary", value=13000)],
    )

    extract_uc = ExtractGuestPayslipUseCase(
        document_repository=MagicMock(),
        extraction_repository=MagicMock(),
        object_storage=MagicMock(),
        organization_bootstrap=MagicMock(),
        ocr_use_case=MagicMock(),
        document_extractor=MagicMock(),
    )
    _document, extraction = extract_uc.confirm_ephemeral_session(session.document_id)
    assert extraction.confirmation_status == "confirmed"
    assert extraction.structured_data["base_salary"]["value"] == 13000
    # Provenance: Document Model retained under structured_data.dynamic_entries
    entries = extraction.structured_data.get("dynamic_entries") or []
    corrected = next(row for row in entries if row.get("key") == "base_salary")
    assert corrected["value"] == 13000
    assert corrected.get("source") == "user"

    # Validation context reads confirmed structured_data (corrected value).
    bundle = await GuestExtractionValidationContextBuilder(
        extraction_repository=MagicMock()
    ).build(document_id=session.document_id, organization_id=None, require_confirmed=True)
    assert bundle.guest_ephemeral is True
    assert bundle.command.payslip.base_salary is not None
    assert bundle.command.payslip.base_salary.amount == Decimal("13000")


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
