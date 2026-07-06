import { PortalPage } from '../../components/PortalPage';

export function AccountantAuditLogsPage() {
  return (
    <PortalPage
      title="Audit Logs"
      description="Append-only audit trail for accountant actions, batch operations, and approval decisions."
      integrationNote="@integration-point ACCOUNTANT_AUDIT_LOGS"
    />
  );
}
