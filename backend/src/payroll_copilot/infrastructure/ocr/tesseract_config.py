"""Tesseract multi-PSM configuration helpers."""

from __future__ import annotations

from dataclasses import dataclass

from payroll_copilot.application.exceptions import OcrProviderError

# Tesseract PSM modes commonly used for documents (subset of 0–13).
_ALLOWED_PSM = frozenset(range(0, 14))


@dataclass(frozen=True, slots=True)
class TesseractStrategyConfig:
    """Immutable multi-PSM OCR strategy settings."""

    multi_psm_enabled: bool = False
    psm_candidates: tuple[int, ...] = (3, 4, 6, 11)
    primary_psm: int = 3
    fallback_psm: int = 6
    default_oem: int = 3
    max_candidates: int = 4
    min_valid_word_confidence: float = 0.0
    min_usable_text_chars: int = 20
    max_pages: int = 20


def parse_psm_candidates(
    raw: str | list[int] | tuple[int, ...] | None,
    *,
    max_candidates: int = 4,
) -> tuple[int, ...]:
    """Parse and validate a PSM candidate list.

    Accepts comma-separated strings (env) or sequences of ints.
    Removes duplicates (first occurrence wins) and enforces max_candidates.
    """
    if max_candidates < 1:
        raise OcrProviderError("OCR_TESSERACT_MAX_CANDIDATES must be >= 1.")

    values: list[int] = []
    if raw is None or raw == "":
        values = [3, 4, 6, 11]
    elif isinstance(raw, str):
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        if not parts:
            raise OcrProviderError("OCR_TESSERACT_PSM_CANDIDATES is empty.")
        for part in parts:
            try:
                value = int(part)
            except ValueError as exc:
                raise OcrProviderError(
                    f"Invalid PSM candidate '{part}'. Expected integers 0–13."
                ) from exc
            values.append(value)
    else:
        values = [int(item) for item in raw]

    seen: set[int] = set()
    unique: list[int] = []
    for value in values:
        if value not in _ALLOWED_PSM:
            raise OcrProviderError(
                f"Invalid PSM candidate {value}. Allowed Tesseract PSM values are 0–13."
            )
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)

    if not unique:
        raise OcrProviderError("No valid PSM candidates configured.")

    return tuple(unique[: max_candidates])


def tesseract_strategy_from_settings(settings: object) -> TesseractStrategyConfig:
    max_candidates = int(getattr(settings, "ocr_tesseract_max_candidates", 4))
    raw_psm = getattr(settings, "ocr_tesseract_psm_candidates", "3,4,6,11")
    candidates = parse_psm_candidates(raw_psm, max_candidates=max_candidates)
    primary = candidates[0] if candidates else 3
    fallback = candidates[1] if len(candidates) > 1 else 6
    return TesseractStrategyConfig(
        multi_psm_enabled=bool(getattr(settings, "ocr_tesseract_multi_psm_enabled", False)),
        psm_candidates=candidates,
        primary_psm=int(getattr(settings, "ocr_tesseract_primary_psm", primary)),
        fallback_psm=int(getattr(settings, "ocr_tesseract_fallback_psm", fallback)),
        default_oem=int(getattr(settings, "ocr_tesseract_default_oem", 3)),
        max_candidates=max_candidates,
        min_valid_word_confidence=float(
            getattr(settings, "ocr_tesseract_min_valid_word_confidence", 0.0)
        ),
        min_usable_text_chars=int(getattr(settings, "ocr_tesseract_min_usable_text_chars", 20)),
        max_pages=int(getattr(settings, "ocr_tesseract_max_pages", 20)),
    )


def build_tesseract_config(*, oem: int, psm: int) -> str:
    return f"--oem {int(oem)} --psm {int(psm)}"
