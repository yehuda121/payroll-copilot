"""Shared Hebrew label normalization utilities (company vocab via active profile)."""

from __future__ import annotations

import re
from datetime import date

from payroll_copilot.application.services.company_payslip_extraction.core.profile import get_profile

_HEBREW_CHAR = re.compile(r"[\u0590-\u05FF]")
_HEBREW_RUN = re.compile(
    r"['׳״\"]?[\u0590-\u05FF]+(?:['׳״\"]+[\u0590-\u05FF]+)*['׳״\"]?"
)

# Seniority cells print a reference date and the years value in one token:
# ``01/07/26-0.00`` → date ``01/07/26`` + ``0.00`` years.
_SENIORITY_COMPOSITE = re.compile(
    r"(?P<date>\d{1,2}/\d{1,2}/\d{2,4})-(?P<years>\d+(?:[.,]\d+)?)"
)

# Payroll period: M/YY, MM/YY, M/YYYY, MM/YYYY (exactly one slash)
_PAYROLL_PERIOD_TOKEN = re.compile(
    r"^(?P<month>0?[1-9]|1[0-2])/(?P<year>\d{2}|\d{4})$"
)
# Print date: DD/MM/YY or DD/MM/YYYY (exactly two slashes)
_PRINT_DATE_TOKEN = re.compile(
    r"^(?P<day>0?[1-9]|[12]\d|3[01])/(?P<month>0?[1-9]|1[0-2])/(?P<year>\d{2}|\d{4})$"
)

# Glyphs that signal PDF font corruption — never invent replacements for names
_CORRUPT_NAME_GLYPHS = re.compile(
    r"[ðÐþÞ\ufffd\uFFFD\u00a0]|(?<![\u0590-\u05FF])[øØ](?![\u0590-\u05FF])"
)
_FINAL_HEBREW = set("ךםןףץ")
# Common logical Hebrew name endings (first/last) — scoring only, not a hard allow-list
_NAME_ENDINGS = (
    "ית",
    "ין",
    "אל",
    "אה",
    "וה",
    "ון",
    "יה",
    "לי",
    "רי",
    "בי",
    "וי",
    "קי",
    "צי",
    "סקי",
    "ביץ",
    "וביץ",
    "מן",
    "רג",
)


# ---------------------------------------------------------------------------
# Profile-backed accessors (compat names used by layout)
# ---------------------------------------------------------------------------

class _HintProxy:
    """Tuple-like proxy so ``_hint_score(text, _LOGICAL_LABEL_HINTS)`` still works."""

    def __init__(self, attr: str) -> None:
        self._attr = attr

    def __iter__(self):
        return iter(getattr(get_profile(), self._attr))

    def __contains__(self, item: object) -> bool:
        return item in getattr(get_profile(), self._attr)


_LOGICAL_LABEL_HINTS = _HintProxy("logical_label_hints")  # type: ignore[assignment]
_VISUAL_LABEL_HINTS = _HintProxy("visual_label_hints")  # type: ignore[assignment]


class _MappingProxy:
    def __init__(self, attr: str) -> None:
        self._attr = attr

    def __contains__(self, item: object) -> bool:
        return item in getattr(get_profile(), self._attr)

    def __getitem__(self, item: str) -> str:
        return getattr(get_profile(), self._attr)[item]

    def get(self, item: str, default=None):
        return getattr(get_profile(), self._attr).get(item, default)

    def items(self):
        return getattr(get_profile(), self._attr).items()


class _SetProxy:
    def __init__(self, attr: str) -> None:
        self._attr = attr

    def __contains__(self, item: object) -> bool:
        return item in getattr(get_profile(), self._attr)

    def __iter__(self):
        return iter(getattr(get_profile(), self._attr))


_LABEL_ALIASES = _MappingProxy("label_aliases")
_YES_NO_VALUE_ALIASES = _MappingProxy("yes_no_value_aliases")
_EMPLOYMENT_TYPE_TOKENS = _MappingProxy("employment_type_tokens")
APOSTROPHE_LABEL_ALLOW = _SetProxy("apostrophe_label_allow")


def normalize_employment_type(value: str) -> str | None:
    """
    Logical form of an employment-type value, or ``None`` when unknown.

    Visual RTL phrases are read right-to-left (``תישדוח הרשמ`` → ``משרה חודשית``);
    input that is already logical is returned as-is.
    """
    tokens = (value or "").split()
    if not tokens:
        return None
    table = get_profile().employment_type_tokens
    mapped = [table.get(t) for t in tokens]
    if any(m is None for m in mapped):
        return None
    if all(token == word for token, word in zip(tokens, mapped)):
        return " ".join(mapped)  # type: ignore[arg-type]
    return " ".join(reversed(mapped))  # type: ignore[arg-type]


def _hint_score(text: str, hints) -> int:
    return sum(1 for h in hints if h in text)


def hebrew_ratio(text: str) -> float:
    if not text:
        return 0.0
    letters = [c for c in text if c.isalpha() or _HEBREW_CHAR.match(c)]
    if not letters:
        return 0.0
    return sum(1 for c in text if _HEBREW_CHAR.match(c)) / max(len(letters), 1)


def unreverse_hebrew_runs(text: str) -> str:
    if not text or not _HEBREW_CHAR.search(text):
        return text
    return _HEBREW_RUN.sub(lambda m: m.group(0)[::-1], text)


def name_has_corrupt_glyphs(text: str) -> bool:
    """True when the PDF text layer contains untrustworthy glyphs (e.g. ð)."""
    if not text:
        return False
    if "ð" in text or "Ð" in text or "\ufffd" in text or "�" in text:
        return True
    for word in text.split():
        has_he = bool(_HEBREW_CHAR.search(word))
        has_lat = bool(re.search(r"[A-Za-zðÐþÞ]", word))
        if has_he and has_lat:
            return True
    return bool(_CORRUPT_NAME_GLYPHS.search(text))


def _logical_person_name_score(text: str) -> int:
    """Higher is more likely logical (human-readable) Hebrew name order."""
    score = 0
    words = text.split()
    if not (2 <= len(words) <= 4):
        score -= 5
    for w in words:
        if not w:
            continue
        if w[0] in _FINAL_HEBREW:
            score -= 12
        if any(c in _FINAL_HEBREW for c in w[:-1]):
            score -= 8
        if w[-1] in _FINAL_HEBREW:
            score += 2
        if any(w.endswith(e) for e in _NAME_ENDINGS):
            score += 3
        if w[0] in "אבגהוזחטיכלמנסעפצקרשת":
            score += 1
    return score


def normalize_person_name(
    text: str,
    *,
    prefer_unreversed: bool = False,
) -> tuple[str, bool]:
    """
    Normalize a detected employee name into logical Hebrew reading order.

    Returns ``(value, safe)``.
    """
    original = (text or "").strip()
    if not original:
        return original, False

    if name_has_corrupt_glyphs(original):
        return original, False

    if hebrew_ratio(original) < 0.5:
        return original, True

    cleaned = re.sub(r"[\u200e\u200f\u202a-\u202e\ufeff]", "", original).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)

    unreversed = unreverse_hebrew_runs(cleaned)
    parts = unreversed.split()
    reordered = " ".join(reversed(parts)) if len(parts) > 1 else unreversed

    candidates = (
        [unreversed, reordered, cleaned] if prefer_unreversed
        else [cleaned, unreversed, reordered]
    )
    preferred = candidates[0]
    best = max(candidates, key=lambda c: (_logical_person_name_score(c), c == preferred))
    if _logical_person_name_score(best) < _logical_person_name_score(cleaned):
        return cleaned, True
    return best, True


def normalize_hebrew_label(text: str) -> str:
    """
    Normalize a field *label* when clearly visually reversed.
    Does not touch dates, numbers, or arbitrary values — call only on labels.
    """
    text = text.strip()
    if not text:
        return text

    aliases = get_profile().label_aliases
    if text in aliases:
        return aliases[text]

    if hebrew_ratio(text) < 0.3:
        return text

    fixed = unreverse_hebrew_runs(text)
    if fixed in aliases:
        return aliases[fixed]

    words = fixed.split()
    reordered = " ".join(reversed(words)) if len(words) > 1 else fixed
    if reordered in aliases:
        return aliases[reordered]

    logical_hints = get_profile().logical_label_hints
    visual_hints = get_profile().visual_label_hints

    def _rank(candidate: str) -> tuple[int, int]:
        logical = _hint_score(candidate, logical_hints)
        visual = _hint_score(candidate, visual_hints)
        return (logical - visual, logical)

    orig_rank = _rank(text)
    fixed_rank = _rank(fixed)
    reordered_rank = _rank(reordered)

    if (
        orig_rank >= fixed_rank
        and orig_rank >= reordered_rank
        and _hint_score(text, visual_hints) == 0
    ):
        return text

    if reordered_rank > fixed_rank:
        return reordered
    if reordered_rank == fixed_rank and reordered_rank > orig_rank:
        return reordered
    if fixed_rank > orig_rank:
        return fixed
    return text


def is_seniority_field(field_name: str) -> bool:
    """True for the seniority-years label (``שנים-ותק`` and spelling variants)."""
    n = normalize_hebrew_label((field_name or "").strip())
    if not n or "ותק" not in n:
        return False
    return n == "ותק" or "שנים" in n or "שנות" in n


def parse_seniority_years(value: str) -> str | None:
    """
    Extract the years portion of a ``DD/MM/YY-years`` seniority cell.

    Returns ``None`` for anything else, so Israeli ID tokens such as
    ``30491361-9`` and plain numbers are never split.
    """
    v = (value or "").strip()
    if not v:
        return None
    match = _SENIORITY_COMPOSITE.fullmatch(v)
    if not match:
        return None
    return match.group("years")


def normalize_hebrew_value(value: str, field_name: str = "") -> str:
    """
    Field-scoped safe normalization for short Hebrew *values*.
    """
    v = (value or "").strip()
    if not v:
        return v

    field = normalize_hebrew_label((field_name or "").strip())

    if is_seniority_field(field):
        years = parse_seniority_years(v)
        if years is not None:
            return years

    if re.fullmatch(r"[\d\s.,/\-%]+", v):
        return v

    yes_no = get_profile().yes_no_value_aliases
    if "זוג" in field or field in {"בן זוג עובד"}:
        if v in yes_no:
            return yes_no[v]
        fixed = unreverse_hebrew_runs(v)
        if fixed in yes_no:
            return yes_no[fixed]

    if field == "משרה" and is_label_like(v):
        employment = normalize_employment_type(v)
        if employment is not None:
            return employment
        return normalize_hebrew_label(v)

    return v


def is_value_like(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if re.fullmatch(r"\d[\d.,/\-%]*", t):
        return True
    if re.fullmatch(r"[\d\s.,/%\-]+", t):
        return True
    if not _HEBREW_CHAR.search(t) and any(c.isdigit() for c in t):
        return True
    return False


def is_label_like(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    return hebrew_ratio(t) >= 0.45


def is_well_formed_label(text: str) -> bool:
    """
    True when a normalized label looks like a real form field name —
    not a visual fragment, footer, or slash-mangled token.
    """
    raw = (text or "").strip()
    if not raw:
        return False
    if "/" in raw:
        return False
    n = normalize_hebrew_label(raw)
    if not n or "/" in n:
        return False
    visual_hints = get_profile().visual_label_hints
    logical_hints = get_profile().logical_label_hints
    if _hint_score(n, visual_hints) > 0:
        return False
    if n in {'ת"ז', "ת.ז", "מס' עובד", "מס׳ עובד"}:
        return True
    if _hint_score(n, logical_hints) == 0:
        return False
    if len(n) <= 3 and n not in {"שם", "נטו"}:
        return False
    return True


def is_person_name_like(text: str) -> bool:
    """Hebrew full-name heuristic (2–4 words, mostly letters, no digits)."""
    t = text.strip()
    if not t or any(c.isdigit() for c in t):
        return False
    if ":" in t:
        return False
    ratio_text = re.sub(r"[ðÐþÞ\ufffd�]", "", t)
    if hebrew_ratio(ratio_text if ratio_text.strip() else t) < 0.7:
        return False
    words = t.split()
    if not (2 <= len(words) <= 4):
        return False

    banned_substrings = get_profile().name_reject_substrings
    if any(b in t for b in banned_substrings):
        return False

    normalized = normalize_hebrew_label(t)
    if normalized in {"שם עובד", "שם העובד", "תאריך הדפסה", "הדפסה תאריך"}:
        return False
    if "תאריך" in normalized or "הדפסה" in normalized:
        return False

    return True


def normalize_document_year(year: int) -> int | None:
    """
    Normalize a year into the 2000s range used by these documents.
    """
    if year < 0:
        return None
    if year <= 99:
        year = 2000 + year
    if 2000 <= year <= 2099:
        return year
    return None


def parse_payroll_period_token(token: str) -> str | None:
    """Parse a payroll-period token into canonical ``YYYY-MM``."""
    t = (token or "").strip()
    if not t or t.count("/") != 1:
        return None
    match = _PAYROLL_PERIOD_TOKEN.fullmatch(t)
    if not match:
        return None
    month = int(match.group("month"))
    year = normalize_document_year(int(match.group("year")))
    if year is None or not (1 <= month <= 12):
        return None
    return f"{year:04d}-{month:02d}"


def parse_print_date_token(token: str) -> str | None:
    """Parse a print-date token into canonical ``YYYY-MM-DD``."""
    t = (token or "").strip()
    if not t or t.count("/") != 2:
        return None
    match = _PRINT_DATE_TOKEN.fullmatch(t)
    if not match:
        return None
    day = int(match.group("day"))
    month = int(match.group("month"))
    year = normalize_document_year(int(match.group("year")))
    if year is None:
        return None
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def is_payslip_title_text(text: str) -> bool:
    """True when text looks like the payslip title (logical or visual)."""
    t = (text or "").strip()
    if not t:
        return False
    markers = get_profile().title_markers
    if any(m in t for m in markers):
        return True
    norm = normalize_hebrew_label(t)
    return "תלוש" in norm or "משכורת" in norm


def is_print_date_label_text(text: str) -> bool:
    """True when text is the print-date label (logical or visual)."""
    t = (text or "").strip()
    if not t:
        return False
    if "הספדה" in t and "ךיראת" in t:
        return True
    norm = normalize_hebrew_label(t)
    return norm in {"תאריך הדפסה", "הדפסה תאריך"} or (
        "תאריך" in norm and "הדפסה" in norm
    )
