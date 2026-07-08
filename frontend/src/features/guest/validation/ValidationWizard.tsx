import { useTranslation } from 'react-i18next';
import { GUEST_DOCUMENT_SLOTS } from '../../../lib/guest/document-slots';
import { useGuestValidationFlow } from '../../../hooks/useGuestValidationFlow';
import { UploadPanel } from '../../../components/ui/UploadPanel';
import { ValidationReportView } from '../report/ValidationReportView';
import type { DocumentLanguage } from '../../../types/api';
import '../guest.css';

type ValidationWizardProps = {
  onAskFollowUp?: (context: { validationRunId: string; documentIds: string[] }) => void;
};

export function ValidationWizard({ onAskFollowUp }: ValidationWizardProps) {
  const { t } = useTranslation();
  const {
    step,
    slots,
    flowError,
    report,
    documentLanguage,
    setDocumentLanguage,
    selectFile,
    removeFile,
    runValidation,
    reset,
  } = useGuestValidationFlow();

  const documentIds = Object.values(slots)
    .map((slot) => slot?.documentId)
    .filter(Boolean) as string[];

  return (
    <div className="validation-wizard">
      <div className="validation-wizard__header">
        <div>
          <h2>{t('validate.title')}</h2>
          <p className="guest-section__intro">{t('validate.intro')}</p>
        </div>
        {step === 'report' && (
          <button type="button" className="btn btn--secondary" onClick={reset}>
            {t('validate.startNew')}
          </button>
        )}
      </div>

      <div className="validation-wizard__steps" aria-label={t('validate.progressLabel')}>
        <span className={`validation-wizard__step ${step === 'upload' ? 'is-active' : ''}`}>
          {t('validate.stepUpload')}
        </span>
        <span className={`validation-wizard__step ${step === 'validating' ? 'is-active' : ''}`}>
          {t('validate.stepValidation')}
        </span>
        <span className={`validation-wizard__step ${step === 'report' ? 'is-active' : ''}`}>
          {t('validate.stepResults')}
        </span>
      </div>

      {flowError && <p className="chat-panel__error">{flowError}</p>}

      {step === 'upload' && (
        <>
          <div className="document-language">
            <label>
              <span>{t('validate.documentLanguage')}</span>
              <select
                value={documentLanguage}
                onChange={(event) => setDocumentLanguage(event.target.value as DocumentLanguage)}
              >
                <option value="auto">{t('validate.langAuto')}</option>
                <option value="he">{t('validate.langHe')}</option>
                <option value="en">{t('validate.langEn')}</option>
                <option value="ar">{t('validate.langAr')}</option>
              </select>
            </label>
            <p className="document-language__hint">{t('validate.documentLanguageHint')}</p>
            <p className="document-language__hint">{t('validate.ocrNotConnected')}</p>
          </div>
          <div className="guest-workspace">
            {GUEST_DOCUMENT_SLOTS.map((slot) => (
              <div key={slot.id} className="document-slot">
                <div className="document-slot__header">
                  <strong>
                    {t(slot.labelKey)}
                    {!slot.optional
                      ? ` (${t('common.required')})`
                      : ` (${t('common.optional')})`}
                  </strong>
                </div>
                <p className="document-slot__why">{t(slot.whyKey)}</p>
                <UploadPanel
                  slots={[
                    {
                      id: slot.id,
                      label: t(slot.labelKey),
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
            {t('validate.run')}
          </button>
        </>
      )}

      {step === 'validating' && (
        <p className="guest-section__intro" aria-live="polite">
          {t('validate.validating')}
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
