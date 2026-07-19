"""Deterministic multi-page payslip boundary detection for bulk PDFs.

Primary path uses embedded PDF text anchors. Continuation pages are merged only
at high confidence. Low-confidence pages are never merged. When text is missing
or boundaries remain ambiguous, callers fall back to one page per payslip.
Optional AI splitting is invoked only by async callers that already own an
event loop (no sync/async bridging).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

import fitz

from payroll_copilot.infrastructure.ocr.pdf_text import assess_embedded_text_quality

# Merge continuation pages only at or above this confidence.
HIGH_CONFIDENCE_MERGE = 0.85

# Below this, treat the package as ambiguous for optional AI / one-page fallback.
AMBIGUOUS_PACKAGE_THRESHOLD = 0.55

_NEW_SLIP_ANCHOR_RE = re.compile(
    r"(?:"
    r"תלוש\s*שכר"
    r"|payslip"
    r"|pay[\s_-]*slip"
    r"|salary\s*slip"
    r"|מספר\s*עובד"
    r"|מס['׳'`]?\s*עובד"
    r"|מספר\s*עובד/ת"
    r"|ת\.?\s*ז\.?"
    r"|תעודת\s*זהות"
    r"|national\s*id"
    r"|employee\s*(?:no\.?|number|id|#)"
    r"|worker\s*(?:no\.?|number|id)"
    r")",
    re.IGNORECASE | re.UNICODE,
)

_CONTINUATION_MARKER_RE = re.compile(
    r"(?:"
    r"המשך"
    r"|continued?"
    r"|cont\.?(?:\s|$)"
    r"|page\s+\d+\s+(?:of|/)\s+\d+"
    r"|עמוד\s+\d+\s+מ(?:תוך)?\s*\d+"
    r")",
    re.IGNORECASE | re.UNICODE,
)

_IDENTITY_ID_RE = re.compile(
    r"(?<!\d)(\d{8,9}-\d)(?!\d)",
)
_EMPLOYEE_NUMBER_RE = re.compile(
    r"(?:מספר\s*עובד|מס['׳'`]?\s*עובד|employee\s*(?:no\.?|number|id|#)|worker\s*(?:no\.?|number))"
    r"\s*[:#\-]?\s*([A-Za-z0-9\-]{2,20})",
    re.IGNORECASE | re.UNICODE,
)
_INCOMPLETE_TOTALS_RE = re.compile(
    r"(?:"
    r"סה[\"״']?כ\s*(?:לתשלום|ברוטו|נטו)?"
    r"|total\s*(?:gross|net|due)?"
    r"|יתרת\s*לתשלום"
    r")",
    re.IGNORECASE | re.UNICODE,
)


AiSplitFn = Callable[
    [Sequence[str], int],
    Awaitable[Sequence[dict[str, Any]]],
]


@dataclass(frozen=True, slots=True)
class PayslipBoundary:
    """Zero-based inclusive page range for one payslip."""

    page_indices: tuple[int, ...]
    confidence: float
    strategy: str
    employee_number_hint: str | None = None
    employee_name_hint: str | None = None
    warnings: tuple[str, ...] = ()

    @property
    def page_start(self) -> int:
        """1-based first page for accountant UX."""
        return self.page_indices[0] + 1

    @property
    def page_end(self) -> int:
        """1-based last page for accountant UX."""
        return self.page_indices[-1] + 1


@dataclass(frozen=True, slots=True)
class PayslipBoundaryDetectionResult:
    boundaries: tuple[PayslipBoundary, ...]
    page_count: int
    strategy: str
    warnings: tuple[str, ...] = ()
    needs_ai: bool = False
    page_texts: tuple[str, ...] = ()


@dataclass(slots=True)
class _PageSignals:
    page_index: int
    text: str
    has_new_slip_anchor: bool
    has_continuation_marker: bool
    identity_fingerprint: str | None
    employee_number_hint: str | None
    text_density: int
    looks_like_new_slip: bool
    has_totals_marker: bool
    continuation_confidence: float = 0.0


@dataclass
class PayslipBoundaryDetector:
    """Hybrid boundary detector: text anchors first, optional AI, safe fallback."""

    high_confidence_merge: float = HIGH_CONFIDENCE_MERGE

    def detect(self, pdf_bytes: bytes) -> PayslipBoundaryDetectionResult:
        """Deterministic detection only. Never calls AI."""
        page_texts, page_count = self._extract_page_texts(pdf_bytes)
        if page_count <= 0:
            return PayslipBoundaryDetectionResult(
                boundaries=(),
                page_count=0,
                strategy="empty",
                warnings=("empty_pdf",),
            )
        if page_count == 1:
            return PayslipBoundaryDetectionResult(
                boundaries=(
                    PayslipBoundary(
                        page_indices=(0,),
                        confidence=1.0,
                        strategy="single_page",
                    ),
                ),
                page_count=1,
                strategy="single_page",
                page_texts=tuple(page_texts),
            )

        quality = assess_embedded_text_quality(page_texts)
        if not quality.usable:
            return self._one_page_fallback(
                page_count,
                page_texts=page_texts,
                reason="insufficient_embedded_text",
                needs_ai=False,
            )

        signals = [self._score_page(index, text) for index, text in enumerate(page_texts)]
        if not any(s.looks_like_new_slip or s.identity_fingerprint for s in signals):
            return self._one_page_fallback(
                page_count,
                page_texts=page_texts,
                reason="no_slip_anchors",
                needs_ai=True,
            )

        return self._group_from_signals(signals, page_texts=page_texts)

    async def detect_async(
        self,
        pdf_bytes: bytes,
        *,
        ai_splitter: AiSplitFn | None = None,
    ) -> PayslipBoundaryDetectionResult:
        """Detect boundaries; optionally ask AI when deterministic result is insufficient.

        Safe for callers that already run inside an event loop (e.g. batch
        ``_process_async``). Does not bridge sync/async itself.
        """
        result = self.detect(pdf_bytes)
        if not result.needs_ai or ai_splitter is None:
            if result.needs_ai:
                return self._one_page_fallback(
                    result.page_count,
                    page_texts=list(result.page_texts),
                    reason="split_ambiguous",
                    needs_ai=False,
                )
            return result

        try:
            raw_splits = await ai_splitter(result.page_texts, result.page_count)
        except Exception:  # noqa: BLE001 - AI is non-authoritative
            return self._one_page_fallback(
                result.page_count,
                page_texts=list(result.page_texts),
                reason="ai_splitter_failed",
                needs_ai=False,
            )

        validated = self._boundaries_from_ai(
            raw_splits,
            page_count=result.page_count,
            page_texts=result.page_texts,
        )
        if validated is None:
            return self._one_page_fallback(
                result.page_count,
                page_texts=list(result.page_texts),
                reason="ai_splitter_invalid",
                needs_ai=False,
            )
        return validated

    def _group_from_signals(
        self,
        signals: list[_PageSignals],
        *,
        page_texts: list[str],
    ) -> PayslipBoundaryDetectionResult:
        groups: list[list[_PageSignals]] = []
        current: list[_PageSignals] = [signals[0]]
        warnings: list[str] = []

        for page in signals[1:]:
            prev = current[-1]
            merge_confidence = self._continuation_confidence(prev, page)
            page.continuation_confidence = merge_confidence
            if merge_confidence >= self.high_confidence_merge:
                current.append(page)
                continue
            # Never merge low-confidence pages — start a new slip instead.
            if merge_confidence > 0.0 and merge_confidence < self.high_confidence_merge:
                warnings.append(
                    f"split_ambiguous:page_{page.page_index + 1}"
                )
            groups.append(current)
            current = [page]
        groups.append(current)

        boundaries = tuple(
            PayslipBoundary(
                page_indices=tuple(p.page_index for p in group),
                confidence=self._group_confidence(group),
                strategy="text_anchor",
                employee_number_hint=next(
                    (p.employee_number_hint for p in group if p.employee_number_hint),
                    None,
                ),
                warnings=tuple(
                    w
                    for w in (
                        "multi_page_slip" if len(group) > 1 else None,
                    )
                    if w
                ),
            )
            for group in groups
        )
        package_confidence = (
            sum(b.confidence for b in boundaries) / len(boundaries)
            if boundaries
            else 0.0
        )
        if package_confidence < AMBIGUOUS_PACKAGE_THRESHOLD:
            return self._one_page_fallback(
                len(signals),
                page_texts=page_texts,
                reason="low_package_confidence",
                needs_ai=True,
            )

        strategy = (
            "text_anchor_multi"
            if any(len(b.page_indices) > 1 for b in boundaries)
            else "text_anchor"
        )
        return PayslipBoundaryDetectionResult(
            boundaries=boundaries,
            page_count=len(signals),
            strategy=strategy,
            warnings=tuple(warnings),
            needs_ai=False,
            page_texts=tuple(page_texts),
        )

    def _continuation_confidence(
        self,
        prev: _PageSignals,
        curr: _PageSignals,
    ) -> float:
        """Return merge confidence in [0, 1]. Only high scores may merge."""
        # Explicit continuation marker is the primary high-confidence merge signal.
        if curr.has_continuation_marker and not curr.has_new_slip_anchor:
            if (
                curr.identity_fingerprint
                and prev.identity_fingerprint
                and curr.identity_fingerprint != prev.identity_fingerprint
            ):
                return 0.0
            return 0.95

        # Never merge a page that clearly starts a new slip.
        if curr.looks_like_new_slip:
            return 0.0

        # Same identity fingerprint without a new-slip header.
        if (
            curr.identity_fingerprint
            and prev.identity_fingerprint
            and curr.identity_fingerprint == prev.identity_fingerprint
            and not curr.has_new_slip_anchor
        ):
            return 0.9

        if (
            not curr.looks_like_new_slip
            and not curr.identity_fingerprint
            and not curr.has_new_slip_anchor
            and prev.has_totals_marker is False
            and curr.text_density >= 40
            and prev.looks_like_new_slip
        ):
            # Soft signal only — below merge threshold on purpose.
            return 0.6

        return 0.0

    @staticmethod
    def _group_confidence(group: list[_PageSignals]) -> float:
        if len(group) == 1:
            head = group[0]
            if head.looks_like_new_slip or head.identity_fingerprint:
                return 0.95
            return 0.7
        merge_scores = [
            page.continuation_confidence
            for page in group[1:]
            if page.continuation_confidence > 0
        ]
        if not merge_scores:
            return 0.7
        return min(0.99, sum(merge_scores) / len(merge_scores))

    def _score_page(self, page_index: int, text: str) -> _PageSignals:
        normalized = text or ""
        density = len(re.sub(r"\s+", "", normalized))
        has_continuation = bool(_CONTINUATION_MARKER_RE.search(normalized))
        has_anchor = bool(_NEW_SLIP_ANCHOR_RE.search(normalized))
        if has_continuation:
            # Phrases like "Continued payslip" / "המשך תלוש שכר" must not count as starts.
            has_anchor = False
        emp_match = _EMPLOYEE_NUMBER_RE.search(normalized)
        employee_number_hint = emp_match.group(1).strip() if emp_match else None
        identity = employee_number_hint
        if identity is None:
            id_match = _IDENTITY_ID_RE.search(normalized)
            if id_match:
                identity = id_match.group(1)
        if has_continuation:
            looks_new = False
        else:
            looks_new = has_anchor or bool(employee_number_hint) or identity is not None
        return _PageSignals(
            page_index=page_index,
            text=normalized,
            has_new_slip_anchor=has_anchor,
            has_continuation_marker=has_continuation,
            identity_fingerprint=identity,
            employee_number_hint=employee_number_hint,
            text_density=density,
            looks_like_new_slip=looks_new,
            has_totals_marker=bool(_INCOMPLETE_TOTALS_RE.search(normalized)),
        )

    def _boundaries_from_ai(
        self,
        raw_splits: Sequence[dict[str, Any]],
        *,
        page_count: int,
        page_texts: Sequence[str],
    ) -> PayslipBoundaryDetectionResult | None:
        if not raw_splits:
            return None

        covered: set[int] = set()
        boundaries: list[PayslipBoundary] = []
        for raw in raw_splits:
            try:
                start = int(raw.get("page_start", 0))
                end = int(raw.get("page_end", 0))
                confidence = float(raw.get("confidence", 0.0))
            except (TypeError, ValueError):
                return None
            # Accept either 1-based (agent schema) or 0-based ranges.
            if start >= 1 and end >= 1:
                start0, end0 = start - 1, end - 1
            else:
                start0, end0 = start, end
            if start0 < 0 or end0 < start0 or end0 >= page_count:
                return None
            if confidence < self.high_confidence_merge and end0 > start0:
                # Never accept low-confidence multi-page AI merges.
                return None
            indices = tuple(range(start0, end0 + 1))
            if covered.intersection(indices):
                return None
            covered.update(indices)
            boundaries.append(
                PayslipBoundary(
                    page_indices=indices,
                    confidence=max(0.0, min(1.0, confidence)),
                    strategy="ai",
                    employee_number_hint=raw.get("employee_number_hint"),
                    employee_name_hint=raw.get("employee_name_hint"),
                )
            )

        if covered != set(range(page_count)):
            return None

        boundaries.sort(key=lambda b: b.page_indices[0])
        return PayslipBoundaryDetectionResult(
            boundaries=tuple(boundaries),
            page_count=page_count,
            strategy="ai",
            page_texts=tuple(page_texts),
        )

    @staticmethod
    def _one_page_fallback(
        page_count: int,
        *,
        page_texts: list[str] | Sequence[str],
        reason: str,
        needs_ai: bool,
    ) -> PayslipBoundaryDetectionResult:
        boundaries = tuple(
            PayslipBoundary(
                page_indices=(index,),
                confidence=0.5,
                strategy="one_page_fallback",
                warnings=(reason,),
            )
            for index in range(page_count)
        )
        return PayslipBoundaryDetectionResult(
            boundaries=boundaries,
            page_count=page_count,
            strategy="one_page_fallback",
            warnings=(reason, "split_ambiguous"),
            needs_ai=needs_ai,
            page_texts=tuple(page_texts),
        )

    @staticmethod
    def _extract_page_texts(pdf_bytes: bytes) -> tuple[list[str], int]:
        if not pdf_bytes:
            return [], 0
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            texts = [
                document.load_page(index).get_text("text") or ""
                for index in range(document.page_count)
            ]
            return texts, document.page_count
        finally:
            document.close()
