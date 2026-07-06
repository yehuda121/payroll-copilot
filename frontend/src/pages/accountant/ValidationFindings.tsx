import { PortalPage } from '../../components/PortalPage';

export function ValidationFindingsPage() {
  return (
    <PortalPage
      title="Validation Findings"
      description="Review aggregated deterministic findings across employees, departments, and batch runs."
      integrationNote="@integration-point VALIDATION_FINDINGS"
    />
  );
}
