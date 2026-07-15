import { useTranslation } from 'react-i18next';
import { ExtractionReviewTable } from '../../components/ui/ExtractionReviewTable';
import { DragDropZone } from '../../components/ui/DragDropZone';
import { isImageFile, buildExtractionReviewFields } from '../../lib/guest/extraction-review';
import { useEmployeePayslipFlow } from '../../hooks/useEmployeePayslipFlow';
import { ValidationReportView } from '../guest/report/ValidationReportView';
import type { DocumentLanguage } from '../../types/api';
import { IdentityPeriodCheck } from './IdentityPeriodCheck';
import '../guest/guest.css';
import './employee-payslip.css';

const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] as const;

export function EmployeePayslipWizard() {
  const { t } = useTranslation();
  const {
    step,
    file,
    fileError,
    periodYear,
    periodMonth,
    setPeriodYear,
    setPeriodMonth,
    documentLanguage,
    setDocumentLanguage,
    flowError,
    extraction,
    fieldDrafts,
    report,
    duplicateConflict,
    identityCheck,
    periodCheck,
    blocksConfirmation,
    selectFile,
    removeFile,
    updateFieldDraft,
    clearFieldDraft,
    startExtraction,
    confirmDuplicateVersion,
    confirmExtractedFields,
    continueToValidate,
    acknowledgement,
    setAcknowledgement,
    isConfirmed,
    dirty,
    reset,
  } = useEmployeePayslipFlow();

  const preparingLabel = isImageFile(file ?? undefined)
    ? t('validate.preparingImage')
    : t('validate.preparingPdf');
  const reviewFields = buildExtractionReviewFields(extraction?.fields, t);
  const reviewNotice =
    extraction?.parser_status === 'completed'
      ? t('validate.reviewManualCheck')
      : extraction
        ? t('validate.reviewPartialNotice')
        : null;

  const years = Array.from({ length: 6 }, (_, i) => new Date().getFullYear() - i + 1);

  const stepActive = (candidate: typeof step) => {
    const order = ['upload', 'prepare', 'review', 'validating', 'report'] as const;
    return order.indexOf(step) >= order.indexOf(candidate);
  };

  return (
    <div className="validation-wizard employee-payslip-wizard">
      <div className="validation-wizard__header">
        <div>
          <h2>{t('employee.upload.title')}</h2>
          <p className="guest-section__intro">{t('employee.upload.intro')}</p>
        </div>
        {(step === 'report' || step === 'review') && (
          <button type="button" className="btn btn--secondary" onClick={() => void reset()}>
            {t('validate.startNew')}
          </button>
        )}
      </div>

      <ol className="validation-wizard__steps" aria-label={t('validate.progressLabel')}>
        <li
          className={`validation-wizard__step ${step === 'upload' ? 'is-active' : ''} ${stepActive('upload') ? 'is-done' : ''}`}
        >
          {t('validate.stepUpload')}
        </li>
        <li
          className={`validation-wizard__step ${step === 'prepare' ? 'is-active' : ''} ${stepActive('prepare') ? 'is-done' : ''}`}
        >
          {t('validate.stepPrepare')}
        </li>
        <li
          className={`validation-wizard__step ${step === 'review' ? 'is-active' : ''} ${stepActive('review') ? 'is-done' : ''}`}
        >
          {t('validate.stepReview')}
        </li>
        <li
          className={`validation-wizard__step ${step === 'report' || step === 'validating' ? 'is-active' : ''} ${stepActive('report') || step === 'validating' ? 'is-done' : ''}`}
        >
          {t('validate.stepResults')}
        </li>
      </ol>

      {flowError && <p className="chat-panel__error">{flowError}</p>}

      {step === 'upload' && (
        <>
          <div className="employee-payslip-wizard__period">
            <h3>{t('employee.upload.periodTitle')}</h3>
            <p className="document-language__hint">{t('employee.upload.periodHint')}</p>
            <div className="employee-payslip-wizard__period-row">
              <label>
                <span>{t('employee.upload.year')}</span>
                <select
                  value={periodYear}
                  onChange={(event) => setPeriodYear(Number(event.target.value))}
                  required
                >
                  {years.map((year) => (
                    <option key={year} value={year}>
                      {year}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>{t('employee.upload.month')}</span>
                <select
                  value={periodMonth}
                  onChange={(event) => setPeriodMonth(Number(event.target.value))}
                  required
                >
                  {MONTHS.map((month) => (
                    <option key={month} value={month}>
                      {t(`employee.upload.months.${month}`)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>

          <div className="document-language">
            <label htmlFor="employee-document-language">
              <span>{t('validate.documentLanguage')}</span>
              <select
                id="employee-document-language"
                value={documentLanguage}
                onChange={(event) => setDocumentLanguage(event.target.value as DocumentLanguage)}
              >
                <option value="auto">{t('validate.langAuto')}</option>
                <option value="he">{t('validate.langHe')}</option>
                <option value="en">{t('validate.langEn')}</option>
                <option value="ar">{t('validate.langAr')}</option>
              </select>
            </label>
          </div>

          <div className="validation-wizard__upload-primary">
            <h3>
              {t('slots.payslip')} ({t('common.required')})
            </h3>
            <DragDropZone
              accept=".pdf,.png,.jpg,.jpeg"
              selectedFileName={file?.name}
              errorMessage={fileError ?? undefined}
              onFileSelected={(next) => {
                void selectFile(next);
              }}
              onRemove={removeFile}
            />
          </div>

          {duplicateConflict && (
            <div className="identity-period-check__banner is-warning" role="alertdialog">
              <p>{t('employee.upload.duplicateDetail')}</p>
              <button
                type="button"
                className="btn btn--secondary"
                onClick={() => {
                  void confirmDuplicateVersion();
                }}
              >
                {t('employee.upload.confirmNewVersion')}
              </button>
            </div>
          )}

          <button
            type="button"
            className="btn btn--primary btn--large"
            onClick={() => {
              void startExtraction();
            }}
            disabled={!file || Boolean(fileError)}
          >
            {t('employee.upload.run')}
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
              {step === 'validating'
                ? t('validate.validatingChecklistHint')
                : t('validate.preparingHint')}
            </p>
          </div>
        </div>
      )}

      {step === 'review' && extraction && identityCheck && periodCheck && (
        <div className="validation-wizard__review">
          <p className="validation-wizard__doc-meta">
            {t('validate.uploadedDocument')}: {file?.name}
          </p>
          <IdentityPeriodCheck identity={identityCheck} period={periodCheck} />
          <ExtractionReviewTable
            fields={reviewFields}
            drafts={fieldDrafts}
            editable
            reviewNotice={reviewNotice}
            onChangeField={updateFieldDraft}
            onClearField={clearFieldDraft}
          />
          {dirty && (
            <p className="employee-payslip-wizard__unsaved" role="status">
              {t('employee.upload.unsavedChanges')}
            </p>
          )}
          <label className="employee-payslip-wizard__ack">
            <input
              type="checkbox"
              checked={acknowledgement}
              disabled={blocksConfirmation || isConfirmed}
              onChange={(event) => setAcknowledgement(event.target.checked)}
            />
            <span>{t('employee.upload.confirmAcknowledgement')}</span>
          </label>
          <div className="employee-payslip-wizard__actions">
            <button
              type="button"
              className="btn btn--secondary btn--large"
              disabled={blocksConfirmation || isConfirmed || !acknowledgement}
              onClick={() => {
                void confirmExtractedFields();
              }}
            >
              {isConfirmed
                ? t('employee.upload.confirmed')
                : t('employee.upload.confirmExtraction')}
            </button>
            <button
              type="button"
              className="btn btn--primary btn--large"
              disabled={blocksConfirmation || !isConfirmed}
              onClick={() => {
                void continueToValidate();
              }}
            >
              {t('employee.upload.runValidation')}
            </button>
          </div>
          {blocksConfirmation && (
            <p className="employee-payslip-wizard__blocked">{t('employee.upload.confirmBlocked')}</p>
          )}
          {!isConfirmed && !blocksConfirmation && (
            <p className="employee-payslip-wizard__hint">{t('employee.upload.confirmBeforeValidate')}</p>
          )}
        </div>
      )}

      {step === 'report' && report && (
        <ValidationReportView
          report={report}
          documentIds={[report.documentId]}
        />
      )}
    </div>
  );
}
