"""Post-extraction review materializer — curated DocumentInstance.slots surface.

Sole choke point that turns an enriched Document (template or AI) into the
authoritative review/edit SoT. Does not invent values. Does not write L2.

Invariants:
- Pure and idempotent (stable slot ids; no UUID/time side effects).
- Preserves layout structure, evidence, and candidate_ids on survivors.
- Preserves all ``source=user`` slots.
- One slot per canonical_key; one slot per unique non-canonical label.
- Open-schema: unknown business labels survive; OCR duplicate fan-out does not.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from payroll_copilot.application.services.layout_fingerprint import normalize_label
from payroll_copilot.domain.document_model import DocumentInstance, DocumentSlot

REVIEW_MATERIALIZED_META_KEY = "review_materialized"
REVIEW_MATERIALIZER_ID = "document_review_materializer_v1"

_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2, "unknown": 3}


def materialize_review_document(
    instance: DocumentInstance | dict[str, Any] | None,
) -> DocumentInstance:
    """Return a DocumentInstance whose ``slots`` are the curated review surface.

    Layout collections (pages/cells/tables/…) are preserved unchanged.
    """
    doc = (
        deepcopy(instance)
        if isinstance(instance, DocumentInstance)
        else DocumentInstance.from_dict(instance or {})
    )
    curated = _curate_slots(list(doc.slots))
    doc.slots = curated
    doc.slot_count = len(curated)
    meta = dict(doc.layout_metadata or {})
    meta[REVIEW_MATERIALIZED_META_KEY] = True
    meta["review_materializer"] = REVIEW_MATERIALIZER_ID
    doc.layout_metadata = meta
    return doc


def _curate_slots(slots: list[DocumentSlot]) -> list[DocumentSlot]:
    """Deterministic dedupe; survivors keep their original slot ids."""
    if not slots:
        return []

    # source=user slots always survive as themselves (keyed by id).
    user_slots: list[DocumentSlot] = []
    system_slots: list[tuple[int, DocumentSlot]] = []
    for index, slot in enumerate(slots):
        if _is_user_slot(slot):
            user_slots.append(slot)
        else:
            system_slots.append((index, slot))

    groups: dict[str, list[tuple[int, DocumentSlot]]] = {}
    for index, slot in system_slots:
        if not _is_review_candidate(slot):
            continue
        key = _group_key(slot)
        groups.setdefault(key, []).append((index, slot))

    winners: list[tuple[tuple, DocumentSlot]] = []
    for group in groups.values():
        winner_index, winner = min(group, key=lambda item: _winner_sort_key(item[0], item[1]))
        winners.append((_order_key(winner_index, winner), winner))

    for slot in user_slots:
        # Prefer original position among all slots for stable ordering.
        try:
            orig_index = next(i for i, s in enumerate(slots) if s.id == slot.id)
        except StopIteration:
            orig_index = 10_000_000
        winners.append((_order_key(orig_index, slot), slot))

    # If the same id appears twice (should not), keep first by order key.
    seen_ids: set[str] = set()
    ordered: list[DocumentSlot] = []
    for _, slot in sorted(winners, key=lambda item: item[0]):
        if slot.id in seen_ids:
            continue
        seen_ids.add(slot.id)
        ordered.append(slot)
    return ordered


def _is_user_slot(slot: DocumentSlot) -> bool:
    meta = slot.metadata if isinstance(slot.metadata, dict) else {}
    return str(meta.get("source") or "").strip().lower() == "user"


def _canonical_key(slot: DocumentSlot) -> str | None:
    meta = slot.metadata if isinstance(slot.metadata, dict) else {}
    raw = meta.get("canonical_key")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _is_review_candidate(slot: DocumentSlot) -> bool:
    """Slots that may appear on the review surface (open schema)."""
    if _is_user_slot(slot):
        return True
    if _canonical_key(slot):
        return True
    label = (slot.label or "").strip()
    if label:
        # Drop internal machine labels from the review surface.
        lower = label.casefold()
        if lower.startswith("slot_") or lower.startswith("candidate_"):
            return False
        if lower == "unknown":
            return slot.value not in (None, "")
        return True
    return slot.value not in (None, "")


def _group_key(slot: DocumentSlot) -> str:
    canonical = _canonical_key(slot)
    if canonical:
        return f"canonical:{canonical}"
    label = normalize_label(slot.label or "")
    if label:
        return f"label:{label}"
    # Unlabeled value rows stay distinct (no silent merge).
    return f"id:{slot.id}"


def _winner_sort_key(index: int, slot: DocumentSlot) -> tuple:
    """Lower is better — deterministic champion among duplicates."""
    meta = slot.metadata if isinstance(slot.metadata, dict) else {}
    source = str(meta.get("source") or "").strip().lower()
    source_rank = 0 if source == "user" else 1 if source in {"template_apply", "structured_enrichment"} else 2
    has_canonical = 0 if _canonical_key(slot) else 1
    conflict = 1 if slot.evidence.conflict else 0
    has_value = 0 if slot.value not in (None, "") else 1
    conf = _CONFIDENCE_RANK.get(str(slot.confidence or "unknown").strip().lower(), 3)
    has_evidence = 0 if slot.evidence.candidate_ids else 1
    return (
        source_rank,
        has_canonical,
        conflict,
        has_value,
        conf,
        has_evidence,
        index,
        slot.id,
    )


def _order_key(index: int, slot: DocumentSlot) -> tuple:
    page = slot.layout.page if slot.layout.page is not None else 10_000
    reading = (
        slot.layout.reading_index
        if slot.layout.reading_index is not None
        else 10_000_000
    )
    bbox = slot.layout.bbox or []
    y = float(bbox[1]) if len(bbox) >= 2 else 10_000_000.0
    x = float(bbox[0]) if len(bbox) >= 1 else 10_000_000.0
    return (page, reading, y, x, index, slot.id)
