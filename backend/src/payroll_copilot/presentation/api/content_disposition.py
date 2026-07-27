"""Helpers for safe Content-Disposition filename values."""

from __future__ import annotations

from urllib.parse import quote


def sanitize_content_disposition_filename(
    filename: str | None,
    *,
    fallback: str = "document",
) -> str:
    """Strip path components, quotes, CR/LF, and other control characters.

    Preserves normal printable filenames (including Unicode) for use in
    RFC 5987 ``filename*`` values. Callers that need a latin-1-safe header
    must use :func:`build_content_disposition`.
    """
    raw = (filename or "").replace("\\", "/").split("/")[-1]
    cleaned_chars: list[str] = []
    for ch in raw:
        code = ord(ch)
        if ch in {'"', "'"} or ch in "\r\n" or code < 32 or code == 127:
            continue
        cleaned_chars.append(ch)
    cleaned = "".join(cleaned_chars).strip() or fallback
    return cleaned[:200]


def _ascii_filename_fallback(sanitized: str, *, fallback: str = "document") -> str:
    """Build a latin-1/ASCII-safe ``filename=`` token from a sanitized name."""
    ascii_chars: list[str] = []
    for ch in sanitized:
        code = ord(ch)
        if 32 <= code < 127 and ch not in {'"', "\\", ";"}:
            ascii_chars.append(ch)
        elif ch.isspace():
            ascii_chars.append("_")
        else:
            ascii_chars.append("_")
    ascii_name = "".join(ascii_chars).strip(" ._")
    if any(ch.isalnum() for ch in ascii_name):
        return ascii_name[:200]

    extension = ""
    if "." in sanitized:
        ext = sanitized.rsplit(".", 1)[-1]
        ext_clean = "".join(ch for ch in ext if ch.isalnum())[:12]
        if ext_clean:
            extension = f".{ext_clean}"
    return f"{fallback}{extension}"[:200]


def build_content_disposition(
    filename: str | None,
    *,
    disposition: str = "inline",
    fallback: str = "document",
) -> str:
    """Build a Starlette-safe Content-Disposition header value.

    Always includes an ASCII ``filename=`` fallback so header encoding cannot
    raise ``UnicodeEncodeError``. When the sanitized name differs from the
    ASCII fallback (Unicode or non-ASCII), also emits RFC 5987
    ``filename*=UTF-8''...``.
    """
    safe_disposition = (disposition or "inline").strip() or "inline"
    if any(ch in safe_disposition for ch in "\r\n;") or not safe_disposition.isascii():
        safe_disposition = "inline"

    sanitized = sanitize_content_disposition_filename(filename, fallback=fallback)
    ascii_name = _ascii_filename_fallback(sanitized, fallback=fallback)
    header = f'{safe_disposition}; filename="{ascii_name}"'
    if sanitized != ascii_name:
        encoded = quote(sanitized, safe="")
        header = f"{header}; filename*=UTF-8''{encoded}"
    # Entire header must remain latin-1 encodable for Starlette.
    header.encode("latin-1")
    return header
