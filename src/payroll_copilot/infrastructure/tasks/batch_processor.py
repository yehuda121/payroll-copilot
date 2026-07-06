"""Batch payslip PDF processor."""

from __future__ import annotations

import hashlib
from uuid import uuid4

import fitz

from payroll_copilot.infrastructure.config.settings import get_settings


class BatchPayslipProcessor:
    """Processes bulk PDF containing multiple payslips."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def process(self, batch_job_id: str, document_id: str) -> dict:
        """Split PDF, create child documents, queue validation for each slip."""
        from payroll_copilot.infrastructure.storage.s3_storage import S3ObjectStorage

        storage = S3ObjectStorage(
            endpoint=self._settings.s3_endpoint,
            access_key=self._settings.s3_access_key,
            secret_key=self._settings.s3_secret_key,
            bucket=self._settings.s3_bucket,
            region=self._settings.s3_region,
            use_ssl=self._settings.s3_use_ssl,
        )

        storage_key = f"documents/{document_id}"
        import asyncio

        pdf_bytes = asyncio.get_event_loop().run_until_complete(storage.download(storage_key))

        splits = self._split_pdf(pdf_bytes)
        child_documents = []

        for i, split_bytes in enumerate(splits):
            child_id = str(uuid4())
            child_key = f"documents/{child_id}"
            asyncio.get_event_loop().run_until_complete(
                storage.upload(child_key, split_bytes, "application/pdf")
            )
            child_documents.append({
                "document_id": child_id,
                "slip_index": i,
                "storage_key": child_key,
            })

        return {
            "batch_job_id": batch_job_id,
            "total_slips": len(splits),
            "child_documents": child_documents,
            "status": "split_complete",
        }

    def _split_pdf(self, pdf_bytes: bytes) -> list[bytes]:
        """Split PDF into individual payslips using page boundary detection."""
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
