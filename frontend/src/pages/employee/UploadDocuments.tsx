import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { EmployeePayslipWizard } from '../../features/employee/EmployeePayslipWizard';

export function UploadDocumentsPage() {
  const { t } = useTranslation();
  return (
    <PortalPage title={t('employee.upload.pageTitle')} description={t('employee.upload.pageDescription')}>
      <EmployeePayslipWizard />
    </PortalPage>
  );
}
