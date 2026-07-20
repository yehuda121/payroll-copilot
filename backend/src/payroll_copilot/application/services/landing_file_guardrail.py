"""Landing-page file guardrails — PDF only for the public chat entry point."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from payroll_copilot.application.exceptions import DocumentUploadRejectedError
from payroll_copilot.application.ports.upload_limits import UploadSizeLimits


@dataclass(frozen=True, slots=True)
class LandingFilePayload:
    filename: str
    content: bytes
    mime_type: str


@dataclass(frozen=True, slots=True)
class LandingFileGuardrailResult:
    accepted: list[LandingFilePayload]
    content_hashes: list[str]


class LandingFileGuardrailService:
    """Reject non-PDF and unsafe PDFs before OCR."""

    ALLOWED_MIME = frozenset({"application/pdf"})
    ALLOWED_EXTENSIONS = frozenset({".pdf"})

    def __init__(self, settings: UploadSizeLimits) -> None:
        self._settings = settings

    def validate(
        self,
        files: list[LandingFilePayload],
        *,
        existing_filenames: set[str] | None = None,
        existing_hashes: set[str] | None = None,
    ) -> LandingFileGuardrailResult:
        if not files:
            return LandingFileGuardrailResult(accepted=[], content_hashes=[])

        existing_names = existing_filenames or set()
        existing_digests = existing_hashes or set()
        accepted: list[LandingFilePayload] = []
        hashes: list[str] = []

        for payload in files:
            self._validate_one(payload, existing_names=existing_names, existing_hashes=existing_digests)
            digest = hashlib.sha256(payload.content).hexdigest()
            accepted.append(payload)
            hashes.append(digest)
            existing_names.add(payload.filename)
            existing_digests.add(digest)

        return LandingFileGuardrailResult(accepted=accepted, content_hashes=hashes)

    def _validate_one(
        self,
        payload: LandingFilePayload,
        *,
        existing_names: set[str],
        existing_hashes: set[str],
    ) -> None:
        if not payload.content:
            raise DocumentUploadRejectedError("Empty files cannot be uploaded.")

        max_size = self._settings.max_upload_size_mb * 1024 * 1024
        if len(payload.content) > max_size:
            raise DocumentUploadRejectedError(
                f"File exceeds the maximum allowed size of {max_size // (1024 * 1024)}MB."
            )

        name_lower = payload.filename.lower()
        if not any(name_lower.endswith(ext) for ext in self.ALLOWED_EXTENSIONS):
            raise DocumentUploadRejectedError(
                "Only PDF files are supported on the landing page."
            )

        mime = (payload.mime_type or "").lower().strip()
        if mime and mime not in self.ALLOWED_MIME and mime != "application/octet-stream":
            raise DocumentUploadRejectedError(
                f"Unsupported file type '{payload.mime_type}'. Only PDF is accepted."
            )

        if payload.filename in existing_names:
            raise DocumentUploadRejectedError(
                f"Duplicate upload in this session: '{payload.filename}'."
            )

        digest = hashlib.sha256(payload.content).hexdigest()
        if digest in existing_hashes:
            raise DocumentUploadRejectedError(
                f"Duplicate file content already uploaded in this session: '{payload.filename}'."
            )

        if not payload.content.startswith(b"%PDF"):
            raise DocumentUploadRejectedError(
                "The uploaded PDF appears to be corrupted or invalid."
            )

        if b"/Encrypt" in payload.content[:8192]:
            raise DocumentUploadRejectedError(
                "Password-protected PDF files are not supported."
            )
