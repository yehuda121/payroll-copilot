# Payroll Copilot

**AI-powered payroll validation platform for Israeli labor law compliance.**

Payroll Copilot helps payroll accountants validate hundreds of payroll slips before salaries are paid, and enables employees to upload slips and employment documents for legal validation, explanations, and personalized recommendations.

> **Production SaaS** — designed for multi-tenant deployment, long-term maintainability, and deterministic compliance validation.

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
├── pyproject.toml
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── alembic/                    # Database migrations
├── config/
│   ├── rules/labor_law/        # YAML legal rules (source of truth)
│   ├── rules/departments/      # Department rule profiles
│   ├── prompts/                # AI agent system prompts
│   └── ai_models.yaml          # Model selection per agent
├── docs/                       # Technical documentation
├── mcp/                        # MCP server for legal rule sync
├── src/payroll_copilot/
│   ├── domain/                 # Entities, value objects, rule interfaces
│   ├── application/            # Use cases, ports, DTOs
│   ├── infrastructure/         # DB, storage, OCR, AI, Celery
│   └── presentation/           # FastAPI app, routes, middleware
└── tests/
```

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
| OCR | Pluggable port | Tesseract (default), PaddleOCR |
| Embeddings | pgvector | Contract/policy RAG |
| Agents | Specialized orchestrators | Splitter, extractor, explainer, email parser |

See [docs/ai-architecture.md](docs/ai-architecture.md).

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

Hebrew · English · Arabic with RTL support.

API uses `Accept-Language` header. Validation messages stored as i18n keys.

---

## Installation

### Prerequisites

- Docker & Docker Compose
- Python 3.12+ (for local development)
- 16GB+ RAM recommended (Ollama)

### Quick Start

```bash
# Clone and configure
cp .env.example .env

# Start core services (uses host Ollama if already running — see Ollama section below)
docker compose up -d

# Run migrations
docker compose exec api alembic upgrade head

# API available at http://localhost:8000
# Swagger UI at http://localhost:8000/docs
```

Ensure Ollama is running on your host with the required models, or start the Docker Ollama fallback (see **Ollama** below).

### Local Development

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# In .env set:
#   OLLAMA_BASE_URL=http://localhost:11434
#   OLLAMA_HOST_URL=http://localhost:11434

# Start dependencies only (no Docker Ollama required if host Ollama is running)
docker compose up -d postgres redis minio

# Run API locally
uvicorn payroll_copilot.presentation.main:app --reload

# Run worker
celery -A payroll_copilot.infrastructure.tasks.celery_app worker -l info
```

---

## Ollama

Payroll Copilot prefers an **Ollama instance already running on your host machine**. The Docker Ollama container is an optional fallback.

### URL resolution order

When `MODEL_PROVIDER=ollama`:

1. **`OLLAMA_BASE_URL` set** → use it exactly (no probing)
2. **`OLLAMA_BASE_URL` empty** and `OLLAMA_AUTO_FALLBACK=true` → probe `OLLAMA_HOST_URL`
3. Host unreachable → use `OLLAMA_DOCKER_URL` (requires `--profile docker-ollama`)

### Docker Compose (default `.env.example`)

| Variable | Value | Purpose |
|----------|-------|---------|
| `OLLAMA_BASE_URL` | *(empty)* | Enable auto-resolution |
| `OLLAMA_HOST_URL` | `http://host.docker.internal:11434` | Host Ollama from containers |
| `OLLAMA_DOCKER_URL` | `http://ollama:11434` | Fallback Docker service |
| `OLLAMA_AUTO_FALLBACK` | `true` | Probe host before fallback |

`api` and `worker` include `extra_hosts: host.docker.internal:host-gateway` for Linux compatibility.

### Local development (no Docker for API)

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_HOST_URL=http://localhost:11434
```

### Docker Ollama fallback

Use when host Ollama is not installed or not reachable:

```bash
docker compose --profile docker-ollama up -d
docker compose exec ollama ollama pull llama3.1:8b
docker compose exec ollama ollama pull nomic-embed-text
```

### Explicit override

To pin a specific endpoint (no probing):

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

---

## Docker

```bash
docker compose up -d                         # Core services + host Ollama
docker compose --profile docker-ollama up -d # Include Docker Ollama fallback
docker compose --profile automation up -d    # Include n8n
docker compose logs -f api                   # Follow API logs
docker compose exec api pytest               # Run tests
```

Services: `api`, `worker`, `beat`, `postgres`, `redis`, `minio`, (`ollama` via profile `docker-ollama`), (`n8n` via profile `automation`).

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis connection | `redis://localhost:6379/0` |
| `S3_ENDPOINT` | Object storage endpoint | `http://minio:9000` |
| `S3_ACCESS_KEY` | Storage access key | — |
| `S3_SECRET_KEY` | Storage secret key | — |
| `S3_BUCKET` | Bucket name | `payroll-copilot` |
| `OLLAMA_BASE_URL` | Ollama API (explicit override; empty = auto-resolve) | *(empty)* |
| `OLLAMA_HOST_URL` | Host Ollama URL probed from containers | `http://host.docker.internal:11434` |
| `OLLAMA_DOCKER_URL` | Docker Ollama fallback URL | `http://ollama:11434` |
| `OLLAMA_AUTO_FALLBACK` | Probe host before using Docker URL | `true` |
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
- `POST /documents/upload` — Document upload
- `POST /validation/run` — Trigger validation
- `POST /batch/payslips` — Bulk PDF processing
- `POST /employees/import` — Excel master data import
- `GET /compliance/diff-proposals` — MCP legal diffs

See [docs/api.md](docs/api.md).

---

## Testing

```bash
pytest                          # All tests
pytest tests/unit               # Unit tests
pytest tests/integration        # Integration tests (requires Docker)
ruff check src tests            # Lint
mypy src                        # Type check
```

---

## Future Roadmap

- [ ] Web frontend (React, RTL-aware)
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
