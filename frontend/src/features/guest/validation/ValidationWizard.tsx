import { useTranslation } from 'react-i18next';
import { GUEST_ACTIVE_DOCUMENT_SLOTS } from '../../../lib/guest/document-slots';
import { isImageFile } from '../../../lib/guest/extraction-review';
import { useGuestValidationFlow } from '../../../hooks/useGuestValidationFlow';
import { DragDropZone } from '../../../components/ui/DragDropZone';
import { UploadPanel } from '../../../components/ui/UploadPanel';
import { ValidationReportView } from '../report/ValidationReportView';
import { ChatDocumentReviewCard } from '../landing/ChatDocumentReviewCard';
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
    extraction,
    entries,
    documentLanguage,
    setDocumentLanguage,
    selectFile,
    removeFile,
    updateEntry,
    deleteEntry,
    addEntry,
    startExtraction,
    continueToValidate,
    reset,
  } = useGuestValidationFlow();

  const documentIds = Object.values(slots)
    .map((slot) => slot?.documentId)
    .filter(Boolean) as string[];

  const payslipFile = slots.payslip?.file;
  const preparingLabel = isImageFile(payslipFile)
    ? t('validate.preparingImage')
    : t('validate.preparingPdf');

  const stepActive = (candidate: typeof step) => {
    const order = ['upload', 'prepare', 'review', 'validating', 'report'] as const;
    return order.indexOf(step) >= order.indexOf(candidate);
  };

  return (
    <div className="validation-wizard">
      <div className="validation-wizard__header">
        <div>
          <h2>{t('validate.title')}</h2>
          <p className="guest-section__intro">{t('validate.intro')}</p>
        </div>
        {(step === 'report' || step === 'review') && (
          <button type="button" className="btn btn--secondary" onClick={reset}>
            {t('validate.startNew')}
          </button>
        )}
      </div>

      <ol className="validation-wizard__steps" aria-label={t('validate.progressLabel')}>
        <li className={`validation-wizard__step ${step === 'upload' ? 'is-active' : ''} ${stepActive('upload') ? 'is-done' : ''}`}>
          {t('validate.stepUpload')}
        </li>
        <li className={`validation-wizard__step ${step === 'prepare' ? 'is-active' : ''} ${stepActive('prepare') ? 'is-done' : ''}`}>
          {t('validate.stepPrepare')}
        </li>
        <li className={`validation-wizard__step ${step === 'review' ? 'is-active' : ''} ${stepActive('review') ? 'is-done' : ''}`}>
          {t('validate.stepReview')}
        </li>
        <li className={`validation-wizard__step ${step === 'report' || step === 'validating' ? 'is-active' : ''} ${stepActive('report') || step === 'validating' ? 'is-done' : ''}`}>
          {t('validate.stepResults')}
        </li>
      </ol>

      {flowError && <p className="chat-panel__error">{flowError}</p>}

      {step === 'upload' && (
        <>
          <div className="document-language">
            <label htmlFor="document-language">
              <span>{t('validate.documentLanguage')}</span>
              <select
                id="document-language"
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
          </div>

          <div className="validation-wizard__upload-primary">
            <h3>
              {t('slots.payslip')} ({t('common.required')})
            </h3>
            <p className="document-slot__why">{t('slots.payslipWhy')}</p>
            <DragDropZone
              accept=".pdf,.png,.jpg,.jpeg"
              selectedFileName={slots.payslip?.file.name}
              errorMessage={slots.payslip?.error}
              onFileSelected={(file) => {
                void selectFile('payslip', file);
              }}
              onRemove={() => removeFile('payslip')}
            />
          </div>

          <div className="validation-wizard__upload-supporting">
            <h3>{t('validate.supportingTitle')}</h3>
            <div className="guest-workspace">
              {GUEST_ACTIVE_DOCUMENT_SLOTS.filter((slot) => slot.id !== 'payslip').map((slot) => (
                <div key={slot.id} className="document-slot">
                  <div className="document-slot__header">
                    <strong>
                      {t(slot.labelKey)} ({t('common.optional')})
                    </strong>
                  </div>
                  <p className="document-slot__why">{t(slot.whyKey)}</p>
                  <UploadPanel
                    slots={[
                      {
                        id: slot.id,
                        label: t(slot.labelKey),
                        accept: slot.accept,
                        optional: true,
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
          </div>

          <button
            type="button"
            className="btn btn--primary btn--large"
            onClick={() => {
              void startExtraction();
            }}
            disabled={!slots.payslip?.file || Boolean(slots.payslip?.error)}
          >
            {t('validate.run')}
          </button>
        </>
      )}

      {(step === 'prepare' || step === 'validating') && (
        <div className="validation-wizard__prepare" aria-live="polite">
          <div className="validation-wizard__prepare-card">
            <div className="chat-typing" aria-hidden="true">
              <span className="chat-typing__dots">
                <span />
                <span />
                <span />
              </span>
            </div>
            <h3>{step === 'validating' ? t('validate.validatingChecklist') : preparingLabel}</h3>
            <p>
              {step === 'validating' ? t('validate.validatingChecklistHint') : t('validate.preparingHint')}
            </p>
            <p>{t('validate.preparingDetails')}</p>
          </div>
        </div>
      )}

      {step === 'review' && extraction && (
        <div className="validation-wizard__review">
          <ChatDocumentReviewCard
            fileName={slots.payslip?.file.name || t('slots.payslip')}
            entries={entries}
            confirmed={false}
            busy={false}
            onChangeEntry={updateEntry}
            onDeleteEntry={deleteEntry}
            onAddEntry={addEntry}
            onConfirm={() => {
              void continueToValidate();
            }}
          />
        </div>
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
