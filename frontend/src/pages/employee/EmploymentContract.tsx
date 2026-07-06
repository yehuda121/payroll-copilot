import { PortalPage } from '../../components/PortalPage';

export function EmploymentContractPage() {
  return (
    <PortalPage
      title="Employment Contract"
      description="Access your employment agreement and contract-derived validation context (RAG-indexed)."
      integrationNote="@integration-point EMPLOYEE_CONTRACT"
    />
  );
}
