"""REVIEW-ONLY fixture extraction — NOT production, NOT approved seed generation.

Invokes the running local API OCR + payslip parser endpoints (existing use cases)
against payslip fixtures and writes review artifacts under
tests/fixtures/review/accountant_seed_extraction/.

Why HTTP API: the Docker API image has OCR/parser dependencies; host Python may not.
Endpoints used do not persist to the database:
  POST /api/v1/ocr/extract
  POST /api/v1/parser/payslip

Safety:
- Does not write to the application database
- Does not mutate fixture source files
- Does not create approved seed JSON
- Safe to re-run (overwrites review artifacts only)

Usage (API must be reachable; default http://127.0.0.1:8000):

  py scripts/dev/extract_fixture_review.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = BACKEND_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import fitz  # noqa: E402

from payroll_copilot.application.ports.payslip_parser import (  # noqa: E402
    PAYSLIP_FIELD_KEYS,
    FieldExtractionStatus,
)
from payroll_copilot.application.services.fixture_document_loader import (  # noqa: E402
    read_fixture_bytes,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("extract_fixture_review")

REVIEW_DIR = BACKEND_ROOT / "tests" / "fixtures" / "review" / "accountant_seed_extraction"
MARKER = "REVIEW ARTIFACTS ONLY — NOT APPROVED SEED DATA"
API_BASE = os.environ.get("PAYROLL_REVIEW_API_BASE", "http://127.0.0.1:8000").rstrip("/")

FIXTURES = [
    ("valid", "valid/payslips_valid_2026_06_multi.pdf"),
    ("invalid", "invalid/payslips_invalid_2026_07_multi.pdf"),
    ("valid", "valid/payslip_valid_2026_06_employee_001.png"),
]

IDENTITY_FIELDS = ("employee_id", "employee_number", "employee_name")


def git_commit() -> str | None:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=BACKEND_ROOT.parent,
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            or None
        )
    except Exception:  # noqa: BLE001
        return None


def mask_national_id(value: object) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    if len(digits) < 4:
        text = str(value).strip()
        if not text:
            return None
        if len(text) <= 2:
            return "*" * len(text)
        return text[:1] + ("*" * (len(text) - 2)) + text[-1:]
    return ("*" * max(0, len(digits) - 4)) + digits[-4:]


def classify_review_status(status: str, confidence: float | None, value: object) -> str:
    normalized = (status or "").upper()
    if normalized == FieldExtractionStatus.MISSING.value or value in (None, ""):
        return "MISSING"
    if normalized == FieldExtractionStatus.UNCERTAIN.value:
        return "REQUIRES_HUMAN_REVIEW" if confidence is None or confidence < 0.75 else "UNCERTAIN"
    if normalized == FieldExtractionStatus.FOUND.value:
        if confidence is not None and confidence < 0.55:
            return "REQUIRES_HUMAN_REVIEW"
        if confidence is not None and confidence < 0.75:
            return "UNCERTAIN"
        return "CONFIRMED"
    return "REQUIRES_HUMAN_REVIEW"


def field_payload(name: str, raw: dict[str, Any], *, source_page: int) -> dict[str, Any]:
    value = raw.get("value")
    status = str(raw.get("status") or "MISSING")
    confidence = raw.get("confidence")
    review_status = classify_review_status(status, confidence, value)
    notes = [str(w) for w in (raw.get("warnings") or [])]
    if review_status == "REQUIRES_HUMAN_REVIEW":
        notes.append("Parser/status or confidence requires human confirmation.")
    payload = {
        "field": name,
        "raw_value": value,
        "normalized_candidate": raw.get("normalized_value")
        if raw.get("normalized_value") is not None
        else value,
        "confidence": confidence,
        "source_text": raw.get("source_text"),
        "evidence_ids": list(raw.get("evidence_ids") or []),
        "source_page": raw.get("source_page") if raw.get("source_page") is not None else source_page,
        "source_bbox": raw.get("source_bbox"),
        "parser_status": status,
        "review_status": review_status,
        "review_notes": notes,
        "parser_method": raw.get("parser_method"),
    }
    if name == "employee_id" and value not in (None, ""):
        payload["raw_value_masked"] = mask_national_id(value)
    return payload


def tokenize(text: str) -> set[str]:
    return {tok for tok in re.findall(r"[\w\u0590-\u05FF]+", text.lower()) if len(tok) > 1}


def jaccard(a: str, b: str) -> float:
    ta, tb = tokenize(a), tokenize(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def page_count_pdf(content: bytes) -> int:
    doc = fitz.open(stream=content, filetype="pdf")
    try:
        return doc.page_count
    finally:
        doc.close()


def extract_pdf_page(content: bytes, page_index: int) -> bytes:
    src = fitz.open(stream=content, filetype="pdf")
    try:
        out = fitz.open()
        out.insert_pdf(src, from_page=page_index, to_page=page_index)
        data = out.tobytes()
        out.close()
        return data
    finally:
        src.close()


def multipart_ocr(content: bytes, filename: str, content_type: str, language: str) -> dict[str, Any]:
    boundary = f"----PayrollReview{int(time.time() * 1000)}"
    body = bytearray()

    def add_field(name: str, value: str) -> None:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")

    add_field("language", language)
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    )
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
    body.extend(content)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    request = urllib.request.Request(
        f"{API_BASE}/api/v1/ocr/extract",
        data=bytes(body),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode("utf-8"))


def post_parser(ocr_payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(ocr_payload).encode("utf-8")
    request = urllib.request.Request(
        f"{API_BASE}/api/v1/parser/payslip",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=360) as response:
        return json.loads(response.read().decode("utf-8"))


def run_ocr_parse(
    *,
    content: bytes,
    filename: str,
    content_type: str,
    language: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    ocr_dict: dict[str, Any] | None = None
    parse_dict: dict[str, Any] | None = None
    try:
        ocr_dict = multipart_ocr(content, filename, content_type, language)
        warnings.extend(list(ocr_dict.get("warnings") or []))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        warnings.append(f"OCR failed HTTP {exc.code}: {detail[:500]}")
        logger.error("OCR failed for %s: %s", filename, detail[:500])
        return None, None, warnings
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"OCR failed: {exc}")
        logger.exception("OCR failed for %s", filename)
        return None, None, warnings

    try:
        parse_dict = post_parser(ocr_dict)
        warnings.extend(list(parse_dict.get("warnings") or []))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        warnings.append(f"Parser failed HTTP {exc.code}: {detail[:500]}")
        logger.error("Parser failed for %s: %s", filename, detail[:500])
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Parser failed: {exc}")
        logger.exception("Parser failed for %s", filename)
    return ocr_dict, parse_dict, warnings


def summarize_fields(fields: dict[str, Any], *, source_page: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in PAYSLIP_FIELD_KEYS:
        raw = fields.get(key) or {"status": "MISSING", "value": None}
        if not isinstance(raw, dict):
            raw = {"status": "MISSING", "value": None}
        rows.append(field_payload(key, raw, source_page=source_page))
    additional = fields.get("additional_fields") or {}
    if isinstance(additional, dict):
        for key, raw in sorted(additional.items()):
            if not isinstance(raw, dict):
                raw = {"status": "MISSING", "value": None}
            rows.append(field_payload(f"additional.{key}", raw, source_page=source_page))
    return rows


def proposed_employee_groups(payslips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    ungrouped: list[dict[str, Any]] = []

    for slip in payslips:
        fields = {f["field"]: f for f in slip["fields"]}
        emp_id = fields.get("employee_id")
        raw = (emp_id or {}).get("raw_value")
        conf = (emp_id or {}).get("confidence")
        digits = re.sub(r"\D", "", str(raw)) if raw not in (None, "") else ""
        can_group = (
            emp_id is not None
            and emp_id.get("parser_status") == "FOUND"
            and emp_id.get("review_status") == "CONFIRMED"
            and len(digits) >= 8
            and (conf is not None and conf >= 0.75)
        )
        if not can_group:
            ungrouped.append(slip)
            continue
        bucket = groups.setdefault(
            digits,
            {
                "national_id_hash": hashlib.sha256(digits.encode("utf-8")).hexdigest()[:16],
                "national_id_masked": mask_national_id(digits),
                "names_observed": [],
                "employee_numbers_observed": [],
                "source_refs": [],
                "payslip_keys": [],
                "conflicts": [],
                "missing_profile_fields": [],
                "grouping_confidence": "high",
                "grouping_basis": "exact_national_id_confirmed",
            },
        )
        name = (fields.get("employee_name") or {}).get("raw_value")
        number = (fields.get("employee_number") or {}).get("raw_value")
        if name and str(name) not in bucket["names_observed"]:
            bucket["names_observed"].append(str(name))
        if number and str(number) not in bucket["employee_numbers_observed"]:
            bucket["employee_numbers_observed"].append(str(number))
        bucket["source_refs"].append(
            {"fixture_id": slip["source"]["fixture_id"], "page": slip["source"]["page"]}
        )
        bucket["payslip_keys"].append(slip["payslip_key"])

    for bucket in groups.values():
        if len(bucket["names_observed"]) > 1:
            bucket["conflicts"].append(
                {
                    "type": "name_variance",
                    "values": bucket["names_observed"],
                    "note": "Multiple names for same national ID — review required.",
                }
            )
            bucket["grouping_confidence"] = "medium"

    proposed: list[dict[str, Any]] = []
    for idx, (_nid, bucket) in enumerate(sorted(groups.items(), key=lambda item: item[0]), start=1):
        proposed.append({"proposed_fixture_key": f"employee_{idx:03d}", **bucket})

    for idx, slip in enumerate(ungrouped, start=1):
        fields = {f["field"]: f for f in slip["fields"]}
        proposed.append(
            {
                "proposed_fixture_key": f"ungrouped_{idx:03d}",
                "national_id_hash": None,
                "national_id_masked": mask_national_id(
                    (fields.get("employee_id") or {}).get("raw_value")
                ),
                "names_observed": [
                    str((fields.get("employee_name") or {}).get("raw_value"))
                ]
                if (fields.get("employee_name") or {}).get("raw_value") not in (None, "")
                else [],
                "employee_numbers_observed": [
                    str((fields.get("employee_number") or {}).get("raw_value"))
                ]
                if (fields.get("employee_number") or {}).get("raw_value") not in (None, "")
                else [],
                "source_refs": [
                    {
                        "fixture_id": slip["source"]["fixture_id"],
                        "page": slip["source"]["page"],
                    }
                ],
                "payslip_keys": [slip["payslip_key"]],
                "conflicts": [
                    {
                        "type": "not_auto_grouped",
                        "note": "National ID missing/low-confidence/not CONFIRMED — manual review.",
                    }
                ],
                "missing_profile_fields": [
                    key
                    for key in IDENTITY_FIELDS
                    if (fields.get(key) or {}).get("review_status") == "MISSING"
                ],
                "grouping_confidence": "none",
                "grouping_basis": "manual_review_required",
            }
        )
    return proposed


def build_schema_preview() -> dict[str, Any]:
    return {
        "status": "schema_preview_only",
        "note": MARKER,
        "dataset": {
            "version": "0.0.0-review",
            "locale_default": "he",
            "currency_default": "ILS",
            "extensible": True,
            "registry_driven_document_types": True,
            "registry_driven_validation_modules": True,
        },
        "entities": {
            "source_documents": {
                "fields": [
                    "document_key",
                    "fixture_path",
                    "fixture_classification",
                    "media_type",
                    "page_count",
                    "sha256",
                ]
            },
            "employees": {
                "fields": [
                    "employee_key",
                    "national_id_hash",
                    "national_id_masked",
                    "display_name",
                    "employee_number",
                    "aliases",
                    "review_status",
                ],
                "note": "Employee is business data, separate from auth User.",
            },
            "documents": {
                "fields": [
                    "document_key",
                    "employee_key",
                    "document_type_key",
                    "period_year",
                    "period_month",
                    "source_document_key",
                    "source_page",
                    "version",
                    "availability",
                ]
            },
            "expected_extractions": {
                "fields": [
                    "document_key",
                    "field_key",
                    "raw_value",
                    "normalized_value",
                    "review_status",
                    "evidence_ids",
                    "confidence",
                ]
            },
            "expected_validation_scenarios": {
                "fields": [
                    "scenario_key",
                    "document_key",
                    "module_keys",
                    "expected_overall",
                    "notes",
                    "unavailable_checks",
                ]
            },
            "review_metadata": {
                "fields": ["reviewed_by", "reviewed_at", "approval_status", "blocking_items"]
            },
        },
        "example_shape": {
            "dataset_version": "1.0.0",
            "employees": [{"employee_key": "employee_001", "review_status": "approved"}],
            "documents": [
                {
                    "document_key": "doc_payslip_employee_001_2026_06",
                    "document_type_key": "payslip",
                    "employee_key": "employee_001",
                    "period_year": 2026,
                    "period_month": 6,
                    "source_page": 1,
                }
            ],
        },
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    summary = report["summary"]
    lines: list[str] = [
        "# Accountant Fixture Extraction Review",
        "",
        f"> {MARKER}",
        "",
        "## Executive Summary",
        "",
    ]
    for key, label in [
        ("files_processed", "Files processed"),
        ("pages_processed", "Pages processed"),
        ("payslips_detected", "Payslips detected"),
        ("proposed_employees", "Proposed employee groups"),
        ("ungrouped_candidates", "Ungrouped candidates"),
        ("confirmed_fields", "Confirmed fields"),
        ("uncertain_fields", "Uncertain fields"),
        ("missing_fields", "Missing fields"),
        ("requires_human_review_fields", "Requires human review"),
        ("conflicting_fields", "Conflicts"),
        ("failed_pages", "Failed pages"),
        ("pipeline_warnings", "Pipeline warnings"),
    ]:
        lines.append(f"- **{label}:** {summary.get(key, 0)}")
    lines.extend(["", "## Environment", ""])
    for key, value in report["environment"].items():
        lines.append(f"- **{key}:** `{value}`")
    lines.extend(["", "## Source Files", ""])
    for doc in report["source_documents"]:
        lines.append(
            f"- `{doc['fixture_id']}` — {doc['size_bytes']} bytes — "
            f"pages={doc['page_count']} — status={doc['processing_status']}"
        )
    lines.extend(["", "## Payslip-by-Payslip Results", ""])
    important = {
        "employee_name",
        "employee_id",
        "employee_number",
        "pay_period",
        "employment_type",
        "department",
        "hourly_rate",
        "base_salary",
        "regular_hours",
        "overtime_hours",
        "gross_salary",
        "net_salary",
        "income_tax",
        "national_insurance",
        "health_tax",
        "pension_employee",
        "pension_employer",
        "travel_expenses",
        "vacation_balance",
        "sick_leave_balance",
    }
    for slip in report["payslips"]:
        fields = {f["field"]: f for f in slip["fields"]}
        emp_id = fields.get("employee_id") or {}
        name = fields.get("employee_name") or {}
        period = fields.get("pay_period") or {}
        lines.extend(
            [
                f"### {slip['payslip_key']}",
                "",
                f"- **Source:** `{slip['source']['fixture_id']}` page {slip['source']['page']}",
                f"- **Fixture intent:** {slip['fixture_classification']}",
                f"- **Masked national ID:** {emp_id.get('raw_value_masked') or '—'}",
                f"- **Employee name (raw):** "
                f"{name.get('raw_value') if name.get('review_status') != 'MISSING' else '—'}",
                f"- **Pay period (raw):** "
                f"{period.get('raw_value') if period.get('review_status') != 'MISSING' else '—'}",
                f"- **Extraction status:** {slip['extraction_status']}",
                f"- **OCR engine / conf:** {slip['ocr']['engine']} / {slip['ocr']['overall_confidence']}",
                f"- **Parser model / retry:** {slip['parser']['model']} / {slip['parser']['retry_used']}",
                "",
                "| Field | Review | Parser | Confidence | Raw | Source text |",
                "|---|---|---|---|---|---|",
            ]
        )
        for field in slip["fields"]:
            if field["review_status"] == "MISSING" and field["field"] not in important:
                continue
            raw_display = field.get("raw_value_masked", field.get("raw_value"))
            if raw_display is None:
                raw_display = "—"
            raw_display = str(raw_display).replace("|", "\\|")[:80]
            src = str(field.get("source_text") or "—").replace("|", "\\|").replace("\n", " ")[:60]
            lines.append(
                f"| `{field['field']}` | {field['review_status']} | {field['parser_status']} | "
                f"{field.get('confidence')} | {raw_display} | {src} |"
            )
        if slip.get("warnings"):
            lines.extend(["", "**Warnings:**"])
            lines.extend(f"- {w}" for w in slip["warnings"])
        if slip.get("manual_review_items"):
            lines.extend(["", "**Manual review items:**"])
            for item in slip["manual_review_items"][:40]:
                lines.append(f"- {item}")
            if len(slip["manual_review_items"]) > 40:
                lines.append(f"- … and {len(slip['manual_review_items']) - 40} more")
        lines.append("")

    lines.extend(["## Employee Grouping Proposal", ""])
    for group in report["proposed_employee_groups"]:
        lines.extend(
            [
                f"### {group['proposed_fixture_key']}",
                "",
                f"- **Masked ID:** {group.get('national_id_masked') or '—'}",
                f"- **Names:** {', '.join(group.get('names_observed') or []) or '—'}",
                f"- **Employee numbers:** {', '.join(group.get('employee_numbers_observed') or []) or '—'}",
                f"- **Grouping confidence:** {group.get('grouping_confidence')}",
                f"- **Basis:** {group.get('grouping_basis')}",
            ]
        )
        for conflict in group.get("conflicts") or []:
            lines.append(f"- **Conflict:** {conflict}")
        lines.append("")

    lines.extend(["## PNG vs PDF Comparison", ""])
    cmp_ = report.get("png_pdf_comparison") or {}
    if not cmp_:
        lines.append("No comparison available.")
    else:
        lines.extend(
            [
                f"- **Best matching PDF page:** {cmp_.get('best_match_page')}",
                f"- **OCR text Jaccard similarity:** {cmp_.get('ocr_text_similarity')}",
                f"- **Matching fields:** {', '.join(cmp_.get('matching_fields') or []) or '—'}",
                f"- **Differing fields:** {', '.join(cmp_.get('differing_fields') or []) or '—'}",
                f"- **Recommended review source (not approved):** {cmp_.get('recommended_review_source')}",
                "",
                cmp_.get("notes") or "",
            ]
        )
    lines.extend(
        [
            "",
            "## Proposed Seed Structure",
            "",
            "See `proposed_seed_schema.json` for the extensible preview. Not approved.",
            "",
            "## Blocking Review Questions",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in (report.get("blocking_review_items") or []))
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    (REVIEW_DIR / "README.md").write_text(
        f"# {MARKER}\n\n"
        "Temporary extraction review artifacts for accountant development seed workflow.\n\n"
        "- Do **not** treat as approved seed data.\n"
        "- Do **not** load into production databases.\n"
        "- Final seed generation requires explicit human approval.\n",
        encoding="utf-8",
    )

    log_lines: list[str] = []
    started = datetime.now(UTC)
    env: dict[str, Any] = {
        "command": "py scripts/dev/extract_fixture_review.py",
        "api_base": API_BASE,
        "generated_at": started.isoformat(),
        "git_commit": git_commit(),
        "language_requested": "he",
        "execution_mode": "http_ocr_extract_then_parser_payslip",
        "db_writes": False,
    }
    log_lines.append(f"START {started.isoformat()}")
    log_lines.append(json.dumps(env, ensure_ascii=False))

    try:
        with urllib.request.urlopen(f"{API_BASE}/api/v1/health", timeout=10) as response:
            health = response.read().decode("utf-8")
            log_lines.append(f"HEALTH {health}")
    except Exception as exc:  # noqa: BLE001
        logger.error("API not reachable at %s: %s", API_BASE, exc)
        (REVIEW_DIR / "execution_log.txt").write_text(
            "\n".join(log_lines + [f"FATAL API unreachable: {exc}"]) + "\n",
            encoding="utf-8",
        )
        return 1

    source_documents: list[dict[str, Any]] = []
    payslips: list[dict[str, Any]] = []
    warnings_global: list[str] = []
    failed_pages = 0
    language = "he"

    with tempfile.TemporaryDirectory(prefix="fixture_review_") as tmp:
        tmp_path = Path(tmp)
        for classification, fixture_id in FIXTURES:
            fixture, content = read_fixture_bytes(fixture_id)
            sha = hashlib.sha256(content).hexdigest()
            is_pdf = fixture.filename.lower().endswith(".pdf")
            pages = page_count_pdf(content) if is_pdf else 1
            doc_entry = {
                "fixture_id": fixture_id,
                "fixture_classification": classification,
                "filename": fixture.filename,
                "media_type": fixture.media_type,
                "size_bytes": fixture.size_bytes,
                "page_count": pages,
                "sha256": sha,
                "processing_status": "pending",
            }
            log_lines.append(f"PROCESS {fixture_id} pages={pages}")
            logger.info("Processing %s (%s pages)", fixture_id, pages)
            page_errors = 0
            for page_index in range(pages):
                page_no = page_index + 1
                if is_pdf:
                    page_bytes = extract_pdf_page(content, page_index)
                    page_name = f"{Path(fixture.filename).stem}_p{page_no:02d}.pdf"
                    page_type = "application/pdf"
                else:
                    page_bytes = content
                    page_name = fixture.filename
                    page_type = fixture.media_type
                (tmp_path / page_name).write_bytes(page_bytes)
                logger.info("  OCR+parse %s page %s", fixture_id, page_no)
                ocr_dict, parse_dict, page_warnings = run_ocr_parse(
                    content=page_bytes,
                    filename=page_name,
                    content_type=page_type,
                    language=language,
                )
                payslip_key = f"{classification}_{Path(fixture.filename).stem}_p{page_no:02d}"
                extraction_status = "ok"
                if ocr_dict is None:
                    extraction_status = "ocr_failed"
                    failed_pages += 1
                    page_errors += 1
                elif parse_dict is None:
                    extraction_status = "parser_failed"
                    failed_pages += 1
                    page_errors += 1

                field_rows: list[dict[str, Any]] = []
                manual_items: list[str] = []
                if parse_dict and isinstance(parse_dict.get("fields"), dict):
                    field_rows = summarize_fields(parse_dict["fields"], source_page=page_no)
                    for field in field_rows:
                        if field["review_status"] in {
                            "REQUIRES_HUMAN_REVIEW",
                            "UNCERTAIN",
                            "CONFLICTING",
                            "INVALID_FORMAT",
                        }:
                            manual_items.append(
                                f"{field['field']}: {field['review_status']} "
                                f"(parser={field['parser_status']}, conf={field.get('confidence')})"
                            )

                slip = {
                    "payslip_key": payslip_key,
                    "fixture_classification": classification,
                    "source": {
                        "fixture_id": fixture_id,
                        "page": page_no,
                        "page_filename": page_name,
                    },
                    "extraction_status": extraction_status,
                    "ocr": {
                        "engine": (ocr_dict or {}).get("engine"),
                        "language_requested": (ocr_dict or {}).get("language_requested"),
                        "language_effective": (ocr_dict or {}).get("language_effective"),
                        "overall_confidence": (ocr_dict or {}).get("overall_confidence"),
                        "raw_text_preview": ((ocr_dict or {}).get("raw_text") or "")[:500],
                        "raw_text_sha256": hashlib.sha256(
                            ((ocr_dict or {}).get("raw_text") or "").encode("utf-8")
                        ).hexdigest(),
                        "warnings": (ocr_dict or {}).get("warnings") or [],
                    },
                    "parser": {
                        "model": (parse_dict or {}).get("model"),
                        "language": (parse_dict or {}).get("language"),
                        "retry_used": (parse_dict or {}).get("retry_used"),
                        "warnings": (parse_dict or {}).get("warnings") or [],
                    },
                    "fields": field_rows,
                    "warnings": page_warnings,
                    "manual_review_items": manual_items,
                    "validation_observations": {
                        "could_evaluate_with_current_engine": bool(
                            parse_dict
                            and any(
                                f["field"]
                                in {"gross_salary", "net_salary", "base_salary", "hourly_rate"}
                                and f["review_status"] != "MISSING"
                                for f in field_rows
                            )
                        ),
                        "unavailable_without_supporting_data": [
                            "attendance_cross_check",
                            "contract_rag_cross_check",
                            "historical_comparison",
                            "department_rule_profile_without_master_data",
                        ],
                        "note": "No fabricated compliance findings — observations only.",
                    },
                    "_ocr_raw_text": (ocr_dict or {}).get("raw_text"),
                    "_parser_fields_raw": (parse_dict or {}).get("fields"),
                }
                payslips.append(slip)
                log_lines.append(
                    f"  page {page_no}: status={extraction_status} warnings={len(page_warnings)}"
                )
                (REVIEW_DIR / "_partial_payslips.json").write_text(
                    json.dumps(payslips, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            doc_entry["processing_status"] = "completed_with_errors" if page_errors else "completed"
            source_documents.append(doc_entry)

    png_slips = [s for s in payslips if s["source"]["fixture_id"].endswith(".png")]
    valid_pdf_slips = [
        s
        for s in payslips
        if s["source"]["fixture_id"].endswith("payslips_valid_2026_06_multi.pdf")
    ]
    png_pdf_comparison: dict[str, Any] = {}
    if png_slips and valid_pdf_slips:
        png = png_slips[0]
        png_text = png.get("_ocr_raw_text") or ""
        best = None
        best_score = -1.0
        for slip in valid_pdf_slips:
            score = jaccard(png_text, slip.get("_ocr_raw_text") or "")
            if score > best_score:
                best_score = score
                best = slip
        matching: list[str] = []
        differing: list[str] = []
        if best:
            png_fields = {f["field"]: f for f in png["fields"]}
            pdf_fields = {f["field"]: f for f in best["fields"]}
            for key in PAYSLIP_FIELD_KEYS:
                a = png_fields.get(key, {})
                b = pdf_fields.get(key, {})
                if a.get("review_status") == "MISSING" and b.get("review_status") == "MISSING":
                    continue
                if str(a.get("raw_value")) == str(b.get("raw_value")) and a.get(
                    "review_status"
                ) == b.get("review_status"):
                    matching.append(key)
                else:
                    differing.append(key)
            png_pdf_comparison = {
                "png_fixture_id": png["source"]["fixture_id"],
                "best_match_pdf_fixture_id": best["source"]["fixture_id"],
                "best_match_page": best["source"]["page"],
                "ocr_text_similarity": round(best_score, 4),
                "png_ocr_confidence": png["ocr"]["overall_confidence"],
                "pdf_page_ocr_confidence": best["ocr"]["overall_confidence"],
                "matching_fields": matching,
                "differing_fields": differing,
                "recommended_review_source": (
                    "pdf_page"
                    if (best["ocr"]["overall_confidence"] or 0)
                    >= (png["ocr"]["overall_confidence"] or 0)
                    else "png"
                ),
                "notes": (
                    "Comparison only — do not auto-approve either source. "
                    "PNG is documented as a screenshot of one valid multi-PDF payslip."
                ),
            }

    groups = proposed_employee_groups(payslips)
    status_counter: Counter[str] = Counter()
    for slip in payslips:
        for field in slip["fields"]:
            status_counter[field["review_status"]] += 1

    blocking: list[str] = []
    for slip in payslips:
        for item in slip.get("manual_review_items") or []:
            blocking.append(f"{slip['payslip_key']}: {item}")
    for group in groups:
        if group.get("grouping_confidence") in {"none", "medium"} or group.get("conflicts"):
            blocking.append(
                f"Grouping {group['proposed_fixture_key']}: "
                f"confidence={group.get('grouping_confidence')} conflicts={group.get('conflicts')}"
            )
    blocking.append(
        "No employee master records should be created until national IDs and names are explicitly approved."
    )
    blocking.append(
        "Valid/invalid directory names are fixture intent only — do not treat extraction success as legal correctness."
    )

    summary = {
        "files_processed": len(source_documents),
        "pages_processed": sum(d["page_count"] for d in source_documents),
        "payslips_detected": len(payslips),
        "proposed_employees": len(
            [g for g in groups if str(g["proposed_fixture_key"]).startswith("employee_")]
        ),
        "ungrouped_candidates": len(
            [g for g in groups if str(g["proposed_fixture_key"]).startswith("ungrouped_")]
        ),
        "confirmed_fields": status_counter.get("CONFIRMED", 0),
        "uncertain_fields": status_counter.get("UNCERTAIN", 0),
        "missing_fields": status_counter.get("MISSING", 0),
        "requires_human_review_fields": status_counter.get("REQUIRES_HUMAN_REVIEW", 0),
        "conflicting_fields": status_counter.get("CONFLICTING", 0),
        "failed_pages": failed_pages,
        "pipeline_warnings": sum(len(s.get("warnings") or []) for s in payslips),
    }

    for slip in payslips:
        if slip["ocr"].get("engine"):
            env["ocr_engine_observed"] = slip["ocr"]["engine"]
            env["ocr_language_effective_sample"] = slip["ocr"].get("language_effective")
            env["parser_model_observed"] = slip["parser"].get("model")
            break

    report = {
        "report_version": "1.0",
        "status": "review_only",
        "marker": MARKER,
        "generated_at": started.isoformat(),
        "environment": env,
        "source_documents": source_documents,
        "payslips": payslips,
        "proposed_employee_groups": groups,
        "png_pdf_comparison": png_pdf_comparison,
        "summary": summary,
        "warnings": warnings_global,
        "blocking_review_items": blocking,
    }

    finished = datetime.now(UTC)
    log_lines.append(f"END {finished.isoformat()}")
    log_lines.append(json.dumps(summary, ensure_ascii=False))

    (REVIEW_DIR / "extraction_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (REVIEW_DIR / "employee_grouping_proposal.json").write_text(
        json.dumps(
            {
                "status": "review_only",
                "marker": MARKER,
                "generated_at": started.isoformat(),
                "groups": groups,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (REVIEW_DIR / "proposed_seed_schema.json").write_text(
        json.dumps(build_schema_preview(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (REVIEW_DIR / "execution_log.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    write_markdown(report, REVIEW_DIR / "extraction_report.md")
    partial = REVIEW_DIR / "_partial_payslips.json"
    if partial.exists():
        partial.unlink()

    logger.info("Review artifacts written to %s", REVIEW_DIR)
    logger.info("Summary: %s", summary)
    return 0 if failed_pages == 0 else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        raise
