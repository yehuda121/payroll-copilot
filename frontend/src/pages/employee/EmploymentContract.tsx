import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';

export function EmploymentContractPage() {
  const { t } = useTranslation();
  return (
    <PortalPage
      title={t('employee.pages.contractTitle')}
      description={t('employee.pages.contractDescription')}
      integrationNote="@integration-point EMPLOYEE_CONTRACT"
    />
  );
}
