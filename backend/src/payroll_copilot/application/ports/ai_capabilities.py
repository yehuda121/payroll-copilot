"""Strongly typed AI capabilities used for provider routing."""

from __future__ import annotations

from enum import StrEnum


class AICapability(StrEnum):
    PAYSLIP_EXTRACTION = "payslip_extraction"
    DOCUMENT_EXTRACTION = "document_extraction"
    ASSISTANT = "assistant"
    EMPLOYEE_CHAT = "employee_chat"
    ACCOUNTANT_CHAT = "accountant_chat"
    RAG = "rag"
    EMBEDDINGS = "embeddings"
    GENERAL = "general"
