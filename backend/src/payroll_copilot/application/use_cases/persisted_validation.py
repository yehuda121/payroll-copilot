"""Use cases for persisting and retrieving validation runs."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID

from payroll_copilot.application.dto.validation_run import ValidationRunRecord
from payroll_copilot.application.exceptions import DocumentNotFoundError
from payroll_copilot.application.mappers.validation_mapper import (
    report_to_finding_records,
    report_to_run_record,
)
from payroll_copilot.application.ports.employee_audit import EmployeeRepository
from payroll_copilot.application.ports.organization_bootstrap import OrganizationBootstrapPort
from payroll_copilot.application.ports.repositories import (
    DocumentRepository,
    ValidationFindingRepository,
    ValidationRunRepository,
)
from payroll_copilot.application.services.validation_evidence_report import (
    ValidationEvidenceReportBuilder,
)
from payroll_copilot.application.use_cases.validation import RunValidationCommand, RunValidationUseCase
from payroll_copilot.application.validation.guest_extraction_context_builder import (
    ExtractionRequiredError,
    GuestExtractionValidationContextBuilder,
)
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.security.field_crypto import decrypt_national_id


@dataclass(frozen=True, slots=True)
class RunPersistedValidationCommand:
    document_id: UUID
    employee_id: UUID | None = None
    include_historical: bool = True
    include_contract_rag: bool = True
    supporting_document_ids: tuple[UUID, ...] = field(default_factory=tuple)
    locale: str | None = None
    extraction_id: UUID | None = None
    # Optional in-process National ID for authorized comparison (Employee path).
    trusted_national_id: str | None = None
    # Selective rerun: full | employee_checks | law_checks | rules
    rerun_scope: str | None = None
    rule_ids: tuple[str, ...] = field(default_factory=tuple)
    merge_with_previous: bool = True


class RunPersistedValidationUseCase:
    """Run deterministic validation from guest extraction and persist results."""

    def __init__(
        self,
        run_validation: RunValidationUseCase,
        guest_context_builder: GuestExtractionValidationContextBuilder,
        document_repository: DocumentRepository,
        validation_run_repository: ValidationRunRepository,
        validation_finding_repository: ValidationFindingRepository,
        organization_bootstrap: OrganizationBootstrapPort,
        evidence_report_builder: ValidationEvidenceReportBuilder | None = None,
        employee_repository: EmployeeRepository | None = None,
        employment_terms_loader: Any | None = None,
    ) -> None:
        self._run_validation = run_validation
        self._guest_context_builder = guest_context_builder
        self._document_repository = document_repository
        self._validation_run_repository = validation_run_repository
        self._validation_finding_repository = validation_finding_repository
        self._organization_bootstrap = organization_bootstrap
        self._evidence_report_builder = evidence_report_builder or ValidationEvidenceReportBuilder(
            get_settings()
        )
        self._employees = employee_repository
        self._employment_terms_loader = employment_terms_loader

    async def execute(self, command: RunPersistedValidationCommand) -> ValidationRunRecord:
        from payroll_copilot.application.services.guest_ephemeral_store import get_guest_ephemeral_store
        from payroll_copilot.application.services.validation_rerun_scope import (
            disabled_rule_ids_for_scope,
            merge_findings_preserving_unscoped,
        )
        from payroll_copilot.domain.rules import get_registered_rules
        from payroll_copilot.domain.value_objects import ValidationReport

        ephemeral = get_guest_ephemeral_store().get(command.document_id)
        if ephemeral is not None:
            return await self._execute_guest_ephemeral(command, ephemeral)

        document = await self._document_repository.get_by_id(command.document_id)
        if document is None:
            raise DocumentNotFoundError(command.document_id)

        supporting_documents = await self._load_supporting_documents(command.supporting_document_ids)

        bundle = await self._guest_context_builder.build(
            document_id=command.document_id,
            organization_id=document.organization_id,
            employee_id=command.employee_id,
        )
        validation_command = await self._with_authorized_employee(
            bundle.command,
            employee_id=command.employee_id,
            organization_id=document.organization_id,
            trusted_national_id=command.trusted_national_id,
            document_metadata=dict(document.metadata or {}),
            document_period_year=document.period.year if document.period else None,
            document_period_month=document.period.month if document.period else None,
        )

        disabled = disabled_rule_ids_for_scope(
            scope=command.rerun_scope,
            rule_ids=frozenset(command.rule_ids) if command.rule_ids else None,
        )
        validation_command = replace(
            validation_command,
            disabled_rule_ids=disabled,
            rerun_scope=command.rerun_scope or "full",
        )

        report = self._run_validation.execute(validation_command)

        # Selective merge: preserve prior findings for rules not re-evaluated.
        if (
            command.merge_with_previous
            and command.rerun_scope
            and command.rerun_scope not in {"full", "all", ""}
        ):
            previous_runs = await self._validation_run_repository.list_for_document(document.id)
            if previous_runs:
                previous = previous_runs[0]
                if not previous.findings:
                    previous.findings = await self._validation_finding_repository.list_by_run_id(
                        previous.id
                    )
                evaluated = frozenset(get_registered_rules().keys()) - disabled
                # Convert finding records ↔ domain findings is lossy; merge at record level after map.
                # Domain report findings use RuleFinding; merge RuleFinding by rule_id then remap.
                from payroll_copilot.domain.value_objects import RuleFinding

                prior_domain: list[RuleFinding] = []
                for fr in previous.findings:
                    prior_domain.append(
                        RuleFinding(
                            rule_id=fr.rule_id,
                            category=fr.rule_category,
                            severity=fr.severity,
                            message_key=fr.message_key,
                            message_params=fr.message_params,
                            expected_value=fr.expected_value,
                            actual_value=fr.actual_value,
                            confidence=__import__(
                                "payroll_copilot.domain.value_objects", fromlist=["ConfidenceScore"]
                            ).ConfidenceScore(
                                value=float(fr.confidence),
                                source=__import__(
                                    "payroll_copilot.domain.enums", fromlist=["ConfidenceSource"]
                                ).ConfidenceSource.RULE,
                            ),
                            legal_reference=fr.legal_reference,
                        )
                    )
                merged = merge_findings_preserving_unscoped(
                    previous_findings=prior_domain,
                    new_findings=list(report.findings),
                    evaluated_rule_ids=evaluated,
                )
                # Merge additive rule outcomes the same way as findings.
                from payroll_copilot.domain.value_objects import RuleEvaluationOutcome
                from payroll_copilot.application.services.validation_rerun_scope import (
                    merge_rule_outcomes_preserving_unscoped,
                )

                prior_outcomes: list[RuleEvaluationOutcome] = []
                for raw in (previous.context_snapshot or {}).get("rule_outcomes") or []:
                    if not isinstance(raw, dict):
                        continue
                    rid = str(raw.get("rule_id") or "").strip()
                    if not rid:
                        continue
                    prior_outcomes.append(
                        RuleEvaluationOutcome(
                            rule_id=rid,
                            outcome=str(raw.get("outcome") or "skipped"),
                            skip_reason=raw.get("skip_reason"),
                        )
                    )

                merged_outcomes = merge_rule_outcomes_preserving_unscoped(
                    previous_outcomes=prior_outcomes,
                    new_outcomes=list(report.rule_outcomes),
                    evaluated_rule_ids=evaluated,
                )
                report = ValidationReport(
                    validation_run_id=report.validation_run_id,
                    overall_result=report.overall_result,
                    overall_confidence=report.overall_confidence,
                    findings=tuple(merged),
                    rules_evaluated=report.rules_evaluated,
                    rules_failed=sum(
                        1
                        for f in merged
                        if f.severity.value in {"warning", "critical"}
                    ),
                    rule_outcomes=tuple(merged_outcomes),
                )
                # Recompute overall from merged
                from payroll_copilot.application.validation.orchestrator import ValidationOrchestrator

                overall = ValidationOrchestrator._compute_result(list(merged))
                report = ValidationReport(
                    validation_run_id=report.validation_run_id,
                    overall_result=overall.value,
                    overall_confidence=report.overall_confidence,
                    findings=tuple(merged),
                    rules_evaluated=sum(
                        1 for item in merged_outcomes if item.outcome in {"passed", "failed"}
                    ),
                    rules_failed=sum(
                        1
                        for f in merged
                        if f.severity.value in {"warning", "critical"}
                    ),
                    rule_outcomes=tuple(merged_outcomes),
                )

        organization_id = document.organization_id or bundle.organization_id
        await self._organization_bootstrap.ensure_demo_organization(organization_id)

        enrichment = self._evidence_report_builder.build(
            payslip_document=document,
            supporting_documents=supporting_documents,
            report=report,
            locale=command.locale,
            extraction_connected=bundle.extraction_connected,
            core_fields_usable=bundle.core_fields_usable,
        )

        run_record = report_to_run_record(
            report=report,
            document_id=document.id,
            organization_id=organization_id,
            employee_id=command.employee_id,
        )
        run_record.enrichment = enrichment
        snapshot = enrichment.to_context_snapshot()
        snapshot["rerun_scope"] = command.rerun_scope or "full"
        if command.rule_ids:
            snapshot["rule_ids"] = list(command.rule_ids)
        if report.rule_outcomes:
            snapshot["rule_outcomes"] = [
                {
                    "rule_id": item.rule_id,
                    "outcome": item.outcome,
                    "skip_reason": item.skip_reason,
                }
                for item in report.rule_outcomes
            ]
        run_record.context_snapshot = snapshot
        run_record.extraction_id = command.extraction_id or bundle.extraction_id

        finding_records = report_to_finding_records(report, run_record.id)

        saved_run = await self._validation_run_repository.save(run_record)
        saved_findings = await self._validation_finding_repository.save_all(
            saved_run.id,
            finding_records,
        )
        saved_run.findings = saved_findings
        saved_run.enrichment = enrichment
        return saved_run

    async def _execute_guest_ephemeral(self, command: RunPersistedValidationCommand, ephemeral) -> ValidationRunRecord:
        """Run validation for guest landing without permanent S3/DB writes."""
        from payroll_copilot.application.services.guest_ephemeral_store import get_guest_ephemeral_store

        store = get_guest_ephemeral_store()
        document = store.build_document(ephemeral)
        supporting_documents = []
        support_ids = tuple(command.supporting_document_ids) or tuple(ephemeral.supporting_document_ids)
        for sid in support_ids:
            support = store.get_supporting(sid)
            if support is not None:
                supporting_documents.append(store.build_supporting_document(support))

        bundle = await self._guest_context_builder.build(
            document_id=command.document_id,
            organization_id=document.organization_id,
            employee_id=command.employee_id,
            require_confirmed=True,
        )
        # Guest has no authorized employee profile — EMPLOYEE rules must not apply.
        report = self._run_validation.execute(bundle.command)

        enrichment = self._evidence_report_builder.build(
            payslip_document=document,
            supporting_documents=supporting_documents,
            report=report,
            locale=command.locale,
            extraction_connected=bundle.extraction_connected,
            core_fields_usable=bundle.core_fields_usable,
        )

        run_record = report_to_run_record(
            report=report,
            document_id=document.id,
            organization_id=document.organization_id or bundle.organization_id,
            employee_id=command.employee_id,
        )
        # Guest runs are returned in-memory only — never persisted.
        run_record.enrichment = enrichment
        guest_snapshot = enrichment.to_context_snapshot()
        if report.rule_outcomes:
            guest_snapshot["rule_outcomes"] = [
                {
                    "rule_id": item.rule_id,
                    "outcome": item.outcome,
                    "skip_reason": item.skip_reason,
                }
                for item in report.rule_outcomes
            ]
        run_record.context_snapshot = guest_snapshot
        run_record.extraction_id = command.extraction_id or bundle.extraction_id
        finding_records = report_to_finding_records(report, run_record.id)
        run_record.findings = finding_records
        return run_record

    async def _with_authorized_employee(
        self,
        command: RunValidationCommand,
        *,
        employee_id: UUID | None,
        organization_id: UUID | None,
        trusted_national_id: str | None,
        document_metadata: dict,
        document_period_year: int | None,
        document_period_month: int | None,
    ) -> RunValidationCommand:
        """Replace synthetic Employee with authorized profile when available."""
        selected_year = document_metadata.get("selected_period_year") or document_period_year
        selected_month = document_metadata.get("selected_period_month") or document_period_month
        try:
            selected_year_i = int(selected_year) if selected_year else None
            selected_month_i = int(selected_month) if selected_month else None
        except (TypeError, ValueError):
            selected_year_i, selected_month_i = None, None

        if employee_id is None or self._employees is None:
            return replace(
                command,
                authorized_employee=False,
                trusted_national_id=None,
                selected_period_year=selected_year_i,
                selected_period_month=selected_month_i,
            )

        employee = await self._employees.get_by_id(employee_id)
        if employee is None:
            return replace(
                command,
                authorized_employee=False,
                trusted_national_id=None,
                selected_period_year=selected_year_i,
                selected_period_month=selected_month_i,
            )
        if organization_id is not None and employee.organization_id != organization_id:
            return replace(
                command,
                authorized_employee=False,
                trusted_national_id=None,
                selected_period_year=selected_year_i,
                selected_period_month=selected_month_i,
            )

        plaintext = trusted_national_id
        if plaintext is None:
            encrypted = await self._employees.get_national_id_encrypted(employee_id)
            plaintext = decrypt_national_id(
                encrypted,
                encryption_key=get_settings().encryption_key,
            )

        terms = None
        if self._employment_terms_loader is not None and organization_id is not None:
            terms = await self._employment_terms_loader.load_for_employee_period(
                organization_id=organization_id,
                employee_id=employee_id,
                period_year=selected_year_i,
                period_month=selected_month_i,
            )

        return replace(
            command,
            employee=employee,
            authorized_employee=True,
            trusted_national_id=plaintext,
            selected_period_year=selected_year_i,
            selected_period_month=selected_month_i,
            confirmed_employment_terms=terms,
        )

    async def _load_supporting_documents(self, document_ids: tuple[UUID, ...]):
        from payroll_copilot.application.services.guest_ephemeral_store import get_guest_ephemeral_store
        from payroll_copilot.domain.entities import Document

        store = get_guest_ephemeral_store()
        documents: list[Document] = []
        for document_id in document_ids:
            support = store.get_supporting(document_id)
            if support is not None:
                documents.append(store.build_supporting_document(support))
                continue
            document = await self._document_repository.get_by_id(document_id)
            if document is not None:
                documents.append(document)
        return documents


class GetValidationRunUseCase:
    """Load a persisted validation run and its findings."""

    def __init__(
        self,
        validation_run_repository: ValidationRunRepository,
        validation_finding_repository: ValidationFindingRepository,
    ) -> None:
        self._validation_run_repository = validation_run_repository
        self._validation_finding_repository = validation_finding_repository

    async def execute(self, validation_run_id: UUID) -> ValidationRunRecord | None:
        run = await self._validation_run_repository.get_by_id(validation_run_id)
        if run is None:
            return None

        run.findings = await self._validation_finding_repository.list_by_run_id(validation_run_id)
        return run


__all__ = [
    "ExtractionRequiredError",
    "GetValidationRunUseCase",
    "RunPersistedValidationCommand",
    "RunPersistedValidationUseCase",
]
