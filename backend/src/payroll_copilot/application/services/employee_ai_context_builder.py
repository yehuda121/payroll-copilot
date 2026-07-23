"""Backend-authorized structured context for authenticated Employee AI chat.

This builder is deliberately not an AI tool. It performs lightweight intent
routing, loads only resources owned by the bound employee, and produces a
sanitized context string. The LLM never receives repositories, storage
handles, employee selectors, or frontend-supplied identifiers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
    ValidationFindingRepository,
    ValidationRunRepository,
)
from payroll_copilot.application.services.assistant_intent import (
    contains_any,
    is_personal_payroll_message,
    parse_message_period,
)
from payroll_copilot.application.services.assistant_response_templates import (
    facts_preamble,
    period_clarification_message,
)
from payroll_copilot.application.services.conversation_summary import ConversationSummary
from payroll_copilot.application.use_cases.employee_payroll_months import (
    BuildEmployeePayrollMonthsUseCase,
)
from payroll_copilot.application.use_cases.list_employee_documents import (
    ListEmployeeDocumentsUseCase,
)

# Late import type for AnswerStrategyPlan to avoid cycles at runtime in type hints.
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from payroll_copilot.application.services.answer_strategy import AnswerStrategyPlan


_PROFILE_TERMS = (
    "my name",
    "who am i",
    "my profile",
    "employee number",
    "national id",
    "השם שלי",
    "מי אני",
    "הפרופיל שלי",
    "מספר עובד",
    "תעודת זהות",
    "اسمي",
    "من أنا",
    "ملفي",
    "رقم الموظف",
    "الهوية",
)
_VALIDATION_TERMS = (
    "validation",
    "validate",
    "finding",
    "warning",
    "critical",
    "compliance",
    "בדיקה",
    "אזהרה",
    "קריטי",
    "תקין",
    "تحقق",
    "فحص",
    "تحذير",
    "امتثال",
)
_EVIDENCE_TERMS = (
    "evidence",
    "extracted from",
    "source page",
    "associated",
    "association",
    "ראיה",
    "חולץ מ",
    "עמוד מקור",
    "שיוך",
    "دليل",
    "مستخرج من",
    "صفحة المصدر",
    "مرتبط",
)
_DOCUMENT_TERMS = (
    "my document",
    "my contract",
    "id card",
    "id appendix",
    "uploaded document",
    "המסמך שלי",
    "החוזה שלי",
    "תעודת זהות",
    "ספח",
    "מסמכים שהעליתי",
    "مستنداتي",
    "عقدي",
    "بطاقة الهوية",
)
_IDENTIFIER_KEYS = {
    "employee_id",
    "organization_id",
    "document_id",
    "extraction_id",
    "validation_run_id",
}
_SENSITIVE_EXTRACTED_FIELD_KEYS = {
    "national_id",
    "employee_national_id",
    "id_number",
    "identity_number",
}


@dataclass(frozen=True, slots=True)
class EmployeeContextIntent:
    profile: bool = False
    payroll: bool = False
    validation: bool = False
    documents: bool = False
    year: int | None = None
    month: int | None = None

    @property
    def needs_employee_context(self) -> bool:
        return self.profile or self.payroll or self.validation or self.documents

    @property
    def needs_period_clarification(self) -> bool:
        """True when payroll/validation is needed but no explicit/last-month period."""
        return (self.payroll or self.validation) and self.month is None


@dataclass(slots=True)
class EmployeeAIContextResult:
    prepared_context: str = ""
    loaded_resource_keys: list[str] = field(default_factory=list)
    profile: dict[str, Any] | None = None
    payroll_months: list[dict[str, Any]] = field(default_factory=list)
    payroll_month_details: list[dict[str, Any]] = field(default_factory=list)
    document_center: dict[str, Any] | None = None


class EmployeeAIContextBuilder:
    """Build canonical employee context through employee-scoped repositories."""

    def __init__(
        self,
        *,
        documents: DocumentRepository,
        validation_runs: ValidationRunRepository,
        validation_findings: ValidationFindingRepository,
        extractions: DocumentExtractionRepository,
    ) -> None:
        self._documents = documents
        self._validation_runs = validation_runs
        self._validation_findings = validation_findings
        self._extractions = extractions

    async def build(
        self,
        *,
        message: str,
        employee: Any,
        national_id_encrypted: bytes | None,
        today: date | None = None,
        include_unpublished: bool = False,
        review_document_id: UUID | None = None,
        strategy_plan: AnswerStrategyPlan | None = None,
        conversation_summary: ConversationSummary | None = None,
    ) -> EmployeeAIContextResult:
        """Load only context requested by intent / answer strategy for the bound employee."""
        from payroll_copilot.application.services.answer_strategy import (
            AnswerStrategy,
            AnswerStrategyPlan as Plan,
        )

        current_date = today or date.today()
        plan = strategy_plan
        if plan is None:
            from payroll_copilot.application.services.answer_strategy import (
                resolve_answer_strategy,
            )

            plan = resolve_answer_strategy(message, today=current_date)
        assert isinstance(plan, Plan)

        intent = plan.intent or analyze_employee_context_intent(message, today=current_date)
        # Apply strategy period when referential resolution filled it.
        if plan.year is not None and plan.month is not None:
            intent = EmployeeContextIntent(
                profile=intent.profile,
                payroll=intent.payroll or plan.needs.payslip,
                validation=intent.validation or plan.needs.validation,
                documents=intent.documents or plan.needs.documents,
                year=plan.year,
                month=plan.month,
            )

        needs = plan.needs
        load_profile = needs.profile or intent.profile
        load_payslip = needs.payslip or needs.multi_payslip or needs.validation
        load_documents = needs.documents or intent.documents
        load_summary = needs.conversation_summary and conversation_summary is not None

        # Labor-law-only / conversation-only: skip personal payroll repositories.
        if (
            plan.strategy
            in {
                AnswerStrategy.LABOR_LAW,
                AnswerStrategy.CONVERSATION_HISTORY,
                AnswerStrategy.GENERAL_PAYROLL,
            }
            and not load_payslip
            and not load_documents
            and not load_profile
            and review_document_id is None
        ):
            chunks: list[dict[str, Any]] = []
            loaded_keys: list[str] = []
            if load_summary and conversation_summary is not None:
                chunks.append(
                    {
                        "resource": "conversation_summary",
                        "data": conversation_summary.to_public_dict(),
                    }
                )
                loaded_keys.append("conversation_summary")
            return EmployeeAIContextResult(
                prepared_context=(
                    facts_preamble() + json.dumps(chunks, ensure_ascii=False, default=str)
                    if chunks
                    else ""
                ),
                loaded_resource_keys=loaded_keys,
            )

        if (
            not load_profile
            and not load_payslip
            and not load_documents
            and review_document_id is None
            and not load_summary
        ):
            return EmployeeAIContextResult()

        profile = self._profile_payload(employee) if load_profile else None
        payroll_lists: list[dict[str, Any]] = []
        month_details: list[dict[str, Any]] = []
        document_center: dict[str, Any] | None = None
        chunks = []
        loaded_keys = []

        if load_summary and conversation_summary is not None:
            chunks.append(
                {
                    "resource": "conversation_summary",
                    "data": conversation_summary.to_public_dict(),
                }
            )
            loaded_keys.append("conversation_summary")

        if profile is not None:
            chunks.append(
                {"resource": "employee_profile", "data": _sanitize_for_llm(profile)}
            )
            loaded_keys.append("employee_profile")

        payroll_builder = BuildEmployeePayrollMonthsUseCase(
            documents=self._documents,
            validation_runs=self._validation_runs,
            validation_findings=self._validation_findings,
            extractions=self._extractions,
        )

        if review_document_id is not None:
            review_document = await self._documents.get_by_id(review_document_id)
            if (
                review_document is None
                or review_document.organization_id != employee.organization_id
                or review_document.employee_id != employee.id
                or review_document.period is None
            ):
                return EmployeeAIContextResult(
                    prepared_context=(
                        facts_preamble() + json.dumps(chunks, ensure_ascii=False, default=str)
                        if chunks
                        else ""
                    ),
                    loaded_resource_keys=loaded_keys,
                    profile=profile,
                )
            detail = await payroll_builder.month_detail(
                organization_id=employee.organization_id,
                employee_id=employee.id,
                year=review_document.period.year,
                month=review_document.period.month,
                employee=employee,
                national_id_encrypted=national_id_encrypted,
                include_unpublished=include_unpublished,
                document_id=review_document_id,
            )
            month_details.append(detail)
            chunks.append(
                {
                    "resource": (
                        f"review_payslip:{review_document.period.year}-"
                        f"{review_document.period.month:02d}"
                    ),
                    "data": _sanitize_for_llm(detail),
                }
            )
            loaded_keys.append(f"review_document:{review_document_id}")
        elif load_payslip:
            if intent.needs_period_clarification and plan.month is None:
                chunks.append(
                    {
                        "resource": "period_clarification",
                        "data": {"message": period_clarification_message()},
                    }
                )
                loaded_keys.append("period_clarification")
            else:
                year = intent.year or plan.year or current_date.year
                month = int(intent.month if intent.month is not None else plan.month)
                periods: list[tuple[int, int]] = [(year, month)]
                # Calculation strategy may also need the prior month when only one is named.
                if needs.multi_payslip:
                    prev_month = month - 1
                    prev_year = year
                    if prev_month == 0:
                        prev_month = 12
                        prev_year -= 1
                    if (prev_year, prev_month) not in periods:
                        periods.append((prev_year, prev_month))

                for period_year, period_month in periods:
                    detail = await payroll_builder.month_detail(
                        organization_id=employee.organization_id,
                        employee_id=employee.id,
                        year=period_year,
                        month=period_month,
                        employee=employee,
                        national_id_encrypted=national_id_encrypted,
                        include_unpublished=include_unpublished,
                    )
                    month_details.append(detail)
                    chunks.append(
                        {
                            "resource": (
                                f"payroll_month:{period_year}-{period_month:02d}"
                            ),
                            "data": _sanitize_for_llm(detail),
                        }
                    )
                    loaded_keys.append(
                        f"payroll_month_detail:{period_year}-{period_month:02d}"
                    )

        if load_documents and review_document_id is None:
            document_center = await ListEmployeeDocumentsUseCase(
                documents=self._documents,
                extractions=self._extractions,
            ).execute(
                organization_id=employee.organization_id,
                employee_id=employee.id,
                include_unpublished=include_unpublished,
            )
            chunks.append(
                {
                    "resource": "employee_documents",
                    "data": _sanitize_for_llm(document_center),
                }
            )
            loaded_keys.append("employee_documents")

        return EmployeeAIContextResult(
            prepared_context=(
                facts_preamble() + json.dumps(chunks, ensure_ascii=False, default=str)
                if chunks
                else ""
            ),
            loaded_resource_keys=loaded_keys,
            profile=profile,
            payroll_months=payroll_lists,
            payroll_month_details=month_details,
            document_center=document_center,
        )

    @staticmethod
    def _profile_payload(employee: Any) -> dict[str, Any]:
        metadata = dict(employee.metadata or {})
        localized = metadata.get("verified_display_name") or (
            f"{employee.first_name} {employee.last_name}".strip()
        )
        return {
            "employee_id": str(employee.id),
            "employee_number": employee.employee_number,
            "full_name": str(metadata.get("display_name_en") or localized),
            "full_name_localized": str(localized),
            # Only the existing masked value is allowed into chat context.
            "national_id_masked": metadata.get("national_id_masked"),
            "organization_id": str(employee.organization_id),
            "status": (
                employee.status.value
                if hasattr(employee.status, "value")
                else str(employee.status)
            ),
        }

    @staticmethod
    def _select_relevant_month(
        overview: dict[str, Any],
        *,
        require_validation: bool,
    ) -> int | None:
        rows = list(overview.get("months") or [])
        candidates = [
            row
            for row in rows
            if (
                bool((row.get("latest_validation") or {}).get("exists"))
                if require_validation
                else bool((row.get("payslip") or {}).get("exists"))
            )
        ]
        if not candidates:
            return None
        return max(int(row["month"]) for row in candidates)


def analyze_employee_context_intent(
    message: str,
    *,
    today: date | None = None,
) -> EmployeeContextIntent:
    """Deterministic multilingual routing; no LLM or external access."""
    normalized = " ".join(message.lower().split())
    profile = contains_any(normalized, _PROFILE_TERMS)
    payroll = is_personal_payroll_message(normalized)
    validation = contains_any(normalized, _VALIDATION_TERMS)
    documents = contains_any(normalized, _DOCUMENT_TERMS)
    evidence = contains_any(normalized, _EVIDENCE_TERMS)

    year, month = parse_message_period(message, today=today)

    # A personal compliance question needs both canonical payroll/validation
    # facts and the unchanged legal-law search path.
    if validation:
        payroll = True
    if evidence:
        payroll = True

    return EmployeeContextIntent(
        profile=profile,
        payroll=payroll,
        validation=validation,
        documents=documents,
        year=year,
        month=month,
    )


def _sanitize_for_llm(value: Any) -> Any:
    """Remove internal selectors while preserving structured employee facts."""
    if isinstance(value, dict):
        semantic_key = str(value.get("key") or "").strip().lower()
        if semantic_key in _SENSITIVE_EXTRACTED_FIELD_KEYS:
            return {
                key: _sanitize_for_llm(item)
                for key, item in value.items()
                if key
                not in {
                    *_IDENTIFIER_KEYS,
                    "value",
                    "effective_value",
                    "source_text",
                }
            }
        return {
            key: _sanitize_for_llm(item)
            for key, item in value.items()
            if key not in _IDENTIFIER_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_for_llm(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    return value
