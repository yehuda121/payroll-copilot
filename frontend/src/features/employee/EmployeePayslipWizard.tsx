import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { DragDropZone } from '../../components/ui/DragDropZone';
import { isImageFile } from '../../lib/guest/extraction-review';
import { useEmployeePayslipFlow } from '../../hooks/useEmployeePayslipFlow';
import type { DocumentLanguage } from '../../types/api';
import { EmployeeDigitalForm } from './EmployeeDigitalForm';
import { EmployeeValidationResults } from './EmployeeValidationResults';
import { IdentityPeriodCheck } from './IdentityPeriodCheck';
import '../guest/guest.css';
import '../guest/landing/landing-chat.css';
import './employee-payslip.css';

const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] as const;

const TIMELINE_STEPS = [
  { id: 'upload', labelKey: 'employee.upload.timeline.upload' },
  { id: 'prepare', labelKey: 'employee.upload.timeline.extraction' },
  { id: 'review', labelKey: 'employee.upload.timeline.review' },
  { id: 'validating', labelKey: 'employee.upload.timeline.validation' },
  { id: 'report', labelKey: 'employee.upload.timeline.results' },
] as const;

export function EmployeePayslipWizard() {
  const { t } = useTranslation();
  const reviewHeadingRef = useRef<HTMLHeadingElement>(null);
  const {
    step,
    busyPhase,
    isBusy,
    statusMessage,
    file,
    fileError,
    filePreviewUrl,
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
    cancelUploadSelection,
    updateFieldDraft,
    clearFieldDraft,
    startExtraction,
    cancelExtraction,
    confirmDuplicateVersion,
    confirmExtractedFields,
    continueToValidate,
    cancelValidation,
    acknowledgement,
    setAcknowledgement,
    isConfirmed,
    dirty,
    reviewTab,
    setReviewTab,
    reset,
  } = useEmployeePayslipFlow();

  const reviewNotice =
    extraction?.parser_status === 'completed'
      ? t('validate.reviewManualCheck')
      : extraction
        ? t('validate.reviewPartialNotice')
        : null;

  const years = Array.from({ length: 6 }, (_, i) => new Date().getFullYear() - i + 1);
  const stepOrder = ['upload', 'prepare', 'review', 'validating', 'report'] as const;
  const currentIndex = stepOrder.indexOf(step);

  useEffect(() => {
    if (step === 'review' || step === 'report') {
      reviewHeadingRef.current?.focus();
    }
  }, [step]);

  const timelineState = (index: number) => {
    if (index < currentIndex) return 'done';
    if (index === currentIndex) return 'current';
    return 'upcoming';
  };

  return (
    <div className="validation-wizard employee-payslip-wizard">
      <div className="validation-wizard__header">
        <div>
          <h2>{t('employee.upload.title')}</h2>
          <p className="guest-section__intro">{t('employee.upload.intro')}</p>
        </div>
        {(step === 'report' || step === 'review') && (
          <button
            type="button"
            className="btn btn--secondary"
            onClick={() => void reset()}
            disabled={isBusy}
          >
            {t('validate.startNew')}
          </button>
        )}
      </div>

      <ol className="employee-timeline" aria-label={t('validate.progressLabel')}>
        {TIMELINE_STEPS.map((item, index) => {
          const state = timelineState(index);
          return (
            <li
              key={item.id}
              className={`employee-timeline__step is-${state}`}
              aria-current={state === 'current' ? 'step' : undefined}
            >
              <span className="employee-timeline__marker" aria-hidden="true">
                {state === 'done' ? '✔' : index + 1}
              </span>
              <span className="employee-timeline__label">{t(item.labelKey)}</span>
              {state === 'current' && (
                <span className="employee-timeline__current">{t('employee.upload.timeline.current')}</span>
              )}
            </li>
          );
        })}
      </ol>

      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {statusMessage || (flowError ?? '')}
      </div>

      {flowError && (
        <p className="chat-panel__error" role="alert">
          {flowError}
        </p>
      )}

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
                  disabled={isBusy}
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
                  disabled={isBusy}
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
                disabled={isBusy}
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
            {file && (
              <div className="employee-upload-status" role="status">
                <p>{t('employee.upload.fileReady', { name: file.name })}</p>
                <button
                  type="button"
                  className="btn btn--secondary"
                  onClick={cancelUploadSelection}
                  disabled={isBusy}
                >
                  {t('employee.upload.cancelUpload')}
                </button>
              </div>
            )}
          </div>

          {duplicateConflict && (
            <div className="identity-period-check__banner is-warning" role="alertdialog">
              <p>{t('employee.upload.duplicateDetail')}</p>
              <button
                type="button"
                className="btn btn--secondary"
                disabled={isBusy}
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
            disabled={!file || Boolean(fileError) || isBusy}
          >
            {t('employee.upload.run')}
          </button>
        </>
      )}

      {(step === 'prepare' || step === 'validating') && (
        <div className="validation-wizard__prepare" aria-live="polite" aria-busy="true">
          <div className="validation-wizard__prepare-card">
            <div className="chat-typing" aria-hidden="true">
              <span className="chat-typing__dots">
                <span />
                <span />
                <span />
              </span>
            </div>
            <h3>
              {step === 'validating'
                ? t('employee.upload.validatingPayroll')
                : t('employee.upload.extractingDocument')}
            </h3>
            <p>
              {step === 'validating'
                ? t('employee.upload.validatingHint')
                : t('employee.upload.extractingHint')}
            </p>
            <div
              className="employee-progress"
              role="progressbar"
              aria-valuetext={statusMessage || undefined}
              aria-label={
                step === 'validating'
                  ? t('employee.upload.validatingPayroll')
                  : t('employee.upload.extractingDocument')
              }
            >
              <div className="employee-progress__bar" />
            </div>
            {step === 'prepare' && (
              <button type="button" className="btn btn--secondary" onClick={cancelExtraction}>
                {t('employee.upload.cancelExtraction')}
              </button>
            )}
            {step === 'validating' && (
              <button type="button" className="btn btn--secondary" onClick={cancelValidation}>
                {t('employee.upload.cancelValidation')}
              </button>
            )}
          </div>
        </div>
      )}

      {step === 'review' && extraction && identityCheck && periodCheck && (
        <div className="validation-wizard__review">
          <h3 ref={reviewHeadingRef} tabIndex={-1} className="employee-review-heading">
            {t('employee.upload.reviewHeading')}
          </h3>
          <p className="validation-wizard__doc-meta">
            {t('validate.uploadedDocument')}: {file?.name}
          </p>
          <IdentityPeriodCheck identity={identityCheck} period={periodCheck} />

          <div className="employee-review-tabs" role="tablist" aria-label={t('employee.upload.reviewTabs')}>
            <button
              type="button"
              role="tab"
              id="employee-tab-original"
              aria-selected={reviewTab === 'original'}
              aria-controls="employee-panel-original"
              className={`employee-review-tabs__tab ${reviewTab === 'original' ? 'is-active' : ''}`}
              onClick={() => setReviewTab('original')}
              disabled={busyPhase === 'confirming'}
            >
              {t('employee.upload.tabOriginal')}
            </button>
            <button
              type="button"
              role="tab"
              id="employee-tab-digital"
              aria-selected={reviewTab === 'digital'}
              aria-controls="employee-panel-digital"
              className={`employee-review-tabs__tab ${reviewTab === 'digital' ? 'is-active' : ''}`}
              onClick={() => setReviewTab('digital')}
              disabled={busyPhase === 'confirming'}
            >
              {t('employee.upload.tabDigital')}
            </button>
          </div>

          {reviewTab === 'original' ? (
            <div
              id="employee-panel-original"
              role="tabpanel"
              aria-labelledby="employee-tab-original"
              className="employee-original-preview"
            >
              {filePreviewUrl && isImageFile(file ?? undefined) ? (
                <img src={filePreviewUrl} alt={t('employee.upload.originalAlt', { name: file?.name })} />
              ) : filePreviewUrl ? (
                <iframe
                  title={t('employee.upload.originalAlt', { name: file?.name })}
                  src={filePreviewUrl}
                  className="employee-original-preview__pdf"
                />
              ) : (
                <p>{t('employee.upload.originalUnavailable')}</p>
              )}
            </div>
          ) : (
            <div
              id="employee-panel-digital"
              role="tabpanel"
              aria-labelledby="employee-tab-digital"
            >
              <EmployeeDigitalForm
                fields={extraction.fields}
                drafts={fieldDrafts}
                editable={!isConfirmed}
                busy={busyPhase === 'confirming'}
                reviewNotice={reviewNotice}
                onChangeField={updateFieldDraft}
                onClearField={clearFieldDraft}
              />
            </div>
          )}

          {dirty && !isConfirmed && (
            <p className="employee-payslip-wizard__unsaved" role="status">
              {t('employee.upload.unsavedChanges')}
            </p>
          )}
          <label className="employee-payslip-wizard__ack">
            <input
              type="checkbox"
              checked={acknowledgement}
              disabled={blocksConfirmation || isConfirmed || busyPhase === 'confirming'}
              onChange={(event) => setAcknowledgement(event.target.checked)}
            />
            <span>{t('employee.upload.confirmAcknowledgement')}</span>
          </label>
          <div className="employee-payslip-wizard__actions">
            <button
              type="button"
              className="btn btn--secondary btn--large"
              disabled={
                blocksConfirmation ||
                isConfirmed ||
                !acknowledgement ||
                busyPhase === 'confirming'
              }
              onClick={() => {
                void confirmExtractedFields();
              }}
            >
              {busyPhase === 'confirming'
                ? t('employee.upload.confirming')
                : isConfirmed
                  ? t('employee.upload.confirmed')
                  : t('employee.upload.confirmExtraction')}
            </button>
            <button
              type="button"
              className="btn btn--primary btn--large"
              disabled={blocksConfirmation || !isConfirmed || isBusy}
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
        <div>
          <h3 ref={reviewHeadingRef} tabIndex={-1} className="employee-review-heading">
            {t('employee.upload.timeline.results')}
          </h3>
          <EmployeeValidationResults
            report={report}
            identity={identityCheck}
            period={periodCheck}
            fileName={file?.name}
          />
        </div>
      )}
    </div>
  );
}
