import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useEmployeeSession } from '../../auth/EmployeeSessionContext';
import { PortalPage } from '../../components/PortalPage';
import { GuestChatPanel } from '../../components/guest/GuestChatPanel';
import { useEmployeeWorkspace } from '../../features/employee/EmployeeWorkspaceContext';
import { useEmployeeContextBuilder } from '../../hooks/useEmployeeContextBuilder';
import { employeeAssistantService } from '../../services/assistant';
import type { AssistantChatRequest, AssistantChatResponse } from '../../types/assistant';

export function PayrollChatPanel() {
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

  return <GuestChatPanel chatHandler={employeeChat} />;
}

export function PayrollChatPage() {
  const { t } = useTranslation();
  return (
    <PortalPage
      title={t('employee.pages.chatTitle')}
      description={t('employee.pages.chatDescription')}
      integrationNote="@integration-point EMPLOYEE_AI_CHAT"
    >
      <PayrollChatPanel />
    </PortalPage>
  );
}
