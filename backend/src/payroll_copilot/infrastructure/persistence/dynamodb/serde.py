"""Serialize domain values to DynamoDB-safe attribute maps."""

from __future__ import annotations

import base64
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID


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
