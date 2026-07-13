"""Catalog endpoints for extensible document types and validation modules."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from payroll_copilot.domain.document_types import list_document_types
from payroll_copilot.domain.validation_modules import list_validation_modules

router = APIRouter()


class DocumentTypeResponse(BaseModel):
    key: str
    label: str
    category: str
    supports_period: bool
    supports_ocr: bool
    supports_parser: bool
    supports_validation_modules: list[str] = Field(default_factory=list)
    collection_key: str
    sort_order: int


class ValidationModuleResponse(BaseModel):
    key: str
    label: str
    description: str
    supported_document_types: list[str] = Field(default_factory=list)
    rule_categories: list[str] = Field(default_factory=list)
    enabled: bool


@router.get("/document-types", response_model=list[DocumentTypeResponse])
async def get_document_types() -> list[DocumentTypeResponse]:
    return [
        DocumentTypeResponse(
            key=item.key,
            label=item.label,
            category=item.category,
            supports_period=item.supports_period,
            supports_ocr=item.supports_ocr,
            supports_parser=item.supports_parser,
            supports_validation_modules=list(item.supports_validation_modules),
            collection_key=item.collection_key,
            sort_order=item.sort_order,
        )
        for item in list_document_types()
    ]


@router.get("/validation-modules", response_model=list[ValidationModuleResponse])
async def get_validation_modules() -> list[ValidationModuleResponse]:
    return [
        ValidationModuleResponse(
            key=item.key,
            label=item.label,
            description=item.description,
            supported_document_types=list(item.supported_document_types),
            rule_categories=list(item.rule_categories),
            enabled=item.enabled,
        )
        for item in list_validation_modules()
    ]
