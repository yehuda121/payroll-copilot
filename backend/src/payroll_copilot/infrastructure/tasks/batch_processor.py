"""Batch payslip PDF processor with stage progress reporting."""

from __future__ import annotations

from uuid import uuid4

import fitz

from payroll_copilot.application.services.batch_progress_store import get_batch_progress_store
from payroll_copilot.application.services.manual_review_queue import (
    get_manual_review_queue,
    should_enqueue_low_confidence,
)
from payroll_copilot.infrastructure.config.settings import get_settings


class BatchPayslipProcessor:
    """Processes bulk PDF containing multiple payslips.

    Pipeline foundation:
    Upload → Split → OCR → Parser → Employee Identification → Validation → Report

    Downstream OCR/parser/validation wiring remains incremental; stages are marked
    honestly (skipped) when not yet connected — never invents validation results.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._progress = get_batch_progress_store()

    def process(self, batch_job_id: str, document_id: str) -> dict:
        from payroll_copilot.infrastructure.storage.s3_storage import S3ObjectStorage

        storage = S3ObjectStorage(
            endpoint=self._settings.s3_endpoint,
            access_key=self._settings.s3_access_key,
            secret_key=self._settings.s3_secret_key,
            bucket=self._settings.s3_bucket,
            region=self._settings.s3_region,
            use_ssl=self._settings.s3_use_ssl,
        )

        try:
            self._progress.mark_stage(
                batch_job_id,
                "split",
                status="running",
                job_status="running",
                detail="Downloading source PDF",
            )

            storage_key = f"documents/{document_id}"
            import asyncio

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            pdf_bytes = loop.run_until_complete(storage.download(storage_key))

            splits = self._split_pdf(pdf_bytes)
            child_documents = []

            for i, split_bytes in enumerate(splits):
                child_id = str(uuid4())
                child_key = f"documents/{child_id}"
                loop.run_until_complete(storage.upload(child_key, split_bytes, "application/pdf"))
                child_documents.append(
                    {
                        "document_id": child_id,
                        "slip_index": i,
                        "storage_key": child_key,
                    }
                )

            self._progress.mark_stage(
                batch_job_id,
                "split",
                status="completed",
                total_slips=len(splits),
                detail=f"Split into {len(splits)} slip(s)",
            )
            self._progress.mark_stage(
                batch_job_id,
                "ocr",
                status="skipped",
                detail="OCR per-slip wiring pending — documents stored for downstream processing",
            )
            self._progress.mark_stage(
                batch_job_id,
                "parser",
                status="skipped",
                detail="Parser per-slip wiring pending",
            )
            self._progress.mark_stage(
                batch_job_id,
                "identify",
                status="skipped",
                detail="National-ID matching runs when OCR/parser fields are available",
            )
            self._progress.mark_stage(
                batch_job_id,
                "validation",
                status="skipped",
                detail="Validation wiring pending for batch children",
            )
            self._progress.mark_stage(
                batch_job_id,
                "report",
                status="completed",
                job_status="completed",
                processed_slips=len(splits),
                report_summary={
                    "total": len(splits),
                    "passed": 0,
                    "warnings": 0,
                    "critical": 0,
                    "pending_pipeline": len(splits),
                },
                detail="Split complete; downstream validation not yet executed",
            )

            return {
                "batch_job_id": batch_job_id,
                "total_slips": len(splits),
                "child_documents": child_documents,
                "status": "split_complete",
            }
        except Exception as exc:  # noqa: BLE001 — surface failure into progress store
            self._progress.mark_stage(
                batch_job_id,
                "split",
                status="failed",
                job_status="failed",
                error_message=str(exc),
                detail=str(exc),
            )
            raise

    def enqueue_low_confidence_match(
        self,
        *,
        batch_job_id: str,
        confidence: float | None,
        national_id_masked: str | None,
        extracted_fields: dict | None = None,
    ) -> str | None:
        """Called by future identify stage — never auto-creates employees."""
        if not should_enqueue_low_confidence(confidence):
            return None
        item = get_manual_review_queue().enqueue(
            reason="low_confidence_employee_identification",
            confidence=confidence,
            batch_job_id=batch_job_id,
            national_id_masked=national_id_masked,
            extracted_fields=extracted_fields or {},
        )
        return item.id

    def _split_pdf(self, pdf_bytes: bytes) -> list[bytes]:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        splits: list[bytes] = []
        current_pages: list[int] = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            is_boundary = self._is_payslip_start(text, page_num == 0)

            if is_boundary and current_pages:
                splits.append(self._extract_pages(doc, current_pages))
                current_pages = []

            current_pages.append(page_num)

        if current_pages:
            splits.append(self._extract_pages(doc, current_pages))

        doc.close()

        if not splits:
            splits = [pdf_bytes]

        return splits

    @staticmethod
    def _is_payslip_start(text: str, is_first_page: bool) -> bool:
        if is_first_page:
            return True
        indicators = ["תלוש שכר", "payslip", "salary slip", "מספר עובד", "employee"]
        text_lower = text.lower()
        return any(ind.lower() in text_lower for ind in indicators)

    @staticmethod
    def _extract_pages(doc: fitz.Document, page_indices: list[int]) -> bytes:
        new_doc = fitz.open()
        for idx in page_indices:
            new_doc.insert_pdf(doc, from_page=idx, to_page=idx)
        pdf_bytes = new_doc.tobytes()
        new_doc.close()
        return pdf_bytes
