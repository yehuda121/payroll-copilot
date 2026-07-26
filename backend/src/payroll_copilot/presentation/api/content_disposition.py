"""Helpers for safe Content-Disposition filename values."""

from __future__ import annotations


def sanitize_content_disposition_filename(
    filename: str | None,
    *,
    fallback: str = "document",
) -> str:
    """Strip path components, quotes, CR/LF, and other control characters.

    Preserves normal printable filenames for download/preview headers.
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
