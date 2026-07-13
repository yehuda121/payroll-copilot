"""Field-level encryption helpers for sensitive employee identifiers."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def derive_fernet(encryption_key: str) -> Fernet:
    digest = hashlib.sha256(encryption_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


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


def encrypt_national_id(national_id: str, *, encryption_key: str) -> bytes:
    return derive_fernet(encryption_key).encrypt(national_id.strip().encode("utf-8"))


def decrypt_national_id(payload: bytes | None, *, encryption_key: str) -> str | None:
    if not payload:
        return None
    try:
        return derive_fernet(encryption_key).decrypt(payload).decode("utf-8")
    except InvalidToken:
        return None
