import { PortalPage } from '../../components/PortalPage';

export function ValidationHistoryPage() {
  return (
    <PortalPage
      title="Validation History"
      description="Browse past deterministic validation runs, findings, and confidence breakdowns."
      integrationNote="@integration-point VALIDATION_HISTORY"
    />
  );
}
