import type { AssistantChatRequest, AssistantChatResponse } from '../types/assistant';
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
