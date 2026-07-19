"""OpenAI implementation of the application ModelProvider port."""

from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel

from payroll_copilot.application.ports import (
    CompletionResult,
    Message,
    StructuredResult,
)


class OpenAIProvider:
    """OpenAI chat-completions and embeddings adapter."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-5",
        embedding_model: str = "text-embedding-3-small",
        embedding_dimensions: int = 1536,
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
        reasoning_effort: str = "minimal",
        base_url: str | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        if not (api_key or "").strip() and client is None:
            raise ValueError(
                "OPENAI_API_KEY is required when an AI capability uses OpenAI."
            )
        self._model = (model or "gpt-5").strip()
        self._embedding_model = (
            embedding_model or "text-embedding-3-small"
        ).strip()
        self._embedding_dimensions = int(embedding_dimensions) or 1536
        self._reasoning_effort = (reasoning_effort or "minimal").strip()
        self._client = client or AsyncOpenAI(
            api_key=api_key.strip(),
            base_url=(base_url or "").strip() or None,
            timeout=float(timeout_seconds),
            max_retries=int(max_retries),
        )

    @property
    def embedding_dimensions(self) -> int:
        return self._embedding_dimensions

    async def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> CompletionResult:
        params: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "max_completion_tokens": int(max_tokens),
        }
        # GPT-5 and reasoning models reject non-default temperature values.
        lowered_model = self._model.lower()
        if lowered_model.startswith(("gpt-5", "o1", "o3", "o4")):
            params["reasoning_effort"] = self._reasoning_effort
        else:
            params["temperature"] = float(temperature)
        if json_mode:
            params["response_format"] = {"type": "json_object"}

        response = await self._client.chat.completions.create(**params)
        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice is not None else ""
        usage = response.usage
        return CompletionResult(
            content=content or "",
            confidence=0.85 if content else 0.0,
            model=str(response.model or self._model),
            tokens_used=int(usage.total_tokens if usage is not None else 0),
        )

    async def complete_structured(
        self,
        messages: list[Message],
        response_schema: type[BaseModel],
        *,
        temperature: float = 0.0,
    ) -> StructuredResult:
        schema_json = json.dumps(response_schema.model_json_schema(), indent=2)
        result = await self.complete(
            [
                *messages,
                Message(
                    role="system",
                    content=(
                        "Respond ONLY with valid JSON matching this schema:\n"
                        f"{schema_json}\n"
                        "No markdown, no explanation, JSON only."
                    ),
                ),
            ],
            temperature=temperature,
            json_mode=True,
        )
        payload = self._parse_json_response(result.content)
        validated = response_schema.model_validate(payload)
        return StructuredResult(
            data=validated,
            confidence=0.9 if payload else 0.0,
            model=result.model,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        params: dict[str, Any] = {
            "model": self._embedding_model,
            "input": texts,
        }
        if self._embedding_model.startswith("text-embedding-3"):
            params["dimensions"] = self._embedding_dimensions
        response = await self._client.embeddings.create(**params)
        ordered = sorted(response.data, key=lambda item: item.index)
        return [[float(value) for value in item.embedding] for item in ordered]

    @staticmethod
    def _parse_json_response(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(
                lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            )
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("OpenAI structured response must be a JSON object.")
        return payload
