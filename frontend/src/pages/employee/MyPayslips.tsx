import { PortalPage } from '../../components/PortalPage';

export function MyPayslipsPage() {
  return (
    <PortalPage
      title="My Payslips"
      description="View uploaded payslips, OCR extraction results, and validation summaries."
      integrationNote="@integration-point EMPLOYEE_PAYSLIPS"
    />
  );
}
