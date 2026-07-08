"""OCR infrastructure package — generic document text extraction adapters."""

from __future__ import annotations

from typing import Any

__all__ = ["create_ocr_provider"]


def create_ocr_provider(provider_name: str, settings: Any):
    """Lazy factory import so installing/importing OCR extras is deferred."""
    from payroll_copilot.infrastructure.ocr.factory import create_ocr_provider as _create

    return _create(provider_name, settings)
