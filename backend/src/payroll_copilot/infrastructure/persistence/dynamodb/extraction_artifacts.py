"""Size-aware offload of large DocumentExtraction artifacts to object storage.

DynamoDB rejects items over 400 KiB (409,600 bytes). Canonical structured_data
stays inline; OCR/layout payloads may be stored in S3 with pointer keys on the
extraction item when the projected item would exceed a safe threshold.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping, Protocol

from boto3.dynamodb.types import TypeSerializer

logger = logging.getLogger(__name__)

# DynamoDB hard limit is 400 KiB (409,600). Leave headroom for attribute-name
# overhead, AttributeValue encoding vs Python dict differences, and small
# additive metadata fields that may appear on future writes.
DYNAMODB_ITEM_SAFE_SIZE_BYTES = 350_000

ARTIFACT_OCR_RESULT = "ocr_result"
ARTIFACT_LAYOUT_ANALYSIS = "layout_analysis"
ARTIFACT_LAYOUT_SNAPSHOT = "layout_snapshot"

# Deterministic offload order when the item exceeds the safe threshold.
OFFLOAD_ARTIFACT_FIELDS: tuple[str, ...] = (
    ARTIFACT_OCR_RESULT,
    ARTIFACT_LAYOUT_ANALYSIS,
    ARTIFACT_LAYOUT_SNAPSHOT,
)

STORAGE_KEY_FIELDS: Mapping[str, str] = {
    ARTIFACT_OCR_RESULT: "ocr_result_storage_key",
    ARTIFACT_LAYOUT_ANALYSIS: "layout_analysis_storage_key",
    ARTIFACT_LAYOUT_SNAPSHOT: "layout_snapshot_storage_key",
}

_ARTIFACT_CONTENT_TYPE = "application/json; charset=utf-8"


class ExtractionArtifactMissingError(RuntimeError):
    """Raised when an offloaded extraction artifact cannot be loaded."""

    def __init__(self, *, artifact: str, storage_key: str, cause: Exception | None = None) -> None:
        self.artifact = artifact
        self.storage_key = storage_key
        message = (
            f"Extraction artifact '{artifact}' is missing or unreadable "
            f"at storage key '{storage_key}'"
        )
        super().__init__(message)
        self.__cause__ = cause


class ExtractionItemTooLargeError(RuntimeError):
    """Raised when an extraction item still exceeds the safe DynamoDB size."""

    def __init__(self, *, size_bytes: int, limit_bytes: int) -> None:
        self.size_bytes = size_bytes
        self.limit_bytes = limit_bytes
        super().__init__(
            f"DocumentExtraction item size {size_bytes} exceeds safe limit {limit_bytes}"
        )


class _ObjectStorage(Protocol):
    async def upload(self, key: str, data: bytes, content_type: str) -> str: ...

    async def download(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...


def build_extraction_artifact_storage_key(
    *,
    document_id: str,
    extraction_id: str,
    extraction_version: int,
    artifact: str,
) -> str:
    """Collision-safe object key without PII."""
    return (
        f"documents/{document_id}/extractions/{extraction_id}/"
        f"v{int(extraction_version)}/{artifact}.json"
    )


def serialize_artifact_payload(payload: Mapping[str, Any] | dict[str, Any]) -> bytes:
    return json.dumps(
        dict(payload or {}),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")


def deserialize_artifact_payload(data: bytes) -> dict[str, Any]:
    loaded = json.loads(data.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("extraction artifact payload must be a JSON object")
    return loaded


def estimate_dynamodb_item_size_bytes(item: Mapping[str, Any]) -> int:
    """Estimate DynamoDB item size using AttributeValue encoding rules."""
    from payroll_copilot.infrastructure.persistence.dynamodb.serde import dumps_value

    serializer = TypeSerializer()
    # Mirror put_item input: floats → Decimal, etc., so TypeSerializer succeeds.
    normalized = dumps_value(dict(item))
    if not isinstance(normalized, dict):
        return 0
    total = 0
    for name, value in normalized.items():
        if value is None:
            continue
        total += len(str(name).encode("utf-8"))
        total += _attribute_value_size(serializer.serialize(value))
    return total


def _attribute_value_size(attr: Mapping[str, Any]) -> int:
    if "S" in attr:
        return len(str(attr["S"]).encode("utf-8"))
    if "N" in attr:
        return len(str(attr["N"]).encode("utf-8"))
    if "B" in attr:
        raw = attr["B"]
        return len(raw) if isinstance(raw, (bytes, bytearray)) else len(bytes(raw))
    if "BOOL" in attr or "NULL" in attr:
        return 1
    if "SS" in attr:
        return sum(len(str(s).encode("utf-8")) for s in attr["SS"])
    if "NS" in attr:
        return sum(len(str(n).encode("utf-8")) for n in attr["NS"])
    if "BS" in attr:
        return sum(len(b) if isinstance(b, (bytes, bytearray)) else len(bytes(b)) for b in attr["BS"])
    if "L" in attr:
        return sum(_attribute_value_size(child) for child in attr["L"])
    if "M" in attr:
        nested = 0
        for key, child in attr["M"].items():
            nested += len(str(key).encode("utf-8"))
            nested += _attribute_value_size(child)
        return nested
    return 0


def _artifact_is_substantial(payload: Any) -> bool:
    return isinstance(payload, dict) and bool(payload)


async def prepare_extraction_item_for_put(
    *,
    item: dict[str, Any],
    document_id: str,
    extraction_id: str,
    extraction_version: int,
    object_storage: _ObjectStorage | None,
    safe_size_bytes: int = DYNAMODB_ITEM_SAFE_SIZE_BYTES,
) -> tuple[dict[str, Any], list[str]]:
    """Return a Dynamo-safe item and any newly uploaded object keys.

    When the projected item exceeds ``safe_size_bytes``, approved large
    artifacts are uploaded and replaced with storage-key pointers.
    """
    projected = dict(item)
    uploaded_keys: list[str] = []

    if estimate_dynamodb_item_size_bytes(projected) <= safe_size_bytes:
        # Inline payloads are the source of truth for small items — drop stale pointers.
        for field, key_field in STORAGE_KEY_FIELDS.items():
            if _artifact_is_substantial(projected.get(field)):
                projected.pop(key_field, None)
        return projected, uploaded_keys

    if object_storage is None:
        size = estimate_dynamodb_item_size_bytes(projected)
        raise ExtractionItemTooLargeError(size_bytes=size, limit_bytes=safe_size_bytes)

    # Deterministic: when over threshold, offload all substantial approved artifacts
    # (do not stop after the first field merely because size dropped mid-pass).
    for field in OFFLOAD_ARTIFACT_FIELDS:
        payload = projected.get(field)
        if not _artifact_is_substantial(payload):
            continue
        storage_key_field = STORAGE_KEY_FIELDS[field]
        key = build_extraction_artifact_storage_key(
            document_id=document_id,
            extraction_id=extraction_id,
            extraction_version=extraction_version,
            artifact=field,
        )
        await object_storage.upload(
            key,
            serialize_artifact_payload(payload),
            _ARTIFACT_CONTENT_TYPE,
        )
        uploaded_keys.append(key)
        projected.pop(field, None)
        projected[storage_key_field] = key
        logger.info(
            "extraction_artifact_offloaded field=%s key=%s extraction_id=%s",
            field,
            key,
            extraction_id,
        )

    final_size = estimate_dynamodb_item_size_bytes(projected)
    if final_size > safe_size_bytes:
        raise ExtractionItemTooLargeError(
            size_bytes=final_size,
            limit_bytes=safe_size_bytes,
        )
    return projected, uploaded_keys


async def hydrate_extraction_artifacts(
    *,
    entity_fields: dict[str, Any],
    storage_keys: Mapping[str, str | None],
    object_storage: _ObjectStorage | None,
) -> dict[str, Any]:
    """Fill artifact fields from object storage when inline payloads are absent."""
    hydrated = dict(entity_fields)
    for field, key_field in STORAGE_KEY_FIELDS.items():
        storage_key = storage_keys.get(key_field)
        inline = hydrated.get(field)
        if _artifact_is_substantial(inline):
            continue
        if not storage_key:
            hydrated.setdefault(field, {})
            continue
        if object_storage is None:
            raise ExtractionArtifactMissingError(
                artifact=field,
                storage_key=str(storage_key),
            )
        try:
            raw = await object_storage.download(str(storage_key))
            hydrated[field] = deserialize_artifact_payload(raw)
        except ExtractionArtifactMissingError:
            raise
        except Exception as exc:  # noqa: BLE001 — surface as controlled missing-artifact error
            raise ExtractionArtifactMissingError(
                artifact=field,
                storage_key=str(storage_key),
                cause=exc,
            ) from exc
    return hydrated


async def best_effort_delete_keys(
    object_storage: _ObjectStorage | None,
    keys: list[str],
) -> None:
    if object_storage is None or not keys:
        return
    for key in keys:
        try:
            await object_storage.delete(key)
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to roll back extraction artifact object key=%s",
                key,
                exc_info=True,
            )
