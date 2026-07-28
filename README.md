# Payroll Copilot

**Deterministic Israeli labor-law payroll validation, with AI for extraction, explanation, and source-bound assistance.**

Payroll Copilot is a multi-tenant platform that turns payslip documents into auditable compliance results. Humans review an editable Document Model before anything reaches the rule engine. **AI never decides pass/fail.**

> **Status:** Production-oriented modular monolith under active development. Guest, Employee, Accountant, and Admin surfaces are operational. Several supporting-document analyzers and ops integrations remain partial. See [Project status](#project-status).

---

## Table of contents

1. [Executive summary](#executive-summary)
2. [Design principles](#design-principles)
3. [Why These Decisions](#why-these-decisions)
4. [Architecture](#architecture)
5. [Document processing pipeline](#document-processing-pipeline)
6. [Domain model and terminology](#domain-model-and-terminology)
7. [AI engineering](#ai-engineering)
8. [AI Governance](#ai-governance)
9. [Portals](#portals)
10. [Analytics and observability](#analytics-and-observability)
11. [Persistence](#persistence)
12. [Security and tenancy](#security-and-tenancy)
13. [Jobs and integrations](#jobs-and-integrations)
14. [Repository layout](#repository-layout)
15. [Local development](#local-development)
16. [Configuration](#configuration)
17. [API and testing](#api-and-testing)
18. [Project status](#project-status)
19. [Documentation](#documentation)
20. [Troubleshooting](#troubleshooting)

---

## Executive summary

### Problem

Israeli payroll compliance depends on labor law, department profiles, and employment context. Today that work is mostly:

- Manual reading of PDF/image payslips
- Spreadsheet checks that do not version findings
- Tribal knowledge that does not scale across accountants or tenants
- AI chatbots that invent legal outcomes without evidence or audit trails

Mistakes are expensive, hard to reproduce, and difficult to defend in review.

### Why deterministic validation alone is insufficient

A rule engine can evaluate clean, structured payroll facts. It cannot:

- Recover text from scanned or image-heavy PDFs
- Reconstruct arbitrary payslip layouts into editable fields
- Explain findings in the user’s language
- Answer labor-law questions grounded in an approved corpus

Those gaps require AI **around** the rules — not instead of them.

### Why AI alone is insufficient

Unconstrained LLMs are a poor compliance engine:

- Non-deterministic pass/fail
- Hallucinated rules and invented line items
- No stable audit artifact
- No hard boundary between “what appeared on the slip” and “what the engine evaluated”

### What this system does

| Layer | Responsibility |
|-------|----------------|
| **OCR / extraction (AI-assisted)** | Reconstruct what appears on the document into a Document Model / Digital Payslip |
| **Human review** | Edit and confirm before canonicalization |
| **Canonical mapping (deterministic)** | Project confirmed fields into the rule-engine input model |
| **Validation (deterministic)** | YAML + Python rule packs decide outcomes and findings |
| **Explanation / assistant (AI)** | Explain findings and answer source-bound questions; never override results |

### Differentiation

1. **Document Model ≠ Canonical Model** — review edits the document reconstruction; the engine only sees a post-confirm projection.
2. **Confirm-before-validate** — identity/period gates can block confirmation; validation requires a confirmed extraction.
3. **Honest partiality** — missing or unverifiable fields stay `MISSING` / `partial` / `not_available` instead of invented values.
4. **Tenant-bound AI context** — employee chat context is derived from auth bindings on the server; browser-supplied IDs are not trusted as LLM context.
5. **Legal RAG with a hard source of truth** — version-aware retrieval over an approved labor-law index; YAML rule packs remain authoritative for validation.

Authoritative architecture detail: [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Design principles

These invariants are intentional product constraints, not style preferences.

| # | Principle | Implication |
|---|-----------|-------------|
| 1 | **Determinism over spectacle** | Compliance outcomes come only from the rule engine. |
| 2 | **Document-first extraction** | Reconstruct the slip completely; map to canonical later. |
| 3 | **Confirm before canonicalize** | Humans review the Document Model before Canonical Payroll Model mapping. |
| 4 | **Ports over vendors** | Cognito, Bedrock, DynamoDB, S3, OCR, and LLM providers sit behind interfaces. |
| 5 | **Access patterns over tables** | Single-table DynamoDB keyed by real query paths. |
| 6 | **Modular monolith first** | One deployable API with Clean Architecture layers; no premature service split. |
| 7 | **Tenant isolation always** | Org-scoped keys and application-layer authorization on every owned resource. |
| 8 | **Honest partiality** | Prefer `MISSING` / unable-to-verify over fabricated completeness. |
| 9 | **Audit sensitive mutations** | Append-only audit events for high-risk actions. |
| 10 | **Legal sync is proposals-only** | Sync never auto-approves rule changes; YAML remains validation SoT. |
| 11 | **Batch drafts stay invisible** | `publication_status=draft` is a hard Employee Portal visibility boundary. |
| 12 | **Leave domains stay separate** | `VacationRequest` and `SickLeaveRequest` do not share a generic leave entity. |

---

## Why These Decisions

- **Document Model ≠ Canonical Payroll Model.** Payslips are reconstructed as they appear so humans can review real evidence. The rule engine needs a stable schema. Separating the two prevents review edits and layout quirks from leaking into rule packs, and prevents schema-first filtering from silently dropping fields before confirmation.
- **Human confirmation before validation.** Identity and payroll-period trust are product gates, not model confidence scores. Confirmation makes the reviewed Document Model an explicit checkpoint; validation then runs only on a confirmed, mapped input.
- **AI for extraction and explanation; deterministic compliance.** OCR and heterogeneous layouts need probabilistic reconstruction. Findings need plain-language explanation. Pass/fail must remain repeatable, versioned, and independent of model temperature—so YAML + Python rules own outcomes.
- **Evidence-first, not schema-first.** Filling a fixed DTO from the LLM first drops line items the engine may need after human edit. Reconstruct evidence completely, then project to canonical after confirm.
- **YAML rule packs validate; Legal RAG retrieves.** Compliance SoT must be editable, reviewable, and proposal-gated. The vector index serves assistants for version-aware retrieval; it is not an alternate rule engine and never auto-approves legal changes.
- **Immutable validation runs over in-place updates.** Re-validation creates a new run so prior outcomes remain auditable. Sensitive mutations append audit events instead of rewriting history—required for dispute and review trails.
- **Modular monolith before microservices.** Clean Architecture boundaries already isolate domain, use cases, and adapters. Early service splits would multiply deploy, auth, and data-consistency cost before access patterns and team scale justify them.

---

## Architecture

### Shape

Modular monolith: FastAPI API + React SPA + Celery workers (Redis broker). Persistence is DynamoDB (business state) + S3/MinIO (document bytes). Identity is Cognito when configured, with a local dev role picker otherwise.

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Presentation │ ──▶ │ Application  │ ──▶ │   Domain     │
│   (FastAPI)  │     │  (Use Cases) │     │ (Entities +  │
└──────────────┘     └──────┬───────┘     │    Rules)    │
                            │             └──────────────┘
                            ▼
                     ┌──────────────┐
                     │Infrastructure│
                     │ DynamoDB · S3 · Cognito · OCR · AI · Redis · CloudWatch │
                     └──────────────┘
```

| Concern | Runtime choice |
|---------|----------------|
| API | FastAPI (`/api/v1`) |
| Frontend | React 19 + TypeScript + Vite |
| Primary DB | Amazon DynamoDB (single-table; DynamoDB Local in Compose) |
| Objects | Amazon S3 (MinIO locally) |
| Identity | Amazon Cognito (+ guest JWT; local `/auth/dev/*` sessions) |
| Workers | Celery + Redis |
| LLM | Capability-routed Ollama / OpenAI / Bedrock behind `ModelProvider` + telemetry |
| Legal vector index | ChromaDB (version-aware retriever; YAML keyword fallback) |
| i18n | Hebrew / English / Arabic (RTL-aware) |

**Note on production target vs local runtime:** [ARCHITECTURE.md](ARCHITECTURE.md) describes the AWS target (including SQS-style async). The **current Compose/runtime path** uses Celery + Redis. Do not assume SQS, API Gateway, or CloudFront are wired in local development.

### Component boundaries

| Component | Owns | Does not own |
|-----------|------|--------------|
| OCR adapters | Text / layout evidence | Compliance decisions |
| Payslip parser / Document Model | Structured reconstruction + confidence | Pass/fail |
| Confirmation use cases | Trust gates, versioned confirm state | Rule evaluation |
| Canonical mapper | Projection into engine input | UI field editing |
| `ValidationOrchestrator` | Findings, overall result, run persistence | LLM calls |
| Assistants / explainers | Grounded natural language | Changing stored findings |
| Analytics | On-demand rollups over existing SoT | Pipeline writes |
| AI observability | Tokens, cost, latency, reliability | Document quality KPIs |

---

## Document processing pipeline

### End-to-end payslip path (guest and employee)

Deterministic stages are marked **[D]**. AI-assisted stages are marked **[AI]**.

```
Upload [D]  (type/size guardrails)
    ↓
OCR [AI/D]  (embedded PDF text preferred; OCR when needed)
    ↓
Document Model / Digital Payslip extraction [AI]
    ↓
Human review & edit [D]
    ↓
Confirm extraction [D]  (identity / period gates)
    ↓
Canonical Payroll Model mapping [D]
    ↓
Deterministic validation [D]
    ↓
Optional AI explanation of findings [AI]
    ↓
Persistence [D]  (employee/accountant: DynamoDB + S3; guest: ephemeral)
```

Guest LangGraph node sequence (simplified):  
`input_guardrails` → `file_guardrails` → `ocr` → `extraction` → `human_review` → `deterministic_validation` → `ai_explanation` → `final_response` (plus RAG / explain-finding branches).

Employee UI timeline: **Upload → Extract → Review → Validate → Completed**.

### Why the split exists

| Stage | Why it is not collapsed into “one AI call” |
|-------|-------------------------------------------|
| OCR | Needs specialized engines and embedded-text shortcuts; language fallbacks (Hebrew → Tesseract) are operational, not prompt tricks. |
| Document Model | Layouts vary; evidence-first reconstruction must survive human edit without silently dropping fields that rules need later. |
| Confirm | Compliance and identity trust require an explicit server gate, not a model “I’m sure.” |
| Canonical map | Rules need a stable schema; dynamic slip keys must not leak into rule packs. |
| Validation | Must be repeatable, versioned, and independent of model temperature. |
| Explanation | Language layer only; findings already exist as structured artifacts. |

### Accountant batch pipeline

```
Queued → Split PDF pages → OCR/Extract per page → Match employee
      → Draft Digital Payslip + draft validation → Accountant review
      → Approve & Publish (employee-visible)
```

Matching: national ID first, employee number fallback. Failures are isolated per page. Progress is polled from Redis-backed job state. Drafts use `publication_status=draft` until publish.

### Extraction status fields (persistence)

| Field | Meaning |
|-------|---------|
| `ocr_status` | OCR lifecycle |
| `parser_status` | Document Model / parser lifecycle |
| `confirmation_status` | `review_required` \| `confirmed` \| `missing` |
| `overall_confidence` | Aggregated extraction confidence |
| `extraction_version` | Immutable version lineage for edits |

---

## Domain model and terminology

Use these terms consistently in code, UI, and LLM context.

| Term | Meaning |
|------|---------|
| **Organization** | Tenant boundary |
| **Employee** | Org-scoped worker record (number, employment/salary type, optional accountant assignment) |
| **Document** | Metadata + S3 object key + period + lifecycle (`publication_status`, processing stage) |
| **Document Model / Digital Payslip** | Evidence-bound reconstruction of what appears on the slip; human-editable SoT before confirm |
| **Canonical Payroll Model** | Post-confirm projection consumed by the rule engine only |
| **Validation run** | Immutable deterministic execution; re-validate creates a new run |
| **Validation finding** | Structured issue attached to a run |
| **User binding** | Cognito (or dev) subject → org / role / employee |
| **VacationRequest / SickLeaveRequest** | Separate leave domains (`VAC#` / `SICK#` key families) |
| **Legal rule pack (YAML)** | Authoritative source for validation |
| **Legal vector index** | Retrieval projection for assistants; not the validation SoT |

### Document types

`payslip` · `attendance` · `contract` · `national_id` · `id_appendix` · `employee_excel` · `bulk_payslip_pdf`

### Roles

| Domain role | Typical API / UI label | Portal |
|-------------|------------------------|--------|
| `guest` | guest JWT | Public landing |
| `employee` | employee | `/employee` |
| `accountant` | `payroll_accountant` | `/accountant` |
| `admin` | `developer_admin` | `/admin` |

---

## AI engineering

### Capability routing

Providers are selected **per capability** (e.g. `PAYSLIP_EXTRACTION_PROVIDER`, `ASSISTANT_PROVIDER`, RAG / embeddings) with fallback to `MODEL_PROVIDER`.

Supported providers in code: **Ollama**, **OpenAI**, **Amazon Bedrock**.

Every completion passes through `TelemetryModelProvider` (tokens, estimated cost, latency, success/error, retry/fallback flags, capability tags).

### Where AI is used — and why

| Capability | Why AI | Guardrail / boundary |
|------------|--------|----------------------|
| **OCR assist** | Scans and image PDFs are not structured tables | Embedded text preferred; Hebrew Tesseract fallback; OCR text guardrails |
| **Payslip / Document Model extraction** | Layouts are heterogeneous; schema-first parsers drop evidence | Semantic checks + controlled retry; prefer `MISSING` over invention; structured outputs via provider APIs |
| **Finding explanation** | Users need plain language over rule codes | Explains existing findings only; does not mutate outcomes |
| **Payroll assistant** | Labor-law Q&A at scale | Source-bound retrieval + guardrails; LangGraph orchestration; graceful degradation if LLM unreachable |
| **Employee chat context** | Personalized answers need employee facts | Server loads intent-required structured resources from **auth binding**; never trusts client-supplied employee selectors as LLM context |
| **Legal RAG** | Assistants need temporal, version-aware retrieval | Chroma index over approved legal chunks; YAML keyword fallback; proposals-only sync into the catalog |
| **Leave email extraction (n8n)** | Inbox text → structured leave draft | PC stores immutable `ai_extraction_original`; accountant corrections do not erase AI evidence |

### Evidence-first extraction

1. Recover evidence (embedded text or OCR).
2. Reconstruct dynamic fields/tables as they appear.
3. Persist as a versioned extraction with confidence.
4. Allow human edit.
5. Confirm.
6. Map to canonical **after** confirm.
7. Validate.

Schema-first “fill our DTO from the LLM” is rejected because it silently drops evidence the engine may need after review.

### Hallucination and grounding controls

- Structured completion schemas where providers support them
- Semantic validation on parser output with one controlled retry
- Explicit `MISSING` stubs instead of plausible fabrications
- Assistant answers grounded in approved legal corpus / findings — not free-form statute invention
- Legal knowledge sync creates **proposals**; admins approve; validation continues to read YAML SoT
- Optional legal-chunk reranker exists but is **disabled by default** (benchmark MRR regression); fail-open to vector order when enabled

### Confidence and review-before-persist

- Field / overall confidence is stored on extractions and surfaces in quality analytics.
- Employee and guest flows require **confirm** before validation.
- Accountant batch writes **drafts** until **Approve & Publish**.
- Leave inbound stores an immutable AI extraction snapshot for audit.

### What AI must not do

- Decide compliance pass/fail
- Auto-approve legal rule proposals
- Accept browser-supplied employee IDs as authoritative chat context
- Invent official government source URLs (registry slots remain `SOURCE_UNVERIFIED` until configured)

---

## AI Governance

AI Governance covers how the platform documents, reviews, and bounds AI behavior over time. It is separate from the deterministic rule engine and from live LLM ops dashboards.

### Scope today

| Capability | Status |
|------------|--------|
| **Prompt Engineering Center** | Implemented (Admin `/admin/prompt-engineering`) |
| **AI Telemetry** | Future (ops metrics exist under AI Observability; not linked into this governance catalog) |
| **RAG Evaluation** | Future under this governance umbrella (a separate Admin RAG Evaluation page already exists for quality benchmarks) |

Prompt Engineering manages **prompt evolution**. Runtime AI telemetry (tokens, cost, latency, retries) remains intentionally separate.

### Prompt Engineering Center

Admin surface under **AI Platform** at `/admin/prompt-engineering`.

The Prompt Engineering Center is an implemented AI governance capability. It maintains a versioned catalog of production prompts and records how each prompt evolved: problem, change, expected result, engineering notes, and evaluation status.

**Why prompt versioning exists.** Prompt wording drifts across releases. A versioned catalog makes those changes reviewable instead of tribal knowledge.

**Why engineering rationale is preserved.** Reviewers can see *why* an instruction changed, not only that a new version exists.

**Why reproducibility matters.** Documented versions support audits, incident review, and onboarding without reconstructing intent from chat logs or ad-hoc notes.

**Prompt governance vs runtime telemetry.** This catalog documents intended prompt evolution. Runtime AI telemetry (tokens, cost, latency, retries) answers operational questions and remains intentionally separate. The catalog does not store individual LLM requests or conversations. Governance metrics are shown as pending until AI Telemetry is linked.

**Evaluation history.** Per-prompt test-case outcomes (PASS / WARNING / FAIL) support governance review. They are not RAGAS runs and are not live pipeline scores.

**Auditability.** Immutable version rows create a durable trail of prompt decisions without claiming integrations that do not exist.
---

## Portals

### Public landing (`/`)

1. **Payroll Assistant** — `POST /assistant/chat` (LangGraph + guardrails + version-aware legal RAG with YAML fallback).
2. **Validate My Payslip** — document-first guest pipeline (upload → OCR → Document Model → review → confirm → canonical → validate → optional explanation).

Guest state is **ephemeral** (Redis shared store with in-memory fallback), not the employee DynamoDB ownership model.

### Employee portal (`/employee`)

Primary nav (code of truth): **Chat → Documents → Payslips**.

| Area | Behavior |
|------|----------|
| **Payroll AI Chat** | Labor-law RAG + backend-authorized employee context |
| **My Documents** | ID Card, ID Appendix, Employment Contract — Upload / Digital Form / Original Document |
| **My Payslips** | Monthly workspace: Upload → Digital Payslip → Validation → Original Document; **Salary Analytics** (net/gross by payroll period) |

**Digital Payslip** is the editable SoT after extraction. **Run Validation** saves dirty fields, confirms, then runs the rule engine. Re-validation creates a new immutable run; older runs remain for audit.

Attendance validation is out of scope on the Validation tab. Original Document is metadata + delete — no in-app binary viewer yet.

### Accountant portal (`/accountant`)

Nav: **Employees · Vacations · Sick Leaves · Bulk Upload · Analytics**.

- Opens employee workspaces via org-scoped selected-employee APIs (backend resolves by employee number inside the accountant’s org).
- **Bulk Upload:** split → extract → match → draft validate → review → publish.
- **Leave:** separate Vacation / Sick Leave domains; n8n owns IMAP + AI extract + send instruction; PC owns match, overlap/duplicate, review lifecycle, notifications. Prefer `POST /api/v1/integrations/email/inbound-leave/batch`. Details: [docs/vacation-email.md](docs/vacation-email.md).

### Admin portal (`/admin`)

Role: `developer_admin` / `UserRole.ADMIN`.

| Group | Surfaces |
|-------|----------|
| **Monitoring** | System Dashboard (AI ops KPIs + trends) |
| **Analytics** | Organization census; cross-org AI quality |
| **AI Platform** | AI Models comparison; Prompt Engineering Center (see [AI Governance](#ai-governance)) |
| **Knowledge** | Legal Knowledge; RAG Evaluation |
| **Document Processing (DEV)** | Developer Console / Document Lab (Vite DEV only) |

Census/quality analytics answer pipeline-quality questions from DynamoDB SoT. System Dashboard / AI Models answer LLM ops questions from telemetry + CloudWatch.

---

## Analytics and observability

### Business analytics (on-demand)

No aggregation warehouse. `AnalyticsService` derives metrics from documents, extractions, validation runs/findings, and bindings.

| Endpoint | Audience |
|----------|----------|
| `GET /analytics/employee/salary` | Bound employee |
| `GET /analytics/org/payroll` | Org accountant |
| `GET /analytics/org/quality` | Org accountant |
| `GET /analytics/admin/census` | Admin |
| `GET /analytics/admin/quality` | Admin |

Period grouping uses document `period_year` / `period_month` only (never upload timestamps). Contracts: [docs/analytics.md](docs/analytics.md).

**Quality metric definitions (existing SoT):**

| Metric | Source |
|--------|--------|
| Extraction success | Latest extraction `ocr_status` + `parser_status` both completed |
| OCR success/fail | Latest `ocr_status` |
| Validation success | Latest run `overall_result == pass` |
| Confidence | Extraction `overall_confidence`, else validation run |
| Manual review | Document outcome / confirmation review (not Redis match-queue depth) |

### AI observability

| Path | Role |
|------|------|
| Emit | Every routed LLM call → process-local aggregates + optional CloudWatch PutMetricData |
| `GET /admin/ai/dashboard` | Snapshot KPIs (process-local) |
| `GET /admin/ai/models/comparison` | Provider/model operational rows |
| `GET /admin/ai/history` | Trends via CloudWatch GetMetricData when available; else real process-local hourly buckets (never fabricated) |

Emit failures never break AI calls. Retry rates under-report when callers omit `AICallContext.retry_count`. `prompt_version` is counted locally when set; it is not a CloudWatch dimension today.

---

## Persistence

### DynamoDB (primary business database)

Single table per environment (default `PayrollCopilot`). Document **bytes** stay in S3.

| `entity_type` | Stores |
|---------------|--------|
| `organization` | Tenant |
| `department` | Unit + rule profile |
| `employee` | Master data |
| `user_binding` | Subject → org/role/employee |
| `document` | Metadata, S3 key, period, lifecycle |
| `extraction` | Versioned Document Model + confirmation |
| `validation_run` / `validation_finding` | Immutable engine results |
| `audit_event` | Sensitive-action trail |
| Leave + legal meta | `vacation_request` / `sick_leave_request`; `LEGAL#SYSTEM` sync/proposal/eval metadata |

GSIs support lookup by id (GSI1), employee number (GSI2), national-ID hash / dataset queries (GSI3).

PostgreSQL/Alembic remain as **optional legacy tooling** (`legacy-postgres` Compose profile), not the active runtime path.

### Object storage

| Environment | Objects | Metadata |
|-------------|---------|----------|
| Production | Private S3 (encryption, versioning, Block Public Access) | DynamoDB |
| Local | MinIO | DynamoDB Local |

Employee keys: `organizations/{org}/employees/{emp}/…`.

---

## Security and tenancy

- Cognito JWTs when configured; guest JWT for landing; local `/auth/dev/*` blocked when Cognito is set or `APP_ENV=production`
- Application-layer RBAC and org/employee binding checks (frontend routes are not sufficient)
- Encrypted national ID at rest; APIs return masked IDs
- Upload guardrails (type/size); OCR/assistant guardrails
- Tenant-prefixed DynamoDB/S3 keys
- Append-only audit for sensitive mutations
- SSRF-hardened legal source fetch (HTTPS allowlist, private IP block, size/timeouts)
- Production secret placeholder refusal (`production_guards`)

Some accountant/guest mutation routes still have **partial** RBAC coverage — treat as an active hardening area, not complete.

Module notes: [docs/security-and-deployment.md](docs/security-and-deployment.md) (may still mention legacy Postgres; prefer this README + ARCHITECTURE for persistence posture).

---

## Jobs and integrations

| Concern | Implementation |
|---------|----------------|
| Async work | Celery workers + beat (Redis) |
| Batch payslips | Worker pipeline; Redis job state; browser polls |
| Legal sync schedule | Beat hook; **disabled until official sources configured** (`LEGAL_SYNC_SCHEDULE_ENABLED=false`) |
| Leave email | Optional n8n Compose profile; batch inbound API |
| Email send | SES adapter; console fallback when unset |
| MCP | `backend/mcp/` legal sync tooling (compare/proposal foundation) |

---

## Repository layout

```
payroll-copilot/
├── README.md
├── ARCHITECTURE.md
├── .env.*.example
├── docker-compose.yml
├── docs/                          # Module docs (some lag DynamoDB migration)
├── backend/
│   ├── config/rules/labor_law/    # YAML SoT for validation
│   ├── config/prompts/
│   ├── config/ai_models.yaml
│   ├── mcp/
│   └── src/payroll_copilot/
│       ├── domain/
│       ├── application/           # Use cases, ports, validation, services
│       ├── infrastructure/        # DynamoDB, S3, Cognito, OCR, AI, Celery, RAG
│       └── presentation/          # FastAPI routes
└── frontend/
    └── src/
        ├── app/                   # Routing
        ├── auth/
        ├── layouts/portalConfig.ts
        ├── pages/{public,employee,accountant,admin}/
        ├── features/
        ├── services/
        └── i18n/locales/{en,he,ar}.json
```

---

## Local development

### Prerequisites

Docker Compose v2.20+ · optional Python 3.12+ / Node 20+ · 16GB+ RAM if using local Ollama

### Start

```powershell
copy .env.docker.example .env
docker compose up --build
```

| URL | Purpose |
|-----|---------|
| http://localhost:3000 | Frontend |
| http://localhost:8000/docs | OpenAPI |
| http://localhost:8000/health | Health |
| http://localhost:9001 | MinIO console |

Compose services: DynamoDB Local, Redis, MinIO, API, Celery worker/beat, frontend. Optional profiles: `legacy-postgres`, `docker-ollama`, `automation` (n8n).

### Frontend `node_modules` volume

Compose mounts named volume `frontend_node_modules`. After `package.json` / lockfile changes:

```powershell
docker compose down -v
docker compose up --build
```

### Dev auth

With `VITE_DEV_AUTH_ENABLED=true`: roles `employee` → `/employee`, `payroll_accountant` → `/accountant`, `developer_admin` → `/admin`.

### AI routing locally

Capability `*_PROVIDER` variables fall back to `MODEL_PROVIDER`. Examples commonly route extraction to OpenAI and chats/RAG to Ollama. Prefer host Ollama; optional `--profile docker-ollama`.

```bash
ollama pull mistral-nemo:12b
```

---

## Configuration

| Variable | Role |
|----------|------|
| `DYNAMODB_TABLE_NAME` / `DYNAMODB_ENDPOINT` | Single-table name; empty endpoint = AWS |
| `DYNAMODB_AUTO_CREATE_TABLE` | `true` locally; `false` in production |
| `S3_ENDPOINT` / `S3_BUCKET` / `S3_REGION` | Object storage |
| `COGNITO_USER_POOL_ID` / `COGNITO_APP_CLIENT_ID` | Auth |
| `MODEL_PROVIDER` / `*_PROVIDER` | Capability routing (`ollama` \| `openai` \| `bedrock`) |
| `OPENAI_API_KEY` / `BEDROCK_MODEL_ID` | Cloud LLM credentials |
| `OCR_PROVIDER` | Default `paddleocr` |
| `REDIS_URL` | Celery / cache / guest store |
| `JWT_SECRET_KEY` / `ENCRYPTION_KEY` | Guest JWT + PII |
| `CLOUDWATCH_ENABLED` / `CLOUDWATCH_METRICS_NAMESPACE` | AI metrics emit/read |
| `LEGAL_SYNC_SCHEDULE_ENABLED` | Scheduled legal sync (off until sources verified) |
| `LEGAL_RAG_RERANK_ENABLED` | Optional rerank (default `false`) |

Full lists: `.env.docker.example`, `.env.production.example`, `frontend/.env.example`.

---

## API and testing

REST under `/api/v1`. Interactive docs: `/docs`. Module reference: [docs/api.md](docs/api.md).

Selected areas: auth (login/refresh/guest/dev sessions), documents, extraction (guest + employee), validation, assistant, analytics, admin AI monitoring, batch, leave ingest, legal knowledge, RAG evaluation, Document Lab (dev).

```powershell
# Backend
cd backend
$env:PYTHONPATH="src"
pytest
ruff check src tests
mypy src

# Frontend
cd frontend
npm test
npm run build
```

Smoke: `GET /health`, guest chat, upload → extract → confirm → validate, accountant/admin analytics (auth), admin AI dashboard/history (auth).

---

## Project status

### Implemented

- Deterministic validation + DynamoDB runs/findings
- S3/MinIO uploads with DynamoDB metadata
- OCR + evidence-bound Document Model / Digital Payslip extraction
- Guest landing (assistant + validate-my-payslip)
- Employee Documents, Payslips workspace, Salary Analytics, Payroll AI Chat
- Accountant employees, leave domains, bulk pipeline, org analytics
- Admin System Dashboard, census, quality, AI Models, Prompt Engineering Center, Legal Knowledge, RAG Evaluation
- Cognito adapter + local dev sessions
- Version-aware legal Chroma RAG + YAML fallback; proposals-only legal sync
- RAG Evaluation (RAGAS adapter + temporal accuracy + `benchmark_v1`)
- AI telemetry + CloudWatch history with process-local fallback
- i18n (he / en / ar) + Docker Compose stack

### Partial / in progress

- Deep analysis for attendance / contract / national ID beyond forms/extract foundations
- Full RBAC on every accountant/guest mutation route
- SES delivery in all environments (console fallback common)
- Background Celery OCR on generic upload (interactive flows are sync)
- Prompt-version / retry-context completeness on all AI call sites
- Official watched legal URLs + scheduled sync (registry ready; schedule off)
- Live RAGAS numeric scores require embedding + judge credentials
- Guest durability beyond Redis/ephemeral store

### Not claimed (avoid README inflation)

- Claude / Gemini / Azure provider adapters (not in code)
- Postgres as primary runtime store
- SQS / Step Functions / CloudFront as the local Compose path
- Vector RAG over contracts/policies (labor-law index only)
- In-app binary document viewer
- Full historical payroll comparison product (beyond salary series + limited rules)

---

## Documentation

| Document | Use when |
|----------|----------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture SoT |
| [docs/analytics.md](docs/analytics.md) | Analytics contracts |
| [docs/rule-engine.md](docs/rule-engine.md) | Deterministic rules |
| [docs/legal-knowledge-and-rag.md](docs/legal-knowledge-and-rag.md) | Legal sync + Chroma RAG |
| [docs/legal-rag-rerank.md](docs/legal-rag-rerank.md) | Optional reranker |
| [docs/vacation-email.md](docs/vacation-email.md) | Leave ownership (n8n vs PC) |
| [docs/n8n-vacation-workflow.md](docs/n8n-vacation-workflow.md) | Gmail/n8n build guide |
| [docs/payroll-investigation-agent.md](docs/payroll-investigation-agent.md) | Investigation graph |
| [docs/api.md](docs/api.md) | API reference |
| [docs/ai-architecture.md](docs/ai-architecture.md) | AI notes — **verify against code** (provider registry may lag) |
| [docs/database.md](docs/database.md) | DB notes — contains legacy Postgres material |
| [docs/security-and-deployment.md](docs/security-and-deployment.md) | Security checklist — persistence posture may lag |
| [backend/README.md](backend/README.md) | Backend package notes |

**Trust hierarchy:** code → `ARCHITECTURE.md` → this README → specialized `docs/*` → treat older Postgres-centric docs as historical where they conflict.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Frontend cannot reach API | API down | `docker compose up` or start uvicorn |
| `getaddrinfo` for `redis` / `minio` / `dynamodb` on host | Docker DNS from host process | Use `.env.local` localhost URLs |
| New npm package missing in Docker frontend | Stale `frontend_node_modules` | `docker compose down -v` then `up --build` |
| Upload `background_status: not_queued` | Redis/Celery down | Document may still store; start worker |
| Assistant limited / unavailable | Ollama unreachable | Start host Ollama; pull configured model |
| Hebrew OCR uses Tesseract | Expected with PaddleOCR default | Intentional fallback |

---

## Internationalization

UI languages: **Hebrew (`he`, RTL)**, **English (`en`)**, **Arabic (`ar`, RTL)**. Default: `he`.

Locale packs: `frontend/src/i18n/locales/`. API accepts `Accept-Language` / explicit `locale` on relevant requests.
