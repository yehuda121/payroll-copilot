import { useState } from 'react';
import { Card } from '../ui/Card';
import { UploadPanel } from '../ui/UploadPanel';
import '../ui/ui.css';

/**
 * Guest document upload area on the public landing page.
 * @integration-point GUEST_UPLOAD — documentsService.upload + authService.createGuestSession
 */
export function GuestUploadArea() {
  const [selectedFiles, setSelectedFiles] = useState<Record<string, string>>({});

  const handleFile = (slotId: string, file: File) => {
    setSelectedFiles((prev) => ({ ...prev, [slotId]: file.name }));
    // @integration-point GUEST_UPLOAD_HANDLER
    // await authService.createGuestSession();
    // await documentsService.upload(file, mapSlotToDocumentType(slotId));
  };

  return (
    <Card title="Upload Documents for Review">
      <p className="guest-section__intro">
        Upload your payroll documents for OCR extraction and deterministic validation.
        AI explanations are advisory only — compliance decisions are made by the rule engine.
      </p>
      <UploadPanel
        slots={[
          { id: 'payslip', label: 'Payslip', accept: '.pdf,.png,.jpg' },
          { id: 'attendance', label: 'Attendance Report', accept: '.pdf,.xlsx,.csv' },
          { id: 'contract', label: 'Employment Contract', accept: '.pdf' },
          { id: 'id_document', label: 'ID Document', accept: '.pdf,.png,.jpg', optional: true },
        ]}
        onFilesSelected={handleFile}
      />
      {Object.keys(selectedFiles).length > 0 && (
        <ul className="guest-section__file-list">
          {Object.entries(selectedFiles).map(([slot, name]) => (
            <li key={slot}>
              <strong>{slot}:</strong> {name} (selected — not uploaded)
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
