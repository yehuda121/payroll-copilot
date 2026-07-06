import { PortalPage } from '../../components/PortalPage';

export function EmployeeDashboardPage() {
  return (
    <PortalPage
      title="Employee Dashboard"
      description="Overview of your recent payslips, validation status, and document activity."
      integrationNote="@integration-point EMPLOYEE_DASHBOARD"
    />
  );
}
