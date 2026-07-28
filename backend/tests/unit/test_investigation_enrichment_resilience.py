"""Resilience tests for Scenario C ephemeral enrichment (P2)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from payroll_copilot.application.exceptions import OcrTimeoutError
from payroll_copilot.application.use_cases.ocr_extract import ExtractDocumentTextUseCase
from payroll_copilot.domain.investigation.types import (
    InvestigationOutcome,
    PeriodRef,
    PeriodSnapshot,
)
from payroll_copilot.infrastructure.ai.agents.investigation_data_adapter import (
    InvestigationDataAdapter,
)
from payroll_copilot.infrastructure.ai.agents.payroll_investigation_graph import (
    PayrollInvestigationGraph,
)


class _RaisingStorage:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def download(self, key: str) -> bytes:
        raise self._exc


class _EmptyStorage:
    async def download(self, key: str) -> bytes:
        return b""


class _OkStorage:
    def __init__(self, payload: bytes = b"%PDF-1.4 corrupt") -> None:
        self.payload = payload

    async def download(self, key: str) -> bytes:
        return self.payload


class _TimeoutOcr:
    async def extract(self, **kwargs):  # noqa: ANN003
        raise OcrTimeoutError("OCR processing timed out after 1s.")


class _EmptyOcr:
    async def extract(self, **kwargs):  # noqa: ANN003
        return SimpleNamespace(pages=(), raw_text="")


class _OkOcr:
    async def extract(self, **kwargs):  # noqa: ANN003
        return SimpleNamespace(
            pages=(SimpleNamespace(text="שעות נוספות 12"),),
            raw_text="שעות נוספות 12",
        )


class _RaisingParser:
    async def parse(self, **kwargs):  # noqa: ANN003
        raise RuntimeError("parser boom")


class _OkParser:
    async def parse(self, **kwargs):  # noqa: ANN003
        return SimpleNamespace(
            fields=SimpleNamespace(
                model_dump=lambda: {"overtime_hours": {"value": "12", "status": "FOUND"}}
            ),
            parsed_payload={"overtime_hours": {"value": "12"}},
        )


def _adapter(*, storage, ocr, parser) -> InvestigationDataAdapter:
    return InvestigationDataAdapter(
        documents=SimpleNamespace(),
        extractions=SimpleNamespace(),
        validation_runs=SimpleNamespace(),
        validation_findings=SimpleNamespace(),
        object_storage=storage,
        ocr_use_case=ExtractDocumentTextUseCase(ocr, timeout_seconds=5)
        if not isinstance(ocr, ExtractDocumentTextUseCase)
        else ocr,
        payslip_parser=parser,
    )


def _snap(fields: dict | None = None) -> PeriodSnapshot:
    return PeriodSnapshot(
        period=PeriodRef(2026, 7),
        document_id=uuid4(),
        storage_key="org/emp/payslip.pdf",
        structured_fields=fields or {},
    )


@pytest.mark.asyncio
async def test_adapter_timeout_returns_failed_note_without_raise() -> None:
    adapter = _adapter(storage=_OkStorage(), ocr=_TimeoutOcr(), parser=_OkParser())
    result = await adapter.enrich_snapshot_from_original(
        _snap(),
        missing_keys=("overtime_hours",),
    )
    assert result.enrichment_applied is False
    assert result.enrichment_notes == "enrichment_failed:OcrTimeoutError"


@pytest.mark.asyncio
async def test_adapter_empty_s3_object_is_soft_failure() -> None:
    adapter = _adapter(storage=_EmptyStorage(), ocr=_OkOcr(), parser=_OkParser())
    result = await adapter.enrich_snapshot_from_original(
        _snap(),
        missing_keys=("overtime_hours",),
    )
    assert result.enrichment_applied is False
    assert result.enrichment_notes == "enrichment_failed:empty_s3_object"


@pytest.mark.asyncio
async def test_adapter_corrupt_download_error_is_soft_failure() -> None:
    adapter = _adapter(
        storage=_RaisingStorage(OSError("corrupt object")),
        ocr=_OkOcr(),
        parser=_OkParser(),
    )
    result = await adapter.enrich_snapshot_from_original(
        _snap(),
        missing_keys=("gross_salary", "net_salary"),
    )
    assert result.enrichment_applied is False
    assert "enrichment_failed:OSError" == result.enrichment_notes


@pytest.mark.asyncio
async def test_adapter_empty_ocr_is_soft_failure() -> None:
    adapter = _adapter(storage=_OkStorage(), ocr=_EmptyOcr(), parser=_OkParser())
    result = await adapter.enrich_snapshot_from_original(
        _snap(),
        missing_keys=("overtime_hours",),
    )
    assert result.enrichment_applied is False
    assert result.enrichment_notes == "enrichment_failed:empty_ocr"


@pytest.mark.asyncio
async def test_adapter_parser_error_is_soft_failure() -> None:
    adapter = _adapter(storage=_OkStorage(), ocr=_OkOcr(), parser=_RaisingParser())
    result = await adapter.enrich_snapshot_from_original(
        _snap({"gross_salary": {"value": "1"}}),
        missing_keys=("overtime_hours",),
    )
    assert result.enrichment_applied is False
    assert result.enrichment_notes == "enrichment_failed:RuntimeError"


class _FailingEnrichData:
    def __init__(self, *, snapshots: dict[str, PeriodSnapshot], fail_note: str) -> None:
        self.snapshots = snapshots
        self.fail_note = fail_note
        self.enrich_calls = 0

    async def list_available_payslip_periods(self, **kwargs) -> set[str]:  # noqa: ANN003
        return set(self.snapshots)

    async def load_period_snapshot(self, *, period: PeriodRef, **kwargs) -> PeriodSnapshot | None:
        return self.snapshots.get(period.key)

    async def enrich_snapshot_from_original(
        self,
        snapshot: PeriodSnapshot,
        *,
        missing_keys: tuple[str, ...],
    ) -> PeriodSnapshot:
        self.enrich_calls += 1
        return PeriodSnapshot(
            period=snapshot.period,
            document_id=snapshot.document_id,
            storage_key=snapshot.storage_key,
            structured_fields=dict(snapshot.structured_fields),
            finding_excerpts=list(snapshot.finding_excerpts),
            enrichment_applied=False,
            enrichment_notes=self.fail_note,
        )


@pytest.mark.asyncio
async def test_graph_enrichment_timeout_with_missing_essentials_clarifies() -> None:
    jul = PeriodRef(2026, 7)
    jun = PeriodRef(2026, 6)
    data = _FailingEnrichData(
        snapshots={
            "2026-07": PeriodSnapshot(
                period=jul,
                document_id=uuid4(),
                storage_key="a.pdf",
                structured_fields={"base_salary": {"value": "8000"}},
            ),
            "2026-06": PeriodSnapshot(
                period=jun,
                document_id=uuid4(),
                storage_key="b.pdf",
                structured_fields={"base_salary": {"value": "8000"}},
            ),
        },
        fail_note="enrichment_failed:OcrTimeoutError",
    )
    result = await PayrollInvestigationGraph(data).run(
        message="why did my overtime increase?",
        session_id="p2-1",
        locale="en",
        organization_id=uuid4(),
        employee_id=uuid4(),
        target_year=2026,
        target_month=7,
    )
    assert result.outcome == InvestigationOutcome.INSUFFICIENT_EVIDENCE
    assert data.enrich_calls >= 1
    assert "could not complete" in result.answer.lower() or "missing" in result.answer.lower()
    assert result.clarification_prompt


@pytest.mark.asyncio
async def test_graph_enrichment_failure_with_essentials_still_explains() -> None:
    """Soft path: essentials present → continue with partial answer, no exception."""
    jul = PeriodRef(2026, 7)
    jun = PeriodRef(2026, 6)
    data = _FailingEnrichData(
        snapshots={
            "2026-07": PeriodSnapshot(
                period=jul,
                document_id=uuid4(),
                storage_key="a.pdf",
                structured_fields={
                    "gross_salary": {"value": "12000"},
                    "net_salary": {"value": "9000"},
                },
            ),
            "2026-06": PeriodSnapshot(
                period=jun,
                document_id=uuid4(),
                storage_key="b.pdf",
                structured_fields={
                    "gross_salary": {"value": "11000"},
                    "net_salary": {"value": "8500"},
                    "overtime_hours": {"value": "2"},
                },
            ),
        },
        fail_note="enrichment_failed:OcrTimeoutError",
    )
    result = await PayrollInvestigationGraph(data).run(
        message="why did my overtime increase?",
        session_id="p2-2",
        locale="en",
        organization_id=uuid4(),
        employee_id=uuid4(),
        target_year=2026,
        target_month=7,
    )
    assert result.outcome == InvestigationOutcome.EXPLAINED
    assert data.enrich_calls >= 1
    assert "July 2026" in result.answer
