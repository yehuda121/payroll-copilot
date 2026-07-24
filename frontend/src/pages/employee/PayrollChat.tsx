import { useCallback, useState } from 'react';
import { useEmployeeSession } from '../../auth/EmployeeSessionContext';
import { PortalPage } from '../../components/PortalPage';
import { EMPLOYEE_CHAT_SUGGESTIONS } from '../../components/chat/ChatWelcome';
import { GuestChatPanel } from '../../components/guest/GuestChatPanel';
import { PopularQuestionsPanel } from '../../components/guest/PopularQuestionsPanel';
import { useEmployeeWorkspace } from '../../features/employee/EmployeeWorkspaceContext';
import '../../features/guest/guest.css';
import '../../features/guest/landing/landing-chat.css';
import { useEmployeeContextBuilder } from '../../hooks/useEmployeeContextBuilder';
import { useWorkspacePageCopy } from '../../hooks/useWorkspacePageCopy';
import { employeeAssistantService } from '../../services/assistant';
import type { AssistantChatRequest, AssistantChatResponse } from '../../types/assistant';

type PayrollChatPanelProps = {
  pendingQuestion?: string | null;
  onPendingQuestionConsumed?: () => void;
};

export function PayrollChatPanel({
  pendingQuestion = null,
  onPendingQuestionConsumed,
}: PayrollChatPanelProps = {}) {
  const session = useEmployeeSession();
  const { build } = useEmployeeContextBuilder();
  const workspace = useEmployeeWorkspace();

  const employeeChat = useCallback(
    async (payload: AssistantChatRequest): Promise<AssistantChatResponse> => {
      const before = build();
      const request = {
        message: payload.message,
        session_id: payload.session_id,
        locale: payload.locale,
        document_id: workspace.batchReview?.documentId,
        available_resource_keys: before.resources
          .filter((resource) => resource.status === 'available')
          .map((resource) => resource.key),
        model_provider_override: payload.model_provider_override,
      };
      const response =
        workspace.mode === 'accountant' && workspace.employeeNumber
          ? await employeeAssistantService.chatForAccountant({
              ...request,
              employee_number: workspace.employeeNumber,
            })
          : await employeeAssistantService.chat(request);

      const updates = response.context_updates;
      if (updates.profile) session.setProfile(updates.profile);
      for (const months of updates.payroll_months) {
        session.setPayrollMonths(months);
      }
      for (const detail of updates.payroll_month_details) {
        session.setPayrollMonthDetail(detail);
      }
      if (updates.document_center) {
        session.setDocumentCenter(updates.document_center);
      }

      // Rebuild after canonical backend updates so subsequent turns see the
      // newly available resources. The builder itself performs no fetching.
      build();
      return response;
    },
    [
      build,
      session,
      workspace.batchReview?.documentId,
      workspace.employeeNumber,
      workspace.mode,
    ],
  );

  return (
    <GuestChatPanel
      chatHandler={employeeChat}
      pendingQuestion={pendingQuestion}
      onPendingQuestionConsumed={onPendingQuestionConsumed}
      productShell
      welcomeNamespace="employee.chat.welcome"
      welcomeSuggestionKeys={EMPLOYEE_CHAT_SUGGESTIONS}
    />
  );
}

export function PayrollChatPage() {
  const copy = useWorkspacePageCopy();
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);

  return (
    <PortalPage
      title={copy.chatTitle}
      description={copy.chatDescription}
      hideHeader
      integrationNote="@integration-point EMPLOYEE_AI_CHAT"
    >
      {/*
        Structural layout is fixed (chat primary, supporting + popular secondary).
        Locale only affects text direction inside each region.
        On narrow screens DOM order keeps Chat first.
      */}
      <div className="chat-with-popular chat-with-popular--workspace" dir="ltr">
        <div className="chat-with-popular__primary">
          <PayrollChatPanel
            pendingQuestion={pendingQuestion}
            onPendingQuestionConsumed={() => {
              setPendingQuestion(null);
            }}
          />
        </div>
        <aside className="chat-with-popular__secondary" dir="auto">
          <header className="employee-chat-support">
            <h1 className="employee-chat-support__title">{copy.chatTitle}</h1>
            <p className="employee-chat-support__description">{copy.chatDescription}</p>
          </header>
          <PopularQuestionsPanel
            onSelect={(question) => {
              setPendingQuestion(question);
            }}
          />
        </aside>
      </div>
    </PortalPage>
  );
}
