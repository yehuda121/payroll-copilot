import { PortalPage } from '../../components/PortalPage';
import { UploadPanel } from '../../components/ui/UploadPanel';
import { Card } from '../../components/ui/Card';

export function BulkPayrollUploadPage() {
  return (
    <PortalPage
      title="Bulk Payroll Upload"
      description="Upload a single PDF containing hundreds of payslips for automated splitting, identification, and deterministic validation."
      integrationNote="@integration-point BATCH_SERVICE — POST /batch/payslips"
    >
      <Card title="Bulk PDF Upload">
        <UploadPanel
          slots={[{ id: 'bulk_pdf', label: 'Bulk Payslip PDF', accept: '.pdf' }]}
        />
        <p className="guest-section__intro" style={{ marginTop: '1rem' }}>
          Processing runs as a background Celery job. Monitor progress in Batch Processing Monitor.
        </p>
      </Card>
    </PortalPage>
  );
}
