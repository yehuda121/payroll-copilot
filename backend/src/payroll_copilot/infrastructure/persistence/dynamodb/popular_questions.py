"""Global popular-question counters (no answers stored)."""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from payroll_copilot.infrastructure.persistence.dynamodb.client import GSI2, DynamoTable

logger = logging.getLogger(__name__)

_PUNCT_RE = re.compile(r"[?？؟!.。,…]+$", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)
_SESSION_MARKERS = (
    "\n\n[Session context",
    "\n\n[Ephemeral session memory",
)


@dataclass(frozen=True, slots=True)
class PopularQuestion:
    normalized_text: str
    display_text: str
    count: int
    last_asked_at: str


def strip_session_context(message: str) -> str:
    text = message or ""
    for marker in _SESSION_MARKERS:
        if marker in text:
            text = text.split(marker, 1)[0]
    return text.strip()


def normalize_question(message: str) -> str:
    text = strip_session_context(message)
    text = unicodedata.normalize("NFKC", text)
    text = text.casefold().strip()
    text = _PUNCT_RE.sub("", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def question_hash(normalized: str) -> str:
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def rank_sort_key(count: int, qhash: str) -> str:
    return f"{int(count):016d}#{qhash}"


class PopularQuestionRepository(Protocol):
    async def increment(self, message: str, *, locale: str = "en") -> PopularQuestion | None: ...

    async def top(self, *, limit: int = 10) -> list[PopularQuestion]: ...


class DynamoPopularQuestionRepository:
    """Sparse GSI2 ranking: GSI2PK=POPULAR#GLOBAL, GSI2SK=zero-padded count#hash."""

    ENTITY = "popular_question"
    PK = "POPULAR#GLOBAL"
    GSI_PK = "POPULAR#GLOBAL"

    def __init__(self, table: DynamoTable) -> None:
        self._table = table

    async def increment(self, message: str, *, locale: str = "en") -> PopularQuestion | None:
        display = strip_session_context(message).strip()[:500]
        normalized = normalize_question(message)
        if len(normalized) < 8:
            return None
        qhash = question_hash(normalized)
        now = datetime.now(UTC).isoformat()
        key = {"PK": self.PK, "SK": f"Q#{qhash}"}

        try:
            attrs = await self._table.update_item(
                key,
                update_expression=(
                    "ADD #count :one "
                    "SET entity_type = if_not_exists(entity_type, :etype), "
                    "normalized_text = if_not_exists(normalized_text, :norm), "
                    "display_text = if_not_exists(display_text, :display), "
                    "locale = if_not_exists(locale, :locale), "
                    "last_asked_at = :ts, "
                    "GSI2PK = :gpk"
                ),
                expression_attribute_names={"#count": "count"},
                expression_attribute_values={
                    ":one": 1,
                    ":etype": self.ENTITY,
                    ":norm": normalized,
                    ":display": display or normalized,
                    ":locale": locale,
                    ":ts": now,
                    ":gpk": self.GSI_PK,
                },
                return_values="ALL_NEW",
            )
        except ClientError:
            logger.warning("popular_question_increment_failed", exc_info=True)
            return None

        new_count = int(attrs.get("count") or 1)
        try:
            attrs = await self._table.update_item(
                key,
                update_expression="SET GSI2SK = :gsk",
                expression_attribute_values={":gsk": rank_sort_key(new_count, qhash)},
                return_values="ALL_NEW",
            )
        except ClientError:
            logger.warning("popular_question_rank_key_update_failed", exc_info=True)

        return PopularQuestion(
            normalized_text=str(attrs.get("normalized_text") or normalized),
            display_text=str(attrs.get("display_text") or display or normalized),
            count=new_count,
            last_asked_at=str(attrs.get("last_asked_at") or now),
        )

    async def top(self, *, limit: int = 10) -> list[PopularQuestion]:
        limit = max(1, min(int(limit), 50))
        items = await self._table.query(
            key_condition_expression=Key("GSI2PK").eq(self.GSI_PK),
            index_name=GSI2,
            scan_index_forward=False,
            limit=limit,
        )
        results: list[PopularQuestion] = []
        for item in items:
            if item.get("entity_type") != self.ENTITY:
                continue
            results.append(
                PopularQuestion(
                    normalized_text=str(item.get("normalized_text") or ""),
                    display_text=str(item.get("display_text") or ""),
                    count=int(item.get("count") or 0),
                    last_asked_at=str(item.get("last_asked_at") or ""),
                )
            )
            if len(results) >= limit:
                break
        return results
