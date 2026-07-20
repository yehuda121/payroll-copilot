"""Field-level encryption helpers for sensitive employee identifiers.

Pure hash/mask helpers live in ``application.services.national_id_privacy`` and are
re-exported here so existing infrastructure imports keep working.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from payroll_copilot.application.services.national_id_privacy import (
    hash_national_id,
    mask_national_id,
)

__all__ = [
    "derive_fernet",
    "hash_national_id",
    "mask_national_id",
    "encrypt_national_id",
    "decrypt_national_id",
]


def derive_fernet(encryption_key: str) -> Fernet:
    digest = hashlib.sha256(encryption_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_national_id(national_id: str, *, encryption_key: str) -> bytes:
    return derive_fernet(encryption_key).encrypt(national_id.strip().encode("utf-8"))


def decrypt_national_id(payload: bytes | None, *, encryption_key: str) -> str | None:
    if not payload:
        return None
    try:
        return derive_fernet(encryption_key).decrypt(payload).decode("utf-8")
    except InvalidToken:
        return None
