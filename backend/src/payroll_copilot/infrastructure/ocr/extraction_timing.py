"""Structured extraction timing (no document content logged)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from payroll_copilot.infrastructure.ocr.pdf_text import log_extraction_stage


@dataclass
class ExtractionTimer:
    """Wall-clock marks for guest/document extraction stages."""

    document_type: str = "payslip"
    _started: float = field(default_factory=time.perf_counter)
    _marks: dict[str, float] = field(default_factory=dict)

    def mark(self, stage: str) -> float:
        now = time.perf_counter()
        self._marks[stage] = (now - self._started) * 1000.0
        return self._marks[stage]

    def duration_ms(self, stage: str) -> float | None:
        return self._marks.get(stage)

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._started) * 1000.0

    def log_stage(
        self,
        stage: str,
        *,
        page_count: int | None = None,
        extracted_text_length: int | None = None,
        extracted_field_count: int | None = None,
        error_code: str | None = None,
    ) -> None:
        duration = self.mark(stage)
        log_extraction_stage(
            stage=stage,
            document_type=self.document_type,
            page_count=page_count,
            extracted_text_length=extracted_text_length,
            extracted_field_count=extracted_field_count,
            error_code=error_code,
            duration_ms=duration,
        )

    def log_summary(self) -> None:
        total = self.elapsed_ms()
        log_extraction_stage(
            stage="extraction_total",
            document_type=self.document_type,
            duration_ms=total,
        )
        for name, ms in self._marks.items():
            log_extraction_stage(
                stage=f"timing_{name}",
                document_type=self.document_type,
                duration_ms=ms,
            )
