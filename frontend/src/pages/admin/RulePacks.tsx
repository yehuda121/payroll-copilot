import { PortalPage } from '../../components/PortalPage';

export function RulePacksPage() {
  return (
    <PortalPage
      title="Rule Packs"
      description="Manage YAML legal rule packs, versions, and approval workflow. Local YAML remains authoritative."
      integrationNote="@integration-point RULE_PACKS — backend/config/rules/labor_law"
    />
  );
}
