import { PortalPage } from '../../components/PortalPage';

export function AttendancePage() {
  return (
    <PortalPage
      title="Attendance"
      description="Review attendance records, leave balances, and imported attendance reports."
      integrationNote="@integration-point EMPLOYEE_ATTENDANCE"
    />
  );
}
