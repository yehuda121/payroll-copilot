"""Phase 1 Document Builder — layout/evidence → DocumentInstance.

Deterministic. No AI. No PAYSLIP_FIELD_KEYS. Reuses evidence_binder + layout_analysis.
"""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.services.evidence_binder import bind_evidence_candidates
from payroll_copilot.domain.document_model import (
    DOCUMENT_BUILDER_ID,
    DOCUMENT_MODEL_SCHEMA_VERSION,
    DocumentCell,
    DocumentColumn,
    DocumentEvidenceRef,
    DocumentGroup,
    DocumentInstance,
    DocumentLayoutRef,
    DocumentPage,
    DocumentRow,
    DocumentSection,
    DocumentSlot,
    DocumentTable,
    empty_document_instance,
)


def build_document_instance(
    layout_analysis: dict[str, Any] | None,
    *,
    evidence_bundle: dict[str, Any] | None = None,
    max_candidates: int = 400,
) -> DocumentInstance:
    """Construct a complete DocumentInstance from L0 layout + candidates.

    Preserves sections, tables, rows, columns, cells, and all evidence-backed
    slots (including unresolved values). Does not filter by payroll schema.
    """
    if not layout_analysis or not isinstance(layout_analysis, dict):
        return empty_document_instance(warning="document_builder_missing_layout_analysis")

    pages_raw = layout_analysis.get("pages") or []
    if not pages_raw:
        return empty_document_instance(warning="document_builder_empty_layout_pages")

    bundle = evidence_bundle
    if bundle is None or not isinstance(bundle, dict):
        bundle = bind_evidence_candidates(layout_analysis, max_candidates=max_candidates)

    pages: list[DocumentPage] = []
    sections: list[DocumentSection] = []
    tables: list[DocumentTable] = []
    rows: list[DocumentRow] = []
    columns: list[DocumentColumn] = []
    cells: list[DocumentCell] = []
    groups: list[DocumentGroup] = []

    column_ids_seen: set[str] = set()
    section_page: dict[str, int] = {}
    table_page: dict[str, int] = {}

    for page_raw in pages_raw:
        if not isinstance(page_raw, dict):
            continue
        page_num = int(page_raw.get("page") or 0)
        section_ids: list[str] = []
        table_ids: list[str] = []

        for sec in page_raw.get("sections") or []:
            if not isinstance(sec, dict) or not sec.get("id"):
                continue
            sec_id = str(sec["id"])
            section_ids.append(sec_id)
            section_page[sec_id] = page_num
            sections.append(
                DocumentSection(
                    id=sec_id,
                    title=None,
                    row_ids=[str(x) for x in (sec.get("row_ids") or []) if x],
                    table_ids=[str(x) for x in (sec.get("table_ids") or []) if x],
                    confidence=_conf(sec.get("confidence")),
                    layout=DocumentLayoutRef(
                        page=page_num,
                        section_id=sec_id,
                        bbox=_bbox(sec.get("bbox")),
                    ),
                )
            )
            groups.append(
                DocumentGroup(
                    id=f"grp_section_{sec_id}",
                    kind="section",
                    label=None,
                    section_id=sec_id,
                    page=page_num,
                )
            )

        for table in page_raw.get("tables") or []:
            if not isinstance(table, dict) or not table.get("id"):
                continue
            table_id = str(table["id"])
            table_ids.append(table_id)
            table_page[table_id] = page_num
            col_ids = [str(x) for x in (table.get("column_ids") or []) if x]
            tables.append(
                DocumentTable(
                    id=table_id,
                    row_ids=[str(x) for x in (table.get("row_ids") or []) if x],
                    column_ids=col_ids,
                    column_count=int(table.get("column_count") or len(col_ids) or 0),
                    confidence=_conf(table.get("confidence")),
                    layout=DocumentLayoutRef(
                        page=page_num,
                        table_id=table_id,
                        bbox=_bbox(table.get("bbox")),
                    ),
                )
            )
            groups.append(
                DocumentGroup(
                    id=f"grp_table_{table_id}",
                    kind="table",
                    label=None,
                    table_id=table_id,
                    page=page_num,
                )
            )

        for col in page_raw.get("columns") or []:
            if not isinstance(col, dict) or not col.get("id"):
                continue
            col_id = str(col["id"])
            if col_id in column_ids_seen:
                continue
            column_ids_seen.add(col_id)
            columns.append(
                DocumentColumn(
                    id=col_id,
                    index=int(col.get("index") or 0),
                    confidence=_conf(col.get("confidence")),
                    layout=DocumentLayoutRef(
                        page=page_num,
                        column_id=col_id,
                        column_index=int(col.get("index") or 0),
                    ),
                )
            )

        for row in page_raw.get("rows") or []:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            row_id = str(row["id"])
            rows.append(
                DocumentRow(
                    id=row_id,
                    cell_ids=[str(x) for x in (row.get("cell_ids") or []) if x],
                    confidence=_conf(row.get("confidence")),
                    layout=DocumentLayoutRef(
                        page=page_num,
                        section_id=_optional_str(row.get("section_id")),
                        table_id=_optional_str(row.get("table_id")),
                        row_id=row_id,
                        bbox=_bbox(row.get("bbox")),
                        reading_index=_optional_int(row.get("reading_index")),
                    ),
                )
            )

        for cell in page_raw.get("cells") or []:
            if not isinstance(cell, dict) or not cell.get("id"):
                continue
            cell_id = str(cell["id"])
            row_id = _optional_str(cell.get("row_id"))
            cells.append(
                DocumentCell(
                    id=cell_id,
                    text=str(cell.get("text") or ""),
                    token_kind=_optional_str(cell.get("token_kind")),
                    confidence=_conf(cell.get("confidence")),
                    layout=DocumentLayoutRef(
                        page=page_num,
                        row_id=row_id,
                        column_index=_optional_int(cell.get("column_index")),
                        bbox=_bbox(cell.get("bbox")),
                    ),
                    source_line_ids=[str(x) for x in (cell.get("source_line_ids") or []) if x],
                    source_word_ids=[str(x) for x in (cell.get("source_word_ids") or []) if x],
                )
            )

        pages.append(
            DocumentPage(
                page=page_num,
                width=_optional_float(page_raw.get("width")),
                height=_optional_float(page_raw.get("height")),
                section_ids=section_ids,
                table_ids=table_ids,
                confidence=_conf(page_raw.get("confidence")),
            )
        )

    slots = _slots_from_candidates(bundle.get("candidates") or [])
    _assign_group_members(groups, slots)

    # Unresolved labels (no value association) become label-only slots when not
    # already covered by a candidate label_cell_id.
    covered_label_cells = {
        sid
        for slot in slots
        for sid in ([slot.evidence.label_cell_id] if slot.evidence.label_cell_id else [])
    }
    for label_id in layout_analysis.get("unresolved_labels") or []:
        label_cell_id = str(label_id)
        if label_cell_id in covered_label_cells:
            continue
        cell = next((c for c in cells if c.id == label_cell_id), None)
        if cell is None or not str(cell.text or "").strip():
            continue
        slots.append(
            DocumentSlot(
                id=f"slot_unresolved_label_{label_cell_id}",
                kind="unresolved_label",
                label=str(cell.text).strip(),
                value=None,
                confidence=cell.confidence,
                layout=DocumentLayoutRef(
                    page=cell.layout.page,
                    row_id=cell.layout.row_id,
                    column_index=cell.layout.column_index,
                    bbox=cell.layout.bbox,
                ),
                evidence=DocumentEvidenceRef(
                    label_cell_id=label_cell_id,
                    source_line_ids=list(cell.source_line_ids),
                    source_word_ids=list(cell.source_word_ids),
                    relation="unresolved_label",
                ),
            )
        )

    warnings = list(dict.fromkeys([*(layout_analysis.get("warnings") or []), *(bundle.get("warnings") or [])]))
    warnings = [str(w) for w in warnings]

    layout_metadata: dict[str, Any] = {
        "layout_schema_version": layout_analysis.get("schema_version"),
        "layout_builder": layout_analysis.get("builder"),
        "association_engine": layout_analysis.get("association_engine"),
        "evidence_schema_version": bundle.get("schema_version"),
        "evidence_binder": bundle.get("binder"),
        "candidate_count": bundle.get("candidate_count"),
        "unresolved_labels": list(layout_analysis.get("unresolved_labels") or []),
        "unresolved_values": list(layout_analysis.get("unresolved_values") or []),
        "conflict_groups": list(layout_analysis.get("conflict_groups") or []),
    }
    if layout_analysis.get("layout_fingerprint"):
        layout_metadata["layout_fingerprint"] = layout_analysis.get("layout_fingerprint")
    if layout_analysis.get("fingerprint_features"):
        layout_metadata["fingerprint_features"] = dict(layout_analysis.get("fingerprint_features") or {})

    return DocumentInstance(
        schema_version=DOCUMENT_MODEL_SCHEMA_VERSION,
        builder=DOCUMENT_BUILDER_ID,
        pages=pages,
        sections=sections,
        groups=groups,
        tables=tables,
        rows=rows,
        columns=columns,
        cells=cells,
        slots=slots,
        layout_metadata=layout_metadata,
        warnings=warnings,
        slot_count=len(slots),
        cell_count=len(cells),
    )


def build_document_model_dict(
    layout_analysis: dict[str, Any] | None,
    *,
    evidence_bundle: dict[str, Any] | None = None,
    max_candidates: int = 400,
) -> dict[str, Any]:
    """Convenience: DocumentInstance as a plain dict for persistence."""
    return build_document_instance(
        layout_analysis,
        evidence_bundle=evidence_bundle,
        max_candidates=max_candidates,
    ).to_dict()


def _slots_from_candidates(candidates: list[Any]) -> list[DocumentSlot]:
    slots: list[DocumentSlot] = []
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        candidate_id = str(cand.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        relation = _optional_str(cand.get("relation")) or "association"
        kind = "unresolved_value" if relation == "unresolved_value" else "field"
        label = _optional_str(cand.get("label_text"))
        value_text = cand.get("value_text")
        value: Any = value_text if value_text is not None else None
        if isinstance(value, str):
            value = value.strip() if value.strip() else None

        section_id = _optional_str(cand.get("section_id"))
        table_id = None  # candidates do not carry table_id; group assignment fills group_id
        group_id = f"grp_section_{section_id}" if section_id else None

        score_raw = cand.get("score")
        try:
            score = float(score_raw) if score_raw is not None and score_raw != "" else None
        except (TypeError, ValueError):
            score = None

        slots.append(
            DocumentSlot(
                id=f"slot_{candidate_id}",
                kind=kind,
                label=label,
                value=value,
                confidence=_conf(cand.get("confidence")),
                layout=DocumentLayoutRef(
                    page=_optional_int(cand.get("page")),
                    section_id=section_id,
                    group_id=group_id,
                    table_id=table_id,
                    row_id=_optional_str(cand.get("row_id")),
                    column_index=_optional_int(cand.get("column_index")),
                    bbox=_bbox(cand.get("bbox")),
                ),
                evidence=DocumentEvidenceRef(
                    candidate_ids=[candidate_id],
                    association_id=_optional_str(cand.get("association_id")),
                    label_cell_id=_optional_str(cand.get("label_cell_id")),
                    value_cell_id=_optional_str(cand.get("value_cell_id")),
                    source_line_ids=[str(x) for x in (cand.get("source_line_ids") or []) if x],
                    source_word_ids=[str(x) for x in (cand.get("source_word_ids") or []) if x],
                    relation=relation,
                    score=score,
                    conflict=bool(cand.get("conflict") or False),
                ),
                metadata={
                    k: cand[k]
                    for k in ("normalized_value",)
                    if cand.get(k) is not None
                },
            )
        )
    return slots


def _assign_group_members(groups: list[DocumentGroup], slots: list[DocumentSlot]) -> None:
    by_id = {g.id: g for g in groups}
    for slot in slots:
        group_id = slot.layout.group_id
        if group_id and group_id in by_id:
            by_id[group_id].member_slot_ids.append(slot.id)
            continue
        # Fallback: match by section_id / table via row layout if group_id unset.
        section_id = slot.layout.section_id
        if section_id:
            gid = f"grp_section_{section_id}"
            if gid in by_id:
                slot.layout.group_id = gid
                by_id[gid].member_slot_ids.append(slot.id)


def _bbox(raw: Any) -> list[float] | None:
    if not isinstance(raw, list) or len(raw) < 4:
        return None
    try:
        return [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])]
    except (TypeError, ValueError):
        return None


def _conf(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


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
