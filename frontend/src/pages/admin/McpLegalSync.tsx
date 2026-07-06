import { PortalPage } from '../../components/PortalPage';

export function McpLegalSyncPage() {
  return (
    <PortalPage
      title="MCP Legal Sync"
      description="Compare local YAML rules against Kol Zchut and government sources. Diffs require manual approval before update."
      integrationNote="@integration-point MCP_SYNC — GET /compliance/diff-proposals"
    />
  );
}
