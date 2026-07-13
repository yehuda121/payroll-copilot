"""Deterministic quality scoring for Tesseract multi-PSM candidates.

Scores are general OCR-quality signals only — no fixture-specific or payroll
business rules. Confidence (engine) and quality score (selection) are separate.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from payroll_copilot.infrastructure.ocr.tesseract_layout import LayoutCandidate

_HEBREW = re.compile(r"[\u0590-\u05FF]")
_ARABIC = re.compile(r"[\u0600-\u06FF]")
_LATIN = re.compile(r"[A-Za-z]")
_DIGIT = re.compile(r"[0-9]")
_PUNCT = re.compile(r"[.,;:%/+\-()\[\]{}'\"₪$€£]")


@dataclass(frozen=True, slots=True)
class CandidateMetrics:
    mean_confidence: float
    valid_word_count: int
    non_empty_line_count: int
    alnum_ratio: float
    script_ratio: float
    duplicate_ratio: float
    single_char_ratio: float
    punct_ratio: float
    script_mix_penalty: float
    coverage_score: float


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _expected_scripts(tess_lang: str) -> set[str]:
    packs = {part.strip() for part in tess_lang.split("+") if part.strip()}
    scripts: set[str] = {"digit", "punct", "space"}
    if "heb" in packs:
        scripts.add("hebrew")
    if "eng" in packs:
        scripts.add("latin")
    if "ara" in packs:
        scripts.add("arabic")
    if not packs.intersection({"heb", "eng", "ara"}):
        scripts.update({"hebrew", "latin", "arabic"})
    return scripts


def _char_kind(ch: str) -> str:
    if ch.isspace():
        return "space"
    if _HEBREW.match(ch):
        return "hebrew"
    if _ARABIC.match(ch):
        return "arabic"
    if _LATIN.match(ch):
        return "latin"
    if _DIGIT.match(ch):
        return "digit"
    if _PUNCT.match(ch):
        return "punct"
    return "other"


def compute_candidate_metrics(
    candidate: LayoutCandidate,
    *,
    tess_lang: str,
    image_width: int,
    image_height: int,
) -> CandidateMetrics:
    words = list(candidate.words)
    text = candidate.text or ""
    mean_conf = float(candidate.mean_confidence or 0.0)
    word_count = len(words)

    non_space = [ch for ch in text if not ch.isspace()]
    total_ns = len(non_space) or 1
    alnum = sum(1 for ch in non_space if ch.isalnum() or _HEBREW.match(ch) or _ARABIC.match(ch))
    alnum_ratio = alnum / total_ns

    expected = _expected_scripts(tess_lang)
    compatible = 0
    kinds_present: set[str] = set()
    for ch in non_space:
        kind = _char_kind(ch)
        kinds_present.add(kind)
        if kind in expected or kind in {"digit", "punct"}:
            compatible += 1
    script_ratio = compatible / total_ns

    # Bilingual documents are expected for heb+eng / ara+eng; penalize unexpected third scripts.
    unexpected = kinds_present - expected - {"other"}
    script_mix_penalty = 0.0
    if "other" in kinds_present:
        other_count = sum(1 for ch in non_space if _char_kind(ch) == "other")
        script_mix_penalty += other_count / total_ns
    if "arabic" in unexpected and "arabic" not in expected:
        arab_count = sum(1 for ch in non_space if _char_kind(ch) == "arabic")
        script_mix_penalty += arab_count / total_ns
    if "hebrew" in unexpected and "hebrew" not in expected:
        heb_count = sum(1 for ch in non_space if _char_kind(ch) == "hebrew")
        script_mix_penalty += heb_count / total_ns

    tokens = [w.text for w in words]
    if tokens:
        unique = len(set(tokens))
        duplicate_ratio = 1.0 - (unique / len(tokens))
        single_char_ratio = sum(1 for t in tokens if len(t) == 1) / len(tokens)
    else:
        duplicate_ratio = 0.0
        single_char_ratio = 0.0

    punct_count = sum(1 for ch in non_space if _char_kind(ch) == "punct")
    punct_ratio = punct_count / total_ns

    # Layout coverage: fraction of image area covered by word boxes (capped).
    image_area = max(1, int(image_width) * int(image_height))
    covered = 0.0
    for word in words:
        x, y, w, h = word.bbox
        covered += max(0.0, w) * max(0.0, h)
    coverage_raw = covered / image_area
    # Prefer moderate coverage (tables/forms); very tiny or near-full both score lower.
    if coverage_raw <= 0:
        coverage_score = 0.0
    elif coverage_raw < 0.02:
        coverage_score = coverage_raw / 0.02 * 0.5
    elif coverage_raw <= 0.55:
        coverage_score = 0.5 + (coverage_raw - 0.02) / (0.55 - 0.02) * 0.5
    else:
        coverage_score = max(0.2, 1.0 - (coverage_raw - 0.55))

    return CandidateMetrics(
        mean_confidence=_clamp01(mean_conf),
        valid_word_count=word_count,
        non_empty_line_count=candidate.non_empty_line_count,
        alnum_ratio=_clamp01(alnum_ratio),
        script_ratio=_clamp01(script_ratio),
        duplicate_ratio=_clamp01(duplicate_ratio),
        single_char_ratio=_clamp01(single_char_ratio),
        punct_ratio=_clamp01(punct_ratio),
        script_mix_penalty=_clamp01(script_mix_penalty),
        coverage_score=_clamp01(coverage_score),
    )


def score_candidate_metrics(metrics: CandidateMetrics) -> float:
    """Bounded 0–1 quality score from normalized metrics."""
    # Soft-saturate word/line counts so larger documents don't dominate unbounded.
    word_signal = math.tanh(metrics.valid_word_count / 40.0)
    line_signal = math.tanh(metrics.non_empty_line_count / 20.0)

    positive = (
        0.28 * metrics.mean_confidence
        + 0.16 * word_signal
        + 0.10 * line_signal
        + 0.14 * metrics.alnum_ratio
        + 0.14 * metrics.script_ratio
        + 0.08 * metrics.coverage_score
    )
    penalties = (
        0.12 * metrics.duplicate_ratio
        + 0.10 * metrics.single_char_ratio
        + 0.08 * max(0.0, metrics.punct_ratio - 0.25)
        + 0.20 * metrics.script_mix_penalty
    )
    return _clamp01(positive - penalties)


def score_layout_candidate(
    candidate: LayoutCandidate,
    *,
    tess_lang: str,
    image_width: int,
    image_height: int,
) -> float:
    metrics = compute_candidate_metrics(
        candidate,
        tess_lang=tess_lang,
        image_width=image_width,
        image_height=image_height,
    )
    return score_candidate_metrics(metrics)


def select_best_candidate(
    scored: list[tuple[int, float, float, int, LayoutCandidate]],
) -> tuple[int, float, LayoutCandidate]:
    """Select best candidate.

    ``scored`` items: ``(psm, quality_score, mean_confidence, valid_word_count, candidate)``.

    Tie-break: higher score → higher mean confidence → more words → lower PSM.
    """
    if not scored:
        raise ValueError("No OCR candidates to select.")

    def sort_key(item: tuple[int, float, float, int, LayoutCandidate]) -> tuple:
        psm, score, mean_conf, words, _candidate = item
        return (score, mean_conf, words, -psm)

    best = max(scored, key=sort_key)
    return best[0], best[1], best[4]
