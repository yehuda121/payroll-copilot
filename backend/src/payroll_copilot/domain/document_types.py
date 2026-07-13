"""Extensible document-type registry for accountant portal and pipelines.

New document types register metadata and capabilities without changing UI shells.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from payroll_copilot.domain.enums import DocumentType


class ExpectedDocumentAvailability(StrEnum):
    """UI/status vocabulary for expected documents on an employee profile."""

    AVAILABLE = "available"
    MISSING = "missing"
    PROCESSING = "processing"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"
    VERSIONED = "versioned"


@dataclass(frozen=True, slots=True)
class DocumentTypeDefinition:
    """Capability metadata for one document type."""

    key: str
    label: str
    category: str
    supports_period: bool = False
    supports_ocr: bool = False
    supports_parser: bool = False
    supports_validation_modules: tuple[str, ...] = ()
    collection_key: str = "documents"
    sort_order: int = 100
    domain_type: DocumentType | None = None
    metadata: dict[str, str] = field(default_factory=dict)


_REGISTRY: dict[str, DocumentTypeDefinition] = {}


def register_document_type(definition: DocumentTypeDefinition) -> DocumentTypeDefinition:
    _REGISTRY[definition.key] = definition
    return definition


def get_document_type(key: str) -> DocumentTypeDefinition | None:
    return _REGISTRY.get(key)


def list_document_types() -> list[DocumentTypeDefinition]:
    return sorted(_REGISTRY.values(), key=lambda item: (item.sort_order, item.label))


def _bootstrap_builtin_document_types() -> None:
    if _REGISTRY:
        return
    register_document_type(
        DocumentTypeDefinition(
            key="payslip",
            label="Payslips",
            category="payroll",
            supports_period=True,
            supports_ocr=True,
            supports_parser=True,
            supports_validation_modules=("payroll",),
            collection_key="payslips",
            sort_order=10,
            domain_type=DocumentType.PAYSLIP,
        )
    )
    register_document_type(
        DocumentTypeDefinition(
            key="attendance",
            label="Attendance Reports",
            category="attendance",
            supports_period=True,
            supports_ocr=True,
            supports_validation_modules=("attendance",),
            collection_key="attendance",
            sort_order=20,
            domain_type=DocumentType.ATTENDANCE,
        )
    )
    register_document_type(
        DocumentTypeDefinition(
            key="contract",
            label="Employment Contracts",
            category="employment",
            supports_ocr=True,
            supports_validation_modules=("contract",),
            collection_key="contracts",
            sort_order=30,
            domain_type=DocumentType.CONTRACT,
        )
    )
    register_document_type(
        DocumentTypeDefinition(
            key="national_id",
            label="Israeli ID",
            category="identity",
            supports_ocr=True,
            supports_validation_modules=("identity",),
            collection_key="identity",
            sort_order=40,
            domain_type=DocumentType.NATIONAL_ID,
        )
    )
    register_document_type(
        DocumentTypeDefinition(
            key="id_appendix",
            label="ID Appendix",
            category="identity",
            supports_ocr=True,
            collection_key="identity",
            sort_order=45,
            domain_type=DocumentType.ID_APPENDIX,
        )
    )


_bootstrap_builtin_document_types()
