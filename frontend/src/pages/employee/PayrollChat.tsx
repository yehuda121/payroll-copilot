import { PortalPage } from '../../components/PortalPage';
import { GuestChatPanel } from '../../components/guest/GuestChatPanel';

export function PayrollChatPage() {
  return (
    <PortalPage
      title="Personal Payroll AI Chat"
      description="Ask questions about your payslips and employment terms. AI provides explanations only — not compliance decisions."
      integrationNote="@integration-point EMPLOYEE_AI_CHAT"
    >
      <GuestChatPanel />
    </PortalPage>
  );
}
