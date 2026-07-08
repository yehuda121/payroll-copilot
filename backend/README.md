# Payroll Copilot Backend

Python package for the **Payroll Copilot** backend: a FastAPI API that runs a deterministic payroll validation engine, persists document uploads, and orchestrates the payroll assistant.

## Scope

- **FastAPI** presentation layer (`payroll_copilot.presentation`)
- **Deterministic validation** of payroll against configured labor-law and policy rules
- **Document upload and persistence** (metadata in PostgreSQL; object storage for files)
- **Assistant orchestration** (LangGraph tools and guardrails; synthesis via an LLM provider when available)
- **PostgreSQL** for durable application data
- **Celery / Redis** for background tasks (for example OCR enqueue and batch jobs)
- **Object storage** (S3-compatible / MinIO in development)

## Compliance principle

**Pass/fail compliance outcomes are decided only by the deterministic rule engine.** AI assists with extraction, explanation, and orchestration — it never overrides validation results.

## Layout

Source lives under `src/payroll_copilot/` (domain, application, infrastructure, presentation). See the repository root `README.md` for run modes, configuration, and product-level documentation.
