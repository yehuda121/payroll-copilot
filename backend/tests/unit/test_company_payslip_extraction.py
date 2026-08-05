"""Company-aware payslip extraction: registry, adapter, multi-slip, validation mapping."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import fitz
import pytest

from payroll_copilot.application.services.company_payslip_extraction import (
    DEFAULT_COMPANY_KEY,
    list_companies,
)
from payroll_copilot.application.services.company_payslip_extraction.adapter import (
    COMPANY_PAYSLIP_EXTRACTOR_VERSION,
    extract_payslip_document,
    paystub_entries_to_normalized_fields,
)
from payroll_copilot.application.services.company_payslip_extraction.registry import extract
from payroll_copilot.application.services.deterministic_pdf import (
    DeterministicExtractionErrorCode,
    DeterministicExtractionStatus,
    extract_document_from_pdf,
)
from payroll_copilot.application.services.dynamic_document import resolve_canonical_key

from payroll_copilot.application.use_cases.extract_guest_payslip import (
    ExtractGuestPayslipUseCase,
    GuestPayslipExtractionCommand,
)
from payroll_copilot.domain.entities import Document, DocumentExtraction
from payroll_copilot.domain.enums import DocumentType
from payroll_copilot.infrastructure.ai.deterministic_payslip_parser import DeterministicPayslipParser

FIXTURE_MULTI = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "company_payslip"
    / "payslips"
    / "primary_company"
    / "payslips_valid_2026_06_multi.pdf"
)


class _FakeStorage:
    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        return key

    async def delete(self, key: str) -> None:
        return None

    async def list_keys(self, prefix: str) -> list[str]:
        return []

    async def delete_prefix(self, prefix: str) -> int:
        return 0


class _FakeBootstrap:
    async def ensure_demo_organization(self, organization_id) -> None:  # noqa: ANN001
        return None


class _FakeDocs:
    def __init__(self) -> None:
        self.saved: list[Document] = []

    async def get_by_id(self, document_id):  # noqa: ANN001
        return next((d for d in self.saved if d.id == document_id), None)

    async def save(self, document: Document) -> Document:
        self.saved = [d for d in self.saved if d.id != document.id]
        self.saved.append(document)
        return document


class _FakeExtractions:
    def __init__(self) -> None:
        self.saved: list[DocumentExtraction] = []

    async def get_by_id(self, extraction_id):  # noqa: ANN001
        return next((e for e in self.saved if e.id == extraction_id), None)

    async def get_latest_for_document(self, document_id):  # noqa: ANN001
        matches = [e for e in self.saved if e.document_id == document_id]
        return matches[-1] if matches else None

    async def save(self, extraction: DocumentExtraction) -> DocumentExtraction:
        self.saved.append(extraction)
        return extraction


def test_registry_lists_primary_company_only() -> None:
    assert DEFAULT_COMPANY_KEY in list_companies()
    assert list_companies() == ["primary_company"]


def test_primary_company_multi_payslip_fixture() -> None:
    payload = extract(FIXTURE_MULTI.read_bytes(), company_key=DEFAULT_COMPANY_KEY)
    stubs = payload.get("paystubs") or []
    assert len(stubs) == 7
    assert payload.get("extraction_mode") in {"layout", "lines"}
    assert any((s.get("entries") or []) for s in stubs)


def test_canonical_field_mapping_from_hebrew_labels() -> None:
    assert resolve_canonical_key("שם עובד") == "employee_name"
    assert resolve_canonical_key("שכר נטו") == "net_salary"
    assert resolve_canonical_key("מספר עובד") == "employee_number"
    assert resolve_canonical_key("שעות עבודה") == "regular_hours"
    assert resolve_canonical_key("ניכויי חובה וגמל") == "total_deductions"
    assert resolve_canonical_key("מס בריאות") == "health_tax"

    payload = extract(FIXTURE_MULTI.read_bytes(), company_key=DEFAULT_COMPANY_KEY)
    fields = paystub_entries_to_normalized_fields(payload["paystubs"], paystub_index=0)
    keys = {f.key for f in fields}
    assert "employee_name" in keys
    assert "gross_salary" in keys
    assert "net_salary" in keys
    assert "regular_hours" in keys
    assert "total_deductions" in keys
    assert "health_tax" in keys


def _stub_entry_map(stub: dict) -> dict[str, object]:
    return {
        str(e.get("name")): e.get("value")
        for e in (stub.get("entries") or [])
        if isinstance(e, dict) and e.get("name")
    }


def test_multi_payslip_canonical_fields_from_stub0_only() -> None:
    """Regression: never fill missing stub-0 fields from another employee."""
    result = extract_payslip_document(
        FIXTURE_MULTI.read_bytes(), document_type=DocumentType.PAYSLIP
    )
    assert result.status is DeterministicExtractionStatus.COMPLETED
    assert result.extractor_version == COMPANY_PAYSLIP_EXTRACTOR_VERSION

    paystubs = (result.structured or {}).get("paystubs") or []
    assert len(paystubs) == 7

    dynamic = (result.structured or {}).get("dynamic_entries") or []
    sections = {e.get("section") for e in dynamic if isinstance(e, dict)}
    assert "paystub_1" in sections
    assert "paystub_7" in sections or any(
        str(s).startswith("paystub_") for s in sections if s
    )

    fm = result.field_map()
    assert fm.get("employee_name") == "אורית סבירסקי"
    assert fm.get("national_id") == "30491361-9"
    assert fm.get("pay_period") == "2026-06"
    assert fm.get("gross_salary") == "8,872.30"
    assert fm.get("net_salary") == "7,921.30"
    assert fm.get("national_insurance") == "162.00"
    assert fm.get("health_tax") == "309.00"
    assert "182" in str(fm.get("regular_hours") or "")
    assert fm.get("total_deductions") == "951.00"

    # Stub 5 has income_tax 47,125.35; stub 0 has no amount — must stay missing.
    assert "income_tax" not in fm or fm.get("income_tax") in (None, "")
    assert fm.get("income_tax") != "47,125.35"

    raw = extract(FIXTURE_MULTI.read_bytes(), company_key=DEFAULT_COMPANY_KEY)
    stub0 = _stub_entry_map(raw["paystubs"][0])
    stub5 = _stub_entry_map(raw["paystubs"][4])
    assert stub5.get("מס הכנסה") == "47,125.35"
    assert stub0.get("מס הכנסה") in (None, "")
    assert stub0.get("שם עובד") == fm.get("employee_name")
    assert stub0.get("ת\"ז") == fm.get("national_id")
    assert stub0.get('סה"כ תשלומים') == fm.get("gross_salary")
    assert stub0.get("ביטוח לאומי") == fm.get("national_insurance")
    assert stub0.get("מס בריאות") == fm.get("health_tax")
    assert stub0.get("ניכויי חובה וגמל") == fm.get("total_deductions")

    warnings = [str(w) for w in result.warnings]
    assert any(w.startswith("multi_payslip_count:7") for w in warnings)
    assert any("other_paystubs_not_merged" in w for w in warnings)
    assert (result.structured or {}).get("extractor_meta", {}).get(
        "canonical_paystub_index"
    ) == 0


def test_missing_fields_stay_missing_across_stubs() -> None:
    payload = extract(FIXTURE_MULTI.read_bytes(), company_key=DEFAULT_COMPANY_KEY)
    stubs = payload["paystubs"]
    assert len(stubs) == 7

    fields0 = {f.key: f.value for f in paystub_entries_to_normalized_fields(stubs, paystub_index=0)}
    fields4 = {f.key: f.value for f in paystub_entries_to_normalized_fields(stubs, paystub_index=4)}

    assert "income_tax" not in fields0
    assert fields4.get("income_tax") == "47,125.35"
    # Selecting stub 0 must not pull stub 4 tax even when both are available.
    merged_wrong = paystub_entries_to_normalized_fields(stubs, paystub_index=0)
    assert all(f.key != "income_tax" for f in merged_wrong)


def test_invalid_empty_encrypted_pdfs() -> None:
    empty = extract_document_from_pdf(b"", document_type=DocumentType.PAYSLIP)
    assert empty.error_code == DeterministicExtractionErrorCode.EMPTY_PDF.value

    blank = fitz.open()
    blank.new_page()
    blank_bytes = blank.tobytes()
    blank.close()
    ocr_needed = extract_document_from_pdf(
        blank_bytes, document_type=DocumentType.PAYSLIP, filename="blank.pdf", mime_type="application/pdf"
    )
    assert ocr_needed.status is DeterministicExtractionStatus.OCR_REQUIRED

    locked = fitz.open()
    page = locked.new_page()
    page.insert_text((72, 72), "תלוש משכורת")
    encrypted = locked.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="y"
    )
    locked.close()
    rejected = extract_document_from_pdf(
        encrypted, document_type=DocumentType.PAYSLIP, filename="x.pdf", mime_type="application/pdf"
    )
    assert rejected.status is DeterministicExtractionStatus.REJECTED
    assert rejected.error_code == DeterministicExtractionErrorCode.ENCRYPTED_PDF.value


def test_adapter_marks_multi_payslip_warning() -> None:
    result = extract_payslip_document(
        FIXTURE_MULTI.read_bytes(), document_type=DocumentType.PAYSLIP
    )
    assert result.status is DeterministicExtractionStatus.COMPLETED
    assert any(str(w).startswith("multi_payslip_count:") for w in result.warnings)
    assert any("other_paystubs_not_merged" in str(w) for w in result.warnings)
    assert (result.structured or {}).get("extractor_meta", {}).get("paystub_count", 0) >= 2


@pytest.mark.asyncio
async def test_guest_extraction_uses_company_extractor() -> None:
    from payroll_copilot.application.services.guest_ephemeral_store import (
        reset_guest_ephemeral_store_for_tests,
    )

    reset_guest_ephemeral_store_for_tests()
    use_case = ExtractGuestPayslipUseCase(
        document_repository=_FakeDocs(),
        extraction_repository=_FakeExtractions(),
        object_storage=_FakeStorage(),
        organization_bootstrap=_FakeBootstrap(),
    )
    result = await use_case.execute(
        GuestPayslipExtractionCommand(
            content=FIXTURE_MULTI.read_bytes(),
            original_filename="multi.pdf",
            mime_type="application/pdf",
            ephemeral=True,
        )
    )
    assert result.parser_status == "completed"
    assert result.parser_model == COMPANY_PAYSLIP_EXTRACTOR_VERSION
    assert result.entries
    assert any(e.key for e in result.entries)


@pytest.mark.asyncio
async def test_employee_extraction_projects_canonical_for_validation() -> None:
    docs = _FakeDocs()
    extractions = _FakeExtractions()
    use_case = ExtractGuestPayslipUseCase(
        document_repository=docs,
        extraction_repository=extractions,
        object_storage=_FakeStorage(),
        organization_bootstrap=_FakeBootstrap(),
    )
    emp_id = uuid4()
    org_id = uuid4()
    result = await use_case.execute(
        GuestPayslipExtractionCommand(
            content=FIXTURE_MULTI.read_bytes(),
            original_filename="employee.pdf",
            mime_type="application/pdf",
            ephemeral=False,
            employee_id=emp_id,
            organization_id=org_id,
            uploaded_by=uuid4(),
        )
    )
    assert result.parser_status == "completed"
    assert extractions.saved
    structured = extractions.saved[-1].structured_data or {}
    # Durable path projects canonical keys for validation.
    assert "employee_name" in structured or "gross_salary" in structured
    assert "dynamic_entries" in structured
    assert result.fields


@pytest.mark.asyncio
async def test_batch_style_reuse_document_extraction() -> None:
    """Batch invokes the same use case with ephemeral=False / reuse_document_id."""
    docs = _FakeDocs()
    extractions = _FakeExtractions()
    use_case = ExtractGuestPayslipUseCase(
        document_repository=docs,
        extraction_repository=extractions,
        object_storage=_FakeStorage(),
        organization_bootstrap=_FakeBootstrap(),
    )
    first = await use_case.execute(
        GuestPayslipExtractionCommand(
            content=FIXTURE_MULTI.read_bytes(),
            original_filename="batch-slip.pdf",
            mime_type="application/pdf",
            ephemeral=False,
            employee_id=uuid4(),
            organization_id=uuid4(),
            uploaded_by=uuid4(),
        )
    )
    second = await use_case.execute(
        GuestPayslipExtractionCommand(
            content=FIXTURE_MULTI.read_bytes(),
            original_filename="batch-slip.pdf",
            mime_type="application/pdf",
            ephemeral=False,
            employee_id=uuid4(),
            organization_id=uuid4(),
            uploaded_by=uuid4(),
            reuse_document_id=first.document_id,
        )
    )
    assert first.parser_status == "completed"
    assert second.parser_status == "completed"
    assert second.document_id == first.document_id
    assert len(extractions.saved) >= 2


@pytest.mark.asyncio
async def test_deterministic_payslip_parser_line_path() -> None:
    parser = DeterministicPayslipParser()
    # Line path: markers + Hebrew labels (no PDF geometry).
    text = (
        "תלוש משכורת\n"
        "שם עובד: בדיקה כהן\n"
        "מספר עובד: 42\n"
        "שכר נטו: 1,000.00\n"
        'הופק ע"י מערכת\n'
    )
    result = await parser.parse(ocr_text=text, language="he")
    assert result.model == COMPANY_PAYSLIP_EXTRACTOR_VERSION
    assert result.fields.employee_name is not None or result.fields.net_salary is not None


def test_non_payslip_types_unchanged() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Full Name: Dana Levi\nNational ID: 123456782")
    pdf = doc.tobytes()
    doc.close()
    result = extract_document_from_pdf(pdf, document_type=DocumentType.NATIONAL_ID)
    assert result.status is DeterministicExtractionStatus.COMPLETED
    assert result.field_map().get("national_id") == "123456782"
