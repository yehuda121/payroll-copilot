# Payroll Copilot

**A payroll validation platform for Israeli labor-law compliance, built around a deterministic rule engine.**

Payroll Copilot helps guests and employees upload payslips, reconstruct them as editable digital documents, and receive structured validation from a **deterministic backend rule engine**. AI assists with OCR, document reconstruction, explanations, and a source-bound payroll assistant — it never decides pass/fail.

> **Status: work in progress.** Guest landing, Employee monthly workspace, Accountant portal foundation, DynamoDB/S3 persistence, Cognito adapters, local Docker development, and developer AI monitoring (telemetry, dashboard, popular questions) are in place. Several capabilities remain partial or planned. See [Project status](#project-status).

---

## Table of contents

- [Business overview](#business-overview)
- [Architecture](#architecture)
- [Architecture decisions](#architecture-decisions)
- [Project structure](#project-structure)
- [Features](#features)
- [Employee Portal](#employee-portal)
- [Public Landing](#public-landing)
- [Accountant Portal](#accountant-portal)
- [AI, OCR, extraction, and validation](#ai-ocr-extraction-and-validation)
- [AWS](#aws)
- [DynamoDB](#dynamodb)
- [Storage](#storage)
- [Security](#security)
- [Docker and development setup](#docker-and-development-setup)
- [Configuration](#configuration)
- [API](#api)
- [Testing](#testing)
- [Project status](#project-status)
- [Documentation](#documentation)
- [Troubleshooting](#troubleshooting)

---

## Business overview

Payroll Copilot validates payroll against:

- Israeli labor law (YAML-configured, locally authoritative)
- Department-specific rule profiles (lawyers, interns, and similar)
- Company / organization parameters (where configured)
- Employment contracts and historical payroll (planned / partial)

### Target users

| Role | Capabilities today |
|------|-------------------|
| **Guest** | Upload a payslip without registration; review a Document Model; confirm; receive deterministic validation; chat with the Payroll Assistant |
| **Employee** | Authenticated monthly workspace: upload → extract → edit Digital Payslip → confirm → validate → history; Document Center for supporting files |
| **Payroll accountant** | Employee master data, profile, bulk upload UI, batch monitor, rules browse/edit, review queue, audit logs (pipeline wiring still incremental) |
| **Admin / developer** | AI monitoring dashboard, model comparison, Document Lab, rule-pack and config screens |

### Document types

Payslips · Attendance reports · Employment agreements · Israeli ID · ID appendix · Employee master Excel · Bulk payslip PDFs

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
                     │ DynamoDB · S3 · Cognito · OCR · AI │
                     └──────────────┘
```

**Key principle:** The validation engine is deterministic. AI handles OCR, document reconstruction, explanations, and assistant orchestration — never compliance outcomes.

| Concern | Choice |
|---------|--------|
| API | FastAPI (`/api/v1`) |
| Frontend | React + TypeScript + Vite |
| Primary DB | Amazon DynamoDB (single-table) |
| Objects | Amazon S3 (MinIO locally) |
| Identity | Amazon Cognito (dev role picker when Cognito unset) |
| LLM | Capability-routed OpenAI / Ollama / Bedrock behind `ModelProvider` + telemetry wrapper |
| Workers | Celery + Redis |
| i18n | Hebrew / English / Arabic (RTL-aware) |

Authoritative architecture detail: [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Architecture decisions

| Decision | Why |
|----------|-----|
| **DynamoDB single-table** | Access-pattern–driven keys and GSIs fit multi-tenant payroll reads (employee months, document/extraction lookup, validation history) without joining across many tables. One table per environment keeps ops simple while entity types remain explicit via `entity_type`. |
| **S3 for documents** | Payslip binaries are large, versioned, and rarely queried as rows. Object storage keeps DynamoDB items small and lets encryption, versioning, and Block Public Access sit at the bucket boundary. |
| **Cognito for authentication** | Managed identity (email auth, verification, JWTs) without owning password storage. Application code still owns org scope, employee binding, and role authorization after the token is verified. |
| **Deterministic validation** | Compliance pass/fail must be auditable and repeatable. AI extracts and explains; the rule engine alone decides outcomes against versioned YAML rule packs. |
| **Bedrock prepared, currently on hold** | AWS region and provider adapters were laid out for managed inference, but the active development/runtime path remains the local Ollama pipeline until the next implementation phase. |
| **Employee session in-memory cache** | Authenticated employee UI may reuse data already loaded in the current browser session (e.g. payroll month detail). The cache never fetches on its own, never persists to storage, clears on logout, and does not bypass backend authorization. |
| **Employee AI context boundary** | The authenticated Employee Chat inspects the frontend session inventory, then calls a dedicated employee-authorized endpoint. The backend derives the employee identity from authentication, loads only intent-required structured resources, sanitizes them, and appends that prepared context to the unchanged labor-law RAG context. Browser values and identifiers are never trusted as LLM context; Public Landing Chat remains on its existing endpoint. |

---

## Project structure

```
payroll-copilot/
├── README.md
├── ARCHITECTURE.md
├── .env.example / .env.docker.example / .env.local.example / .env.production.example
├── docker-compose.yml
├── docs/                          # Module docs (some still lag DynamoDB migration)
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── alembic/                   # Optional legacy PostgreSQL tooling only
│   ├── config/
│   │   ├── rules/labor_law/       # YAML legal rules (source of truth)
│   │   ├── rules/departments/
│   │   ├── prompts/
│   │   └── ai_models.yaml
│   ├── mcp/                       # Legal-rule sync tooling (foundation)
│   └── src/payroll_copilot/
│       ├── domain/
│       ├── application/           # Use cases, ports, services
│       ├── infrastructure/        # DynamoDB, S3, Cognito, OCR, AI, Celery
│       └── presentation/          # FastAPI routes
└── frontend/
    └── src/
        ├── app/                   # Routing
        ├── auth/                  # Cognito + dev auth
        ├── features/              # Guest landing, employee digital form, …
        ├── pages/                 # public / employee / accountant / admin
        ├── services/              # Typed API clients
        └── i18n/locales/          # en, he, ar
```

---

## Features

### Deterministic validation

- Rule evaluation, findings, confidence aggregation
- Persistence of validation runs and findings in DynamoDB
- Guest and employee validation entry points
- AI may explain findings; it does not change outcomes

### Document upload and object storage

- Guardrailed uploads (type/size)
- Bytes in S3 (or MinIO); metadata in DynamoDB
- Employee-owned keys under organization / employee prefixes

### OCR and payslip parsing

- Pluggable OCR (PaddleOCR default; Hebrew → Tesseract fallback)
- Embedded PDF text preferred when available
- Evidence-bound payslip / Document Model extraction via LLM
- Semantic validation and controlled retry (honest MISSING over invented values)

### Portals

- Public landing (assistant + validate-my-payslip)
- Employee monthly payslip workspace (primary employee flow)
- Accountant portal foundation
- Admin / Document Lab for developers
- Developer AI monitoring (usage footer, dashboard, model comparison)
- Global popular questions sidebar on landing chat (counters only; answers always live)

### Auth

- Guest short-lived JWT for landing
- Cognito login / refresh when configured
- Dev role selector (`VITE_DEV_AUTH_ENABLED=true`) for local portals
- Employee routes require Bearer auth + employee binding

---

## Employee Portal

Navigation (Employee Portal only):

1. **My Documents** (default home)
2. **My Payslips**
3. **Payroll AI Chat**

### My Documents

Workspace at `/employee/documents` with top-level document tabs:

- **ID Card**
- **ID Appendix**
- **Employment Contract**

Each document type uses the same inner structure as the payslip month workspace:

| Tab | Purpose |
|-----|---------|
| **Upload** | Select a file and run OCR/AI extraction (default language: Hebrew). Replacements require confirmation; the previous version remains active unless the new extraction and persistence succeed |
| **Digital Form** | ID Card and ID Appendix use fixed payroll fields (manual entry or extraction). Employment Contract keeps the dynamic extracted-field editor. All support explicit save |
| **Original Document** | Filename, upload date, type, status; delete original with confirmation. No embedded preview |

### My Payslips

Monthly list → workspace at `/employee/payslips/:year/:month`.

### End-to-end payslip workflow

```mermaid
flowchart TD
  A[Upload] --> B[OCR]
  B --> C[AI Extraction]
  C --> D[Digital Payslip]
  D --> E[Employee Review / Edit]
  E --> F[Confirm Extraction]
  F --> G[Validation]
  G --> H[Validation History]
```

Compact workspace timeline: **Upload → Extract → Review → Validate → Completed**.

### Payslip workspace tabs

| Tab | Purpose |
|-----|---------|
| **Upload** | Select/replace the payslip for the month; start extraction. Delete on this tab removes a *selected replacement*, not the confirmed original. |
| **Digital Payslip** | Editable **source of truth** after extraction. Field cards with typed previews, edit dialog, delete-with-confirm. Long values truncate in the grid. |
| **Validation** | Deterministic findings as compact cards; optional AI explanation per finding. Attendance validation is **out of scope** and not shown. |
| **Original Document** | Document management metadata (filename, upload date, type, status/size when available) and **Delete Original Document** with confirmation. No embedded PDF/image preview. |

### Digital Payslip as source of truth

- Extraction produces a structured field set stored as a versioned extraction.
- The Digital Payslip is what the employee reviews and edits.
- Edits are draft corrections until confirmation.
- **Run Validation** saves dirty fields, confirms the extraction, then runs the rule engine.
- After edits, previous validation runs are treated as **outdated** until re-validation.

### Extraction confirmation

- Confirmation is an explicit server-side step (`POST /extraction/employee/{document_id}/confirm`).
- National ID mismatch or payroll-period mismatch can **block** confirmation.
- Name-only mismatches are typically warnings, not hard blocks.
- Validation requires a confirmed extraction.

### Validation lifecycle

1. Confirm latest Digital Payslip (with acknowledgement).
2. `POST /validation/employee/run` creates a new validation run + findings in DynamoDB.
3. Results appear on the Validation tab and in month detail / history.
4. Re-validation after edits creates a **new** run; older runs remain for audit and may be flagged outdated.

### Other employee pages

| Page | Status |
|------|--------|
| My Documents workspace | Implemented (extract / persisted digital form / safe replacement / original document) |
| My Payslips / month workspace | Implemented |
| Payroll AI Chat | Implemented (authenticated endpoint; labor-law RAG + backend-authorized structured employee context; no document embeddings) |
| Attendance & Employment Contract nav items | Removed from Employee navigation (legacy routes redirect to My Documents) |

---

## Public Landing

Public `/` offers:

1. **Payroll Assistant** — `POST /assistant/chat` (LangGraph + guardrails + keyword search over approved YAML rules; safe Markdown rendering in UI).
2. **Validate My Payslip** — document-first guest flow:

```
Upload payslip
        ↓
OCR (embedded text first; OCR when needed)
        ↓
Complete Document Model (dynamic fields / tables)
        ↓
User review (edit / add / delete optional)
        ↓
Confirm → Canonical Payroll Model mapping
        ↓
Deterministic validation
        ↓
Optional AI explanation of findings
```

| Layer | Role |
|-------|------|
| **Document Model** | Source of truth for guest review — dynamic keys/values from *this* slip |
| **Canonical Payroll Model** | Built after confirmation for the rule engine only |

Guest extraction/session state is **ephemeral** (in-process TTL store), not the employee DynamoDB ownership model.

---

## Accountant Portal

Primary navigation under `/accountant`:

1. **Employees** — organization-scoped search and employee master data
2. **Bulk Upload** — persistent two-tab upload and incremental extracted-employee workspace

Opening an employee reuses the Employee Portal Documents, Payslips, monthly
workspace, validation, Digital Payslip, Original Document, and Payroll AI Chat
components. The frontend injects an accountant-selected workspace API; the
backend always resolves that employee by employee number inside the
authenticated accountant's organization before any read, edit, validation, or
AI context operation.

Bulk batch state lives above routes, so progress, results, filters, and scroll
position survive tab changes and employee-workspace navigation. Redis-backed
job state allows processing to continue without an open browser. The worker
splits payroll packages into one independent payslip document per page, then
processes each page sequentially through the shared OCR/parser, Digital Payslip
persistence, employee matching, and deterministic validation use cases.
National ID matching runs first, with employee number as a fallback. Every
split PDF, OCR result, extraction version, validation run, review state, and
processing correlation is persisted before the worker starts the next page.

Batch payslips are accountant-review drafts. A provisional employee match lets
the accountant reuse the existing Digital Payslip, Validation, Original
Document, and Payroll AI Chat workspace, but `publication_status=draft` is a
hard Employee Portal visibility boundary. Corrections create extraction
versions; every revalidation creates another immutable validation run displayed
in validation history. Only **Approve & Publish**, after the current extraction
has been confirmed and validated, changes the document to employee-visible.

Legacy accountant pages (rules, findings, approvals, audit, batch monitor) remain
routable but are intentionally not in the Phase 1 primary navigation.

One payslip failure is isolated to that item and does not stop the batch.
Unknown-employee resolution can correct the extracted National ID or attach a
selected employee, then resumes the same persisted draft without repeating OCR.
Progress currently reaches the browser by polling Redis-backed job state; the UI
contract does not depend on polling and can later move to push events.

---

## AI, OCR, extraction, and validation

### Model providers

| Provider | Status |
|----------|--------|
| **Ollama** | Supported — local / Docker development |
| **OpenAI** | Supported — cloud chat/embeddings when configured |
| **Amazon Bedrock** | Supported — managed inference when configured |

Providers are selected per AI capability (`PAYSLIP_EXTRACTION_PROVIDER`, `ASSISTANT_PROVIDER`, …) with fallback to `MODEL_PROVIDER`. Every completion passes through a **telemetry wrapper** that normalizes prompt/completion/total tokens, estimates cost, measures latency, and records retry/fallback flags for the developer UI.

### AI monitoring (developer)

| Surface | What it shows |
|---------|----------------|
| Conversation usage footer | Provider, model, tokens, estimated cost, latency, retry, fallback under each Q→A |
| `/admin` System Dashboard | Total tokens, tokens by provider/model, cost, average latency, error/retry/fallback rates |
| `/admin/ai-models` | Operational model comparison (requests, latency, tokens, cost, success rate) |
| Landing popular questions | Top 10 global questions by ask count (no answer cache; click re-asks the LLM) |

Aggregates for the dashboard and comparison page are process-local counters plus optional CloudWatch metric emission (`CLOUDWATCH_ENABLED`). **AI call event history is not stored in DynamoDB.** Popular questions store only normalized text, display text, counter, and last-asked time.

### OCR

- Port + factory; default `OCR_PROVIDER=paddleocr`
- Hebrew: intentional Tesseract fallback (PaddleOCR has no official Hebrew model)
- Preprocessing, language mapping, layout words/bboxes, multi-PSM Tesseract selection
- Guest/employee interactive flows use sync extraction endpoints (background Celery OCR on generic upload remains limited)

### Extraction

- Evidence-bound parsing with semantic checks and one controlled retry
- Guest: complete Document Model → confirm → canonical mapping
- Employee: owned extract → Digital Payslip → confirm → validate
- Corrections create new extraction versions

### Validation

- Deterministic Python rule engine + YAML labor-law packs
- Findings and confidence from backend only
- Scope honestly reports `partial` / `not_available` for unwired areas (contract, attendance analysis, historical comparison, vector RAG)

### Assistant

- Orchestrator only; source-bound answers from approved YAML
- No vector RAG yet
- Graceful degradation if the LLM is unreachable
- Optional usage footer on chat responses (same contract for all providers)
- Global popular-question counters for the landing sidebar

---

## AWS

### Infrastructure-first approach

AWS foundations were prepared **before** full application cutover: region, private storage, identity, and IAM for local/dev access. The application then integrated against those boundaries (DynamoDB adapters, S3 storage, Cognito auth).

**Region:** `us-east-1` — selected so future Amazon Bedrock integration can use models available in that region, alongside the rest of the AWS footprint.

### AWS services

| Service | Purpose | Current status |
|---------|---------|----------------|
| **Amazon Cognito** | User Pool authentication (email), JWT verification | In use when `COGNITO_*` is configured; local/dev may use the role picker |
| **Amazon DynamoDB** | Primary business database (single-table) | In use (DynamoDB Local in Compose) |
| **Amazon S3** | Private document object storage | In use (MinIO locally) |
| **IAM** | Least-privilege roles; development user / access keys for local AWS access | In use |
| **Amazon Bedrock** | Managed LLM inference | In use when a capability routes to `bedrock` |
| **Amazon SES** | Outbound email | Adapter present; console fallback when unset |
| **CloudWatch** | Logs + optional AI custom metrics | Configured; AI telemetry emits metrics when `CLOUDWATCH_ENABLED=true` |

### Storage posture (S3)

- Private bucket
- Block Public Access
- Server-side encryption
- Versioning enabled (production bucket configuration)

### Identity posture (Cognito)

- Cognito User Pool for production authentication
- Email-based sign-in / verification policies on the pool
- **Business roles** (employee, payroll accountant, admin) are enforced in the **application layer** after identity is established (groups/claims are mapped; fine-grained org/employee binding is app-owned)

### Local development credentials

- IAM development user + AWS access keys may be used to call real AWS APIs from a developer machine when not using Local/MinIO substitutes
- Docker Compose defaults to DynamoDB Local + MinIO so day-to-day work does not require live AWS

---

## DynamoDB

**Primary runtime database.** One application table per environment (default name `PayrollCopilot`).

PostgreSQL / Alembic remain in the repo only as **optional legacy tooling** (`docker compose --profile legacy-postgres`). They are not part of the active runtime path.

### Single-table design

- Every item has `PK` and `SK` (plus `entity_type`, and usually `organization_id` / timestamps)
- Access patterns drive key design
- Sparse GSIs for alternate lookups
- Document **bytes** stay in S3; DynamoDB stores metadata and structured business state

### Global Secondary Indexes

| Index | Partition Key | Sort Key |
| ----- | ------------- | -------- |
| GSI1 | GSI1PK | GSI1SK |
| GSI2 | GSI2PK | GSI2SK |
| GSI3 | GSI3PK | GSI3SK |

**Typical usage in code today:**

| Index | Examples |
|-------|----------|
| **GSI1** | Lookup by document / extraction / validation-run / employee / user / department id |
| **GSI2** | Employee number within an organization |
| **GSI3** | National ID hash within an organization; dataset-scoped document/audit queries |

### Entity types currently stored

| Entity | `entity_type` | What it stores |
|--------|---------------|----------------|
| **Organization** | `organization` | Tenant metadata |
| **Department** | `department` | Org unit + rule profile |
| **Employee** | `employee` | Employee master data |
| **User binding** | `user_binding` | Auth subject → org / role / employee |
| **Document** | `document` | File metadata, S3 key, period, lifecycle; month workspace pointers live here (no separate workspace entity) |
| **Extraction** | `extraction` | Versioned Digital Payslip fields + confirmation state |
| **Validation run** | `validation_run` | One deterministic rule-engine execution |
| **Validation finding** | `validation_finding` | Findings belonging to a run |
| **Audit log** | `audit_event` | Sensitive-action audit trail |

Also present for seeding/tooling: `dataset_employee`.

### Access patterns (summary)

| Pattern | Approach |
|---------|----------|
| List employee documents / months | Query `PK = ORG#…#EMP#…`, `SK begins_with DOC#` |
| Get document / extraction / run by id | GSI1 |
| Resolve user binding | `USER#…` under org + GSI1 |
| Find employee by number / national ID | GSI2 / GSI3 |
| Validation history | Query `VALRUN#` under employee partition |
| Org audit | Query `AUDIT#` under org |

Guest landing sessions use an **in-process ephemeral store**, not durable DynamoDB guest items (by design today).

Deeper design notes: [ARCHITECTURE.md](ARCHITECTURE.md) § DynamoDB. Module doc [docs/database.md](docs/database.md) still contains legacy PostgreSQL material and should be treated carefully until refreshed.

---

## Storage

| Environment | Objects | Metadata |
|-------------|---------|----------|
| Production | Amazon S3 | DynamoDB |
| Docker / local | MinIO (`S3_ENDPOINT`) | DynamoDB Local |

Employee uploads use logical keys under `organizations/{org}/employees/{emp}/…` (including period paths for payslips). File bytes are never stored in the database.

---

## Security

- Cognito JWTs when configured; guest JWT for landing; employee routes require Bearer + binding
- Application-layer RBAC and organization scoping (Cognito groups alone are insufficient)
- Encrypted National ID at rest; API returns masked ID only
- Upload guardrails; tenant isolation on employee-owned documents
- Append-only audit events for sensitive employee/accountant actions
- Do not rely on frontend route protection alone for ownership checks

See [docs/security-and-deployment.md](docs/security-and-deployment.md).

---

## Docker and development setup

### Prerequisites

- Docker & Docker Compose v2.20+
- Optional host tooling: Python 3.12+, Node.js 20+
- 16GB+ RAM recommended when using local Ollama

### Primary startup

```powershell
copy .env.docker.example .env
docker compose up --build
```

| URL | Purpose |
|-----|---------|
| http://localhost:3000 | Frontend (Vite hot reload) |
| http://localhost:8000/docs | OpenAPI / Swagger |
| http://localhost:8000/health | API health |
| http://localhost:9001 | MinIO console |

### Compose architecture

```
payroll_net
├── dynamodb          # DynamoDB Local (primary persistence)
├── redis             # Celery broker / cache
├── minio             # S3-compatible object store
├── api               # FastAPI :8000
├── worker            # Celery worker
├── beat              # Celery beat
├── frontend          # Vite :3000
├── postgres          # profile: legacy-postgres (optional)
├── migrate           # profile: legacy-postgres
├── ollama            # profile: docker-ollama (optional local LLM)
└── n8n               # profile: automation (optional)
```

Startup order: Redis healthy + DynamoDB/MinIO up → API / worker / beat → frontend (waits for API healthy).

### Important: frontend `node_modules` volume

The Compose `frontend` service mounts a **named volume** `frontend_node_modules` over `/app/node_modules`.

If `frontend/package.json` or `frontend/package-lock.json` change (for example after adding an npm package):

```powershell
docker compose down -v
docker compose up --build
```

**Why:** recreating containers **without** removing volumes keeps the old `node_modules` volume. New packages will not appear inside the container until that volume is recreated. Use `down -v` when dependencies change; avoid casual `-v` otherwise (it also wipes Redis/MinIO/Ollama data volumes).

### Environment files

| File | Role |
|------|------|
| `.env.docker.example` → `.env` | Docker development (DynamoDB Local, MinIO, Ollama) |
| `.env.local.example` → `.env.local` | Host-local API against localhost infra |
| `.env.production.example` / `.env.example` | AWS-oriented defaults (S3, DynamoDB, Cognito; Bedrock keys reserved for a later phase) |
| `frontend/.env.example` | Vite; set `VITE_DEV_AUTH_ENABLED=false` for Cognito UI |

### Dev auth roles

When `VITE_DEV_AUTH_ENABLED=true` (Compose frontend default):

| Role | Portal |
|------|--------|
| `employee` | `/employee` |
| `payroll_accountant` | `/accountant` |
| `developer_admin` | `/admin` |

### Optional host development

```powershell
docker compose up -d redis dynamodb minio
# then run uvicorn / celery / npm on the host against localhost endpoints
```

### AI provider routing

- Each AI capability selects `ollama`, `openai`, or `bedrock` independently.
- Capability variables fall back to legacy `MODEL_PROVIDER` when omitted.
- The supplied examples route extraction to OpenAI GPT-5 and chats/RAG to Ollama.
- Prefer host Ollama; optional `--profile docker-ollama`
- URL resolution probes local → host gateway → Docker service (see `ollama_resolver.py`)

```bash
ollama pull mistral-nemo:12b
```

### Developer Document Lab

Admin-only debugger (`/admin/document-lab`) for OCR → parser → validation on fixtures. Enabled only when `APP_ENV` is development-like or `DEBUG=true`.

### Developer AI monitoring

- System Dashboard (`/admin`) — token/cost/latency/reliability KPIs for the API process
- AI Models (`/admin/ai-models`) — operational comparison table
- APIs: `GET /admin/ai/dashboard`, `GET /admin/ai/models/comparison` (developer admin role)
- Popular questions: `GET /assistant/popular-questions`

---

## Configuration

| Variable | Description |
|----------|-------------|
| `AWS_REGION` | Shared region hint (`us-east-1`) |
| `DYNAMODB_TABLE_NAME` | Single-table name (`PayrollCopilot`) |
| `DYNAMODB_ENDPOINT` | Empty = AWS; set for DynamoDB Local |
| `DYNAMODB_AUTO_CREATE_TABLE` | `true` locally; `false` in production |
| `S3_ENDPOINT` / `S3_BUCKET` / `S3_REGION` | Object storage |
| `COGNITO_USER_POOL_ID` / `COGNITO_APP_CLIENT_ID` | Cognito auth |
| `MODEL_PROVIDER` | Backward-compatible fallback provider |
| `*_PROVIDER` | Capability route, e.g. `PAYSLIP_EXTRACTION_PROVIDER=openai` |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | OpenAI credentials and default chat model |
| `BEDROCK_MODEL_ID` | Bedrock model used when a capability routes to Bedrock |
| `OCR_PROVIDER` | `paddleocr` (default) or tesseract path |
| `REDIS_URL` | Celery / cache |
| `JWT_SECRET_KEY` | Guest JWT signing |
| `ENCRYPTION_KEY` | PII encryption |
| `DEFAULT_LOCALE` | `he` |
| `DATABASE_URL` | Optional legacy Postgres only |

Full lists: `.env.production.example`, `.env.docker.example`.

---

## API

REST under `/api/v1`. Interactive docs: `/docs`.

Selected endpoints:

| Area | Endpoints |
|------|-----------|
| Auth | `POST /auth/login`, `/auth/refresh`, `/auth/guest/session`, `/auth/dev/employee-session` |
| Employee | `GET /employees/me`, payslips / payroll-months, document center, finding explanations |
| Documents | `POST /documents/upload`, `POST /documents/employee/upload` |
| Extraction | Guest + employee payslip-extract / corrections / confirm |
| Validation | `POST /validation/run`, `POST /validation/employee/run`, run fetch |
| Assistant | `POST /assistant/chat`, `GET /assistant/popular-questions` |
| AI monitoring | `GET /admin/ai/dashboard`, `GET /admin/ai/models/comparison` |
| OCR / parser | `POST /ocr/extract`, `POST /parser/payslip` |
| Batch / compliance | Bulk payslip jobs, MCP diff proposals (foundation) |

See [docs/api.md](docs/api.md).

---

## Testing

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

Smoke: `GET /health`, guest assistant chat, document upload, guest/employee extract → confirm → validate.

---

## Project status

### Implemented

- Deterministic validation engine + DynamoDB persistence for runs/findings
- Document upload to S3/MinIO with DynamoDB metadata
- OCR + evidence-bound payslip / Document Model extraction
- Guest landing: assistant + validate-my-payslip (document-first)
- Employee monthly workspace (Upload / Digital Payslip / Validation / Original Document)
- Employee identity/period comparison, confirmation gate, owned validation, re-validation after edits
- Accountant Phase 1 workspace (organization-scoped employees, reused employee workspaces and selected-employee AI, persistent bulk UX)
- Accountant bulk pipeline (split → OCR → canonical extraction → match → confirm → deterministic validation, persisted incrementally)
- Cognito adapter (login/refresh/JWT verify) + local dev auth
- DynamoDB single-table repositories (org, employee, documents, extractions, validation, audit, bindings)
- i18n (he / en / ar) with RTL
- Docker Compose development stack
- AI telemetry wrapper (normalized tokens/cost/latency) and developer monitoring UI
- Global popular questions (DynamoDB counters + landing sidebar)

### In progress / partial

- Supporting document analysis (attendance / contract / national ID structured extract)
- Full RBAC enforcement on every accountant/guest mutation route
- SES delivery in real environments (console fallback when unset)
- Background Celery OCR on generic upload (interactive flows use sync extraction)
- Multi-instance CloudWatch-backed dashboard aggregation (process-local aggregates today)

### Planned

- Vector RAG over legal rules and contracts
- Historical payroll comparison / richer employee trends
- Absolute uniqueness constraints beyond application-level period gates
- MCP Kol Zchut sync automation in production
- In-app binary document viewer for side-by-side review
- Stronger guest session durability (replace process-local ephemeral store if product requires it)
- WebSocket batch progress, mobile app, payroll-system integrations, SOC 2 — product roadmap items

---

## Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture (DynamoDB, AWS, auth) — preferred source of truth |
| [docs/architecture.md](docs/architecture.md) | Older architecture notes (may lag) |
| [docs/database.md](docs/database.md) | DB notes — still contains legacy PostgreSQL material |
| [docs/ai-architecture.md](docs/ai-architecture.md) | AI / OCR / agents |
| [docs/rule-engine.md](docs/rule-engine.md) | Deterministic rules |
| [docs/api.md](docs/api.md) | API reference |
| [docs/security-and-deployment.md](docs/security-and-deployment.md) | Security & deployment |
| [backend/README.md](backend/README.md) | Backend package notes |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Frontend cannot reach API | API not running | `docker compose up` or start uvicorn |
| `getaddrinfo` for `redis` / `minio` / `dynamodb` on host | Docker hostnames from host process | Use `.env.local` localhost URLs or `*_LOCAL_URL` fallbacks |
| New npm package missing in Docker frontend | Stale `frontend_node_modules` volume | `docker compose down -v` then `up --build` |
| Upload `background_status: not_queued` | Redis/Celery down | Document still stored; start worker for background jobs |
| Assistant limited / unavailable | Ollama unreachable | Start host Ollama and pull `OLLAMA_DEFAULT_MODEL` |
| Hebrew OCR uses Tesseract | Expected with PaddleOCR default | Not a bug — intentional fallback |

---

## Internationalization

Supported UI languages: **Hebrew (`he`, RTL)**, **English (`en`, LTR)**, **Arabic (`ar`, RTL)**. Default: `he`.

Locale packs live under `frontend/src/i18n/locales/`. The API accepts `Accept-Language` / explicit `locale` on relevant requests. OCR quality still depends on image quality and model availability.
