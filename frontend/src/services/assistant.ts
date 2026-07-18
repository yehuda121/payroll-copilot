import type {
  AssistantChatRequest,
  AssistantChatResponse,
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
};
