# Payroll Copilot — AI Architecture

## Core Principle

**AI never validates payroll.** The Validation Engine is 100% deterministic. AI handles:

1. Document understanding (OCR augmentation, PDF splitting)
2. Natural language explanations
3. Contract/policy retrieval augmentation (RAG)
4. Email intent parsing
5. Employee identification assistance (confidence-scored, human-reviewable)

---

## Model Provider Abstraction

```
┌─────────────────────────────────────────┐
│           ModelProvider (Port)           │
│  complete() │ embed() │ structured()    │
└─────────────────┬───────────────────────┘
                  │
    ┌─────────────┼─────────────┬─────────────┐
    ▼             ▼             ▼             ▼
 OllamaProvider OpenAIProvider ClaudeProvider GeminiProvider
 (default)                                    AzureOpenAIProvider
```

### Interface (`application/ports/model_provider.py`)

```python
class ModelProvider(Protocol):
    async def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> CompletionResult: ...

    async def complete_structured(
        self,
        messages: list[Message],
        response_schema: type[BaseModel],
    ) -> StructuredResult: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def embedding_dimensions(self) -> int: ...
```

Every result includes `ConfidenceScore` derived from:
- Logprobs when available
- Schema validation success
- Self-consistency checks (optional double-query for critical extractions)

Configuration via `MODEL_PROVIDER=ollama` and provider-specific env vars.

---

## Agent Framework

Agents are specialized orchestrators — not autonomous validators. Each agent:

- Has a defined input/output schema (Pydantic)
- Uses a system prompt from `config/prompts/`
- Returns structured output + confidence
- Logs to audit trail
- Can be invoked synchronously (small docs) or via Celery (batch)

### Agent Registry

| Agent | Purpose | Model Task | Validation Impact |
|-------|---------|------------|-------------------|
| `PayslipSplitterAgent` | Split bulk PDF into individual slips | Vision + text layout | None — produces documents |
| `PayslipExtractorAgent` | Structure OCR text into payslip fields | Structured extraction | Feeds rule engine input |
| `ContractAnalysisAgent` | Extract clauses for RAG indexing | Long-doc chunking | None — indexes only |
| `ComplianceExplainerAgent` | Human-readable explanation of findings | NLG | None — post-validation |
| `VacationSickLeaveAgent` | Parse leave from emails/reports | Structured extraction | Writes attendance (reviewed) |
| `EmailParserAgent` | Route and classify payroll emails | Classification + extraction | None directly |
| `EmployeeIdentificationAgent` | Match slip to employee record | Fuzzy match + LLM assist | Confidence only |

### Agent Base Class

```python
class BaseAgent(ABC):
    name: str
    system_prompt_path: Path

    async def run(self, input: AgentInput) -> AgentOutput:
        # 1. Load prompt
        # 2. Build messages with input context
        # 3. Call ModelProvider.complete_structured
        # 4. Attach confidence metadata
        # 5. Audit log
```

---

## Payslip Splitter Agent

**Input:** Bulk PDF (storage reference)

**Process:**
1. PyMuPDF extracts page boundaries and text blocks
2. LLM identifies slip boundaries when layout ambiguous (common in scanned batches)
3. Each segment saved as child document
4. Per-segment confidence stored

**Output:** `list[SplitPayslip]` with `{ page_range, employee_hints, confidence }`

Fallback: Fixed pages-per-slip config for known formats (deterministic, no LLM).

---

## OCR Architecture

OCR is a **generic document text extraction layer**. It must not contain payroll
field logic. Downstream consumers (future AI Parser → Structured Payroll Data →
Validation Engine) are separate.

```
Document → OCR → AI Parser (future) → Structured Payroll Data → Validation Engine → AI Explanation
```

```
┌──────────────────┐
│  OCRProvider     │  ← Port (application/ports/ocr.py)
│  extract(...)    │     returns pages[{page, language, text, confidence, lines}]
└────────┬─────────┘
         │
    ┌────┴────┐
    ▼         ▼
 PaddleOCR  Tesseract
 (default)  (Hebrew H1 fallback + optional full provider)
```

- PDF → images via shared PyMuPDF rasterizer (`infrastructure/ocr/pdf_rasterizer.py`)
- Languages: Hebrew, English, Arabic (API: `he` / `en` / `ar` / `auto`)
- **PaddleOCR** is primary for English/Arabic
- **Hebrew** uses **Tesseract fallback** (intentional): PaddleOCR has no official
  production-ready Hebrew recognizer. Responses include the real `engine` and a warning.
- Confidence comes only from the OCR engine — never invented
- Sync API: `POST /api/v1/ocr/extract` (Phase 1). Async Celery worker remains for future wiring.
- Phase 1 does **not** extract payslip fields or feed the Validation Engine.

---

## RAG Pipeline

### Ingestion

```
Document Upload → Text Extraction → Chunk (512 tokens, 64 overlap) →
Embed via ModelProvider → Store in rag_chunks
```

Metadata filters: `organization_id`, `employee_id`, `department_id`, `document_type`.

### Retrieval (during validation)

When a contract rule requires clause lookup:

1. Rule engine emits `RAGQuery` with `{ topic, employee_id, keywords }`
2. Retriever performs hybrid search: vector similarity + keyword (pg_trgm)
3. Top-k chunks returned with relevance score → `contract_rag` confidence
4. Rule evaluates extracted numeric/text constraints from chunks
5. **Rule decision is deterministic** given retrieved text; RAG quality affects confidence, not logic

### Embedding Model

Default: `nomic-embed-text` via Ollama (768 dimensions). Configurable per provider.

---

## MCP — Legal Rule Sync

MCP server exposes tools for external legal source comparison.

### Tools

| Tool | Description |
|------|-------------|
| `compare_vacation_rules` | Diff local `vacation.yaml` vs Kol Zchut |
| `compare_overtime_rules` | Diff local `overtime.yaml` vs gov source |
| `compare_minimum_wage` | Diff `labor_law.yaml` minimum wage section |
| `fetch_legal_source` | Retrieve current external text for review |

### Flow

```
Scheduled job / manual trigger
    → MCP tool fetches external source
    → Diff engine compares structured YAML vs parsed external
    → Creates legal_rule_diff_proposal (status: pending)
    → Notifies accountant
    → Accountant reviews in UI
    → Approve → write YAML + invalidate rule cache
    → Reject → log reason
```

**Never auto-update.** Local YAML remains authoritative until human approval.

---

## Email Agent (n8n Integration)

n8n workflow:
1. IMAP trigger on shared payroll mailbox
2. HTTP Request to `POST /integrations/email/parse-leave`
3. If `action == pending_review` → Slack/email notification to accountant
4. Accountant approves via `POST /attendance/review/{id}/approve`

Email Agent uses `VacationSickLeaveAgent` internally:
- Extract: leave type, dates, partial hours, employee identity from signature
- Confidence < 0.85 → `pending_review`
- Confidence ≥ 0.85 → auto-record with audit flag

---

## Confidence Aggregation

For reports, compute layered confidence:

```
report_confidence = min(
    ocr_field_confidences used in findings,
    identity_match_confidence,
    rule_input_confidence,
    rag_retrieval_confidence  # if contract rules invoked
)
```

Display breakdown in UI/API so accountants know when to manually verify.

---

## Prompt Management

Prompts stored in `config/prompts/{agent_name}/system.md` with version tags.

- Loaded at startup, hot-reload in dev
- Prompt version logged in audit for reproducibility
- Hebrew prompts for HE locale agents; English fallback for structured extraction (JSON schema is locale-neutral)

---

## Local AI (Ollama) Configuration

Default models:
| Task | Model |
|------|-------|
| Structured extraction | `llama3.1:8b` or `qwen2.5:7b` |
| Explanation NLG | `llama3.1:8b` |
| Embeddings | `nomic-embed-text` |
| Vision (splitter) | `llava` (when needed) |

Model selection per agent in `config/ai_models.yaml` — no code changes to swap models.

---

## AI Safety & Data Privacy

- Payroll data never sent to external providers unless org explicitly enables cloud provider
- `MODEL_PROVIDER=ollama` is default; cloud providers require org admin opt-in
- PII redaction layer before external API calls (national ID masked)
- All LLM calls logged with token counts, no raw payroll in logs
- Guest uploads: AI processing on isolated worker pool, data deleted per retention

---

## Testing AI Components

- Agent unit tests: mock ModelProvider with fixture responses
- Golden-file tests for OCR extraction on anonymized sample slips
- Property tests for rule engine (no AI)
- Confidence calibration tracking over time (metrics dashboard)
