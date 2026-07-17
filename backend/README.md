# Payroll Copilot Backend

Python package for the **Payroll Copilot** backend: a FastAPI API that runs a deterministic payroll validation engine, persists document uploads, and orchestrates the payroll assistant.

## Scope

- **FastAPI** presentation layer (`payroll_copilot.presentation`)
- **Deterministic validation** of payroll against configured labor-law and policy rules
- **Document upload and persistence** (metadata in PostgreSQL; object storage for files)
- **OCR text extraction (Phase 1)** — pluggable providers, structured page text + confidence
- **AI Payslip Parser (Phase 2A)** — local Ollama LLM turns OCR text into structured fields
- **Guest validation (Phases 3–7)** — review/edit → map to ValidationContext → Rule Engine → AI explain existing findings
- **Assistant orchestration** (LangGraph tools and guardrails; synthesis via an LLM provider when available)
- **PostgreSQL** for durable application data
- **Celery / Redis** for background tasks (for example OCR enqueue and batch jobs)
- **Object storage** (S3-compatible / MinIO in development)

## Compliance principle

**Pass/fail compliance outcomes are decided only by the deterministic rule engine.** AI assists with extraction, explanation, and orchestration — it never overrides validation results. AI never creates findings; it only explains existing deterministic findings.

## Extraction + validation pipeline

```
Document
  → OCR (generic text + confidence + metadata)
  → AI Parser (layout-independent structured payslip JSON)
  → Persist extraction (`document_extractions`)
  → Guest Review / Edit (new extraction version; edited_by_user=true)
  → Structured mapper → ValidationContext (synthetic guest employee; rule_profile=payroll)
  → Validation Engine (deterministic)
  → AI Explanation (existing findings only)
```

- OCR never feeds the Validation Engine directly.
- Guest path does **not** use `DemoValidationContextBuilder`.
- Missing / invalid money → unavailable → **Unable to verify** (no fake pass/fail).
- `vacation_balance` / `sick_leave_balance` stay additional fields only (not days used).

### Guest flow

```
Upload payslip
  → OCR + AI Parser + persist
  → Review / edit fields
  → Persist corrections as new extraction version (if any)
  → Continue → Rule Engine on mapped fields
  → Results checklist
```

### Mapping highlights

| Parser field | Validation field |
|--------------|------------------|
| `travel_expenses` | `transportation_allowance` |
| `regular_hours` | `work_hours` |
| `income_tax` | `tax_deducted` |

`extraction_connected=true` only when parser completed and the structured mapper ran. Payroll scope is `completed` only when core fields are usable; otherwise `partial` with localized unable reasons.

### Field edit persistence

- Edits create a **new** `document_extractions` row (incremented `extraction_version`).
- Original OCR (`ocr_result` / `raw_text`) is preserved.
- Edited fields: `edited_by_user=true`, `original_value` retained, `source_text` kept, confidence set to `1.0`.

### APIs

- `POST /api/v1/ocr/extract` — file → OCR pages/text
- `POST /api/v1/parser/payslip` — OCR JSON body → structured payslip fields
- `POST /api/v1/extraction/guest/payslip-extract` — upload → OCR → parser → persist → fields
- `POST /api/v1/extraction/guest/{document_id}/corrections` — persist review edits as a new version
- `POST /api/v1/validation/run` — guest validation from latest extraction (requires completed parser)

### OCR providers (Phase 1)

| Provider | Role |
|----------|------|
| **PaddleOCR** (default) | Primary for English and Arabic |
| **Tesseract** | Pluggable alternative; **automatic fallback for Hebrew (`he`)** |

Tesseract runs a conservative image preprocess before OCR (EXIF orientation, alpha flatten onto white, grayscale, long-edge upscale, mild contrast/sharpen). Tunables: `OCR_PREPROCESSING_*`. This does not change language mapping, provider selection, or Tesseract PSM/OEM.

OCR document language is independent of UI/assistant locale (`he|en|ar`). Mapping: `auto`/`he` → `heb+eng`, `en` → `eng`, `ar` → `ara+eng`. Arabic remains available for chat/UI and for OCR when `language=ar` is requested. Default `TESSERACT_LANG=heb+eng` (no Arabic in the auto pack).

Tesseract layout extraction (when used):
1. Preprocess image once (see above).
2. Run configurable PSM candidates (`OCR_TESSERACT_PSM_CANDIDATES`, default `3,4,6,11`) with explicit `--oem` / `--psm`.
3. Normalize words with real `(x, y, width, height)` boxes in **processed-image** coordinates.
4. Group words into lines (Tesseract block/par/line); line bbox is the union of word boxes.
5. Score candidates deterministically (confidence, word/line density, script fit, noise penalties — **not** payroll-field heuristics).
6. Select best candidate; expose line/word boxes; strategy summary is appended to `warnings`.

Confidence remains engine confidence (0–1). Quality score is selection-only and is not substituted for confidence. OCR output still requires the AI parser and user review — it is not a compliance decision.

### AI Payslip Parser (Phase 2A)

| Piece | Detail |
|-------|--------|
| Port | `PayslipParser` (`application/ports/payslip_parser.py`) |
| Implementation | `OllamaPayslipParser` |
| Prompt | `config/prompts/payslip_extractor/system.md` |
| Confidence | Per field, from model only; never invent; never hardcode 0.9 |

The Ollama prompt uses a **compact JSON instance template** (all required field names with `MISSING` stubs). It does **not** embed Pydantic `model_json_schema()` / `$ref` / `$defs` (models were copying schema stubs into the response).

Every field is:

```json
{
  "value": ...,
  "confidence": 0.0-1.0 | null,
  "source_text": "...",
  "status": "FOUND|MISSING|UNCERTAIN",
  "evidence_ids": ["p1_l7_w1"],
  "source_bbox": [x, y, w, h] | null,
  "source_page": 1 | null,
  "parser_method": "layout_llm",
  "warnings": [],
  "normalized_value": null
}
```

**Semantic validation** (after JSON parse, before coercion) rejects schema-copy output, missing required keys, numeric/`additional_fields` OCR keys, and all-MISSING responses when OCR evidence exists. One controlled retry runs for JSON/schema/semantic failures (`retry_used=true`, warning codes such as `parser_semantic_retry_used`).

**`additional_fields` keys** must be semantic labels (`meal_allowance`, `bonus`, …) — never amounts, IDs, or OCR fragments.

Document Lab OCR→Parser preserves line/page word geometry so layout evidence IDs (`p1_lN_wN`) reach the parser.

Layout-aware parsing is evidence-bound: non-null fields must cite OCR evidence IDs; deterministic post-validation rejects invented digits/names/bboxes. Confidence is capped by supporting OCR confidence. The parser does **not** repair OCR hallucinations and does **not** decide compliance — guest review remains required for uncertain fields.

**Remaining limitations:** quality still depends on the local Ollama model and OCR text; Hebrew payslips may need UNCERTAIN for ambiguous lines; Document Lab is a developer tool, not a production SLA.

### Install PaddleOCR (optional extra)

```bash
pip install -e ".[ocr-paddle]"
```

### Settings (parser)

- `PAYSLIP_PARSER_MODEL` — defaults to `OLLAMA_DEFAULT_MODEL` when empty
- `PAYSLIP_PARSER_TIMEOUT_SECONDS` (default 180)
- `PAYSLIP_PARSER_USE_JSON_FORMAT` (default true; local to this parser path)
- `PAYSLIP_PARSER_LAYOUT_ENABLED` (default true) — send OCR lines/words/bboxes to the LLM
- `PAYSLIP_PARSER_INCLUDE_WORDS` / `PAYSLIP_PARSER_MAX_LINES` / `PAYSLIP_PARSER_MAX_WORDS` / `PAYSLIP_PARSER_MAX_CONTEXT_CHARS`

### Database migrations (legacy)

Runtime persistence is DynamoDB. `DATABASE_URL` is optional and used only for Alembic / SQLAlchemy tooling (`alembic/env.py` prefers the env var over `alembic.ini`).

```powershell
docker compose --profile legacy-postgres up -d
docker compose --profile legacy-postgres run --rm migrate
```

### Current limitations

- Supporting documents (attendance / contract / ID) may be uploaded but extraction/cross-check is not connected yet → scope remains unable for those areas
- Historical comparison is not available in guest mode
- OCR upload Celery worker is still a stub (guest flow uses `/extraction/guest/payslip-extract`)
- Parser quality depends on the local Ollama model and OCR text quality
- `language=auto` OCR uses English Paddle model unless `language=he` is set
- Age / family / department-specific employee data stay missing for guests (no demo employee profile)

### Developer Document Lab

Developer-only API under `/api/v1/dev/document-lab/*` (404 outside dev/local or when `DEBUG` is false). Lists payslip fixtures from `tests/fixtures/documents/payslips/{valid,invalid}/` and runs existing OCR/parser/validation use cases step by step. See the root `README.md` → **Developer Document Lab**.

## Layout

Source lives under `src/payroll_copilot/` (domain, application, infrastructure, presentation). See the repository root `README.md` for run modes, configuration, and product-level documentation.
