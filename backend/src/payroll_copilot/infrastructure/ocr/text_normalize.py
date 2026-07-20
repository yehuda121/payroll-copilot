"""Normalize extracted document text without altering meaning.

Canonical implementation: ``application.services.text_normalize``.
Re-exported here for infrastructure OCR callers that historically imported this path.
"""

from payroll_copilot.application.services.text_normalize import normalize_extracted_text

__all__ = ["normalize_extracted_text"]
