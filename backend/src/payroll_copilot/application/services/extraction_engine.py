"""Helpers for extraction engine classification."""

from __future__ import annotations


def is_embedded_text_engine(engine: str | None) -> bool:
    return bool(engine and "pdf_text" in engine.lower())
