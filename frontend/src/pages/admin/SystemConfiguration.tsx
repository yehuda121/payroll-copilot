import { PortalPage } from '../../components/PortalPage';

export function SystemConfigurationPage() {
  return (
    <PortalPage
      title="System Configuration"
      description="Organization settings, locale defaults, rate limits, storage, and integration keys."
      integrationNote="@integration-point SYSTEM_CONFIG"
    />
  );
}
