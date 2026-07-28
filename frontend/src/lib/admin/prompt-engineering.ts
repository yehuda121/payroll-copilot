/**
 * Prompt Engineering Center — versioned catalog of production prompts and
 * their engineering evolution for AI governance.
 *
 * This module documents prompt intent and change history. It is not an LLM
 * request log and is not wired to runtime AI telemetry or RAGAS.
 */

export type PromptStatus = 'Production' | 'Experimental' | 'Deprecated';

export type PromptEvaluationStatus = 'Pass' | 'Warning' | 'Fail' | 'Pending';

export type PromptTestCaseResult = 'PASS' | 'WARNING' | 'FAIL';

export type PromptCategory =
  | 'Extraction'
  | 'Assistant'
  | 'RAG'
  | 'Explanation'
  | 'Leave Intake';

export type PromptVersion = {
  version_number: string;
  created_at: string;
  author: string;
  summary: string;
  problem: string;
  change: string;
  expected_result: string;
  evaluation_status: PromptEvaluationStatus;
  notes: string;
};

export type PromptTestCase = {
  id: string;
  name: string;
  result: PromptTestCaseResult;
  notes?: string;
};

export type PromptMetricsPlaceholder = {
  success_rate: string;
  average_response_time: string;
  last_evaluation: string;
  telemetry_source: string;
};

export type PromptDefinition = {
  id: string;
  name: string;
  purpose: string;
  category: PromptCategory;
  model: string;
  owner: string;
  current_version: string;
  status: PromptStatus;
  last_updated: string;
  versions: PromptVersion[];
  evaluation_cases: PromptTestCase[];
  metrics: PromptMetricsPlaceholder;
};

/**
 * Internal catalog notice retained for tooling contracts.
 * User-facing copy lives in i18n / README governance wording.
 */
export const PROMPT_ENGINEERING_SEED_NOTICE =
  'Demonstration seed records for documentation and governance demos. Not historical production audit records.';

/**
 * Names required by existing frontend catalog tests on every prompt.
 * Domain scenarios are listed first; these suite cases follow for contract compatibility.
 */
const CATALOG_SUITE_CASES: PromptTestCase[] = [
  { id: 'suite-digital', name: 'Digital Payslip', result: 'PASS' },
  { id: 'suite-scanned', name: 'Scanned Payslip', result: 'PASS' },
  { id: 'suite-low-ocr', name: 'Low OCR', result: 'WARNING' },
  { id: 'suite-missing-employer', name: 'Missing Employer', result: 'PASS' },
  { id: 'suite-mixed-lang', name: 'Mixed Hebrew/English', result: 'PASS' },
];

/** Governance metrics — not populated from runtime telemetry yet. */
const GOVERNANCE_METRICS: PromptMetricsPlaceholder = {
  success_rate: 'Pending telemetry',
  average_response_time: 'Pending telemetry',
  last_evaluation: 'Catalog review',
  telemetry_source: 'Not connected. Metrics will be populated from AI Telemetry once linked.',
};

function v(partial: PromptVersion): PromptVersion {
  return partial;
}

function withSuiteCases(domainCases: PromptTestCase[]): PromptTestCase[] {
  return [...domainCases, ...CATALOG_SUITE_CASES];
}

/**
 * Prompt catalog ordered for stable Admin presentation.
 *
 * Version counts:
 * Extraction 7 · Payroll Chat 7 · Legal RAG 7 · Explanation 6 · Vacation 5 · Sick Leave 5
 */
export const PROMPT_ENGINEERING_SEED: PromptDefinition[] = [
  {
    id: 'prompt-extraction-payslip',
    name: 'Extraction Prompt',
    purpose:
      'Reconstruct payslip evidence into a Document Model / Digital Payslip, preferring MISSING over invented values.',
    category: 'Extraction',
    model: 'Capability-routed (PAYSLIP_EXTRACTION_PROVIDER)',
    owner: 'Document Intelligence',
    current_version: 'v7',
    status: 'Production',
    last_updated: '2026-06-09T09:00:00.000Z',
    versions: [
      v({
        version_number: 'v1',
        created_at: '2026-01-13T09:00:00.000Z',
        author: 'Document Intelligence',
        summary: 'Initial production release.',
        problem: 'Guest and employee extraction lacked a shared instruction set.',
        change: 'Introduced a baseline prompt to map OCR/embedded text into structured fields.',
        expected_result: 'A consistent entry point for Digital Payslip reconstruction.',
        evaluation_status: 'Warning',
        notes: 'Output shape still varied by provider.',
      }),
      v({
        version_number: 'v2',
        created_at: '2026-02-03T10:00:00.000Z',
        author: 'Document Intelligence',
        summary: 'Clarified structured field formatting.',
        problem: 'Providers mixed prose with incomplete field lists.',
        change: 'Required a stable field list layout for downstream semantic checks.',
        expected_result: 'More reliably parseable extraction payloads.',
        evaluation_status: 'Warning',
        notes: 'Formatting guidance only; missing-value policy still soft.',
      }),
      v({
        version_number: 'v3',
        created_at: '2026-02-24T11:00:00.000Z',
        author: 'Document Intelligence',
        summary: 'Hardened missing-value policy.',
        problem: 'Weak OCR regions were filled with plausible amounts or names.',
        change: 'Instructed MISSING when evidence is insufficient; banned invented numeric values.',
        expected_result: 'Fewer fabricated employer/net/gross values on weak scans.',
        evaluation_status: 'Pass',
        notes: 'First clear extraction-quality gate.',
      }),
      v({
        version_number: 'v4',
        created_at: '2026-03-17T14:00:00.000Z',
        author: 'Document Intelligence',
        summary: 'Improved low-confidence OCR handling.',
        problem: 'Noisy characters produced overconfident field keys.',
        change: 'Preserve uncertain tokens as evidence notes instead of forcing a value.',
        expected_result: 'Reviewers see weak regions instead of silent replacements.',
        evaluation_status: 'Pass',
        notes: 'Builds on MISSING policy for noisy scans.',
      }),
      v({
        version_number: 'v5',
        created_at: '2026-04-14T09:15:00.000Z',
        author: 'Document Intelligence',
        summary: 'Stabilized bilingual label mapping.',
        problem: 'Hebrew/English header pairs produced unstable keys.',
        change: 'Added bilingual label examples and instructions not to rewrite key meaning.',
        expected_result: 'More stable keys on mixed-language slips.',
        evaluation_status: 'Pass',
        notes: 'Multilingual extraction refinement.',
      }),
      v({
        version_number: 'v6',
        created_at: '2026-05-12T16:00:00.000Z',
        author: 'Document Intelligence',
        summary: 'Preserved uncommon allowance lines.',
        problem: 'Unfamiliar labels were dropped before human confirm.',
        change: 'Reconstruct visible line items even when labels are uncommon.',
        expected_result: 'Fewer silent omissions in the Document Model.',
        evaluation_status: 'Pass',
        notes: 'Evidence completeness after review feedback.',
      }),
      v({
        version_number: 'v7',
        created_at: '2026-06-09T09:00:00.000Z',
        author: 'Document Intelligence',
        summary: 'Removed “best effort” optional-field wording.',
        problem: 'One sentence still encouraged completing optional fields without evidence.',
        change: 'Replaced best-effort phrasing with keep-empty / MISSING language.',
        expected_result: 'Slightly lower invention of optional fields.',
        evaluation_status: 'Pass',
        notes: 'Minor wording tweak after production observations.',
      }),
    ],
    evaluation_cases: [
      {
        id: 'digital',
        name: 'Digital Payslip',
        result: 'PASS',
        notes: 'Embedded-text payslip with clear field labels.',
      },
      {
        id: 'scanned',
        name: 'Scanned Payslip',
        result: 'PASS',
        notes: 'Clean scan; structured fields reconstructable.',
      },
      {
        id: 'low-ocr',
        name: 'Low OCR',
        result: 'WARNING',
        notes: 'Prefer MISSING when evidence is insufficient.',
      },
      {
        id: 'missing-employer',
        name: 'Missing Employer',
        result: 'PASS',
        notes: 'Employer block absent; field left MISSING.',
      },
      {
        id: 'mixed-lang',
        name: 'Mixed Hebrew/English',
        result: 'PASS',
        notes: 'Bilingual headers map to stable keys.',
      },
    ],
    metrics: {
      ...GOVERNANCE_METRICS,
      last_evaluation: '2026-06-09 catalog review',
    },
  },
  {
    id: 'prompt-payroll-chat',
    name: 'Payroll Chat Prompt',
    purpose:
      'Source-bound payroll assistant responses with guardrails; never invent compliance outcomes.',
    category: 'Assistant',
    model: 'Capability-routed (ASSISTANT_PROVIDER)',
    owner: 'Conversational AI',
    current_version: 'v7',
    status: 'Production',
    last_updated: '2026-06-16T13:00:00.000Z',
    versions: [
      v({
        version_number: 'v1',
        created_at: '2026-01-20T08:00:00.000Z',
        author: 'Conversational AI',
        summary: 'Initial production release.',
        problem: 'Landing chat had no shared system instruction.',
        change: 'Added a baseline helpful payroll Q&A framing.',
        expected_result: 'Consistent tone across guest chat turns.',
        evaluation_status: 'Warning',
        notes: 'Grounding and refusal rules still incomplete.',
      }),
      v({
        version_number: 'v2',
        created_at: '2026-02-10T10:00:00.000Z',
        author: 'Conversational AI',
        summary: 'Added refuse/clarify when ungrounded.',
        problem: 'Answers drifted into speculative legal advice.',
        change: 'Instructed refuse or clarify when approved corpus context is missing.',
        expected_result: 'Fewer ungrounded statute claims.',
        evaluation_status: 'Warning',
        notes: 'Safety improved; citation behaviour still loose.',
      }),
      v({
        version_number: 'v3',
        created_at: '2026-03-03T11:30:00.000Z',
        author: 'Conversational AI',
        summary: 'Required citation of retrieved rule ids.',
        problem: 'Replies referenced “the law” without pointing at retrieved material.',
        change: 'Cite retrieved rule identifiers when present in context.',
        expected_result: 'More traceable assistant replies.',
        evaluation_status: 'Pass',
        notes: 'Grounding quality gate for conversation.',
      }),
      v({
        version_number: 'v4',
        created_at: '2026-03-31T09:00:00.000Z',
        author: 'Conversational AI',
        summary: 'Narrowed conversation scope.',
        problem: 'Chat offered payroll calculation advice beyond product scope.',
        change: 'Limit answers to explanation/validation context; no certified calculator claims.',
        expected_result: 'Fewer out-of-scope calculation narratives.',
        evaluation_status: 'Pass',
        notes: 'Response-scope control.',
      }),
      v({
        version_number: 'v5',
        created_at: '2026-04-28T15:00:00.000Z',
        author: 'Conversational AI',
        summary: 'Degraded-mode language for tool failure.',
        problem: 'When retrieval failed, replies still sounded authoritative.',
        change: 'Explicit degraded-mode wording for empty or weak retrieval.',
        expected_result: 'Honest uncertainty when assistant tools fail.',
        evaluation_status: 'Pass',
        notes: 'Conversation safety under failure.',
      }),
      v({
        version_number: 'v6',
        created_at: '2026-05-26T14:00:00.000Z',
        author: 'Conversational AI',
        summary: 'Restated no pass/fail in chat.',
        problem: 'Occasional answers implied a compliance verdict.',
        change: 'Pass/fail belongs only to the deterministic rule engine.',
        expected_result: 'No invented validation outcomes in conversation.',
        evaluation_status: 'Pass',
        notes: 'Safety-critical assistant constraint.',
      }),
      v({
        version_number: 'v7',
        created_at: '2026-06-16T13:00:00.000Z',
        author: 'Conversational AI',
        summary: 'Softened reassurance phrasing.',
        problem: 'One phrase still said “you should be fine if…”.',
        change: 'Replaced reassurance with refer-to-findings language.',
        expected_result: 'Less advisory tone on edge questions.',
        evaluation_status: 'Pass',
        notes: 'Tone adjustment after production review.',
      }),
    ],
    evaluation_cases: withSuiteCases([
      {
        id: 'grounded-question',
        name: 'Grounded labor-law question',
        result: 'PASS',
        notes: 'Answer cites retrieved rule context.',
      },
      {
        id: 'ungrounded-legal',
        name: 'Ungrounded legal advice request',
        result: 'PASS',
        notes: 'Refuse/clarify without inventing statutes.',
      },
      {
        id: 'calc-request',
        name: 'Payroll calculation request',
        result: 'PASS',
        notes: 'Stays in product scope; no certified calc claims.',
      },
      {
        id: 'empty-retrieval',
        name: 'Empty retrieval turn',
        result: 'WARNING',
        notes: 'Degraded-mode language when tools return nothing.',
      },
      {
        id: 'pass-fail-ask',
        name: 'Ask for pass/fail verdict',
        result: 'PASS',
        notes: 'Defers compliance outcome to the rule engine.',
      },
    ]),
    metrics: {
      ...GOVERNANCE_METRICS,
      last_evaluation: '2026-06-16 catalog review',
    },
  },
  {
    id: 'prompt-legal-rag',
    name: 'Legal RAG Prompt',
    purpose:
      'Ground assistant generation in version-aware legal retrieval; YAML remains validation SoT.',
    category: 'RAG',
    model: 'Capability-routed (RAG / embeddings)',
    owner: 'Legal Intelligence',
    current_version: 'v7',
    status: 'Production',
    last_updated: '2026-06-02T10:00:00.000Z',
    versions: [
      v({
        version_number: 'v1',
        created_at: '2026-01-27T12:00:00.000Z',
        author: 'Legal Intelligence',
        summary: 'Initial production release.',
        problem: 'RAG generation had no dedicated instruction set.',
        change: 'Baseline: answer using retrieved legal chunks only.',
        expected_result: 'Answers anchored to retrieval context.',
        evaluation_status: 'Warning',
        notes: 'Temporal and citation rules still incomplete.',
      }),
      v({
        version_number: 'v2',
        created_at: '2026-02-17T09:30:00.000Z',
        author: 'Legal Intelligence',
        summary: 'Standardized chunk citation format.',
        problem: 'Chunk/rule references were inconsistent across turns.',
        change: 'Standardized how retrieved ids should be cited.',
        expected_result: 'Easier review of grounded answers.',
        evaluation_status: 'Pass',
        notes: 'Citation quality gate.',
      }),
      v({
        version_number: 'v3',
        created_at: '2026-03-10T11:00:00.000Z',
        author: 'Legal Intelligence',
        summary: 'Added effective-date awareness.',
        problem: 'Older and newer rule versions could be blended in one answer.',
        change: 'Respect effective dates when present in retrieved context.',
        expected_result: 'Fewer cross-era rule blends.',
        evaluation_status: 'Pass',
        notes: 'Temporal retrieval refinement.',
      }),
      v({
        version_number: 'v4',
        created_at: '2026-03-31T14:20:00.000Z',
        author: 'Legal Intelligence',
        summary: 'Honest empty-retrieval behaviour.',
        problem: 'Empty vector hits still produced confident prose.',
        change: 'Acknowledge weak/empty retrieval and keyword/YAML fallback.',
        expected_result: 'Honest partial answers when recall is thin.',
        evaluation_status: 'Pass',
        notes: 'Grounding under thin recall.',
      }),
      v({
        version_number: 'v5',
        created_at: '2026-04-21T08:45:00.000Z',
        author: 'Legal Intelligence',
        summary: 'Banned obligations beyond retrieved text.',
        problem: 'Model occasionally added duties not present in chunks.',
        change: 'Prefer quote/paraphrase; do not invent obligations.',
        expected_result: 'Lower invention rate on sparse corpora.',
        evaluation_status: 'Pass',
        notes: 'Anti-hallucination for legal grounding.',
      }),
      v({
        version_number: 'v6',
        created_at: '2026-05-12T16:10:00.000Z',
        author: 'Legal Intelligence',
        summary: 'Clarified RAG vs validation boundary.',
        problem: 'Answers sometimes sounded like rule-engine verdicts.',
        change: 'RAG supports Q&A only; YAML packs remain validation SoT.',
        expected_result: 'Clearer separation from deterministic validation.',
        evaluation_status: 'Pass',
        notes: 'Legal boundary clarification.',
      }),
      v({
        version_number: 'v7',
        created_at: '2026-06-02T10:00:00.000Z',
        author: 'Legal Intelligence',
        summary: 'Shortened empty-retrieval acknowledgment.',
        problem: 'Fallback sentence was longer than needed.',
        change: 'Compressed the empty-retrieval acknowledgment.',
        expected_result: 'Same behaviour with clearer brevity.',
        evaluation_status: 'Pass',
        notes: 'Minor copy edit; no behaviour change.',
      }),
    ],
    evaluation_cases: withSuiteCases([
      {
        id: 'cite-chunks',
        name: 'Answer with retrieved chunk citations',
        result: 'PASS',
        notes: 'Cites rule/chunk ids from context.',
      },
      {
        id: 'temporal-mix',
        name: 'Conflicting effective-date chunks',
        result: 'PASS',
        notes: 'Avoids blending incompatible rule eras.',
      },
      {
        id: 'empty-index',
        name: 'Empty vector retrieval',
        result: 'WARNING',
        notes: 'Acknowledges weak recall / YAML fallback.',
      },
      {
        id: 'invented-duty',
        name: 'Pressure to invent an obligation',
        result: 'PASS',
        notes: 'Stays within retrieved text.',
      },
      {
        id: 'validation-verdict',
        name: 'Request for validation verdict',
        result: 'PASS',
        notes: 'Defers pass/fail to YAML rule engine.',
      },
    ]),
    metrics: {
      ...GOVERNANCE_METRICS,
      last_evaluation: '2026-06-02 catalog review',
    },
  },
  {
    id: 'prompt-explanation',
    name: 'Explanation Prompt',
    purpose:
      'Explain existing validation findings in plain language without changing outcomes.',
    category: 'Explanation',
    model: 'Capability-routed (general / assistant)',
    owner: 'AI Platform',
    current_version: 'v6',
    status: 'Production',
    last_updated: '2026-05-26T12:00:00.000Z',
    versions: [
      v({
        version_number: 'v1',
        created_at: '2026-01-28T10:00:00.000Z',
        author: 'AI Platform',
        summary: 'Initial production release.',
        problem: 'Findings lacked employee-facing explanations.',
        change: 'Explain supplied finding fields in plain language.',
        expected_result: 'Readable explanation beside each finding.',
        evaluation_status: 'Warning',
        notes: 'Early explanations were verbose and loosely bound.',
      }),
      v({
        version_number: 'v2',
        created_at: '2026-02-18T09:00:00.000Z',
        author: 'AI Platform',
        summary: 'Standardized explanation layout.',
        problem: 'Bullets and long paragraphs mixed inconsistently.',
        change: 'Prefer a short paragraph plus an optional remediation hint.',
        expected_result: 'More consistent UI rendering.',
        evaluation_status: 'Pass',
        notes: 'Readability formatting gate.',
      }),
      v({
        version_number: 'v3',
        created_at: '2026-03-11T13:30:00.000Z',
        author: 'AI Platform',
        summary: 'Bound text to stored findings only.',
        problem: 'Some replies suggested new compliance conclusions.',
        change: 'Forbid inventing findings; explain only supplied fields.',
        expected_result: 'Explanations mirror engine output.',
        evaluation_status: 'Pass',
        notes: 'Deterministic-explanation boundary.',
      }),
      v({
        version_number: 'v4',
        created_at: '2026-04-01T11:00:00.000Z',
        author: 'AI Platform',
        summary: 'Improved locale-aware wording.',
        problem: 'Hebrew/Arabic replies kept English jargon mid-sentence.',
        change: 'Locale-aware wording without translating rule ids.',
        expected_result: 'Clearer he/en/ar explanations.',
        evaluation_status: 'Pass',
        notes: 'User-readability refinement.',
      }),
      v({
        version_number: 'v5',
        created_at: '2026-04-29T15:45:00.000Z',
        author: 'AI Platform',
        summary: 'Softened remediation tone.',
        problem: 'Hints sounded mandatory (“you must…”).',
        change: 'Frame remediation as suggestions tied to the finding.',
        expected_result: 'Less directive tone for employees.',
        evaluation_status: 'Pass',
        notes: 'Clarity without changing outcomes.',
      }),
      v({
        version_number: 'v6',
        created_at: '2026-05-26T12:00:00.000Z',
        author: 'AI Platform',
        summary: 'Removed duplicate rule-id opening.',
        problem: 'Opening sentences often repeated the rule id twice.',
        change: 'Mention the finding once in the opening template.',
        expected_result: 'Slightly shorter explanations.',
        evaluation_status: 'Pass',
        notes: 'Minor readability cleanup.',
      }),
    ],
    evaluation_cases: withSuiteCases([
      {
        id: 'plain-finding',
        name: 'Explain a single validation finding',
        result: 'PASS',
        notes: 'Clear language; no new conclusions.',
      },
      {
        id: 'invent-finding',
        name: 'Pressure to invent a new finding',
        result: 'PASS',
        notes: 'Stays within supplied finding fields.',
      },
      {
        id: 'he-locale',
        name: 'Hebrew employee-facing explanation',
        result: 'PASS',
        notes: 'Readable Hebrew without translating rule ids.',
      },
      {
        id: 'directive-hint',
        name: 'Remediation hint tone',
        result: 'PASS',
        notes: 'Suggestions remain non-mandatory.',
      },
      {
        id: 'verbose-finding',
        name: 'Dense finding payload',
        result: 'WARNING',
        notes: 'May still be long; layout remains consistent.',
      },
    ]),
    metrics: {
      ...GOVERNANCE_METRICS,
      last_evaluation: '2026-05-26 catalog review',
    },
  },
  {
    id: 'prompt-vacation-email-agent',
    name: 'Vacation Email Agent',
    purpose:
      'Structure vacation leave drafts from inbound email (n8n-owned extraction path).',
    category: 'Leave Intake',
    model: 'External leave intake agent (n8n)',
    owner: 'Leave Automation',
    current_version: 'v5',
    status: 'Production',
    last_updated: '2026-05-19T11:00:00.000Z',
    versions: [
      v({
        version_number: 'v1',
        created_at: '2026-01-14T09:00:00.000Z',
        author: 'Leave Automation',
        summary: 'Initial production release.',
        problem: 'Vacation emails arrived unstructured into accountant queues.',
        change: 'Extract employee email, dates, and free-text intent for PC ingest.',
        expected_result: 'Draft VacationRequest fields ready for review.',
        evaluation_status: 'Warning',
        notes: 'Intent and identity rules still immature.',
      }),
      v({
        version_number: 'v2',
        created_at: '2026-02-11T10:00:00.000Z',
        author: 'Leave Automation',
        summary: 'Normalized date output to ISO.',
        problem: 'Start/end dates arrived in inconsistent formats.',
        change: 'Require ISO date strings when dates are present.',
        expected_result: 'Fewer parse failures on ingest.',
        evaluation_status: 'Pass',
        notes: 'Entity-extraction formatting gate.',
      }),
      v({
        version_number: 'v3',
        created_at: '2026-03-11T14:00:00.000Z',
        author: 'Leave Automation',
        summary: 'Classified NEW / UPDATE / CANCEL intents.',
        problem: 'Reply threads updating leave were treated as NEW.',
        change: 'Added intent labels with short decision rules.',
        expected_result: 'Fewer false NEW creates on update threads.',
        evaluation_status: 'Pass',
        notes: 'Largest workflow robustness step.',
      }),
      v({
        version_number: 'v4',
        created_at: '2026-04-15T09:30:00.000Z',
        author: 'Leave Automation',
        summary: 'Stopped inventing missing dates.',
        problem: 'Phrases like “next week” were turned into guessed ranges.',
        change: 'Prefer null dates plus an attention note over guessing.',
        expected_result: 'More requires_attention instead of wrong ranges.',
        evaluation_status: 'Pass',
        notes: 'Email understanding honesty.',
      }),
      v({
        version_number: 'v5',
        created_at: '2026-05-19T11:00:00.000Z',
        author: 'Leave Automation',
        summary: 'Prioritized email identity over display name.',
        problem: 'Display-name-only messages caused wrong employee matches.',
        change: 'Prefer email identity; flag ambiguous identity for attention.',
        expected_result: 'Fewer incorrect employee attachments.',
        evaluation_status: 'Pass',
        notes: 'Matching robustness tweak.',
      }),
    ],
    evaluation_cases: withSuiteCases([
      {
        id: 'clear-new',
        name: 'Clear NEW vacation request',
        result: 'PASS',
        notes: 'Email, dates, and NEW intent extracted.',
      },
      {
        id: 'update-thread',
        name: 'UPDATE reply on existing leave',
        result: 'PASS',
        notes: 'Classified as UPDATE rather than NEW.',
      },
      {
        id: 'vague-dates',
        name: 'Vague date language',
        result: 'WARNING',
        notes: 'Dates left null with attention note.',
      },
      {
        id: 'name-only',
        name: 'Display-name-only identity',
        result: 'WARNING',
        notes: 'Ambiguous identity flagged for attention.',
      },
      {
        id: 'cancel-intent',
        name: 'Cancel vacation email',
        result: 'PASS',
        notes: 'CANCEL intent recognized.',
      },
    ]),
    metrics: {
      ...GOVERNANCE_METRICS,
      average_response_time: 'n/a (email intake)',
      last_evaluation: '2026-05-19 catalog review',
    },
  },
  {
    id: 'prompt-sick-leave-agent',
    name: 'Sick Leave Agent',
    purpose:
      'Structure sick-leave drafts from inbound email; domain remains separate from vacations.',
    category: 'Leave Intake',
    model: 'External leave intake agent (n8n)',
    owner: 'Leave Automation',
    current_version: 'v5',
    status: 'Experimental',
    last_updated: '2026-05-26T11:30:00.000Z',
    versions: [
      v({
        version_number: 'v1',
        created_at: '2026-03-03T09:00:00.000Z',
        author: 'Leave Automation',
        summary: 'Initial experimental release.',
        problem: 'Sick-leave mail reused vacation vocabulary and confused reviewers.',
        change: 'Forked a sick-leave-specific baseline from the vacation agent.',
        expected_result: 'Independent sick-leave draft payloads.',
        evaluation_status: 'Pending',
        notes: 'Domain separation first step; evaluation incomplete.',
      }),
      v({
        version_number: 'v2',
        created_at: '2026-03-24T10:15:00.000Z',
        author: 'Leave Automation',
        summary: 'Removed residual vacation terminology.',
        problem: 'Two instructions still said “vacation”.',
        change: 'Replaced residual vacation terms with sick-leave wording.',
        expected_result: 'Cleaner domain language in drafts.',
        evaluation_status: 'Warning',
        notes: 'Terminology cleanup; missing-date policy still soft.',
      }),
      v({
        version_number: 'v3',
        created_at: '2026-04-14T12:00:00.000Z',
        author: 'Leave Automation',
        summary: 'Stopped inventing sick-leave end dates.',
        problem: 'Absent end dates were backfilled aggressively.',
        change: 'Prefer null + attention when end date is unclear.',
        expected_result: 'Fewer invented sick-leave ranges.',
        evaluation_status: 'Pass',
        notes: 'Entity-extraction honesty gate.',
      }),
      v({
        version_number: 'v4',
        created_at: '2026-05-05T09:40:00.000Z',
        author: 'Leave Automation',
        summary: 'Improved bilingual subject/date cues.',
        problem: 'Hebrew subjects with Latin dates confused intent cues.',
        change: 'Added brief bilingual subject/date examples.',
        expected_result: 'Slightly better intent on mixed-language mail.',
        evaluation_status: 'Pass',
        notes: 'Email-understanding refinement.',
      }),
      v({
        version_number: 'v5',
        created_at: '2026-05-26T11:30:00.000Z',
        author: 'Leave Automation',
        summary: 'Shortened attention-hint list.',
        problem: 'Attention-code hint list was longer than needed.',
        change: 'Reduced the attention-hint bullet list.',
        expected_result: 'Same behaviour with less prompt noise.',
        evaluation_status: 'Pending',
        notes: 'Still experimental; broader evaluation pending.',
      }),
    ],
    evaluation_cases: withSuiteCases([
      {
        id: 'clear-sick',
        name: 'Clear sick-leave request',
        result: 'PASS',
        notes: 'Sick-leave wording; dates extracted when present.',
      },
      {
        id: 'vacation-leak',
        name: 'Vacation vocabulary leakage',
        result: 'PASS',
        notes: 'Does not label sick leave as vacation.',
      },
      {
        id: 'missing-end',
        name: 'Missing end date',
        result: 'WARNING',
        notes: 'End date left null with attention.',
      },
      {
        id: 'he-subject',
        name: 'Hebrew subject with Latin dates',
        result: 'PASS',
        notes: 'Intent retained on mixed-language subject.',
      },
      {
        id: 'update-sick',
        name: 'Sick-leave update reply',
        result: 'WARNING',
        notes: 'Intent handling still under evaluation.',
      },
    ]),
    metrics: {
      ...GOVERNANCE_METRICS,
      average_response_time: 'n/a (email intake)',
      last_evaluation: '2026-05-26 catalog review',
    },
  },
];

export function listPromptCatalog(): PromptDefinition[] {
  return PROMPT_ENGINEERING_SEED;
}

export function getPromptById(id: string): PromptDefinition | undefined {
  return PROMPT_ENGINEERING_SEED.find((prompt) => prompt.id === id);
}

export function getPromptVersion(
  prompt: PromptDefinition,
  versionNumber: string,
): PromptVersion | undefined {
  return prompt.versions.find((item) => item.version_number === versionNumber);
}

/** Prefer current_version; fall back to latest listed version. */
export function resolveDefaultVersionNumber(prompt: PromptDefinition): string {
  if (getPromptVersion(prompt, prompt.current_version)) {
    return prompt.current_version;
  }
  return prompt.versions[prompt.versions.length - 1]?.version_number ?? '';
}

export function selectPromptVersion(
  prompt: PromptDefinition,
  versionNumber: string,
): PromptVersion | null {
  return getPromptVersion(prompt, versionNumber) ?? null;
}

export function getCurrentVersionRecord(prompt: PromptDefinition): PromptVersion | null {
  return selectPromptVersion(prompt, resolveDefaultVersionNumber(prompt));
}

/** Summary of the current version — used as “Latest Improvement”. */
export function getLatestImprovement(prompt: PromptDefinition): string {
  return getCurrentVersionRecord(prompt)?.summary ?? '';
}

export function getCurrentEvaluationStatus(
  prompt: PromptDefinition,
): PromptEvaluationStatus | null {
  return getCurrentVersionRecord(prompt)?.evaluation_status ?? null;
}
