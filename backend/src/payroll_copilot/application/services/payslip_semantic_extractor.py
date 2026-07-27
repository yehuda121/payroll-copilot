"""Payslip semantic extraction (semantic_v1) — shared Guest / Employee / Batch Stage-1.

Field Catalog–guided LLM maps document evidence → grounded canonical concepts.
Does NOT validate payroll correctness. Does NOT backfill from employee profiles.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from payroll_copilot.application.exceptions import (
    PayslipParserEmptyOcrError,
    PayslipParserJsonError,
    PayslipParserUnavailableError,
)
from payroll_copilot.application.ports import AICapability, Message
from payroll_copilot.application.ports.payslip_parser import (
    PAYSLIP_CANONICAL_EXTRA_KEYS,
    PAYSLIP_FIELD_KEYS,
)
from payroll_copilot.application.services.candidate_evidence_validator import (
    _value_matches_candidate,
)
from payroll_copilot.application.services.dynamic_document import (
    DynamicDocumentEntry,
    entries_have_usable_values,
    new_entry,
)
from payroll_copilot.application.services.parser_evidence import (
    employee_name_implausible_reason,
    employee_name_looks_like_field_caption,
    normalize_numeric_token,
)
from payroll_copilot.application.services.ocr_line_evidence import (
    evidence_candidate_priority_tier,
)
from payroll_copilot.application.services.payslip_field_registry import (
    FieldRequirementCategory,
    requirement_category_for_key,
)
from payroll_copilot.application.services.payslip_semantic_catalog import (
    EXTRACTOR_VERSION,
    all_catalog_keys,
    catalog_as_prompt_rows,
)
from payroll_copilot.infrastructure.ai.provider_router import AIProviderRouter
from payroll_copilot.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)

_DEFAULT_MAX_PREDICT = 8192
_MIN_TIMEOUT_SECONDS = 90.0
_LOW_CONFIDENCE_THRESHOLD = 0.6

# Concepts that must not share the same evidence candidate (identity collision).
_MUTUALLY_EXCLUSIVE_PAIRS: frozenset[frozenset[str]] = frozenset(
    {
        frozenset({"national_id", "employee_number"}),
        frozenset({"national_id", "employee_id"}),
        frozenset({"employee_number", "employee_id"}),
        frozenset({"employee_name", "employer_name"}),
        frozenset({"gross_salary", "net_salary"}),
        frozenset({"gross_salary", "base_salary"}),
    }
)

_SYSTEM_PROMPT = """You are a payroll payslip SEMANTIC extractor.
Return STRICT JSON only. No markdown. No commentary.

Your job is to answer: WHAT PAYROLL CONCEPT does each piece of document evidence represent?

You are NOT reconstructing every printed label for completeness.
You are NOT validating legal correctness (checksums, minimum wage, etc.).
You MUST NOT invent values that are not supported by the evidence candidates or OCR text.
You MUST NOT use employee profile / HR / account data — only the document evidence provided.

Unlabeled values are valid. Header / personal-details blocks often contain:
- person name WITHOUT an explicit "שם" / "שם העובד" / "Employee Name" label
- national ID without an "ID" label
- employee number / employment start date / department / period nearby

employee_name means the person who receives this salary — not the employer, payroll provider,
bank, website, address, heading, or organization name.

When identifying employee_name:
- Prefer a letter-bearing person name near national_id / employee_number / personal details
- Never use national_id digits, employee numbers, money amounts, dates, emails, or URLs as the name
- Never use company/employer legal names (e.g. Ltd / בע"מ / company registration) as employee_name
- Return employee_name only when a document evidence candidate supports the exact name text

Distinguish carefully:
- national_id = government Teudat Zehut (usually 9 digits)
- employee_number / employee_id = employer payroll identifiers (NOT national ID)
- employer_name = business / company issuing the payslip

Priority:
1. REQUIRED catalog concepts
2. EXPECTED catalog concepts
3. additional meaningful payroll components not in the catalog

Output shape:
{
  "extractor_version": "semantic_v1",
  "fields": [
    {
      "canonical_key": "employee_name",
      "value": "as on document",
      "status": "FOUND",
      "confidence": 0.0,
      "evidence_ids": ["cand_..."],
      "label_as_printed": null
    }
  ],
  "additional_fields": [
    {
      "label": "printed label",
      "value": "value",
      "confidence": 0.0,
      "evidence_ids": ["cand_..."],
      "page": 1
    }
  ],
  "not_found": ["employment_scope"]
}

Rules:
- status must be FOUND | FOUND_LOW_CONFIDENCE | NOT_FOUND
- For FOUND / FOUND_LOW_CONFIDENCE cite evidence_ids from the candidate list when possible
- Prefer evidence candidates over free OCR invention
- Do not force unknown components into the closest canonical key — use additional_fields
- Put catalog keys you cannot support in not_found (do not fabricate)
- Extract printed values even if they look invalid (e.g. bad ID checksum) — validation is downstream
"""


@dataclass
class SemanticExtractionResult:
    entries: list[DynamicDocumentEntry]
    model_name: str
    warnings: list[str] = field(default_factory=list)
    extractor_version: str = EXTRACTOR_VERSION
    not_found: list[str] = field(default_factory=list)
    grounded_count: int = 0
    rejected_ungrounded: int = 0
    low_confidence_count: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise PayslipParserJsonError("Semantic extractor returned non-JSON content.")
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise PayslipParserJsonError("Semantic extractor returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise PayslipParserJsonError("Semantic extractor JSON root must be an object.")
    return payload


def _as_confidence(raw: Any) -> float | None:
    try:
        confidence = float(raw) if raw is not None and raw != "" else None
    except (TypeError, ValueError):
        return None
    if confidence is not None and (confidence < 0 or confidence > 1):
        return None
    return confidence


def _normalize_status(raw: Any, confidence: float | None) -> str:
    text = str(raw or "").strip().upper()
    if text in {"FOUND_LOW_CONFIDENCE", "LOW_CONFIDENCE", "UNCERTAIN"}:
        return "FOUND_LOW_CONFIDENCE"
    if text in {"NOT_FOUND", "MISSING", "ABSENT"}:
        return "NOT_FOUND"
    if text == "FOUND":
        if confidence is not None and confidence < _LOW_CONFIDENCE_THRESHOLD:
            return "FOUND_LOW_CONFIDENCE"
        return "FOUND"
    if confidence is not None and confidence < _LOW_CONFIDENCE_THRESHOLD:
        return "FOUND_LOW_CONFIDENCE"
    return "FOUND"


def _prompt_priority_tier(item: dict[str, Any]) -> int:
    """Lower = earlier in the prompt. Prefer unlabeled person-name-like lines."""
    return evidence_candidate_priority_tier(item)

def _compact_candidates_for_prompt(
    llm_candidates: list[dict[str, Any]],
    *,
    max_items: int = 220,
) -> list[dict[str, Any]]:
    indexed = [
        (idx, item)
        for idx, item in enumerate(llm_candidates)
        if isinstance(item, dict)
    ]
    ordered = [item for _, item in sorted(indexed, key=lambda pair: (_prompt_priority_tier(pair[1]), pair[0]))]
    compact: list[dict[str, Any]] = []
    for item in ordered[:max_items]:
        row = {
            "id": item.get("candidate_id") or item.get("id"),
            "label": item.get("label"),
            "value": item.get("value"),
            "page": item.get("page"),
            "section": item.get("section_id") or item.get("section"),
            "relation": item.get("relation"),
        }
        if item.get("conflict"):
            row["conflict"] = True
        # Omit nulls to keep prompt compact.
        compact.append({k: v for k, v in row.items() if v not in (None, "", [])})
    return compact


def _employee_name_reject_warning(reason: str) -> str:
    if reason in {
        "implausible_employee_name_numeric_only",
        "implausible_employee_name_monetary",
        "implausible_employee_name_date",
    }:
        return f"employee_name_rejected_numeric:{reason}"
    if reason == "implausible_employee_name_employer_like":
        return f"employee_name_rejected_employer_like:{reason}"
    if reason in {
        "implausible_employee_name_url",
        "implausible_employee_name_email",
    }:
        return f"employee_name_rejected_url:{reason}"
    return f"employee_name_rejected_unsupported:{reason}"


def _employee_name_outcome_from_warnings(
    warnings: list[str],
    *,
    has_entry: bool,
    listed_not_found: bool,
) -> str:
    """Non-PII diagnostic category for employee_name grounding."""
    joined = " ".join(warnings)
    if has_entry and "employee_name_grounded" in joined:
        return "employee_name_grounded"
    if "employee_name_rejected_numeric" in joined:
        return "employee_name_rejected_numeric"
    if "employee_name_rejected_employer_like" in joined:
        return "employee_name_rejected_employer_like"
    if "employee_name_rejected_url" in joined:
        return "employee_name_rejected_url"
    if "employee_name_rejected_unsupported" in joined or "unsupported_model_value_rejected" in joined:
        return "employee_name_rejected_unsupported"
    if listed_not_found or not has_entry:
        return "employee_name_missing"
    return "employee_name_candidate_found"


def _hydrate_employee_name_from_candidates(
    resolved: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, Any, str | None, str, str]:
    """Pick a plausible person-name side from cited candidates (value or label)."""
    for cand in resolved:
        value_text = str(cand.get("value_text") or "").strip()
        label_text = str(cand.get("label_text") or "").strip()
        if value_text and employee_name_implausible_reason(value_text) is None:
            return cand, value_text, "value", value_text, label_text
        if (
            label_text
            and not employee_name_looks_like_field_caption(label_text)
            and employee_name_implausible_reason(label_text) is None
        ):
            return cand, label_text, "label", value_text, label_text
    return None, None, None, "", ""


def ground_semantic_field(
    *,
    canonical_key: str,
    model_value: Any,
    status: str,
    confidence: float | None,
    evidence_ids: list[str],
    label_as_printed: str | None,
    candidate_index: dict[str, dict[str, Any]],
    consumed: dict[str, str],
) -> tuple[DynamicDocumentEntry | None, list[str], bool]:
    """Ground one canonical field. Returns (entry|None, warnings, was_rejected)."""
    warnings: list[str] = []
    if status == "NOT_FOUND":
        return None, warnings, False

    known = set(candidate_index.keys())
    cited = [str(eid).strip() for eid in evidence_ids if str(eid).strip()]
    resolved: list[dict[str, Any]] = []
    for cid in cited:
        if cid not in known:
            warnings.append(f"unknown_evidence_id:{cid}")
            continue
        owner = consumed.get(cid)
        if owner and owner != canonical_key and _exclusive_conflict(owner, canonical_key):
            warnings.append(f"consumed_evidence_conflict:{cid}:{owner}")
            continue
        resolved.append(candidate_index[cid])

    if not resolved:
        # Allow OCR-text support without IDs only as low-confidence review when value present.
        if model_value not in (None, "") and not cited:
            if canonical_key == "employee_name":
                reason = employee_name_implausible_reason(model_value)
                if reason:
                    warnings.append(_employee_name_reject_warning(reason))
                    warnings.append("ungrounded_rejected")
                    return None, warnings, True
                # employee_name still requires citeable document evidence — do not accept bare LLM guess.
                warnings.append("employee_name_rejected_unsupported:missing_evidence_ids")
                warnings.append("ungrounded_rejected")
                return None, warnings, True
            warnings.append("missing_evidence_ids")
            entry = new_entry(
                key=canonical_key,
                value=model_value,
                confidence=min(confidence or 0.45, 0.45),
                page=None,
                source=EXTRACTOR_VERSION,
                source_text=label_as_printed,
                section=_section_for_key(canonical_key),
                kind="canonical_field_ungrounded",
            )
            return entry, warnings, False
        warnings.append("ungrounded_rejected")
        return None, warnings, True

    model_has_value = model_value not in (None, "")
    primary: dict[str, Any] | None = None
    hydrated: Any = None
    supported_by: str | None = None  # "value" | "label"
    value_text = ""
    label_text = ""

    if model_has_value:
        # Ground if ANY cited candidate supports the model via value_text OR label_text.
        # Association candidates often hold two concepts (e.g. name on label, NID on value).
        from payroll_copilot.application.services.payslip_identity_comparison import (
            person_name_tokens_equal,
        )

        for cand in resolved:
            cand_value = str(cand.get("value_text") or "").strip()
            cand_label = str(cand.get("label_text") or "").strip()
            if not cand_value and not cand_label:
                continue
            if cand_value and _value_matches_candidate(model_value, cand_value):
                primary = cand
                value_text = cand_value
                label_text = cand_label
                # Prefer OCR/evidence text when model only reorders name tokens.
                if (
                    isinstance(model_value, str)
                    and person_name_tokens_equal(model_value, cand_value)
                    and str(model_value).strip() != cand_value
                ):
                    hydrated = cand_value
                else:
                    hydrated = model_value
                supported_by = "value"
                break
            if cand_label and _value_matches_candidate(model_value, cand_label):
                primary = cand
                value_text = cand_value
                label_text = cand_label
                if (
                    isinstance(model_value, str)
                    and person_name_tokens_equal(model_value, cand_label)
                    and str(model_value).strip() != cand_label
                ):
                    hydrated = cand_label
                else:
                    hydrated = model_value
                supported_by = "label"
                break
        if primary is None:
            # Do NOT replace with value_text — that may be a different concept.
            warnings.append("unsupported_model_value_rejected")
            if canonical_key == "employee_name":
                warnings.append("employee_name_rejected_unsupported:model_value_mismatch")
            return None, warnings, True
    elif canonical_key == "employee_name":
        primary, hydrated, supported_by, value_text, label_text = (
            _hydrate_employee_name_from_candidates(resolved)
        )
        if primary is None or hydrated in (None, ""):
            warnings.append("employee_name_rejected_unsupported:empty_plausible_candidate")
            warnings.append("empty_candidate_value")
            return None, warnings, True
    else:
        # Model cited evidence without a value — hydrate from the first usable value_text.
        primary = resolved[0]
        value_text = str(primary.get("value_text") or "").strip()
        label_text = str(primary.get("label_text") or "").strip()
        if not value_text:
            warnings.append("empty_candidate_value")
            return None, warnings, True
        hydrated = value_text
        supported_by = "value"

    # Prefer numeric hydration only when the grounded side is value_text.
    if supported_by == "value":
        normalized = primary.get("normalized_value") if primary else None
        if normalized is None:
            normalized = normalize_numeric_token(value_text)
        if normalized is not None and _looks_numeric_key(canonical_key):
            hydrated = int(normalized) if float(normalized).is_integer() else float(normalized)

    if canonical_key == "employee_name":
        reason = employee_name_implausible_reason(hydrated)
        if reason:
            warnings.append(_employee_name_reject_warning(reason))
            return None, warnings, True
        warnings.append("employee_name_grounded")

    out_confidence = confidence
    if out_confidence is None:
        out_confidence = 0.75
    if primary and bool(primary.get("conflict")):
        out_confidence = min(out_confidence, 0.55)
        status = "FOUND_LOW_CONFIDENCE"
        warnings.append("conflicted_candidate")

    if status == "FOUND_LOW_CONFIDENCE":
        out_confidence = min(out_confidence, _LOW_CONFIDENCE_THRESHOLD - 0.01)

    page = None
    try:
        page = int(primary["page"]) if primary and primary.get("page") is not None else None
    except (TypeError, ValueError):
        page = None

    for item in resolved:
        cid = str(item.get("candidate_id") or "")
        if cid:
            consumed[cid] = canonical_key

    kind = (
        "canonical_field_low_confidence"
        if status == "FOUND_LOW_CONFIDENCE"
        else "canonical_field"
    )
    evidence_side = label_text if supported_by == "label" else value_text
    entry = new_entry(
        key=canonical_key,
        value=hydrated,
        confidence=out_confidence,
        page=page,
        source=EXTRACTOR_VERSION,
        source_text=label_as_printed or evidence_side or None,
        section=_section_for_key(canonical_key),
        kind=kind,
    )
    return entry, warnings, False


def ground_additional_field(
    *,
    label: str,
    model_value: Any,
    confidence: float | None,
    evidence_ids: list[str],
    page: int | None,
    candidate_index: dict[str, dict[str, Any]],
) -> tuple[DynamicDocumentEntry | None, list[str]]:
    warnings: list[str] = []
    label = (label or "").strip()
    if not label and model_value in (None, ""):
        return None, warnings

    # Never promote additional into a catalog key by accident.
    snake = re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")
    if snake in all_catalog_keys() or snake in PAYSLIP_FIELD_KEYS or snake in PAYSLIP_CANONICAL_EXTRA_KEYS:
        warnings.append(f"additional_looks_canonical:{snake}")
        # Keep printed label as key for review; projection will map if synonym exists (legacy).

    known = set(candidate_index.keys())
    cited = [str(eid).strip() for eid in evidence_ids if str(eid).strip()]
    hydrated = model_value
    source_text = label or None
    out_page = page
    if cited:
        for cid in cited:
            if cid not in known:
                warnings.append(f"unknown_evidence_id:{cid}")
                continue
            cand = candidate_index[cid]
            value_text = str(cand.get("value_text") or "").strip()
            if not value_text:
                continue
            if model_value not in (None, "") and not _value_matches_candidate(model_value, value_text):
                warnings.append("additional_hallucination_replaced")
                hydrated = value_text
            elif hydrated in (None, ""):
                hydrated = value_text
            source_text = value_text
            try:
                out_page = int(cand["page"]) if cand.get("page") is not None else out_page
            except (TypeError, ValueError):
                pass
            break

    if hydrated in (None, ""):
        return None, warnings

    display_key = label or "unknown"
    entry = new_entry(
        key=display_key,
        value=hydrated,
        confidence=confidence if confidence is not None else 0.7,
        page=out_page,
        source=EXTRACTOR_VERSION,
        source_text=source_text,
        section="other",
        kind="additional_field",
    )
    return entry, warnings


def _exclusive_conflict(owner: str, candidate_key: str) -> bool:
    pair = frozenset({owner, candidate_key})
    return pair in _MUTUALLY_EXCLUSIVE_PAIRS


def _looks_numeric_key(canonical_key: str) -> bool:
    return canonical_key in {
        "base_salary",
        "gross_salary",
        "net_salary",
        "amount_paid",
        "income_tax",
        "national_insurance",
        "health_tax",
        "total_deductions",
        "hourly_rate",
        "regular_hours",
        "overtime_hours",
        "travel_expenses",
        "pension_employee",
        "pension_employer",
        "severance",
        "training_fund",
        "seniority_years",
        "vacation_balance",
        "sick_leave_balance",
        "minimum_wage_monthly",
        "minimum_wage_hourly",
        "employment_scope",
    }


def _section_for_key(canonical_key: str) -> str:
    category = requirement_category_for_key(canonical_key)
    if canonical_key in {
        "employee_name",
        "national_id",
        "employee_number",
        "employee_id",
        "employment_start_date",
        "employment_scope",
        "employment_type",
        "department",
        "seniority_years",
    }:
        return "identity"
    if canonical_key.startswith("employer"):
        return "employer"
    if canonical_key == "pay_period":
        return "period"
    if canonical_key in {
        "gross_salary",
        "base_salary",
        "salary_calculation_basis",
        "hourly_rate",
        "regular_hours",
        "overtime_hours",
        "travel_expenses",
    }:
        return "earnings"
    if canonical_key in {
        "income_tax",
        "national_insurance",
        "health_tax",
        "pension_employee",
        "pension_employer",
        "total_deductions",
        "severance",
        "training_fund",
    }:
        return "deductions"
    if canonical_key in {"net_salary", "amount_paid", "payment_method", "bank_name", "bank_branch", "bank_account"}:
        return "payment"
    if category == FieldRequirementCategory.REQUIRED:
        return "required"
    return "expected"


class PayslipSemanticExtractor:
    """Shared semantic_v1 Stage-1 extractor (Guest / Employee / Batch)."""

    def __init__(
        self,
        *,
        model_provider: Any | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        max_predict: int | None = None,
    ) -> None:
        settings = get_settings()
        router = AIProviderRouter(settings)
        self._provider = model_provider or router.provider_for(
            AICapability.DOCUMENT_EXTRACTION
        )
        self._model = model or router.model_for(AICapability.DOCUMENT_EXTRACTION)
        configured_timeout = float(
            timeout_seconds
            if timeout_seconds is not None
            else getattr(settings, "payslip_parser_timeout_seconds", 45.0)
        )
        self._timeout_seconds = max(configured_timeout, _MIN_TIMEOUT_SECONDS)
        configured_predict = int(
            max_predict
            if max_predict is not None
            else getattr(settings, "payslip_parser_max_predict", 4096)
        )
        self._max_predict = max(configured_predict, _DEFAULT_MAX_PREDICT)

    async def extract(
        self,
        *,
        ocr_text: str,
        language: str = "auto",
        pages_text: list[str] | None = None,
        evidence_bundle: dict[str, Any] | None = None,
    ) -> SemanticExtractionResult:
        if not (ocr_text or "").strip():
            raise PayslipParserEmptyOcrError()

        candidate_index: dict[str, dict[str, Any]] = {}
        llm_candidates: list[dict[str, Any]] = []
        warnings: list[str] = []
        if isinstance(evidence_bundle, dict):
            raw_index = evidence_bundle.get("candidate_index") or {}
            if isinstance(raw_index, dict):
                candidate_index = {
                    str(k): v for k, v in raw_index.items() if isinstance(v, dict)
                }
            llm_candidates = list(evidence_bundle.get("llm_candidates") or [])
            warnings.extend(str(w) for w in (evidence_bundle.get("warnings") or []) if w)

        catalog_rows = catalog_as_prompt_rows()
        compact = _compact_candidates_for_prompt(llm_candidates)
        if any(
            isinstance(item, dict) and _prompt_priority_tier(item) <= 1
            for item in llm_candidates
        ):
            warnings.append("employee_name_candidate_found")

        pages_block = ""
        if pages_text:
            chunks = [
                f"--- PAGE {i} ---\n{page}"
                for i, page in enumerate(pages_text, start=1)
                if page
            ]
            pages_block = "\n\n".join(chunks)

        # Keep OCR context bounded; candidates carry structure.
        ocr_context = (pages_block or ocr_text)[:24_000]

        user_content = (
            f"Document language hint: {language}\n"
            f"Extractor version: {EXTRACTOR_VERSION}\n\n"
            "FIELD CATALOG (identify these concepts when evidence supports them):\n"
            f"{json.dumps(catalog_rows, ensure_ascii=False)}\n\n"
            "EVIDENCE CANDIDATES (cite ids in evidence_ids):\n"
            f"{json.dumps(compact, ensure_ascii=False)}\n\n"
            "OCR TEXT CONTEXT (supporting only; prefer candidates):\n"
            f"{ocr_context}\n\n"
            "Extract grounded canonical fields + additional meaningful components.\n"
            "Do not invent. Do not validate. Unlabeled values are allowed.\n"
        )

        raw_content, model_name = await self._chat(user_content)
        payload = _parse_json_object(raw_content)
        result = self._materialize(payload, candidate_index=candidate_index)
        result.model_name = model_name
        result.warnings = list(dict.fromkeys([*warnings, *result.warnings]))
        if not entries_have_usable_values(result.entries):
            result.warnings.append("semantic_extractor_no_usable_entries")
        return result

    def _materialize(
        self,
        payload: dict[str, Any],
        *,
        candidate_index: dict[str, dict[str, Any]],
    ) -> SemanticExtractionResult:
        warnings: list[str] = []
        entries: list[DynamicDocumentEntry] = []
        not_found: list[str] = []
        grounded = 0
        rejected = 0
        low_conf = 0
        consumed: dict[str, str] = {}
        seen_canonical: set[str] = set()

        for item in payload.get("not_found") or []:
            key = str(item or "").strip()
            if key:
                not_found.append(key)

        for raw in payload.get("fields") or []:
            if not isinstance(raw, dict):
                continue
            key = str(raw.get("canonical_key") or raw.get("key") or "").strip()
            if not key:
                continue
            if key not in all_catalog_keys() and key not in PAYSLIP_FIELD_KEYS and key not in PAYSLIP_CANONICAL_EXTRA_KEYS:
                warnings.append(f"unknown_canonical_key:{key}")
                continue
            if key in seen_canonical:
                warnings.append(f"duplicate_canonical:{key}")
                continue
            confidence = _as_confidence(raw.get("confidence"))
            status = _normalize_status(raw.get("status"), confidence)
            evidence_ids = raw.get("evidence_ids") or raw.get("candidate_ids") or []
            if not isinstance(evidence_ids, list):
                evidence_ids = [evidence_ids]
            label = raw.get("label_as_printed")
            label_as_printed = str(label).strip() if isinstance(label, str) and label.strip() else None

            entry, field_warnings, was_rejected = ground_semantic_field(
                canonical_key=key,
                model_value=raw.get("value"),
                status=status,
                confidence=confidence,
                evidence_ids=[str(x) for x in evidence_ids],
                label_as_printed=label_as_printed,
                candidate_index=candidate_index,
                consumed=consumed,
            )
            warnings.extend(field_warnings)
            if was_rejected:
                rejected += 1
                if key not in not_found:
                    not_found.append(key)
                continue
            if entry is None:
                if key not in not_found:
                    not_found.append(key)
                continue
            seen_canonical.add(key)
            if entry.kind == "canonical_field":
                grounded += 1
            if entry.kind == "canonical_field_low_confidence" or (
                entry.confidence is not None and entry.confidence < _LOW_CONFIDENCE_THRESHOLD
            ):
                low_conf += 1
            if entry.kind == "canonical_field_ungrounded":
                low_conf += 1
                warnings.append(f"ungrounded_low_confidence:{key}")
            entries.append(entry)

        for raw in payload.get("additional_fields") or []:
            if not isinstance(raw, dict):
                continue
            label = str(raw.get("label") or raw.get("key") or "").strip()
            evidence_ids = raw.get("evidence_ids") or raw.get("candidate_ids") or []
            if not isinstance(evidence_ids, list):
                evidence_ids = [evidence_ids]
            page_raw = raw.get("page")
            try:
                page = int(page_raw) if page_raw is not None and page_raw != "" else None
            except (TypeError, ValueError):
                page = None
            entry, add_warnings = ground_additional_field(
                label=label,
                model_value=raw.get("value"),
                confidence=_as_confidence(raw.get("confidence")),
                evidence_ids=[str(x) for x in evidence_ids],
                page=page,
                candidate_index=candidate_index,
            )
            warnings.extend(add_warnings)
            if entry is not None:
                entries.append(entry)

        meta = {
            "extractor_version": EXTRACTOR_VERSION,
            "grounded_canonical_count": grounded,
            "rejected_ungrounded_count": rejected,
            "low_confidence_count": low_conf,
            "not_found": list(dict.fromkeys(not_found)),
            "candidate_count": len(candidate_index),
            "employee_name_outcome": _employee_name_outcome_from_warnings(
                warnings,
                has_entry=any(e.key == "employee_name" for e in entries),
                listed_not_found="employee_name" in not_found,
            ),
        }
        return SemanticExtractionResult(
            entries=entries,
            model_name="",
            warnings=list(dict.fromkeys(warnings)),
            extractor_version=EXTRACTOR_VERSION,
            not_found=list(dict.fromkeys(not_found)),
            grounded_count=grounded,
            rejected_ungrounded=rejected,
            low_confidence_count=low_conf,
            meta=meta,
        )

    async def _chat(self, user_content: str) -> tuple[str, str]:
        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ]
        try:
            result = await self._provider.complete(
                messages,
                temperature=0.0,
                max_tokens=self._max_predict,
                json_mode=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Semantic payslip extractor LLM request failed")
            raise PayslipParserUnavailableError(
                f"Semantic extractor LLM unavailable: {exc}"
            ) from exc

        content = result.content if isinstance(result.content, str) else ""
        if not content.strip():
            raise PayslipParserJsonError("Model returned an empty semantic extraction response.")
        return content, result.model or self._model
