# Payroll Copilot

**A payroll validation platform for Israeli labor law compliance, built around a deterministic rule engine.**

Payroll Copilot lets a guest upload a payslip and receive a structured validation report from a deterministic rule engine, and provides a source-bound payroll assistant that answers payroll/labor-law questions using approved local content only. Compliance pass/fail decisions are always made by the backend rule engine — never by AI.

> **Status: work in progress.** Guest validate-my-payslip, assistant chat, OCR/parser pipeline, accountant portal foundation, and **authenticated employee payslip upload with server-side identity/period comparison** are implemented. Several capabilities remain unconnected (vector RAG, contract/attendance/ID analysis, production Cognito for all routes, document viewer). See **[Current Status](#current-status)** and **[Current Limitations](#current-limitations)**. Nothing here fabricates validation results, OCR fields, or legal answers.

---

## Current Status

Honest snapshot of what exists today. "Partial" means real code runs but a downstream capability is deliberately not wired.

### Implemented (working today)
- **Deterministic validation engine** — rule evaluation, findings, confidence aggregation.
- **Validation persistence** — `POST /validation/run` and `GET /validation/runs/{id}` persist to PostgreSQL.
- **Document upload & persistence** — `POST /documents/upload`, `GET /documents/{id}` with server-side upload guardrails.
- **OCR text extraction (Phase 1)** — `POST /ocr/extract` returns page-level text + real OCR confidence via pluggable providers (PaddleOCR primary; Hebrew→Tesseract fallback). Includes preprocessing, language mapping, layout words/bboxes, and multi-PSM selection for Tesseract.
- **AI Payslip Parser (Phase 2A)** — `POST /parser/payslip` turns OCR JSON into per-field structured payslip data via local Ollama. Layout-aware / evidence-bound extraction with semantic validation and one controlled retry (no silent schema-copy → all-MISSING).
- **Guest extraction + validation (Phases 2B–7)** — extract → review/edit → validate on Continue → results; mapper builds a synthetic guest employee from parser fields (`rule_profile=payroll`); demo builder is not used on the guest path.
- **Employee payslip trust boundary (foundation)** — `users.employee_id` binding (Alembic `004`), `GET /employees/me`, authenticated `POST /extraction/employee/payslip-extract` + corrections, server-side identity/period comparison, duplicate-period `409`, owned `POST /validation/employee/run` that blocks National ID / period mismatches, Employee Portal upload/review UI that renders backend comparison only (no client-side National ID compare).
- **Public Guest Experience (frontend)** — landing page, Payroll Assistant chat (**safe Markdown rendering** for assistant answers), Validate-My-Payslip upload/review/results flow, enterprise validation report with honest scope.
- **LangGraph Payroll Assistant (backend)** — `POST /assistant/chat` with input/output guardrails, greeting handling, and keyword search over approved YAML legal rules.
- **Ollama integration** — host-first URL resolution with optional Docker fallback and graceful degradation when unavailable.
- **i18n foundation** — Hebrew / English / Arabic UI + RTL, locale-aware API responses and assistant answers (OCR language extraction not connected). **Payroll Accountant Portal UI** is fully covered under the existing i18next locale files (`accountant.*` + shared `common`/`portal` keys). Employee upload/payslip strings live under `employee.*` in `{en,he,ar}.json`.
- **Database schema & Alembic migrations**, **Docker Compose orchestration**, **guest JWT tokens** (`POST /auth/guest/session`), **dev employee JWT** (`POST /auth/dev/employee-session`, non-production).

### Partially implemented
- **Supporting document analysis** — attendance / contract / national ID can be uploaded, but extraction/cross-check is not connected yet (scope stays unable for those areas).
- **Assistant legal search** — keyword search over local YAML rules only; **no vector RAG** yet.
- **Role-based portals (employee/accountant/admin)** — accountant portal has a production-oriented foundation (employees, profile, rules, batch progress, audit, manual review). Employee payslip upload/review + My Payslips list are wired to the trusted employee APIs; other employee pages (attendance, contract, chat, validation history) remain largely unwired. Admin pages remain largely unwired.
- **Payroll Accountant Portal foundation** — employee master-data API (separate from auth users), extensible document-type + validation-module catalogs, employee profile with document collections / monthly expectations, rule browse/edit with versioning + audit + rollback, bulk PDF upload with stage progress store, national-ID match helper, low-confidence manual review queue, enterprise dialogs (no browser `alert`/`confirm`), batch navigation/`beforeunload` guards. Downstream OCR→parser→identify→validate wiring for each split slip is still incremental (stages marked skipped honestly).
- **Guest sessions** — guest JWT is issued and sent, but there is **no `guest_sessions` DB table** and guest routes do not yet enforce the token. **Employee extract/correct/`/me`/employee validation do enforce Bearer auth + binding.**
- **Production identity providers** — Cognito login path is scaffolded; local development uses the role selector + server-issued employee JWT.

### Planned but not built
- Vector RAG over legal rules and employment contracts.
- Contract / attendance / national-ID analysis.
- Historical payroll comparison and full employee trend history.
- Production auth (AWS Cognito) and full RBAC enforcement across all routes (including guest + accountant mutation routes).
- Batch bulk-PDF OCR/parser/identify/validate wiring (split + progress foundation exists; per-slip pipeline incomplete).
- MCP Kol Zchut legal sync automation.
- In-app document image/PDF viewer for extraction review.
- Absolute DB uniqueness constraint on employee+period payslips (current gate is application-level `find_payslip_for_period`).

---

## Business Overview

Payroll Copilot validates payroll against:

- Israeli labor law (YAML-configured, locally authoritative)
- Company policies
- Department-specific rules (lawyers, interns, accounting, etc.)
- Individual employment contracts (RAG-indexed)
- Historical payroll data

### Target Users

| Role | Capabilities |
|------|-------------|
| **Guest Employee** | Upload payslip without registration; receive validation, legal explanation, recommendations |
| **Registered Employee** | Upload payslips, attendance, ID, contract; historical insights and comparisons |
| **Payroll Accountant** | Bulk PDF upload (300+ slips); automatic split, identify, validate; aggregated reports |
| **Admin** | User management, legal rule approval, organization settings |

### Document Types

Payroll slips · Attendance reports · Employment agreements · Israeli ID · ID appendix · Employee master Excel

Employee Excel is imported into PostgreSQL using **header-name field detection** — never column positions.

---

## Architecture

Modular monolith with Clean Architecture and Domain-Driven Design.

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Presentation │ ──▶ │ Application  │ ──▶ │   Domain     │
│   (FastAPI)  │     │  (Use Cases) │     │ (Entities +  │
└──────────────┘     └──────┬───────┘     │    Rules)    │
                            │             └──────────────┘
                            ▼
                     ┌──────────────┐
                     │Infrastructure│
                     │ DB · S3 · AI │
                     └──────────────┘
```

**Key principle:** The Validation Engine is 100% deterministic. AI handles OCR, splitting, explanations, and email parsing — never pass/fail decisions.

See [docs/architecture.md](docs/architecture.md) for full design.

---

## Folder Structure

```
payroll-copilot/
├── README.md
├── .env.example
├── docker-compose.yml
├── docs/                       # Technical documentation
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── alembic/                # Database migrations
│   ├── config/
│   │   ├── rules/labor_law/    # YAML legal rules (source of truth)
│   │   ├── rules/departments/   # Department rule profiles
│   │   ├── prompts/             # AI agent system prompts
│   │   └── ai_models.yaml       # Model selection per agent
│   ├── mcp/                     # MCP server for legal rule sync
│   ├── src/payroll_copilot/
│   │   ├── domain/              # Entities, value objects, rule interfaces
│   │   ├── application/         # Use cases, ports, DTOs
│   │   ├── infrastructure/      # DB, storage, OCR, AI, Celery
│   │   └── presentation/        # FastAPI app, routes, middleware
│   └── tests/
└── frontend/                    # React + TypeScript + Vite
    └── src/
        ├── app/                 # Routing
        ├── auth/                # Dev auth + Cognito boundary
        ├── layouts/             # Role-based portal shells
        ├── pages/
        │   ├── public/          # Landing, login, signup
        │   ├── employee/        # Employee portal
        │   ├── accountant/      # Payroll accountant portal
        │   └── admin/           # Developer/admin portal
        ├── components/          # Shared UI
        ├── services/            # Typed API client stubs
        └── types/
```

---

## Implementation Status

See **[Current Status](#current-status)** above for the authoritative, honest breakdown of Implemented / Partial / Planned. The sections below describe the intended full design; anything not listed as Implemented or Partial in Current Status is a design target, not shipped behavior.

---

## Project Principles

1. **Deterministic validation** — The rule engine decides pass/fail. AI never overrides compliance outcomes.
2. **Extensible rule packs** — Legal, department, contract, and org rules live in backend configuration — not hardcoded in the frontend.
3. **AI assists, does not judge** — OCR, document understanding, RAG, and explanations support human review.
4. **Clean architecture** — Backend uses domain-driven design; frontend keeps auth and API boundaries separate from UI.
5. **Multi-tenant SaaS** — Organization isolation, RBAC, and audit trails are first-class concerns.

---

## Database

PostgreSQL 16 with pgvector for RAG embeddings.

Core entities: `organizations`, `users`, `employees`, `departments`, `documents`, `validation_runs`, `validation_findings`, `batch_jobs`, `attendance_records`, `rag_chunks`, `audit_logs`.

Multi-tenant isolation via `organization_id` + PostgreSQL Row-Level Security.

See [docs/database.md](docs/database.md).

---

## AI Components

| Component | Technology | Role |
|-----------|------------|------|
| Local LLM | Ollama | Default inference |
| Model Provider | Abstract port | Swappable: OpenAI, Claude, Gemini, Azure |
| OCR | Pluggable port | **PaddleOCR (default)** for en/ar; **Tesseract** for Hebrew fallback (H1, intentional) + optional full provider |
| Embeddings | pgvector | Contract/policy RAG |
| Agents | Specialized orchestrators | Splitter, extractor, explainer, email parser |
| Payroll Assistant | LangGraph + Ollama | Public guest chat orchestration (tools + guardrails) |

See [docs/ai-architecture.md](docs/ai-architecture.md).

---

## LangGraph Payroll Assistant

**Status: Frontend foundation + backend API implemented.** Guest chat on the public landing page calls `POST /api/v1/assistant/chat`. Assistant answers are shown with **safe Markdown rendering** in the UI (headings, lists, bold/italic, code, links) — the API response text is unchanged.

### OCR pipeline (Phase 1 highlights)

- **Preprocessing (Tesseract path)** — EXIF orientation, alpha flatten, grayscale, long-edge upscale, contrast/sharpen when enabled via settings.
- **Language mapping** — `auto`/`he` → `heb+eng`; `en` → `eng`; `ar` → `ara+eng` (actual pack reported in `language_effective`).
- **Layout-aware OCR** — word/line geometry with bounding boxes in processed-image coordinates; optional word payloads on API pages/lines.
- **Multi-PSM strategy** — Tesseract candidates (e.g. PSM 3/4/6/11) scored deterministically; best layout selected without payroll-field heuristics.

### AI Payslip Parser (Phase 2A highlights)

- **Evidence-based / layout-aware parsing** — OCR layout context with evidence IDs (`p1_lN`, `p1_lN_wN`); non-null fields must cite real evidence.
- **Compact instance-template prompting** — does **not** embed Pydantic `$ref`/`$defs` JSON Schema in the model prompt.
- **Semantic validation** — rejects schema-copy output, numeric OCR keys under `additional_fields`, fake evidence IDs, and all-MISSING responses when OCR evidence exists.
- **Controlled retry** — one retry on invalid JSON/schema/semantic failure; explicit warnings; no invented values.

### Principles

- The assistant is an **orchestrator only** — it does not decide legal compliance.
- **Deterministic validation** remains in the backend rule engine.
- Legal/payroll-rights answers must come from **approved local sources** (currently YAML legal rules; vector RAG planned).
- If no approved source is found, the assistant returns a **limited response** and does not invent law.
- AI may assist with explanations, document summaries, and tool orchestration only.

### Architecture

```
Guest chat → POST /assistant/chat → PayrollAssistantChatUseCase
                                 → LangGraph (input guardrail → tools → answer → output guardrail)
                                 → Ollama via ModelProvider (optional synthesis from tool context only)
```

**Backend layers:**
- `application/ports/assistant.py` — tool and runner ports
- `application/use_cases/payroll_assistant.py` — chat use case
- `infrastructure/ai/agents/payroll_assistant_graph.py` — LangGraph orchestration
- `infrastructure/ai/agents/payroll_assistant_tools.py` — safe tool adapters
- `infrastructure/ai/guardrails/payroll_assistant_guardrails.py` — input/tool/output guardrails

### Tools (initial)

| Tool | Purpose |
|------|---------|
| `search_approved_labor_law` | Keyword search over approved local YAML legal rules |
| `get_validation_report` | Read deterministic validation report by `validation_run_id` |
| `get_uploaded_document_summary` | Guest-scoped document metadata summaries |
| `explain_validation_finding` | Explain existing deterministic findings only |
| `fallback_safe_response` | Safe response when guardrails block or sources are insufficient |

### Guardrails

- **Input:** blocks prompt injection, secrets/source-code requests, off-topic content
- **Tool scope:** guest-only; only explicit `document_ids` / `validation_run_id`
- **RAG/source:** no approved hit → limited response with knowledge-base message
- **Output:** requires sources for legal claims; includes deterministic-validation disclaimer

### Environment

Uses existing Ollama settings (`MODEL_PROVIDER=ollama`). If Ollama is unavailable, the assistant falls back to template answers from approved tool context only.

### Planned follow-ups

- [ ] Vector RAG over legal rules and contracts
- [ ] Connect uploaded `document_ids` from guest upload flow to chat
- [ ] Connect `validation_run_id` from validation UI to explanations
- [ ] Production auth/RBAC with AWS Cognito
- [ ] Persistent chat sessions in PostgreSQL/Redis

---

## Validation Engine

Deterministic rule evaluation pipeline:

1. Build `ValidationContext` from payslip, employee, attendance, history
2. Select applicable rules via department profile
3. Evaluate each rule independently
4. Aggregate findings with confidence scores

See [docs/rule-engine.md](docs/rule-engine.md).

---

## Rule Engine

- **Legal rules:** YAML files in `config/rules/labor_law/`
- **Department rules:** Plugin classes + profile YAML
- **Contract rules:** RAG retrieval + deterministic evaluation
- **Org rules:** Database-configured parameters
- **Historical rules:** DB comparison (salary drift, anomalies)

New departments added without modifying core logic.

---

## RAG

Indexes employment agreements, company policies, internal procedures, and department agreements.

Queried by the Validation Engine when contract-specific rules are required. Tenant-scoped vector search in PostgreSQL.

---

## MCP (Legal Rule Sync)

MCP tools compare local YAML rules against [Kol Zchut](https://www.kolzchut.org.il/) and government sources.

- Local YAML remains authoritative
- Differences create approval proposals for accountants
- Rules update only after manual approval

---

## Batch Processing

Accountant uploads one PDF with 300+ payslips:

1. Celery job queued
2. Payslip Splitter Agent segments PDF
3. Parallel OCR and employee identification
4. Validation Engine runs per slip
5. Aggregated report: employee ID, department, issues, warnings, recommendations, confidence

Progress via `GET /api/v1/batch/jobs/{id}`.

---

## Employee Flow

```
Authenticated employee → Select payroll period → Upload payslip →
Shared OCR + parser (same pipeline as guest) → Server identity/period compare →
Review / correct → Confirm (blocked on National ID or period mismatch) →
Deterministic validation → Appears in My Payslips
```

### Working now
- **User ↔ employee binding** — nullable `users.employee_id` FK; employee-role users resolve to exactly one employee; accountants/admins are not treated as employee owners.
- **Trusted context** — `GET /api/v1/employees/me` returns safe display fields only (masked National ID, never plaintext).
- **Document lifecycle** — Original file → S3-compatible object storage (MinIO locally / Amazon S3 in production) → OCR/extraction (payslip) → employee review & correction → **explicit confirmation** → deterministic validation → immutable validation history → optional on-demand AI explanation (employee-only).
- **Storage keys** — Employee uploads use logical keys under `organizations/{org}/employees/{emp}/…` (persistent or `payroll/{year}/{month}/…`). File bytes are never stored in PostgreSQL.
- **Document Center** — `GET /employees/me/documents` + Employee Portal **My Documents** for National ID, ID appendix, and contract (with real file status; field extraction marked not connected where unsupported).
- **Extract + correct + confirm** — reuses guest OCR/parser/correction architecture; confirmation persists on `document_extractions`; validation is rejected until the latest extraction is confirmed.
- **Comparison policy** — National ID mismatch = critical block; name-only mismatch = warning; selected vs extracted period mismatch = block (no silent reassignment); low confidence = uncertain (never mismatch alone).
- **Duplicates** — same employee + selected year/month → HTTP `409 duplicate_payslip_period`; explicit `confirm_new_version=true` creates a new document and preserves the previous one.
- **Validation history** — Month detail returns immutable runs with `extraction_id` and an `outdated` flag when a newer extraction exists; reruns create new runs.
- **Employee AI explanations** — `POST /employees/me/validation-runs/{id}/findings/{id}/explanation` (owned findings only). AI never changes pass/fail; deterministic results remain usable if Ollama is down.
- **Employee Portal UI** — upload wizard with confirmation checkbox + gated validation; Document Center; My Payslips year/month dialog with review/confirmation/history/AI actions.

### Partial / known limitations
- **National ID** — review/foundation API and upload are implemented; automatic field OCR/parser is **not connected** (no fabricated fields).
- **Contract & attendance** — files upload and show status; structured extraction analysis is **not connected**.
- Other employee portal pages (dedicated attendance/contract viewers, chat) remain stubs beyond document center status.
- No in-app binary document viewer yet; payslip review is field-table based.
- Application-level duplicate gate (not a DB unique index).
- Dev employee session maps to a stable seeded employee (#5); production Cognito binding is not shipped.

Registered employees get persistent document rows scoped by organization + employee ownership. Guest flow remains available without employee binding.

---

## Payroll Accountant Flow

```
Upload bulk PDF → Background job → Split → Identify → Validate all →
Export report (PDF/Excel/JSON)
```

Email leave requests processed via n8n → Email Agent → Attendance DB (with human review for low confidence).

---

## Security

- Role-Based Access Control roles: guest, employee, accountant, admin
- JWT authentication + guest tokens; **employee extract/correct/`/me`/employee validation require Bearer auth and a bound `users.employee_id`**
- Encrypted National ID storage; API responses expose **masked** ID only; decrypted plaintext is used in-process for equality checks and is not logged
- Secure file storage with pre-signed URLs (design target; local object storage in current stack)
- Append-only audit logs for employee upload, mismatch, correction, duplicate-version confirm, and validation-blocked events
- Input validation, upload guardrails, tenant/organization isolation on employee-owned documents
- **Do not rely on frontend route protection alone** for employee document ownership

See [docs/security-and-deployment.md](docs/security-and-deployment.md).

---

## Internationalization

Supported UI languages: **Hebrew (`he`, RTL)**, **English (`en`, LTR)**, **Arabic (`ar`, RTL)**. Default locale: `he`.

### What is implemented

- Frontend language selector in the public header; selection persists in `localStorage`.
- Document `dir` / `lang` update automatically (`he`/`ar` → RTL, `en` → LTR).
- Public guest UI strings live in `frontend/src/i18n/locales/{he,en,ar}.json` (i18next + react-i18next).
- Frontend sends `Accept-Language` on API calls and includes `locale` on assistant and validation requests.
- Backend resolves locale from explicit `locale` field, then `Accept-Language`, then `DEFAULT_LOCALE`.
- Validation findings return stable machine codes (`code` / `message_key`) plus localized `message` and `explanation`.
- Assistant system prompt requires answers in the selected language; guardrails remain language-agnostic for safety.
- Document upload accepts `document_language` (`he` | `en` | `ar` | `auto`) metadata.

### Current limitations (honest)

- **OCR / parser quality depends on image quality and the local Ollama model.** Evidence validation rejects invented digits/names; fields may remain MISSING or UNCERTAIN when OCR or the model is weak.
- **Multilingual OCR text extraction is available via `POST /api/v1/ocr/extract`.** Hebrew uses Tesseract fallback (PaddleOCR has no official Hebrew model — intentional). Guest upload may still report `ocr_language_status: "not_connected"` on some async paths until fully wired.
- Auth portal pages (login/signup) are not fully translated yet.
- Some approved legal rule YAML text is bilingual (`he`/`en`); Arabic assistant answers may translate/summarize approved sources without inventing new legal claims.
- Public chat Markdown is presentation-only; the assistant may still return limited answers when no approved source matches.

---

## Installation

### Prerequisites

- Docker & Docker Compose v2.20+ (supports `service_completed_successfully`)
- Python 3.12+ (only for optional host-local backend development)
- Node.js 20+ (only for optional host-local frontend development)
- 16GB+ RAM recommended (Ollama)

### Primary startup (full stack)

Everything — Postgres, Redis, MinIO, migrations, API, worker, beat, and the Vite frontend — starts with one command.

```powershell
# One-time: create Docker env file (if .env does not exist)
copy .env.docker.example .env

# Start the full development stack
docker compose up --build
```

| URL | Purpose |
|-----|---------|
| http://localhost:3000 | Frontend (Vite hot reload in Docker) |
| http://localhost:8000/docs | Backend Swagger UI |
| http://localhost:8000/health | API health check |
| http://localhost:9001 | MinIO console |

Stop:

```powershell
docker compose down
# Never use `down -v` unless you intentionally want to wipe DB/volumes.
```

Ensure Ollama is running on your host with the required models, or start the optional Docker Ollama profile (see **Ollama** below).

### Startup flow

```
postgres (healthy)
  → redis (healthy)
  → minio (started)
  → migrate  (alembic upgrade head → exit 0)
  → api / worker / beat
  → frontend (waits for api healthy)
```

The `migrate` service:

- runs `alembic upgrade head`
- is **idempotent**
- never drops tables or recreates volumes
- must succeed before `api`, `worker`, and `beat` start

`DATABASE_URL` from `.env` is the **single source of truth** for FastAPI and Alembic (no hardcoded localhost inside containers).

### Environment files

| File | Role |
|------|------|
| `.env.docker.example` → `.env` | **Docker development** (primary). Compose `env_file`. Hosts: `postgres` / `redis` / `minio`. |
| `.env.example` | Same Docker defaults (alias of docker example). |
| `.env.local.example` → `.env.local` | **Host development** only (`@localhost`). Used when API runs on the host. |
| `frontend/.env.example` | Host-only Vite; Compose frontend sets `VITE_*` via service `environment`. |

Future production: inject the same keys via the orchestrator; do not commit secrets.

### Optional: host development (infra in Docker only)

Use this when you prefer host Python/Node tooling. Not required for day-to-day work.

```powershell
copy .env.local.example .env.local
copy frontend\.env.example frontend\.env.local

docker compose up -d postgres redis minio
docker compose run --rm migrate

# API (backend/)
cd backend
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn payroll_copilot.presentation.main:app --reload

# Worker / frontend in other terminals as needed
```

Host Redis/Celery/S3 resolution: when Docker hostnames are unreachable, `*_LOCAL_URL` fallbacks apply (see `service_resolver.py`). **`DATABASE_URL` is never auto-resolved** — use `@localhost` in `.env.local`.

### Frontend notes

Under `docker compose up --build`, the `frontend` service runs Vite with hot reload on port 3000 and sets:

- `VITE_API_BASE_URL=http://localhost:8000/api/v1` (browser → host-mapped API)
- `VITE_DEV_AUTH_ENABLED=true`

When `VITE_DEV_AUTH_ENABLED=true`, the login page shows a dev-only role selector:

| Role | Portal path | Dev identity |
|------|-------------|--------------|
| `employee` | `/employee` | Yehuda Shmulovitz |
| `payroll_accountant` | `/accountant` | David Levy |
| `developer_admin` | `/admin` | Yael Administrator |

Dev sessions are stored in `localStorage` only. Production auth will use AWS Cognito via `frontend/src/auth/authProvider.ts`.

### Role-Based UI

The frontend provides three portals after login:

**Employee Portal** — Payslip upload/review with trusted server comparison; **My Payslips** year/month history with month dialog (upload payslip/attendance, run validation, real findings). Dashboard, contract, chat, and validation-history pages still largely stubs. Default development employee is **Yehuda Shmulovitz** (יהודה שמולביץ), bound via `/employees/me`.

**Payroll Accountant Portal** — Dashboard, employee management (CRUD/disable/search), employee profile (document collections + monthly history), bulk payroll upload, batch monitor with pipeline stages, payroll rules (versioned edit/rollback), validation findings, manual review / approvals, audit logs.

**Developer/Admin Portal** — Rule packs, department rules, MCP legal sync, AI models, RAG management, system configuration, **Document Lab** (developer debugging).

Public landing page (`/`) includes guest validate + payroll chat.

### Developer Document Lab

Manual step-by-step debugger for OCR, parser, and validation. **Not for end users** — available only in the Developer/Admin portal (`/admin/document-lab`) and only when the API runs in a dev environment (`APP_ENV` is `development`, `dev`, or `local`, or `DEBUG=true`). In other environments the `/api/v1/dev/document-lab/*` routes return 404.

**Fixture location** (read-only, mounted into the API container in Docker):

```
backend/tests/fixtures/documents/payslips/valid/
backend/tests/fixtures/documents/payslips/invalid/
```

Expected sample files (add your own payslips for manual runs):

- `valid/payslips_valid_2026_06_multi.pdf`
- `valid/payslip_valid_2026_06_employee_001.png`
- `invalid/payslips_invalid_2026_07_multi.pdf`

**Add a new fixture:** place a PDF or image under `valid/` or `invalid/` (no subfolders). Restart is not required on host dev; in Docker the `./backend/tests/fixtures` volume is mounted read-only.

**Run manually:**

1. Start the stack (`docker compose up --build` or host API + `npm run dev`).
2. Log in as **Developer / Admin** (dev auth) and open **Document Lab** in the admin sidebar.
3. Select a fixture or upload a temporary file.
4. Use **Run OCR**, **Run Parser** (after OCR), **Run OCR → Parser**, or **Run OCR → Parser → Validation**.
5. Copy raw JSON/text from the output panels. Pipeline runs persist via the existing guest extraction + validation use cases (same as production wiring).

Fixture access is restricted to the known `valid/` and `invalid/` groups; path traversal (`..`) is rejected.
---

## Ollama

Payroll Copilot prefers an **Ollama instance already running on your host machine**. The Docker Ollama container is an **optional** fallback. Payroll Copilot never downloads or starts an Ollama instance for you.

### URL resolution order

When `MODEL_PROVIDER=ollama` and `OLLAMA_BASE_URL` is empty, the resolver **probes candidates in order** and uses the first that responds (implemented in `backend/src/payroll_copilot/infrastructure/config/ollama_resolver.py`):

1. **`OLLAMA_BASE_URL` set** → used exactly, no probing.
2. **`OLLAMA_LOCAL_URL`** (`http://127.0.0.1:11434`) → local host Ollama. This is what makes **local backend execution** work.
3. **`OLLAMA_HOST_URL`** (`http://host.docker.internal:11434`) → host gateway, used when running **inside Docker**.
4. **`OLLAMA_DOCKER_URL`** (`http://ollama:11434`) → optional Docker service, only reachable with `--profile docker-ollama`.

Because `127.0.0.1` is probed first, a local `uvicorn` process connects straight to host Ollama; inside a container `127.0.0.1` has no Ollama so the probe moves on to the host gateway, then the Docker service. The selected URL is logged at startup, e.g. `Ollama URL: local host Ollama reachable at http://127.0.0.1:11434`.

If **no** candidate responds, the resolver logs a warning and defaults to the local URL, and the assistant **degrades gracefully** (see below) rather than crashing.

### Graceful failure

If the resolved Ollama endpoint is unreachable at request time, the assistant does **not** return HTTP 500. The failure is logged and the assistant returns a controlled answer built only from approved tool context (or a limited/off-topic/greeting response, per the guardrails). Compliance results are unaffected because validation is deterministic and separate from the LLM.

### Environment variables

| Variable | Value | Purpose |
|----------|-------|---------|
| `OLLAMA_BASE_URL` | *(empty)* | Explicit override; empty enables auto-resolution |
| `OLLAMA_LOCAL_URL` | `http://127.0.0.1:11434` | Local host Ollama (probed first) |
| `OLLAMA_HOST_URL` | `http://host.docker.internal:11434` | Host Ollama from inside containers |
| `OLLAMA_DOCKER_URL` | `http://ollama:11434` | Optional Docker service fallback |
| `OLLAMA_AUTO_FALLBACK` | `true` | Probe candidates; if `false`, use the local URL deterministically |
| `OLLAMA_PROBE_TIMEOUT_SECONDS` | `2.0` | Per-candidate probe timeout |
| `OLLAMA_DEFAULT_MODEL` | `mistral-nemo:12b` | Chat model — set to a model you have pulled locally |

The chat model is read from settings/`.env` only (`OLLAMA_DEFAULT_MODEL`); it is not hardcoded in application code.

### Required model

Pull a model on the host and set it in `.env`:

```bash
ollama pull mistral-nemo:12b
ollama list            # confirm mistral-nemo:12b is present
```

```env
OLLAMA_DEFAULT_MODEL=mistral-nemo:12b
```

`api` and `worker` containers include `extra_hosts: host.docker.internal:host-gateway` for Linux compatibility.

### Docker Ollama fallback (optional)

Use only when host Ollama is not installed or not reachable:

```bash
docker compose --profile docker-ollama up -d
docker compose exec ollama ollama pull mistral-nemo:12b
docker compose exec ollama ollama pull nomic-embed-text
```

---

## Docker

### Architecture

```
payroll_net
├── postgres          # pgvector/pg16 — durable volume postgres_data
├── redis             # durable volume redis_data
├── minio             # durable volume minio_data
├── migrate           # one-shot alembic upgrade head (restart: "no")
├── api               # FastAPI :8000 (after migrate)
├── worker            # Celery worker (after migrate)
├── beat              # Celery beat (after migrate)
├── frontend          # Vite :3000 (after api healthy)
├── ollama            # profile: docker-ollama
└── n8n               # profile: automation
```

### Commands

```bash
docker compose up --build              # Full stack (primary)
docker compose up --build -d           # Detached
docker compose --profile docker-ollama up -d   # Optional Ollama container
docker compose --profile automation up -d      # Optional n8n
docker compose logs -f api migrate frontend
docker compose run --rm migrate        # Re-run migrations only
docker compose exec api alembic current
```

Migrations always use the same `DATABASE_URL` as the API (from `.env`). Do not rely on `alembic.ini` localhost inside containers.
---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL DSN — **single source of truth for API + Alembic**. Docker: `@postgres`. Host: `@localhost`. | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis connection (Docker hostname) | `redis://redis:6379/0` |
| `REDIS_LOCAL_URL` | Local fallback when `REDIS_URL` host is unreachable | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Celery broker / result store (Docker hostname) | `redis://redis:6379/1`, `/2` |
| `CELERY_BROKER_LOCAL_URL` / `CELERY_RESULT_BACKEND_LOCAL_URL` | Local fallbacks | `redis://localhost:6379/1`, `/2` |
| `S3_ENDPOINT` | Object storage endpoint (Docker hostname) | `http://minio:9000` |
| `S3_LOCAL_ENDPOINT` | Local fallback when `S3_ENDPOINT` host is unreachable | `http://localhost:9000` |
| `SERVICE_AUTO_FALLBACK` | Probe configured host, fall back to `*_LOCAL_URL` if unreachable | `true` |
| `SERVICE_PROBE_TIMEOUT_SECONDS` | Per-host TCP probe timeout for service resolution | `0.5` |
| `S3_ACCESS_KEY` | Storage access key | — |
| `S3_SECRET_KEY` | Storage secret key | — |
| `S3_BUCKET` | Bucket name | `payroll-copilot` |
| `OLLAMA_BASE_URL` | Ollama API (explicit override; empty = auto-resolve) | *(empty)* |
| `OLLAMA_LOCAL_URL` | Local host Ollama (probed first) | `http://127.0.0.1:11434` |
| `OLLAMA_HOST_URL` | Host Ollama URL probed from containers | `http://host.docker.internal:11434` |
| `OLLAMA_DOCKER_URL` | Optional Docker Ollama fallback URL | `http://ollama:11434` |
| `OLLAMA_AUTO_FALLBACK` | Probe candidates (local → host → docker) | `true` |
| `OLLAMA_DEFAULT_MODEL` | Chat model (must be pulled locally) | `mistral-nemo:12b` |
| `MODEL_PROVIDER` | AI provider | `ollama` |
| `JWT_SECRET_KEY` | JWT signing key | — |
| `ENCRYPTION_KEY` | AES key for PII | — |
| `DEFAULT_LOCALE` | Default language | `he` |
| `GUEST_SESSION_TTL_HOURS` | Guest token lifetime | `24` |

See `.env.example` for complete list.

---

## API

REST API at `/api/v1`. Full OpenAPI spec at `/docs`.

Key endpoints:
- `POST /auth/login` — Authentication (production path scaffold)
- `POST /auth/guest/session` — Guest JWT
- `POST /auth/dev/employee-session` — Dev-only employee JWT bound to seeded employee (blocked in production)
- `GET /employees/me` — Trusted employee context (masked National ID; `full_name` + `full_name_localized`)
- `GET /employees/me/documents` — Employee Document Center (persistent docs + monthly pointer)
- `GET /employees/me/documents/national-id/review` — National ID review foundation (`extraction_not_connected`)
- `GET /employees/me/payslips` — Employee-owned payslip list
- `GET /employees/me/payroll-months?year=` — Year overview (12 months, payslip/attendance/validation summaries)
- `GET /employees/me/payroll-months/{year}/{month}` — Month detail + extraction confirmation + validation history + findings
- `POST /employees/me/validation-runs/{validation_run_id}/findings/{finding_id}/explanation` — Employee-owned on-demand finding explanation
- `POST /documents/employee/upload` — Owned uploads (attendance/contract/national_id/id_appendix) with forced employee binding
- `POST /assistant/chat` — Public guest payroll assistant (LangGraph orchestration)
- `POST /documents/upload` — Document upload
- `POST /extraction/guest/payslip-extract` — Guest extract (unchanged)
- `POST /extraction/employee/payslip-extract` — Authenticated employee extract + `identity_check` / `period_check`
- `POST /extraction/employee/{document_id}/corrections` — Owned corrections + refreshed comparison
- `POST /extraction/employee/{document_id}/confirm` — Persist confirmation acknowledgement before validation
- `POST /validation/run` — Guest/general validation trigger
- `POST /validation/employee/run` — Owned validation (requires confirmed extraction)
- `POST /batch/payslips` — Bulk PDF processing
- `GET /compliance/diff-proposals` — MCP legal diffs

See [docs/api.md](docs/api.md).

---

## Testing

### Automated tests

```bash
cd backend
# Windows PowerShell: prefix with `$env:PYTHONPATH="src";`
PYTHONPATH=src pytest                    # All tests
PYTHONPATH=src pytest tests/unit         # Unit tests
PYTHONPATH=src pytest tests/integration  # Integration tests
ruff check src tests                     # Lint
mypy src                                 # Type check
```

Assistant + Ollama-resolver focused run (Windows PowerShell):

```powershell
cd backend
$env:PYTHONPATH="src"
pytest tests/unit/test_ollama_resolver.py tests/unit/test_payroll_assistant_guardrails.py tests/unit/test_payroll_assistant_use_case.py tests/integration/test_assistant_api.py -v
```

Employee trust-boundary unit tests (Windows PowerShell):

```powershell
cd backend
$env:PYTHONPATH="src"
pytest tests/unit/test_payslip_identity_comparison.py tests/unit/test_employee_payslip_policies.py -v
```

Frontend:

```powershell
cd frontend
npm test
npm run build
```

### Manual smoke tests

Assumes the API is running on `http://localhost:8000` and (for the assistant) host Ollama is running with `OLLAMA_DEFAULT_MODEL` pulled.

**Health**
```bash
curl http://localhost:8000/health           # {"status":"healthy"}
curl http://localhost:8000/ready            # DB connectivity
```

**Frontend**
```bash
cd frontend && npm install && npm run dev    # http://localhost:3000
```

**Assistant** (`POST /api/v1/assistant/chat`)
```bash
# Greeting → guardrail_status "passed"
curl -X POST http://localhost:8000/api/v1/assistant/chat -H "Content-Type: application/json" -d "{\"message\":\"hi\"}"
# Payroll question → answer from approved context (or clean degraded answer if Ollama is down)
curl -X POST http://localhost:8000/api/v1/assistant/chat -H "Content-Type: application/json" -d "{\"message\":\"How should overtime appear on a payslip?\"}"
# Off-topic → scoped response, HTTP 200 (never 500)
curl -X POST http://localhost:8000/api/v1/assistant/chat -H "Content-Type: application/json" -d "{\"message\":\"Who won the World Cup?\"}"
```

**Document upload** (`POST /api/v1/documents/upload`)
```bash
curl -X POST http://localhost:8000/api/v1/documents/upload -F "file=@payslip.pdf" -F "document_type=payslip"
# → { "document_id": "...", "status": "uploaded", "processing_job_id": "...", "background_status": "queued" }
```
If the Celery broker (Redis) is unavailable, the upload still succeeds and returns `"background_status": "not_queued"` with `"processing_job_id": null` — the document is persisted, only background processing was skipped.

**Validation** (`POST /api/v1/validation/run`, then fetch)
```bash
curl -X POST http://localhost:8000/api/v1/validation/run -H "Content-Type: application/json" -d "{\"document_id\":\"<id-from-upload>\"}"
curl http://localhost:8000/api/v1/validation/runs/<validation-run-id>
```
The validation response includes `validation_scope`, `uploaded_documents`, `validation_confidence`, and `findings`. Note that payroll rules run against the demo context builder (see Current Limitations), so scope for payroll rules is reported as `partial`.

---

## Current Limitations

These are intentional and surfaced honestly in the UI/API — nothing is faked:

- **OCR text extraction (Phase 1) is implemented** via `POST /api/v1/ocr/extract` (PDF/PNG/JPG/JPEG → pages + text + confidence + layout/bboxes). Preprocessing, language mapping, and multi-PSM Tesseract selection apply on the Tesseract path. Install Paddle with `pip install -e ".[ocr-paddle]"`.
- **AI Payslip Parser (Phase 2A) is implemented** via `POST /api/v1/parser/payslip` (OCR JSON → per-field `{value, confidence, source_text, status, evidence_ids, …}`). Layout-aware evidence validation, semantic rejection of schema-copy / invalid keys, one controlled retry; confidence never invented.
- **Guest extraction persistence (Phase 2B/2C)** — `POST /api/v1/extraction/guest/payslip-extract` orchestrates upload → OCR → parser → `document_extractions` row; guest Review shows real fields (Missing / unable to read / confidence unavailable — never invented).
- **Guest validation connected (Phases 3–7)** — Review/edit → `POST /extraction/guest/{id}/corrections` (new extraction version) → `POST /validation/run` maps structured fields to a synthetic guest context (`rule_profile=payroll`). Missing data → Unable to verify. AI explains existing findings only.
- **Employee trust boundary is connected for payslip upload/review** — binding migration `004`, `/employees/me`, employee extract/correct, server comparison, duplicate `409`, and `/validation/employee/run` gate. Frontend renders backend checks only.
- **Public chat Markdown rendering** — assistant answers are rendered as sanitized Markdown in the guest chat UI; response text from the API is unchanged.
- **OCR worker on document upload is still a stub.** The Celery `process_document_ocr` task remains a placeholder; guest and employee validate flows use the sync extraction endpoints instead.
- **DemoValidationContextBuilder remains in codebase for non-guest/dev use only** — it is not used on the guest validation path.
- **No real vector RAG yet.** The assistant uses keyword search over local YAML legal rules only.
- **Production Cognito / full RBAC not complete.** Dev role selector + guest JWT + **employee JWT for bound routes** exist; many accountant/guest routes still do not enforce auth.
- **Guest session DB persistence not completed.** Guest JWT is issued and sent, but there is no `guest_sessions` table and guest routes don't require the token.
- **Contract / attendance / national-ID analysis not connected.** Uploading these documents is supported on guest flows, but they are reported as `not_available` in the validation scope because analysis is not wired.
- **Historical comparison not available.** Always reported as `not_available`.
- **Batch bulk-PDF, MCP legal sync** are design targets, not shipped.
- **Hebrew OCR:** when `OCR_PROVIDER=paddleocr` (default), `language=he` transparently uses **Tesseract** and returns `engine=tesseract` plus a warning. This is intentional production-honest behavior — not a bug.
- **Parser model quality** — local Ollama (e.g. `mistral-nemo:12b`) may still leave fields MISSING after semantic retry; the pipeline prefers honest MISSING over invented values.
- **No payslip document viewer UI** — review is field-based; side-by-side page imaging is still planned.
- **Intended final product goal:** an end-to-end payroll compliance platform where employees and payroll accountants upload documents, the system securely extracts and matches data, deterministic rules validate compliance, and users receive traceable findings — **without AI making legal pass/fail decisions**.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Frontend shows `ERR_CONNECTION_REFUSED` calling the API | FastAPI is not running | Start it: `PYTHONPATH=src uvicorn payroll_copilot.presentation.main:app --reload` |
| `getaddrinfo failed` / `Error 11001 connecting to redis:6379` (or `minio`) | Local backend is using Docker hostnames | Set `REDIS_URL`/`CELERY_*`/`S3_ENDPOINT` to `localhost` (see Local Development), or rely on `*_LOCAL_URL` auto-fallback; ensure `docker compose up -d postgres redis minio` is running |
| Upload returns `"background_status": "not_queued"` | Celery broker (Redis) unreachable | Expected graceful degradation — the document is still persisted; start Redis + the worker to enable background processing |
| `getaddrinfo failed` for `postgres` | `DATABASE_URL` still points at the Docker hostname | Set `DATABASE_URL` to `...@localhost:5432/...` (Postgres is **not** auto-resolved) |
| Assistant returns "temporarily unavailable" / limited answers | Ollama not running or misconfigured | Run host Ollama (`ollama serve`), pull `OLLAMA_DEFAULT_MODEL`; see the **Ollama** section |
| `ModuleNotFoundError: No module named 'langgraph'` | Dependencies not installed into the active interpreter | `pip install -e ".[dev]"` in the venv you launch `uvicorn` with |

---

## Public Guest Experience

The public landing page (`/`) offers two actions, both wired to the backend:

| Feature | Status |
|---------|--------|
| **Landing page** | Implemented — two action cards (Payroll Assistant / Validate My Payslip) |
| **Payroll Assistant** | Implemented — `POST /assistant/chat`; approved-source answers, greeting handling, guardrails; hides assistant confidence from the UI |
| **Upload** | Implemented — client + server upload guardrails; payslip required, supporting docs optional |
| **Validation report** | Implemented — overall status, scope, uploaded documents, backend `validation_confidence`, findings with an Explain panel |
| **Honest scope limitations** | Implemented — scope shows `partial` / `not_available` for capabilities that are not connected; no invented results, OCR, RAG answers, historical comparison, or contract analysis |

Backend remains the source of truth for validation results and validation confidence; the frontend only displays values returned by the API.

---

## Future Roadmap

- [x] Monorepo structure (`backend/`, `frontend/`)
- [x] Frontend role-based portal foundation (React, TypeScript, Vite)
- [x] LangGraph Payroll Assistant foundation (public guest chat API + guardrails)
- [ ] Vector RAG for assistant legal rule search
- [ ] Frontend API integration (auth, documents, validation, batch)
- [ ] AWS Cognito production authentication
- [ ] RTL-aware UI (Hebrew, English, Arabic)
- [ ] SSO / SAML integration
- [ ] Real-time batch progress via WebSocket
- [ ] Advanced analytics dashboard for accountants
- [ ] Mobile app for employee self-service
- [ ] Integration with popular Israeli payroll systems (Hashavshevet, Priority)
- [ ] Automated Kol Zchut sync scheduling
- [ ] Multi-region deployment
- [ ] SOC 2 compliance certification
- [ ] GPU-accelerated OCR pipeline

---

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | System design and bounded contexts |
| [Database](docs/database.md) | Schema and RLS |
| [API](docs/api.md) | REST endpoint reference |
| [AI Architecture](docs/ai-architecture.md) | Agents, RAG, MCP |
| [Rule Engine](docs/rule-engine.md) | Deterministic validation |
| [Security & Deployment](docs/security-and-deployment.md) | Production hardening |

---

## License

Proprietary. All rights reserved.
