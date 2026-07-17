"""Port interfaces (dependency inversion)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel

from payroll_copilot.application.ports.ocr import OCRProvider, OCRResult, OcrLine, OcrPage
from payroll_copilot.application.ports.email import (
    EmailAddress,
    EmailDeliveryError,
    EmailMessage,
    EmailSendResult,
    EmailService,
)

__all__ = [
    "CompletionResult",
    "EmailAddress",
    "EmailDeliveryError",
    "EmailMessage",
    "EmailSendResult",
    "EmailService",
    "LegalRulesLoader",
    "Message",
    "ModelProvider",
    "ObjectStorage",
    "OCRProvider",
    "OCRResult",
    "OcrLine",
    "OcrPage",
    "RAGChunk",
    "RAGRetriever",
    "StructuredResult",
]


@dataclass
class Message:
    role: str
    content: str


@dataclass
class CompletionResult:
    content: str
    confidence: float
    model: str
    tokens_used: int = 0


@dataclass
class StructuredResult:
    data: BaseModel
    confidence: float
    model: str


@runtime_checkable
class ModelProvider(Protocol):
    """Abstraction for LLM providers (Amazon Bedrock, Ollama, etc.)."""

    @property
    def embedding_dimensions(self) -> int: ...

    async def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> CompletionResult: ...

    async def complete_structured(
        self,
        messages: list[Message],
        response_schema: type[BaseModel],
    ) -> StructuredResult: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class ObjectStorage(Protocol):
    """Abstraction for S3/MinIO file storage."""

    async def upload(self, key: str, data: bytes, content_type: str) -> str: ...

    async def download(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...

    async def generate_presigned_url(self, key: str, expires_seconds: int = 300) -> str: ...


@runtime_checkable
class RAGRetriever(Protocol):
    """Abstraction for RAG document retrieval."""

    async def ingest(
        self,
        organization_id: UUID,
        document_id: UUID,
        content: str,
        metadata: dict[str, Any],
    ) -> int: ...

    async def search(
        self,
        organization_id: UUID,
        query: str,
        *,
        employee_id: UUID | None = None,
        top_k: int = 5,
    ) -> list[RAGChunk]: ...


@dataclass
class RAGChunk:
    content: str
    score: float
    metadata: dict[str, Any]


class LegalRulesLoader(ABC):
    """Loads and caches YAML legal rules."""

    @abstractmethod
    def load_all(self) -> dict[str, Any]: ...

    @abstractmethod
    def get_file_hash(self, filename: str) -> str: ...

    @abstractmethod
    def reload(self) -> None: ...
