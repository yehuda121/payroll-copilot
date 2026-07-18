"""Sequential bulk-payslip processor using the Employee Portal pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import fitz

from payroll_copilot.application.ports.object_storage import ObjectStoragePort
from payroll_copilot.application.services.batch_payslip_pipeline import (
    BatchPayslipPipelineService,
    BatchSlipPipelineResult,
)
from payroll_copilot.application.services.batch_progress_store import (
    BatchExtractedItem,
    BatchProgressStoreProtocol,
    get_batch_progress_store,
)
from payroll_copilot.infrastructure.config.settings import get_settings

_PHASE_TO_STAGE = {
    "ocr": "ocr",
    "extracting": "parser",
    "matching": "identify",
    "validation": "validation",
    "completed": "report",
}


class BatchPayslipProcessor:
    """Split once, then process and persist every payslip independently."""

    def __init__(
        self,
        *,
        progress: BatchProgressStoreProtocol | None = None,
        storage: ObjectStoragePort | None = None,
        pipeline: BatchPayslipPipelineService | None = None,
    ) -> None:
        settings = get_settings()
        self._progress = progress or get_batch_progress_store()
        if storage is None:
            from payroll_copilot.infrastructure.storage.factory import (
                create_object_storage,
            )

            storage = create_object_storage(settings)
        if pipeline is None:
            from payroll_copilot.infrastructure.tasks.batch_pipeline_factory import (
                create_batch_payslip_pipeline,
            )

            pipeline = create_batch_payslip_pipeline()
        self._storage = storage
        self._pipeline = pipeline

    def process(self, batch_job_id: str, document_id: str) -> dict[str, Any]:
        """Celery entry point. The worker itself is synchronous."""
        return asyncio.run(self._process_async(batch_job_id, document_id))

    async def _process_async(
        self,
        batch_job_id: str,
        document_id: str,
    ) -> dict[str, Any]:
        job = self._progress.get(batch_job_id)
        if (
            job is None
            or not job.organization_id
            or not job.created_by_user_id
        ):
            raise ValueError("Batch job is missing organization or actor context.")

        organization_id = UUID(job.organization_id)
        actor_user_id = UUID(job.created_by_user_id)
        source_name = job.source_filename or "bulk-payslips.pdf"

        try:
            self._progress.mark_stage(
                batch_job_id,
                "split",
                status="running",
                job_status="running",
                detail="Downloading and splitting the source PDF",
            )
            pdf_bytes = await self._storage.download(f"documents/{document_id}")
            splits = self._split_pdf(pdf_bytes)
            total = len(splits)
            self._progress.mark_stage(
                batch_job_id,
                "split",
                status="completed",
                total_slips=total,
                detail=f"Split into {total} payslip(s)",
            )

            counts = {
                "passed": 0,
                "warnings": 0,
                "failed": 0,
                "unknown": 0,
                "processing": total,
            }
            completed_items: list[dict[str, Any]] = []
            failed_count = 0

            for index, split_bytes in enumerate(splits):
                item_id = str(uuid4())
                item = BatchExtractedItem(
                    id=item_id,
                    slip_index=index,
                    status="processing",
                    processing_stage="queued",
                )
                self._progress.upsert_item(batch_job_id, item)

                current_phase = "queued"

                def publish_phase(
                    phase: str,
                    details: dict[str, Any] | None = None,
                ) -> None:
                    nonlocal item, current_phase
                    current_phase = phase
                    item = BatchExtractedItem(
                        **{
                            **item.to_dict(),
                            "processing_stage": phase,
                            "status": "processing",
                            "employee_number": (
                                details.get("employee_number")
                                if details
                                else item.employee_number
                            ),
                            "employee_name": (
                                details.get("employee_name")
                                if details
                                else item.employee_name
                            ),
                        }
                    )
                    self._progress.upsert_item(batch_job_id, item)
                    stage = _PHASE_TO_STAGE.get(phase)
                    if stage:
                        self._progress.mark_stage(
                            batch_job_id,
                            stage,
                            status="running",
                            job_status="running",
                            detail=f"Payslip {index + 1}/{total}: {phase}",
                        )

                try:
                    result = await self._pipeline.process(
                        content=split_bytes,
                        original_filename=self._split_filename(source_name, index),
                        organization_id=organization_id,
                        actor_user_id=actor_user_id,
                        progress=publish_phase,
                        batch_job_id=batch_job_id,
                        batch_item_id=item_id,
                        slip_index=index,
                        source_document_id=document_id,
                    )
                    item = self._item_from_result(
                        item_id=item_id,
                        slip_index=index,
                        result=result,
                    )
                except Exception as exc:  # noqa: BLE001 - isolate one bad payslip
                    item = BatchExtractedItem(
                        id=item_id,
                        slip_index=index,
                        status="failed",
                        processing_stage=current_phase,
                        error_message=str(exc) or exc.__class__.__name__,
                    )

                self._progress.upsert_item(batch_job_id, item)
                self._increment_counts(counts, item.status)
                if item.status == "failed":
                    failed_count += 1
                processed = index + 1
                self._progress.mark_stage(
                    batch_job_id,
                    _PHASE_TO_STAGE.get(item.processing_stage, "report"),
                    status="completed"
                    if item.status != "processing"
                    else "running",
                    job_status="running",
                    processed_slips=processed,
                    failed_slips=failed_count,
                    report_summary={"total": total, **counts},
                    detail=(
                        f"Processed payslip {processed}/{total}: {item.status}"
                    ),
                )
                completed_items.append(item.to_dict())

            for stage in ("ocr", "parser", "identify", "validation"):
                self._progress.mark_stage(
                    batch_job_id,
                    stage,
                    status="completed",
                    detail=f"Completed across {total} payslip(s)",
                )
            self._progress.mark_stage(
                batch_job_id,
                "report",
                status="completed",
                job_status="completed",
                processed_slips=total,
                failed_slips=failed_count,
                report_summary={"total": total, **counts},
                detail=f"Completed {total} payslip(s)",
            )
            return {
                "batch_job_id": batch_job_id,
                "total_slips": total,
                "items": completed_items,
                "status": "completed",
            }
        except Exception as exc:  # source download/split failure only
            self._progress.mark_stage(
                batch_job_id,
                "split",
                status="failed",
                job_status="failed",
                error_message=str(exc),
                detail=str(exc),
            )
            raise

    @staticmethod
    def _item_from_result(
        *,
        item_id: str,
        slip_index: int,
        result: BatchSlipPipelineResult,
    ) -> BatchExtractedItem:
        return BatchExtractedItem(
            id=item_id,
            slip_index=slip_index,
            status=result.status,
            employee_number=result.employee_number,
            employee_name=result.employee_name,
            document_id=str(result.document_id),
            national_id_masked=result.national_id_masked,
            payroll_year=result.payroll_year,
            payroll_month=result.payroll_month,
            warnings=result.warnings,
            critical_issues=result.critical_issues,
            processing_stage=result.processing_stage,
            validation_run_id=(
                str(result.validation_run_id)
                if result.validation_run_id is not None
                else None
            ),
            error_message=result.error_message,
        )

    @staticmethod
    def _increment_counts(counts: dict[str, int], status: str) -> None:
        counts["processing"] = max(0, counts["processing"] - 1)
        key = {
            "warning": "warnings",
            "unknown_employee": "unknown",
        }.get(status, status)
        if key in counts:
            counts[key] += 1
        else:
            counts["failed"] += 1

    @staticmethod
    def _split_filename(source_name: str, index: int) -> str:
        stem = Path(source_name).stem or "bulk-payslips"
        return f"{stem}-payslip-{index + 1}.pdf"

    def _split_pdf(self, pdf_bytes: bytes) -> list[bytes]:
        """Split a payroll package into one independent payslip per page.

        Bulk payroll files in this workflow are page packages: each page is a
        separate employee payslip. OCR cannot be used to discover boundaries
        here because scanned pages often have no embedded PDF text.
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            splits = [
                self._extract_pages(doc, [page_num])
                for page_num in range(len(doc))
            ]
            return splits or [pdf_bytes]
        finally:
            doc.close()

    @staticmethod
    def _extract_pages(doc: fitz.Document, page_indices: list[int]) -> bytes:
        new_doc = fitz.open()
        try:
            for index in page_indices:
                new_doc.insert_pdf(doc, from_page=index, to_page=index)
            return new_doc.tobytes()
        finally:
            new_doc.close()
