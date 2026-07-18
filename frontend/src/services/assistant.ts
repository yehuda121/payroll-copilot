import type {
  AssistantChatRequest,
  AssistantChatResponse,
  AccountantEmployeeAssistantChatRequest,
  EmployeeAssistantChatRequest,
  EmployeeAssistantChatResponse,
} from '../types/assistant';
import { apiRequest } from './api';

/**
 * Public payroll assistant chat service.
 * @integration-point ASSISTANT_SERVICE — POST /assistant/chat
 */
export const assistantService = {
  async chat(payload: AssistantChatRequest): Promise<AssistantChatResponse> {
    return apiRequest<AssistantChatResponse>('/assistant/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
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
