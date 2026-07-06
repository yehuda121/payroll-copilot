# Payroll Copilot — System Architecture

## Executive Summary

Payroll Copilot is a multi-tenant SaaS platform for AI-assisted, **deterministic** payroll validation under Israeli labor law. The system separates concerns into clearly bounded contexts while shipping as a **modular monolith** — one deployable unit with strict internal boundaries, not premature microservices.

### Architectural Principles

| Principle | Implementation |
|-----------|----------------|
| Deterministic validation | Rule Engine is pure Python; AI never decides pass/fail |
| AI as augmentation | OCR extraction, splitting, explanations, email parsing only |
| Local rules as truth | YAML labor law + DB company rules; MCP proposes diffs only |
| Extensibility | Plugin rules, swappable OCR/LLM providers, department registry |
| Multi-tenancy | Organization-scoped data with PostgreSQL RLS |
| Auditability | Immutable audit log for all sensitive operations |

---

## Recommended Production Adjustments

The requirements are sound. The following refinements improve long-term operability:

### 1. Modular Monolith over Microservices

**Why:** Payroll validation has strong transactional consistency needs (employee master data → payslip → rules → report). Splitting into microservices early adds network failure modes, distributed tracing burden, and deployment complexity without proportional benefit at initial scale.

**Approach:** One FastAPI application with bounded contexts (`identity`, `employees`, `documents`, `validation`, `reports`, `ai`, `compliance`). Extract services only when a context has independent scaling or team ownership needs.

### 2. Celery + Redis over inline async for batch PDFs

**Why:** A 300-slip PDF batch can take 15–45 minutes. HTTP request/response cannot hold that connection. Background workers with job status polling or WebSocket progress is production-standard.

### 3. pgvector inside PostgreSQL over separate vector DB

**Why:** RAG corpus sizes (contracts, policies) per tenant are moderate. Co-locating embeddings with relational data simplifies backups, transactions, and tenant isolation.

### 4. n8n as external orchestrator, not embedded runtime

**Why:** n8n excels at email triggers and human-in-the-loop workflows. The platform exposes webhooks and authenticated APIs; n8n owns the email polling workflow graph. This avoids coupling Python release cycles to n8n node versions.

### 5. Field detection by header name (Excel)

**Why:** Already specified correctly. We implement a `ColumnMappingResolver` that maps canonical field names to detected headers via fuzzy matching and alias tables — never positional indices.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENTS                                         │
│  Web App (future) │ Guest Upload │ Accountant Portal │ n8n Email Workflow   │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │ HTTPS
┌───────────────────────────────────▼─────────────────────────────────────────┐
│                         API GATEWAY (FastAPI)                                │
│  Auth (JWT) │ RBAC │ Rate Limit │ i18n │ Audit Middleware │ OpenAPI         │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐         ┌─────────────────┐         ┌─────────────────┐
│  Application  │         │  Background     │         │  MCP Server     │
│  Use Cases    │         │  Workers        │         │  (Legal Sync)   │
│  (Clean Arch) │         │  (Celery)       │         │                 │
└───────┬───────┘         └────────┬────────┘         └────────┬────────┘
        │                          │                           │
        ▼                          ▼                           ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                            DOMAIN LAYER                                    │
│  Employee │ Payslip │ ValidationResult │ Rule │ Contract │ Attendance     │
└───────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                         INFRASTRUCTURE LAYER                               │
├─────────────┬─────────────┬─────────────┬─────────────┬─────────────────────┤
│ PostgreSQL  │ MinIO/S3    │ Ollama      │ OCR Engine  │ Redis               │
│ + pgvector  │ (files)     │ (local LLM) │ (abstract)  │ (cache + broker)    │
└─────────────┴─────────────┴─────────────┴─────────────┴─────────────────────┘
```

---

## Bounded Contexts

### Identity & Access (`identity`)

- Organizations (tenants), users, roles, permissions
- Guest session tokens for unregistered employee uploads
- JWT access + refresh tokens; API keys for n8n integration

### Employee Master Data (`employees`)

- Employee records imported from Excel (header-based mapping)
- Department assignments, employment types, salary configuration
- Historical snapshots for point-in-time validation

### Document Management (`documents`)

- Upload pipeline: virus scan hook → object storage → metadata in DB
- Document types: payslip, attendance, contract, ID, ID appendix, employee Excel
- OCR extraction with confidence scores persisted per field

### Validation (`validation`)

- **Deterministic Rule Engine** — core business value
- Rule categories: legal, tax, pension, overtime, vacation, department, contract, historical
- Validation runs produce structured `ValidationReport` with severity, confidence, citations

### AI Services (`ai`)

- Agent orchestration (not validation decisions)
- Agents: Payslip Splitter, Contract Analyzer, Compliance Explainer, Email Parser, Vacation/Sick Leave
- Model Provider abstraction: Ollama (default), OpenAI, Claude, Gemini, Azure OpenAI

### Compliance & Legal Sync (`compliance`)

- YAML rule files (version controlled)
- MCP tools compare against Kol Zchut / government sources
- Diff proposals require accountant approval before YAML update

### RAG (`rag`)

- Embeddings for contracts, policies, procedures, department agreements
- Queried by Validation Engine when contract-specific rules needed
- Tenant-scoped collections in pgvector

### Reporting (`reports`)

- Batch validation reports for accountants
- Employee-facing explanations (localized HE/EN/AR)
- Export: PDF, Excel, JSON

### Attendance (`attendance`)

- Parsed from reports and email agent
- Feeds vacation/sick leave validation rules

---

## Clean Architecture Layers

```
src/payroll_copilot/
├── domain/           # Entities, value objects, domain events, rule interfaces
├── application/      # Use cases, ports (interfaces), DTOs, orchestration
├── infrastructure/   # Adapters: SQLAlchemy, S3, Ollama, OCR, Celery
└── presentation/     # FastAPI routers, request/response schemas, middleware
```

**Dependency rule:** Domain knows nothing. Application depends on domain + port interfaces. Infrastructure implements ports. Presentation depends on application.

---

## Request Flows

### Guest Employee Upload

```
Upload PDF → Store → OCR Extract → Match Employee (optional) →
Run Validation Engine → AI Explainer (non-binding) → Return Report
```

Guest sessions expire after 24h; files deleted per retention policy unless user registers.

### Registered Employee

Same as guest plus: persist history, RAG over own contract, trend comparisons.

### Accountant Batch (300+ slips)

```
Upload bulk PDF → Enqueue Job → Payslip Splitter Agent →
N payslip documents → Parallel OCR → Employee identification →
Validation Engine (per slip) → Aggregate Report → Notify accountant
```

Progress: `GET /api/v1/jobs/{id}` returns `{ processed, total, status, errors[] }`.

### Email Vacation Request (via n8n)

```
n8n polls mailbox → POST /api/v1/integrations/email/parse-leave →
Email Agent extracts dates/hours/type → confidence check →
High: write attendance │ Low: human review queue
```

---

## Confidence Model

Every extracted or inferred value carries a `ConfidenceScore` (0.0–1.0) with `source` enum:

| Source | Description |
|--------|-------------|
| `ocr` | Optical character recognition |
| `llm` | Language model extraction |
| `rule` | Deterministic rule computation |
| `identity_match` | Employee ID / name matching |
| `contract_rag` | RAG retrieval match quality |
| `historical` | Historical payroll comparison |

Reports surface the **minimum confidence** across fields used in a finding, plus per-finding breakdown.

---

## Internationalization

- Babel/gettext for server messages
- `Accept-Language` header + user preference
- RTL layout handled by frontend; API returns `direction: rtl|ltr` in locale metadata
- Rule finding messages stored as message keys + interpolation params; translated at presentation layer

---

## Security Architecture

| Control | Implementation |
|---------|----------------|
| RBAC | Roles: `guest`, `employee`, `accountant`, `admin`, `system` |
| Tenant isolation | `organization_id` on all tenant tables + PostgreSQL RLS |
| Encryption at rest | PostgreSQL TDE or disk encryption; S3 SSE; field-level AES for ID numbers |
| Encryption in transit | TLS 1.3 everywhere |
| Audit | Append-only `audit_logs` table; who, what, when, IP, resource |
| File access | Pre-signed URLs, short TTL; no public buckets |
| Input validation | Pydantic v2 strict mode; file type magic-byte verification |
| Secrets | Environment variables / vault; never in repo |

---

## Observability

- Structured JSON logging (correlation ID per request)
- OpenTelemetry traces: API → worker → OCR → LLM
- Metrics: validation duration, rule failure rates, OCR confidence distribution
- Health: `/health`, `/ready` (DB, Redis, Ollama, storage)

---

## Deployment Topology (Docker)

```
docker-compose:
  api          → FastAPI (uvicorn)
  worker       → Celery workers
  beat         → Celery beat (scheduled jobs)
  postgres     → PostgreSQL 16 + pgvector
  redis        → Redis 7
  minio        → S3-compatible storage
  ollama       → Local LLM
  n8n          → Workflow automation (optional profile)
```

Production: Kubernetes or managed containers; managed PostgreSQL; S3 instead of MinIO.

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.12+ |
| API | FastAPI |
| ORM | SQLAlchemy 2.0 async |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Task queue | Celery + Redis |
| Database | PostgreSQL 16 + pgvector |
| LLM (local) | Ollama |
| OCR | Pluggable (Tesseract default, PaddleOCR optional) |
| PDF | PyMuPDF (fitz) for splitting |
| Excel | openpyxl + header detection |
| i18n | Babel |
| Auth | python-jose JWT |

---

## Future Extraction Points

When scale demands, these contexts can become independent services:

1. **Document Processing Worker** — OCR/splitting is CPU-heavy
2. **AI Inference Gateway** — centralize LLM routing
3. **Report Generation** — PDF rendering at scale

Internal boundaries are already port-based; extraction requires new deployment, not rewrite.
