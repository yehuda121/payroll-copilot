"""DocumentInstance review editor — sole writer of review mutations (Phase 2).

Edits are versioned slot updates. Never patches structured_data / L2.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from payroll_copilot.domain.document_model import (
    DOCUMENT_BUILDER_ID,
    DOCUMENT_MODEL_SCHEMA_VERSION,
    DocumentInstance,
    DocumentLayoutRef,
    DocumentSlot,
)


@dataclass(frozen=True, slots=True)
class ReviewLineEdit:
    line_id: str | None = None
    display_label: str | None = None
    value: Any = None
    delete: bool = False
    add: bool = False


def apply_review_edits(
    instance: DocumentInstance | dict[str, Any] | None,
    edits: list[ReviewLineEdit],
) -> DocumentInstance:
    """Apply review-line commands to a DocumentInstance (new object)."""
    doc = (
        deepcopy(instance)
        if isinstance(instance, DocumentInstance)
        else DocumentInstance.from_dict(instance or {})
    )
    slots_by_id = {slot.id: slot for slot in doc.slots}

    for edit in edits:
        if edit.add:
            label = (edit.display_label or "").strip() or None
            new_id = edit.line_id or f"slot_user_{uuid4().hex[:12]}"
            slots_by_id[new_id] = DocumentSlot(
                id=new_id,
                kind="field",
                label=label,
                value=None if edit.value is None and edit.display_label is None else edit.value,
                layout=DocumentLayoutRef(),
                metadata={"source": "user"},
            )
            continue

        if not edit.line_id:
            continue
        target = slots_by_id.get(edit.line_id)
        if target is None:
            continue
        if edit.delete:
            slots_by_id.pop(edit.line_id, None)
            continue
        if edit.display_label is not None:
            target.label = edit.display_label.strip() or None
        # Allow explicit clear when value key present as None via edit
        target.value = edit.value
        meta = dict(target.metadata or {})
        meta["source"] = "user"
        target.metadata = meta

    slots = list(slots_by_id.values())
    return DocumentInstance(
        schema_version=doc.schema_version or DOCUMENT_MODEL_SCHEMA_VERSION,
        builder=doc.builder or DOCUMENT_BUILDER_ID,
        pages=list(doc.pages),
        sections=list(doc.sections),
        groups=list(doc.groups),
        tables=list(doc.tables),
        rows=list(doc.rows),
        columns=list(doc.columns),
        cells=list(doc.cells),
        slots=slots,
        layout_metadata=dict(doc.layout_metadata or {}),
        warnings=list(doc.warnings or []),
        slot_count=len(slots),
        cell_count=doc.cell_count,
    )


def replace_review_lines(
    instance: DocumentInstance | dict[str, Any] | None,
    lines: list[dict[str, Any]],
) -> DocumentInstance:
    """Replace slot values/labels from a full review-lines snapshot."""
    edits: list[ReviewLineEdit] = []
    seen: set[str] = set()
    for raw in lines:
        if not isinstance(raw, dict):
            continue
        line_id = str(raw.get("line_id") or "").strip()
        if not line_id:
            continue
        seen.add(line_id)
        edits.append(
            ReviewLineEdit(
                line_id=line_id,
                display_label=raw.get("display_label"),
                value=raw.get("value"),
            )
        )
    doc = apply_review_edits(instance, edits)
    # Delete slots missing from the snapshot when snapshot is authoritative
    if lines:
        keep = {e.line_id for e in edits if e.line_id}
        remaining = [slot for slot in doc.slots if slot.id in keep]
        # Also allow newly added lines without prior id
        for raw in lines:
            if not isinstance(raw, dict):
                continue
            line_id = str(raw.get("line_id") or "").strip()
            if line_id and line_id not in {s.id for s in remaining}:
                remaining.append(
                    DocumentSlot(
                        id=line_id,
                        kind="field",
                        label=(str(raw.get("display_label") or "").strip() or None),
                        value=raw.get("value"),
                        layout=DocumentLayoutRef(),
                        metadata={"source": "user"},
                    )
                )
        return DocumentInstance(
            schema_version=doc.schema_version,
            builder=doc.builder,
            pages=list(doc.pages),
            sections=list(doc.sections),
            groups=list(doc.groups),
            tables=list(doc.tables),
            rows=list(doc.rows),
            columns=list(doc.columns),
            cells=list(doc.cells),
            slots=remaining,
            layout_metadata=dict(doc.layout_metadata or {}),
            warnings=list(doc.warnings or []),
            slot_count=len(remaining),
            cell_count=doc.cell_count,
        )
    return doc
