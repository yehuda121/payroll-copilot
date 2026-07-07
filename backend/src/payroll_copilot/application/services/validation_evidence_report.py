"""Build validation scope and evidence-based confidence for guest reports."""

from __future__ import annotations

from decimal import Decimal

from payroll_copilot.application.dto.validation_report_enrichment import (
    UploadedDocumentSummary,
    ValidationReportEnrichment,
    ValidationScopeItem,
)
from payroll_copilot.domain.entities import Document
from payroll_copilot.domain.enums import DocumentType
from payroll_copilot.domain.value_objects import ValidationReport
from payroll_copilot.infrastructure.config.settings import Settings


class ValidationEvidenceReportBuilder:
    """Computes honest validation scope and confidence from persisted documents."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def build(
        self,
        *,
        payslip_document: Document,
        supporting_documents: list[Document],
        report: ValidationReport,
    ) -> ValidationReportEnrichment:
        documents_by_type: dict[DocumentType, Document] = {payslip_document.document_type: payslip_document}
        for document in supporting_documents:
            documents_by_type[document.document_type] = document

        uploaded_summaries = self._build_uploaded_summaries(
            payslip_document=payslip_document,
            documents_by_type=documents_by_type,
        )
        scope = self._build_scope(documents_by_type=documents_by_type)
        confidence, explanation = self._compute_confidence(scope=scope)

        checks_passed = max(report.rules_evaluated - report.rules_failed, 0)

        return ValidationReportEnrichment(
            validation_scope=scope,
            uploaded_documents=uploaded_summaries,
            validation_confidence=confidence,
            confidence_explanation=explanation,
            checks_passed_count=checks_passed,
            extraction_connected=False,
        )

    def _build_uploaded_summaries(
        self,
        *,
        payslip_document: Document,
        documents_by_type: dict[DocumentType, Document],
    ) -> tuple[UploadedDocumentSummary, ...]:
        slots = (
            (DocumentType.PAYSLIP, "payslip"),
            (DocumentType.ATTENDANCE, "attendance"),
            (DocumentType.CONTRACT, "contract"),
            (DocumentType.NATIONAL_ID, "national_id"),
        )
        summaries: list[UploadedDocumentSummary] = []
        for doc_type, key in slots:
            document = documents_by_type.get(doc_type)
            if document is not None:
                summaries.append(
                    UploadedDocumentSummary(
                        document_type=key,
                        document_id=str(document.id),
                        uploaded=True,
                        original_filename=document.original_filename,
                    )
                )
            else:
                summaries.append(
                    UploadedDocumentSummary(
                        document_type=key,
                        document_id="",
                        uploaded=False,
                    )
                )
        return tuple(summaries)

    def _build_scope(
        self,
        *,
        documents_by_type: dict[DocumentType, Document],
    ) -> tuple[ValidationScopeItem, ...]:
        extraction_note = (
            "Document extraction is not yet connected. Rules ran on the validation engine context only."
        )

        payroll_status = "partial"
        payroll_reason = extraction_note

        attendance_doc = documents_by_type.get(DocumentType.ATTENDANCE)
        if attendance_doc is None:
            attendance = ValidationScopeItem(
                key="attendance",
                label="Attendance Validation",
                status="not_available",
                reason="Attendance report not uploaded.",
            )
        else:
            attendance = ValidationScopeItem(
                key="attendance",
                label="Attendance Validation",
                status="not_available",
                reason=(
                    "Attendance report uploaded, but attendance extraction and cross-check "
                    "are not yet connected."
                ),
            )

        contract_doc = documents_by_type.get(DocumentType.CONTRACT)
        if contract_doc is None:
            contract = ValidationScopeItem(
                key="employment_agreement",
                label="Employment Agreement Validation",
                status="not_available",
                reason="Employment agreement not uploaded.",
            )
        else:
            contract = ValidationScopeItem(
                key="employment_agreement",
                label="Employment Agreement Validation",
                status="not_available",
                reason=(
                    "Employment agreement uploaded, but contract analysis is not yet connected."
                ),
            )

        id_doc = documents_by_type.get(DocumentType.NATIONAL_ID)
        if id_doc is None:
            tax_benefits = ValidationScopeItem(
                key="tax_benefits",
                label="Tax Benefits",
                status="not_available",
                reason="Israeli ID was not uploaded.",
            )
        else:
            tax_benefits = ValidationScopeItem(
                key="tax_benefits",
                label="Tax Benefits",
                status="not_available",
                reason="Israeli ID uploaded, but identity-dependent tax checks are not yet connected.",
            )

        return (
            ValidationScopeItem(
                key="payroll_rules",
                label="Payroll Rules",
                status=payroll_status,
                reason=payroll_reason,
            ),
            attendance,
            contract,
            tax_benefits,
            ValidationScopeItem(
                key="historical_comparison",
                label="Historical Comparison",
                status="not_available",
                reason="Historical payroll data is not available.",
            ),
        )

    def _compute_confidence(
        self,
        *,
        scope: tuple[ValidationScopeItem, ...],
    ) -> tuple[Decimal, str]:
        confidence = Decimal("1.0")
        reasons: list[str] = []

        penalties = {
            "attendance": Decimal(str(self._settings.guest_validation_confidence_penalty_attendance)),
            "employment_agreement": Decimal(
                str(self._settings.guest_validation_confidence_penalty_contract)
            ),
            "tax_benefits": Decimal(str(self._settings.guest_validation_confidence_penalty_national_id)),
            "historical_comparison": Decimal(
                str(self._settings.guest_validation_confidence_penalty_historical)
            ),
        }

        for item in scope:
            if item.key == "payroll_rules" and item.status == "partial":
                penalty = Decimal(str(self._settings.guest_validation_confidence_penalty_extraction))
                confidence -= penalty
                if item.reason:
                    reasons.append(item.reason)
            elif item.status == "not_available" and item.key in penalties:
                confidence -= penalties[item.key]
                if item.reason:
                    reasons.append(item.reason)

        minimum = Decimal(str(self._settings.guest_validation_confidence_minimum))
        if confidence < minimum:
            confidence = minimum

        confidence = confidence.quantize(Decimal("0.01"))

        if not reasons:
            explanation = "All required evidence for the currently supported validation scope is available."
        else:
            explanation = " ".join(reasons)

        return confidence, explanation
