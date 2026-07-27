import { apiRequest } from './api';

export type RagEvalMetricValue = {
  value: number | null;
  status: 'ok' | 'unavailable' | 'error' | string;
  reason?: string | null;
};

export type EvaluationRun = {
  run_id: string;
  dataset_version: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  provider: string | null;
  model: string | null;
  prompt_version: string | null;
  case_count: number;
  completed_cases: number;
  failed_cases: number;
  faithfulness: RagEvalMetricValue;
  context_precision: RagEvalMetricValue;
  context_recall: RagEvalMetricValue;
  answer_relevancy: RagEvalMetricValue;
  temporal_accuracy: RagEvalMetricValue;
  triggered_by: string | null;
  error: string | null;
};

export type EvaluationCaseResult = {
  case_id: string;
  question: string;
  reference_answer: string;
  generated_answer: string;
  effective_date: string | null;
  expected_rule_ids: string[];
  retrieved_rule_ids: string[];
  retrieved_versions: string[];
  retrieved_contexts: string[];
  sources: Array<Record<string, unknown>>;
  retrieval_mode?: string | null;
  retrieval_diagnostics?: Record<string, unknown>;
  faithfulness: RagEvalMetricValue;
  context_precision: RagEvalMetricValue;
  context_recall: RagEvalMetricValue;
  answer_relevancy: RagEvalMetricValue;
  temporal_pass: boolean | null;
  temporal_detail: string | null;
  error: string | null;
  status: string;
};

export type RagEvaluationSummary = {
  latest_run: EvaluationRun | null;
  ragas_available: boolean;
  ragas_version: string | null;
  ragas_import_error: string | null;
};

export type RagEvaluationCompare = {
  run_a: EvaluationRun;
  run_b: EvaluationRun;
  dataset_version_mismatch: boolean;
  deltas: {
    faithfulness: number | null;
    context_precision: number | null;
    context_recall: number | null;
    answer_relevancy: number | null;
    temporal_accuracy: number | null;
  };
  improved_cases: string[];
  regressed_cases: string[];
};

export type RagBenchmarkCase = {
  case_id: string;
  question: string;
  effective_date: string | null;
  tags: string[] | null;
  enabled: boolean;
};

export type RagBenchmark = {
  dataset_version: string | null;
  case_count: number;
  cases: RagBenchmarkCase[];
};

export const ragEvaluationService = {
  async summary(signal?: AbortSignal): Promise<RagEvaluationSummary> {
    return apiRequest<RagEvaluationSummary>('/admin/rag-evaluation/summary', {
      method: 'GET',
      portalAuth: true,
      signal,
    });
  },

  async startRun(signal?: AbortSignal): Promise<EvaluationRun> {
    return apiRequest<EvaluationRun>('/admin/rag-evaluation/runs', {
      method: 'POST',
      portalAuth: true,
      signal,
    });
  },

  async listRuns(limit = 50, signal?: AbortSignal): Promise<EvaluationRun[]> {
    return apiRequest<EvaluationRun[]>(`/admin/rag-evaluation/runs?limit=${limit}`, {
      method: 'GET',
      portalAuth: true,
      signal,
    });
  },

  async getRun(runId: string, signal?: AbortSignal): Promise<EvaluationRun> {
    return apiRequest<EvaluationRun>(`/admin/rag-evaluation/runs/${encodeURIComponent(runId)}`, {
      method: 'GET',
      portalAuth: true,
      signal,
    });
  },

  async listCases(runId: string, signal?: AbortSignal): Promise<EvaluationCaseResult[]> {
    return apiRequest<EvaluationCaseResult[]>(
      `/admin/rag-evaluation/runs/${encodeURIComponent(runId)}/cases`,
      {
        method: 'GET',
        portalAuth: true,
        signal,
      },
    );
  },

  async getCase(runId: string, caseId: string, signal?: AbortSignal): Promise<EvaluationCaseResult> {
    return apiRequest<EvaluationCaseResult>(
      `/admin/rag-evaluation/runs/${encodeURIComponent(runId)}/cases/${encodeURIComponent(caseId)}`,
      {
        method: 'GET',
        portalAuth: true,
        signal,
      },
    );
  },

  async compare(runA: string, runB: string, signal?: AbortSignal): Promise<RagEvaluationCompare> {
    return apiRequest<RagEvaluationCompare>(
      `/admin/rag-evaluation/compare?run_a=${encodeURIComponent(runA)}&run_b=${encodeURIComponent(runB)}`,
      {
        method: 'GET',
        portalAuth: true,
        signal,
      },
    );
  },

  async benchmark(signal?: AbortSignal): Promise<RagBenchmark> {
    return apiRequest<RagBenchmark>('/admin/rag-evaluation/benchmark', {
      method: 'GET',
      portalAuth: true,
      signal,
    });
  },
};
