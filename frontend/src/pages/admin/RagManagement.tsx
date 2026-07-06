import { PortalPage } from '../../components/PortalPage';

export function RagManagementPage() {
  return (
    <PortalPage
      title="RAG Management"
      description="Manage indexed contracts, policies, and embeddings in pgvector. Used for contract-specific rule context."
      integrationNote="@integration-point RAG_MANAGEMENT"
    />
  );
}
