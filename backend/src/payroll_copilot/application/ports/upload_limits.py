"""Upload size limits consumed by application guardrails.

Infrastructure Settings satisfies this Protocol; tests can pass a SimpleNamespace.
"""

from __future__ import annotations

from typing import Protocol


class UploadSizeLimits(Protocol):
    max_upload_size_mb: int
    max_bulk_pdf_size_mb: int
