import type {
  DocumentLabFixtureItem,
  DocumentLabFixtureListResponse,
  DocumentLabPipelineResult,
  DocumentLabRunResult,
} from '../types/document-lab';
import { apiRequest } from './api';

function formWithFixture(fixtureId: string, language = 'auto') {
  const form = new FormData();
  form.append('fixture_id', fixtureId);
  form.append('language', language);
  return form;
}

function formWithFile(file: File, language = 'auto') {
  const form = new FormData();
  form.append('file', file);
  form.append('language', language);
  return form;
}

export const documentLabService = {
  async listFixtures(): Promise<DocumentLabFixtureListResponse> {
    return apiRequest<DocumentLabFixtureListResponse>('/dev/document-lab/fixtures');
  },

  async runOcr(params: { fixtureId?: string; file?: File; language?: string }): Promise<DocumentLabRunResult> {
    const form = params.fixtureId
      ? formWithFixture(params.fixtureId, params.language)
      : formWithFile(params.file as File, params.language);
    return apiRequest<DocumentLabRunResult>('/dev/document-lab/run/ocr', {
      method: 'POST',
      body: form,
      rawBody: true,
    });
  },

  async runParser(ocr: Record<string, unknown>): Promise<DocumentLabRunResult> {
    return apiRequest<DocumentLabRunResult>('/dev/document-lab/run/parser', {
      method: 'POST',
      body: JSON.stringify({ ocr }),
    });
  },

  async runOcrParser(params: {
    fixtureId?: string;
    file?: File;
    language?: string;
  }): Promise<DocumentLabRunResult> {
    const form = params.fixtureId
      ? formWithFixture(params.fixtureId, params.language)
      : formWithFile(params.file as File, params.language);
    return apiRequest<DocumentLabRunResult>('/dev/document-lab/run/ocr-parser', {
      method: 'POST',
      body: form,
      rawBody: true,
    });
  },

  async runPipeline(params: {
    fixtureId?: string;
    file?: File;
    language?: string;
    locale?: 'he' | 'en' | 'ar';
    includeExplanation?: boolean;
  }): Promise<DocumentLabPipelineResult> {
    const form = params.fixtureId
      ? formWithFixture(params.fixtureId, params.language)
      : formWithFile(params.file as File, params.language);
    if (params.locale) {
      form.append('locale', params.locale);
    }
    form.append('include_explanation', String(params.includeExplanation ?? true));
    return apiRequest<DocumentLabPipelineResult>('/dev/document-lab/run/pipeline', {
      method: 'POST',
      body: form,
      rawBody: true,
      auth: true,
    });
  },
};

export type { DocumentLabFixtureItem };
