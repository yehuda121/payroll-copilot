from pathlib import Path
from uuid import uuid4

import fitz
import pytest

from payroll_copilot.application.services.batch_payslip_pipeline import (
    BatchSlipPipelineResult,
)
from payroll_copilot.application.services.batch_progress_store import (
    InMemoryBatchProgressStore,
)
from payroll_copilot.infrastructure.tasks.batch_processor import (
    BatchPayslipProcessor,
)

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "documents" / "payslips"


def _two_payslip_pdf() -> bytes:
    document = fitz.open()
    try:
        for number in (1, 2):
            page = document.new_page()
            page.insert_text((72, 72), f"Payslip employee {number}")
        return document.tobytes()
    finally:
        document.close()


def _scanned_package(page_count: int) -> bytes:
    document = fitz.open()
    try:
        for _ in range(page_count):
            document.new_page()
        return document.tobytes()
    finally:
        document.close()


class _Storage:
    async def download(self, _key: str) -> bytes:
        return _two_payslip_pdf()

    async def upload(self, *_args, **_kwargs) -> None:
        return None

    async def delete(self, _key: str) -> None:
        return None


class _Pipeline:
    def __init__(self) -> None:
        self.calls = 0

    async def process(self, *, progress, **_kwargs):
        self.calls += 1
        progress("ocr")
        progress("extracting")
        if self.calls == 1:
            raise RuntimeError("Unreadable first payslip")
        progress("matching")
        progress("validation")
        return BatchSlipPipelineResult(
            status="passed",
            document_id=uuid4(),
            processing_stage="completed",
            employee_number="EMP-2",
            employee_name="Employee Two",
            payroll_year=2026,
            payroll_month=6,
            validation_run_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_one_failed_payslip_does_not_stop_remaining_items() -> None:
    store = InMemoryBatchProgressStore()
    batch_id = "batch-1"
    store.create(
        batch_id,
        organization_id=str(uuid4()),
        created_by_user_id=str(uuid4()),
        document_id=str(uuid4()),
        source_filename="payroll.pdf",
    )
    pipeline = _Pipeline()
    processor = BatchPayslipProcessor(
        progress=store,
        storage=_Storage(),
        pipeline=pipeline,
    )

    result = await processor._process_async(batch_id, str(uuid4()))

    job = store.get(batch_id)
    assert job is not None
    assert result["status"] == "completed"
    assert pipeline.calls == 2
    assert job.status == "completed"
    assert job.processed_slips == 2
    assert [item.status for item in job.items] == ["failed", "passed"]
    assert job.items[0].error_message == "Unreadable first payslip"
    assert job.items[1].employee_number == "EMP-2"
    assert job.report_summary["failed"] == 1
    assert job.report_summary["passed"] == 1


def test_scanned_package_creates_one_independent_payslip_per_page() -> None:
    processor = BatchPayslipProcessor(
        progress=InMemoryBatchProgressStore(),
        storage=_Storage(),
        pipeline=_Pipeline(),
    )

    splits = processor._split_pdf(_scanned_package(4))

    assert len(splits) == 4
    assert all(len(fitz.open(stream=payload, filetype="pdf")) == 1 for payload in splits)


@pytest.mark.parametrize(
    ("relative_path", "expected_pages"),
    [
        ("valid/payslips_valid_2026_06_multi.pdf", 7),
        ("invalid/payslips_invalid_2026_07_multi.pdf", 7),
    ],
)
def test_real_multi_employee_fixture_splits_one_payslip_per_page(
    relative_path: str,
    expected_pages: int,
) -> None:
    processor = BatchPayslipProcessor(
        progress=InMemoryBatchProgressStore(),
        storage=_Storage(),
        pipeline=_Pipeline(),
    )
    pdf_bytes = (_FIXTURES / relative_path).read_bytes()

    splits = processor._split_pdf(pdf_bytes)

    assert len(splits) == expected_pages
    page_counts = [len(fitz.open(stream=payload, filetype="pdf")) for payload in splits]
    assert page_counts == [1] * expected_pages
