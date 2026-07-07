import { GUEST_DOCUMENT_SLOTS } from '../../../lib/guest/document-slots';
import { useGuestValidationFlow } from '../../../hooks/useGuestValidationFlow';
import { UploadPanel } from '../../../components/ui/UploadPanel';
import { ValidationReportView } from '../report/ValidationReportView';
import '../guest.css';

type ValidationWizardProps = {
  onAskFollowUp?: (context: { validationRunId: string; documentIds: string[] }) => void;
};

export function ValidationWizard({ onAskFollowUp }: ValidationWizardProps) {
  const { step, slots, flowError, report, selectFile, removeFile, runValidation, reset } =
    useGuestValidationFlow();

  const documentIds = Object.values(slots)
    .map((slot) => slot?.documentId)
    .filter(Boolean) as string[];

  return (
    <div className="validation-wizard">
      <div className="validation-wizard__header">
        <div>
          <h2>Validate My Payslip</h2>
          <p className="guest-section__intro">
            Upload your payslip and optional supporting documents. Validation results are produced
            by the deterministic payroll rule engine.
          </p>
        </div>
        {step === 'report' && (
          <button type="button" className="btn btn--secondary" onClick={reset}>
            Start new validation
          </button>
        )}
      </div>

      <div className="validation-wizard__steps" aria-label="Validation progress">
        <span className={`validation-wizard__step ${step === 'upload' ? 'is-active' : ''}`}>
          1. Upload
        </span>
        <span className={`validation-wizard__step ${step === 'validating' ? 'is-active' : ''}`}>
          2. Validation
        </span>
        <span className={`validation-wizard__step ${step === 'report' ? 'is-active' : ''}`}>
          3. Results
        </span>
      </div>

      {flowError && <p className="chat-panel__error">{flowError}</p>}

      {step === 'upload' && (
        <>
          <div className="guest-workspace">
            {GUEST_DOCUMENT_SLOTS.map((slot) => (
              <div key={slot.id} className="document-slot">
                <div className="document-slot__header">
                  <strong>
                    {slot.label}
                    {!slot.optional ? ' (required)' : ' (optional)'}
                  </strong>
                </div>
                <p className="document-slot__why">{slot.why}</p>
                <UploadPanel
                  slots={[
                    {
                      id: slot.id,
                      label: slot.label,
                      accept: slot.accept,
                      optional: slot.optional,
                    },
                  ]}
                  selectedFileName={slots[slot.id]?.file.name}
                  errorMessage={slots[slot.id]?.error}
                  onFilesSelected={(_, file) => {
                    void selectFile(slot.id, file);
                  }}
                  onRemove={() => removeFile(slot.id)}
                />
              </div>
            ))}
          </div>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => {
              void runValidation();
            }}
            disabled={!slots.payslip?.file || Boolean(slots.payslip?.error)}
          >
            Run validation
          </button>
        </>
      )}

      {step === 'validating' && (
        <p className="guest-section__intro" aria-live="polite">
          Uploading documents and running validation. This may take a moment.
        </p>
      )}

      {step === 'report' && report && (
        <ValidationReportView
          report={report}
          documentIds={documentIds.length > 0 ? documentIds : [report.documentId]}
          onAskFollowUp={
            onAskFollowUp
              ? () =>
                  onAskFollowUp({
                    validationRunId: report.runId,
                    documentIds: documentIds.length > 0 ? documentIds : [report.documentId],
                  })
              : undefined
          }
        />
      )}
    </div>
  );
}
