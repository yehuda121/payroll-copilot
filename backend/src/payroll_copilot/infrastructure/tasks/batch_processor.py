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
from payroll_copilot.application.services.payslip_boundary_detector import (
    PayslipBoundary,
    PayslipBoundaryDetectionResult,
    PayslipBoundaryDetector,
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
        boundary_detector: PayslipBoundaryDetector | None = None,
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
        self._boundary_detector = boundary_detector or PayslipBoundaryDetector()

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
        worker_id = f"worker-{uuid4()}"

        if not self._progress.try_claim_processing(batch_job_id, worker_id=worker_id):
            current = self._progress.get(batch_job_id)
            return {
                "batch_job_id": batch_job_id,
                "status": "skipped_duplicate",
                "existing_status": current.status if current else "missing",
            }

        try:
            self._progress.mark_stage(
                batch_job_id,
                "split",
                status="running",
                job_status="running",
                detail="Downloading and splitting the source PDF",
            )
            pdf_bytes = await self._storage.download(f"documents/{document_id}")
            detection = await self._detect_boundaries(pdf_bytes)
            boundaries = list(detection.boundaries) or [
                PayslipBoundary(
                    page_indices=(0,),
                    confidence=0.5,
                    strategy="one_page_fallback",
                    warnings=("empty_boundaries",),
                )
            ]
            total = len(boundaries)
            split_detail = f"Split into {total} payslip(s) via {detection.strategy}"
            if detection.warnings:
                split_detail = f"{split_detail}; {', '.join(detection.warnings)}"
            self._progress.mark_stage(
                batch_job_id,
                "split",
                status="completed",
                total_slips=total,
                detail=split_detail,
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

            # Keep source PDF open and extract one slip at a time to reduce peak RAM.
            source_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            try:
                # Drop the full-bytes reference after open when possible; PyMuPDF keeps
                # its own buffer. Bound memory by not retaining all split PDFs.
                pdf_bytes = b""

                for index, boundary in enumerate(boundaries):
                    item_id = str(uuid4())
                    item = BatchExtractedItem(
                        id=item_id,
                        slip_index=index,
                        status="processing",
                        processing_stage="queued",
                        page_start=boundary.page_start,
                        page_end=boundary.page_end,
                        split_confidence=boundary.confidence,
                        split_strategy=boundary.strategy,
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

                    split_bytes = self._extract_pages(
                        source_doc,
                        list(boundary.page_indices),
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
                            boundary=boundary,
                        )
                    except Exception as exc:  # noqa: BLE001 - isolate one bad payslip
                        item = BatchExtractedItem(
                            id=item_id,
                            slip_index=index,
                            status="failed",
                            processing_stage=current_phase,
                            error_message=str(exc) or exc.__class__.__name__,
                            page_start=boundary.page_start,
                            page_end=boundary.page_end,
                            split_confidence=boundary.confidence,
                            split_strategy=boundary.strategy,
                        )
                    finally:
                        del split_bytes

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
            finally:
                source_doc.close()

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

    async def _detect_boundaries(
        self,
        pdf_bytes: bytes,
    ) -> PayslipBoundaryDetectionResult:
        """Run deterministic detection; AI only when already inside this async path."""
        return await self._boundary_detector.detect_async(
            pdf_bytes,
            ai_splitter=None,
        )

    def _materialize_splits(
        self,
        pdf_bytes: bytes,
        detection: PayslipBoundaryDetectionResult,
    ) -> list[tuple[bytes, PayslipBoundary]]:
        if not detection.boundaries:
            return [(pdf_bytes, PayslipBoundary(
                page_indices=(0,),
                confidence=0.5,
                strategy="one_page_fallback",
                warnings=("empty_boundaries",),
            ))]

        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            return [
                (
                    self._extract_pages(document, list(boundary.page_indices)),
                    boundary,
                )
                for boundary in detection.boundaries
            ]
        finally:
            document.close()

    @staticmethod
    def _item_from_result(
        *,
        item_id: str,
        slip_index: int,
        result: BatchSlipPipelineResult,
        boundary: PayslipBoundary,
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
            page_start=boundary.page_start,
            page_end=boundary.page_end,
            split_confidence=boundary.confidence,
            split_strategy=boundary.strategy,
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
        """Split a payroll package using the smart boundary detector.

        Deterministic text anchors group multi-page slips at high confidence.
        Scanned or ambiguous packages fall back to one payslip per page.
        """
        detection = self._boundary_detector.detect(pdf_bytes)
        return [payload for payload, _boundary in self._materialize_splits(pdf_bytes, detection)]

    @staticmethod
    def _extract_pages(doc: fitz.Document, page_indices: list[int]) -> bytes:
        new_doc = fitz.open()
        try:
            for index in page_indices:
                new_doc.insert_pdf(doc, from_page=index, to_page=index)
            return new_doc.tobytes()
        finally:
            new_doc.close()
