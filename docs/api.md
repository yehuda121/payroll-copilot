# Payroll Copilot — API Design

## Conventions

| Aspect | Standard |
|--------|----------|
| Base URL | `/api/v1` |
| Auth | Bearer JWT (`Authorization: Bearer <token>`) |
| Guest auth | `X-Guest-Token` header |
| Content-Type | `application/json` (uploads: `multipart/form-data`) |
| i18n | `Accept-Language: he`, `en`, `ar` |
| Errors | RFC 7807 Problem Details |
| Pagination | `?page=1&page_size=50` → `{ items, total, page, page_size }` |
| Idempotency | `Idempotency-Key` header on POST for uploads |

---

## Authentication

Bearer tokens for authenticated users are **Amazon Cognito** access tokens (verified via JWKS). Guest landing uses a short-lived app-issued JWT from `POST /auth/guest/session` (not Cognito).

### POST /auth/login

Authenticates against Cognito `USER_PASSWORD_AUTH`. Requires `COGNITO_USER_POOL_ID` and `COGNITO_APP_CLIENT_ID`.

```json
// Request
{ "email": "accountant@company.co.il", "password": "..." }

// Response 200
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": { "id": "...", "email": "...", "role": "payroll_accountant", "preferred_locale": "he" }
}
```

### POST /auth/refresh

```json
// Request
{ "refresh_token": "...", "username": "optional@when-client-has-secret.com" }
```

### POST /auth/guest/session

Creates ephemeral guest session for unregistered uploads.

```json
// Response 201
{ "guest_token": "...", "expires_at": "2026-07-06T18:00:00Z" }
```

---

## Organizations (Admin)

### GET /organizations/me

Current user's organization profile.

### PATCH /organizations/me/settings

Update locale, retention, notification preferences.

---

## Employees

### GET /employees

Query: `department_id`, `status`, `search`, `page`, `page_size`.

Roles: `accountant`, `admin`.

### GET /employees/{employee_id}

Roles: `accountant`, `admin`, `employee` (own record only).

### POST /employees/import

Upload Employee Excel. Header-based field detection.

```
multipart/form-data:
  file: <xlsx>
```

```json
// Response 202
{
  "import_id": "...",
  "status": "processing",
  "detected_columns": {
    "employee_number": "מספר עובד",
    "department": "מחלקה",
    "hourly_rate": "שכר שעתי"
  }
}
```

### GET /employees/import/{import_id}

Import status and error report.

---

## Documents

### POST /documents/upload

```
multipart/form-data:
  file: <file>
  document_type: payslip | attendance | contract | national_id | id_appendix | bulk_payslip_pdf
  employee_id: <uuid>  (optional)
  period_year: 2026     (payslip)
  period_month: 6
```

Roles:
- Guest: payslip only, requires guest token
- Employee: own documents
- Accountant: any document, bulk PDF

```json
// Response 201
{
  "document_id": "...",
  "status": "uploaded",
  "processing_job_id": "..."
}
```

### GET /documents/{document_id}

Metadata and processing status. Sensitive file content never returned inline.

### GET /documents/{document_id}/download-url

Pre-signed URL, 5-minute TTL. RBAC enforced.

### GET /documents

List with filters: `document_type`, `employee_id`, `status`, date range.

---

## Validation

### POST /validation/run

Trigger validation for a processed payslip document.

```json
// Request
{
  "document_id": "...",
  "employee_id": "...",       // optional if auto-identified
  "include_historical": true,
  "include_contract_rag": true
}

// Response 202
{
  "validation_run_id": "...",
  "status": "running"
}
```

### GET /validation/runs/{validation_run_id}

```json
// Response 200 (completed)
{
  "id": "...",
  "status": "completed",
  "overall_result": "warnings",
  "overall_confidence": 0.94,
  "findings": [
    {
      "rule_id": "legal.overtime.daily_limit",
      "severity": "warning",
      "message": "שעות נוספות יומיות חרגו מהמגבלה החוקית",
      "expected_value": "≤ 2 hours",
      "actual_value": "3 hours",
      "confidence": 0.98,
      "legal_reference": "חוק שעות עבודה ומנוחה"
    }
  ],
  "explanation": {
    "summary": "...",
    "recommendations": ["..."],
    "confidence": 0.91,
    "locale": "he"
  }
}
```

**Note:** `explanation` is AI-generated and clearly labeled non-binding. Pass/fail comes from `findings` only.

### GET /validation/runs

History for employee or organization. Filters: `employee_id`, `result`, date range.

---

## Batch Processing (Accountant)

### POST /batch/payslips

Upload bulk PDF. Accountant role required.

```
multipart/form-data:
  file: <pdf>
```

```json
// Response 202
{
  "batch_job_id": "...",
  "status": "queued"
}
```

### GET /batch/jobs/{batch_job_id}

```json
{
  "id": "...",
  "status": "validating",
  "total_slips": 312,
  "processed_slips": 187,
  "failed_slips": 2,
  "progress_percent": 59.9
}
```

### GET /batch/jobs/{batch_job_id}/report

Aggregated validation report.

```json
{
  "summary": {
    "total": 312,
    "passed": 280,
    "warnings": 25,
    "critical": 7
  },
  "items": [
    {
      "employee_number": "12345",
      "employee_name": "ישראל ישראלי",
      "department": "משפטים",
      "overall_result": "critical",
      "critical_issues": 1,
      "warnings": 2,
      "recommendations": 3,
      "confidence": 0.89,
      "validation_run_id": "..."
    }
  ]
}
```

### GET /batch/jobs/{batch_job_id}/report/export

Query: `format=pdf|xlsx|json`.

---

## Attendance

### GET /attendance

Employee own records or accountant all. Filters: `employee_id`, `record_type`, date range.

### POST /attendance

Manual entry. Accountant/admin.

### GET /attendance/review-queue

Low-confidence email agent extractions pending human review.

### POST /attendance/review/{record_id}/approve

### POST /attendance/review/{record_id}/reject

---

## AI & Agents

### POST /ai/explain

Generate compliance explanation for a validation run (does not alter results).

```json
{ "validation_run_id": "...", "locale": "he" }
```

### POST /ai/agents/{agent_name}/invoke

Internal/debug endpoint. Agents: `payslip_splitter`, `contract_analyzer`, `compliance_explainer`, `email_parser`, `vacation_sick_leave`.

System role or API key only in production.

---

## RAG

### POST /rag/documents

Ingest contract/policy for embedding. Links to uploaded document.

### GET /rag/search

Query: `q`, `document_type`, `employee_id`, `limit`.

Returns relevant chunks with scores. Used internally by validation; exposed for accountant contract lookup.

---

## Compliance (MCP)

### GET /compliance/legal-rules

List loaded YAML rule files and versions.

### GET /compliance/diff-proposals

Pending MCP diffs. Accountant/admin.

### GET /compliance/diff-proposals/{id}

Full diff detail with external source citation.

### POST /compliance/diff-proposals/{id}/approve

Applies diff to YAML after manual approval. Creates new `legal_rule_versions` entry.

### POST /compliance/diff-proposals/{id}/reject

### POST /compliance/sync-check

Trigger MCP comparison against external sources. Enqueues background job.

---

## Integrations (n8n)

### POST /integrations/email/parse-leave

Webhook for n8n email workflow.

```json
{
  "organization_id": "...",
  "from_email": "employee@company.co.il",
  "subject": "בקשה לחופשה",
  "body_text": "...",
  "received_at": "2026-07-05T09:00:00Z"
}
```

```json
// Response 200
{
  "parsed": {
    "leave_type": "vacation",
    "start_date": "2026-07-15",
    "end_date": "2026-07-17",
    "hours": null
  },
  "confidence": 0.87,
  "action": "pending_review"  // or "recorded" if high confidence
}
```

Authenticated via `X-API-Key` header (system integration key per org).

---

## Jobs

### GET /jobs/{job_id}

Generic async job status (OCR, import, validation, batch).

---

## Health

### GET /health

Liveness.

### GET /ready

Readiness: DB, Redis, storage, Ollama connectivity.

---

## WebSocket (Future)

### WS /ws/batch/{batch_job_id}

Real-time batch progress. Optional v1.1 enhancement; v1 uses polling.

---

## Error Format

```json
{
  "type": "https://payroll-copilot.example/errors/validation-failed",
  "title": "Validation Failed",
  "status": 422,
  "detail": "Document has not completed OCR processing",
  "instance": "/api/v1/validation/run",
  "errors": [
    { "field": "document_id", "message": "Status must be 'processed'" }
  ]
}
```

---

## Rate Limits

| Role | Limit |
|------|-------|
| Guest | 5 uploads / hour / IP |
| Employee | 20 uploads / hour |
| Accountant | 100 uploads / hour |
| Batch | 5 concurrent jobs / org |

---

## OpenAPI

Full spec auto-generated at `/api/v1/openapi.json` and Swagger UI at `/docs`.
