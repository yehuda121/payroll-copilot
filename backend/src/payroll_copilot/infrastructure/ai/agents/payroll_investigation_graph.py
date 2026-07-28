"""LangGraph orchestration for payroll investigation / anomaly questions."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from payroll_copilot.application.ports.investigation import (
    InvestigationDataPort,
    InvestigationRunnerPort,
)
from payroll_copilot.application.services.investigation_completeness import (
    assess_completeness,
    needs_s3_enrichment,
)
from payroll_copilot.application.services.investigation_intent import (
    detect_investigation_focus,
)
from payroll_copilot.application.services.investigation_synthesizer import (
    clarification_insufficient_evidence,
    clarification_no_current,
    clarification_no_history,
    synthesize_explained,
)
from payroll_copilot.application.services.payslip_line_item_diff import (
    COMPARISON_FIELD_KEYS,
    diff_snapshots,
    material_deltas,
)
from payroll_copilot.application.services.payslip_period_lookback import (
    previous_month,
    select_comparison_period,
)
from payroll_copilot.domain.investigation.types import (
    InvestigationFocus,
    InvestigationOutcome,
    InvestigationResult,
    PeriodRef,
)
from payroll_copilot.infrastructure.ai.agents.payroll_investigation_state import (
    InvestigationGraphState,
)
from payroll_copilot.infrastructure.i18n import normalize_locale

logger = logging.getLogger(__name__)

_FOCUS_FIELD_KEYS: dict[InvestigationFocus, tuple[str, ...]] = {
    InvestigationFocus.GENERAL: COMPARISON_FIELD_KEYS,
    InvestigationFocus.NET_GROSS: (
        "gross_salary",
        "net_salary",
        "base_salary",
        "total_deductions",
        "income_tax",
    ),
    InvestigationFocus.OVERTIME: ("overtime_hours", "gross_salary", "net_salary"),
    InvestigationFocus.DEDUCTIONS: (
        "income_tax",
        "national_insurance",
        "health_tax",
        "total_deductions",
        "net_salary",
        "gross_salary",
    ),
    InvestigationFocus.PENSION: (
        "pension_employee",
        "pension_employer",
        "net_salary",
        "gross_salary",
    ),
    InvestigationFocus.LEAVE: (
        "vacation_balance",
        "sick_leave_balance",
        "net_salary",
    ),
    InvestigationFocus.BASE_SALARY: ("base_salary", "gross_salary", "net_salary"),
}


def _parse_period_key(key: str) -> PeriodRef | None:
    text = (key or "").strip()
    if len(text) != 7 or text[4] != "-":
        return None
    try:
        year = int(text[:4])
        month = int(text[5:7])
    except ValueError:
        return None
    if not (1 <= month <= 12):
        return None
    return PeriodRef(year=year, month=month)


def _latest_period(available: set[str]) -> PeriodRef | None:
    if not available:
        return None
    return _parse_period_key(max(available))


def _enrichment_failed(notes: str | None) -> bool:
    text = (notes or "").strip().lower()
    if not text:
        return False
    return (
        text.startswith("enrichment_failed:")
        or text == "s3_enrichment_unavailable"
        or text == "enrichment_no_fields"
    )


class PayrollInvestigationGraph(InvestigationRunnerPort):
    """Scenario A–D investigation graph. Auth IDs are injected; never from the message."""

    def __init__(self, data: InvestigationDataPort) -> None:
        self._data = data
        self._graph = self._build_graph()

    async def run(
        self,
        *,
        message: str,
        session_id: str,
        locale: str,
        organization_id: UUID,
        employee_id: UUID,
        include_unpublished: bool = False,
        target_year: int | None = None,
        target_month: int | None = None,
    ) -> InvestigationResult:
        initial: InvestigationGraphState = {
            "message": message,
            "locale": normalize_locale(locale),
            "session_id": session_id or str(uuid4()),
            "organization_id": str(organization_id),
            "employee_id": str(employee_id),
            "include_unpublished": include_unpublished,
            "target_year": target_year,
            "target_month": target_month,
            "focus": InvestigationFocus.GENERAL.value,
            "requested_field_keys": list(COMPARISON_FIELD_KEYS),
            "available_periods": [],
            "target_period": None,
            "comparison_period": None,
            "lookback_attempts": [],
            "current_snapshot": None,
            "prior_snapshot": None,
            "completeness": None,
            "enrichment_needed": False,
            "deltas": [],
            "outcome": InvestigationOutcome.INSUFFICIENT_EVIDENCE.value,
            "clarification_prompt": None,
            "answer": "",
            "confidence": 0.0,
            "used_tools": [],
            "sources": [],
            "route_hint": "continue",
            "notes": [],
            "extra": {},
        }
        final = await self._graph.ainvoke(initial)
        outcome = InvestigationOutcome(final["outcome"])
        return InvestigationResult(
            outcome=outcome,
            answer=str(final["answer"] or ""),
            target_period=final.get("target_period"),
            comparison_period=final.get("comparison_period"),
            deltas=tuple(final.get("deltas") or ()),
            lookback_attempts=tuple(final.get("lookback_attempts") or ()),
            used_tools=tuple(final.get("used_tools") or ()),
            sources=tuple(final.get("sources") or ()),
            confidence=float(final.get("confidence") or 0.0),
            clarification_prompt=final.get("clarification_prompt"),
            session_id=str(final.get("session_id") or session_id or ""),
        )

    def _build_graph(self) -> Any:
        from langgraph.graph import END, StateGraph

        graph = StateGraph(InvestigationGraphState)
        graph.add_node("planner", self._node_planner)
        graph.add_node("retrieve", self._node_retrieve)
        graph.add_node("completeness", self._node_completeness)
        graph.add_node("enrich", self._node_enrich)
        graph.add_node("reason", self._node_reason)
        graph.add_node("synthesize", self._node_synthesize)
        graph.add_node("clarify", self._node_clarify)

        graph.set_entry_point("planner")
        graph.add_edge("planner", "retrieve")
        graph.add_conditional_edges(
            "retrieve",
            self._route_after_retrieve,
            {
                "clarify": "clarify",
                "completeness": "completeness",
            },
        )
        graph.add_conditional_edges(
            "completeness",
            self._route_after_completeness,
            {
                "enrich": "enrich",
                "reason": "reason",
            },
        )
        graph.add_conditional_edges(
            "enrich",
            self._route_after_enrich,
            {
                "clarify": "clarify",
                "reason": "reason",
            },
        )
        graph.add_edge("reason", "synthesize")
        graph.add_edge("synthesize", END)
        graph.add_edge("clarify", END)
        return graph.compile()

    def _node_planner(self, state: InvestigationGraphState) -> InvestigationGraphState:
        focus = detect_investigation_focus(state["message"])
        keys = list(_FOCUS_FIELD_KEYS.get(focus, COMPARISON_FIELD_KEYS))
        return {
            **state,
            "focus": focus.value,
            "requested_field_keys": keys,
            "used_tools": [*state["used_tools"], "investigation_planner"],
        }

    async def _node_retrieve(
        self, state: InvestigationGraphState
    ) -> InvestigationGraphState:
        org_id = UUID(state["organization_id"])
        emp_id = UUID(state["employee_id"])
        include_unpublished = bool(state["include_unpublished"])
        available = await self._data.list_available_payslip_periods(
            organization_id=org_id,
            employee_id=emp_id,
            include_unpublished=include_unpublished,
        )
        tools = [*state["used_tools"], "dynamodb_retrieve"]
        sources = list(state["sources"])

        target: PeriodRef | None = None
        if state["target_year"] is not None and state["target_month"] is not None:
            target = PeriodRef(year=int(state["target_year"]), month=int(state["target_month"]))
        else:
            target = _latest_period(available)

        if target is None:
            return {
                **state,
                "available_periods": sorted(available),
                "used_tools": tools,
                "route_hint": "clarify",
                "outcome": InvestigationOutcome.NEEDS_USER_INPUT.value,
                "clarification_prompt": clarification_no_current(
                    locale=state["locale"],
                    message=state["message"],
                ),
                "notes": [*state["notes"], "no_target_period"],
            }

        current = await self._data.load_period_snapshot(
            organization_id=org_id,
            employee_id=emp_id,
            period=target,
            include_unpublished=include_unpublished,
        )
        if current is None:
            return {
                **state,
                "available_periods": sorted(available),
                "target_period": target,
                "used_tools": tools,
                "route_hint": "clarify",
                "outcome": InvestigationOutcome.NEEDS_USER_INPUT.value,
                "clarification_prompt": clarification_no_current(
                    locale=state["locale"],
                    message=state["message"],
                ),
                "notes": [*state["notes"], "missing_current_snapshot"],
            }

        sources.append(
            {
                "title": f"Payslip {target.key}",
                "type": "payslip",
                "reference": str(current.document_id) if current.document_id else None,
            }
        )

        comparison, attempts = select_comparison_period(
            target=target,
            available=available,
        )
        lookback_keys = [p.key for p in attempts]
        if comparison is None:
            expected_prior = attempts[0] if attempts else previous_month(target)
            return {
                **state,
                "available_periods": sorted(available),
                "target_period": target,
                "comparison_period": None,
                "lookback_attempts": lookback_keys,
                "current_snapshot": current,
                "prior_snapshot": None,
                "used_tools": tools,
                "sources": sources,
                "route_hint": "clarify",
                "outcome": InvestigationOutcome.NEEDS_USER_INPUT.value,
                "clarification_prompt": clarification_no_history(
                    locale=state["locale"],
                    target=target,
                    message=state["message"],
                    expected_prior=expected_prior,
                ),
                "notes": [*state["notes"], "scenario_d_no_history"],
            }

        prior = await self._data.load_period_snapshot(
            organization_id=org_id,
            employee_id=emp_id,
            period=comparison,
            include_unpublished=include_unpublished,
        )
        if prior is None:
            return {
                **state,
                "available_periods": sorted(available),
                "target_period": target,
                "comparison_period": comparison,
                "lookback_attempts": lookback_keys,
                "current_snapshot": current,
                "prior_snapshot": None,
                "used_tools": tools,
                "sources": sources,
                "route_hint": "clarify",
                "outcome": InvestigationOutcome.NEEDS_USER_INPUT.value,
                "clarification_prompt": clarification_no_history(
                    locale=state["locale"],
                    target=target,
                    message=state["message"],
                    expected_prior=comparison,
                ),
                "notes": [*state["notes"], "comparison_period_missing_snapshot"],
            }

        sources.append(
            {
                "title": f"Payslip {comparison.key}",
                "type": "payslip",
                "reference": str(prior.document_id) if prior.document_id else None,
            }
        )
        # Scenario A vs B is distinguished only by whether comparison == previous month.
        note = (
            "scenario_a_adjacent"
            if attempts and comparison == attempts[0]
            else "scenario_b_lookback"
        )
        return {
            **state,
            "available_periods": sorted(available),
            "target_period": target,
            "comparison_period": comparison,
            "lookback_attempts": lookback_keys,
            "current_snapshot": current,
            "prior_snapshot": prior,
            "used_tools": tools,
            "sources": sources,
            "route_hint": "completeness",
            "notes": [*state["notes"], note],
        }

    def _route_after_retrieve(self, state: InvestigationGraphState) -> str:
        return "clarify" if state.get("route_hint") == "clarify" else "completeness"

    def _node_completeness(
        self, state: InvestigationGraphState
    ) -> InvestigationGraphState:
        current = state.get("current_snapshot")
        if current is None:
            return {
                **state,
                "route_hint": "clarify",
                "outcome": InvestigationOutcome.INSUFFICIENT_EVIDENCE.value,
            }
        focus = InvestigationFocus(state["focus"])
        report = assess_completeness(current, focus=focus)
        enrich = needs_s3_enrichment(report)
        return {
            **state,
            "completeness": report,
            "enrichment_needed": enrich,
            "used_tools": [*state["used_tools"], "completeness_check"],
            "route_hint": "enrich" if enrich else "reason",
        }

    def _route_after_completeness(self, state: InvestigationGraphState) -> str:
        return "enrich" if state.get("enrichment_needed") else "reason"

    async def _node_enrich(
        self, state: InvestigationGraphState
    ) -> InvestigationGraphState:
        """Scenario C: ephemeral S3→OCR→parse. Never writes DynamoDB.

        Failures must not raise — soft-fallback to insufficient_evidence when
        essentials remain missing after enrichment.
        """
        current = state.get("current_snapshot")
        prior = state.get("prior_snapshot")
        report = state.get("completeness")
        if current is None or report is None:
            return {
                **state,
                "route_hint": "clarify",
                "outcome": InvestigationOutcome.INSUFFICIENT_EVIDENCE.value,
                "clarification_prompt": clarification_insufficient_evidence(
                    locale=state["locale"],
                    target=state.get("target_period"),
                    message=state["message"],
                ),
            }
        missing = tuple(
            dict.fromkeys(
                list(report.missing_essential_keys) + list(report.missing_enrichment_keys)
            )
        )
        tools = [*state["used_tools"], "s3_ephemeral_enrichment"]
        notes = list(state["notes"])
        focus = InvestigationFocus(state["focus"])
        try:
            enriched_current = await self._data.enrich_snapshot_from_original(
                current,
                missing_keys=missing,
            )
            notes.append(enriched_current.enrichment_notes or "enrichment_done")
            enriched_prior = prior
            if prior is not None:
                prior_report = assess_completeness(prior, focus=focus)
                prior_missing = tuple(
                    dict.fromkeys(
                        list(prior_report.missing_essential_keys)
                        + list(prior_report.missing_enrichment_keys)
                    )
                )
                if prior_missing:
                    enriched_prior = await self._data.enrich_snapshot_from_original(
                        prior,
                        missing_keys=prior_missing,
                    )
                    notes.append(
                        f"prior:{enriched_prior.enrichment_notes or 'enrichment_done'}"
                    )
        except Exception as exc:  # noqa: BLE001 — never break the chat turn
            logger.info(
                "investigation enrich node failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            prompt = clarification_insufficient_evidence(
                locale=state["locale"],
                target=state.get("target_period"),
                missing_keys=missing,
                message=state["message"],
            )
            return {
                **state,
                "used_tools": tools,
                "notes": [*notes, f"enrich_node_exception:{type(exc).__name__}"],
                "route_hint": "clarify",
                "outcome": InvestigationOutcome.INSUFFICIENT_EVIDENCE.value,
                "clarification_prompt": prompt,
            }

        post = assess_completeness(enriched_current, focus=focus)
        enrichment_failed = _enrichment_failed(enriched_current.enrichment_notes)
        if post.missing_essential_keys and enrichment_failed:
            prompt = clarification_insufficient_evidence(
                locale=state["locale"],
                target=state.get("target_period"),
                missing_keys=post.missing_essential_keys,
                message=state["message"],
            )
            return {
                **state,
                "current_snapshot": enriched_current,
                "prior_snapshot": enriched_prior,
                "completeness": post,
                "used_tools": tools,
                "notes": [*notes, "enrichment_insufficient_essentials"],
                "route_hint": "clarify",
                "outcome": InvestigationOutcome.INSUFFICIENT_EVIDENCE.value,
                "clarification_prompt": prompt,
            }

        return {
            **state,
            "current_snapshot": enriched_current,
            "prior_snapshot": enriched_prior,
            "completeness": post,
            "used_tools": tools,
            "notes": notes,
            "route_hint": "reason",
        }

    def _route_after_enrich(self, state: InvestigationGraphState) -> str:
        return "clarify" if state.get("route_hint") == "clarify" else "reason"

    def _node_reason(self, state: InvestigationGraphState) -> InvestigationGraphState:
        current = state.get("current_snapshot")
        prior = state.get("prior_snapshot")
        if current is None or prior is None:
            target = state.get("target_period")
            expected = previous_month(target) if target is not None else None
            return {
                **state,
                "outcome": InvestigationOutcome.INSUFFICIENT_EVIDENCE.value,
                "route_hint": "clarify",
                "clarification_prompt": clarification_no_history(
                    locale=state["locale"],
                    target=target,
                    message=state["message"],
                    expected_prior=expected,
                ),
            }
        keys = tuple(state.get("requested_field_keys") or COMPARISON_FIELD_KEYS)
        deltas = diff_snapshots(current, prior, field_keys=keys)
        return {
            **state,
            "deltas": material_deltas(deltas) or deltas,
            "used_tools": [*state["used_tools"], "line_item_diff"],
            "outcome": InvestigationOutcome.EXPLAINED.value,
        }

    def _node_synthesize(
        self, state: InvestigationGraphState
    ) -> InvestigationGraphState:
        current = state.get("current_snapshot")
        target = state.get("target_period")
        comparison = state.get("comparison_period")
        if current is None or target is None or comparison is None:
            expected = previous_month(target) if target is not None else None
            prompt = state.get("clarification_prompt") or clarification_no_history(
                locale=state["locale"],
                target=target,
                message=state["message"],
                expected_prior=expected,
            )
            return {
                **state,
                "answer": prompt,
                "outcome": InvestigationOutcome.NEEDS_USER_INPUT.value,
                "confidence": 0.2,
            }
        answer = synthesize_explained(
            locale=state["locale"],
            focus=InvestigationFocus(state["focus"]),
            target=target,
            comparison=comparison,
            deltas=list(state.get("deltas") or []),
            message=state["message"],
        )
        confidence = 0.85 if state.get("deltas") else 0.55
        notes = " ".join(state.get("notes") or [])
        if "enrichment_failed" in notes or "s3_enrichment_unavailable" in notes:
            confidence = min(confidence, 0.6)
        return {
            **state,
            "answer": answer,
            "outcome": InvestigationOutcome.EXPLAINED.value,
            "confidence": confidence,
            "used_tools": [*state["used_tools"], "investigation_synthesizer"],
        }

    def _node_clarify(self, state: InvestigationGraphState) -> InvestigationGraphState:
        target = state.get("target_period")
        expected = previous_month(target) if target is not None else None
        prompt = state.get("clarification_prompt") or clarification_no_history(
            locale=state["locale"],
            target=target,
            message=state["message"],
            expected_prior=expected,
        )
        outcome = state.get("outcome") or InvestigationOutcome.NEEDS_USER_INPUT.value
        return {
            **state,
            "answer": prompt,
            "clarification_prompt": prompt,
            "outcome": outcome,
            "confidence": 0.3,
            "used_tools": [*state["used_tools"], "investigation_clarify"],
        }


__all__ = ["PayrollInvestigationGraph"]
