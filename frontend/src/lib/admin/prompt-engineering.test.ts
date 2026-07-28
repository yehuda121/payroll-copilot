import { describe, expect, it } from 'vitest';
import {
  PROMPT_ENGINEERING_SEED,
  PROMPT_ENGINEERING_SEED_NOTICE,
  getCurrentEvaluationStatus,
  getLatestImprovement,
  getPromptById,
  getPromptVersion,
  listPromptCatalog,
  resolveDefaultVersionNumber,
  selectPromptVersion,
} from './prompt-engineering';

describe('prompt engineering catalog', () => {
  it('loads the seed catalog with expected prompts', () => {
    const catalog = listPromptCatalog();
    expect(catalog).toBe(PROMPT_ENGINEERING_SEED);
    expect(catalog.length).toBeGreaterThanOrEqual(6);
    expect(catalog.map((item) => item.name)).toEqual(
      expect.arrayContaining([
        'Extraction Prompt',
        'Payroll Chat Prompt',
        'Legal RAG Prompt',
        'Explanation Prompt',
        'Vacation Email Agent',
        'Sick Leave Agent',
      ]),
    );
  });

  it('marks seed data as demonstration-only', () => {
    expect(PROMPT_ENGINEERING_SEED_NOTICE.toLowerCase()).toContain('demonstration');
    expect(PROMPT_ENGINEERING_SEED_NOTICE.toLowerCase()).toContain('not historical production');
  });

  it('resolves prompt by id and enforces required version counts', () => {
    const extraction = getPromptById('prompt-extraction-payslip');
    expect(extraction).toBeDefined();
    expect(extraction?.versions).toHaveLength(7);
    expect(extraction?.current_version).toBe('v7');
    expect(getPromptById('prompt-payroll-chat')?.versions).toHaveLength(7);
    expect(getPromptById('prompt-legal-rag')?.versions).toHaveLength(7);
    expect(getPromptById('prompt-explanation')?.versions).toHaveLength(6);
    expect(getPromptById('prompt-vacation-email-agent')?.versions).toHaveLength(5);
    expect(getPromptById('prompt-sick-leave-agent')?.versions).toHaveLength(5);
  });

  it('keeps incremental version fields for history rendering', () => {
    const prompt = getPromptById('prompt-extraction-payslip');
    expect(prompt).toBeDefined();
    if (!prompt) return;
    for (const version of prompt.versions) {
      expect(version.summary.length).toBeGreaterThan(8);
      expect(version.problem.length).toBeGreaterThan(8);
      expect(version.change.length).toBeGreaterThan(8);
      expect(version.expected_result.length).toBeGreaterThan(8);
    }
  });

  it('selects a version and returns change-detail fields', () => {
    const prompt = getPromptById('prompt-extraction-payslip');
    expect(prompt).toBeDefined();
    if (!prompt) return;

    const version = selectPromptVersion(prompt, 'v2');
    expect(version).not.toBeNull();
    expect(version?.summary).toBeTruthy();
    expect(version?.problem).toBeTruthy();
    expect(version?.change).toBeTruthy();
    expect(version?.expected_result).toBeTruthy();
    expect(getPromptVersion(prompt, 'v9')).toBeUndefined();
    expect(selectPromptVersion(prompt, 'v9')).toBeNull();
  });

  it('defaults selection to current_version and exposes latest improvement', () => {
    const prompt = getPromptById('prompt-payroll-chat');
    expect(prompt).toBeDefined();
    if (!prompt) return;
    expect(resolveDefaultVersionNumber(prompt)).toBe(prompt.current_version);
    expect(selectPromptVersion(prompt, resolveDefaultVersionNumber(prompt))?.version_number).toBe(
      prompt.current_version,
    );
    expect(getLatestImprovement(prompt)).toBe(
      selectPromptVersion(prompt, prompt.current_version)?.summary,
    );
    expect(getCurrentEvaluationStatus(prompt)).toBe(
      selectPromptVersion(prompt, prompt.current_version)?.evaluation_status,
    );
  });

  it('includes evaluation cases and placeholder metrics on each seed prompt', () => {
    for (const prompt of listPromptCatalog()) {
      expect(prompt.evaluation_cases.length).toBeGreaterThanOrEqual(5);
      expect(prompt.evaluation_cases.map((c) => c.name)).toEqual(
        expect.arrayContaining([
          'Digital Payslip',
          'Scanned Payslip',
          'Low OCR',
          'Missing Employer',
          'Mixed Hebrew/English',
        ]),
      );
      expect(prompt.metrics.telemetry_source.toLowerCase()).toContain('not connected');
      expect(prompt.metrics.success_rate).toBeTruthy();
    }
  });

  it('exposes version history rows needed for UI rendering', () => {
    const prompt = getPromptById('prompt-legal-rag');
    expect(prompt).toBeDefined();
    if (!prompt) return;
    const history = [...prompt.versions].reverse().map((row) => ({
      version: row.version_number,
      date: row.created_at,
      author: row.author,
      summary: row.summary,
    }));
    expect(history[0]?.version).toBe(prompt.versions[prompt.versions.length - 1]?.version_number);
    expect(history.every((row) => row.author && row.summary && row.date)).toBe(true);
  });
});
