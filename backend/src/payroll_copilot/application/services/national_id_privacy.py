"""Pure national-id privacy helpers (no encryption keys, no Fernet).

Hash/mask are framework-independent and belong in application so identity
comparison and employee flows do not import infrastructure crypto.
"""

from __future__ import annotations

import hashlib
from typing import Any


def normalize_national_id_digits(value: Any) -> str | None:
    """Return digits-only national ID as a string (preserve leading zeros).

    Examples:
    - ``31336678-3`` → ``313366783``
    - ``012345678`` → ``012345678``
    """
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits or None


def hash_national_id(national_id: str) -> str:
    """SHA-256 of the digits-only national ID (shared matching/storage form)."""
    digits = normalize_national_id_digits(national_id) or ""
    return hashlib.sha256(digits.encode("utf-8")).hexdigest()


def mask_national_id(national_id: str | None) -> str | None:
    if not national_id:
        return None
    digits = normalize_national_id_digits(national_id) or ""
    if len(digits) < 4:
        return "****"
    return f"****{digits[-4:]}"
