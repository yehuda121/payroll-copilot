"""Mapper between DocumentExtraction domain entity and ORM model."""

from __future__ import annotations

from decimal import Decimal

from payroll_copilot.domain.entities import DocumentExtraction
from payroll_copilot.infrastructure.persistence.models import DocumentExtractionModel


def extraction_to_entity(model: DocumentExtractionModel) -> DocumentExtraction:
    overall: float | None = None
    if model.overall_confidence is not None:
        overall = float(model.overall_confidence)
    return DocumentExtraction(
        id=model.id,
        document_id=model.document_id,
        engine=model.engine,
        raw_text=model.raw_text or "",
        structured_data=dict(model.structured_data or {}),
        overall_confidence=overall,
        field_confidences={
            str(k): float(v)
            for k, v in dict(model.field_confidences or {}).items()
            if v is not None
        },
        extraction_version=model.extraction_version,
        created_at=model.created_at,
        ocr_result=dict(model.ocr_result or {}),
        # Runtime persistence is DynamoDB; legacy SQL may lack this column.
        layout_snapshot=dict(getattr(model, "layout_snapshot", None) or {}),
        layout_analysis=dict(getattr(model, "layout_analysis", None) or {}),
        parser_model=model.parser_model,
        language=model.language or "auto",
        ocr_status=model.ocr_status,
        parser_status=model.parser_status,
        warnings=list(model.warnings or []),
        error_message=model.error_message,
        updated_at=model.updated_at,
        confirmation_status=getattr(model, "confirmation_status", None) or "review_required",
        confirmed_at=getattr(model, "confirmed_at", None),
        confirmed_by=getattr(model, "confirmed_by", None),
    )


def extraction_to_model(entity: DocumentExtraction) -> DocumentExtractionModel:
    overall = None
    if entity.overall_confidence is not None:
        overall = Decimal(str(round(entity.overall_confidence, 3)))
    return DocumentExtractionModel(
        id=entity.id,
        document_id=entity.document_id,
        extraction_version=entity.extraction_version,
        engine=entity.engine,
        parser_model=entity.parser_model,
        language=entity.language,
        ocr_status=entity.ocr_status,
        parser_status=entity.parser_status,
        raw_text=entity.raw_text,
        ocr_result=entity.ocr_result,
        structured_data=entity.structured_data,
        field_confidences=entity.field_confidences,
        overall_confidence=overall,
        warnings=entity.warnings,
        error_message=entity.error_message,
        confirmation_status=entity.confirmation_status or "review_required",
        confirmed_at=entity.confirmed_at,
        confirmed_by=entity.confirmed_by,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )
