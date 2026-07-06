"""Ollama model provider implementation."""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel

from payroll_copilot.application.ports import CompletionResult, Message, StructuredResult


class OllamaProvider:
    """Local LLM provider via Ollama API."""

    EMBEDDING_DIMENSIONS = 768

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_model: str = "llama3.1:8b",
        embedding_model: str = "nomic-embed-text",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._embedding_model = embedding_model

    @property
    def embedding_dimensions(self) -> int:
        return self.EMBEDDING_DIMENSIONS

    async def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> CompletionResult:
        payload = {
            "model": self._default_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(f"{self._base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

        content = data.get("message", {}).get("content", "")
        eval_count = data.get("eval_count", 0)
        return CompletionResult(
            content=content,
            confidence=0.85 if content else 0.0,
            model=self._default_model,
            tokens_used=eval_count,
        )

    async def complete_structured(
        self,
        messages: list[Message],
        response_schema: type[BaseModel],
        *,
        temperature: float = 0.0,
    ) -> StructuredResult:
        schema_json = json.dumps(response_schema.model_json_schema(), indent=2)
        structured_messages = [
            *messages,
            Message(
                role="system",
                content=(
                    f"Respond ONLY with valid JSON matching this schema:\n{schema_json}\n"
                    "No markdown, no explanation, JSON only."
                ),
            ),
        ]
        result = await self.complete(structured_messages, temperature=temperature)
        parsed = self._parse_json_response(result.content)
        validated = response_schema.model_validate(parsed)
        confidence = 0.9 if parsed else 0.0
        return StructuredResult(data=validated, confidence=confidence, model=result.model)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        async with httpx.AsyncClient(timeout=60.0) as client:
            for text in texts:
                response = await client.post(
                    f"{self._base_url}/api/embeddings",
                    json={"model": self._embedding_model, "prompt": text},
                )
                response.raise_for_status()
                data = response.json()
                embeddings.append(data.get("embedding", []))
        return embeddings

    @staticmethod
    def _parse_json_response(content: str) -> dict[str, Any]:
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(content)


def create_model_provider(provider_name: str, settings: Any) -> OllamaProvider:
    """Factory for model providers. Extend for OpenAI, Claude, etc."""
    if provider_name == "ollama":
        from payroll_copilot.infrastructure.config.ollama_resolver import get_resolved_ollama_base_url

        return OllamaProvider(
            base_url=get_resolved_ollama_base_url(settings),
            default_model=settings.ollama_default_model,
            embedding_model=settings.ollama_embedding_model,
        )
    msg = f"Unsupported model provider: {provider_name}"
    raise ValueError(msg)
