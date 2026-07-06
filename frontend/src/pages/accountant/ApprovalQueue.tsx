import { PortalPage } from '../../components/PortalPage';

export function ApprovalQueuePage() {
  return (
    <PortalPage
      title="Approval Queue"
      description="Review items requiring accountant approval — legal rule diffs, low-confidence extractions, and policy exceptions."
      integrationNote="@integration-point COMPLIANCE_DIFFS"
    />
  );
}
