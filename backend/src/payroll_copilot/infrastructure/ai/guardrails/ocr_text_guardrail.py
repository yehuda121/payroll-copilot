"""OCR text injection guardrails applied after OCR, before LLM extraction."""

from __future__ import annotations

import re

from payroll_copilot.application.exceptions import DocumentUploadRejectedError
from payroll_copilot.infrastructure.ai.guardrails.payroll_assistant_guardrails import (
    _INJECTION_PATTERNS,
)

# Extend chat injection patterns with OCR-oriented variants.
_OCR_INJECTION_PATTERNS = _INJECTION_PATTERNS + (
    r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
    r"do\s+not\s+follow\s+(your|the)\s+(instructions?|rules?|policy)",
    r"override\s+(your|the)\s+(system|safety)\s+(prompt|rules?|policy)",
    r"exfiltrate|leak\s+(the\s+)?(system\s+)?prompt",
    r"new\s+system\s+prompt\s*:",
    r"<\s*/?\s*system\s*>",
    r"admin\s+override",
)

_COMPILED = tuple(re.compile(pattern, re.IGNORECASE) for pattern in _OCR_INJECTION_PATTERNS)


def reject_ocr_injection(ocr_text: str) -> None:
    """Raise when normalized OCR text looks like prompt-injection content."""
    text = (ocr_text or "").strip()
    if not text:
        return
    sample = text[:12_000]
    for pattern in _COMPILED:
        if pattern.search(sample):
            raise DocumentUploadRejectedError(
                "The uploaded document contains unsupported instruction-like content."
            )
