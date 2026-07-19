"""Serialize domain values to DynamoDB-safe attribute maps."""

from __future__ import annotations

import base64
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID


def is_empty_for_storage(value: Any) -> bool:
    """Return True when ``value`` should be omitted from DynamoDB writes.

    Empty means ``None``, whitespace-only strings, empty containers, or
    containers that become empty after recursive pruning. Retains ``0``,
    ``False``, enums, and other meaningful scalars.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, Enum):
        return False
    if isinstance(value, dict):
        return len(value) == 0
    if isinstance(value, (list, tuple)):
        return len(value) == 0
    return False


def prune_empty(value: Any) -> Any:
    """Recursively drop empty values for DynamoDB persistence.

    Rules:
    - Remove ``None``, ``\"\"`` / whitespace-only strings, ``[]``, ``{}``
    - Recurse into dicts and lists
    - Keep ``0``, ``False``, enums, and non-empty scalars
    - Return ``None`` when the pruned value itself becomes empty (callers omit)
    """
    if value is None:
        return None
    if isinstance(value, Enum):
        return value
    if isinstance(value, str):
        return None if value.strip() == "" else value
    if isinstance(value, dict):
        pruned: dict[str, Any] = {}
        for key, child in value.items():
            cleaned = prune_empty(child)
            if is_empty_for_storage(cleaned):
                continue
            pruned[str(key)] = cleaned
        return pruned if pruned else None
    if isinstance(value, (list, tuple)):
        pruned_list: list[Any] = []
        for child in value:
            cleaned = prune_empty(child)
            if is_empty_for_storage(cleaned):
                continue
            pruned_list.append(cleaned)
        return pruned_list if pruned_list else None
    return value


def dumps_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, bytes):
        return value  # boto3 Binary
    if isinstance(value, dict):
        return {str(k): dumps_value(v) for k, v in value.items() if v is not None}
    if isinstance(value, (list, tuple)):
        return [dumps_value(v) for v in value]
    return value


def loads_uuid(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    return UUID(str(value))


def loads_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def loads_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def loads_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def loads_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def bytes_to_b64(value: bytes | None) -> str | None:
    if value is None:
        return None
    return base64.b64encode(value).decode("ascii")


def b64_to_bytes(value: Any) -> bytes | None:
    if value is None or value == "":
        return None
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    return base64.b64decode(str(value))
