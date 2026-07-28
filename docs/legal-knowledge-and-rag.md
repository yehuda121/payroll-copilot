# Legal Knowledge + Vector RAG + RAGAS Evaluation

Final production-oriented documentation for the Legal Knowledge platform.

## Non-negotiable boundaries

- Deterministic payroll validation remains authoritative for PASS/FAIL.
- Approved YAML labor-law packs + temporal rule catalog are the legal Source of Truth.
- The vector store is an INDEX / projection only.
- Sync may fetch, normalize, compare, discover, and create **proposals** only.
- Only `developer_admin` (`UserRole.ADMIN`) may approve/reject and activate versions.
- Never invent statutes, URLs, effective dates, RAG contexts, or RAGAS scores.
- Fetched external pages are **UNTRUSTED DATA** (SSRF-guarded HTTPS allowlist; analyzer ignores embedded instructions).

## Architecture (as implemented)

```text
Approved YAML rules ──► LegalRuleVersionCatalog (temporal overlay + snapshots)
        │
        ├── Deterministic validation engine (unchanged semantics)
        │
        └── LegalRagIndexer ──► ChromaDB persistent collection (production)
                                    │         └── NumPy file adapter (tests/local)
                                    └── VersionAwareLegalRetriever ──► LangGraph
                                            └── YAML keyword fallback (observable)

Legal Source Registry ──► LegalKnowledgeSyncService ◄── Admin manual / Celery Beat
        │                         │
        │                         ├── hash unchanged → NO_CHANGE (no AI)
        │                         ├── hash changed → diff + AI analyzer → proposals
        │                         └── never auto-approves
        │
        └── developer approve → new version + close previous valid_to
                              → audit + re-index affected rule version

Durable metadata ──► DynamoDB LEGAL#SYSTEM (production default)
        └── file adapter when LEGAL_KNOWLEDGE_STORE=file (tests/local only)

Benchmark_v1 ──► RagEvaluationService (real vector path; YAML fallback = case error)
        ├── RAGAS adapter (4 metrics; UNAVAILABLE/ERROR never coerced to 0)
        └── Temporal Retrieval Accuracy
```

## Source coverage matrix (deterministic rules)

| internal_rule_id | topic | watched official | interpretation | discovery | status |
|---|---|---|---|---|---|
| legal.minimum_wage | minimum wage | watch_minimum_wage | — | kolzchut_base | watched **SOURCE_UNVERIFIED**; discovery verified |
| legal.overtime.daily_limit | overtime limits | watch_overtime_daily | — | kolzchut_base | SOURCE_UNVERIFIED |
| legal.overtime.weekly_limit | overtime limits | watch_overtime_daily | — | kolzchut_base | SOURCE_UNVERIFIED |
| legal.overtime.rate_tier_1 | overtime pay | watch_overtime_rates | — | kolzchut_base | SOURCE_UNVERIFIED |
| legal.overtime.rate_tier_2 | overtime pay | watch_overtime_rates | — | kolzchut_base | SOURCE_UNVERIFIED |
| legal.vacation.annual_entitlement | annual leave | watch_vacation | — | kolzchut_base | SOURCE_UNVERIFIED |
| legal.vacation.monthly_accrual | annual leave | watch_vacation | — | kolzchut_base | SOURCE_UNVERIFIED |
| legal.sick_leave.annual_entitlement | sick leave | watch_sick_leave | — | kolzchut_base | SOURCE_UNVERIFIED |
| legal.pension.* (3) | mandatory pension | watch_pension | — | kolzchut_base | SOURCE_UNVERIFIED |
| legal.tax.* (2) | tax/payroll | watch_tax | — | kolzchut_base | SOURCE_UNVERIFIED |
| legal.transportation.* (2) | travel reimbursement | watch_transportation | — | kolzchut_base | SOURCE_UNVERIFIED |
| legal.youth.* (2) | youth employment | watch_youth | — | kolzchut_base | SOURCE_UNVERIFIED |

Topics **not** in the deterministic engine (weekly rest, holiday pay, recreation pay, breaks, wage timing, payslip fields, deductions, employment-terms notice) have **no** fake rules or URLs.

### Verified sources

| source_id | URL | Verification |
|---|---|---|
| kolzchut_base | `KOL_ZCHUT_BASE_URL` (default https://www.kolzchut.org.il) | Smoke HTTP 200; authority **SECONDARY_INTERPRETATION** |

Official government watched URLs: intentionally **unconfigured** — `SOURCE_UNVERIFIED` (no invention).

## MCP / fetch connector

- `backend/mcp/legal_sync_server.py` — **compare-only** MCP tools over local YAML; does **not** HTTP-fetch.
- Production fetch path: `LegalKnowledgeSyncService._fetch` via httpx with SSRF guards (HTTPS only, allowlisted registry hosts, block private/localhost, size/timeout limits, limited redirect re-validation).

## DynamoDB persistence

Partition `PK=LEGAL#SYSTEM`:

| SK prefix | Entity |
|---|---|
| SYNCRUN# / RUNID# | sync runs |
| PROPOSAL# / PROPID# | proposals |
| SRCSTATE# / SNAP# | source hash + normalized snapshot (capped) |
| DISCOVERY# | discovery dedup |
| EVALRUN# / EVALID# / EVALCASE# | evaluation |
| EVALLOCK | concurrent eval lock |
| VECTORHEALTH | index health projection |

YAML packs remain filesystem SoT for validation. Temporal catalog remains filesystem overlay under `.versions/`.

`LEGAL_KNOWLEDGE_STORE=dynamodb` (default) | `file` (tests/local). Production does **not** silently fall back to files on Dynamo failure.

## Vector DB

**Production:** ChromaDB persistent (`LEGAL_VECTOR_BACKEND=chroma`, path `data/chroma_legal`, collection `approved_legal_knowledge_v1`).

Relative persist paths resolve against process CWD (`WORKDIR=/app` in Docker) so the named volume `legal_chroma_data` → `/app/data/chroma_legal` is used. Do not resolve via `Path(__file__)` — that points into `site-packages` when the package is installed and silently writes outside the volume.

On API startup, if the live vector count is empty, the service fail-open bootstraps via `LegalRagIndexer.rebuild_all()` (Admin rebuild remains available).

**Why Chroma:** persistent, cosine HNSW, metadata filters, Docker volume friendly, no revived Postgres, no managed SaaS required.

**Tests/local:** `LEGAL_VECTOR_BACKEND=numpy`.

Rebuild/reconcile via Admin → Vector Index (idempotent upsert by `chunk_id`).

## RAGAS

- Pin: `ragas>=0.2.15,<0.3`
- Metrics: Faithfulness, Context Precision, Context Recall, Answer Relevancy
- Project metric: Temporal Retrieval Accuracy
- Benchmark: `benchmark_v1` — **24** enabled cases (grounded in approved YAML)
- Eval path rejects silent YAML fallback (`evaluation_used_yaml_fallback`)
- If judge/provider missing: metrics = **UNAVAILABLE** (never 0)

## Scheduled sync

Celery task `sync_legal_rules_mcp` → same `LegalKnowledgeSyncService`.

`LEGAL_SYNC_SCHEDULE_ENABLED=false` by default until official watched sources are verified.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| LEGAL_KNOWLEDGE_STORE | dynamodb | file for tests |
| LEGAL_VECTOR_BACKEND | chroma | numpy for tests |
| LEGAL_VECTOR_PERSIST_PATH | data/chroma_legal | Docker volume |
| LEGAL_SYNC_SCHEDULE_ENABLED | false | keep off until sources verified |
| RAGAS_ENABLED | true | eval only |
| KOL_ZCHUT_BASE_URL | https://www.kolzchut.org.il | discovery |

## Admin UI

- `/admin/legal-knowledge`
- `/admin/rag-evaluation`

## How to deploy

1. Install backend deps including `chromadb`, `ragas`, `datasets`.
2. Ensure DynamoDB table reachable.
3. Set `LEGAL_KNOWLEDGE_STORE=dynamodb`, `LEGAL_VECTOR_BACKEND=chroma`.
4. Mount/persist `data/chroma_legal`.
5. Configure embedding-capable model provider.
6. Admin → Rebuild vector index.
7. Optionally configure verified official watched URLs, then consider enabling schedule.
8. Run RAG Evaluation when judge/provider available.

## Recovery

- Rebuild index from approved catalog (Admin).
- Sync history/proposals recoverable from Dynamo `LEGAL#SYSTEM`.
- YAML validation packs remain independent of vector/sync failures.
