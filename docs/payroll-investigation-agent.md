# Payroll Investigation & Anomaly Agent

**Status:** Implemented (P0–P3)  
**Entry point:** Intent routing inside existing authenticated chat — no new public employee-ID fields.

## Purpose

Answer open-ended employee (and accountant-bound employee) questions about salary changes, unexpected deductions, and period-over-period anomalies.

The agent **explains** stored structured payslip fields and deterministic rule-engine findings. It never recalculates tax or salary rules. The rule engine remains the single source of truth for validation findings.

## Approved product decisions

| Decision | Choice |
| --- | --- |
| Write-back | Ephemeral in-graph only — Scenario C enrichment must **not** write DynamoDB |
| Lookback | Rolling **12 months** across calendar year boundaries |
| API shape | Intent route inside `/api/v1/assistant/employee/chat` (and accountant bind path) |
| Accountant | Same graph when accountant is bound to a selected same-org employee (`include_unpublished=True`) |

## Security guardrails

- Employee and organization IDs come **only** from backend auth binding (`require_bound_employee` / `bind_accountant_selected_employee`).
- Request bodies must not supply authoritative `employee_id` / `organization_id` selectors.
- Unpublished payslips are visible to accountants in selected-employee context only.
- Input safety guardrails still run before investigation routing.
- User-facing answers must not invent missing history (Scenario D) or fabricate line items.

## Intent routing

`resolve_answer_strategy` sets `AnswerStrategy.INVESTIGATION` when `is_investigation_message` matches (HE/EN/AR anomaly / “what changed” terms).

The employee chat implementation short-circuits to `PayrollInvestigationUseCase` instead of the general payroll assistant graph for that turn.

## LangGraph flow

```text
planner → retrieve → (clarify | completeness)
completeness → (enrich | reason)
enrich → (clarify | reason)   # soft fail if essentials still missing
reason → synthesize → END
clarify → END
```

| Scenario | Behavior |
| --- | --- |
| **A** | Current + previous month (X−1) present → deterministic diffs → explained answer |
| **B** | X−1 missing → scan rolling 12-month lookback for nearest prior payslip |
| **C** | Structured data incomplete for focus → ephemeral S3→OCR→parse; **no Dynamo write** |
| **D** | No historical comparator → `needs_user_input` clarification (no hallucination) |

### Enrichment failure (P2)

If S3 download, OCR, or parse fails:

- Exceptions are caught in the adapter and enrich node (never bubble to the HTTP layer).
- When **essential** fields (`gross_salary`, `net_salary`) remain missing → `insufficient_evidence` + soft clarification.
- When essentials already exist → continue with a partial deterministic explanation and enrichment notes.

## Key modules

| Path | Role |
| --- | --- |
| `domain/investigation/types.py` | Periods, deltas, outcomes, snapshots |
| `application/services/payslip_period_lookback.py` | Rolling 12-month comparator selection |
| `application/services/payslip_line_item_diff.py` | Deterministic field diffs |
| `application/services/investigation_completeness.py` | Scenario C gate |
| `application/services/investigation_intent.py` | Intent / focus detection |
| `application/services/investigation_synthesizer.py` | Locale-aware factual answers / clarifications |
| `application/use_cases/payroll_investigation.py` | Auth-bound command → runner |
| `infrastructure/ai/agents/payroll_investigation_graph.py` | LangGraph orchestration |
| `infrastructure/ai/agents/investigation_data_adapter.py` | Dynamo load + ephemeral S3 enrich |

## Tests

- Unit: lookback, diffs, completeness, graph A–D, enrichment resilience (timeout / empty S3 / OCR / parser).
- Integration: `/assistant/employee/chat` and `/assistant/accountant/employee/chat` for Scenarios A–D with auth overrides and fake investigation data (no live Dynamo/S3 required).
