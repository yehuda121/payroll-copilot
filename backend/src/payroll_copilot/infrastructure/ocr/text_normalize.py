"""Normalize extracted document text without altering meaning."""

from __future__ import annotations

import re
import unicodedata

_MULTI_SPACE = re.compile(r"[ \t]+")
_MULTI_NL = re.compile(r"\n{3,}")


def normalize_extracted_text(text: str) -> str:
    """Collapse noisy whitespace; preserve line structure and RTL characters."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(_MULTI_SPACE.sub(" ", line).strip() for line in normalized.split("\n"))
    normalized = _MULTI_NL.sub("\n\n", normalized).strip()
    return normalized
