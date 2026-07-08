# Payroll Copilot

**A payroll validation platform for Israeli labor law compliance, built around a deterministic rule engine.**

Payroll Copilot lets a guest upload a payslip and receive a structured validation report from a deterministic rule engine, and provides a source-bound payroll assistant that answers payroll/labor-law questions using approved local content only. Compliance pass/fail decisions are always made by the backend rule engine — never by AI.

> **Status: work in progress.** The architecture, deterministic validation engine, document upload/persistence, Phase 1 OCR text extraction (`POST /ocr/extract`), and the public guest experience (assistant + validate-my-payslip) are implemented. Several capabilities are intentionally **not connected yet** (OCR→AI Parser→validation wiring, vector RAG, contract/attendance/ID analysis, production auth). This README calls out exactly what is and is not built — see **[Current Status](#current-status)** and **[Current Limitations](#current-limitations)**. Nothing here fabricates validation results, OCR fields, or legal answers.

---

## Current Status

Honest snapshot of what exists today. "Partial" means real code runs but a downstream capability is deliberately not wired.

### Implemented (working today)
- **Deterministic validation engine** — rule evaluation, findings, confidence aggregation.
- **Validation persistence** — `POST /validation/run` and `GET /validation/runs/{id}` persist to PostgreSQL.
- **Document upload & persistence** — `POST /documents/upload`, `GET /documents/{id}` with server-side upload guardrails.
- **OCR text extraction (Phase 1)** — `POST /ocr/extract` returns page-level text + real OCR confidence via pluggable providers (PaddleOCR primary; Hebrew→Tesseract fallback). No payroll field parsing.
- **AI Payslip Parser (Phase 2A)** — `POST /parser/payslip` turns OCR JSON into per-field structured payslip data via local Ollama (layout-independent).
- **Guest extraction + validation (Phases 2B–7)** — extract → review/edit → validate on Continue → results; mapper builds a synthetic guest employee from parser fields (`rule_profile=payroll`); demo builder is not used on the guest path.
- **Public Guest Experience (frontend)** — landing page, Payroll Assistant chat, Validate-My-Payslip upload/review/results flow, enterprise validation report with honest scope.
- **LangGraph Payroll Assistant (backend)** — `POST /assistant/chat` with input/output guardrails, greeting handling, and keyword search over approved YAML legal rules.
- **Ollama integration** — host-first URL resolution with optional Docker fallback and graceful degradation when unavailable.
- **i18n foundation** — Hebrew / English / Arabic UI + RTL, locale-aware API responses and assistant answers (OCR language extraction not connected).
- **Database schema & Alembic migrations**, **Docker Compose orchestration**, **guest JWT tokens** (`POST /auth/guest/session`).

### Partially implemented
- **Supporting document analysis** — attendance / contract / national ID can be uploaded, but extraction/cross-check is not connected yet (scope stays unable for those areas).
- **Assistant legal search** — keyword search over local YAML rules only; **no vector RAG** yet.
- **Role-based portals (employee/accountant/admin)** — UI foundation exists; most portal pages are not wired to the backend.
- **Guest sessions** — guest JWT is issued and sent, but there is **no `guest_sessions` DB table** and routes do not yet enforce the token.

### Planned but not built
- Vector RAG over legal rules and employment contracts.
- Contract / attendance / national-ID analysis.
- Historical payroll comparison.
- Production auth (AWS Cognito) and full RBAC enforcement.
- Batch bulk-PDF splitting/identification pipeline (endpoints are stubs).
- MCP Kol Zchut legal sync automation.
- RTL / i18n UI.

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

**Status: Frontend foundation + backend API implemented.** Guest chat on the public landing page calls `POST /api/v1/assistant/chat`.

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
Guest/Employee → Upload payslip → OCR extract → Validate (deterministic) →
AI explanation (non-binding) → Report with confidence breakdown
```

Registered employees get persistent history and trend analysis.

---

## Payroll Accountant Flow

```
Upload bulk PDF → Background job → Split → Identify → Validate all →
Export report (PDF/Excel/JSON)
```

Email leave requests processed via n8n → Email Agent → Attendance DB (with human review for low confidence).

---

## Security

- Role-Based Access Control (guest, employee, accountant, admin)
- JWT authentication + guest tokens
- Encrypted national ID storage
- Secure file storage with pre-signed URLs
- Append-only audit logs (7-year retention)
- Input validation, rate limiting, tenant isolation

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

- **Multilingual OCR text extraction is available via `POST /api/v1/ocr/extract`.** Hebrew uses Tesseract fallback (PaddleOCR has no official Hebrew model — intentional). Payslip **field** parsing / AI Parser is not implemented; document upload still returns `ocr_language_status: "not_connected"` for the guest upload path until async wiring lands.
- Auth portal pages (login/signup) are not fully translated yet.
- Some approved legal rule YAML text is bilingual (`he`/`en`); Arabic assistant answers may translate/summarize approved sources without inventing new legal claims.

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
| `employee` | `/employee` | Sarah Cohen |
| `payroll_accountant` | `/accountant` | David Levy |
| `developer_admin` | `/admin` | Yael Administrator |

Dev sessions are stored in `localStorage` only. Production auth will use AWS Cognito via `frontend/src/auth/authProvider.ts`.

### Role-Based UI

The frontend provides three portals after login:

**Employee Portal** — Dashboard, document upload, payslips, attendance, contract, AI chat (explanations only), validation history.

**Payroll Accountant Portal** — Employee management table, bulk payroll upload, batch monitor, validation findings, approval queue, audit logs.

**Developer/Admin Portal** — Rule packs, department rules, MCP legal sync, AI models, RAG management, system configuration.

Public landing page (`/`) includes guest validate + payroll chat.
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
- `POST /auth/login` — Authentication
- `POST /assistant/chat` — Public guest payroll assistant (LangGraph orchestration)
- `POST /documents/upload` — Document upload
- `POST /validation/run` — Trigger validation
- `POST /batch/payslips` — Bulk PDF processing
- `POST /employees/import` — Excel master data import
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

- **OCR text extraction (Phase 1) is implemented** via `POST /api/v1/ocr/extract` (PDF/PNG/JPG/JPEG → pages + text + confidence). Install Paddle with `pip install -e ".[ocr-paddle]"`.
- **AI Payslip Parser (Phase 2A) is implemented** via `POST /api/v1/parser/payslip` (OCR JSON → per-field `{value, confidence, source_text, status}`). Uses local Ollama; one retry on invalid JSON; confidence never invented.
- **Guest extraction persistence (Phase 2B/2C)** — `POST /api/v1/extraction/guest/payslip-extract` orchestrates upload → OCR → parser → `document_extractions` row; guest Review shows real fields (Missing / unable to read / confidence unavailable — never invented).
- **Guest validation connected (Phases 3–7)** — Review/edit → `POST /extraction/guest/{id}/corrections` (new extraction version) → `POST /validation/run` maps structured fields to a synthetic guest context (`rule_profile=payroll`). Missing data → Unable to verify. AI explains existing findings only.
- **OCR worker on document upload is still a stub.** The Celery `process_document_ocr` task remains a placeholder; the guest validate flow uses the sync extraction endpoint instead.
- **DemoValidationContextBuilder remains in codebase for non-guest/dev use only** — it is not used on the guest validation path.
- **No real vector RAG yet.** The assistant uses keyword search over local YAML legal rules only.
- **No production auth / Cognito yet.** A dev role selector and guest JWT exist; routes do not enforce auth.
- **Guest session DB persistence not completed.** Guest JWT is issued and sent, but there is no `guest_sessions` table and routes don't require the token.
- **Contract / attendance / national-ID analysis not connected.** Uploading these documents is supported, but they are reported as `not_available` in the validation scope because analysis is not wired.
- **Historical comparison not available.** Always reported as `not_available`.
- **Batch bulk-PDF, MCP legal sync** are design targets, not shipped.
- **Hebrew OCR:** when `OCR_PROVIDER=paddleocr` (default), `language=he` transparently uses **Tesseract** and returns `engine=tesseract` plus a warning. This is intentional production-honest behavior — not a bug.

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
