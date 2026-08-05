"""
Recover Hebrew letters that a broken embedded font maps to a non-Hebrew glyph.

Some payroll PDFs ship a subset CID font whose ``ToUnicode`` table has a hole:
one CID in an otherwise contiguous Hebrew alphabet block points at a Latin
codepoint (for example ``ð``, U+00F0). The correct letter is *derived* from the
CIDs on both sides — never guessed and never hardcoded per document.

Nothing is repaired unless the neighbouring CIDs prove the intended letter, and
the repair is always scoped to the specific font that produced the glyph.
"""

from __future__ import annotations

import re
from typing import Any

from pdfminer.pdftypes import PDFStream, resolve1

_HEBREW_FIRST = 0x05D0  # א
_HEBREW_LAST = 0x05EA  # ת

_BFCHAR_PAIR = re.compile(r"<([0-9A-Fa-f]{2,8})>\s*<([0-9A-Fa-f]{4,})>")


def _is_hebrew_letter(codepoint: int) -> bool:
    return _HEBREW_FIRST <= codepoint <= _HEBREW_LAST


def _font_name(font: Any) -> str:
    base = font.get("BaseFont")
    name = getattr(base, "name", None)
    return str(name or base or "").strip()


def _parse_tounicode(stream: PDFStream) -> dict[int, str]:
    """Parse ``beginbfchar`` pairs into {cid: unicode_text}."""
    try:
        data = stream.get_data()
    except Exception:  # noqa: BLE001 - unreadable stream is simply not usable
        return {}
    text = data.decode("utf-8", errors="replace")
    mapping: dict[int, str] = {}
    for cid_hex, uni_hex in _BFCHAR_PAIR.findall(text):
        try:
            cid = int(cid_hex, 16)
        except ValueError:
            continue
        chunks = [uni_hex[i : i + 4] for i in range(0, len(uni_hex), 4)]
        try:
            value = "".join(chr(int(c, 16)) for c in chunks if len(c) == 4)
        except ValueError:
            continue
        if value:
            mapping[cid] = value
    return mapping


def derive_glyph_overrides(cid_to_unicode: dict[int, str]) -> dict[str, str]:
    """
    Infer {wrong_glyph: hebrew_letter} from CID neighbours.

    A CID is repairable only when its neighbours map to Hebrew letters exactly
    two codepoints apart, which leaves a single possible letter in between.
    """
    overrides: dict[str, str] = {}
    for cid, value in cid_to_unicode.items():
        if len(value) != 1 or _is_hebrew_letter(ord(value)):
            continue
        before = cid_to_unicode.get(cid - 1)
        after = cid_to_unicode.get(cid + 1)
        if not before or not after or len(before) != 1 or len(after) != 1:
            continue
        low, high = ord(before), ord(after)
        if not (_is_hebrew_letter(low) and _is_hebrew_letter(high)):
            continue
        if high - low != 2:
            continue
        letter = chr(low + 1)
        if overrides.get(value, letter) != letter:
            # The same glyph would resolve to two different letters — unsafe
            overrides.pop(value, None)
            continue
        overrides[value] = letter
    return overrides


def page_glyph_overrides(page: Any) -> dict[str, dict[str, str]]:
    """
    Build {fontname: {wrong_glyph: hebrew_letter}} for one pdfplumber page.

    Returns an empty mapping when the page has no provable repair.
    """
    try:
        resources = resolve1(page.page_obj.resources) or {}
        fonts = resolve1(resources.get("Font")) or {}
    except Exception:  # noqa: BLE001 - malformed resources are not repairable
        return {}

    result: dict[str, dict[str, str]] = {}
    for font_ref in getattr(fonts, "values", lambda: [])():
        try:
            font = resolve1(font_ref)
            name = _font_name(font)
            to_unicode = resolve1(font.get("ToUnicode"))
        except Exception:  # noqa: BLE001
            continue
        if not name or not isinstance(to_unicode, PDFStream):
            continue
        overrides = derive_glyph_overrides(_parse_tounicode(to_unicode))
        if overrides:
            result[name] = overrides
    return result


def repair_word_text(
    text: str,
    word_chars: list[dict[str, Any]],
    overrides_by_font: dict[str, dict[str, str]],
) -> str | None:
    """
    Repair a word's text using only glyphs proven for the font that drew them.

    Returns ``None`` when nothing is repairable, so callers can keep the
    original text untouched.
    """
    if not text or not overrides_by_font or not word_chars:
        return None

    replacements: dict[str, str] = {}
    for char in word_chars:
        glyph = char.get("text") or ""
        if len(glyph) != 1:
            continue
        font_map = overrides_by_font.get(str(char.get("fontname") or ""))
        if not font_map:
            continue
        letter = font_map.get(glyph)
        if letter:
            replacements[glyph] = letter

    if not replacements:
        return None

    # Every occurrence in the word must be backed by a proven char
    for glyph in replacements:
        drawn = sum(
            1
            for c in word_chars
            if (c.get("text") or "") == glyph
            and glyph in (overrides_by_font.get(str(c.get("fontname") or "")) or {})
        )
        if text.count(glyph) != drawn:
            return None

    repaired = text
    for glyph, letter in replacements.items():
        repaired = repaired.replace(glyph, letter)
    return repaired if repaired != text else None
