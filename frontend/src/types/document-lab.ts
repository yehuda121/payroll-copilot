export type DocumentLabFixtureItem = {
  id: string;
  filename: string;
  group: string;
  size_bytes: number;
  media_type: string;
};

export type DocumentLabFixtureListResponse = {
  valid: DocumentLabFixtureItem[];
  invalid: DocumentLabFixtureItem[];
};

export type DocumentLabOcrResult = {
  engine: string;
  language_requested: string;
  language_effective: string;
  overall_confidence: number | null;
  raw_text: string;
  warnings: string[];
  pages: Array<{
    page: number;
    language: string;
    text: string;
    confidence: number | null;
    lines: Array<{
      text: string;
      confidence: number | null;
      bbox: number[] | null;
    }>;
  }>;
};

export type DocumentLabParserField = {
  key: string;
  value: unknown;
  confidence: number | null;
  source_text: string | null;
  status: string;
};

export type DocumentLabRunResult = {
  source?: {
    filename: string;
    media_type: string;
    source_type: string;
    fixture_id?: string | null;
  };
  ocr?: DocumentLabOcrResult;
  parser?: {
    model: string;
    language: string | null;
    retry_used: boolean;
    warnings: string[];
    structured: Record<string, unknown>;
    fields: DocumentLabParserField[];
  };
  validation_context_summary?: Record<string, unknown>;
};

export type DocumentLabPipelineResult = DocumentLabRunResult & {
  extraction?: {
    document_id: string;
    extraction_id: string;
    ocr_status: string;
    parser_status: string;
    ocr_engine: string | null;
    parser_model: string | null;
    warnings: string[];
    fields: DocumentLabParserField[];
    raw_text: string;
  };
  validation?: {
    id: string;
    document_id: string;
    status: string;
    overall_result: string | null;
    rules_evaluated: number;
    rules_failed: number;
    extraction_connected: boolean;
    validation_scope: Array<{ key: string; status: string; reason?: string | null }>;
    findings: Array<{
      id: string;
      rule_id: string;
      severity: string;
      message_key: string;
      expected_value: string | null;
      actual_value: string | null;
      confidence: number;
      legal_reference: string | null;
    }>;
  };
  ai_explanation?: string | null;
};
