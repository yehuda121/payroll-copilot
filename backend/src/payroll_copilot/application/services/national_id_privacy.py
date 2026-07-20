"""Pure national-id privacy helpers (no encryption keys, no Fernet).

Hash/mask are framework-independent and belong in application so identity
comparison and employee flows do not import infrastructure crypto.
"""

from __future__ import annotations

import hashlib


def hash_national_id(national_id: str) -> str:
    normalized = "".join(ch for ch in national_id.strip() if ch.isalnum())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def mask_national_id(national_id: str | None) -> str | None:
    if not national_id:
        return None
    digits = "".join(ch for ch in national_id if ch.isdigit())
    if len(digits) < 4:
        return "****"
    return f"****{digits[-4:]}"
