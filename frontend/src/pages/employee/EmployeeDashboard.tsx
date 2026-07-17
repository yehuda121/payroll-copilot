import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';

export function EmployeeDashboardPage() {
  const { t } = useTranslation();
  return (
    <PortalPage
      title={t('employee.pages.dashboardTitle')}
      description={t('employee.pages.dashboardDescription')}
      integrationNote="@integration-point EMPLOYEE_DASHBOARD"
    />
  );
}
