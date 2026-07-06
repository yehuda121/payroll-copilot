import { PortalPage } from '../../components/PortalPage';

export function SystemDashboardPage() {
  return (
    <PortalPage
      title="System Dashboard"
      description="Platform health, service status, and configuration overview for administrators."
      integrationNote="@integration-point ADMIN_DASHBOARD"
    />
  );
}
