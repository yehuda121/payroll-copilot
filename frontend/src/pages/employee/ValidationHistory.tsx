import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';

export function ValidationHistoryPage() {
  const { t } = useTranslation();
  return (
    <PortalPage
      title={t('employee.pages.validationHistoryTitle')}
      description={t('employee.pages.validationHistoryDescription')}
      integrationNote="@integration-point VALIDATION_HISTORY"
    />
  );
}
