import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { GuestChatPanel } from '../../components/guest/GuestChatPanel';

export function PayrollChatPage() {
  const { t } = useTranslation();
  return (
    <PortalPage
      title={t('employee.pages.chatTitle')}
      description={t('employee.pages.chatDescription')}
      integrationNote="@integration-point EMPLOYEE_AI_CHAT"
    >
      <GuestChatPanel />
    </PortalPage>
  );
}
