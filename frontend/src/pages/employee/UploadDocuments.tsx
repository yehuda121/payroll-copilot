import { PortalPage } from '../../components/PortalPage';
import { UploadPanel } from '../../components/ui/UploadPanel';

export function UploadDocumentsPage() {
  return (
    <PortalPage
      title="Upload Documents"
      description="Submit payslips, attendance reports, contracts, and optional ID documents for validation."
      integrationNote="@integration-point DOCUMENTS_SERVICE"
    >
      <UploadPanel
        slots={[
          { id: 'payslip', label: 'Payslip', accept: '.pdf,.png,.jpg' },
          { id: 'attendance', label: 'Attendance Report', accept: '.pdf,.xlsx,.csv' },
          { id: 'contract', label: 'Employment Contract', accept: '.pdf' },
          { id: 'id_document', label: 'ID Document', accept: '.pdf,.png,.jpg', optional: true },
        ]}
      />
    </PortalPage>
  );
}
