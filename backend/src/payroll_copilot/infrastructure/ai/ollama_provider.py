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
        json_mode: bool = False,
    ) -> CompletionResult:
        payload: dict[str, Any] = {
            "model": self._default_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(f"{self._base_url}/api/chat", json=payload)
            if response.status_code >= 400 and json_mode and "format" in payload:
                payload.pop("format", None)
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
        result = await self.complete(structured_messages, temperature=temperature, json_mode=True)
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


def create_model_provider(provider_name: str, settings: Any) -> Any:
    """Factory for model providers (Amazon Bedrock primary; Ollama for local)."""
    name = (provider_name or "bedrock").strip().lower()
    if name == "bedrock":
        from payroll_copilot.infrastructure.ai.bedrock_provider import BedrockProvider

        return BedrockProvider(
            region=getattr(settings, "bedrock_region", None) or "us-east-1",
            model_id=getattr(settings, "bedrock_model_id", "") or "",
            embedding_model_id=getattr(settings, "bedrock_embedding_model_id", "")
            or "amazon.titan-embed-text-v2:0",
            embedding_dimensions=int(
                getattr(settings, "bedrock_embedding_dimensions", 1024) or 1024
            ),
            endpoint_url=(getattr(settings, "bedrock_endpoint", None) or "").strip() or None,
        )
    if name == "ollama":
        from payroll_copilot.infrastructure.config.ollama_resolver import get_resolved_ollama_base_url

        return OllamaProvider(
            base_url=get_resolved_ollama_base_url(settings),
            default_model=settings.ollama_default_model,
            embedding_model=settings.ollama_embedding_model,
        )
    msg = f"Unsupported model provider: {provider_name}"
    raise ValueError(msg)
