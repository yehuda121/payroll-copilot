"""Versioned Document Model — layout-grounded document instance (Phase 0).

This is the future source of truth for extraction review and template learning.
It does **not** depend on PAYSLIP_FIELD_KEYS or StructuredPayslipParse.

Layering (Document-First architecture):
  L0  layout_analysis + evidence candidates (existing)
  L1  DocumentInstance (this module)
  L2  StructuredPayslipParse (canonical projection — separate)

Schema is additive and versioned via ``DOCUMENT_MODEL_SCHEMA_VERSION``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

DOCUMENT_MODEL_SCHEMA_VERSION = 1
DOCUMENT_BUILDER_ID = "document_builder_v1"


@dataclass
class DocumentLayoutRef:
    """Geometric placement within the reconstructed document."""

    page: int | None = None
    section_id: str | None = None
    group_id: str | None = None
    table_id: str | None = None
    row_id: str | None = None
    column_id: str | None = None
    column_index: int | None = None
    bbox: list[float] | None = None
    reading_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> DocumentLayoutRef:
        if not isinstance(raw, dict):
            return cls()
        bbox = raw.get("bbox")
        bbox_list: list[float] | None = None
        if isinstance(bbox, list) and len(bbox) >= 4:
            try:
                bbox_list = [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]
            except (TypeError, ValueError):
                bbox_list = None
        return cls(
            page=_optional_int(raw.get("page")),
            section_id=_optional_str(raw.get("section_id")),
            group_id=_optional_str(raw.get("group_id")),
            table_id=_optional_str(raw.get("table_id")),
            row_id=_optional_str(raw.get("row_id")),
            column_id=_optional_str(raw.get("column_id")),
            column_index=_optional_int(raw.get("column_index")),
            bbox=bbox_list,
            reading_index=_optional_int(raw.get("reading_index")),
        )


@dataclass
class DocumentEvidenceRef:
    """Links a slot back to L0 evidence / candidates."""

    candidate_ids: list[str] = field(default_factory=list)
    association_id: str | None = None
    label_cell_id: str | None = None
    value_cell_id: str | None = None
    source_line_ids: list[str] = field(default_factory=list)
    source_word_ids: list[str] = field(default_factory=list)
    relation: str | None = None
    score: float | None = None
    conflict: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> DocumentEvidenceRef:
        if not isinstance(raw, dict):
            return cls()
        score_raw = raw.get("score")
        score: float | None
        try:
            score = float(score_raw) if score_raw is not None and score_raw != "" else None
        except (TypeError, ValueError):
            score = None
        return cls(
            candidate_ids=[str(x) for x in (raw.get("candidate_ids") or []) if x],
            association_id=_optional_str(raw.get("association_id")),
            label_cell_id=_optional_str(raw.get("label_cell_id")),
            value_cell_id=_optional_str(raw.get("value_cell_id")),
            source_line_ids=[str(x) for x in (raw.get("source_line_ids") or []) if x],
            source_word_ids=[str(x) for x in (raw.get("source_word_ids") or []) if x],
            relation=_optional_str(raw.get("relation")),
            score=score,
            conflict=bool(raw.get("conflict") or False),
        )


@dataclass
class DocumentSlot:
    """Addressable label/value (or unlabeled value) — open schema, not payroll keys."""

    id: str
    kind: str
    label: str | None = None
    value: Any = None
    confidence: str | None = None
    layout: DocumentLayoutRef = field(default_factory=DocumentLayoutRef)
    evidence: DocumentEvidenceRef = field(default_factory=DocumentEvidenceRef)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "value": self.value,
            "confidence": self.confidence,
            "layout": self.layout.to_dict(),
            "evidence": self.evidence.to_dict(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DocumentSlot:
        return cls(
            id=str(raw.get("id") or ""),
            kind=str(raw.get("kind") or "field"),
            label=_optional_str(raw.get("label")),
            value=raw.get("value"),
            confidence=_optional_str(raw.get("confidence")),
            layout=DocumentLayoutRef.from_dict(
                raw.get("layout") if isinstance(raw.get("layout"), dict) else None
            ),
            evidence=DocumentEvidenceRef.from_dict(
                raw.get("evidence") if isinstance(raw.get("evidence"), dict) else None
            ),
            metadata=dict(raw.get("metadata") or {})
            if isinstance(raw.get("metadata"), dict)
            else {},
        )


@dataclass
class DocumentCell:
    id: str
    text: str = ""
    token_kind: str | None = None
    confidence: str | None = None
    layout: DocumentLayoutRef = field(default_factory=DocumentLayoutRef)
    source_line_ids: list[str] = field(default_factory=list)
    source_word_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "token_kind": self.token_kind,
            "confidence": self.confidence,
            "layout": self.layout.to_dict(),
            "source_line_ids": list(self.source_line_ids),
            "source_word_ids": list(self.source_word_ids),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DocumentCell:
        return cls(
            id=str(raw.get("id") or ""),
            text=str(raw.get("text") or ""),
            token_kind=_optional_str(raw.get("token_kind")),
            confidence=_optional_str(raw.get("confidence")),
            layout=DocumentLayoutRef.from_dict(
                raw.get("layout") if isinstance(raw.get("layout"), dict) else None
            ),
            source_line_ids=[str(x) for x in (raw.get("source_line_ids") or []) if x],
            source_word_ids=[str(x) for x in (raw.get("source_word_ids") or []) if x],
        )


@dataclass
class DocumentRow:
    id: str
    cell_ids: list[str] = field(default_factory=list)
    confidence: str | None = None
    layout: DocumentLayoutRef = field(default_factory=DocumentLayoutRef)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cell_ids": list(self.cell_ids),
            "confidence": self.confidence,
            "layout": self.layout.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DocumentRow:
        return cls(
            id=str(raw.get("id") or ""),
            cell_ids=[str(x) for x in (raw.get("cell_ids") or []) if x],
            confidence=_optional_str(raw.get("confidence")),
            layout=DocumentLayoutRef.from_dict(
                raw.get("layout") if isinstance(raw.get("layout"), dict) else None
            ),
        )


@dataclass
class DocumentColumn:
    id: str
    index: int = 0
    confidence: str | None = None
    layout: DocumentLayoutRef = field(default_factory=DocumentLayoutRef)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "index": self.index,
            "confidence": self.confidence,
            "layout": self.layout.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DocumentColumn:
        return cls(
            id=str(raw.get("id") or ""),
            index=int(raw.get("index") or 0),
            confidence=_optional_str(raw.get("confidence")),
            layout=DocumentLayoutRef.from_dict(
                raw.get("layout") if isinstance(raw.get("layout"), dict) else None
            ),
        )


@dataclass
class DocumentTable:
    id: str
    row_ids: list[str] = field(default_factory=list)
    column_ids: list[str] = field(default_factory=list)
    column_count: int = 0
    confidence: str | None = None
    layout: DocumentLayoutRef = field(default_factory=DocumentLayoutRef)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "row_ids": list(self.row_ids),
            "column_ids": list(self.column_ids),
            "column_count": self.column_count,
            "confidence": self.confidence,
            "layout": self.layout.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DocumentTable:
        return cls(
            id=str(raw.get("id") or ""),
            row_ids=[str(x) for x in (raw.get("row_ids") or []) if x],
            column_ids=[str(x) for x in (raw.get("column_ids") or []) if x],
            column_count=int(raw.get("column_count") or 0),
            confidence=_optional_str(raw.get("confidence")),
            layout=DocumentLayoutRef.from_dict(
                raw.get("layout") if isinstance(raw.get("layout"), dict) else None
            ),
        )


@dataclass
class DocumentSection:
    id: str
    title: str | None = None
    row_ids: list[str] = field(default_factory=list)
    table_ids: list[str] = field(default_factory=list)
    confidence: str | None = None
    layout: DocumentLayoutRef = field(default_factory=DocumentLayoutRef)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "row_ids": list(self.row_ids),
            "table_ids": list(self.table_ids),
            "confidence": self.confidence,
            "layout": self.layout.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DocumentSection:
        return cls(
            id=str(raw.get("id") or ""),
            title=_optional_str(raw.get("title")),
            row_ids=[str(x) for x in (raw.get("row_ids") or []) if x],
            table_ids=[str(x) for x in (raw.get("table_ids") or []) if x],
            confidence=_optional_str(raw.get("confidence")),
            layout=DocumentLayoutRef.from_dict(
                raw.get("layout") if isinstance(raw.get("layout"), dict) else None
            ),
        )


@dataclass
class DocumentGroup:
    """Logical grouping for UI / future template learning (section- or table-backed)."""

    id: str
    kind: str
    label: str | None = None
    member_slot_ids: list[str] = field(default_factory=list)
    section_id: str | None = None
    table_id: str | None = None
    page: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "member_slot_ids": list(self.member_slot_ids),
            "section_id": self.section_id,
            "table_id": self.table_id,
            "page": self.page,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DocumentGroup:
        return cls(
            id=str(raw.get("id") or ""),
            kind=str(raw.get("kind") or "custom"),
            label=_optional_str(raw.get("label")),
            member_slot_ids=[str(x) for x in (raw.get("member_slot_ids") or []) if x],
            section_id=_optional_str(raw.get("section_id")),
            table_id=_optional_str(raw.get("table_id")),
            page=_optional_int(raw.get("page")),
            metadata=dict(raw.get("metadata") or {})
            if isinstance(raw.get("metadata"), dict)
            else {},
        )


@dataclass
class DocumentPage:
    page: int
    width: float | None = None
    height: float | None = None
    section_ids: list[str] = field(default_factory=list)
    table_ids: list[str] = field(default_factory=list)
    confidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "width": self.width,
            "height": self.height,
            "section_ids": list(self.section_ids),
            "table_ids": list(self.table_ids),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DocumentPage:
        return cls(
            page=int(raw.get("page") or 0),
            width=_optional_float(raw.get("width")),
            height=_optional_float(raw.get("height")),
            section_ids=[str(x) for x in (raw.get("section_ids") or []) if x],
            table_ids=[str(x) for x in (raw.get("table_ids") or []) if x],
            confidence=_optional_str(raw.get("confidence")),
        )


@dataclass
class DocumentInstance:
    """Complete reconstructed document (L1). Independent of canonical payroll fields."""

    schema_version: int = DOCUMENT_MODEL_SCHEMA_VERSION
    builder: str = DOCUMENT_BUILDER_ID
    pages: list[DocumentPage] = field(default_factory=list)
    sections: list[DocumentSection] = field(default_factory=list)
    groups: list[DocumentGroup] = field(default_factory=list)
    tables: list[DocumentTable] = field(default_factory=list)
    rows: list[DocumentRow] = field(default_factory=list)
    columns: list[DocumentColumn] = field(default_factory=list)
    cells: list[DocumentCell] = field(default_factory=list)
    slots: list[DocumentSlot] = field(default_factory=list)
    layout_metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    slot_count: int = 0
    cell_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "builder": self.builder,
            "pages": [p.to_dict() for p in self.pages],
            "sections": [s.to_dict() for s in self.sections],
            "groups": [g.to_dict() for g in self.groups],
            "tables": [t.to_dict() for t in self.tables],
            "rows": [r.to_dict() for r in self.rows],
            "columns": [c.to_dict() for c in self.columns],
            "cells": [c.to_dict() for c in self.cells],
            "slots": [s.to_dict() for s in self.slots],
            "layout_metadata": dict(self.layout_metadata),
            "warnings": list(self.warnings),
            "slot_count": self.slot_count,
            "cell_count": self.cell_count,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> DocumentInstance:
        if not isinstance(raw, dict) or not raw:
            return empty_document_instance()
        return cls(
            schema_version=int(raw.get("schema_version") or DOCUMENT_MODEL_SCHEMA_VERSION),
            builder=str(raw.get("builder") or DOCUMENT_BUILDER_ID),
            pages=[
                DocumentPage.from_dict(item)
                for item in (raw.get("pages") or [])
                if isinstance(item, dict)
            ],
            sections=[
                DocumentSection.from_dict(item)
                for item in (raw.get("sections") or [])
                if isinstance(item, dict)
            ],
            groups=[
                DocumentGroup.from_dict(item)
                for item in (raw.get("groups") or [])
                if isinstance(item, dict)
            ],
            tables=[
                DocumentTable.from_dict(item)
                for item in (raw.get("tables") or [])
                if isinstance(item, dict)
            ],
            rows=[
                DocumentRow.from_dict(item)
                for item in (raw.get("rows") or [])
                if isinstance(item, dict)
            ],
            columns=[
                DocumentColumn.from_dict(item)
                for item in (raw.get("columns") or [])
                if isinstance(item, dict)
            ],
            cells=[
                DocumentCell.from_dict(item)
                for item in (raw.get("cells") or [])
                if isinstance(item, dict)
            ],
            slots=[
                DocumentSlot.from_dict(item)
                for item in (raw.get("slots") or [])
                if isinstance(item, dict)
            ],
            layout_metadata=dict(raw.get("layout_metadata") or {})
            if isinstance(raw.get("layout_metadata"), dict)
            else {},
            warnings=[str(w) for w in (raw.get("warnings") or [])],
            slot_count=int(raw.get("slot_count") or 0),
            cell_count=int(raw.get("cell_count") or 0),
        )


def empty_document_instance(*, warning: str | None = None) -> DocumentInstance:
    warnings = [warning] if warning else []
    return DocumentInstance(warnings=warnings)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
