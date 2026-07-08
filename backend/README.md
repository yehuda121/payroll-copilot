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

### AI Payslip Parser (Phase 2A)

| Piece | Detail |
|-------|--------|
| Port | `PayslipParser` (`application/ports/payslip_parser.py`) |
| Implementation | `OllamaPayslipParser` |
| Prompt | `config/prompts/payslip_extractor/system.md` |
| Confidence | Per field, from model only; never invent; never hardcode 0.9 |

Every field is:

```json
{ "value": ..., "confidence": 0.0-1.0 | null, "source_text": "...", "status": "FOUND|MISSING|UNCERTAIN", "edited_by_user": false, "original_value": null }
```

### Install PaddleOCR (optional extra)

```bash
pip install -e ".[ocr-paddle]"
```

### Settings (parser)

- `PAYSLIP_PARSER_MODEL` — defaults to `OLLAMA_DEFAULT_MODEL` when empty
- `PAYSLIP_PARSER_TIMEOUT_SECONDS` (default 180)
- `PAYSLIP_PARSER_USE_JSON_FORMAT` (default true; local to this parser path)

### Database migrations

`DATABASE_URL` is shared by FastAPI and Alembic (`alembic/env.py` prefers the env var over `alembic.ini`).

In Docker, the one-shot `migrate` Compose service runs `alembic upgrade head` before `api` / `worker` / `beat` start. Do not use localhost inside containers.

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
