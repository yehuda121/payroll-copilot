"""AI agent implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from payroll_copilot.application.ports import Message, ModelProvider


@dataclass
class AgentOutput:
    data: dict[str, Any]
    confidence: float
    agent_name: str


class BaseAgent(ABC):
    """Base class for specialized AI agents."""

    name: str
    system_prompt_path: str

    def __init__(self, model_provider: ModelProvider, prompts_base: str = "config/prompts") -> None:
        self._model = model_provider
        self._prompts_base = Path(prompts_base)

    @abstractmethod
    async def run(self, input_data: dict[str, Any]) -> AgentOutput:
        pass

    def _load_system_prompt(self) -> str:
        path = self._prompts_base / self.system_prompt_path
        if path.exists():
            return path.read_text(encoding="utf-8")
        return f"You are the {self.name} agent for Payroll Copilot."

    async def _complete_structured(
        self,
        user_content: str,
        response_schema: type[BaseModel],
    ) -> AgentOutput:
        messages = [
            Message(role="system", content=self._load_system_prompt()),
            Message(role="user", content=user_content),
        ]
        result = await self._model.complete_structured(messages, response_schema)
        return AgentOutput(
            data=result.data.model_dump(),
            confidence=result.confidence,
            agent_name=self.name,
        )


class SplitPayslipResult(BaseModel):
    page_start: int
    page_end: int
    employee_number_hint: str | None = None
    employee_name_hint: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class PayslipSplitterOutput(BaseModel):
    splits: list[SplitPayslipResult]
    total_pages: int


class PayslipSplitterAgent(BaseAgent):
    """Segments bulk PDF into individual payslip documents."""

    name = "payslip_splitter"
    system_prompt_path = "payslip_splitter/system.md"

    async def run(self, input_data: dict[str, Any]) -> AgentOutput:
        page_count = input_data.get("page_count", 1)
        page_texts: list[str] = input_data.get("page_texts", [])

        preview = "\n---\n".join(
            f"Page {i + 1}:\n{text[:500]}" for i, text in enumerate(page_texts[:10])
        )
        prompt = (
            f"Analyze this payroll PDF with {page_count} pages.\n"
            f"Identify individual payslip boundaries.\n\n{preview}"
        )
        return await self._complete_structured(prompt, PayslipSplitterOutput)


class LeaveExtractionResult(BaseModel):
    leave_type: str = Field(description="vacation, sick_leave, or other")
    start_date: str = Field(description="ISO date YYYY-MM-DD")
    end_date: str = Field(description="ISO date YYYY-MM-DD")
    hours: float | None = None
    employee_email: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class VacationSickLeaveAgent(BaseAgent):
    """Extracts leave request details from email content."""

    name = "vacation_sick_leave"
    system_prompt_path = "vacation_sick_leave/system.md"

    async def run(self, input_data: dict[str, Any]) -> AgentOutput:
        subject = input_data.get("subject", "")
        body = input_data.get("body_text", "")
        from_email = input_data.get("from_email", "")

        prompt = (
            f"Extract leave request details from this email.\n"
            f"From: {from_email}\nSubject: {subject}\n\n{body}"
        )
        return await self._complete_structured(prompt, LeaveExtractionResult)


class ComplianceExplanation(BaseModel):
    summary: str
    recommendations: list[str]
    legal_context: str
    confidence: float = Field(ge=0.0, le=1.0)


class ComplianceExplainerAgent(BaseAgent):
    """Generates human-readable explanations for validation findings."""

    name = "compliance_explainer"
    system_prompt_path = "compliance_explainer/system.md"

    async def run(self, input_data: dict[str, Any]) -> AgentOutput:
        findings = input_data.get("findings", [])
        locale = input_data.get("locale", "he")
        prompt = (
            f"Explain these payroll validation findings in {locale}.\n"
            f"Findings: {findings}\n\n"
            "Provide summary, recommendations, and legal context. "
            "This is explanatory only — do not change validation results."
        )
        return await self._complete_structured(prompt, ComplianceExplanation)


class AgentRegistry:
    """Registry for AI agent lookup."""

    def __init__(self, model_provider: ModelProvider) -> None:
        self._agents: dict[str, BaseAgent] = {
            "payslip_splitter": PayslipSplitterAgent(model_provider),
            "vacation_sick_leave": VacationSickLeaveAgent(model_provider),
            "compliance_explainer": ComplianceExplainerAgent(model_provider),
        }

    def get(self, name: str) -> BaseAgent:
        agent = self._agents.get(name)
        if agent is None:
            msg = f"Unknown agent: {name}"
            raise ValueError(msg)
        return agent

    def list_agents(self) -> list[str]:
        return list(self._agents.keys())
