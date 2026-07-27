"""Docs: Legal RAG local multilingual reranker (Phases 1–3)."""

# Legal RAG reranker

## Status

| Phase | Status |
|-------|--------|
| Phase 1 — immutable BEFORE baseline | Done (`baseline_91cbde6f-…`) |
| Phase 2 — abstraction + fail-open | Done (flag default **off**) |
| Phase 3 — local multilingual model | Done (flag default **off**) |
| Phase 4 — production rollout | Not started |

## Selected model

**`BAAI/bge-reranker-v2-m3`**

Why:

- True multilingual cross-encoder (Hebrew + English + cross-lingual), MIRACL-trained lineage
- MIT-friendly open weights suitable for commercial self-host / AWS (unlike Jina v2 base self-host **CC-BY-NC-4.0**)
- Smaller/lighter than LLM rerankers (Gemma/MiniCPM variants)
- CPU-feasible for Top-20 → Top-5; GPU optional via `LEGAL_RAG_RERANK_DEVICE=cuda`

Rejected / deferred:

- `jina-reranker-v2-base-multilingual` — strong and faster, but **non-commercial** self-host license
- `bge-reranker-base/large` — primarily Chinese/English, weak Hebrew justification
- Hosted APIs (Cohere/Jina API) — out of scope for local/Docker-first path

## Pipeline

```
query → embed → authorized vector search (approval/date/scope)
      → Top-20 candidates
      → LegalChunkReranker (optional)
      → Top-5
      → existing assistant / RAGAS flow
```

When `LEGAL_RAG_RERANK_ENABLED=false` (default): pool size equals caller `top_k` (Phase 1 behavior). No model load.

## Configuration

```env
LEGAL_RAG_RERANK_ENABLED=false
LEGAL_RAG_RETRIEVAL_TOP_K=20
LEGAL_RAG_RERANK_TOP_N=5
LEGAL_RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3
LEGAL_RAG_RERANK_TIMEOUT_MS=15000
LEGAL_RAG_RERANK_DEVICE=          # empty = auto; use cpu or cuda
```

Set model to `noop` to exercise plumbing without weights.

## Dependencies / weights

Optional extra (not in default Docker image):

```bash
cd backend
pip install ".[legal-rerank]"
```

Weights download from Hugging Face on first use into the standard cache:

- `HF_HOME` / `TRANSFORMERS_CACHE` / `~/.cache/huggingface`

Production:

- Pre-warm cache in the AMI/image build **or** mount a persistent volume at the HF cache path
- Do not bake secrets; weights are public
- Keep `LEGAL_RAG_RERANK_ENABLED=false` until Phase 4 decision

Docker impact: `sentence-transformers` pulls **torch** (~1–2GB+ layers). Prefer a dedicated worker image or optional stage rather than forcing every API container to include torch until rollout.

## Fail-open

Load failure, timeout, NaN/mismatched scores, foreign `chunk_id` → original vector order; request continues (`rerank_fallback=true`).

## Evaluation

Immutable BEFORE snapshot:

`backend/data/rag_eval_baselines/baseline_91cbde6f-ca42-4cba-a83c-3fce49ce08dd.json`

AFTER run (Phase 3 A/B):

`backend/data/rag_eval_baselines/phase3_ab_29e2676a-17f9-45b6-aaae-8e2a81fb9299.json`

| Metric | BEFORE | AFTER | Δ |
|--------|--------|-------|---|
| HitRate@5 | 0.955 | 0.955 | 0 |
| Recall@5 | 0.955 | 0.955 | 0 |
| MRR | 0.932 | 0.879 | **−0.053** |
| Temporal | 0.955 | 0.955 | 0 |
| Faithfulness | 0.729 | 0.706 | −0.023 |
| Context Recall | 0.386 | 0.304 | −0.082 |
| Answer Relevancy | 0.283 | 0.485 | +0.201 |
| Context Precision | 0.065 | 0.130 | +0.065 |

Ranking deltas: 23/24 cases changed order; **0** first-relevant improvements; **2** regressions (`misleading_unrelated` 1→3, `ambiguous_overtime` 1→2); **0** fail-open fallbacks. Model warm ~8.6s; full eval ~6.6 min (includes RAGAS).

### Decision

**REJECT RERANKER** for default/production enablement on this corpus+benchmark: primary retrieval quality did not improve and **MRR regressed**. Keep the adapter available behind the flag for future tuning; leave `LEGAL_RAG_RERANK_ENABLED=false`.

Re-run A/B:

```bash
cd backend
py -3 scripts/dev/run_rag_baseline_phase3_ab.py
```

Smoke (downloads model):

```bash
py -3 -m pytest tests/integration/test_legal_rerank_model_smoke.py -m real_model -q
```
