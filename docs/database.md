# Payroll Copilot — Database Design

## Overview

**Production runtime:** Amazon DynamoDB (single-table) is the primary business database. Document bytes are stored in Amazon S3. See [ARCHITECTURE.md](../ARCHITECTURE.md).

**Legacy (optional):** PostgreSQL 16 + Alembic / SQLAlchemy models remain in the repo for older tests and tooling. They are **not** the active runtime path. Start with `docker compose --profile legacy-postgres` and set `DATABASE_URL` only when needed.

### Legacy PostgreSQL notes (optional tooling)

PostgreSQL 16 with extensions:
- `pgvector` — RAG embeddings (legacy path)
- `uuid-ossp` — UUID primary keys
- `pg_trgm` — fuzzy name matching for employee identification

All tenant-scoped tables include `organization_id` with Row-Level Security (RLS) policies.

---

## Entity Relationship Diagram

```
organizations ──┬── users
                ├── departments
                ├── employees ──┬── employee_contracts
                │               ├── employee_salary_history
                │               └── employee_documents
                ├── documents ──┬── document_extractions
                │               └── ocr_field_confidences
                ├── validation_runs ── validation_findings
                ├── batch_jobs ── batch_job_items
                ├── attendance_records
                ├── rag_documents ── rag_chunks (vector)
                ├── rule_definitions (custom org/ dept rules)
                ├── legal_rule_versions
                ├── legal_rule_diff_proposals
                ├── audit_logs
                └── guest_sessions
```

---

## Core Tables

### organizations

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| name | VARCHAR(255) | |
| slug | VARCHAR(100) UNIQUE | URL identifier |
| settings | JSONB | locale default, retention days |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### users

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| organization_id | UUID FK | NULL for platform admin |
| email | VARCHAR(255) | UNIQUE per org |
| password_hash | VARCHAR(255) | NULL for SSO future |
| role | ENUM | guest, employee, accountant, admin |
| preferred_locale | VARCHAR(5) | he, en, ar |
| is_active | BOOLEAN | |
| created_at | TIMESTAMPTZ | |

### departments

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| organization_id | UUID FK | |
| code | VARCHAR(50) | e.g. `lawyers`, `interns` |
| name | JSONB | Localized names `{"he": "...", "en": "..."}` |
| rule_profile | VARCHAR(100) | Maps to rule plugin set |
| is_active | BOOLEAN | |

**Extensibility:** New departments added via DB + rule profile YAML; no code changes.

### employees

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| organization_id | UUID FK | |
| employee_number | VARCHAR(50) | Business ID (ת.ז. / מספר עובד) |
| national_id_encrypted | BYTEA | AES encrypted |
| first_name | VARCHAR(100) | |
| last_name | VARCHAR(100) | |
| department_id | UUID FK | |
| employment_type | ENUM | full_time, part_time, intern, pre_intern, contractor |
| salary_type | ENUM | hourly, monthly |
| hourly_rate | DECIMAL(10,2) | NULL if monthly |
| monthly_salary | DECIMAL(12,2) | NULL if hourly |
| contract_start_date | DATE | |
| contract_end_date | DATE | NULL |
| manager_id | UUID FK | Self-ref to employees |
| status | ENUM | active, on_leave, terminated |
| metadata | JSONB | Extensible professional fields |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

**Indexes:** `(organization_id, employee_number)` UNIQUE, `(organization_id, department_id)`, GIN on `metadata`.

### employee_import_snapshots

Tracks each Excel import for audit and rollback.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| organization_id | UUID FK | |
| document_id | UUID FK | Source Excel file |
| column_mapping | JSONB | Detected header → canonical field |
| rows_imported | INTEGER | |
| rows_updated | INTEGER | |
| rows_failed | INTEGER | |
| error_log | JSONB | |
| imported_at | TIMESTAMPTZ | |
| imported_by | UUID FK | users |

### employee_salary_history

Point-in-time salary for historical validation.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| employee_id | UUID FK | |
| effective_from | DATE | |
| effective_to | DATE | NULL = current |
| hourly_rate | DECIMAL(10,2) | |
| monthly_salary | DECIMAL(12,2) | |
| salary_type | ENUM | |

---

## Document Tables

### documents

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| organization_id | UUID FK | NULL for guest uploads |
| guest_session_id | UUID FK | NULL for authenticated |
| uploaded_by | UUID FK | users, nullable |
| document_type | ENUM | payslip, attendance, contract, national_id, id_appendix, employee_excel, bulk_payslip_pdf |
| storage_key | VARCHAR(500) | S3/MinIO path |
| original_filename | VARCHAR(255) | |
| mime_type | VARCHAR(100) | |
| file_size_bytes | BIGINT | |
| checksum_sha256 | CHAR(64) | |
| status | ENUM | uploaded, processing, processed, failed |
| employee_id | UUID FK | Linked after identification |
| period_year | SMALLINT | Payslip period |
| period_month | SMALLINT | |
| metadata | JSONB | |
| created_at | TIMESTAMPTZ | |
| expires_at | TIMESTAMPTZ | Guest TTL |

### document_extractions

Structured OCR/LLM output per document.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| document_id | UUID FK | |
| extraction_version | INTEGER | Re-extraction counter |
| engine | VARCHAR(50) | tesseract, paddleocr, llm |
| raw_text | TEXT | Full OCR text |
| structured_data | JSONB | Parsed payslip fields |
| overall_confidence | DECIMAL(4,3) | 0.000–1.000 |
| created_at | TIMESTAMPTZ | |

### ocr_field_confidences

Per-field confidence for transparency in reports.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| extraction_id | UUID FK | |
| field_name | VARCHAR(100) | e.g. `gross_salary` |
| field_value | TEXT | |
| confidence | DECIMAL(4,3) | |
| bounding_box | JSONB | Optional coordinates |

---

## Validation Tables

### validation_runs

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| organization_id | UUID FK | |
| document_id | UUID FK | Source payslip |
| employee_id | UUID FK | |
| triggered_by | UUID FK | users |
| status | ENUM | pending, running, completed, failed |
| overall_result | ENUM | pass, warnings, critical |
| overall_confidence | DECIMAL(4,3) | |
| rules_evaluated | INTEGER | |
| rules_failed | INTEGER | |
| started_at | TIMESTAMPTZ | |
| completed_at | TIMESTAMPTZ | |
| context_snapshot | JSONB | Employee + period state used |

### validation_findings

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| validation_run_id | UUID FK | |
| rule_id | VARCHAR(100) | e.g. `legal.overtime.daily_limit` |
| rule_category | ENUM | legal, tax, pension, department, contract, historical |
| severity | ENUM | info, warning, critical |
| message_key | VARCHAR(200) | i18n key |
| message_params | JSONB | Interpolation values |
| expected_value | TEXT | |
| actual_value | TEXT | |
| confidence | DECIMAL(4,3) | |
| legal_reference | VARCHAR(200) | e.g. `חוק שכר מינימום סעיף 4` |
| rag_citation | JSONB | Contract clause reference if applicable |
| created_at | TIMESTAMPTZ | |

---

## Batch Processing

### batch_jobs

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| organization_id | UUID FK | |
| source_document_id | UUID FK | Bulk PDF |
| created_by | UUID FK | accountant |
| status | ENUM | queued, splitting, validating, completed, failed |
| total_slips | INTEGER | |
| processed_slips | INTEGER | |
| failed_slips | INTEGER | |
| celery_task_id | VARCHAR(100) | |
| started_at | TIMESTAMPTZ | |
| completed_at | TIMESTAMPTZ | |

### batch_job_items

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| batch_job_id | UUID FK | |
| slip_index | INTEGER | Order in PDF |
| child_document_id | UUID FK | Split payslip doc |
| employee_id | UUID FK | Identified employee |
| identity_match_confidence | DECIMAL(4,3) | |
| validation_run_id | UUID FK | |
| status | ENUM | pending, identified, validated, failed |

---

## Attendance

### attendance_records

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| organization_id | UUID FK | |
| employee_id | UUID FK | |
| record_type | ENUM | vacation, sick_leave, holiday, work_day |
| start_date | DATE | |
| end_date | DATE | |
| hours | DECIMAL(5,2) | NULL for full days |
| source | ENUM | manual, email_agent, attendance_report |
| source_reference | UUID FK | document or email parse id |
| confidence | DECIMAL(4,3) | |
| review_status | ENUM | approved, pending_review, rejected |
| created_at | TIMESTAMPTZ | |

---

## RAG

### rag_documents

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| organization_id | UUID FK | |
| document_type | ENUM | contract, policy, procedure, department_agreement |
| employee_id | UUID FK | NULL for org-wide |
| department_id | UUID FK | NULL for org-wide |
| source_document_id | UUID FK | |
| title | VARCHAR(255) | |
| created_at | TIMESTAMPTZ | |

### rag_chunks

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| rag_document_id | UUID FK | |
| chunk_index | INTEGER | |
| content | TEXT | |
| embedding | vector(768) | Model-dependent dimension |
| metadata | JSONB | page, section |
| created_at | TIMESTAMPTZ | |

**Index:** HNSW on `embedding` for cosine similarity, filtered by `organization_id`.

---

## Rules & Compliance

### rule_definitions

Organization/department custom rules (legal rules stay in YAML).

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| organization_id | UUID FK | |
| department_id | UUID FK | NULL = org-wide |
| rule_code | VARCHAR(100) | |
| rule_config | JSONB | Parameters |
| is_active | BOOLEAN | |
| priority | INTEGER | Evaluation order |
| created_at | TIMESTAMPTZ | |

### legal_rule_versions

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| rule_file | VARCHAR(100) | e.g. `vacation.yaml` |
| version | VARCHAR(20) | Semver |
| content_hash | CHAR(64) | SHA256 of YAML |
| applied_at | TIMESTAMPTZ | |
| applied_by | UUID FK | |

### legal_rule_diff_proposals

MCP-generated diffs awaiting approval.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| rule_file | VARCHAR(100) | |
| external_source | VARCHAR(100) | kol_zchut, gov_il |
| diff_content | JSONB | Structured diff |
| status | ENUM | pending, approved, rejected |
| proposed_at | TIMESTAMPTZ | |
| reviewed_by | UUID FK | |
| reviewed_at | TIMESTAMPTZ | |
| review_notes | TEXT | |

---

## Audit & Sessions

### audit_logs

Append-only.

| Column | Type | Notes |
|--------|------|-------|
| id | BIGSERIAL PK | |
| organization_id | UUID FK | |
| user_id | UUID FK | |
| action | VARCHAR(100) | e.g. `document.upload`, `validation.run` |
| resource_type | VARCHAR(50) | |
| resource_id | UUID | |
| ip_address | INET | |
| user_agent | TEXT | |
| details | JSONB | Non-sensitive metadata |
| created_at | TIMESTAMPTZ | |

### guest_sessions

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| token_hash | CHAR(64) | |
| expires_at | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ | |

---

## Row-Level Security

```sql
ALTER TABLE employees ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON employees
  USING (organization_id = current_setting('app.current_org_id')::uuid);
```

Application sets `app.current_org_id` at connection start from JWT claims.

---

## Migration Strategy

- Alembic sequential migrations
- Seed data: default departments, column alias mappings for Excel
- Legal YAML loaded at startup into in-memory cache with file watcher for hot reload after approved MCP diffs

---

## Retention Policies

| Data | Default Retention |
|------|-------------------|
| Guest uploads | 24 hours |
| Guest validation reports | 7 days |
| Employee documents | Org setting (default 7 years) |
| Audit logs | 7 years (immutable) |
| Batch job artifacts | 90 days |

Implemented via scheduled Celery beat tasks.
