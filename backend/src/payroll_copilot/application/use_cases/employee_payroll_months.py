"""Build authenticated employee payroll-month history (year overview)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from payroll_copilot.application.dto.validation_run import ValidationRunRecord
from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
    ValidationFindingRepository,
    ValidationRunRepository,
)
from payroll_copilot.application.services.employee_document_lifecycle import (
    LIFECYCLE_CONFIRMED,
    LIFECYCLE_REVIEW_REQUIRED,
    fields_from_structured,
    is_employee_visible_document,
)
from payroll_copilot.application.services.employee_payroll_month_status import (
    compute_presentation_status,
    document_summary,
    highest_severity,
)
from payroll_copilot.application.services.extraction_explainability import (
    attach_field_evidence,
    build_field_evidence_map,
    build_validation_explanation,
    build_validation_run_explanation,
)
from payroll_copilot.domain.enums import DocumentType
from payroll_copilot.infrastructure.config.settings import get_settings


class BuildEmployeePayrollMonthsUseCase:
    def __init__(
        self,
        *,
        documents: DocumentRepository,
        validation_runs: ValidationRunRepository,
        validation_findings: ValidationFindingRepository | None = None,
        extractions: DocumentExtractionRepository | None = None,
    ) -> None:
        self._documents = documents
        self._runs = validation_runs
        self._findings = validation_findings
        self._extractions = extractions

    async def execute(
        self,
        *,
        organization_id: UUID,
        employee_id: UUID,
        year: int,
        current_year: int | None = None,
        include_unpublished: bool = False,
    ) -> dict[str, Any]:
        now_year = current_year or datetime.utcnow().year
        docs = await self._documents.list_for_employee(
            organization_id=organization_id,
            employee_id=employee_id,
        )
        if not include_unpublished:
            docs = [doc for doc in docs if is_employee_visible_document(doc)]

        years_from_docs = {d.period.year for d in docs if d.period is not None}
        available_years = sorted(years_from_docs | {now_year}, reverse=True)

        payslips_by_month: dict[int, Any] = {}
        attendance_by_month: dict[int, Any] = {}
        for doc in docs:
            if doc.period is None or doc.period.year != year:
                continue
            month = doc.period.month
            if doc.document_type == DocumentType.PAYSLIP:
                existing = payslips_by_month.get(month)
                if existing is None or (
                    doc.created_at
                    and existing.created_at
                    and doc.created_at > existing.created_at
                ):
                    payslips_by_month[month] = doc
            elif doc.document_type == DocumentType.ATTENDANCE:
                existing = attendance_by_month.get(month)
                if existing is None or (
                    doc.created_at
                    and existing.created_at
                    and doc.created_at > existing.created_at
                ):
                    attendance_by_month[month] = doc

        payslip_ids = [d.id for d in payslips_by_month.values()]
        latest_runs = await self._runs.list_latest_by_document_ids(payslip_ids)
        findings_by_run = await self._load_findings_map(list(latest_runs.values()))

        months: list[dict[str, Any]] = []
        for month in range(1, 13):
            payslip = payslips_by_month.get(month)
            attendance = attendance_by_month.get(month)
            run = latest_runs.get(payslip.id) if payslip is not None else None
            validation_payload = self._validation_payload(
                run, findings_by_run.get(run.id, []) if run else []
            )
            presentation = compute_presentation_status(
                payslip_exists=payslip is not None,
                validation_exists=validation_payload is not None,
                overall_result=validation_payload.get("status_result") if validation_payload else None,
                highest_finding_severity=(
                    validation_payload.get("highest_severity") if validation_payload else None
                ),
                overall_confidence=(
                    validation_payload.get("confidence") if validation_payload else None
                ),
                validation_status=(
                    validation_payload.get("status") if validation_payload else None
                ),
            )
            months.append(
                {
                    "month": month,
                    "payslip": document_summary(payslip),
                    "attendance": {
                        **document_summary(attendance),
                        "analysis_status": (
                            "not_connected" if attendance is not None else "missing"
                        ),
                    },
                    "latest_validation": (
                        {
                            "exists": True,
                            "validation_run_id": validation_payload["validation_run_id"],
                            "status": validation_payload["status"],
                            "overall_result": validation_payload.get("status_result"),
                            "confidence": validation_payload.get("confidence"),
                            "completed_at": validation_payload.get("completed_at"),
                            "findings_count": validation_payload.get("findings_count", 0),
                            "highest_severity": validation_payload.get("highest_severity"),
                            "scope": validation_payload.get("scope") or [],
                        }
                        if validation_payload
                        else {
                            "exists": False,
                            "validation_run_id": None,
                            "status": "not_run",
                            "overall_result": None,
                            "confidence": None,
                            "completed_at": None,
                            "findings_count": 0,
                            "highest_severity": None,
                            "scope": [],
                        }
                    ),
                    "presentation_status": presentation,
                }
            )

        return {
            "year": year,
            "available_years": available_years,
            "months": months,
        }

    async def month_detail(
        self,
        *,
        organization_id: UUID,
        employee_id: UUID,
        year: int,
        month: int,
        employee: Any | None = None,
        national_id_encrypted: bytes | None = None,
        include_unpublished: bool = False,
        document_id: UUID | None = None,
    ) -> dict[str, Any]:
        if month < 1 or month > 12:
            raise ValueError("month must be 1-12")
        overview = await self.execute(
            organization_id=organization_id,
            employee_id=employee_id,
            year=year,
            include_unpublished=include_unpublished,
        )
        row = next(m for m in overview["months"] if m["month"] == month)
        findings: list[dict[str, Any]] = []
        confidence_explanation: str | None = None

        docs = await self._documents.list_for_employee(
            organization_id=organization_id,
            employee_id=employee_id,
        )
        if not include_unpublished:
            docs = [doc for doc in docs if is_employee_visible_document(doc)]
        matching_payslips = [
            d
            for d in docs
            if d.document_type == DocumentType.PAYSLIP
            and d.period
            and d.period.year == year
            and d.period.month == month
        ]
        if document_id is not None:
            payslip_doc = next(
                (document for document in matching_payslips if document.id == document_id),
                None,
            )
            if payslip_doc is None:
                from payroll_copilot.application.exceptions import DocumentNotFoundError

                raise DocumentNotFoundError(document_id)
        else:
            payslip_doc = (
                sorted(
                    matching_payslips,
                    key=lambda item: item.created_at or item.id,
                    reverse=True,
                )[0]
                if matching_payslips
                else None
            )

        selected_run = None
        if payslip_doc is not None:
            selected_run = (
                await self._runs.list_latest_by_document_ids([payslip_doc.id])
            ).get(payslip_doc.id)
        selected_findings = (
            await self._findings.list_by_run_id(selected_run.id)
            if selected_run is not None and self._findings is not None
            else []
        )
        selected_validation = (
            self._validation_payload(selected_run, selected_findings)
            if selected_run is not None
            else None
        )
        row["payslip"] = document_summary(payslip_doc)
        row["latest_validation"] = (
            {
                "exists": True,
                "validation_run_id": selected_validation["validation_run_id"],
                "status": selected_validation["status"],
                "overall_result": selected_validation.get("status_result"),
                "confidence": selected_validation.get("confidence"),
                "completed_at": selected_validation.get("completed_at"),
                "findings_count": selected_validation.get("findings_count", 0),
                "highest_severity": selected_validation.get("highest_severity"),
                "scope": selected_validation.get("scope") or [],
            }
            if selected_validation
            else {
                "exists": False,
                "validation_run_id": None,
                "status": "not_run",
                "overall_result": None,
                "confidence": None,
                "completed_at": None,
                "findings_count": 0,
                "highest_severity": None,
                "scope": [],
            }
        )
        row["presentation_status"] = compute_presentation_status(
            payslip_exists=payslip_doc is not None,
            validation_exists=selected_validation is not None,
            overall_result=(
                selected_validation.get("status_result")
                if selected_validation
                else None
            ),
            highest_finding_severity=(
                selected_validation.get("highest_severity")
                if selected_validation
                else None
            ),
            overall_confidence=(
                selected_validation.get("confidence")
                if selected_validation
                else None
            ),
            validation_status=(
                selected_validation.get("status")
                if selected_validation
                else None
            ),
        )
        run_id = row["latest_validation"].get("validation_run_id")
        if run_id and self._findings is not None:
            records = selected_findings
            findings = [
                {
                    "id": str(f.id),
                    "code": f.message_key,
                    "severity": f.severity.value
                    if hasattr(f.severity, "value")
                    else str(f.severity),
                    "message_key": f.message_key,
                    "message_params": dict(f.message_params or {}),
                    "expected_value": f.expected_value,
                    "actual_value": f.actual_value,
                    "confidence": float(f.confidence)
                    if f.confidence is not None
                    else None,
                    "legal_reference": f.legal_reference,
                    "explanation": (
                        str((f.message_params or {}).get("explanation") or "")
                        or None
                    ),
                }
                for f in records
            ]
        extraction_summary: dict[str, Any] = {
            "exists": False,
            "extraction_id": None,
            "extraction_version": None,
            "confirmation_status": "missing",
            "fields": [],
            "lifecycle_status": "missing",
            "identity_check": None,
            "period_check": None,
            "blocks_confirmation": False,
            "confirmed_at": None,
        }
        validation_history: list[dict[str, Any]] = []
        if payslip_doc is not None:
            from payroll_copilot.application.services.employee_workspace_snapshot import (
                apply_comparison_snapshot,
                fields_for_workspace_api,
                read_comparison_snapshot,
                rebuild_comparison,
            )

            meta = dict(payslip_doc.metadata or {})
            latest_ext = None
            if self._extractions is not None:
                latest_ext = await self._extractions.get_latest_for_document(payslip_doc.id)
            confirmation_status = (
                (latest_ext.confirmation_status if latest_ext else None)
                or (
                    "confirmed"
                    if meta.get("lifecycle_status") == "confirmed"
                    else meta.get("lifecycle_status")
                )
                or "review_required"
            )
            raw_fields = (
                fields_from_structured(latest_ext.structured_data) if latest_ext else []
            )
            api_fields = fields_for_workspace_api(raw_fields)
            explainability_enabled = bool(
                get_settings().layout_explainability_enabled
            )
            evidence_by_field = (
                build_field_evidence_map(
                    latest_ext.structured_data,
                    latest_ext.layout_analysis,
                )
                if explainability_enabled and latest_ext
                else {}
            )
            if evidence_by_field:
                api_fields = attach_field_evidence(api_fields, evidence_by_field)

            snapshot = read_comparison_snapshot(meta)
            if snapshot is None and latest_ext is not None and employee is not None:
                comparison = rebuild_comparison(
                    employee=employee,
                    national_id_encrypted=national_id_encrypted,
                    document=payslip_doc,
                    extraction=latest_ext,
                )
                snapshot = {
                    "identity_check": comparison.identity_check.to_dict(),
                    "period_check": comparison.period_check.to_dict(),
                    "blocks_confirmation": comparison.blocks_confirmation,
                }
                # Backfill so subsequent loads do not need to rebuild.
                payslip_doc.metadata = apply_comparison_snapshot(meta, comparison)
                await self._documents.save(payslip_doc)
                meta = dict(payslip_doc.metadata or {})

            extraction_summary = {
                "exists": True,
                "extraction_id": str(latest_ext.id)
                if latest_ext
                else (
                    meta.get("current_extraction_id") or meta.get("confirmed_extraction_id")
                ),
                "extraction_version": (
                    latest_ext.extraction_version
                    if latest_ext
                    else (
                        meta.get("current_extraction_version")
                        or meta.get("confirmed_extraction_version")
                    )
                ),
                "confirmation_status": confirmation_status,
                "fields": api_fields,
                "explainability_enabled": explainability_enabled,
                "lifecycle_status": meta.get("lifecycle_status")
                or (
                    LIFECYCLE_CONFIRMED
                    if confirmation_status == "confirmed"
                    else LIFECYCLE_REVIEW_REQUIRED
                ),
                "original_filename": payslip_doc.original_filename,
                "identity_check": snapshot["identity_check"] if snapshot else None,
                "period_check": snapshot["period_check"] if snapshot else None,
                "blocks_confirmation": bool(snapshot["blocks_confirmation"])
                if snapshot
                else False,
                "confirmed_at": (
                    latest_ext.confirmed_at.isoformat()
                    if latest_ext and latest_ext.confirmed_at
                    else None
                ),
            }
            current_ext = (
                str(latest_ext.id)
                if latest_ext
                else meta.get("current_extraction_id")
            )
            if hasattr(self._runs, "list_for_document"):
                runs = await self._runs.list_for_document(payslip_doc.id)
                run_evidence_cache: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
                for run in runs:
                    run_findings = (
                        await self._findings.list_by_run_id(run.id)
                        if self._findings is not None
                        else []
                    )
                    outdated = bool(
                        current_ext
                        and run.extraction_id
                        and str(run.extraction_id) != str(current_ext)
                    )
                    if (
                        run_id
                        and str(run.id) == str(run_id)
                        and run.enrichment is not None
                    ):
                        confidence_explanation = getattr(
                            run.enrichment, "confidence_explanation", None
                        )
                    run_structured: dict[str, Any] = {}
                    run_evidence: dict[str, Any] = {}
                    if explainability_enabled and self._extractions is not None:
                        run_key = str(run.extraction_id) if run.extraction_id else ""
                        if run_key and run_key in run_evidence_cache:
                            run_structured, run_evidence = run_evidence_cache[run_key]
                        elif run.extraction_id is not None:
                            if (
                                latest_ext is not None
                                and str(run.extraction_id) == str(latest_ext.id)
                            ):
                                run_ext = latest_ext
                            else:
                                run_ext = await self._extractions.get_by_id(
                                    run.extraction_id
                                )
                            if run_ext is not None:
                                run_structured = dict(run_ext.structured_data or {})
                                run_evidence = build_field_evidence_map(
                                    run_ext.structured_data,
                                    run_ext.layout_analysis,
                                )
                            run_evidence_cache[run_key] = (
                                run_structured,
                                run_evidence,
                            )
                    validation_history.append(
                        {
                            "validation_run_id": str(run.id),
                            "status": run.status.value
                            if hasattr(run.status, "value")
                            else str(run.status),
                            "overall_result": (
                                run.overall_result.value
                                if run.overall_result is not None
                                and hasattr(run.overall_result, "value")
                                else None
                            ),
                            "confidence": float(run.overall_confidence)
                            if run.overall_confidence is not None
                            else None,
                            "completed_at": run.completed_at.isoformat()
                            if run.completed_at
                            else None,
                            "extraction_id": str(run.extraction_id)
                            if run.extraction_id
                            else None,
                            "outdated": outdated,
                            "findings": [
                                {
                                    "id": str(finding.id),
                                    "code": finding.message_key,
                                    "severity": finding.severity.value
                                    if hasattr(finding.severity, "value")
                                    else str(finding.severity),
                                    "message_key": finding.message_key,
                                    "message_params": dict(
                                        finding.message_params or {}
                                    ),
                                    "expected_value": finding.expected_value,
                                    "actual_value": finding.actual_value,
                                    "confidence": (
                                        float(finding.confidence)
                                        if finding.confidence is not None
                                        else None
                                    ),
                                    **(
                                        {
                                            "evidence_explanation": build_validation_explanation(
                                                finding=finding,
                                                structured_data=run_structured,
                                                evidence_by_field=run_evidence,
                                            )
                                        }
                                        if explainability_enabled
                                        else {}
                                    ),
                                }
                                for finding in run_findings
                            ],
                            **(
                                {
                                    "evidence_summary": build_validation_run_explanation(
                                        overall_result=run.overall_result,
                                        fields=fields_for_workspace_api(
                                            fields_from_structured(run_structured)
                                        )
                                        if run_structured
                                        else [],
                                        evidence_by_field=run_evidence,
                                    )
                                }
                                if explainability_enabled
                                else {}
                            ),
                        }
                    )
        confirmed = extraction_summary.get("confirmation_status") == "confirmed"
        missing: list[dict[str, str]] = []
        if not row["payslip"]["exists"]:
            missing.append({"document_type": "payslip", "reason_code": "payslip_missing"})
        if not row["attendance"]["exists"]:
            missing.append({"document_type": "attendance", "reason_code": "attendance_missing"})
        if row["payslip"]["exists"] and not confirmed:
            missing.append(
                {
                    "document_type": "payslip_extraction",
                    "reason_code": "extraction_not_confirmed",
                }
            )
        return {
            "year": year,
            "month": month,
            "payslip": row["payslip"],
            "attendance": row["attendance"],
            "extraction": extraction_summary,
            "validation_history": validation_history,
            "latest_validation": {
                **row["latest_validation"],
                "findings": findings,
                "confidence_explanation": confidence_explanation,
                "outdated": next(
                    (
                        h["outdated"]
                        for h in validation_history
                        if h["validation_run_id"]
                        == row["latest_validation"].get("validation_run_id")
                    ),
                    False,
                ),
                "extraction_id": next(
                    (
                        h.get("extraction_id")
                        for h in validation_history
                        if h["validation_run_id"]
                        == row["latest_validation"].get("validation_run_id")
                    ),
                    None,
                ),
            },
            "missing_documents": missing,
            "presentation_status": row["presentation_status"],
            "actions": {
                "can_upload_payslip": True,
                "can_upload_attendance": True,
                "can_run_validation": bool(row["payslip"]["exists"]) and confirmed,
                "can_confirm_extraction": bool(row["payslip"]["exists"]) and not confirmed,
                "can_review_extraction": bool(row["payslip"]["exists"]),
            },
        }

    async def _load_findings_map(
        self, runs: list[ValidationRunRecord]
    ) -> dict[UUID, list[Any]]:
        out: dict[UUID, list[Any]] = {}
        if self._findings is None:
            return out
        for run in runs:
            out[run.id] = await self._findings.list_by_run_id(run.id)
        return out

    def _validation_payload(
        self,
        run: ValidationRunRecord | None,
        findings: list[Any],
    ) -> dict[str, Any] | None:
        if run is None:
            return None
        status = run.status.value if hasattr(run.status, "value") else str(run.status)
        overall = (
            run.overall_result.value
            if run.overall_result is not None and hasattr(run.overall_result, "value")
            else (str(run.overall_result) if run.overall_result else None)
        )
        conf = float(run.overall_confidence) if run.overall_confidence is not None else None
        completed_at = run.completed_at.isoformat() if run.completed_at is not None else None
        findings_count = len(findings) if findings else int(run.rules_failed or 0)
        severity_codes = [
            f.severity.value if hasattr(f.severity, "value") else str(f.severity) for f in findings
        ]

        scope: list[dict[str, Any]] = []
        if run.enrichment is not None:
            scope = [
                {
                    "key": item.key,
                    "label": item.label,
                    "status": item.status,
                    "reason": item.reason,
                }
                for item in (run.enrichment.validation_scope or [])
            ]

        return {
            "validation_run_id": str(run.id),
            "status": status,
            "status_result": overall,
            "confidence": conf,
            "completed_at": completed_at,
            "findings_count": findings_count,
            "highest_severity": highest_severity(severity_codes),
            "scope": scope,
        }
