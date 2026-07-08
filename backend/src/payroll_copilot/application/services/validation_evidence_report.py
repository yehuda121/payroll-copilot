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
from payroll_copilot.infrastructure.i18n import normalize_locale, scope_label, scope_reason


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
        locale: str | None = None,
        extraction_connected: bool = False,
        core_fields_usable: bool = False,
    ) -> ValidationReportEnrichment:
        lang = normalize_locale(locale or self._settings.default_locale)
        documents_by_type: dict[DocumentType, Document] = {payslip_document.document_type: payslip_document}
        for document in supporting_documents:
            documents_by_type[document.document_type] = document

        uploaded_summaries = self._build_uploaded_summaries(
            payslip_document=payslip_document,
            documents_by_type=documents_by_type,
        )
        scope = self._build_scope(
            documents_by_type=documents_by_type,
            locale=lang,
            extraction_connected=extraction_connected,
            core_fields_usable=core_fields_usable,
        )
        confidence, explanation = self._compute_confidence(scope=scope, locale=lang)

        checks_passed = max(report.rules_evaluated - report.rules_failed, 0)

        return ValidationReportEnrichment(
            validation_scope=scope,
            uploaded_documents=uploaded_summaries,
            validation_confidence=confidence,
            confidence_explanation=explanation,
            checks_passed_count=checks_passed,
            extraction_connected=extraction_connected,
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
        locale: str,
        extraction_connected: bool = False,
        core_fields_usable: bool = False,
    ) -> tuple[ValidationScopeItem, ...]:
        if extraction_connected and core_fields_usable:
            payroll_status = "completed"
            payroll_reason = scope_reason("payroll_extraction_connected", locale)
        elif extraction_connected:
            payroll_status = "partial"
            payroll_reason = scope_reason("payroll_core_fields_incomplete", locale)
        else:
            payroll_status = "partial"
            payroll_reason = scope_reason("extraction_not_connected", locale)

        attendance_doc = documents_by_type.get(DocumentType.ATTENDANCE)
        if attendance_doc is None:
            attendance = ValidationScopeItem(
                key="attendance",
                label=scope_label("attendance", locale),
                status="not_available",
                reason=scope_reason("attendance_not_uploaded", locale),
            )
        else:
            attendance = ValidationScopeItem(
                key="attendance",
                label=scope_label("attendance", locale),
                status="not_available",
                reason=scope_reason("attendance_uploaded_not_connected", locale),
            )

        contract_doc = documents_by_type.get(DocumentType.CONTRACT)
        if contract_doc is None:
            contract = ValidationScopeItem(
                key="employment_agreement",
                label=scope_label("employment_agreement", locale),
                status="not_available",
                reason=scope_reason("contract_not_uploaded", locale),
            )
        else:
            contract = ValidationScopeItem(
                key="employment_agreement",
                label=scope_label("employment_agreement", locale),
                status="not_available",
                reason=scope_reason("contract_uploaded_not_connected", locale),
            )

        id_doc = documents_by_type.get(DocumentType.NATIONAL_ID)
        if id_doc is None:
            tax_benefits = ValidationScopeItem(
                key="tax_benefits",
                label=scope_label("tax_benefits", locale),
                status="not_available",
                reason=scope_reason("id_not_uploaded", locale),
            )
        else:
            tax_benefits = ValidationScopeItem(
                key="tax_benefits",
                label=scope_label("tax_benefits", locale),
                status="not_available",
                reason=scope_reason("id_uploaded_not_connected", locale),
            )

        return (
            ValidationScopeItem(
                key="payroll_rules",
                label=scope_label("payroll_rules", locale),
                status=payroll_status,
                reason=payroll_reason,
            ),
            attendance,
            contract,
            tax_benefits,
            ValidationScopeItem(
                key="historical_comparison",
                label=scope_label("historical_comparison", locale),
                status="not_available",
                reason=scope_reason("historical_not_available", locale),
            ),
        )

    def _compute_confidence(
        self,
        *,
        scope: tuple[ValidationScopeItem, ...],
        locale: str,
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
            explanation = scope_reason("all_evidence_available", locale)
        else:
            explanation = " ".join(reasons)

        return confidence, explanation
