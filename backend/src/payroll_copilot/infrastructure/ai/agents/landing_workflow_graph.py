"""LangGraph orchestration for the public landing-page workflow.

Graph owns routing only. Business logic lives in injected services/use cases.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, TypedDict
from uuid import UUID, uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from payroll_copilot.application.exceptions import (
    DocumentUploadRejectedError,
    OcrError,
    PayslipParserError,
)
from payroll_copilot.application.services.landing_file_guardrail import (
    LandingFileGuardrailService,
    LandingFilePayload,
)
from payroll_copilot.application.services.landing_session_memory import (
    LandingChatTurn,
    LandingSessionMemoryStore,
    get_landing_session_memory_store,
)
from payroll_copilot.application.use_cases.correct_guest_extraction import (
    CorrectGuestExtractionUseCase,
    FieldCorrection,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import (
    ExtractGuestPayslipCommand,
    ExtractGuestPayslipUseCase,
)
from payroll_copilot.application.use_cases.payroll_assistant import (
    AssistantChatCommand,
    PayrollAssistantChatUseCase,
)
from payroll_copilot.application.use_cases.persisted_validation import (
    RunPersistedValidationCommand,
    RunPersistedValidationUseCase,
)
from payroll_copilot.domain.assistant.types import AssistantGuardrailStatus
from payroll_copilot.infrastructure.ai.agents.validation_report_store import cache_validation_report
from payroll_copilot.infrastructure.ai.guardrails.payroll_assistant_guardrails import (
    PayrollAssistantGuardrails,
)
from payroll_copilot.infrastructure.i18n import finding_explanation, finding_message

logger = logging.getLogger(__name__)

INSUFFICIENT_INFO = "I don't have enough verified information."


class LandingWorkflowState(TypedDict, total=False):
    session_id: str
    locale: str
    message: str
    files: list[dict[str, Any]]
    intent: str
    route: str
    guardrail_status: str
    rejected: bool
    reject_reason: str
    document_id: str | None
    extraction_id: str | None
    document_ids: list[str]
    extracted_fields: list[dict[str, Any]]
    confirmed_fields: list[dict[str, Any]]
    validation_run_id: str | None
    validation_report: dict[str, Any] | None
    field_statuses: list[dict[str, Any]]
    answer: str
    sources: list[dict[str, str | None]]
    phase: str
    used_nodes: list[str]
    explain_finding_id: str | None
    explain_rule_id: str | None
    confidence: float
    requires_human_review: bool
    interrupt_payload: dict[str, Any] | None


class LandingWorkflowGraph:
    """Full landing workflow: guardrails → RAG/OCR → review interrupt → validation → response."""

    def __init__(
        self,
        *,
        file_guardrails: LandingFileGuardrailService,
        extract_guest: ExtractGuestPayslipUseCase,
        correct_guest: CorrectGuestExtractionUseCase,
        run_validation: RunPersistedValidationUseCase,
        assistant: PayrollAssistantChatUseCase,
        input_guardrails: PayrollAssistantGuardrails | None = None,
        memory: LandingSessionMemoryStore | None = None,
        checkpointer: MemorySaver | None = None,
    ) -> None:
        self._file_guardrails = file_guardrails
        self._extract_guest = extract_guest
        self._correct_guest = correct_guest
        self._run_validation = run_validation
        self._assistant = assistant
        self._input_guardrails = input_guardrails or PayrollAssistantGuardrails()
        self._memory = memory or get_landing_session_memory_store()
        self._checkpointer = checkpointer or MemorySaver()
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        graph: StateGraph = StateGraph(LandingWorkflowState)
        graph.add_node("input_guardrails", self._node_input_guardrails)
        graph.add_node("file_guardrails", self._node_file_guardrails)
        graph.add_node("rag_question_decision", self._node_rag_question_decision)
        graph.add_node("ocr", self._node_ocr)
        graph.add_node("extraction", self._node_extraction)
        graph.add_node("human_review", self._node_human_review)
        graph.add_node("deterministic_validation", self._node_deterministic_validation)
        graph.add_node("ai_explanation", self._node_ai_explanation)
        graph.add_node("final_response", self._node_final_response)
        graph.add_node("rag_answer", self._node_rag_answer)
        graph.add_node("explain_finding", self._node_explain_finding)

        graph.add_edge(START, "input_guardrails")
        graph.add_conditional_edges(
            "input_guardrails",
            self._route_after_input,
            {
                "blocked": "final_response",
                "files": "file_guardrails",
                "continue": "rag_question_decision",
            },
        )
        graph.add_conditional_edges(
            "file_guardrails",
            self._route_after_files,
            {
                "blocked": "final_response",
                "process": "ocr",
                "continue": "rag_question_decision",
            },
        )
        graph.add_conditional_edges(
            "rag_question_decision",
            self._route_after_decision,
            {
                "document": "ocr",
                "question": "rag_answer",
                "explain": "explain_finding",
                "final": "final_response",
            },
        )
        graph.add_edge("ocr", "extraction")
        graph.add_edge("extraction", "human_review")
        graph.add_edge("human_review", "deterministic_validation")
        graph.add_edge("deterministic_validation", "ai_explanation")
        graph.add_edge("ai_explanation", "final_response")
        graph.add_edge("rag_answer", "final_response")
        graph.add_edge("explain_finding", "final_response")
        graph.add_edge("final_response", END)
        return graph.compile(checkpointer=self._checkpointer)

    async def run_turn(
        self,
        *,
        session_id: str | None,
        message: str,
        files: list[LandingFilePayload],
        locale: str,
        explain_finding_id: str | None = None,
        explain_rule_id: str | None = None,
    ) -> dict[str, Any]:
        memory = self._memory.get_or_create(session_id, locale=locale)
        if message.strip():
            memory.turns.append(LandingChatTurn(role="user", content=message.strip()))
            self._memory.save(memory)

        initial: LandingWorkflowState = {
            "session_id": memory.session_id,
            "locale": locale,
            "message": message or "",
            "files": [
                {
                    "filename": f.filename,
                    "content": f.content,
                    "mime_type": f.mime_type,
                }
                for f in files
            ],
            "intent": "",
            "route": "",
            "guardrail_status": AssistantGuardrailStatus.PASSED.value,
            "rejected": False,
            "reject_reason": "",
            "document_id": memory.payslip_document_id,
            "extraction_id": None,
            "document_ids": list(memory.document_ids),
            "extracted_fields": list(memory.extracted_fields),
            "confirmed_fields": list(memory.confirmed_fields),
            "validation_run_id": memory.validation_run_id,
            "validation_report": memory.validation_report,
            "field_statuses": list(memory.field_statuses),
            "answer": "",
            "sources": [],
            "phase": "chat",
            "used_nodes": [],
            "explain_finding_id": explain_finding_id,
            "explain_rule_id": explain_rule_id,
            "confidence": 0.0,
            "requires_human_review": False,
            "interrupt_payload": None,
        }
        config = {"configurable": {"thread_id": memory.session_id}}
        result = await self._graph.ainvoke(initial, config)
        return self._normalize_result(result, memory.session_id)

    async def resume_review(
        self,
        *,
        session_id: str,
        confirmed_fields: list[dict[str, Any]],
        locale: str | None = None,
    ) -> dict[str, Any]:
        memory = self._memory.get(session_id)
        if memory is None:
            return {
                "session_id": session_id,
                "phase": "blocked",
                "answer": "Session expired. Refreshing the page starts a new ephemeral session.",
                "rejected": True,
                "guardrail_status": AssistantGuardrailStatus.BLOCKED.value,
                "sources": [],
                "extracted_fields": [],
                "field_statuses": [],
                "validation_report": None,
                "document_id": None,
                "validation_run_id": None,
                "interrupt_payload": None,
                "used_nodes": [],
                "confidence": 0.0,
                "requires_human_review": False,
            }

        if locale:
            memory.locale = locale
        memory.turns.append(
            LandingChatTurn(role="user", content="Confirm extracted payroll fields", kind="confirm")
        )
        memory.confirmed_fields = confirmed_fields
        self._memory.save(memory)

        config = {"configurable": {"thread_id": session_id}}
        result = await self._graph.ainvoke(
            Command(resume={"confirmed": True, "fields": confirmed_fields}),
            config,
        )
        return self._normalize_result(result, session_id)

    def _normalize_result(self, result: dict[str, Any], session_id: str) -> dict[str, Any]:
        interrupts = result.get("__interrupt__") or []
        interrupt_payload = None
        phase = str(result.get("phase") or "chat")
        if interrupts:
            first = interrupts[0]
            interrupt_payload = getattr(first, "value", first)
            if isinstance(interrupt_payload, dict):
                phase = "awaiting_review"
            result = {**result, "phase": phase, "interrupt_payload": interrupt_payload}

        memory = self._memory.get_or_create(session_id, locale=str(result.get("locale") or "en"))
        answer = str(result.get("answer") or "")
        if answer and phase != "awaiting_review":
            memory.turns.append(
                LandingChatTurn(
                    role="assistant",
                    content=answer,
                    kind=phase,
                    meta={
                        "guardrail_status": result.get("guardrail_status"),
                        "sources": result.get("sources") or [],
                    },
                )
            )
        elif phase == "awaiting_review":
            memory.turns.append(
                LandingChatTurn(
                    role="assistant",
                    content=str(
                        (interrupt_payload or {}).get("message")
                        or "Review the extracted payroll form, then press Confirm."
                    ),
                    kind="document_review",
                    meta={"document_id": result.get("document_id")},
                )
            )

        if result.get("document_id"):
            memory.payslip_document_id = str(result["document_id"])
            if memory.payslip_document_id not in memory.document_ids:
                memory.document_ids.append(memory.payslip_document_id)
        if result.get("extracted_fields"):
            memory.extracted_fields = list(result["extracted_fields"])
        if result.get("confirmed_fields"):
            memory.confirmed_fields = list(result["confirmed_fields"])
        if result.get("validation_run_id"):
            memory.validation_run_id = str(result["validation_run_id"])
        if result.get("validation_report") is not None:
            memory.validation_report = dict(result["validation_report"])
        if result.get("field_statuses"):
            memory.field_statuses = list(result["field_statuses"])
        self._memory.save(memory)

        return {
            "session_id": session_id,
            "phase": phase,
            "answer": answer
            if phase != "awaiting_review"
            else str(
                (interrupt_payload or {}).get("message")
                or "Review the extracted payroll form, then press Confirm."
            ),
            "rejected": bool(result.get("rejected")),
            "guardrail_status": str(
                result.get("guardrail_status") or AssistantGuardrailStatus.PASSED.value
            ),
            "sources": list(result.get("sources") or []),
            "extracted_fields": list(result.get("extracted_fields") or []),
            "field_statuses": list(result.get("field_statuses") or []),
            "validation_report": result.get("validation_report"),
            "document_id": result.get("document_id"),
            "extraction_id": result.get("extraction_id"),
            "validation_run_id": result.get("validation_run_id"),
            "interrupt_payload": interrupt_payload,
            "used_nodes": list(result.get("used_nodes") or []),
            "confidence": float(result.get("confidence") or 0.0),
            "requires_human_review": bool(result.get("requires_human_review")),
            "locale": memory.locale,
        }

    # ── Nodes (orchestration only) ──────────────────────────────────────

    def _node_input_guardrails(self, state: LandingWorkflowState) -> LandingWorkflowState:
        used = [*state.get("used_nodes", []), "input_guardrails"]
        message = (state.get("message") or "").strip()
        files = state.get("files") or []
        explain_id = state.get("explain_finding_id")
        explain_rule = state.get("explain_rule_id")

        if explain_id or explain_rule:
            return {
                **state,
                "used_nodes": used,
                "intent": "explain",
                "route": "explain",
                "rejected": False,
                "guardrail_status": AssistantGuardrailStatus.PASSED.value,
            }

        if not message and not files:
            return {
                **state,
                "used_nodes": used,
                "rejected": True,
                "reject_reason": "Empty request.",
                "answer": "Please enter a payroll question or attach a PDF.",
                "phase": "blocked",
                "guardrail_status": AssistantGuardrailStatus.BLOCKED.value,
                "route": "blocked",
            }

        if len(message) > 4000:
            return {
                **state,
                "used_nodes": used,
                "rejected": True,
                "reject_reason": "Input too large.",
                "answer": "Your message is too long. Please shorten it and try again.",
                "phase": "blocked",
                "guardrail_status": AssistantGuardrailStatus.BLOCKED.value,
                "route": "blocked",
            }

        if message:
            result = self._input_guardrails.evaluate_input(message)
            if result.status not in {AssistantGuardrailStatus.PASSED}:
                blocked = self._input_guardrails.build_blocked_response(
                    result.reason or "blocked",
                    locale=state.get("locale") or "en",
                )
                return {
                    **state,
                    "used_nodes": used,
                    "rejected": True,
                    "reject_reason": result.reason or "blocked",
                    "answer": blocked.answer,
                    "phase": "blocked",
                    "guardrail_status": blocked.status.value,
                    "requires_human_review": blocked.requires_human_review,
                    "route": "blocked",
                }

        return {
            **state,
            "used_nodes": used,
            "rejected": False,
            "guardrail_status": AssistantGuardrailStatus.PASSED.value,
            "route": "files" if files else "continue",
            "intent": "document" if files else "question",
        }

    def _route_after_input(
        self, state: LandingWorkflowState
    ) -> Literal["blocked", "files", "continue"]:
        if state.get("rejected") or state.get("route") == "blocked":
            return "blocked"
        if state.get("route") == "files" or (state.get("files") or []):
            return "files"
        return "continue"

    def _node_file_guardrails(self, state: LandingWorkflowState) -> LandingWorkflowState:
        used = [*state.get("used_nodes", []), "file_guardrails"]
        memory = self._memory.get_or_create(state["session_id"], locale=state.get("locale") or "en")
        raw_files = state.get("files") or []
        payloads = [
            LandingFilePayload(
                filename=str(item.get("filename") or "document.pdf"),
                content=bytes(item.get("content") or b""),
                mime_type=str(item.get("mime_type") or "application/pdf"),
            )
            for item in raw_files
        ]
        try:
            result = self._file_guardrails.validate(
                payloads,
                existing_filenames=set(memory.uploaded_filenames),
                existing_hashes=set(memory.uploaded_hashes),
            )
        except DocumentUploadRejectedError as exc:
            return {
                **state,
                "used_nodes": used,
                "rejected": True,
                "reject_reason": str(exc),
                "answer": str(exc),
                "phase": "blocked",
                "guardrail_status": AssistantGuardrailStatus.BLOCKED.value,
                "route": "blocked",
            }

        memory.uploaded_filenames.extend(f.filename for f in result.accepted)
        memory.uploaded_hashes.extend(result.content_hashes)
        self._memory.save(memory)

        return {
            **state,
            "used_nodes": used,
            "files": [
                {
                    "filename": f.filename,
                    "content": f.content,
                    "mime_type": f.mime_type,
                }
                for f in result.accepted
            ],
            "route": "process" if result.accepted else "continue",
            "intent": "document" if result.accepted else state.get("intent") or "question",
            "rejected": False,
        }

    def _route_after_files(
        self, state: LandingWorkflowState
    ) -> Literal["blocked", "process", "continue"]:
        if state.get("rejected") or state.get("route") == "blocked":
            return "blocked"
        if state.get("route") == "process":
            return "process"
        return "continue"

    def _node_rag_question_decision(self, state: LandingWorkflowState) -> LandingWorkflowState:
        used = [*state.get("used_nodes", []), "rag_question_decision"]
        if state.get("explain_finding_id") or state.get("explain_rule_id"):
            return {**state, "used_nodes": used, "route": "explain", "intent": "explain"}
        if state.get("files"):
            return {**state, "used_nodes": used, "route": "document", "intent": "document"}
        if (state.get("message") or "").strip():
            return {**state, "used_nodes": used, "route": "question", "intent": "question"}
        return {
            **state,
            "used_nodes": used,
            "route": "final",
            "answer": "Please enter a payroll question or attach a PDF.",
            "phase": "blocked",
        }

    def _route_after_decision(
        self, state: LandingWorkflowState
    ) -> Literal["document", "question", "explain", "final"]:
        route = state.get("route") or "final"
        if route in {"document", "question", "explain", "final"}:
            return route  # type: ignore[return-value]
        return "final"

    async def _node_ocr(self, state: LandingWorkflowState) -> LandingWorkflowState:
        """OCR stage — performed as the first half of guest extraction (single responsibility entry)."""
        used = [*state.get("used_nodes", []), "ocr"]
        files = state.get("files") or []
        if not files:
            return {
                **state,
                "used_nodes": used,
                "rejected": True,
                "answer": "No PDF available for OCR.",
                "phase": "blocked",
                "route": "blocked",
            }
        # OCR bytes are processed in the extraction node via ExtractGuestPayslipUseCase
        # which owns the OCR→parse pipeline; this node records the OCR stage boundary.
        return {
            **state,
            "used_nodes": used,
            "phase": "ocr",
            "answer": "",
        }

    async def _node_extraction(self, state: LandingWorkflowState) -> LandingWorkflowState:
        used = [*state.get("used_nodes", []), "extraction"]
        files = state.get("files") or []
        if not files:
            return {
                **state,
                "used_nodes": used,
                "rejected": True,
                "answer": "No PDF available for extraction.",
                "phase": "blocked",
            }

        primary = files[0]
        try:
            result = await self._extract_guest.execute(
                ExtractGuestPayslipCommand(
                    content=bytes(primary["content"]),
                    original_filename=str(primary["filename"]),
                    mime_type=str(primary.get("mime_type") or "application/pdf"),
                    language="auto",
                    ephemeral=True,
                )
            )
        except (OcrError, PayslipParserError) as exc:
            return {
                **state,
                "used_nodes": used,
                "rejected": True,
                "answer": str(exc),
                "phase": "blocked",
                "guardrail_status": AssistantGuardrailStatus.BLOCKED.value,
            }
        except Exception as exc:  # noqa: BLE001 — surface extraction failures to the chat
            logger.exception("Landing extraction failed")
            return {
                **state,
                "used_nodes": used,
                "rejected": True,
                "answer": f"Document processing failed: {exc}",
                "phase": "blocked",
                "guardrail_status": AssistantGuardrailStatus.BLOCKED.value,
            }

        fields = [
            {
                "key": field.key,
                "value": field.value,
                "confidence": field.confidence,
                "source_text": field.source_text,
                "status": field.status,
                "edited_by_user": field.edited_by_user,
                "original_value": field.original_value,
            }
            for field in result.fields
        ]

        # Store additional PDFs as supporting docs when present.
        from payroll_copilot.application.services.guest_ephemeral_store import (
            get_guest_ephemeral_store,
        )
        from payroll_copilot.domain.enums import DocumentType

        store = get_guest_ephemeral_store()
        document_ids = [str(result.document_id)]
        for extra in files[1:]:
            support = store.save_supporting(
                document_type=DocumentType.CONTRACT,
                content=bytes(extra["content"]),
                original_filename=str(extra["filename"]),
                mime_type=str(extra.get("mime_type") or "application/pdf"),
                payslip_document_id=result.document_id,
            )
            document_ids.append(str(support.document_id))

        return {
            **state,
            "used_nodes": used,
            "document_id": str(result.document_id),
            "extraction_id": str(result.extraction_id),
            "document_ids": document_ids,
            "extracted_fields": fields,
            "phase": "review",
            "answer": "",
            "requires_human_review": True,
        }

    async def _node_human_review(self, state: LandingWorkflowState) -> LandingWorkflowState:
        used = [*state.get("used_nodes", []), "human_review"]
        resume_value = interrupt(
            {
                "type": "human_review",
                "document_id": state.get("document_id"),
                "extraction_id": state.get("extraction_id"),
                "fields": state.get("extracted_fields") or [],
                "message": "Review the extracted payroll form. Edit any incorrect fields, then press Confirm.",
            }
        )
        fields = state.get("extracted_fields") or []
        if isinstance(resume_value, dict):
            fields = list(resume_value.get("fields") or fields)

        document_id = state.get("document_id")
        extraction_id = state.get("extraction_id")
        if document_id:
            corrections = [
                FieldCorrection(
                    key=str(field.get("key") or ""),
                    value=field.get("value"),
                    clear=bool(field.get("clear"))
                    or field.get("value") in (None, ""),
                )
                for field in fields
                if field.get("key")
            ]
            if corrections:
                corrected = await self._correct_guest.execute(
                    document_id=UUID(document_id),
                    corrections=corrections,
                )
                extraction_id = str(corrected.extraction_id)
                fields = [
                    {
                        "key": item.get("key"),
                        "value": item.get("value"),
                        "confidence": item.get("confidence"),
                        "source_text": item.get("source_text"),
                        "status": item.get("status"),
                        "edited_by_user": item.get("edited_by_user", True),
                        "original_value": item.get("original_value"),
                    }
                    for item in corrected.fields
                ]
            self._extract_guest.confirm_ephemeral_session(UUID(document_id))

        return {
            **state,
            "used_nodes": used,
            "confirmed_fields": fields,
            "extracted_fields": fields,
            "extraction_id": extraction_id,
            "phase": "confirmed",
            "requires_human_review": False,
        }

    async def _node_deterministic_validation(
        self, state: LandingWorkflowState
    ) -> LandingWorkflowState:
        used = [*state.get("used_nodes", []), "deterministic_validation"]
        document_id = state.get("document_id")
        if not document_id:
            return {
                **state,
                "used_nodes": used,
                "rejected": True,
                "answer": "Cannot validate without an extracted document.",
                "phase": "blocked",
            }

        support_ids = [
            UUID(doc_id)
            for doc_id in (state.get("document_ids") or [])
            if doc_id != document_id
        ]
        record = await self._run_validation.execute(
            RunPersistedValidationCommand(
                document_id=UUID(document_id),
                supporting_document_ids=tuple(support_ids),
                locale=state.get("locale"),
                extraction_id=UUID(state["extraction_id"]) if state.get("extraction_id") else None,
            )
        )

        report = self._serialize_validation_report(record, locale=state.get("locale") or "en")
        field_statuses = self._build_field_statuses(
            extracted_fields=state.get("confirmed_fields") or state.get("extracted_fields") or [],
            report=report,
        )
        cache_validation_report(
            str(record.id),
            {
                "status": record.status.value
                if hasattr(record.status, "value")
                else str(record.status),
                "overall_result": report.get("overall_result"),
                "findings": report.get("findings") or [],
            },
        )

        return {
            **state,
            "used_nodes": used,
            "validation_run_id": str(record.id),
            "validation_report": report,
            "field_statuses": field_statuses,
            "phase": "validated",
        }

    async def _node_ai_explanation(self, state: LandingWorkflowState) -> LandingWorkflowState:
        used = [*state.get("used_nodes", []), "ai_explanation"]
        report = state.get("validation_report") or {}
        findings = report.get("findings") or []
        if not findings:
            summary = (
                "Deterministic validation completed with no findings. "
                "Overall status: "
                f"{report.get('overall_result') or report.get('overall_status') or 'pass'}."
            )
            return {
                **state,
                "used_nodes": used,
                "answer": summary,
                "sources": [],
                "phase": "validated",
            }

        # Ask assistant to explain using RAG tools only — never invent legality.
        prompt = (
            "Explain the deterministic validation findings below using only approved "
            "labor-law sources and the validation report. Do not decide pass/fail.\n\n"
            f"Validation run: {state.get('validation_run_id')}\n"
            f"Findings: {findings[:8]}"
        )
        assistant_result = await self._assistant.execute(
            AssistantChatCommand(
                message=prompt,
                session_id=state["session_id"],
                document_ids=state.get("document_ids") or [],
                validation_run_id=state.get("validation_run_id"),
                locale=state.get("locale") or "en",
            )
        )
        return {
            **state,
            "used_nodes": used,
            "answer": assistant_result.answer,
            "sources": assistant_result.sources,
            "guardrail_status": assistant_result.guardrail_status,
            "confidence": assistant_result.confidence,
            "requires_human_review": assistant_result.requires_human_review,
            "phase": "validated",
        }

    async def _node_rag_answer(self, state: LandingWorkflowState) -> LandingWorkflowState:
        used = [*state.get("used_nodes", []), "rag_answer"]
        memory = self._memory.get_or_create(state["session_id"], locale=state.get("locale") or "en")
        history_bits = []
        for turn in memory.turns[-8:]:
            history_bits.append(f"{turn.role}: {turn.content}")
        if memory.extracted_fields:
            history_bits.append(f"Extracted fields in session: {memory.extracted_fields[:20]}")
        if memory.validation_report:
            history_bits.append(
                f"Prior validation overall: {memory.validation_report.get('overall_result')}"
            )

        enriched = state.get("message") or ""
        if history_bits:
            enriched = (
                f"{enriched}\n\n[Ephemeral session memory — do not invent documents]\n"
                + "\n".join(history_bits)
            )

        result = await self._assistant.execute(
            AssistantChatCommand(
                message=enriched,
                session_id=state["session_id"],
                document_ids=memory.document_ids or state.get("document_ids") or [],
                validation_run_id=memory.validation_run_id or state.get("validation_run_id"),
                locale=state.get("locale") or "en",
            )
        )

        answer = result.answer
        # Enforce no-hallucination contract for legal answers without sources.
        if (
            result.guardrail_status
            in {
                AssistantGuardrailStatus.LIMITED.value,
                AssistantGuardrailStatus.LIMITED_IN_DOMAIN.value,
            }
            and not result.sources
        ):
            answer = INSUFFICIENT_INFO

        return {
            **state,
            "used_nodes": used,
            "answer": answer,
            "sources": result.sources,
            "guardrail_status": result.guardrail_status,
            "confidence": result.confidence,
            "requires_human_review": result.requires_human_review,
            "phase": "chat",
        }

    async def _node_explain_finding(self, state: LandingWorkflowState) -> LandingWorkflowState:
        used = [*state.get("used_nodes", []), "explain_finding"]
        rule_id = state.get("explain_rule_id")
        finding_id = state.get("explain_finding_id")
        run_id = state.get("validation_run_id")
        message = (
            f"Explain validation finding {finding_id or ''} "
            f"rule_id {rule_id or ''} from validation run {run_id or ''}. "
            "Use approved labor-law sources only. Include why it failed, "
            "the relevant payroll law, the retrieved source, and a possible fix."
        )
        result = await self._assistant.execute(
            AssistantChatCommand(
                message=message,
                session_id=state["session_id"],
                document_ids=state.get("document_ids") or [],
                validation_run_id=run_id,
                locale=state.get("locale") or "en",
            )
        )
        answer = result.answer
        if not result.sources:
            answer = INSUFFICIENT_INFO
        return {
            **state,
            "used_nodes": used,
            "answer": answer,
            "sources": result.sources,
            "guardrail_status": result.guardrail_status,
            "confidence": result.confidence,
            "phase": "chat",
        }

    def _node_final_response(self, state: LandingWorkflowState) -> LandingWorkflowState:
        used = [*state.get("used_nodes", []), "final_response"]
        if state.get("answer"):
            return {**state, "used_nodes": used}
        phase = state.get("phase") or "chat"
        if phase == "validated" and state.get("validation_report"):
            overall = state["validation_report"].get("overall_result") or "unknown"
            return {
                **state,
                "used_nodes": used,
                "answer": f"Validation complete. Overall result: {overall}.",
                "phase": "validated",
            }
        return {
            **state,
            "used_nodes": used,
            "answer": state.get("reject_reason") or INSUFFICIENT_INFO,
            "phase": state.get("phase") or "chat",
        }

    @staticmethod
    def _serialize_validation_report(record: Any, *, locale: str) -> dict[str, Any]:
        findings = []
        for finding in record.findings or []:
            severity = (
                finding.severity.value if hasattr(finding.severity, "value") else str(finding.severity)
            )
            findings.append(
                {
                    "id": str(finding.id),
                    "code": finding.rule_id,
                    "rule_id": finding.rule_id,
                    "severity": severity,
                    "message_key": finding.message_key,
                    "message": finding_message(finding.message_key, locale)
                    if finding.message_key
                    else finding.message_key,
                    "explanation": finding_explanation(finding.message_key, locale)
                    if finding.message_key
                    else "",
                    "expected_value": finding.expected_value,
                    "actual_value": finding.actual_value,
                    "confidence": float(finding.confidence)
                    if finding.confidence is not None
                    else 0.0,
                    "legal_reference": finding.legal_reference,
                    "status": LandingWorkflowGraph._severity_to_status(severity),
                }
            )

        enrichment = getattr(record, "enrichment", None)
        scope = []
        if enrichment is not None:
            for item in getattr(enrichment, "validation_scope", []) or []:
                status_raw = getattr(item, "status", None) or (
                    item.get("status") if isinstance(item, dict) else None
                )
                scope.append(
                    {
                        "key": getattr(item, "key", None) or item.get("key"),
                        "label": getattr(item, "label", None) or item.get("label"),
                        "status": status_raw,
                        "reason": getattr(item, "reason", None)
                        if not isinstance(item, dict)
                        else item.get("reason"),
                        "field_status": LandingWorkflowGraph._scope_to_field_status(str(status_raw or "")),
                    }
                )

        overall = (
            record.overall_result.value
            if hasattr(record.overall_result, "value")
            else record.overall_result
        )
        return {
            "id": str(record.id),
            "document_id": str(record.document_id),
            "status": record.status.value if hasattr(record.status, "value") else str(record.status),
            "overall_result": overall,
            "overall_status": overall,
            "overall_confidence": float(record.overall_confidence)
            if record.overall_confidence is not None
            else None,
            "rules_evaluated": record.rules_evaluated,
            "rules_failed": record.rules_failed,
            "findings": findings,
            "validation_scope": scope,
            "summary": f"Deterministic validation finished with overall result '{overall}'.",
        }

    @staticmethod
    def _severity_to_status(severity: str) -> str:
        s = (severity or "").lower()
        if s in {"critical", "failed", "error", "fail"}:
            return "FAILED"
        if s in {"warning", "warnings", "warn"}:
            return "WARNING"
        if s in {"pass", "passed", "info", "ok"}:
            return "PASS"
        return "UNKNOWN"

    @staticmethod
    def _scope_to_field_status(status: str) -> str:
        s = (status or "").lower()
        if s in {"completed", "pass", "passed"}:
            return "PASS"
        if s in {"partial", "warning"}:
            return "WARNING"
        if s in {"failed", "critical"}:
            return "FAILED"
        return "UNKNOWN"

    @staticmethod
    def _build_field_statuses(
        *,
        extracted_fields: list[dict[str, Any]],
        report: dict[str, Any],
    ) -> list[dict[str, Any]]:
        by_key: dict[str, str] = {}
        for field in extracted_fields:
            key = str(field.get("key") or "")
            if not key:
                continue
            by_key[key] = "UNKNOWN"

        for finding in report.get("findings") or []:
            status = finding.get("status") or LandingWorkflowGraph._severity_to_status(
                str(finding.get("severity") or "")
            )
            rule = str(finding.get("rule_id") or "")
            hint = rule.split(".")[-1] if rule else ""
            matched = False
            for key in list(by_key):
                if hint and hint in key:
                    by_key[key] = status
                    matched = True
            if not matched and hint:
                by_key[hint] = status

        for scope in report.get("validation_scope") or []:
            key = str(scope.get("key") or "")
            if key:
                by_key[key] = scope.get("field_status") or "UNKNOWN"

        # Fields still unmarked after a clean pass become PASS.
        overall = str(report.get("overall_result") or "").lower()
        if overall == "pass":
            for key, status in list(by_key.items()):
                if status == "UNKNOWN" and key in {f.get("key") for f in extracted_fields}:
                    # Keep unknown for fields without evidence; only mark found values PASS.
                    field = next((f for f in extracted_fields if f.get("key") == key), None)
                    if field and field.get("value") not in (None, ""):
                        by_key[key] = "PASS"

        return [{"key": key, "status": status} for key, status in by_key.items()]
