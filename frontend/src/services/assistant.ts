import type {
  AssistantChatRequest,
  AssistantChatResponse,
  AccountantEmployeeAssistantChatRequest,
  EmployeeAssistantChatRequest,
  EmployeeAssistantChatResponse,
} from '../types/assistant';
import { apiRequest } from './api';

export type AssistantModelChoices = {
  chat: string[];
  extraction: string[];
};

/**
 * Public payroll assistant chat service.
 * @integration-point ASSISTANT_SERVICE — POST /assistant/chat
 */
export const assistantService = {
  async chat(
    payload: AssistantChatRequest,
    options?: { auth?: boolean },
  ): Promise<AssistantChatResponse> {
    const hasPrivateIds =
      Boolean(payload.validation_run_id) ||
      Boolean(payload.document_ids && payload.document_ids.length > 0);
    return apiRequest<AssistantChatResponse>('/assistant/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
      auth: options?.auth ?? hasPrivateIds,
    });
  },

  async popularQuestions(limit = 10): Promise<{ items: { question: string; count: number }[] }> {
    return apiRequest(`/assistant/popular-questions?limit=${limit}`, {
      method: 'GET',
    });
  },

  async modelChoices(): Promise<AssistantModelChoices> {
    return apiRequest<AssistantModelChoices>('/assistant/model-choices', {
      method: 'GET',
    });
  },
};

/**
 * Authenticated employee assistant. Unlike the public service, this endpoint
 * derives personal context from the backend-bound employee identity.
 */
export const employeeAssistantService = {
  async chat(payload: EmployeeAssistantChatRequest): Promise<EmployeeAssistantChatResponse> {
    return apiRequest<EmployeeAssistantChatResponse>('/assistant/employee/chat', {
      method: 'POST',
      portalAuth: true,
      body: JSON.stringify(payload),
    });
  },

  async chatForAccountant(
    payload: AccountantEmployeeAssistantChatRequest,
  ): Promise<EmployeeAssistantChatResponse> {
    return apiRequest<EmployeeAssistantChatResponse>('/assistant/accountant/employee/chat', {
      method: 'POST',
      portalAuth: true,
      body: JSON.stringify(payload),
    });
  },

  async chatForBatchItem(
    payload: EmployeeAssistantChatRequest & {
      batch_job_id: string;
      batch_item_id: string;
    },
  ): Promise<AssistantChatResponse> {
    return apiRequest<AssistantChatResponse>('/assistant/accountant/batch-item/chat', {
      method: 'POST',
      portalAuth: true,
      body: JSON.stringify(payload),
    });
  },
};
