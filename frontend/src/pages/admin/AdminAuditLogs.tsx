import { PortalPage } from '../../components/PortalPage';

export function AdminAuditLogsPage() {
  return (
    <PortalPage
      title="Audit Logs"
      description="System-wide append-only audit logs with 7-year retention policy."
      integrationNote="@integration-point ADMIN_AUDIT_LOGS"
    />
  );
}
