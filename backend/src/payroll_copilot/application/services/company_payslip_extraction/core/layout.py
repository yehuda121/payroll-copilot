"""Layout-aware PDF word extraction, visual rows, and multi-field segmentation."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Iterable, Optional

import pdfplumber

from payroll_copilot.application.services.company_payslip_extraction.core.font_recovery import page_glyph_overrides, repair_word_text
from payroll_copilot.application.services.company_payslip_extraction.core.profile import get_profile
from payroll_copilot.application.services.company_payslip_extraction.core.hebrew import (
    APOSTROPHE_LABEL_ALLOW,
    _LOGICAL_LABEL_HINTS,
    _VISUAL_LABEL_HINTS,
    _hint_score,
    is_label_like,
    is_payslip_title_text,
    is_person_name_like,
    is_print_date_label_text,
    is_value_like,
    is_well_formed_label,
    normalize_employment_type,
    normalize_hebrew_label,
    normalize_hebrew_value,
    normalize_person_name,
    parse_payroll_period_token,
    parse_print_date_token,
)


class _ProfileSetProxy:
    def __init__(self, attr: str) -> None:
        self._attr = attr

    def __contains__(self, item: object) -> bool:
        return item in getattr(get_profile(), self._attr)

    def __iter__(self):
        return iter(getattr(get_profile(), self._attr))


class _ProfileTupleProxy:
    def __init__(self, attr: str) -> None:
        self._attr = attr

    def __iter__(self):
        return iter(getattr(get_profile(), self._attr))

    def __contains__(self, item: object) -> bool:
        return item in getattr(get_profile(), self._attr)


Y_TOLERANCE = 3.5
MIN_WORDS_FOR_LAYOUT = 8

# Numeric value:label pairs (RTL-reversed) — primary, high precision
_REVERSED_PAIR_NUMERIC = re.compile(
    r"(?P<value>\d[\d.,/\-%]*)\s*:\s*(?P<label>[^\d:]+?)"
    r"(?=(?:\s+\d[\d.,/\-%]*\s*:)|$)"
)
# Non-numeric short value:label (e.g. department name) — secondary
_REVERSED_PAIR_TEXT = re.compile(
    r"(?P<value>[^\d:\s][^:]{0,48}?)\s*:\s*"
    r"(?P<label>[\u0590-\u05FF](?:[\u0590-\u05FF'׳״\"\s\-.]{0,28}[\u0590-\u05FF'׳״\"])?)"
    r"(?=(?:\s+[^:]+\s*:)|$)"
)
# Normal label:value pairs (may repeat on one row)
_NORMAL_PAIR = re.compile(
    r"(?P<label>[^\d:]{1,40}?)\s*:\s*(?P<value>\d[\d.,/\-%]*|(?:(?!\s+[^:\d]{1,40}\s*:).)+?)"
    r"(?=(?:\s+[^\d:]{1,40}?\s*:)|$)"
)

# Helper tokens that belong to a neighboring measure field (hours/days)
_HELPER_LABELS = _ProfileSetProxy("helper_labels")  # type: ignore[assignment]

# Footer / calculation labels — keep in entries, never promote to fields
_FOOTER_LABEL_HINTS = _ProfileTupleProxy("footer_label_hints")  # type: ignore[assignment]

# Real summary fields whose text overlaps a footer hint substring
_FOOTER_LABEL_EXCEPTIONS = _ProfileSetProxy("footer_label_exceptions")  # type: ignore[assignment]


@dataclass
class WordSpan:
    text: str
    page: int
    x0: float
    top: float
    x1: float
    bottom: float
    # Set only when a broken embedded font provably mis-mapped a glyph.
    # ``text`` always stays as extracted so raw evidence is never rewritten.
    repaired_text: str | None = None

    @property
    def display_text(self) -> str:
        return self.repaired_text or self.text

    @property
    def x_center(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def y_center(self) -> float:
        return (self.top + self.bottom) / 2.0

    @property
    def width(self) -> float:
        return max(self.x1 - self.x0, 0.0)

    @property
    def height(self) -> float:
        return max(self.bottom - self.top, 0.0)

    def to_bbox(self) -> dict[str, float | int]:
        return {
            "page": self.page,
            "x0": round(self.x0, 2),
            "top": round(self.top, 2),
            "x1": round(self.x1, 2),
            "bottom": round(self.bottom, 2),
        }


@dataclass
class VisualRow:
    page: int
    y: float
    words: list[WordSpan] = field(default_factory=list)

    @property
    def text(self) -> str:
        # Preserve PDF extraction order (usually LTR by x0)
        ordered = sorted(self.words, key=lambda w: w.x0)
        return " ".join(w.text for w in ordered).strip()

    @property
    def display_text(self) -> str:
        """Row text with proven font-glyph repairs applied."""
        ordered = sorted(self.words, key=lambda w: w.x0)
        return " ".join(w.display_text for w in ordered).strip()

    @property
    def bbox(self) -> dict[str, float | int] | None:
        if not self.words:
            return None
        return {
            "page": self.page,
            "x0": round(min(w.x0 for w in self.words), 2),
            "top": round(min(w.top for w in self.words), 2),
            "x1": round(max(w.x1 for w in self.words), 2),
            "bottom": round(max(w.bottom for w in self.words), 2),
        }


@dataclass
class FieldCandidate:
    name: str
    value: str
    raw: str
    bbox: dict[str, float | int] | None = None
    confidence: str = "medium"  # high | medium | low | unknown
    status: str = "ok"

    def to_entry(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "raw": self.raw,
            "bbox": self.bbox,
            "confidence": self.confidence,
            "status": self.status,
        }


@dataclass
class LayoutTemplate:
    """Request-scoped layout learned from repeating payslip regions."""

    # normalized_label -> list of (x_center, y_offset_from_slip_top)
    label_anchors: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    # Relative Y band for unlabeled person-name rows
    name_y_offsets: list[float] = field(default_factory=list)
    info_row_y_offsets: list[float] = field(default_factory=list)
    id_row_y_offsets: list[float] = field(default_factory=list)
    # Colon X centers across slips — recurring column boundaries
    colon_x_positions: list[float] = field(default_factory=list)

    def record_label(self, name: str, x_center: float, y_offset: float) -> None:
        if not name:
            return
        self.label_anchors.setdefault(name, []).append((x_center, y_offset))

    def record_colon_x(self, x: float) -> None:
        self.colon_x_positions.append(x)

    def record_name_offset(self, y_offset: float) -> None:
        self.name_y_offsets.append(y_offset)

    def median(self, values: list[float]) -> Optional[float]:
        if not values:
            return None
        s = sorted(values)
        return s[len(s) // 2]

    def expected_name_offset(self) -> Optional[float]:
        return self.median(self.name_y_offsets)

    def column_boundaries(self, cluster_dx: float = 18.0) -> list[float]:
        """Cluster repeated colon X positions into column boundaries."""
        if not self.colon_x_positions:
            return []
        xs = sorted(self.colon_x_positions)
        clusters: list[list[float]] = [[xs[0]]]
        for x in xs[1:]:
            if abs(x - clusters[-1][-1]) <= cluster_dx:
                clusters[-1].append(x)
            else:
                clusters.append([x])
        # Keep clusters that appear more than once (recurring)
        bounds = []
        for cl in clusters:
            if len(cl) >= 2:
                bounds.append(sum(cl) / len(cl))
        return bounds

    def nearest_label(self, x_center: float, y_offset: float, max_dx: float = 40.0, max_dy: float = 12.0) -> Optional[str]:
        best: tuple[float, str] | None = None
        for name, points in self.label_anchors.items():
            for px, py in points:
                dx = abs(px - x_center)
                dy = abs(py - y_offset)
                if dx <= max_dx and dy <= max_dy:
                    score = dx + dy * 2
                    if best is None or score < best[0]:
                        best = (score, name)
        return best[1] if best else None


# ---------------------------------------------------------------------------
# Word / row extraction
# ---------------------------------------------------------------------------

def extract_words(file_bytes: bytes) -> list[WordSpan]:
    """Extract words with page + bounding-box metadata via pdfplumber."""
    spans: list[WordSpan] = []
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(
                x_tolerance=2,
                y_tolerance=3,
                keep_blank_chars=False,
                use_text_flow=False,
            ) or []
            overrides = page_glyph_overrides(page)
            broken_glyphs = {g for m in overrides.values() for g in m}
            suspect_chars = (
                [c for c in page.chars if (c.get("text") or "") in broken_glyphs]
                if broken_glyphs
                else []
            )

            page_spans: list[WordSpan] = []
            for w in words:
                text = (w.get("text") or "").strip()
                if not text:
                    continue
                x0, top = float(w["x0"]), float(w["top"])
                x1, bottom = float(w["x1"]), float(w["bottom"])
                repaired = None
                if suspect_chars and any(g in text for g in broken_glyphs):
                    inside = [
                        c
                        for c in suspect_chars
                        if x0 - 0.5 <= float(c["x0"]) and float(c["x1"]) <= x1 + 0.5
                        and top - 1.0 <= float(c["top"]) and float(c["bottom"]) <= bottom + 1.0
                    ]
                    repaired = repair_word_text(text, inside, overrides)
                page_spans.append(
                    WordSpan(
                        text=text,
                        page=page_index,
                        x0=x0,
                        top=top,
                        x1=x1,
                        bottom=bottom,
                        repaired_text=repaired,
                    )
                )
            spans.extend(page_spans)
    return spans


# ---------------------------------------------------------------------------
# Fragment reconstruction (before any field segmentation)
# ---------------------------------------------------------------------------

# Adjacent Hebrew tokens that form one structural label (visual and/or logical).
# Do NOT encode full rows or values — only known label bigrams.
_STRUCTURAL_LABEL_BIGRAMS = _ProfileSetProxy("structural_label_bigrams")  # type: ignore[assignment]

# Single-token labels that are almost always incomplete stems of a fuller phrase
_INCOMPLETE_STANDALONE_LABELS = _ProfileSetProxy("incomplete_standalone_labels")  # type: ignore[assignment]

# Prefer extending past these when an adjacent token forms a longer valid label
_EXTENDABLE_PARTIAL_LABELS = _ProfileSetProxy("extendable_partial_labels")  # type: ignore[assignment]

# Known short labels that are complete without a second word
_COMPLETE_SHORT_LABELS = _ProfileSetProxy("complete_short_labels")  # type: ignore[assignment]

_LABEL_VALUE_FORBIDDEN = frozenset({
    "ימי",
    "עבודה",
    "הדובע",
    "תעש",
    "מתוך",
    "ךותמ",
    "מחלקה",
    "הקלחמ",
    "שעות",
    "שעת",
})


def _same_visual_row(a: WordSpan, b: WordSpan, y_tol: float = Y_TOLERANCE) -> bool:
    return a.page == b.page and abs(b.top - a.top) <= y_tol


def _horizontal_gap(a: WordSpan, b: WordSpan) -> float:
    """Gap between a (left) and b (right); negative if overlapping."""
    return b.x0 - a.x1


def _numeric_merge_gap_limit(a: WordSpan, b: WordSpan) -> float:
    """Adaptive gap: tight for most PDFs, slightly wider when glyphs are large."""
    height = max(a.height, b.height, 8.0)
    return max(6.0, height * 0.85)


def _combined_numeric_text(a: str, b: str) -> str | None:
    """
    If a+b (no space) form one number / percent / signed token, return combined text.

    Does NOT glue unrelated digit runs (IDs) — only decimal/comma/percent/sign syntax.
    Every digit from a and b is preserved in order.
    """
    if not a or not b:
        return None
    combined = a + b
    # Intact forms after join (optional leading sign)
    if re.fullmatch(r"[+\-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?", combined):
        return combined
    if re.fullmatch(r"[+\-]?\d+\.\d+%?", combined):
        return combined
    if re.fullmatch(r"[+\-]?\d+%", combined):
        return combined
    # "22" + ".00" / "6" + ",443.85"
    if a[-1].isdigit() and re.match(r"^[.,]\d", b):
        return combined
    # signed head: "-" + "6,443.85" / "+" + "12.5"
    if a in "+-" and re.match(r"^\d", b):
        if _combined_numeric_text(b[0], b[1:]) is not None or re.fullmatch(
            r"\d{1,3}(?:,\d{3})*(?:\.\d+)?%?|\d+(?:\.\d+)?%?", b
        ):
            return combined
        if re.fullmatch(r"\d+(?:[.,]\d+)*%?", b):
            return combined
    # "22." / "6," + "00" / "443.85"
    if re.match(r"^[+\-]?\d+[.,]$", a) and b[0].isdigit():
        return combined
    # "22.0" + "0" / "6,443" + ".85"
    if re.match(r"^[+\-]?\d+[.,]\d+$", a) and re.fullmatch(r"\d+%?", b):
        return combined
    if re.fullmatch(r"[+\-]?[\d.,]+", a) and b == "%":
        return combined
    # "6," + "443" / "6,443" + ".85"
    if re.match(r"^[+\-]?\d+,$", a) and re.fullmatch(r"\d{3}(?:\.\d+)?", b):
        return combined
    if re.match(r"^[+\-]?\d{1,3}(?:,\d{3})*$", a) and re.match(r"^\.\d+%?$", b):
        return combined
    # Lone thousands comma token: "6" + ","  (next pass merges digits)
    if re.fullmatch(r"[+\-]?\d+", a) and b == ",":
        return combined
    # "6," already built + "443.85"
    if re.match(r"^[+\-]?\d+,$", a) and re.fullmatch(r"\d+(?:\.\d+)?%?", b):
        return combined
    return None


def _should_merge_numeric_fragments(a: WordSpan, b: WordSpan, max_gap: float | None = None) -> bool:
    """True when a+b are fragments of one number (22+.00, 6+,443.85, 100+%, -12.5)."""
    if not _same_visual_row(a, b):
        return False
    # Require nearly the same baseline — avoid gluing neighbors from y-sort drift
    if abs(b.top - a.top) > min(Y_TOLERANCE, max(a.height, b.height, 8.0) * 0.45):
        return False
    gap = _horizontal_gap(a, b)
    limit = max_gap if max_gap is not None else _numeric_merge_gap_limit(a, b)
    # Thousands / decimal tails often sit slightly farther — allow a bit more gap
    if b.text[:1] in ".," or a.text[-1:] in ".," or a.text in "+-":
        limit = max(limit, max(a.height, b.height, 8.0) * 1.25)
    if gap > limit:
        return False
    combined = _combined_numeric_text(a.text, b.text)
    if combined is None:
        return False
    # Preserve every original digit in order
    digits_a = re.sub(r"\D", "", a.text)
    digits_b = re.sub(r"\D", "", b.text)
    digits_c = re.sub(r"\D", "", combined)
    return digits_c == digits_a + digits_b


def _should_merge_label_fragments(a: WordSpan, b: WordSpan, max_gap: float | None = None) -> bool:
    """True when adjacent Hebrew tokens form a known structural label bigram."""
    if not _same_visual_row(a, b):
        return False
    if _is_colon_word(a) or _is_colon_word(b):
        return False
    gap = _horizontal_gap(a, b)
    height = max(a.height, b.height, 8.0)
    limit = max_gap if max_gap is not None else max(14.0, height * 1.8)
    if gap > limit:
        return False
    ta, tb = a.text.strip(), b.text.strip()
    if (ta, tb) in _STRUCTURAL_LABEL_BIGRAMS:
        return True
    # Also allow if normalized forms match a logical bigram
    na, nb = normalize_hebrew_label(ta), normalize_hebrew_label(tb)
    if (na, nb) in _STRUCTURAL_LABEL_BIGRAMS:
        return True
    return False


def _merge_span_pair(a: WordSpan, b: WordSpan, *, joiner: str) -> WordSpan:
    repaired = None
    if a.repaired_text or b.repaired_text:
        repaired = a.display_text + joiner + b.display_text
    return WordSpan(
        text=a.text + joiner + b.text,
        page=a.page,
        x0=a.x0,
        top=min(a.top, b.top),
        x1=b.x1,
        bottom=max(a.bottom, b.bottom),
        repaired_text=repaired,
    )


def reconstruct_fragments(words: list[WordSpan]) -> list[WordSpan]:
    """
    Preprocess pdfplumber word fragments into complete tokens.

    Merges:
    - numeric fragments (decimals, thousands commas, percents)
    - adjacent Hebrew fragments that form known structural labels

    Then splits glued-colon labels (``:העשל`` → ``:`` + ``העשל``).
    Segmentation must run only after this reconstruction.
    """
    if not words:
        return []

    # Pass 1: numeric (no space)
    # Within a visual row, x0 is the ownership axis. Sorting by top first lets
    # micro Y drift put a right-edge glued colon *before* its left-side value,
    # which orphans intact values such as ``1`` / ``30491361-9`` / ``35.41``.
    ordered = sorted(words, key=lambda w: (w.page, w.x0, w.top))
    numeric: list[WordSpan] = [ordered[0]]
    for w in ordered[1:]:
        prev = numeric[-1]
        if _should_merge_numeric_fragments(prev, w):
            combined = _combined_numeric_text(prev.text, w.text) or (prev.text + w.text)
            numeric[-1] = WordSpan(
                text=combined,
                page=prev.page,
                x0=prev.x0,
                top=min(prev.top, w.top),
                x1=w.x1,
                bottom=max(prev.bottom, w.bottom),
            )
        else:
            numeric.append(w)

    # Pass 2: glued-colon labels → standalone colon + label (before label bigrams)
    split = split_glued_colon_tokens(numeric)

    # Pass 3: structural Hebrew labels (space-joined)
    if not split:
        return []
    labeled: list[WordSpan] = [split[0]]
    for w in split[1:]:
        prev = labeled[-1]
        if _should_merge_label_fragments(prev, w):
            labeled[-1] = _merge_span_pair(prev, w, joiner=" ")
        else:
            labeled.append(w)
    # Keep stable left→right order after splits/merges
    return sorted(labeled, key=lambda w: (w.page, w.x0, w.top))


def split_glued_colon_tokens(words: list[WordSpan]) -> list[WordSpan]:
    """
    Split tokens that begin with ``:`` into a logical colon boundary and label.

    Examples: ``:העשל`` → ``:`` + ``העשל``, ``:הרשמ`` → ``:`` + ``הרשמ``.

    Does not split:
    - standalone ``:``
    - numeric/punctuation tails (``:12.5``, ``:,443``)
    - tokens with an internal colon (``a:b``)
    """
    if not words:
        return []
    out: list[WordSpan] = []
    for w in words:
        t = (w.text or "").strip()
        if (
            len(t) >= 2
            and t.startswith(":")
            and t != ":"
            and ":" not in t[1:]
            and not re.match(r"^:[\d.,/%+\-]", t)
            and not re.fullmatch(r":[\d.,/%+\-]+", t)
        ):
            label = t[1:].strip()
            if not label or re.fullmatch(r"[\d.,/%+\-]+", label):
                out.append(w)
                continue
            repaired_label = None
            if w.repaired_text:
                candidate = w.repaired_text.strip()
                if candidate.startswith(":"):
                    repaired_label = candidate[1:].strip() or None
            width = max(w.width, 2.0)
            colon_w = min(max(width * 0.12, 1.2), 5.0)
            # Keep colon on the left edge of the original glyph box (LTR word order)
            colon_x1 = min(w.x0 + colon_w, w.x1 - 0.5)
            out.append(
                WordSpan(
                    text=":",
                    page=w.page,
                    x0=w.x0,
                    top=w.top,
                    x1=colon_x1,
                    bottom=w.bottom,
                )
            )
            out.append(
                WordSpan(
                    repaired_text=repaired_label,
                    text=label,
                    page=w.page,
                    x0=colon_x1,
                    top=w.top,
                    x1=w.x1,
                    bottom=w.bottom,
                )
            )
        else:
            out.append(w)
    return out


def merge_fragmented_tokens(words: list[WordSpan]) -> list[WordSpan]:
    """Backward-compatible alias for ``reconstruct_fragments``."""
    return reconstruct_fragments(words)


def words_usable(words: list[WordSpan]) -> bool:
    return len(words) >= MIN_WORDS_FOR_LAYOUT


def build_visual_rows(words: list[WordSpan], y_tol: float = Y_TOLERANCE) -> list[VisualRow]:
    """Group words that share approximately the same vertical position."""
    if not words:
        return []

    # Group by Y first; reconstruct fragments only within each visual row
    by_page: dict[int, list[WordSpan]] = defaultdict(list)
    for w in words:
        by_page[w.page].append(w)

    rows: list[VisualRow] = []
    for page in sorted(by_page):
        page_words = sorted(by_page[page], key=lambda w: (w.top, w.x0))
        current: VisualRow | None = None
        for w in page_words:
            if current is None or abs(w.top - current.y) > y_tol or w.page != current.page:
                current = VisualRow(page=page, y=w.top, words=[w])
                rows.append(current)
            else:
                current.words.append(w)
                tops = sorted(x.top for x in current.words)
                current.y = tops[len(tops) // 2]
    for row in rows:
        row.words = reconstruct_fragments(sorted(row.words, key=lambda w: w.x0))
    return rows


# ---------------------------------------------------------------------------
# Multi-field segmentation within a row
# ---------------------------------------------------------------------------

GAP_SPLIT_RATIO = 2.8  # gap vs median word-gap → field boundary
MAX_LABEL_WORDS = 5
MAX_LABEL_CHARS = 36


def bbox_from_words(page: int, words: list[WordSpan]) -> dict[str, float | int] | None:
    if not words:
        return None
    return {
        "page": page,
        "x0": round(min(w.x0 for w in words), 2),
        "top": round(min(w.top for w in words), 2),
        "x1": round(max(w.x1 for w in words), 2),
        "bottom": round(max(w.bottom for w in words), 2),
    }


def _bbox_for_substring(row: VisualRow, fragment: str) -> dict[str, float | int] | None:
    """Approximate bbox from words whose text appears in the fragment."""
    if not row.words or not fragment.strip():
        return row.bbox
    tokens = set(fragment.split())
    matched = [w for w in row.words if w.text in tokens or w.text in fragment]
    if not matched:
        return row.bbox
    return bbox_from_words(row.page, matched)


def _is_colon_word(w: WordSpan) -> bool:
    t = w.text.strip()
    return t == ":" or t == "："


def _join_words(words: list[WordSpan]) -> str:
    return " ".join(w.text for w in words).strip()


def _is_helper_label(name: str) -> bool:
    n = (name or "").strip()
    if not n:
        return False
    if n in _HELPER_LABELS:
        return True
    return normalize_hebrew_label(n) in _HELPER_LABELS


def _is_footer_label(name: str) -> bool:
    n = normalize_hebrew_label((name or "").strip())
    if not n:
        return False
    if n in _FOOTER_LABEL_EXCEPTIONS:
        return False
    return any(h in n for h in _FOOTER_LABEL_HINTS)


def _is_work_measure_field(name: str) -> bool:
    n = normalize_hebrew_label((name or "").strip())
    return any(
        h in n
        for h in ("שעות עבודה", "שעת עבודה", "ימי עבודה", "שעות", "שעת", "ימי")
    )


def _value_starts_with_punct_fragment(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    return bool(re.match(r"^[.,;:%/\-]", v)) and not v[0].isdigit()


def _is_intact_number_token(text: str) -> bool:
    t = (text or "").strip()
    return bool(
        re.fullmatch(
            r"\d{1,3}(?:,\d{3})*(?:\.\d+)?%?"
            r"|\d+(?:\.\d+)?%?"
            r"|\d+-\d+",  # Israeli ID style 30491361-9
            t,
        )
    )


def _value_is_label_fragment(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    if v in _LABEL_VALUE_FORBIDDEN:
        return True
    n = normalize_hebrew_label(v)
    return n in _LABEL_VALUE_FORBIDDEN or n in {"ימי עבודה", "שעות עבודה", "אחוז משרה"}


def _label_phrase_score(joined: str) -> int:
    """
    Score a candidate label phrase. Higher is better / more complete.
    Incomplete stems like ``עבודה`` score just above invalid so a longer
    phrase (``התחלת עבודה``) always wins when available.
    """
    joined = (joined or "").strip()
    if not joined:
        return -1
    norm = normalize_hebrew_label(joined)
    if not is_well_formed_label(norm):
        return -1
    words = norm.split()
    score = len(words) * 100 + _hint_score(norm, _LOGICAL_LABEL_HINTS) * 20 + len(norm)
    if norm in _COMPLETE_SHORT_LABELS or norm in {
        "מס' עובד",
        "מס׳ עובד",
        "בן זוג עובד",
        "מינימום לחודש",
        "התחלת עבודה",
        "שעות עבודה",
        "ימי עבודה",
    }:
        score += 250
    if norm in _EXTENDABLE_PARTIAL_LABELS or norm in _INCOMPLETE_STANDALONE_LABELS:
        score = min(score, 15)
    return score


def _is_incomplete_standalone_label(name: str) -> bool:
    n = normalize_hebrew_label((name or "").strip())
    return n in _INCOMPLETE_STANDALONE_LABELS


def _is_contextually_invalid_pair(name: str, value: str) -> bool:
    """
    Reject generic / mismatched label-value pairs that are well-formed
    token-wise but wrong in payslip context (e.g. ``משרה: 4080234``).
    """
    n = normalize_hebrew_label((name or "").strip())
    v = (value or "").strip()
    if not n or not v:
        return False
    if n in _INCOMPLETE_STANDALONE_LABELS:
        return True
    # משרה: reject address/ID digits; allow % or Hebrew employment type
    if n == "משרה":
        digits = re.sub(r"[^\d]", "", v)
        if re.fullmatch(r"\d{5,}", digits):
            return True
        if normalize_employment_type(v) is not None:
            return False
        nv = normalize_hebrew_label(v) if is_label_like(v) else v
        if (
            "%" in v
            or re.fullmatch(r"\d{1,3}(?:\.\d+)?%?", v)
            or re.fullmatch(r"0\.\d+", v)
            or ("משרה" in nv and nv != "משרה")
            or "חודש" in nv
        ):
            return False
        if is_label_like(v) and not any(c.isdigit() for c in v):
            return True
        if digits and not (
            "%" in v or re.fullmatch(r"\d{1,3}(?:\.\d+)?%?", v)
        ):
            return True
        return False
    # Bare עובד / short stem with a tiny Hebrew fragment value
    if n == "עובד" and (is_label_like(v) or len(v) <= 3):
        return True
    # Malformed apostrophe labels that are not מס'… / a known abbreviation
    if (
        ("'" in n or "׳" in n)
        and not n.startswith(("מס'", "מס׳"))
        and n not in APOSTROPHE_LABEL_ALLOW
    ):
        if '"' not in n and "״" not in n:
            return True
    return False


def _is_measure_label_without_value(name: str, value: str) -> bool:
    """
    True for a label carrying a unit marker whose paired side holds no number.

    Such a label measures something, so without an explicit numeric value the
    pair names nothing and must not be emitted as a field.
    """
    n = (name or "").strip()
    v = (value or "").strip()
    if "%" not in n or not v:
        return False
    return not any(c.isdigit() for c in v)


def _select_best_label_phrase(tokens: list[WordSpan]) -> list[WordSpan]:
    """Prefer the longest valid normalized label prefix among collected tokens."""
    if not tokens:
        return []
    best: list[WordSpan] = []
    best_score = -1
    for k in range(1, len(tokens) + 1):
        prefix = tokens[:k]
        score = _label_phrase_score(_join_words(prefix))
        if score > best_score:
            best_score = score
            best = prefix
    # If nothing scored valid, keep all collected Hebrew tokens for evidence
    return best if best_score >= 0 else tokens


def _collect_label_tokens_after_colon(
    words: list[WordSpan],
    colon_idx: int,
    used: set[int],
    gap_threshold: float,
) -> tuple[list[WordSpan], list[int]]:
    """
    Gather adjacent same-row Hebrew tokens after a colon (larger x0), then keep
    the longest valid label phrase. Returns (tokens, indices).
    """
    # Labels sit close together; do not inherit large inter-column median gaps
    label_gap = min(float(gap_threshold), 14.0)
    collected: list[WordSpan] = []
    indices: list[int] = []
    j = colon_idx + 1
    while j < len(words) and j not in used and not _is_colon_word(words[j]):
        nxt = words[j]
        prev_x1 = collected[-1].x1 if collected else words[colon_idx].x1
        if collected and (nxt.x0 - prev_x1) > label_gap:
            break
        # Never absorb the next value column into the label
        if _is_intact_number_token(nxt.text) or (
            is_value_like(nxt.text) and not is_label_like(nxt.text)
        ):
            break
        if collected and not is_label_like(nxt.text):
            break

        if collected:
            cur_joined = _join_words(collected)
            cur_norm = normalize_hebrew_label(cur_joined)
            cur_score = _label_phrase_score(cur_joined)
            complete = (
                is_well_formed_label(cur_norm)
                and cur_norm not in _EXTENDABLE_PARTIAL_LABELS
                and cur_norm not in _INCOMPLETE_STANDALONE_LABELS
            )
            if complete:
                ta, tb = collected[-1].text.strip(), nxt.text.strip()
                na, nb = normalize_hebrew_label(ta), normalize_hebrew_label(tb)
                bigram = (ta, tb) in _STRUCTURAL_LABEL_BIGRAMS or (
                    na,
                    nb,
                ) in _STRUCTURAL_LABEL_BIGRAMS
                trial_score = _label_phrase_score(_join_words(collected + [nxt]))
                if len(cur_norm.split()) >= 2 and not bigram:
                    break
                if not bigram and trial_score <= cur_score:
                    break

        collected.append(nxt)
        indices.append(j)
        j += 1
        if len(collected) >= MAX_LABEL_WORDS:
            break

    best = _select_best_label_phrase(collected)
    if not best:
        return [], []
    # Map best prefix back to indices
    n = len(best)
    return best, indices[:n]


def _owns_its_own_left_value(
    words: list[WordSpan],
    collected: list[WordSpan],
    indices: list[int],
    used: set[int],
) -> bool:
    """
    True when the collected tokens are a *peer label* that owns a numeric value
    of its own further left (RTL), so another colon must not consume them.

    Example row: ``100.00 % הרשמ ףקיה : הגרד`` — ``היקף משרה`` belongs to
    ``100.00``, not to the ``דרגה`` colon.
    """
    if not collected or not indices:
        return False
    joined = _join_words(collected)
    if not joined or _is_intact_number_token(joined):
        return False
    # Label phrases may carry a unit marker, but never digits
    if any(c.isdigit() for c in joined):
        return False
    phrase = joined.replace("%", " ").strip()
    if not phrase:
        return False
    if not is_well_formed_label(normalize_hebrew_label(phrase)):
        return False
    left_idx = indices[0] - 1
    if left_idx < 0 or left_idx in used:
        return False
    left = words[left_idx]
    return not _is_colon_word(left) and _is_intact_number_token(left.text)


def _collect_value_tokens_left_of_colon(
    words: list[WordSpan],
    colon_idx: int,
    used: set[int],
    gap_threshold: float,
) -> tuple[list[WordSpan], list[int]]:
    """
    Nearest valid value group spatially left of the colon (smaller x0).

    Prefers a single intact numeric WordSpan; otherwise a short Hebrew text
    group in the same local column. Does not cross other colons or used tokens.
    """
    value_gap = min(float(gap_threshold), 22.0)
    collected: list[WordSpan] = []
    indices: list[int] = []
    j = colon_idx - 1
    while j >= 0 and j not in used and not _is_colon_word(words[j]):
        w = words[j]
        if collected:
            gap = words[j + 1].x0 - w.x1
            if gap > value_gap:
                break
            # Do not grow past a complete number already collected as value
            if _is_intact_number_token(_join_words(collected)) or is_value_like(
                _join_words(collected)
            ):
                # Allow multi-token Hebrew values only
                joined = _join_words(collected)
                if not is_label_like(joined) or any(c.isdigit() for c in joined):
                    break
        collected.insert(0, w)
        indices.insert(0, j)
        j -= 1

        joined = _join_words(collected)
        # Intact number / ID / date → done
        if _is_intact_number_token(joined) or re.fullmatch(
            r"\d{1,2}/\d{1,2}/\d{2,4}(?:-\d[\d.,]*)?", joined
        ):
            break
        if is_value_like(joined) and not is_label_like(joined):
            break
        # Short Hebrew value phrase (e.g. תישדוח הרשמ, אל)
        if is_label_like(joined) and len(collected) >= 3:
            break
        if len(collected) >= 4:
            break

    if _owns_its_own_left_value(words, collected, indices, used):
        return [], []

    return collected, indices


def _field_structural_confidence(name: str, value: str, raw: str) -> tuple[str, str]:
    """
    Return (confidence, status).
    ``ok``/``high`` only for a well-formed label + intact value.
    """
    name = (name or "").strip()
    value = (value or "").strip()
    raw = (raw or "").strip()

    if not name:
        return "unknown", "unclassified"
    if _is_helper_label(name) or _is_footer_label(name):
        return "low", "unclassified"
    if not is_well_formed_label(name):
        return "low", "unclassified"
    if _is_incomplete_standalone_label(name):
        return "low", "unclassified"
    if _is_contextually_invalid_pair(name, value):
        return "low", "unclassified"
    if raw.count(":") > 1 or ":" in name:
        return "low", "unclassified"
    if len(name.split()) > MAX_LABEL_WORDS or len(name) > MAX_LABEL_CHARS:
        return "low", "unclassified"
    if _value_starts_with_punct_fragment(value) or value.startswith((".", ",")):
        return "low", "unclassified"
    if _value_is_label_fragment(value):
        return "low", "unclassified"
    if not value:
        # Empty values (e.g. מחלקה with no department) stay unclassified
        return "low", "unclassified"
    # Reject partial numbers like "22 ." or spaced fragments
    if re.search(r"\d\s+[.,]|[.,]\s+\d", value):
        return "low", "unclassified"
    label_tokens = name.split()
    if sum(1 for t in label_tokens if is_value_like(t)) >= 1 and len(label_tokens) > 2:
        return "low", "unclassified"
    return "high", "ok"


def _pair_candidate(
    label: str,
    value: str,
    raw: str,
    row: VisualRow,
    words: list[WordSpan] | None = None,
) -> FieldCandidate:
    name = normalize_hebrew_label(label.strip())
    raw_val = value.strip()
    val = normalize_hebrew_value(raw_val, name)
    conf, status = _field_structural_confidence(name, val, raw)
    bbox = bbox_from_words(row.page, words) if words else _bbox_for_substring(row, raw)

    if conf == "unknown" or _is_helper_label(name):
        return FieldCandidate(
            name="",
            value=raw.strip() or raw_val,
            raw=raw.strip(),
            bbox=bbox,
            confidence="unknown",
            status="unclassified",
        )
    if status != "ok":
        return FieldCandidate(
            name="" if _is_helper_label(name) or _is_footer_label(name) else name,
            value=val,
            raw=raw.strip(),
            bbox=bbox,
            confidence="low",
            status="unclassified",
        )
    return FieldCandidate(
        name=name,
        value=val,
        raw=raw.strip(),
        bbox=bbox,
        confidence=conf,
        status=status,
    )


def _classify_sides(left: str, right: str) -> tuple[str, str, bool]:
    """Decide (label, value, ok) from text on either side of a colon."""
    left, right = left.strip(), right.strip()
    if not left and is_label_like(right):
        return right, "", True
    if (is_value_like(left) or _is_intact_number_token(left)) and is_label_like(right):
        return right, left, True
    if (is_value_like(right) or _is_intact_number_token(right)) and is_label_like(left):
        return left, right, True
    # Both Hebrew: RTL visual — label on the right, value phrase on the left
    if is_label_like(left) and is_label_like(right):
        nl, nr = normalize_hebrew_label(left), normalize_hebrew_label(right)
        # משרה ← משרה חודשית (left is employment-type value, not a second label)
        if nr == "משרה" and ("משרה" in nl or "חודש" in nl) and nl != "משרה":
            return right, left, True
        if is_well_formed_label(nr) and len(nr.split()) <= 3:
            if is_well_formed_label(nl) and len(nl.split()) <= 2 and nl != nr:
                # Ambiguous pair of field names — do not guess
                if _hint_score(nl, _LOGICAL_LABEL_HINTS) >= 2 and _hint_score(
                    nr, _LOGICAL_LABEL_HINTS
                ) >= 2:
                    return left, right, False
            # Short yes/no / enum values on the left of a real label
            if len(left.split()) <= 3 and (
                is_well_formed_label(nr) or nr in _COMPLETE_SHORT_LABELS
            ):
                if not is_well_formed_label(nl) or len(nl) <= 3 or nr == "משרה":
                    return right, left, True
            if is_well_formed_label(nr) and len(nr.split()) <= 3:
                if not is_well_formed_label(nl) or len(nl.split()) > len(nr.split()):
                    return right, left, True
        if is_well_formed_label(nl) and len(nl.split()) <= 2:
            return left, right, True
    if is_label_like(left) and (is_value_like(right) or right):
        return left, right, True
    if is_label_like(right) and not is_label_like(left):
        return right, left, True
    if is_label_like(left):
        return left, right, True
    return left, right, False


# employment scope label comes from get_profile().employment_scope_label
_PERCENT_VALUE = re.compile(r"^\d{1,3}(?:\.\d+)?%?$")


def _bind_employment_scope(
    row: VisualRow,
    words: list[WordSpan],
    used: set[int],
) -> tuple[list[FieldCandidate], set[int]]:
    """
    Pair a colon-less ``היקף משרה %`` label with the percentage printed to its
    left on the same row.

    Emits nothing when no explicit percentage is printed — the value is never
    assumed to be 100.
    """
    free = [i for i in range(len(words)) if i not in used and not _is_colon_word(words[i])]
    if not free:
        return [], set()

    # Contiguous runs of still-unused tokens
    runs: list[list[int]] = [[free[0]]]
    for i in free[1:]:
        if i == runs[-1][-1] + 1:
            runs[-1].append(i)
        else:
            runs.append([i])

    for run in runs:
        label_idxs = [i for i in run if not _is_intact_number_token(words[i].text)]
        if not label_idxs:
            continue
        phrase = _join_words([words[i] for i in label_idxs]).replace("%", " ").strip()
        if normalize_hebrew_label(phrase) != get_profile().employment_scope_label:
            continue
        value_idx = label_idxs[0] - 1
        if value_idx < 0 or value_idx in used or value_idx not in run:
            continue
        value_word = words[value_idx]
        if not _PERCENT_VALUE.fullmatch(value_word.text):
            continue
        try:
            pct = float(value_word.text.rstrip("%"))
        except ValueError:
            continue
        if not 0.0 <= pct <= 100.0:
            continue
        pair = [value_word] + [words[i] for i in label_idxs]
        return (
            [
                FieldCandidate(
                    name=get_profile().employment_scope_label,
                    value=value_word.text,
                    raw=_join_words(pair),
                    bbox=bbox_from_words(row.page, pair),
                    confidence="high",
                    status="ok",
                )
            ],
            {value_idx, *label_idxs},
        )

    return [], set()


def _segment_work_days_department_row(
    row: VisualRow,
    words: list[WordSpan],
) -> list[FieldCandidate] | None:
    """
    Handle the repeated pattern:
    ``current :מתוך expected :ימי_עבודה [:מחלקה [value]]``
    (PDF LTR order may place מתוך before ימי עבודה).
    """
    texts = [w.text for w in words]
    blob = " ".join(texts)
    has_days_label = any(
        t in ("הדובע ימי", "ימי עבודה") or t == "ימי" or "ימי" in t
        for t in texts
    )
    has_mitoch = "ךותמ" in blob or "מתוך" in blob
    has_dept = any(
        t in ("הקלחמ", "מחלקה") or normalize_hebrew_label(t) == "מחלקה" for t in texts
    )
    # Only claim this structured pattern when days + (mitoch and/or department)
    if not has_days_label or not (has_mitoch or has_dept):
        return None

    days_pair = _extract_work_days_pair(blob)
    if not days_pair:
        return None

    cur, exp = days_pair
    days_value = f"{cur} מתוך {exp}".strip() if exp else cur
    row_raw = blob

    # Find department label token
    dept_idx = next(
        (
            i
            for i, t in enumerate(texts)
            if t in ("הקלחמ", "מחלקה") or normalize_hebrew_label(t) == "מחלקה"
        ),
        None,
    )
    dept_value = ""
    if dept_idx is not None:
        # Value is the token immediately left of ':' before department (RTL visual)
        # Pattern: [value] : הקלחמ   OR just : הקלחמ
        # Find colon just before dept label
        colon_before = dept_idx - 1 if dept_idx > 0 and _is_colon_word(words[dept_idx - 1]) else None
        if colon_before is not None and colon_before > 0:
            left = words[colon_before - 1]
            left_t = left.text.strip()
            if (
                not _is_colon_word(left)
                and not _value_is_label_fragment(left_t)
                and not _is_helper_label(normalize_hebrew_label(left_t))
                and left_t not in ("הדובע ימי", "ימי עבודה")
                and not _is_intact_number_token(left_t)  # number belongs to days, not dept
            ):
                # Only accept a real non-number dept name (Hebrew text)
                if is_label_like(left_t) and "ימי" not in left_t and "עבודה" not in left_t:
                    dept_value = left_t

    out: list[FieldCandidate] = [
        _validated_days_candidate(row_raw, days_value, row.bbox)
    ]
    if dept_value:
        out.append(
            FieldCandidate(
                name="מחלקה",
                value=dept_value,
                raw=f"{dept_value} : מחלקה",
                bbox=row.bbox,
                confidence="high",
                status="ok",
            )
        )
    elif dept_idx is not None:
        out.append(
            FieldCandidate(
                name="",
                value=texts[dept_idx] if dept_idx < len(texts) else "מחלקה",
                raw=" : ".join(t for t in texts[max(0, dept_idx - 1) : dept_idx + 1]),
                bbox=row.bbox,
                confidence="unknown",
                status="unclassified",
            )
        )
    return out


def _segment_row_by_coordinates(
    row: VisualRow,
    column_bounds: list[float] | None = None,
) -> list[FieldCandidate] | None:
    """
    Split a row using complete word tokens only.

    Cuts occur only between tokens (standalone ':' or large gaps), never
    inside a PDF word. Fragments must be reconstructed first.
    """
    if not row.words or len(row.words) < 2:
        return None

    words = reconstruct_fragments(sorted(row.words, key=lambda w: w.x0))
    row.words = words  # keep row in sync for bbox helpers

    # Still-fragmented numbers → uncertain; keep whole row unclassified
    if any(
        (t.startswith((".", ",")) and any(c.isdigit() for c in t))
        or re.fullmatch(r"\d+\s+[.,]\d+", t)
        for w in words
        for t in (w.text,)
    ):
        return [
            FieldCandidate(
                name="",
                value=row.text.strip(),
                raw=row.text.strip(),
                bbox=row.bbox,
                confidence="low",
                status="unclassified",
            )
        ]

    # Prefer structured work-days / department recognition when pattern matches
    days_row = _segment_work_days_department_row(row, words)
    if days_row is not None:
        return days_row

    colon_idxs = [i for i, w in enumerate(words) if _is_colon_word(w)]
    if not colon_idxs:
        for i, w in enumerate(words):
            t = w.text
            # Glued non-numeric token ending with ':' — not a number fragment
            if t.endswith(":") and t != ":" and not re.fullmatch(r"[\d.,/%\-]+", t[:-1] or ""):
                colon_idxs.append(i)

    if not colon_idxs:
        return None

    gaps = [words[i + 1].x0 - words[i].x1 for i in range(len(words) - 1)]
    positive = [g for g in gaps if g > 0]
    median_gap = sorted(positive)[len(positive) // 2] if positive else 4.0
    gap_threshold = max(median_gap * GAP_SPLIT_RATIO, 12.0)
    bounds = sorted(column_bounds or [])

    def _near_column_bound(x: float) -> bool:
        return any(abs(x - b) <= 14.0 for b in bounds)

    out: list[FieldCandidate] = []
    used: set[int] = set()

    # Process colons left→right (x0 order). Words are x0-sorted after reconstruct.
    for ci in colon_idxs:
        if ci in used:
            continue

        # Evaluate label + value before marking anything used, so one pair cannot
        # consume tokens that belong to another colon.
        right_words, right_idxs = _collect_label_tokens_after_colon(
            words, ci, used, gap_threshold
        )
        left_words, left_idxs = _collect_value_tokens_left_of_colon(
            words, ci, used, gap_threshold
        )

        colon_word = words[ci]
        left_text = _join_words(left_words)
        right_text = _join_words(right_words)
        if colon_word.text.endswith(":") and colon_word.text != ":":
            token = colon_word.text[:-1].strip()
            if token and not re.fullmatch(r"[\d.,/%\-]+", token):
                if not left_text:
                    left_text = token
                elif not right_text:
                    right_text = token

        if not left_text and not right_text:
            continue

        label, value, ok = _classify_sides(left_text, right_text)
        pair_words = left_words + [colon_word] + right_words
        raw = _join_words(pair_words)
        cand = _pair_candidate(label, value, raw or row.text, row, pair_words)
        if not ok and cand.status == "ok":
            cand.confidence = "low"
            cand.status = "unclassified"
        if cand.status != "ok" and _is_measure_label_without_value(cand.name, cand.value):
            # e.g. ``היקף משרה % : הגרד`` — keep the row as raw evidence only
            cand.name = ""
        out.append(cand)

        # Mark only the tokens that actually formed this pair
        used.add(ci)
        used.update(left_idxs)
        used.update(right_idxs)

    scope_cands, scope_used = _bind_employment_scope(row, words, used)
    if scope_cands:
        out.extend(scope_cands)
        used.update(scope_used)

    unused = [w for i, w in enumerate(words) if i not in used and not _is_colon_word(w)]
    if unused:
        unused = sorted(unused, key=lambda w: w.x0)
        cluster: list[WordSpan] = [unused[0]]
        for w in unused[1:]:
            if w.x0 - cluster[-1].x1 > gap_threshold:
                frag = _join_words(cluster)
                if frag:
                    out.append(
                        FieldCandidate(
                            name="",
                            value=frag,
                            raw=frag,
                            bbox=bbox_from_words(row.page, cluster),
                            confidence="unknown",
                            status="unclassified",
                        )
                    )
                cluster = [w]
            else:
                cluster.append(w)
        frag = _join_words(cluster)
        if frag:
            out.append(
                FieldCandidate(
                    name="",
                    value=frag,
                    raw=frag,
                    bbox=bbox_from_words(row.page, cluster),
                    confidence="unknown",
                    status="unclassified",
                )
            )

    if not out:
        return None

    # Prefer whole-row unclassified only when "ok" fields are actually junk
    bad_ok = [
        c
        for c in out
        if c.status == "ok"
        and (
            _value_starts_with_punct_fragment(c.value)
            or not is_well_formed_label(c.name)
            or c.value.startswith((".", ","))
        )
    ]
    if bad_ok and row.text.count(":") >= 2:
        return [
            FieldCandidate(
                name="",
                value=row.text.strip(),
                raw=row.text.strip(),
                bbox=row.bbox,
                confidence="low",
                status="unclassified",
            )
        ]

    return out


def _intact_number_texts(row: VisualRow) -> set[str]:
    """Complete numeric token texts present as whole WordSpans on the row."""
    if not row.words:
        return set()
    words = reconstruct_fragments(sorted(row.words, key=lambda w: w.x0))
    return {w.text for w in words if _is_intact_number_token(w.text)}


def _value_conflicts_with_intact_numbers(value: str, intact: set[str]) -> bool:
    """
    True when a regex-derived value is a punct fragment / partial of an intact
    WordSpan number (e.g. ``,443.85`` or ``6`` while ``6,443.85`` exists).
    """
    v = (value or "").strip()
    if not v or not intact:
        return False
    if v in intact:
        return False
    if _value_starts_with_punct_fragment(v) or v.startswith((".", ",")):
        return any(v in num and v != num for num in intact)
    # Bare digit prefix of a thousands/decimal token
    if re.fullmatch(r"\d+", v):
        return any(
            num.startswith(v + ",") or num.startswith(v + ".") for num in intact
        )
    return False


def _text_fallback_safe(
    matches: list,
    row: VisualRow,
) -> list[FieldCandidate] | None:
    """
    Build candidates from regex matches only if no match cuts an intact number.

    Returns None when word-box evidence conflicts → caller should keep row unclassified.
    """
    intact = _intact_number_texts(row)
    for m in matches:
        if _value_conflicts_with_intact_numbers(m.group("value"), intact):
            return None
    out: list[FieldCandidate] = []
    used_spans: list[tuple[int, int]] = []
    text = row.text.strip()
    for m in matches:
        raw = m.group(0).strip()
        out.append(_pair_candidate(m.group("label"), m.group("value"), raw, row))
        used_spans.append(m.span())
    leftover = text
    for start, end in sorted(used_spans, reverse=True):
        leftover = leftover[:start] + " " + leftover[end:]
    leftover = " ".join(leftover.split())
    if leftover and leftover not in {c.raw for c in out}:
        # Leftover that is a punct fragment of an intact number → conflict
        if _value_conflicts_with_intact_numbers(leftover, intact):
            return None
        # Or leftover contains a broken piece of an intact number
        for num in intact:
            if num in text and num not in leftover:
                # number was consumed into a match — OK
                continue
            if any(
                frag and frag != num and frag in num
                for frag in leftover.replace(",", " , ").split()
                if frag.startswith((",", ".")) or (frag.isdigit() and len(frag) <= 2)
            ):
                if num not in " ".join(c.value for c in out):
                    return None
        out.append(
            FieldCandidate(
                name="",
                value=leftover,
                raw=leftover,
                bbox=row.bbox,
                confidence="unknown",
                status="unclassified",
            )
        )
    return out


def segment_row_fields(
    row: VisualRow,
    column_bounds: list[float] | None = None,
    *,
    repeat_labels: set[str] | None = None,
) -> list[FieldCandidate]:
    """
    Split one visual row into one or more field candidates.

    Prefers coordinate-based splitting when words exist; falls back to
    text patterns for multi-colon reversed/normal rows only when that does
    not cut intact numeric WordSpans.
    """
    text = row.text.strip()
    if not text:
        return []

    # Ensure glued-colon preprocessing is applied on the row words
    if row.words:
        row.words = reconstruct_fragments(sorted(row.words, key=lambda w: w.x0))
        text = row.text.strip()

    colon_count = text.count(":")

    if colon_count == 0:
        # Font-glyph repairs affect the readable value only; raw stays as printed
        display = row.display_text.strip() or text
        if is_person_name_like(display):
            return [
                FieldCandidate(
                    name="",
                    value=display,
                    raw=text,
                    bbox=row.bbox,
                    confidence="medium",
                    status="name_candidate",
                )
            ]
        return [
            FieldCandidate(
                name="",
                value=text,
                raw=text,
                bbox=row.bbox,
                confidence="unknown",
                status="unclassified",
            )
        ]

    if row.words:
        coord_cands = _segment_row_by_coordinates(row, column_bounds=column_bounds)
        if coord_cands is not None:
            refined = refine_field_candidates(coord_cands)
            return _apply_repeat_label_promotion(refined, repeat_labels)

    if colon_count >= 2:
        numeric_matches = [
            m
            for m in _REVERSED_PAIR_NUMERIC.finditer(text)
            if is_label_like(m.group("label"))
            and len(m.group("label").strip()) <= MAX_LABEL_CHARS
        ]
        text_matches = [
            m
            for m in _REVERSED_PAIR_TEXT.finditer(text)
            if is_label_like(m.group("label"))
            and len(m.group("label").strip()) <= MAX_LABEL_CHARS
            and not is_value_like(m.group("label"))
        ]
        rev_matches: list = []
        occupied: list[tuple[int, int]] = []
        for m in list(numeric_matches) + list(text_matches):
            span = m.span()
            if any(not (span[1] <= a or span[0] >= b) for a, b in occupied):
                continue
            rev_matches.append(m)
            occupied.append(span)
        rev_matches.sort(key=lambda m: m.start())

        if len(rev_matches) >= 2:
            safe = _text_fallback_safe(rev_matches, row)
            if safe is None:
                return [
                    FieldCandidate(
                        name="",
                        value=text,
                        raw=text,
                        bbox=row.bbox,
                        confidence="low",
                        status="unclassified",
                    )
                ]
            return _apply_repeat_label_promotion(
                refine_field_candidates(safe), repeat_labels
            )

        norm_matches = [
            m
            for m in _NORMAL_PAIR.finditer(text)
            if is_label_like(m.group("label").strip())
        ]
        if len(norm_matches) >= 2:
            safe = _text_fallback_safe(norm_matches, row)
            if safe is None:
                return [
                    FieldCandidate(
                        name="",
                        value=text,
                        raw=text,
                        bbox=row.bbox,
                        confidence="low",
                        status="unclassified",
                    )
                ]
            return _apply_repeat_label_promotion(
                refine_field_candidates(safe), repeat_labels
            )

        return [
            FieldCandidate(
                name="",
                value=text,
                raw=text,
                bbox=row.bbox,
                confidence="low",
                status="unclassified",
            )
        ]

    return _apply_repeat_label_promotion(
        refine_field_candidates([_segment_single_colon(text, row)]),
        repeat_labels,
    )


def _segment_single_colon(text: str, row: VisualRow) -> FieldCandidate:
    before, after = text.split(":", 1)
    before, after = before.strip(), after.strip()
    label, value, ok = _classify_sides(before, after)
    if not ok and not is_label_like(label):
        return FieldCandidate(
            name="",
            value=text,
            raw=text,
            bbox=row.bbox,
            confidence="low",
            status="unclassified",
        )
    return _pair_candidate(label, value, text, row)


def _extract_work_days_pair(blob: str) -> tuple[str, str] | None:
    """Return (current, expected) work-day numbers from a *single-row* blob."""
    text = (blob or "").strip()
    if not text:
        return None
    # Must look like a work-days row (ימי), not hours (תעש / שעות)
    if "ימי" not in text and "ימי עבודה" not in normalize_hebrew_label(text):
        return None
    # Reject pure hours rows even if somehow mixed
    if ("תעש" in text or "שעות" in text) and "ימי" not in text:
        return None
    if "תעש" in text and "ימי" not in text:
        return None
    # Already-normalized logical order: current מתוך expected
    m = re.search(
        r"(?P<cur>\d+(?:[.,]\d+)?)\s+(?:מתוך|ךותמ)\s+(?P<exp>\d+(?:[.,]\d+)?)",
        text,
    )
    if m:
        return m.group("cur"), m.group("exp")
    # Reversed visual: expected :מתוך current :ימי …
    m = re.search(
        r"(?P<exp>\d+(?:[.,]\d+)?)\s*:\s*(?:ךותמ|מתוך)\s+"
        r"(?P<cur>\d+(?:[.,]\d+)?)\s*:\s*",
        text,
    )
    if m:
        return m.group("cur"), m.group("exp")
    nums = re.findall(r"\d+(?:[.,]\d+)?", text)
    has_mitoch = "מתוך" in text or "ךותמ" in text
    if has_mitoch and len(nums) >= 2:
        # In PDF LTR word order, מתוך/ךותמ number usually precedes the days number
        return nums[1], nums[0]
    if len(nums) == 1 and not has_mitoch:
        return nums[0], ""
    return None


def _numbers_in_text(text: str) -> list[str]:
    return re.findall(r"\d+(?:[.,]\d+)?", text or "")


def _value_numbers_supported_by_raw(value: str, raw: str) -> bool:
    """True when every number token in ``value`` also appears in ``raw``."""
    if not (value or "").strip():
        return False
    raw_nums = set(_numbers_in_text(raw))
    val_nums = _numbers_in_text(value)
    if not val_nums:
        return True
    return all(n in raw_nums for n in val_nums)


def _looks_like_empty_department(c: FieldCandidate) -> bool:
    name = normalize_hebrew_label((c.name or "").strip())
    val = (c.value or "").strip()
    if "מחלקה" not in name and "הקלחמ" not in (c.raw or "") and "מחלקה" not in (c.raw or ""):
        return False
    if not val or _value_starts_with_punct_fragment(val):
        return True
    # Value is actually part of work-days label (ימי / עבודה)
    if val in ("ימי", "עבודה", "ימי עבודה") or normalize_hebrew_label(val) in (
        "ימי",
        "עבודה",
        "ימי עבודה",
    ):
        return True
    return False


def _is_days_field_candidate(c: FieldCandidate) -> bool:
    name = c.name or ""
    raw = c.raw or ""
    if "שעות" in name or "שעת" in name or "תעש" in raw:
        return False
    if "ימי" in name and "עבודה" in name:
        return True
    if "הדובע ימי" in raw or "ימי עבודה" in normalize_hebrew_label(raw):
        return True
    if c.status == "ok" and "ימי" in name:
        return True
    if (
        not name
        and c.status == "unclassified"
        and "ימי" in raw
        and ("ךותמ" in raw or "מתוך" in raw or "הקלחמ" in raw)
    ):
        return True
    return False


def _validated_days_candidate(
    raw: str,
    value: str,
    bbox: dict[str, float | int] | None,
) -> FieldCandidate:
    """Emit ימי עבודה only when value numbers appear in this row's raw text."""
    raw = (raw or "").strip()
    value = (value or "").strip()
    if value and _value_numbers_supported_by_raw(value, raw):
        return FieldCandidate(
            name="ימי עבודה",
            value=value,
            raw=raw or value,
            bbox=bbox,
            confidence="high",
            status="ok",
        )
    return FieldCandidate(
        name="",
        value=raw or value,
        raw=raw or value,
        bbox=bbox,
        confidence="low",
        status="unclassified",
    )


def refine_field_candidates(candidates: list[FieldCandidate]) -> list[FieldCandidate]:
    """
    Merge helper labels (e.g. מתוך) into neighboring work-measure fields,
    synthesize intact work-days values from *each candidate's own raw*,
    and demote footer / junk fields.

    Row-local only: never reuse numbers or helpers from other rows.
    """
    if not candidates:
        return candidates

    demoted: list[FieldCandidate] = []
    for c in candidates:
        name = (c.name or "").strip()
        val = (c.value or "").strip()
        raw = (c.raw or "").strip()
        # Drop structurally invalid "ok" fields early
        if c.status == "ok" and (
            _is_footer_label(name)
            or _is_helper_label(name)
            or not is_well_formed_label(name)
            or _value_starts_with_punct_fragment(val)
            or val.startswith((".", ","))
            or (
                name
                and _numbers_in_text(val)
                and raw
                and not _value_numbers_supported_by_raw(val, raw)
            )
        ):
            demoted.append(
                FieldCandidate(
                    name="" if (_is_footer_label(name) or _is_helper_label(name)) else name,
                    value=val,
                    raw=c.raw,
                    bbox=c.bbox,
                    confidence="low",
                    status="unclassified",
                )
            )
        else:
            demoted.append(c)

    # Work-days synthesis: per candidate from its own raw only (no cross-row blob)
    rebuilt: list[FieldCandidate] = []
    for c in demoted:
        if _looks_like_empty_department(c):
            rebuilt.append(
                FieldCandidate(
                    name="",
                    value=(c.raw or c.value or "").strip(),
                    raw=(c.raw or c.value or "").strip(),
                    bbox=c.bbox,
                    confidence="unknown",
                    status="unclassified",
                )
            )
            continue

        if not _is_days_field_candidate(c):
            rebuilt.append(c)
            continue

        local_raw = (c.raw or c.value or "").strip()
        days_pair = _extract_work_days_pair(local_raw)
        if days_pair:
            cur, exp = days_pair
            value = f"{cur} מתוך {exp}".strip() if exp else cur
            rebuilt.append(_validated_days_candidate(local_raw, value, c.bbox))
        elif c.name == "ימי עבודה" and _value_numbers_supported_by_raw(c.value or "", local_raw):
            rebuilt.append(c)
        elif c.name == "ימי עבודה":
            rebuilt.append(
                FieldCandidate(
                    name="",
                    value=local_raw,
                    raw=local_raw,
                    bbox=c.bbox,
                    confidence="low",
                    status="unclassified",
                )
            )
        else:
            rebuilt.append(c)
    demoted = rebuilt

    out: list[FieldCandidate] = []
    i = 0
    while i < len(demoted):
        c = demoted[i]
        raw_l = (c.raw or "").strip()
        val_l = (c.value or "").strip()
        name_l = (c.name or "").strip()

        helper_value = ""
        is_helper = _is_helper_label(name_l)
        if not is_helper and not name_l and c.status == "unclassified":
            if any(h in raw_l or h in val_l for h in _HELPER_LABELS):
                is_helper = True

        if is_helper or (
            not name_l
            and ":" in raw_l
            and any(h in raw_l for h in _HELPER_LABELS)
        ):
            is_helper = True
            if ":" in raw_l:
                before, after = raw_l.split(":", 1)
                before, after = before.strip(), after.strip()
                if is_value_like(before) and (
                    _is_helper_label(normalize_hebrew_label(after))
                    or after in _HELPER_LABELS
                ):
                    helper_value = before
                elif is_value_like(after) and (
                    _is_helper_label(normalize_hebrew_label(before))
                    or before in _HELPER_LABELS
                ):
                    helper_value = after
            elif is_value_like(val_l):
                helper_value = val_l

        if is_helper:
            attached = False
            hv = (helper_value or val_l or "").strip()
            # Only attach helper into a neighbor that already shares this raw context
            # or whose value/raw already relates — never invent numbers from thin air.
            if out and out[-1].status == "ok" and _is_work_measure_field(out[-1].name):
                prev = out[-1]
                combined_raw = f"{prev.raw} {raw_l}".strip()
                if hv and "מתוך" not in prev.value:
                    trial = f"{prev.value} מתוך {hv}".strip()
                    if _value_numbers_supported_by_raw(trial, combined_raw):
                        prev.value = trial
                        prev.raw = combined_raw
                        attached = True
                elif hv and "מתוך" in prev.value:
                    prev.raw = combined_raw
                    attached = True
            elif (
                i + 1 < len(demoted)
                and demoted[i + 1].status == "ok"
                and _is_work_measure_field(demoted[i + 1].name)
            ):
                nxt = demoted[i + 1]
                combined_raw = f"{raw_l} {nxt.raw}".strip()
                if hv and "מתוך" not in nxt.value:
                    trial = f"{nxt.value} מתוך {hv}".strip()
                    if _value_numbers_supported_by_raw(trial, combined_raw):
                        nxt.value = trial
                        nxt.raw = combined_raw
                        attached = True
                elif hv and "מתוך" in nxt.value:
                    nxt.raw = combined_raw
                    attached = True

            if attached:
                i += 1
                continue

            out.append(
                FieldCandidate(
                    name="",
                    value=raw_l or val_l,
                    raw=raw_l or val_l,
                    bbox=c.bbox,
                    confidence="unknown",
                    status="unclassified",
                )
            )
            i += 1
            continue

        # Final guard: ok fields must not carry foreign numbers
        if (
            c.status == "ok"
            and c.name
            and raw_l
            and _numbers_in_text(val_l)
            and not _value_numbers_supported_by_raw(val_l, raw_l)
        ):
            out.append(
                FieldCandidate(
                    name="",
                    value=raw_l,
                    raw=raw_l,
                    bbox=c.bbox,
                    confidence="low",
                    status="unclassified",
                )
            )
        else:
            out.append(c)
        i += 1

    return out


def _apply_repeat_label_promotion(
    candidates: list[FieldCandidate],
    repeat_labels: set[str] | None,
) -> list[FieldCandidate]:
    """
    Promote unclassified candidates whose normalized name is in the
    request-scoped repeat set (same label across multiple payslips).

    Each candidate must independently have a valid same-row value; repeat
    evidence alone never overrides incomplete / invalid pairs.
    """
    if not candidates or not repeat_labels:
        return candidates
    out: list[FieldCandidate] = []
    for c in candidates:
        name = normalize_hebrew_label((c.name or "").strip())
        value = (c.value or "").strip()
        if (
            c.status != "ok"
            and name
            and value
            and name in repeat_labels
            and is_well_formed_label(name)
            and not _is_incomplete_standalone_label(name)
            and not _is_footer_label(name)
            and not _is_helper_label(name)
            and not _is_contextually_invalid_pair(name, value)
            and not _value_starts_with_punct_fragment(value)
            and not _value_is_label_fragment(value)
        ):
            conf, status = _field_structural_confidence(name, value, c.raw or "")
            if status == "ok":
                out.append(
                    FieldCandidate(
                        name=name,
                        value=value,
                        raw=c.raw,
                        bbox=c.bbox,
                        confidence="medium",
                        status="ok",
                    )
                )
                continue
        out.append(c)
    return out


def collect_repeatable_labels(
    draft_by_slip: list[list[FieldCandidate]],
    *,
    min_slips: int = 2,
    x_bucket: float = 28.0,
) -> set[str]:
    """
    Labels that repeat across payslips with similar colon/field X centers.

    Used to promote otherwise-unknown labels without hardcoding values or
    absolute coordinates. Footers/helpers/incomplete stems are excluded.
    Only candidates that already carry a valid same-row value contribute.
    """
    if len(draft_by_slip) < min_slips:
        return set()

    # name -> set of slip indices where it appears near a recurring x
    by_name_x: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for slip_i, cands in enumerate(draft_by_slip):
        for c in cands:
            name = normalize_hebrew_label((c.name or "").strip())
            value = (c.value or "").strip()
            if not name or _is_helper_label(name) or _is_footer_label(name):
                continue
            if "/" in name:
                continue
            if _is_incomplete_standalone_label(name):
                continue
            if not is_well_formed_label(name):
                continue
            if not c.bbox:
                continue
            if not value:
                continue
            if _value_starts_with_punct_fragment(value) or _value_is_label_fragment(value):
                continue
            if _is_contextually_invalid_pair(name, value):
                continue
            x_center = (float(c.bbox["x0"]) + float(c.bbox["x1"])) / 2.0
            by_name_x[name][slip_i].append(x_center)

    approved: set[str] = set()
    for name, per_slip in by_name_x.items():
        if len(per_slip) < min_slips:
            continue
        # Flatten xs; require at least two slips whose median x are within bucket
        slip_medians = []
        for xs in per_slip.values():
            xs_sorted = sorted(xs)
            slip_medians.append(xs_sorted[len(xs_sorted) // 2])
        slip_medians.sort()
        close_pairs = 0
        for i in range(len(slip_medians)):
            for j in range(i + 1, len(slip_medians)):
                if abs(slip_medians[i] - slip_medians[j]) <= x_bucket:
                    close_pairs += 1
        if close_pairs >= 1 and len(per_slip) >= min_slips:
            approved.add(name)
    return approved


def parse_rows_to_candidates(
    rows: list[VisualRow],
    column_bounds: list[float] | None = None,
    *,
    repeat_labels: set[str] | None = None,
) -> list[FieldCandidate]:
    """
    Segment every visual row independently.

    Refinement is row-local inside ``segment_row_fields`` — never merge
    numeric/helper state across rows. ``repeat_labels`` is request-scoped.
    """
    entries: list[FieldCandidate] = []
    for row in rows:
        entries.extend(
            segment_row_fields(
                row, column_bounds=column_bounds, repeat_labels=repeat_labels
            )
        )
    return entries


# ---------------------------------------------------------------------------
# Header payroll period + print date (title-associated, deterministic)
# ---------------------------------------------------------------------------

_HEADER_SCAN_ROWS = 8


def _unique_or_none(values: list[str]) -> str | None:
    uniq = sorted({v for v in values if v})
    if len(uniq) == 1:
        return uniq[0]
    return None


def _pick_period_word(
    words: list[WordSpan], title_words: list[WordSpan]
) -> WordSpan | None:
    """Prefer the period token nearest the title Hebrew cluster."""
    period_hits: list[tuple[float, WordSpan, str]] = []
    for w in words:
        iso = parse_payroll_period_token(w.text)
        if not iso:
            continue
        if title_words:
            dist = min(abs(w.x_center - tw.x_center) for tw in title_words)
        else:
            dist = 0.0
        period_hits.append((dist, w, iso))
    if not period_hits:
        return None
    # Conflict across distinct ISO values → refuse to guess
    if _unique_or_none([iso for _, _, iso in period_hits]) is None:
        return None
    period_hits.sort(key=lambda t: (t[0], -t[1].x0))
    return period_hits[0][1]


def _pick_print_date_word(
    words: list[WordSpan],
    print_label_bbox: dict[str, float | int] | None,
) -> WordSpan | None:
    """Prefer the full date nearest the print-date label; else leftmost."""
    hits: list[tuple[float, float, WordSpan, str]] = []
    label_cx = None
    if print_label_bbox is not None:
        label_cx = (
            float(print_label_bbox["x0"]) + float(print_label_bbox["x1"])
        ) / 2.0
    for w in words:
        iso = parse_print_date_token(w.text)
        if not iso:
            continue
        dist = abs(w.x_center - label_cx) if label_cx is not None else 0.0
        hits.append((dist, w.x0, w, iso))
    if not hits:
        return None
    if _unique_or_none([iso for _, _, _, iso in hits]) is None:
        return None
    hits.sort(key=lambda t: (t[0], t[1]))
    return hits[0][2]


def extract_payslip_header_dates(
    rows: list[VisualRow] | None = None,
    *,
    lines: list[str] | None = None,
) -> list[FieldCandidate]:
    """
    Deterministically extract ``תקופת שכר`` and ``תאריך הדפסה`` from the
    payslip title/header region.

    Requires title-associated evidence. Never infers a period from employment
    or seniority dates elsewhere on the slip. Conflicting candidates leave
    the field omitted (unclassified) rather than guessing.
    """
    out: list[FieldCandidate] = []

    if rows:
        scan = list(rows[:_HEADER_SCAN_ROWS])
        title_rows = [r for r in scan if is_payslip_title_text(r.text)]
        if not title_rows:
            return []

        print_label_rows = [r for r in scan if is_print_date_label_text(r.text)]
        print_label_bbox = print_label_rows[0].bbox if print_label_rows else None

        title_hebrew: list[WordSpan] = []
        all_header_words: list[WordSpan] = []
        for r in title_rows:
            for w in r.words:
                all_header_words.append(w)
                # Hebrew-only title tokens (ignore digits/dates)
                if re.search(r"[\u0590-\u05FF]", w.text) and not any(
                    c.isdigit() for c in w.text
                ):
                    title_hebrew.append(w)

        period_word = _pick_period_word(all_header_words, title_hebrew)
        if period_word is not None:
            iso = parse_payroll_period_token(period_word.text)
            if iso:
                out.append(
                    FieldCandidate(
                        name="תקופת שכר",
                        value=iso,
                        raw=period_word.text,
                        bbox=period_word.to_bbox(),
                        confidence="high",
                        status="ok",
                    )
                )

        # Print date: title-row dates, optionally near the print-date label
        print_word = _pick_print_date_word(all_header_words, print_label_bbox)
        if print_word is not None:
            # Require either a nearby print-date label or coexistence with title
            iso = parse_print_date_token(print_word.text)
            if iso and (print_label_bbox is not None or title_rows):
                out.append(
                    FieldCandidate(
                        name="תאריך הדפסה",
                        value=iso,
                        raw=print_word.text,
                        bbox=print_word.to_bbox(),
                        confidence="high",
                        status="ok",
                    )
                )
        return out

    # Text-only fallback (line mode) — same rules, no bbox
    if not lines:
        return []
    scan_lines = [ln.strip() for ln in lines[:_HEADER_SCAN_ROWS] if (ln or "").strip()]
    title_lines = [ln for ln in scan_lines if is_payslip_title_text(ln)]
    if not title_lines:
        return []
    has_print_label = any(is_print_date_label_text(ln) for ln in scan_lines)

    period_isos: list[str] = []
    period_raws: list[str] = []
    print_isos: list[str] = []
    print_raws: list[str] = []
    for ln in title_lines:
        for tok in ln.split():
            p = parse_payroll_period_token(tok)
            if p:
                period_isos.append(p)
                period_raws.append(tok)
            d = parse_print_date_token(tok)
            if d:
                print_isos.append(d)
                print_raws.append(tok)

    period = _unique_or_none(period_isos)
    if period is not None:
        raw = period_raws[period_isos.index(period)]
        out.append(
            FieldCandidate(
                name="תקופת שכר",
                value=period,
                raw=raw,
                bbox=None,
                confidence="high",
                status="ok",
            )
        )

    printed = _unique_or_none(print_isos)
    if printed is not None and (has_print_label or title_lines):
        raw = print_raws[print_isos.index(printed)]
        out.append(
            FieldCandidate(
                name="תאריך הדפסה",
                value=printed,
                raw=raw,
                bbox=None,
                confidence="high",
                status="ok",
            )
        )
    return out


def merge_additive_candidates(
    existing: list[FieldCandidate],
    extra: list[FieldCandidate],
) -> list[FieldCandidate]:
    """Prepend section-parser candidates without overwriting existing ok fields."""
    if not extra:
        return existing
    locked = {
        normalize_hebrew_label(c.name)
        for c in existing
        if c.status == "ok" and (c.name or "").strip()
    }
    added = [h for h in extra if normalize_hebrew_label(h.name) not in locked]
    if not added:
        return existing
    return list(added) + list(existing)


# Header dates were the first additive section parser; keep the original name
merge_header_date_candidates = merge_additive_candidates


# ---------------------------------------------------------------------------
# Payslip row grouping via start/end markers
# ---------------------------------------------------------------------------

def group_rows_into_payslips(
    rows: list[VisualRow],
    is_start,
    is_end,
) -> list[list[VisualRow]]:
    """Split visual rows into payslip blocks using the same markers as line mode."""
    payslips: list[list[VisualRow]] = []
    current: list[VisualRow] | None = None

    for row in rows:
        text = row.text
        if is_start(text):
            if current is not None and current:
                payslips.append(current)
            current = [row]
            continue
        if current is None:
            continue
        current.append(row)
        if is_end(text):
            payslips.append(current)
            current = None

    if current:
        payslips.append(current)
    return [b for b in payslips if b]


# ---------------------------------------------------------------------------
# Layout learning + employee name resolution
# ---------------------------------------------------------------------------

_ID_LABEL_HINTS = ('ת"ז', "ת.ז", "זהות", "מספר זהות")
_HOURS_LABEL_HINTS = ("שעות עבודה", "ימי עבודה")
_EMP_NUM_HINTS = ("מס' עובד", "מס׳ עובד", "עובד מס")


def _slip_top(rows: list[VisualRow]) -> float:
    return min(r.y for r in rows) if rows else 0.0


def learn_from_payslip(template: LayoutTemplate, rows: list[VisualRow], candidates: list[FieldCandidate]) -> None:
    top = _slip_top(rows)
    for row in rows:
        for w in row.words:
            if _is_colon_word(w) or (w.text.endswith(":") and w.text != ":"):
                template.record_colon_x(w.x_center)

    for cand in candidates:
        if not cand.name or not cand.bbox:
            continue
        if cand.status != "ok":
            continue
        x_center = (float(cand.bbox["x0"]) + float(cand.bbox["x1"])) / 2.0
        y_offset = float(cand.bbox["top"]) - top
        template.record_label(cand.name, x_center, y_offset)

        if any(h in cand.name for h in _EMP_NUM_HINTS) or any(
            h in cand.name for h in ("התחלת עבודה", "שנים-ותק", "שנים ותק")
        ):
            template.info_row_y_offsets.append(y_offset)
        if any(h in cand.name for h in _ID_LABEL_HINTS) or any(
            h in cand.name for h in _HOURS_LABEL_HINTS
        ):
            template.id_row_y_offsets.append(y_offset)

    for cand in candidates:
        if cand.status == "name_candidate" and is_person_name_like(cand.value):
            if cand.bbox:
                template.record_name_offset(float(cand.bbox["top"]) - top)


def collect_cross_payslip_repeats(
    draft_candidates: list[list[FieldCandidate]],
    min_fraction: float = 0.6,
) -> set[str]:
    """
    Texts that appear identically as name_candidate/unclassified Hebrew
    lines across most payslips are headers/footers — never employee names.
    """
    if not draft_candidates:
        return set()
    n = len(draft_candidates)
    threshold = max(2, int(n * min_fraction + 0.999))
    counts: dict[str, int] = defaultdict(int)
    for cands in draft_candidates:
        seen_in_slip: set[str] = set()
        for c in cands:
            if c.status not in ("name_candidate", "unclassified"):
                continue
            text = (c.value or "").strip()
            if not text or text in seen_in_slip:
                continue
            seen_in_slip.add(text)
            counts[text] += 1
    return {t for t, c in counts.items() if c >= threshold}


def _rows_are_visually_reversed(rows: list[VisualRow]) -> bool:
    """
    True when this payslip's own label text is predominantly visual RTL.

    Used as tie-break evidence for names whose reversed and un-reversed forms
    score identically; derived from the document, never from a name list.
    """
    visual = sum(_hint_score(r.text, _VISUAL_LABEL_HINTS) for r in rows)
    logical = sum(_hint_score(r.text, _LOGICAL_LABEL_HINTS) for r in rows)
    return visual > logical


def resolve_employee_names(
    template: LayoutTemplate,
    rows: list[VisualRow],
    candidates: list[FieldCandidate],
    reject_values: set[str] | None = None,
) -> list[FieldCandidate]:
    """
    Promote a name_candidate using relative position between the employee-info
    row and the ID/work-hours row. Reject header/footer and cross-slip repeats.
    """
    reject_values = reject_values or set()
    top = _slip_top(rows)
    expected = template.expected_name_offset()
    info_y = template.median(template.info_row_y_offsets)
    id_y = template.median(template.id_row_y_offsets)

    # Score all eligible candidates; pick the best one only
    scored: list[tuple[float, int, FieldCandidate]] = []
    for idx, cand in enumerate(candidates):
        if cand.name or cand.status not in ("name_candidate", "unclassified"):
            continue
        text = (cand.value or "").strip()
        if text in reject_values:
            continue
        if not is_person_name_like(text):
            continue

        y_off = float(cand.bbox["top"]) - top if cand.bbox else None
        score = 0.0

        if y_off is not None and info_y is not None and id_y is not None:
            lo, hi = (info_y, id_y) if info_y < id_y else (id_y, info_y)
            if lo < y_off < hi:
                score += 100.0
                # Prefer center of the band
                mid = (lo + hi) / 2.0
                score += max(0.0, 20.0 - abs(y_off - mid))
            else:
                # Outside the band — strong penalty (headers sit above info)
                score -= 50.0

        if y_off is not None and expected is not None:
            if abs(y_off - expected) <= 10:
                score += 40.0

        if cand.status == "name_candidate":
            score += 5.0

        scored.append((score, idx, cand))

    best_idx: int | None = None
    if scored:
        scored.sort(key=lambda t: (-t[0], t[1]))
        best_score, best_idx, best_cand = scored[0]
        # Require a positive score (must match band or expected offset)
        if best_score < 20:
            best_idx = None

    out: list[FieldCandidate] = []
    for idx, cand in enumerate(candidates):
        text = (cand.value or "").strip()
        # Downgrade rejected header-like candidates
        if (
            not cand.name
            and cand.status in ("name_candidate", "unclassified")
            and text in reject_values
        ):
            out.append(
                FieldCandidate(
                    name="",
                    value=cand.value,
                    raw=cand.raw,
                    bbox=cand.bbox,
                    confidence="unknown",
                    status="unclassified",
                )
            )
            continue

        if best_idx is not None and idx == best_idx:
            y_off = float(cand.bbox["top"]) - top if cand.bbox else None
            raw_name = (cand.raw or cand.value or "").strip()
            display_name, safe = normalize_person_name(
                cand.value or "",
                prefer_unreversed=_rows_are_visually_reversed(rows),
            )
            # Preserve original PDF text in raw; store logical name in value
            conf = "high" if (info_y is not None and id_y is not None) else "medium"
            if not safe:
                # Still emit the name; lowered confidence, raw preserved, no glyph guessing
                conf = "medium"
            out.append(
                FieldCandidate(
                    name="שם עובד",
                    value=display_name,
                    raw=raw_name,
                    bbox=cand.bbox,
                    confidence=conf,
                    status="ok",
                )
            )
            if y_off is not None:
                template.record_name_offset(y_off)
            continue

        out.append(cand)

    return out


def candidates_to_entries(candidates: Iterable[FieldCandidate]) -> list[dict[str, Any]]:
    return [c.to_entry() for c in candidates]


def entries_to_fields_map(entries: list[dict[str, Any]]) -> dict[str, str]:
    """
    Convenience projection of *reliable* fields only.

    Only ``status == ok`` entries with a well-formed label and intact value
    enter the map. Helpers, footers, punct fragments, and duplicates stay out.
    Keys are always normalized logical labels (never visual glued forms).
    """
    fields: dict[str, str] = {}
    for e in entries:
        if (e.get("status") or "") != "ok":
            continue
        name = normalize_hebrew_label((e.get("name") or "").strip())
        value = (e.get("value") or "").strip()
        if not name or name in fields:
            continue
        if _is_helper_label(name) or _is_footer_label(name):
            continue
        if not is_well_formed_label(name):
            continue
        if _value_starts_with_punct_fragment(value) or value.startswith((".", ",")):
            continue
        if _value_is_label_fragment(value):
            continue
        if re.search(r"\d\s+[.,]|[.,]\s+\d", value):
            continue
        conf = (e.get("confidence") or "").strip()
        if conf in ("low", "unknown"):
            continue
        fields[name] = value
    return fields
