import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';

export function AttendancePage() {
  const { t } = useTranslation();
  return (
    <PortalPage
      title={t('employee.pages.attendanceTitle')}
      description={t('employee.pages.attendanceDescription')}
      integrationNote="@integration-point EMPLOYEE_ATTENDANCE"
    />
  );
}
