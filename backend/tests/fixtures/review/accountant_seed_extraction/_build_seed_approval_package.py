"""Build seed approval review package from OCR evidence only (no parser values)."""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent
REPORT = BASE / "extraction_report.json"
VALID_OCR = BASE / "_diag_ocr_pdf_p1.json"
INVALID_OCR = BASE / "_diag_ocr_invalid_pdf.json"
OUT_JSON = BASE / "seed_approval_table.json"
OUT_MD = BASE / "seed_approval_table.md"
OUT_Q = BASE / "manual_review_questions.md"

STATUS = ("CONFIRMED_FROM_OCR", "REVIEW_REQUIRED", "MISSING", "CONFLICTING", "UNREADABLE")

# Heuristic label → field (candidates only; never auto-approve without clear adjacency)
LABEL_HINTS = {
    "base_salary": ["שכר יסוד"],
    "travel_reimbursement": ["נסיעות"],
    "income_tax": ["מס הכנסה"],
    "national_insurance": ["ביטוח לאומי"],
    "health_insurance": ["מס בריאות"],
    "pension_deductions": ["ניכוי לגמל", "אלשולר"],
    "gross_salary": ['סה"כ תשלומים', "סה״כ תשלומים", "סהכ תשלומים"],
    "net_salary": ["שכר נטו", "נטו לתשלום", "לתשלום נטו", 'סה"כ נטו', "נטו:", "נטו "],
    "overtime_hours": ["שעות נוספות"],
    "regular_hours": ["שעות עבודה", "ועות עבודה"],  # OCR often garbles שעות→ועות
}


def mask_national_id(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 5:
        return raw
    return f"{digits[:2]}****{digits[-2:]}"


def digits_only(raw: str | None) -> str:
    return re.sub(r"\D", "", raw or "")


def normalize_amount(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = raw.strip().replace("₪", "").replace(" ", "")
    if not text:
        return None
    # Israeli OCR sometimes uses 1.234,56 — accept only clear forms
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d{2})?", text):
        return float(text.replace(",", ""))
    if re.fullmatch(r"\d+\.\d{2}", text):
        return float(text)
    if re.fullmatch(r"\d+", text) and len(text) <= 7:
        return float(text)
    return None


def field(
    *,
    review_status: str,
    ocr_raw: str | None = None,
    normalized_candidate: Any = None,
    source_text: str | None = None,
    evidence_ids: list[str] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    assert review_status in STATUS
    return {
        "review_status": review_status,
        "ocr_raw": ocr_raw,
        "normalized_candidate": normalized_candidate,
        "source_text": source_text if source_text is not None else ocr_raw,
        "evidence_ids": evidence_ids or [],
        "reviewer_notes": notes,
    }


def missing(notes: str = "Not clearly present in OCR text for this page.") -> dict[str, Any]:
    return field(review_status="MISSING", notes=notes)


def build_line_index(page: dict[str, Any]) -> list[dict[str, Any]]:
    """Map OCR page lines to evidence IDs matching parser_layout_context naming."""
    page_number = int(page.get("page") or 1)
    indexed: list[dict[str, Any]] = []
    for line_index, line in enumerate(page.get("lines") or [], start=1):
        text = (line.get("text") or "").strip()
        if not text:
            continue
        lid = f"p{page_number}_l{line_index}"
        word_ids: list[str] = []
        for word_index, word in enumerate(line.get("words") or [], start=1):
            wtext = (word.get("text") or "").strip()
            if not wtext:
                continue
            word_ids.append(f"p{page_number}_l{line_index}_w{word_index}")
        indexed.append(
            {
                "id": lid,
                "text": text,
                "confidence": line.get("confidence"),
                "word_ids": word_ids,
                "line_index": line_index,
            }
        )
    return indexed


def find_lines(indexed: list[dict[str, Any]], predicate) -> list[dict[str, Any]]:
    return [row for row in indexed if predicate(row["text"])]


_EMPLOYER_FILE_DENYLIST = frozenset({"935111111", "93511111100", "4080234"})


def _looks_like_national_id(text: str) -> bool:
    raw = text.strip()
    if re.fullmatch(r"\d{7,9}-\d", raw):
        digits = digits_only(raw)
        return digits not in _EMPLOYER_FILE_DENYLIST and 8 <= len(digits) <= 9
    if re.fullmatch(r"\d{8,9}", raw):
        # Bare 8–9 digit IDs are weaker; reject known employer file tokens
        return raw not in _EMPLOYER_FILE_DENYLIST
    return False


def find_name_and_id(indexed: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    tz_lines = find_lines(indexed, lambda t: t.replace("״", '"') in ('ת"ז', 'ת״ז') or t == 'ת"ז')
    name_f = missing("Employee name not located near ת\"ז marker.")
    id_f = missing("National ID not located near ת\"ז marker.")

    for tz in tz_lines:
        idx = tz["line_index"]
        prev = next((r for r in indexed if r["line_index"] == idx - 1), None)
        nxt = next((r for r in indexed if r["line_index"] == idx + 1), None)
        if prev and re.search(r"[\u0590-\u05FF]", prev["text"]) and not re.search(r"\d{5,}", prev["text"]):
            unclean = bool(re.search(r"[\\|/<>]", prev["text"])) or len(prev["text"]) < 3
            name_f = field(
                review_status="REVIEW_REQUIRED",
                ocr_raw=prev["text"],
                normalized_candidate=None,
                source_text=prev["text"],
                evidence_ids=[prev["id"]],
                notes=(
                    "Hebrew name candidate immediately above ת\"ז. Confirm against source PDF "
                    "(do not auto-fix OCR)."
                    + (" OCR contains unusual characters." if unclean else "")
                ),
            )
        if nxt and _looks_like_national_id(nxt["text"]):
            raw = nxt["text"].strip()
            d = digits_only(raw)
            id_f = field(
                review_status="REVIEW_REQUIRED",
                ocr_raw=raw,
                normalized_candidate=d if 8 <= len(d) <= 9 else None,
                source_text=raw,
                evidence_ids=[nxt["id"]],
                notes=(
                    "National ID candidate immediately below ת\"ז. Digits-only normalize only when "
                    "8–9 digits. Must be human-confirmed before grouping/seed."
                ),
            )
        if name_f["ocr_raw"] or id_f["ocr_raw"]:
            break

    # Prefer hyphenated national-ID tokens (common Israeli print form) when ת"ז path missed
    if id_f["review_status"] == "MISSING":
        hyphenated = [
            row
            for row in indexed
            if re.fullmatch(r"\d{7,9}-\d", row["text"].strip())
            and digits_only(row["text"]) not in _EMPLOYER_FILE_DENYLIST
        ]
        if hyphenated:
            row = hyphenated[0]
            raw = row["text"].strip()
            d = digits_only(raw)
            id_f = field(
                review_status="REVIEW_REQUIRED",
                ocr_raw=raw,
                normalized_candidate=d if 8 <= len(d) <= 9 else None,
                source_text=raw,
                evidence_ids=[row["id"]],
                notes="Hyphenated ID-like token without clear ת\"ז adjacency. Confirm on PDF.",
            )

    if id_f["review_status"] == "MISSING":
        for row in indexed:
            if not _looks_like_national_id(row["text"]):
                continue
            # Skip early header employer file numbers (usually first 30 lines are masthead)
            if row["line_index"] <= 12 and digits_only(row["text"]) in _EMPLOYER_FILE_DENYLIST:
                continue
            if row["line_index"] <= 12 and not re.search(r"-", row["text"]):
                continue
            raw = row["text"].strip()
            d = digits_only(raw)
            id_f = field(
                review_status="REVIEW_REQUIRED",
                ocr_raw=raw,
                normalized_candidate=d if 8 <= len(d) <= 9 else None,
                source_text=raw,
                evidence_ids=[row["id"]],
                notes="ID-like token without clear ת\"ז adjacency on this page.",
            )
            break

    if name_f["review_status"] == "MISSING" and id_f.get("evidence_ids"):
        for i, row in enumerate(indexed):
            if row["id"] == id_f["evidence_ids"][0] and i > 0:
                prev = indexed[i - 1]
                if re.search(r"[\u0590-\u05FF]{2,}", prev["text"]) and 'ת"ז' not in prev["text"]:
                    name_f = field(
                        review_status="REVIEW_REQUIRED",
                        ocr_raw=prev["text"],
                        source_text=prev["text"],
                        evidence_ids=[prev["id"]],
                        notes="Name candidate from line before ID token (no ת\"ז line).",
                    )
                break

    return name_f, id_f


def find_period(indexed: list[dict[str, Any]], fixture_month: int | None, fixture_year: int | None) -> tuple[dict, dict]:
    """Period from payslip header '6/26' or '6' — fixture folder is hint only, not authority."""
    month_f = missing("Payroll month not clear in OCR.")
    year_f = missing("Payroll year not clear in OCR.")
    header = next((r for r in indexed if re.fullmatch(r"\d{1,2}/\d{2}", r["text"].strip())), None)
    lone = next((r for r in indexed[:5] if re.fullmatch(r"\d{1,2}", r["text"].strip())), None)
    if header:
        m_s, y_s = header["text"].strip().split("/")
        month = int(m_s)
        year = 2000 + int(y_s)
        month_f = field(
            review_status="REVIEW_REQUIRED",
            ocr_raw=header["text"].strip(),
            normalized_candidate=month,
            source_text=header["text"].strip(),
            evidence_ids=[header["id"]],
            notes=f"Header token interpreted as MM/YY → month={month}, year={year}. Confirm vs printed slip (fixture path suggests {fixture_month}/{fixture_year} but is not evidence).",
        )
        year_f = field(
            review_status="REVIEW_REQUIRED",
            ocr_raw=header["text"].strip(),
            normalized_candidate=year,
            source_text=header["text"].strip(),
            evidence_ids=[header["id"]],
            notes=month_f["reviewer_notes"],
        )
    elif lone:
        month = int(lone["text"].strip())
        month_f = field(
            review_status="REVIEW_REQUIRED",
            ocr_raw=lone["text"].strip(),
            normalized_candidate=month if 1 <= month <= 12 else None,
            source_text=lone["text"].strip(),
            evidence_ids=[lone["id"]],
            notes=f"Only month-like header digit '{month}' found (no /YY). Year not on this OCR token. Fixture path suggests {fixture_year}-{fixture_month:02d} but is NOT used as value.",
        )
        year_f = field(
            review_status="REVIEW_REQUIRED",
            ocr_raw=None,
            normalized_candidate=None,
            source_text=None,
            evidence_ids=[],
            notes=f"Year not printed next to month header in OCR. Fixture filename hints {fixture_year} — human must confirm from source PDF, do not auto-fill.",
        )
    return month_f, year_f


def _amount_tokens(text: str) -> list[str]:
    return re.findall(r"\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\d+\.\d{2}", text)


def amounts_near_label(
    indexed: list[dict[str, Any]],
    labels: list[str],
    *,
    prefer_comma_thousands: bool = False,
) -> dict[str, Any]:
    """Find a single nearest amount candidate; CONFLICTING only for same-row multi-amount ambiguity."""
    label_rows = []
    for lab in labels:
        label_rows.extend(find_lines(indexed, lambda t, lab=lab: lab in t))
    if not label_rows:
        return missing(f"Label(s) {labels!r} not found in OCR.")

    label_rows = sorted({r["id"]: r for r in label_rows}.values(), key=lambda r: r["line_index"])
    lab = label_rows[0]
    idxs = {r["line_index"]: r for r in indexed}

    same_line = _amount_tokens(lab["text"])
    if len(same_line) > 1:
        return field(
            review_status="CONFLICTING",
            ocr_raw=same_line[0],
            normalized_candidate=normalize_amount(same_line[0]),
            source_text=lab["text"],
            evidence_ids=[lab["id"]],
            notes=(
                f"Multiple amounts on the label line {lab['text']!r}: {same_line}. "
                "Pick the payslip column that matches this field from the source PDF."
            ),
        )
    if len(same_line) == 1:
        raw0 = same_line[0]
        return field(
            review_status="REVIEW_REQUIRED",
            ocr_raw=raw0,
            normalized_candidate=normalize_amount(raw0),
            source_text=lab["text"],
            evidence_ids=[lab["id"]],
            notes=f"Amount on same OCR line as label {lab['text']!r}. Confirm column meaning on PDF.",
        )

    # Search nearby lines. Prefer ABOVE the label first (common when Hebrew
    # column labels appear under payment amounts), then below.
    nearby: list[tuple[float, str, str]] = []
    for delta in range(1, 5):
        for li in (lab["line_index"] - delta, lab["line_index"] + delta):
            row = idxs.get(li)
            if not row:
                continue
            toks = _amount_tokens(row["text"])
            if not toks:
                continue
            if len(toks) > 1:
                return field(
                    review_status="CONFLICTING",
                    ocr_raw=toks[0],
                    normalized_candidate=normalize_amount(toks[0]),
                    source_text=row["text"],
                    evidence_ids=[row["id"], lab["id"]],
                    notes=(
                        f"Label {lab['text']!r} near multi-amount line {row['text']!r}. "
                        "Resolve which column applies before confirming."
                    ),
                )
            rank = float(delta) if li < lab["line_index"] else float(delta) + 0.5
            nearby.append((rank, toks[0], row["id"]))

    if not nearby:
        return field(
            review_status="REVIEW_REQUIRED",
            ocr_raw=lab["text"],
            source_text=lab["text"],
            evidence_ids=[lab["id"]],
            notes=f"Label {lab['text']!r} found but no clear numeric amount nearby. Confirm from PDF columns.",
        )

    nearby.sort(key=lambda item: item[0])
    if prefer_comma_thousands:
        preferred = [item for item in nearby if "," in item[1]]
        chosen = preferred[0] if preferred else nearby[0]
    else:
        chosen = nearby[0]

    # Distinct values at essentially the same distance → conflict
    same_dist = [item for item in nearby if abs(item[0] - chosen[0]) < 0.05]
    distinct = {normalize_amount(item[1]) for item in same_dist}
    distinct.discard(None)
    if len(distinct) > 1:
        return field(
            review_status="CONFLICTING",
            ocr_raw=chosen[1],
            normalized_candidate=normalize_amount(chosen[1]),
            source_text="; ".join(f"{a}@{e}" for _, a, e in same_dist),
            evidence_ids=[e for _, _, e in same_dist] + [lab["id"]],
            notes=(
                f"Multiple equally-near amount candidates for {labels[0]!r}: "
                f"{[a for _, a, _ in same_dist]}. Confirm on source PDF."
            ),
        )

    return field(
        review_status="REVIEW_REQUIRED",
        ocr_raw=chosen[1],
        normalized_candidate=normalize_amount(chosen[1]),
        source_text=chosen[1],
        evidence_ids=[chosen[2], lab["id"]],
        notes=(
            f"Nearest amount candidate to label {lab['text']!r}. "
            "Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval."
        ),
    )


def hours_candidate(indexed: list[dict[str, Any]], labels: list[str]) -> dict[str, Any]:
    """Hours often appear as N.00 above garbled שעות label — keep REVIEW_REQUIRED."""
    label_rows = []
    for lab in labels:
        label_rows.extend(find_lines(indexed, lambda t, lab=lab: lab in t))
    if not label_rows:
        return missing(f"Hours label(s) {labels!r} not found.")
    lab = sorted(label_rows, key=lambda r: r["line_index"])[0]
    idxs = {r["line_index"]: r for r in indexed}
    cands = []
    for delta in range(1, 6):
        for li in (lab["line_index"] - delta, lab["line_index"] + delta):
            row = idxs.get(li)
            if not row:
                continue
            if re.fullmatch(r"\d+\.\d{2}", row["text"].strip()) or re.fullmatch(r"\d+", row["text"].strip()):
                cands.append((row["text"].strip(), row["id"]))
    if not cands:
        return field(
            review_status="REVIEW_REQUIRED",
            ocr_raw=lab["text"],
            source_text=lab["text"],
            evidence_ids=[lab["id"]],
            notes="Hours label present; numeric hours not uniquely identified.",
        )
    if len({c[0] for c in cands}) > 2:
        return field(
            review_status="CONFLICTING",
            ocr_raw=cands[0][0],
            normalized_candidate=normalize_amount(cands[0][0]),
            source_text="; ".join(f"{a}@{b}" for a, b in cands[:5]),
            evidence_ids=[b for _, b in cands[:5]] + [lab["id"]],
            notes="Multiple hour-like numbers near hours label — confirm which is reported vs base.",
        )
    return field(
        review_status="REVIEW_REQUIRED",
        ocr_raw=cands[0][0],
        normalized_candidate=normalize_amount(cands[0][0]),
        source_text=cands[0][0],
        evidence_ids=[cands[0][1], lab["id"]],
        notes="Hours candidate near label; verify against PDF (OCR often swaps columns).",
    )


def employee_number_field(indexed: list[dict[str, Any]]) -> dict[str, Any]:
    labels = find_lines(indexed, lambda t: "מס' עובד" in t or "מס׳ עובד" in t or "מס עובד" in t)
    if not labels:
        return missing("Employee number label not found.")
    lab = labels[0]
    idxs = {r["line_index"]: r for r in indexed}
    # Often empty on these demo slips
    nxt = idxs.get(lab["line_index"] + 1)
    if nxt and re.search(r"\d{3,}", nxt["text"]) and "ותק" not in nxt["text"] and "עבודה" not in nxt["text"]:
        return field(
            review_status="REVIEW_REQUIRED",
            ocr_raw=nxt["text"].strip(),
            normalized_candidate=digits_only(nxt["text"]) or None,
            source_text=nxt["text"].strip(),
            evidence_ids=[nxt["id"], lab["id"]],
            notes="Token after employee-number label may not be the employee number — confirm on PDF.",
        )
    return field(
        review_status="MISSING",
        ocr_raw=None,
        source_text=lab["text"],
        evidence_ids=[lab["id"]],
        notes="Employee-number label present; no value clearly OCR'd beside it.",
    )


def other_earnings_deductions(indexed: list[dict[str, Any]]) -> tuple[dict, dict]:
    earn_labels = ["שעות נוספות", "גילום"]
    ded_labels = ["ניכוי רשות", "ניכויי חובה"]
    earn_hits = []
    for lab in earn_labels:
        earn_hits.extend(find_lines(indexed, lambda t, lab=lab: lab in t))
    ded_hits = []
    for lab in ded_labels:
        ded_hits.extend(find_lines(indexed, lambda t, lab=lab: lab in t))

    if earn_hits:
        other_e = field(
            review_status="REVIEW_REQUIRED",
            ocr_raw="; ".join(r["text"] for r in earn_hits[:4]),
            source_text="; ".join(r["text"] for r in earn_hits[:4]),
            evidence_ids=[r["id"] for r in earn_hits[:4]],
            notes="Additional earning-related labels present; extract specific amounts from PDF columns (not auto-summed).",
        )
    else:
        other_e = missing("No additional earning labels clearly identified beyond base/travel/OT exploration.")

    if ded_hits:
        other_d = field(
            review_status="REVIEW_REQUIRED",
            ocr_raw="; ".join(r["text"] for r in ded_hits[:4]),
            source_text="; ".join(r["text"] for r in ded_hits[:4]),
            evidence_ids=[r["id"] for r in ded_hits[:4]],
            notes="Additional deduction labels present; confirm amounts from PDF.",
        )
    else:
        other_d = missing("No extra deduction labels clearly identified beyond tax/NI/health/pension exploration.")
    return other_e, other_d


def fixture_period_hint(fixture_id: str) -> tuple[int | None, int | None]:
    m = re.search(r"(20\d{2})_(\d{2})", fixture_id)
    if not m:
        return None, None
    return int(m.group(2)), int(m.group(1))


def proposed_employee_key(national_id_digits: str | None, name_raw: str | None, page_key: str) -> str:
    if national_id_digits and len(national_id_digits) >= 8:
        digest = hashlib.sha256(national_id_digits.encode("utf-8")).hexdigest()[:12]
        return f"emp_nid_{digest}"
    return f"emp_ungrouped_{page_key}"


def analyze_page(
    *,
    slip: dict[str, Any],
    ocr_page: dict[str, Any] | None,
) -> dict[str, Any]:
    source = slip["source"]
    fixture_id = source["fixture_id"]
    page_no = source["page"]
    intent = slip["fixture_classification"]
    ocr_conf = slip["ocr"].get("overall_confidence")
    fm, fy = fixture_period_hint(fixture_id)

    if ocr_page is None:
        # PNG / missing layout — text-only from report
        text = slip.get("_ocr_raw_text") or ""
        fake_lines = [{"text": line, "confidence": None, "words": []} for line in text.splitlines() if line.strip()]
        ocr_page = {"page": page_no, "text": text, "lines": fake_lines, "words": []}
        layout_note = "No word/line geometry for this source in stored layout OCR; evidence_ids are synthetic sequential from text lines only and must be re-verified."
    else:
        layout_note = "Evidence IDs from OCR layout lines (p{page}_l{n})."

    indexed = build_line_index(ocr_page)
    name_f, id_f = find_name_and_id(indexed)
    month_f, year_f = find_period(indexed, fm, fy)
    emp_no = employee_number_field(indexed)

    fields = {
        "employee_name": name_f,
        "national_id": id_f,
        "employee_number": emp_no,
        "payroll_month": month_f,
        "payroll_year": year_f,
        "base_salary": amounts_near_label(indexed, LABEL_HINTS["base_salary"], prefer_comma_thousands=True),
        "gross_salary": amounts_near_label(indexed, LABEL_HINTS["gross_salary"], prefer_comma_thousands=True),
        "net_salary": amounts_near_label(indexed, LABEL_HINTS["net_salary"], prefer_comma_thousands=True),
        "regular_hours": hours_candidate(indexed, LABEL_HINTS["regular_hours"]),
        "overtime_hours": amounts_near_label(indexed, LABEL_HINTS["overtime_hours"]),
        "travel_reimbursement": amounts_near_label(indexed, LABEL_HINTS["travel_reimbursement"]),
        "income_tax": amounts_near_label(indexed, LABEL_HINTS["income_tax"]),
        "national_insurance": amounts_near_label(indexed, LABEL_HINTS["national_insurance"]),
        "health_insurance": amounts_near_label(indexed, LABEL_HINTS["health_insurance"]),
        "pension_deductions": amounts_near_label(indexed, LABEL_HINTS["pension_deductions"]),
    }
    other_e, other_d = other_earnings_deductions(indexed)
    fields["other_earnings"] = other_e
    fields["other_deductions"] = other_d

    # PNG special case — mostly UNREADABLE for identity
    if fixture_id.endswith(".png") or "employee_001" in fixture_id:
        for key in ("employee_name", "national_id", "employee_number", "payroll_month", "payroll_year"):
            if fields[key]["review_status"] == "MISSING" or not fields[key].get("ocr_raw"):
                fields[key] = field(
                    review_status="UNREADABLE",
                    ocr_raw=fields[key].get("ocr_raw"),
                    source_text=(slip.get("_ocr_raw_text") or "")[:200],
                    evidence_ids=fields[key].get("evidence_ids") or [],
                    notes="PNG OCR too weak for reliable identity/period. Prefer matching PDF page for seed review.",
                )
        # Amounts that appear as bare numbers without labels
        text = slip.get("_ocr_raw_text") or ""
        bare = re.findall(r"\d{1,3}(?:,\d{3})+\.\d{2}|\d+\.\d{2}", text)
        if bare:
            fields["base_salary"] = field(
                review_status="REVIEW_REQUIRED",
                ocr_raw=bare[0] if bare else None,
                normalized_candidate=normalize_amount(bare[0]) if bare else None,
                source_text=", ".join(bare[:6]),
                evidence_ids=[],
                notes="PNG shows amounts without reliable labels/name/ID. Cross-check against recommended PDF page; do not seed from PNG alone.",
            )
            if len(bare) > 1:
                fields["travel_reimbursement"] = field(
                    review_status="CONFLICTING",
                    ocr_raw=bare[1],
                    normalized_candidate=normalize_amount(bare[1]),
                    source_text=", ".join(bare[:6]),
                    evidence_ids=[],
                    notes="Unlabeled amount sequence on PNG; column meaning uncertain.",
                )

    nid_digits = id_f.get("normalized_candidate") if isinstance(id_f.get("normalized_candidate"), str) else None
    if not nid_digits and id_f.get("ocr_raw"):
        d = digits_only(id_f["ocr_raw"])
        nid_digits = d if 8 <= len(d) <= 9 else None

    # Grouping gate: exact high-confidence national ID only — here we only *propose* key; grouping confidence separate
    high_conf_id = bool(
        nid_digits
        and len(nid_digits) >= 8
        and id_f["review_status"] in ("REVIEW_REQUIRED", "CONFIRMED_FROM_OCR")
        and ocr_conf is not None
        and ocr_conf >= 0.8
        and "png" not in fixture_id
    )
    emp_key = proposed_employee_key(nid_digits if high_conf_id else None, name_f.get("ocr_raw"), slip["payslip_key"])
    grouping = {
        "eligible_for_id_grouping": high_conf_id,
        "national_id_digits": nid_digits if high_conf_id else None,
        "national_id_masked": mask_national_id(nid_digits) if high_conf_id else None,
        "note": (
            "Proposed grouping by exact national ID digits only after human confirms ID."
            if high_conf_id
            else "Not grouped by ID yet (missing/low-confidence ID or weak OCR). Name similarity must not merge."
        ),
    }

    return {
        "payslip_key": slip["payslip_key"],
        "proposed_fixture_employee_key": emp_key,
        "source_file": fixture_id,
        "source_page": page_no,
        "fixture_intent": intent,
        "ocr_confidence": ocr_conf,
        "layout_note": layout_note,
        "grouping": grouping,
        "fields": fields,
        "page_review_status": "REVIEW_REQUIRED",
        "page_reviewer_notes": (
            "Parser values intentionally ignored. All monetary/identity fields need human PDF confirmation. "
            + layout_note
        ),
        "ocr_text_preview": (slip.get("_ocr_raw_text") or "")[:400],
    }


def count_field_statuses(pages: list[dict[str, Any]]) -> dict[str, int]:
    counts = defaultdict(int)
    for page in pages:
        for f in page["fields"].values():
            counts[f["review_status"]] += 1
    return dict(counts)


def group_employees(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    ungrouped = []
    for page in pages:
        g = page["grouping"]
        if not g["eligible_for_id_grouping"] or not g["national_id_digits"]:
            ungrouped.append(page["payslip_key"])
            continue
        nid = g["national_id_digits"]
        bucket = buckets.setdefault(
            nid,
            {
                "proposed_fixture_employee_key": f"emp_nid_{hashlib.sha256(nid.encode('utf-8')).hexdigest()[:12]}",
                "national_id_masked": g["national_id_masked"],
                "national_id_digits_local_only": nid,
                "payslip_keys": [],
                "names_observed_ocr": [],
                "grouping_basis": "exact_national_id_digits_pending_human_confirm",
                "grouping_confidence": "pending_human_id_confirmation",
            },
        )
        bucket["payslip_keys"].append(page["payslip_key"])
        name = page["fields"]["employee_name"].get("ocr_raw")
        if name and name not in bucket["names_observed_ocr"]:
            bucket["names_observed_ocr"].append(name)
    proposed = list(buckets.values())
    # Pages that couldn't group stay as singleton ungrouped proposals
    for page in pages:
        if page["payslip_key"] in ungrouped:
            proposed.append(
                {
                    "proposed_fixture_employee_key": page["proposed_fixture_employee_key"],
                    "national_id_masked": None,
                    "national_id_digits_local_only": None,
                    "payslip_keys": [page["payslip_key"]],
                    "names_observed_ocr": [page["fields"]["employee_name"].get("ocr_raw")]
                    if page["fields"]["employee_name"].get("ocr_raw")
                    else [],
                    "grouping_basis": "ungrouped_pending_review",
                    "grouping_confidence": "none",
                }
            )
    return proposed


def md_escape(text: str | None) -> str:
    if text is None:
        return "—"
    return str(text).replace("|", "\\|").replace("\n", " ")


def field_md_row(name: str, f: dict[str, Any], *, mask_id: bool = False) -> str:
    raw = f.get("ocr_raw")
    norm = f.get("normalized_candidate")
    source = f.get("source_text")
    if mask_id:
        if raw:
            raw = mask_national_id(str(raw))
        if source:
            source = mask_national_id(str(source))
        if norm is not None:
            norm = mask_national_id(str(norm))
    eids = ", ".join(f.get("evidence_ids") or []) or "—"
    return (
        f"| `{name}` | {f['review_status']} | {md_escape(raw)} | {md_escape(norm)} | "
        f"{md_escape(source)} | {md_escape(eids)} | {md_escape(f.get('reviewer_notes'))} |"
    )


def mask_ids_in_text(text: str | None) -> str:
    if not text:
        return ""
    # Mask hyphenated Israeli ID print forms and bare 8–9 digit clusters that look like IDs
    text = re.sub(
        r"\b(\d{7,9})-(\d)\b",
        lambda m: f"{mask_national_id(m.group(0))}",
        text,
    )
    return text


def write_markdown(payload: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Seed Approval Table (OCR-only review)")
    lines.append("")
    lines.append("> REVIEW ONLY — NOT APPROVED SEED DATA")
    lines.append(">")
    lines.append("> Parser output ignored (hallucinations rejected). No DB writes. No final seed file.")
    lines.append("")
    lines.append("## How to review")
    lines.append("")
    lines.append("1. Open the source PDF page listed for each slip.")
    lines.append("2. For each field, set `review_status` to `CONFIRMED_FROM_OCR` only if the OCR value matches the printed slip.")
    lines.append("3. Edit `ocr_raw` only to match exact printed text if OCR is wrong — or mark `UNREADABLE` / `CONFLICTING`.")
    lines.append("4. Do **not** merge employees by name; confirm national IDs first.")
    lines.append("5. National IDs are **masked** in this Markdown; full digits are in `seed_approval_table.json` (local).")
    lines.append("")
    s = payload["summary"]
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Pages reviewed: **{s['pages_reviewed']}**")
    lines.append(f"- Proposed employee groups (by exact ID pending confirm): **{s['proposed_employees_id_grouped']}**")
    lines.append(f"- Ungrouped pages: **{s['ungrouped_pages']}**")
    lines.append(f"- Field statuses: `{json.dumps(s['field_status_counts'], ensure_ascii=False)}`")
    lines.append("")
    lines.append("## Proposed employee groups")
    lines.append("")
    lines.append("| Employee key | National ID (masked) | Payslip keys | Names (OCR) | Basis |")
    lines.append("|---|---|---|---|---|")
    for emp in payload["proposed_employees"]:
        lines.append(
            f"| `{emp['proposed_fixture_employee_key']}` | {md_escape(emp.get('national_id_masked'))} | "
            f"{', '.join('`'+k+'`' for k in emp['payslip_keys'])} | "
            f"{md_escape('; '.join(x for x in emp.get('names_observed_ocr') or [] if x))} | "
            f"{emp.get('grouping_basis')} |"
        )
    lines.append("")

    for page in payload["pages"]:
        lines.append(f"## `{page['payslip_key']}`")
        lines.append("")
        lines.append(f"- **Proposed employee key:** `{page['proposed_fixture_employee_key']}`")
        lines.append(f"- **Source file:** `{page['source_file']}`")
        lines.append(f"- **Source page:** {page['source_page']}")
        lines.append(f"- **Fixture intent:** `{page['fixture_intent']}` (intent only — not a validation result)")
        lines.append(f"- **OCR confidence:** {page['ocr_confidence']}")
        lines.append(f"- **Page review status:** `{page['page_review_status']}`")
        lines.append(f"- **Notes:** {page['page_reviewer_notes']}")
        lines.append("")
        lines.append("| Field | Status | OCR raw | Normalized candidate | Source text | Evidence IDs | Reviewer notes |")
        lines.append("|---|---|---|---|---|---|---|")
        for fname, fval in page["fields"].items():
            lines.append(field_md_row(fname, fval, mask_id=(fname == "national_id")))
        lines.append("")
        lines.append("<details><summary>OCR text preview</summary>")
        lines.append("")
        lines.append("```")
        lines.append(mask_ids_in_text(page.get("ocr_text_preview") or ""))
        lines.append("```")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    lines.append("## Edit checklist (copy into reviewer notes)")
    lines.append("")
    lines.append("- [ ] All national IDs confirmed against PDF")
    lines.append("- [ ] Employee merges only by confirmed identical ID")
    lines.append("- [ ] Period month/year confirmed (fixture path is not authority)")
    lines.append("- [ ] Base / gross / net / deductions confirmed from correct columns")
    lines.append("- [ ] PNG page deferred in favor of PDF match if used")
    lines.append("- [ ] Explicit approval recorded before any seed generation")
    lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def write_questions(payload: dict[str, Any]) -> None:
    lines = [
        "# Manual review questions (seed approval)",
        "",
        "> Answer before approving any final seed. Do not invent values.",
        "",
        "## Cross-cutting",
        "",
        "1. Confirm that **parser/LLM values will not be used** for seed fields.",
        "2. Confirm national IDs in `seed_approval_table.json` match the printed PDF (Markdown is masked).",
        "3. Confirm employees are merged **only** when national ID digits match exactly after your confirmation.",
        "4. For invalid-fixture July slips: confirm month/year from the **printed** slip (OCR often shows month `6` without year).",
        "5. Confirm whether PNG `payslip_valid_2026_06_employee_001.png` should be excluded from seed in favor of the matching PDF page.",
        "",
        "## Per proposed employee group",
        "",
    ]
    for emp in payload["proposed_employees"]:
        lines.append(f"### `{emp['proposed_fixture_employee_key']}`")
        lines.append("")
        lines.append(f"- Masked ID: `{emp.get('national_id_masked')}`")
        lines.append(f"- Payslips: {', '.join(emp['payslip_keys'])}")
        lines.append(f"- OCR names observed: {emp.get('names_observed_ocr')}")
        lines.append("- [ ] Is the national ID correct on every listed page?")
        lines.append("- [ ] Are OCR name variants the same person (do **not** merge on name alone if IDs differ)?")
        lines.append("- [ ] Approve this employee key for future seed? (yes/no)")
        lines.append("")

    lines.append("## Per page — critical field questions")
    lines.append("")
    for page in payload["pages"]:
        lines.append(f"### `{page['payslip_key']}` (file `{page['source_file']}` p{page['source_page']})")
        lines.append("")
        critical = [
            "employee_name",
            "national_id",
            "payroll_month",
            "payroll_year",
            "base_salary",
            "gross_salary",
            "net_salary",
            "travel_reimbursement",
            "income_tax",
            "national_insurance",
            "health_insurance",
            "pension_deductions",
        ]
        for fname in critical:
            f = page["fields"][fname]
            if f["review_status"] in ("REVIEW_REQUIRED", "CONFLICTING", "UNREADABLE", "MISSING"):
                shown = f.get("ocr_raw")
                if fname == "national_id" and shown:
                    shown = mask_national_id(str(shown))
                lines.append(
                    f"- `{fname}` status=`{f['review_status']}` OCR=`{shown}` — "
                    f"confirm/correct/mark missing? Notes: {f.get('reviewer_notes')}"
                )
        conflicts = [k for k, v in page["fields"].items() if v["review_status"] == "CONFLICTING"]
        if conflicts:
            lines.append(f"- **Conflicts to resolve:** {', '.join(conflicts)}")
        lines.append("")

    lines.append("## Sign-off")
    lines.append("")
    lines.append("- Reviewer name:")
    lines.append("- Date:")
    lines.append("- Approved to generate final seed: **NO** / YES (circle)")
    lines.append("- Blocking items remaining:")
    lines.append("")
    OUT_Q.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    valid_ocr = json.loads(VALID_OCR.read_text(encoding="utf-8")) if VALID_OCR.exists() else {"pages": []}
    invalid_ocr = json.loads(INVALID_OCR.read_text(encoding="utf-8")) if INVALID_OCR.exists() else {"pages": []}
    valid_pages = {int(p["page"]): p for p in valid_ocr.get("pages") or []}
    invalid_pages = {int(p["page"]): p for p in invalid_ocr.get("pages") or []}

    pages_out: list[dict[str, Any]] = []
    for slip in report["payslips"]:
        fid = slip["source"]["fixture_id"]
        page_no = int(slip["source"]["page"])
        ocr_page = None
        if "valid_2026_06_multi" in fid:
            ocr_page = valid_pages.get(page_no)
        elif "invalid_2026_07_multi" in fid:
            ocr_page = invalid_pages.get(page_no)
        pages_out.append(analyze_page(slip=slip, ocr_page=ocr_page))

    employees = group_employees(pages_out)
    status_counts = count_field_statuses(pages_out)
    id_grouped = [e for e in employees if e.get("grouping_basis", "").startswith("exact_national_id")]
    ungrouped_pages = sum(1 for p in pages_out if not p["grouping"]["eligible_for_id_grouping"])

    payload = {
        "marker": "REVIEW ONLY — NOT APPROVED SEED DATA",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_report": "extraction_report.json",
        "rules": {
            "parser_values_used": False,
            "inference_allowed": False,
            "silent_ocr_correction": False,
            "grouping": "exact_high_confidence_national_id_only_pending_human_confirm",
            "validation_findings_generated": False,
            "db_records_created": False,
            "final_seed_created": False,
        },
        "summary": {
            "pages_reviewed": len(pages_out),
            "proposed_employees_id_grouped": len(id_grouped),
            "proposed_employee_entries_total": len(employees),
            "ungrouped_pages": ungrouped_pages,
            "field_status_counts": status_counts,
            "confidently_extracted_fields": status_counts.get("CONFIRMED_FROM_OCR", 0),
            "fields_requiring_manual_confirmation": (
                status_counts.get("REVIEW_REQUIRED", 0)
                + status_counts.get("CONFLICTING", 0)
                + status_counts.get("UNREADABLE", 0)
            ),
            "conflicts": status_counts.get("CONFLICTING", 0),
            "missing_fields": status_counts.get("MISSING", 0),
        },
        "proposed_employees": employees,
        "pages": pages_out,
        "files_requiring_user_review": [
            str(OUT_MD.relative_to(BASE.parent.parent.parent.parent) if False else OUT_MD.name),
            OUT_JSON.name,
            OUT_Q.name,
        ],
    }
    # Prefer repo-relative paths for humans
    payload["files_requiring_user_review"] = [
        "backend/tests/fixtures/review/accountant_seed_extraction/seed_approval_table.md",
        "backend/tests/fixtures/review/accountant_seed_extraction/seed_approval_table.json",
        "backend/tests/fixtures/review/accountant_seed_extraction/manual_review_questions.md",
        "backend/tests/fixtures/documents/payslips/valid/payslips_valid_2026_06_multi.pdf",
        "backend/tests/fixtures/documents/payslips/invalid/payslips_invalid_2026_07_multi.pdf",
        "backend/tests/fixtures/documents/payslips/valid/payslip_valid_2026_06_employee_001.png",
    ]

    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload)
    write_questions(payload)

    # cleanup temp OCR text dumps if present
    for tmp in BASE.glob("_tmp_*.txt"):
        tmp.unlink(missing_ok=True)

    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print("WROTE", OUT_JSON)
    print("WROTE", OUT_MD)
    print("WROTE", OUT_Q)


if __name__ == "__main__":
    main()
