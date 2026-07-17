"""Amazon Bedrock model provider (Converse + embeddings)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel

from payroll_copilot.application.ports import CompletionResult, Message, StructuredResult

logger = logging.getLogger(__name__)


class BedrockProvider:
    """LLM provider via Amazon Bedrock Runtime (Converse API)."""

    def __init__(
        self,
        *,
        region: str = "us-east-1",
        model_id: str,
        embedding_model_id: str = "amazon.titan-embed-text-v2:0",
        embedding_dimensions: int = 1024,
        endpoint_url: str | None = None,
    ) -> None:
        if not (model_id or "").strip():
            raise ValueError("BEDROCK_MODEL_ID is required when MODEL_PROVIDER=bedrock.")
        self._region = (region or "us-east-1").strip()
        self._model_id = model_id.strip()
        self._embedding_model_id = (embedding_model_id or "").strip() or "amazon.titan-embed-text-v2:0"
        self._embedding_dimensions = int(embedding_dimensions) or 1024
        self._endpoint_url = (endpoint_url or "").strip() or None
        self._client = self._build_client()

    def _build_client(self) -> Any:
        import boto3

        kwargs: dict[str, Any] = {"region_name": self._region}
        if self._endpoint_url:
            kwargs["endpoint_url"] = self._endpoint_url
        return boto3.client("bedrock-runtime", **kwargs)

    @property
    def embedding_dimensions(self) -> int:
        return self._embedding_dimensions

    @property
    def model_id(self) -> str:
        return self._model_id

    def _split_messages(
        self, messages: list[Message]
    ) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        system: list[dict[str, str]] = []
        converse_messages: list[dict[str, Any]] = []
        for message in messages:
            role = (message.role or "user").strip().lower()
            content = message.content or ""
            if role == "system":
                system.append({"text": content})
                continue
            if role not in {"user", "assistant"}:
                role = "user"
            # Converse requires alternating user/assistant; merge consecutive same roles.
            block = {"role": role, "content": [{"text": content}]}
            if converse_messages and converse_messages[-1]["role"] == role:
                converse_messages[-1]["content"].append({"text": content})
            else:
                converse_messages.append(block)
        if not converse_messages:
            converse_messages = [{"role": "user", "content": [{"text": ""}]}]
        # Converse requires the first message to be from user.
        if converse_messages[0]["role"] != "user":
            converse_messages.insert(0, {"role": "user", "content": [{"text": "(continue)"}]})
        return system, converse_messages

    async def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> CompletionResult:
        system, converse_messages = self._split_messages(messages)
        if json_mode:
            system = [
                *system,
                {
                    "text": (
                        "Respond with valid JSON only. No markdown fences, no commentary."
                    )
                },
            ]
        params: dict[str, Any] = {
            "modelId": self._model_id,
            "messages": converse_messages,
            "inferenceConfig": {
                "temperature": float(temperature),
                "maxTokens": int(max_tokens),
            },
        }
        if system:
            params["system"] = system

        try:
            response = await asyncio.to_thread(self._client.converse, **params)
        except (ClientError, BotoCoreError) as exc:
            logger.warning("Bedrock converse failed: %s", exc)
            raise

        content = self._extract_text(response)
        usage = response.get("usage") or {}
        tokens = int(usage.get("totalTokens") or 0)
        if not tokens:
            tokens = int(usage.get("inputTokens") or 0) + int(usage.get("outputTokens") or 0)
        return CompletionResult(
            content=content,
            confidence=0.85 if content else 0.0,
            model=self._model_id,
            tokens_used=tokens,
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
        result = await self.complete(
            structured_messages, temperature=temperature, json_mode=True
        )
        parsed = self._parse_json_response(result.content)
        validated = response_schema.model_validate(parsed)
        confidence = 0.9 if parsed else 0.0
        return StructuredResult(data=validated, confidence=confidence, model=result.model)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for text in texts:
            body = json.dumps(
                {
                    "inputText": text,
                    "dimensions": self._embedding_dimensions,
                    "normalize": True,
                }
            )
            try:
                response = await asyncio.to_thread(
                    self._client.invoke_model,
                    modelId=self._embedding_model_id,
                    contentType="application/json",
                    accept="application/json",
                    body=body,
                )
            except (ClientError, BotoCoreError):
                logger.exception("Bedrock embedding failed")
                raise
            payload = json.loads(response["body"].read())
            vector = payload.get("embedding") or payload.get("embeddings") or []
            if isinstance(vector, dict):
                vector = vector.get("values") or []
            embeddings.append([float(v) for v in vector])
        return embeddings

    @staticmethod
    def _extract_text(response: dict[str, Any]) -> str:
        output = response.get("output") or {}
        message = output.get("message") or {}
        parts = message.get("content") or []
        texts: list[str] = []
        for part in parts:
            if isinstance(part, dict) and "text" in part:
                texts.append(str(part["text"]))
        return "\n".join(texts).strip()

    @staticmethod
    def _parse_json_response(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(text)
