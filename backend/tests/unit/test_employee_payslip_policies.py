"""Employee payslip policy tests: duplicate period, ownership, confirmation gate."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from payroll_copilot.application.exceptions import (
    ConfirmationBlockedError,
    DocumentNotOwnedError,
    DuplicatePayslipPeriodError,
)
from payroll_copilot.application.services.payslip_identity_comparison import (
    PayslipIdentityComparisonService,
)
from payroll_copilot.application.use_cases.correct_employee_extraction import (
    CorrectEmployeeExtractionUseCase,
)
from payroll_copilot.application.use_cases.correct_guest_extraction import (
    CorrectExtractionResult,
    FieldCorrection,
)
from payroll_copilot.application.use_cases.extract_employee_payslip import (
    EmployeePayslipExtractionCommand,
    ExtractEmployeePayslipUseCase,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import (
    ExtractedFieldView,
    GuestPayslipExtractionResult,
)
from payroll_copilot.application.use_cases.validate_employee_payslip import (
    ValidateEmployeePayslipUseCase,
)
from payroll_copilot.domain.entities import Document, DocumentExtraction, Employee
from payroll_copilot.domain.enums import (
    DocumentStatus,
    DocumentType,
    EmployeeStatus,
    EmploymentType,
    SalaryType,
)
from payroll_copilot.domain.value_objects import PayPeriod


ORG_ID = UUID("00000000-0000-4000-8000-000000000001")
EMP_A = uuid4()
EMP_B = uuid4()
USER_A = uuid4()


def _employee(employee_id: UUID, number: str = "5") -> Employee:
    return Employee(
        id=employee_id,
        organization_id=ORG_ID,
        employee_number=number,
        first_name="Yehuda",
        last_name="Shmulovitz",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2020, 1, 1),
        status=EmployeeStatus.ACTIVE,
        monthly_salary=Decimal("12000"),
        metadata={
            "national_id_masked": "****6783",
            "verified_display_name": "Yehuda Shmulovitz",
        },
    )


def _doc(
    *,
    employee_id: UUID,
    year: int = 2026,
    month: int = 6,
    document_id: UUID | None = None,
) -> Document:
    return Document(
        id=document_id or uuid4(),
        organization_id=ORG_ID,
        document_type=DocumentType.PAYSLIP,
        storage_key="test/key.pdf",
        original_filename="payslip.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        checksum_sha256="abc",
        status=DocumentStatus.UPLOADED,
        employee_id=employee_id,
        period=PayPeriod(year=year, month=month),
        metadata={
            "selected_period_year": year,
            "selected_period_month": month,
        },
        created_at=datetime.utcnow(),
    )


def _match_fields() -> list[ExtractedFieldView]:
    return [
        ExtractedFieldView(
            key="employee_id",
            value="313366783",
            confidence=0.95,
            source_text=None,
            status="FOUND",
        ),
        ExtractedFieldView(
            key="employee_name",
            value="Yehuda Shmulovitz",
            confidence=0.95,
            source_text=None,
            status="FOUND",
        ),
        ExtractedFieldView(
            key="pay_period",
            value="06/2026",
            confidence=0.95,
            source_text=None,
            status="FOUND",
        ),
    ]


class _FakeDocs:
    def __init__(self, docs: list[Document] | None = None) -> None:
        self.docs = list(docs or [])

    async def get_by_id(self, document_id: UUID) -> Document | None:
        return next((d for d in self.docs if d.id == document_id), None)

    async def save(self, document: Document) -> Document:
        self.docs = [d for d in self.docs if d.id != document.id]
        self.docs.append(document)
        return document

    async def find_payslip_for_period(
        self,
        *,
        organization_id: UUID,
        employee_id: UUID,
        period_year: int,
        period_month: int,
    ) -> Document | None:
        matches = [
            d
            for d in self.docs
            if d.organization_id == organization_id
            and d.employee_id == employee_id
            and d.document_type == DocumentType.PAYSLIP
            and d.period is not None
            and d.period.year == period_year
            and d.period.month == period_month
        ]
        return matches[-1] if matches else None


class _FakeExtractions:
    def __init__(self, items: list[DocumentExtraction] | None = None) -> None:
        self.items = list(items or [])

    async def get_latest_for_document(self, document_id: UUID) -> DocumentExtraction | None:
        matches = [e for e in self.items if e.document_id == document_id]
        return matches[-1] if matches else None


class _FakeGuestExtract:
    async def execute(self, command) -> GuestPayslipExtractionResult:  # noqa: ANN001
        doc_id = uuid4()
        return GuestPayslipExtractionResult(
            document_id=doc_id,
            extraction_id=uuid4(),
            ocr_status="completed",
            parser_status="completed",
            language=command.language,
            ocr_engine="fake",
            parser_model="fake",
            fields=_match_fields(),
            warnings=[],
            raw_text="fake",
            error_message=None,
        )


class _FakeGuestCorrect:
    async def execute(self, *, document_id: UUID, corrections: list[FieldCorrection]) -> CorrectExtractionResult:
        fields = [
            {
                "key": "employee_id",
                "value": "313366783",
                "status": "FOUND",
                "confidence": 0.99,
                "edited_by_user": True,
            },
            {
                "key": "employee_name",
                "value": "Yehuda Shmulovitz",
                "status": "FOUND",
                "confidence": 0.99,
                "edited_by_user": True,
            },
            {
                "key": "pay_period",
                "value": "06/2026",
                "status": "FOUND",
                "confidence": 0.99,
                "edited_by_user": True,
            },
        ]
        for item in corrections:
            for field in fields:
                if field["key"] == item.key:
                    field["value"] = None if item.clear else item.value
        return CorrectExtractionResult(
            document_id=document_id,
            extraction_id=uuid4(),
            extraction_version=2,
            ocr_status="completed",
            parser_status="completed",
            language="he",
            ocr_engine="fake",
            parser_model="fake",
            fields=fields,
            warnings=[],
            structured_data={f["key"]: f for f in fields},
        )


@pytest.mark.asyncio
async def test_duplicate_period_raises_without_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "payroll_copilot.application.use_cases.extract_employee_payslip.decrypt_national_id",
        lambda *a, **k: "313366783",
    )
    existing = _doc(employee_id=EMP_A)
    docs = _FakeDocs([existing])
    extractions = _FakeExtractions(
        [
            DocumentExtraction(
                id=uuid4(),
                document_id=existing.id,
                engine="fake",
                raw_text="x",
                structured_data={},
                extraction_version=1,
            )
        ]
    )
    use_case = ExtractEmployeePayslipUseCase(
        guest_extract=_FakeGuestExtract(),  # type: ignore[arg-type]
        documents=docs,  # type: ignore[arg-type]
        extractions=extractions,  # type: ignore[arg-type]
        employees=object(),  # type: ignore[arg-type]
    )
    with pytest.raises(DuplicatePayslipPeriodError) as exc:
        await use_case.execute(
            EmployeePayslipExtractionCommand(
                content=b"%PDF",
                original_filename="a.pdf",
                mime_type="application/pdf",
                language="he",
                period_year=2026,
                period_month=6,
                employee=_employee(EMP_A),
                user_id=USER_A,
                national_id_encrypted=b"enc",
                confirm_new_version=False,
            )
        )
    assert exc.value.code == "duplicate_payslip_period"
    assert exc.value.existing_document_id == existing.id


@pytest.mark.asyncio
async def test_confirm_new_version_preserves_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "payroll_copilot.application.use_cases.extract_employee_payslip.decrypt_national_id",
        lambda *a, **k: "313366783",
    )
    existing = _doc(employee_id=EMP_A)
    docs = _FakeDocs([existing])
    extractions = _FakeExtractions()
    guest = _FakeGuestExtract()

    async def _persist_side_effect(command):  # noqa: ANN001
        result = await _FakeGuestExtract.execute(guest, command)
        new_doc = _doc(employee_id=EMP_A, document_id=result.document_id)
        await docs.save(new_doc)
        return result

    guest.execute = _persist_side_effect  # type: ignore[method-assign]
    use_case = ExtractEmployeePayslipUseCase(
        guest_extract=guest,  # type: ignore[arg-type]
        documents=docs,  # type: ignore[arg-type]
        extractions=extractions,  # type: ignore[arg-type]
        employees=object(),  # type: ignore[arg-type]
    )
    result = await use_case.execute(
        EmployeePayslipExtractionCommand(
            content=b"%PDF",
            original_filename="a.pdf",
            mime_type="application/pdf",
            language="he",
            period_year=2026,
            period_month=6,
            employee=_employee(EMP_A),
            user_id=USER_A,
            national_id_encrypted=b"enc",
            confirm_new_version=True,
        )
    )
    assert result.extraction.document_id != existing.id
    assert await docs.get_by_id(existing.id) is not None
    assert len(docs.docs) == 2


@pytest.mark.asyncio
async def test_cross_employee_correction_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "payroll_copilot.application.use_cases.correct_employee_extraction.decrypt_national_id",
        lambda *a, **k: "313366783",
    )
    foreign = _doc(employee_id=EMP_B)
    docs = _FakeDocs([foreign])
    use_case = CorrectEmployeeExtractionUseCase(
        guest_correct=_FakeGuestCorrect(),  # type: ignore[arg-type]
        documents=docs,  # type: ignore[arg-type]
        extractions=_FakeExtractions(),  # type: ignore[arg-type]
    )
    with pytest.raises(DocumentNotOwnedError):
        await use_case.execute(
            document_id=foreign.id,
            corrections=[FieldCorrection(key="employee_name", value="Fixed")],
            employee=_employee(EMP_A),
            user_id=USER_A,
            national_id_encrypted=b"enc",
        )


@pytest.mark.asyncio
async def test_owned_correction_reruns_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "payroll_copilot.application.use_cases.correct_employee_extraction.decrypt_national_id",
        lambda *a, **k: "313366783",
    )
    owned = _doc(employee_id=EMP_A)
    docs = _FakeDocs([owned])
    use_case = CorrectEmployeeExtractionUseCase(
        guest_correct=_FakeGuestCorrect(),  # type: ignore[arg-type]
        documents=docs,  # type: ignore[arg-type]
        extractions=_FakeExtractions(),  # type: ignore[arg-type]
    )
    result = await use_case.execute(
        document_id=owned.id,
        corrections=[FieldCorrection(key="employee_name", value="Yehuda Shmulovitz")],
        employee=_employee(EMP_A),
        user_id=USER_A,
        national_id_encrypted=b"enc",
    )
    assert result.comparison.blocks_confirmation is False
    assert result.correction.extraction_version == 2


@pytest.mark.asyncio
async def test_validation_blocked_on_national_id_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "payroll_copilot.application.use_cases.validate_employee_payslip.decrypt_national_id",
        lambda *a, **k: "313366783",
    )
    owned = _doc(employee_id=EMP_A)
    docs = _FakeDocs([owned])
    extraction = DocumentExtraction(
        id=uuid4(),
        document_id=owned.id,
        engine="fake",
        raw_text="x",
        structured_data={
            "employee_id": {
                "value": "999999999",
                "status": "FOUND",
                "confidence": 0.95,
            },
            "pay_period": {"value": "06/2026", "status": "FOUND", "confidence": 0.95},
        },
        confirmation_status="confirmed",
    )

    class _ValidationNever:
        async def execute(self, command) -> Any:  # noqa: ANN001
            raise AssertionError("validation must not run when blocked")

    use_case = ValidateEmployeePayslipUseCase(
        documents=docs,  # type: ignore[arg-type]
        extractions=_FakeExtractions([extraction]),  # type: ignore[arg-type]
        validation=_ValidationNever(),  # type: ignore[arg-type]
        comparison=PayslipIdentityComparisonService(),
    )
    with pytest.raises(ConfirmationBlockedError) as exc:
        await use_case.execute(
            document_id=owned.id,
            employee=_employee(EMP_A),
            user_id=USER_A,
            national_id_encrypted=b"enc",
        )
    assert exc.value.code == "national_id_mismatch"


def test_plaintext_national_id_never_in_comparison_dict() -> None:
    result = PayslipIdentityComparisonService().compare(
        trusted_full_name="Yehuda Shmulovitz",
        trusted_employee_number="5",
        trusted_national_id_plaintext="313366783",
        trusted_national_id_masked="****6783",
        selected_year=2026,
        selected_month=6,
        extraction_fields=[
            {"key": "employee_id", "value": "313366783", "status": "FOUND", "confidence": 0.95},
            {"key": "pay_period", "value": "06/2026", "status": "FOUND", "confidence": 0.95},
        ],
    )
    blob = str(result.identity_check.to_dict())
    assert "313366783" not in blob
    assert "****6783" in blob
