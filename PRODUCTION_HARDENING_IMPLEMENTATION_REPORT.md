# PRODUCTION_HARDENING_IMPLEMENTATION_REPORT.md

# Executive Summary

- **Implemented:** Train A (manual-review org isolation), Train B (manual leave employee org check), Train D (n8n integration rate limits), Train E (typed leave extraction payload), Train F (Content-Disposition filename sanitization), Train I (markSeen toast), Train J (docs alignment).
- **Intentionally not changed:** Train C (idempotency — analysis only), Vacation/Sick Leave frontend duplication refactor, SQLAlchemy/Postgres deletion, committed n8n API key, OTP behavior, Sick→ON_LEAVE reconciliation, Portal RTL/LTR, broad redesigns.
- **Overall verification:** Focused hardening suites **passed** (74 backend + 12 frontend). Broader backend unit run: **511 passed, 8 failed** — failures are pre-existing/unrelated (guest OCR/ephemeral, batch progress). Full frontend `tsc -b` has pre-existing unrelated type errors. No commits created.

# Git / Baseline State

## Initial git status

Working tree was clean on `main` at Phase 0 start (prior to this hardening pass). After implementation, changes are uncommitted in the working tree (see Files Changed).

## Baseline tests (Phase 0)

| Suite | Result |
| --- | --- |
| Manual review / security / leave focused | Mostly green |
| `test_batch_progress_tracks_pipeline_stages` | **Failed baseline** (`progress_percent` asserted `> 0`, got `0.0`) — unrelated |
| Frontend accountant i18n / sick-leave settings | Passed |

## Existing failures discovered before / outside this work

- `tests/unit/test_accountant_portal_foundation.py::test_batch_progress_tracks_pipeline_stages`
- Guest ephemeral / OCR collection and several guest pipeline tests (environment/mock drift)
- `tests/unit/test_guest_cancel_check.py` — collection ImportError (`_client_disconnect_cancel_check` missing)
- Frontend `tsc -b` errors in unrelated modules (`EmployeeManagement` lazy import, digital-form-model, etc.)

These were **not** “fixed” as part of this task.

# Implemented Changes

## Train A — Manual review multi-tenancy

- **Audit finding:** Global manual-review queue allowed cross-org list/resolve.
- **Previous behavior:** Redis index was global; list/resolve not org-scoped.
- **Exact change:** Required `organization_id` on `ManualReviewItem`; org-scoped Redis index `payroll:manual_review:index:{org_id}`; list/resolve require org and fail closed; API uses `principal.organization_id` only.
- **Why minimum safe:** No Redis redesign; disposable dev Redis may invalidate old global index entries (accepted).
- **Files:** `manual_review_queue.py`, `routes/manual_review.py`, `test_manual_review_tenant_isolation.py`, `test_accountant_portal_foundation.py` (resolve test update).
- **Tests:** Org A list/resolve own; Org B cannot list/resolve Org A; no client org override. **4 passed** focused.
- **Regression risk:** Low. Old global-index Redis rows become invisible (dev-acceptable).
- **Note:** No production `enqueue` callers in `backend/src` (queue API + tests only).

## Train B — Manual leave employee organization check

- **Audit finding:** `create_manual` accepted foreign-org `employee_id`.
- **Previous behavior:** Linked `employee_id` without org verification (unlike `link_employee`).
- **Exact change:** When `employee_id` provided, load employee and require `employee.organization_id == organization_id`; else `ValueError("employee_not_found")` before persist. Create routes map that to HTTP 422.
- **Why minimum safe:** Mirrors existing `link_employee` semantics; no leave-domain refactor.
- **Files:** `manage_vacations.py`, `manage_sick_leaves.py`, `routes/vacations.py`, `routes/sick_leaves.py`, vacation + sick unit tests.
- **Tests:** Same-org succeed / foreign-org rejected for both domains. Surrounding vacation+sick suites **29 passed**.
- **Regression risk:** Low; only rejects previously unsafe foreign IDs.

## Train D — Rate limiting for n8n integrations

- **Audit finding:** Integration endpoints lacked rate limits.
- **Previous behavior:** Auth via org API key; no request-volume limit.
- **Exact change:** Existing `RateLimiter` + new setting `rate_limit_integration_per_hour_per_org=600`; `enforce_integration_org_rate_limit` after principal resolve on all integration routes (parse-leave, mailbox-config, inbound-vacation, inbound-leave/batch, events, mailbox/health).
- **Why threshold is safe:** Recommended n8n path is ~1 batch/poll + health + optional events. At 1-minute polling, tens of requests/hour is typical; batch packs ≤100 items/request. **600/hour/org** (~10/min average) leaves catch-up headroom without allowing flood loops. Scoped by **organization_id** so one tenant cannot starve another.
- **Files:** `settings.py`, `rate_limit_deps.py`, `integrations.py`, `test_integration_rate_limit.py`.
- **Tests:** Normal traffic OK; exceed → 429 `rate_limit_exceeded`; org A vs org B isolation. Security suites green.
- **Regression risk:** Low in production (limits already enforced only when `rate_limit_enforced`). Dev typically disabled.

## Train E — Typed integration extraction payload

- **Audit finding:** `extraction: dict[str, Any]` deferred type errors into deep processing.
- **Previous behavior:** `.get()` on untyped dict; bad `confidence` could fail late.
- **Exact change:** `LeaveExtractionPayload` Pydantic model (all fields optional; `extra="ignore"`) on inbound-vacation and batch item requests.
- **Why minimum safe:** Matches live n8n contract; no new required fields; preserves missing-field behavior.
- **Files:** `integrations.py`, `test_leave_extraction_payload.py`.
- **Tests:** Valid payload; empty extraction; malformed confidence rejected; batch empty extraction OK. **Passed** with sick/batch suite.
- **Regression risk:** Low; numeric strings may still coerce to float (Pydantic default) — intentional compatibility.

## Train F — Filename / Content-Disposition safety

- **Audit finding:** Raw `original_filename` in `Content-Disposition` (header injection).
- **Previous behavior:** Documents route interpolated raw name; batch only stripped `"`.
- **Exact change:** `sanitize_content_disposition_filename` strips path components, quotes, CR/LF, controls; used by documents + batch preview responses.
- **Why minimum safe:** Local helper; no file-management redesign.
- **Files:** `content_disposition.py`, `documents.py`, `batch.py`, `test_content_disposition.py`.
- **Tests:** 5 focused passed.
- **Regression risk:** Very low.

## Train I — Small failure surfacing (markSeen)

- **Audit finding:** markSeen failures only `console.error`.
- **Previous behavior:** Silent badge staleness possible.
- **Exact change:** Error toast via existing `showToast` + new i18n keys for vacations and sickLeaves (en/he/ar).
- **Why minimum safe:** Local catch-block only; no leave business logic change.
- **Skipped (reported):** `PortalShell` unseenCount poll zeros badge on failure every 60s — toasting would spam; left as soft-fail (DEFERRED).
- **Files:** `Vacations.tsx`, `SickLeaves.tsx`, `accountant.{en,he,ar}.json`.
- **Tests:** i18n parity **7 passed**.
- **Regression risk:** Low; users may see toast on transient markSeen failures.

## Train J — Documentation alignment

- **Audit finding:** Docs still described `parse-leave` as primary persist path.
- **Exact change:** Updated `docs/architecture.md`, `docs/ai-architecture.md`, `docs/api.md`, `ARCHITECTURE.md` to state canonical `inbound-leave/batch`, compat `inbound-vacation`, extract-only `parse-leave`.
- **Not changed:** Compatibility routes remain; README already largely accurate.

# Skipped Findings

| Finding | Why skipped | Remaining risk | Approval needed |
| --- | --- | --- | --- |
| Train C idempotency implementation | Explicit analysis-only | Concurrent duplicate leave rows possible | Yes — see Train C |
| FE Vacations/SickLeaves merge | Explicit analysis-only | Duplication maintenance cost; some Sick Leave i18n leakage | Yes — see proposal |
| SQLAlchemy/Postgres removal | Not PROVEN_DEAD | Legacy deps remain in image/tests | Deletion approval only if proven dead later |
| Committed n8n API key / rotation / history scrub | Forbidden | Secret exposure if still in history | Separate security process |
| Notification OTP behavior | Forbidden | As audited | Product decision |
| Sick Leave → ON_LEAVE reconcile | Forbidden | Leave status edge cases | Product decision |
| Portal RTL/LTR | Forbidden | UX | Product/design |
| PortalShell badge poll silent zero | Broader than small toast; spam risk | Badge may show 0 on transient errors | Optional UX approval |
| Pre-existing failing unit/tsc | Out of scope / unsafe to “fix” blindly | CI noise | Separate cleanup |

# Train C — Idempotency / Concurrency Deep Analysis

## Current behavior

Canonical path: n8n → `POST /api/v1/integrations/email/inbound-leave/batch` (compat: `inbound-vacation`) → `IngestLeaveBatchUseCase` / `ManageVacationsUseCase.ingest_inbound` / `ManageSickLeavesUseCase.ingest_inbound` → `get_by_provider_message` (GSI2) → unconditional `put_item` save → response.

Vacation keys: PK `ORG#…`, SK `VAC#{uuid}`, GSI2 `ORG#…#VMSG#{provider}#{message_id}`.  
Sick Leave: SK `SICK#{uuid}`, GSI2 `…#SMSG#…`.  
GSI2 is **not** a uniqueness constraint; GSI reads are eventually consistent; saves have **no** `ConditionExpression`. **No claim/lock exists today.**

Critical race:

```text
A: lookup → none
B: lookup → none
A: PutItem random UUID
B: PutItem random UUID  → duplicate durable rows
```

## Scenario matrix (Vacation ≈ Sick Leave)

| Scenario | Outcome |
| --- | --- |
| Simultaneous identical requests | Both can persist |
| n8n retry after timeout | Usually DUPLICATE after GSI visibility; not linearizable |
| Success but lost response | Retry often DUPLICATE; can still race |
| Duplicate provider_message_id | Sequential OK; concurrent/index-lag can duplicate |
| Failure before persistence | Retry safe (possible orphan large-body S3 object) |
| Failure during persistence | Ambiguous if Dynamo committed |
| Failure after claim before leave save | **N/A today** (no claim) |
| Crash after save before audit/overlap | Leave durable; repair may be skipped; batch may mis-report “not stored” |

## Solution proposals

### Solution 1 (recommended) — TransactWrite idempotency item + leave

- **Mechanism:** Hashed base-table SK `LEAVE_IDEMP#{domain}#{sha256(provider||msg)}` + leave item in one DynamoDB transaction with `attribute_not_exists` on idempotency key; on conflict strongly read leave ID and return DUPLICATE.
- **Files:** ports, dynamo client/transaction, keys, vacations.py, sick_leaves.py, both manage use cases, tests.
- **Schema:** No new table/GSI; sparse items.
- **Guarantee:** Exactly one leave per (org, domain, provider, message_id).
- **Failure/retry/recovery:** Pre-tx fail → retry safe; post-tx lost response → DUPLICATE; **no claim-without-leave**.
- **Complexity / risk / migration:** Medium / low schema risk / no migration.
- **Pros:** Strongest correctness without claim gap. **Cons:** Transaction error handling + tests.

### Solution 2 — Deterministic leave PK + conditional put

- Derive UUIDv5 from org/domain/provider/message; `ConditionExpression attribute_not_exists`.
- Strong for new rows; awkward historical random IDs; couples public entity ID to provider identity.
- Lower code complexity, higher domain-model risk.

### Solution 3 — PROCESSING claim + lease

- Conditional claim → save leave → COMPLETED; lease takeover for stale PROCESSING.
- High complexity; **dangerous** if simplistic.

### Danger: CLAIM → leave save fails → retry sees claim → leave lost

A naive “put claim if absent, then save leave, treat claim as duplicate” permanently suppresses an email when the claim survives and the leave does not. DynamoDB TTL is not a timely unlock. **Do not implement claim-before-save without atomic completion or exhaustive lease recovery.**

## Recommendation

**Solution 1 (atomic idempotency + leave transaction)** is the safest minimal production fix. Also treat post-save audit/overlap as best-effort or outbox repair so failures after commit do not lie about durability.

**REQUIRES USER APPROVAL BEFORE IMPLEMENTATION.**

# Vacation / Sick Leave Frontend Duplication Proposal

## Assessment

`Vacations.tsx` / `SickLeaves.tsx` are near-parallel (~1096 lines each). CSS is largely identical. Domains correctly keep separate services, caches, endpoints, notification preference fields, and i18n namespaces.

**Truly identical:** orchestration flow, table/dialog layout, status model, attention rendering patterns.  
**Must stay domain-owned:** services, caches, notify prefs, request IDs (`vacation_ids` vs `sick_leave_ids`), terminology.  
**Known i18n leakage in Sick Leave strings** (some “vacation” wording) — fix as deliberate i18n step, not as a generic component side effect.

## Safe strategy

Share **presentation primitives** (`leave-ui/*`) that receive already-translated labels + callbacks. Keep domain containers owning services/caches. **Do not** build one `LeaveManagementPage<T>` that can accept the wrong service.

### Proposed structure

```text
pages/accountant/Vacations.tsx          # vacation-only imports
pages/accountant/SickLeaves.tsx         # sick-leave-only imports
pages/accountant/leave-ui/
  LeaveToolbar.tsx
  LeaveRequestsTable.tsx
  LeaveRequestDetailDialog.tsx
  LeaveSettingsDialog.tsx (slot for domain settings body)
  ManualLeaveDialog.tsx
  LeaveManagement.css
```

### Migration sequence

1. Characterization tests (terminology, endpoints, cache isolation).
2. Neutralize shared CSS.
3. Extract display primitives.
4. Extract dialogs as label/callback driven.
5. Slim pages after parity.
6. Fix Sick Leave i18n leakage separately.

### Tests / risks / size

Isolation tests for imports, payload property names, terminology EN/HE/AR; dialog/action parity. Risks: shared `t` namespace construction, shared cache singleton, settings key mixup. Estimated **medium** (8–12 files, ~500–800 lines moved/tested).

**REQUIRES USER APPROVAL BEFORE IMPLEMENTATION.**

# SQLAlchemy / Postgres / Alembic Analysis

Runtime and analytics use **DynamoDB**. Postgres/SQLAlchemy/Alembic remain **legacy tooling** retained by tests and optional migrations. **No component was deleted** (none conclusively PROVEN_DEAD).

| Component | Classification | Evidence | Used By | Safe To Delete? | Action Taken |
| --- | --- | --- | --- | --- | --- |
| DynamoDB repos / DI | ACTIVE_RUNTIME / ACTIVE_ANALYTICS | FastAPI DI, analytics use cases | API, workers, analytics | No | None |
| `database.py` / `DATABASE_URL` | REQUIRED_BY_TESTS / LEGACY_BUT_REFERENCED | pytest fixtures; optional env | Legacy tests, Alembic | No | None |
| `models.py`, mappers, SQL repos | REQUIRED_BY_TESTS | Seed + legacy integration tests | Tests, Alembic metadata | No | None |
| Alembic env/versions/ini | REQUIRED_BY_MIGRATIONS | `alembic upgrade head` | Compose `migrate` profile | No | None |
| Compose postgres / migrate | LEGACY_BUT_REFERENCED / REQUIRED_BY_MIGRATIONS | `legacy-postgres` profile | Optional ops | No | None |
| sqlalchemy/asyncpg/alembic/pgvector deps | LEGACY_BUT_REFERENCED | pyproject | Tests/migrations | No | None |
| Docs claiming Postgres as primary SoT | LEGACY_BUT_REFERENCED | Partially stale | Docs | No (docs cleanup separate) | Leave-ingest docs fixed only |
| CI config for Postgres | PROVEN_DEAD (N/A) | No CI configs found | — | N/A | None |

# Security Changes

1. Manual-review list/resolve tenant isolation.
2. Manual vacation/sick create rejects foreign-org `employee_id`.
3. Org-scoped integration rate limiting (600/hour/org when enforced).
4. Content-Disposition filename sanitization.
5. Typed extraction boundary validation (malformed types → 422).

# Data Integrity Changes

- Train B prevents cross-tenant employee linkage on manual create.
- Train C **not** implemented — provider_message_id races remain.

# UI / Error Handling Changes

- markSeen failure → error toast on Vacations and Sick Leaves pages.
- PortalShell badge poll soft-fail unchanged.

# i18n Changes

Added (en/he/ar, both `accountant.vacations` and `accountant.sickLeaves`):

- `toastMarkSeenFailed`

# Documentation Changes

| File | Why |
| --- | --- |
| `docs/architecture.md` | Canonical batch ingest path |
| `docs/ai-architecture.md` | Replace obsolete parse-leave auto-record narrative |
| `docs/api.md` | Document batch + compat + extract-only parse-leave |
| `ARCHITECTURE.md` | Align leave SoT + ingest endpoints |

# Files Changed

| File | Reason |
| --- | --- |
| `backend/.../manual_review_queue.py` | Org-scoped queue |
| `backend/.../routes/manual_review.py` | Principal org scoping |
| `backend/.../manage_vacations.py` | create_manual org check |
| `backend/.../manage_sick_leaves.py` | create_manual org check |
| `backend/.../routes/vacations.py` | 422 mapping |
| `backend/.../routes/sick_leaves.py` | 422 mapping |
| `backend/.../settings.py` | Integration rate limit setting |
| `backend/.../rate_limit_deps.py` | enforce helper |
| `backend/.../routes/integrations.py` | Rate limit + typed extraction |
| `backend/.../content_disposition.py` | **New** sanitizer |
| `backend/.../routes/documents.py` | Use sanitizer |
| `backend/.../routes/batch.py` | Use sanitizer |
| `backend/tests/unit/test_manual_review_tenant_isolation.py` | **New** |
| `backend/tests/unit/test_integration_rate_limit.py` | **New** |
| `backend/tests/unit/test_leave_extraction_payload.py` | **New** |
| `backend/tests/unit/test_content_disposition.py` | **New** |
| `backend/tests/unit/test_vacation_manage.py` | Train B tests |
| `backend/tests/unit/test_sick_leave_and_batch.py` | Train B tests |
| `backend/tests/unit/test_accountant_portal_foundation.py` | Manual review API update |
| `frontend/.../Vacations.tsx` | markSeen toast |
| `frontend/.../SickLeaves.tsx` | markSeen toast |
| `frontend/.../accountant.{en,he,ar}.json` | toastMarkSeenFailed |
| `docs/*`, `ARCHITECTURE.md` | Train J |

# Files Deleted

None.

# Tests

## Before (baseline)

- Hardening-related areas mostly green.
- Known unrelated failure: batch progress percent.

## After each train

| Train | Result |
| --- | --- |
| A | 4 passed |
| B | 29 passed (vacation+sick suites) |
| D | 24 passed with phase0/1 security |
| E | 23 passed with sick/batch + rate limit |
| F | 5 passed |
| I | 7 i18n tests passed |

## Final suites

| Suite | Result |
| --- | --- |
| Focused hardening backend (10 files) | **74 passed** |
| Frontend i18n + document-card-status | **12 passed** |
| Backend `tests/unit` (excluding guest_cancel_check + accountant seed) | **511 passed, 8 failed** (unrelated guest/OCR/batch progress) |
| Frontend `tsc -b` | **Failed** — pre-existing unrelated errors |
| Frontend full vitest / backend full integration | **Not run** (time + known collection/env issues) |
| Docker/build | **Not run** |

# Remaining Risks

1. Leave ingest concurrent duplicates (Train C).
2. Post-save failure can still return misleading “not stored” in batch path.
3. Manual-review enqueue unused in production code paths (API still hardened).
4. PortalShell badge soft-zeros on unseenCount errors.
5. Pre-existing unit/tsc failures reduce confidence of “full green CI.”
6. Committed/historical n8n API key remains out of scope.
7. Sick Leave FE i18n still contains some vacation wording (pre-existing).

# Decisions Required From User

1. ~~**Train C**~~ — **IMPLEMENTED** in follow-up (atomic TransactWrite).
2. ~~**Vacation/Sick Leave frontend duplication**~~ — **IMPLEMENTED** in follow-up (presentation primitives only).
3. Optional: approve PortalShell badge failure UX (toast vs keep soft-zero).
4. Optional: separate cleanup for pre-existing failing guest/OCR/batch-progress tests and frontend `tsc` errors.
5. Optional: secret rotation / git-history scrub for n8n API key (explicitly out of this task).

# Final Status

| Area | Status |
| --- | --- |
| Manual-review multi-tenancy | **Resolved** |
| Manual create foreign employee_id | **Resolved** |
| Integration rate limits | **Resolved** |
| Typed extraction payload | **Resolved** |
| Content-Disposition safety | **Resolved** |
| markSeen silent failure (pages) | **Resolved** (nav badge poll deferred) |
| Docs leave-ingest drift | **Resolved** (leave path); broader Postgres docs still legacy |
| Train C concurrency | **Requires approval** |
| FE leave page duplication | **Requires approval** |
| SQLAlchemy/Postgres removal | **Intentionally accepted / deferred** (not proven dead) |
| Forbidden audit items (API key, OTP, sick reconcile, RTL) | **Intentionally accepted / out of scope** |
| Implementation trains stopped for safety | **None** of A/B/D/E/F/I/J; C and FE refactor never started by design |

---

# Approved Follow-up Implementation

_Date: 2026-07-26. Implements the two items previously marked REQUIRES USER APPROVAL after explicit user approval._

## Train C — Atomic Idempotency

### Previous behavior

Inbound vacation/sick leave used GSI2 `get_by_provider_message` then unconditional `put_item`. Concurrent requests or index lag could create multiple leave rows for the same org/provider/message.

### Final implementation

`create_inbound` on both Dynamo repositories atomically writes:

1. Idempotency item — `PK=ORG#{org}`, `SK=LEAVE_IDEMP#{domain}#{sha256(provider\\0message)}`, `leave_id=…`
2. Leave item — existing `VAC#` / `SICK#` item shape (unchanged)

via `DynamoTable.transact_put_items` with `ConditionExpression: attribute_not_exists(PK)` on **both** puts.

On `DynamoTransactionCanceledError`, strongly read the idempotency item (then leave by `leave_id`), else fall back to GSI2 lookup, and return `(existing, created=False)`.

Use cases call `create_inbound` instead of `save` for email ingest. When `created=False`, return existing `DUPLICATE` semantics without post-save audit/overlap for the loser.

Manual `save` / updates remain unconditional puts (unchanged).

### Exact DynamoDB transaction design

- Thin `DynamoTable.transact_put_items` wrapping `client.transact_write_items` + TypeSerializer.
- All-or-nothing: if the transaction fails before commit, **neither** item is stored.
- Condition failure → no orphan marker; caller resolves existing leave.

### Why IDEMPOTENCY SUCCESS + LEAVE FAILURE cannot leave an orphan marker

Both Put operations are in a **single** TransactWriteItems. DynamoDB does not commit a partial transaction. There is no independent “claim then save” sequence.

### Organization isolation

Idempotency PK is `ORG#{organization_id}`; identical provider messages in different orgs are independent.

### Duplicate / failure / retry semantics

| Case | Result |
| --- | --- |
| First ingest | create leave + marker |
| Retry / lost response | `DUPLICATE`, same leave id |
| Concurrent double | one winner, one `created=False` |
| Pre-commit tx failure | nothing stored; retry can succeed |
| Cross-domain same message | vacation and sick_leave markers are separate domains |

### Files changed

- `dynamodb/client.py`, `keys.py`, `vacations.py`, `sick_leaves.py`
- ports `vacation_requests.py`, `sick_leave_requests.py`
- `manage_vacations.py`, `manage_sick_leaves.py`
- fakes in vacation/sick/leave_management tests
- `tests/unit/test_leave_inbound_idempotency.py` (new)

### Tests executed / results

- Focused idempotency + vacation + sick + leave_management + security: **70 passed**
- No Train C regressions observed

## Vacation / Sick Leave Presentation Refactor

### What was shared

- `leave-ui/LeaveManagement.css` (shared styles; `vacations-*` and `sickLeaves-*` aliases)
- `leave-ui/LeavePresentation.tsx`: `LeaveToolbar`, `LeaveManualEntryFields`, `LeaveUnsavedChangesDialog`, `LeaveLoadError`
- Presentation helpers in `leave-management-ui.ts`: status/severity/attention/employee label helpers

### What intentionally remains separate

- `VacationsPage` / `SickLeavesPage` domain containers
- `vacationsService` vs `sickLeavesService`
- `leave-management-cache` vs `sick-leave-management-cache`
- Domain i18n namespaces (`accountant.vacations.*` vs `accountant.sickLeaves.*`)
- Settings preference field names and notify toggles
- Detail dialog / settings dialog business wiring (not forced into a generic business page)

### Component structure

```text
pages/accountant/Vacations.tsx          # vacation-only
pages/accountant/SickLeaves.tsx         # sick-leave-only
pages/accountant/leave-ui/
  LeaveManagement.css
  LeavePresentation.tsx
Vacations.css / SickLeaves.css          # thin @import re-exports
```

### Domain-isolation guarantees / tests

`leave-domain-isolation.test.ts` proves:

- Vacations source never imports sickLeaves service/cache or `accountant.sickLeaves.`
- SickLeaves source never imports vacations service/cache or `accountant.vacations.`
- Shared helpers take domain i18n prefix from the caller

### i18n / behavior preservation

No translation keys renamed. RTL/LTR untouched. Endpoints/caches/actions unchanged. Shared components receive already-translated labels.

### Frontend tests

- leave-domain-isolation + leave-management-ui + accountantLabels: **18 passed**

## Problems Encountered

None that required stopping a train. DynamoTable lacked `transact_write`; adding a thin wrapper matched the approved design (not a broad abstraction).

## Files Changed (this follow-up)

Backend: client, keys, vacation/sick repos, ports, manage use cases, fakes, `test_leave_inbound_idempotency.py`, extra ingest race tests.

Frontend: Vacations/SickLeaves pages, leave-ui/*, leave-management-ui.ts, leave-domain-isolation.test.ts, CSS re-exports.

## Files Deleted

None. Old page CSS files retained as `@import` shims.

## Tests

| Suite | Result |
| --- | --- |
| Baseline vacation/sick before changes | 30 passed |
| Train C focused + leave regression | 70 passed |
| Frontend isolation + i18n | 18 passed |
| Full backend/frontend suites | Not fully re-run; pre-existing guest/OCR/tsc failures remain |

## Remaining Risks

- Legacy leave rows created before idempotency markers still rely on GSI2 for early duplicate detection; new races are transaction-protected.
- Post-save audit/overlap failures can still occur after a durable create (pre-existing).
- Detail/settings dialogs still duplicated (intentionally; mixed with domain logic).

## Remaining Pre-existing Failures

Unchanged from prior report: batch progress percent, guest OCR/ephemeral tests, frontend `tsc` unrelated errors, guest_cancel_check import error.

## Final Status (follow-up)

- **Train C:** COMPLETE — all new tests pass
- **Frontend refactor:** COMPLETE (presentation primitives extracted; domain containers remain) — isolation tests pass
- **Regressions introduced by this work:** none observed in executed suites
- **Requires user approval:** none for these two trains
