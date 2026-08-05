"""Tests for shared deterministic PDF extraction (no AI / no OCR)."""

from __future__ import annotations

import io
from pathlib import Path

import fitz
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from payroll_copilot.application.services.company_payslip_extraction.adapter import (
    COMPANY_PAYSLIP_EXTRACTOR_VERSION,
)
from payroll_copilot.application.services.deterministic_pdf import (
    DeterministicExtractionErrorCode,
    DeterministicExtractionStatus,
    extract_document_from_pdf,
)
from payroll_copilot.application.services.payslip_semantic_extractor import (
    PayslipSemanticExtractor,
)
from payroll_copilot.application.exceptions import PayslipParserUnavailableError
from payroll_copilot.domain.enums import DocumentType
from payroll_copilot.presentation.api.routes.extraction import router as extraction_router
from payroll_copilot.presentation.api.security import (
    BoundEmployeeContext,
    require_bound_employee,
)

FIXTURE_MULTI = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "company_payslip"
    / "payslips"
    / "primary_company"
    / "payslips_valid_2026_06_multi.pdf"
)


def _text_pdf(text: str, *, pages: int = 1) -> bytes:
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _blank_pdf(*, pages: int = 1) -> bytes:
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def _encrypted_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Secret payslip text with Gross Salary: 10000")
    data = doc.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw="secret",
        owner_pw="owner",
    )
    doc.close()
    return data


def test_deterministic_payslip_extracts_fields_from_primary_company_fixture() -> None:
    pdf = FIXTURE_MULTI.read_bytes()
    result = extract_document_from_pdf(
        pdf, document_type=DocumentType.PAYSLIP, filename="payslip.pdf", mime_type="application/pdf"
    )
    assert result.status is DeterministicExtractionStatus.COMPLETED
    assert result.extractor_version == COMPANY_PAYSLIP_EXTRACTOR_VERSION
    mapping = result.field_map()
    assert mapping.get("employee_name")
    assert mapping.get("national_id")
    assert mapping.get("gross_salary")
    assert mapping.get("net_salary")
    assert mapping.get("pay_period")
    entries = (result.structured or {}).get("dynamic_entries") or []
    assert len(entries) > 0
    assert any(str(e.get("key") or "") for e in entries)


def test_deterministic_extraction_is_idempotent() -> None:
    pdf = FIXTURE_MULTI.read_bytes()
    first = extract_document_from_pdf(pdf, document_type=DocumentType.PAYSLIP)
    second = extract_document_from_pdf(pdf, document_type=DocumentType.PAYSLIP)
    assert first.to_dict()["fields"] == second.to_dict()["fields"]
    assert first.raw_text == second.raw_text
    assert first.status == second.status


def test_reject_non_pdf() -> None:
    result = extract_document_from_pdf(
        b"not a pdf",
        document_type=DocumentType.PAYSLIP,
        filename="x.png",
        mime_type="image/png",
    )
    assert result.status is DeterministicExtractionStatus.REJECTED
    assert result.error_code == DeterministicExtractionErrorCode.NOT_PDF.value


def test_empty_pdf() -> None:
    result = extract_document_from_pdf(b"", document_type=DocumentType.PAYSLIP)
    assert result.status is DeterministicExtractionStatus.REJECTED
    assert result.error_code == DeterministicExtractionErrorCode.EMPTY_PDF.value


def test_malformed_pdf() -> None:
    result = extract_document_from_pdf(
        b"%PDF-1.4\nnot really a pdf",
        document_type=DocumentType.PAYSLIP,
        filename="bad.pdf",
        mime_type="application/pdf",
    )
    assert result.status in {
        DeterministicExtractionStatus.REJECTED,
        DeterministicExtractionStatus.FAILED,
        DeterministicExtractionStatus.OCR_REQUIRED,
    }
    assert result.error_code in {
        DeterministicExtractionErrorCode.MALFORMED_PDF.value,
        DeterministicExtractionErrorCode.OCR_REQUIRED.value,
        DeterministicExtractionErrorCode.EMPTY_PDF.value,
    }


def test_blank_pdf_requires_ocr() -> None:
    result = extract_document_from_pdf(
        _blank_pdf(),
        document_type=DocumentType.PAYSLIP,
        filename="scan.pdf",
        mime_type="application/pdf",
    )
    assert result.status is DeterministicExtractionStatus.OCR_REQUIRED
    assert result.error_code == DeterministicExtractionErrorCode.OCR_REQUIRED.value


def test_encrypted_pdf_rejected() -> None:
    result = extract_document_from_pdf(
        _encrypted_pdf(),
        document_type=DocumentType.PAYSLIP,
        filename="locked.pdf",
        mime_type="application/pdf",
    )
    assert result.status is DeterministicExtractionStatus.REJECTED
    assert result.error_code == DeterministicExtractionErrorCode.ENCRYPTED_PDF.value


def test_national_id_parser() -> None:
    text = "Full Name: Dana Levi\nNational ID: 123456782\nDate of Birth: 01/02/1990"
    pdf = _text_pdf(text)
    result = extract_document_from_pdf(pdf, document_type=DocumentType.NATIONAL_ID)
    assert result.status is DeterministicExtractionStatus.COMPLETED
    mapping = result.field_map()
    assert mapping.get("national_id") == "123456782"
    assert "Dana" in str(mapping.get("full_name") or "")


@pytest.mark.asyncio
async def test_ai_semantic_extractor_disabled() -> None:
    extractor = PayslipSemanticExtractor.__new__(PayslipSemanticExtractor)
    with pytest.raises(PayslipParserUnavailableError):
        await PayslipSemanticExtractor.extract(extractor, ocr_text="anything")


def test_authorized_deterministic_endpoint_requires_auth() -> None:
    app = FastAPI()
    app.include_router(extraction_router, prefix="/extraction")
    client = TestClient(app)
    pdf = FIXTURE_MULTI.read_bytes()
    response = client.post(
        "/extraction/deterministic/pdf",
        files={"file": ("payslip.pdf", io.BytesIO(pdf), "application/pdf")},
        data={"document_type": "payslip"},
    )
    assert response.status_code in {401, 403, 422}


def test_authorized_deterministic_endpoint_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from uuid import uuid4
    from types import SimpleNamespace

    app = FastAPI()
    app.include_router(extraction_router, prefix="/extraction")

    employee = SimpleNamespace(id=uuid4(), organization_id=uuid4())
    principal = SimpleNamespace(user_id=uuid4())

    def _fake_bound() -> BoundEmployeeContext:
        return BoundEmployeeContext(
            principal=principal,  # type: ignore[arg-type]
            employee=employee,  # type: ignore[arg-type]
            national_id_encrypted=None,
        )

    app.dependency_overrides[require_bound_employee] = _fake_bound
    from payroll_copilot.presentation.api import rate_limit_deps

    app.dependency_overrides[rate_limit_deps.limit_employee_upload] = lambda: None

    client = TestClient(app)
    pdf = FIXTURE_MULTI.read_bytes()
    response = client.post(
        "/extraction/deterministic/pdf",
        files={"file": ("payslip.pdf", io.BytesIO(pdf), "application/pdf")},
        data={"document_type": "payslip"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["extractor_version"] == COMPANY_PAYSLIP_EXTRACTOR_VERSION
    keys = {item["key"] for item in body["fields"]}
    assert "gross_salary" in keys
    assert body["organization_id"] == str(employee.organization_id)
