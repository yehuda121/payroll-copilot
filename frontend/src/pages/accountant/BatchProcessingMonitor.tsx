import { PortalPage } from '../../components/PortalPage';

export function BatchProcessingMonitorPage() {
  return (
    <PortalPage
      title="Batch Processing Monitor"
      description="Track active and completed batch jobs, split progress, and per-slip validation status."
      integrationNote="@integration-point BATCH_LIST — GET /batch/jobs/{id}"
    />
  );
}
