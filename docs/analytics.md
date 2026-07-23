# Analytics API

Backend analytics foundation. Aggregates existing documents, extractions,
validation runs/findings, employees, and user bindings **on demand**. No cache,
no scheduled jobs, no aggregation tables.

## Service responsibilities

| Component | Responsibility |
|-----------|----------------|
| `AnalyticsService` | Facade over registered metric use cases; `run_metric` for future metrics |
| `GetEmployeeSalaryAnalyticsUseCase` | Net/gross by `period_year`/`period_month` for one employee |
| `GetOrgPayrollAnalyticsUseCase` | Org payslip outcomes, validation failures, confidence by payroll period |
| `GetOrgQualityAnalyticsUseCase` | Org AI quality KPIs (extraction/OCR/validation/confidence/review) |
| `GetAdminOrgCensusUseCase` | Companies / employees / payroll accountants / assignment stats |
| `GetAdminQualityAnalyticsUseCase` | Cross-org rollup of `org.quality` |
| `AnalyticsRegistry` | Extensible name → provider map (no central switch) |
| Helpers under `application/services/analytics/` | Period keys, salary extraction, outcome mapping, aggregation, confidence buckets |

Salary amounts and quality metrics are read from existing extraction / validation
SoT. Nothing is duplicated into analytics-specific stores.

## Public endpoints

Base path: `/api/v1/analytics`

### `GET /employee/salary`

Auth: bound employee.

| Query | Type | Notes |
|-------|------|-------|
| `year` | int | Optional; defaults to current UTC year |

Response DTO: `EmployeeSalaryAnalyticsResponse`

- `months[]`: `period_year`, `period_month`, `net_salary`, `gross_salary`, `currency`, ids
- `available_years`
- `documents_missing_period` (payslips without period — excluded from series)

Grouping uses **only** document `period_year` / `period_month` (never `created_at`).

### `GET /org/payroll`

Auth: payroll accountant with organization binding.

| Query | Type | Notes |
|-------|------|-------|
| `year` | int | Optional; defaults to current UTC year |

Response DTO: `OrgPayrollAnalyticsResponse`

- `documents_by_month` — processed + success / review_required / failed
- `validation_failures_by_month`
- `error_type_distribution` / `top_validation_failures`
- `average_confidence_by_month` (extraction `overall_confidence`, else run)

### `GET /org/quality`

Auth: payroll accountant with organization binding.

| Query | Type | Notes |
|-------|------|-------|
| `year` | int | Optional; defaults to current UTC year |

Response DTO: `OrgQualityAnalyticsResponse`

- `months[]` — extraction/OCR/validation success rates, avg confidence, manual review, failures
- `confidence_distribution` — fixed bands `0–0.5`, `0.5–0.7`, `0.7–0.85`, `0.85–1.0`
- `totals` — year rollup
- `documents_missing_period`, `available_years`

Metric definitions (existing SoT only):

| Metric | Source |
|--------|--------|
| Extraction success | Latest extraction `ocr_status` + `parser_status` both `completed` |
| OCR success / failure | Latest extraction `ocr_status` |
| Validation success | Latest validation run `overall_result == pass` |
| Average confidence | Extraction `overall_confidence`, else run |
| Manual review | Document outcome / lifecycle / confirmation review (not Redis match queue) |
| Failed documents | `classify_document_outcome` → FAILED |

### `GET /admin/census`

Auth: developer admin (`UserRole.ADMIN`).

Response DTO: `AdminOrgCensusResponse`

- `companies_count`, `employees_count`, `payroll_accountants_count`
- `employees_without_payroll_accountant` (uses `Employee.payroll_accountant_id`)
- `employees_per_payroll_accountant[]`
- `organizations[]` per-company slices

### `GET /admin/quality`

Auth: developer admin (`UserRole.ADMIN`).

| Query | Type | Notes |
|-------|------|-------|
| `year` | int | Optional; defaults to current UTC year |

Response DTO: `AdminQualityAnalyticsResponse`

- Cross-org rollup of `org.quality` via `OrganizationDirectoryPort`
- Includes per-org slices under `organizations[]`

## Extending

1. Add a use case with `metric_name` + `compute(AnalyticsContext)`.
2. Register it via `AnalyticsService` / `AnalyticsRegistry`.
3. Add a route + response DTO.

Do not modify existing metric DTOs in breaking ways; prefer new endpoints.
