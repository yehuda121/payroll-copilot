import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { DragDropZone } from '../../components/ui/DragDropZone';
import { useConfirmDialog } from '../../components/ui/Dialog';
import { EmployeeDigitalForm } from '../../features/employee/EmployeeDigitalForm';
import { EmployeeFixedDocumentForm } from '../../features/employee/EmployeeFixedDocumentForm';
import {
  useEmployeeDocumentWorkspace,
  type DocumentWorkspaceTab,
  type PersistentDocumentType,
} from '../../hooks/useEmployeeDocumentWorkspace';
import type { DocumentLanguage } from '../../types/api';
import '../../features/employee/employee-payslip.css';
import '../../features/guest/landing/landing-chat.css';
import './PayslipMonthWorkspace.css';
import './MyPayslips.css';

const DOCUMENT_TYPES: Array<{ id: PersistentDocumentType; labelKey: string }> = [
  { id: 'national_id', labelKey: 'employee.documents.tabs.idCard' },
  { id: 'id_appendix', labelKey: 'employee.documents.tabs.idAppendix' },
  { id: 'contract', labelKey: 'employee.documents.tabs.contract' },
];

const INNER_TABS: Array<{ id: DocumentWorkspaceTab; labelKey: string }> = [
  { id: 'upload', labelKey: 'employee.workspace.tabUpload' },
  { id: 'digital', labelKey: 'employee.documents.tabDigital' },
  { id: 'original', labelKey: 'employee.upload.tabOriginal' },
];

export function DocumentCenterPage() {
  const { t } = useTranslation();
  const [documentType, setDocumentType] = useState<PersistentDocumentType>('national_id');
  const flow = useEmployeeDocumentWorkspace(documentType);

  const typeTitle = useMemo(() => {
    const match = DOCUMENT_TYPES.find((row) => row.id === documentType);
    return match ? t(match.labelKey) : t('employee.documents.pageTitle');
  }, [documentType, t]);

  return (
    <PortalPage
      title={t('employee.documents.pageTitle')}
      description={t('employee.documents.pageDescription')}
    >
      <div className="employee-month-workspace">
        <div
          className="employee-review-tabs"
          role="tablist"
          aria-label={t('employee.documents.typeTabs')}
        >
          {DOCUMENT_TYPES.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={documentType === item.id}
              className={`employee-review-tabs__tab ${documentType === item.id ? 'is-active' : ''}`}
              onClick={() => setDocumentType(item.id)}
              disabled={flow.isBusy}
            >
              {t(item.labelKey)}
            </button>
          ))}
        </div>

        <div className="sr-only" aria-live="polite">
          {flow.statusMessage || flow.error || ''}
        </div>
        {flow.error && (
          <p className="chat-panel__error" role="alert">
            {flow.error}
          </p>
        )}
        {flow.statusMessage && (
          <p role="status">{flow.statusMessage}</p>
        )}

        {flow.loading ? (
          <p role="status">{t('common.loading')}</p>
        ) : (
          <>
            <div
              className="employee-review-tabs"
              role="tablist"
              aria-label={t('employee.documents.workspaceTabs', { type: typeTitle })}
            >
              {INNER_TABS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={flow.tab === item.id}
                  className={`employee-review-tabs__tab ${flow.tab === item.id ? 'is-active' : ''}`}
                  onClick={() => flow.setTab(item.id)}
                  disabled={flow.isBusy}
                >
                  {t(item.labelKey)}
                </button>
              ))}
            </div>

            {flow.tab === 'upload' && (
              <UploadTab flow={flow} documentType={documentType} typeTitle={typeTitle} />
            )}
            {flow.tab === 'digital' && (
              <DigitalTab flow={flow} documentType={documentType} />
            )}
            {flow.tab === 'original' && (
              <OriginalTab flow={flow} documentType={documentType} />
            )}
          </>
        )}
      </div>
    </PortalPage>
  );
}

type Flow = ReturnType<typeof useEmployeeDocumentWorkspace>;

function UploadTab({
  flow,
  documentType,
  typeTitle,
}: {
  flow: Flow;
  documentType: PersistentDocumentType;
  typeTitle: string;
}) {
  const { t } = useTranslation();
  const { confirm } = useConfirmDialog();
  const fileReady = Boolean(flow.pendingFile) && !flow.fileError;
  const hasStoredOriginal = flow.hasDocument;

  const uploadEnabled = !flow.isBusy && fileReady;

  const onUpload = async () => {
    if (!flow.pendingFile) return;
    if (hasStoredOriginal) {
      const ok = await confirm({
        title: t('employee.documents.replaceDigitalFormTitle'),
        message: t('employee.documents.replaceConfirmMessage', { type: typeTitle }),
        confirmLabel: t('employee.documents.extractDigitalForm'),
        cancelLabel: t('common.cancel'),
        variant: 'danger',
      });
      if (!ok) return;
    }
    await flow.extractDocument();
  };

  return (
    <section className="employee-month-empty" aria-label={t('employee.workspace.tabUpload')}>
      {!hasStoredOriginal && !flow.pendingFile ? (
        <>
          <h3>{t('employee.documents.noDocumentUploaded', { type: typeTitle })}</h3>
          <p>{t('employee.documents.emptyHint', { type: typeTitle })}</p>
        </>
      ) : hasStoredOriginal && !flow.pendingFile ? (
        <>
          <h3>{t('employee.workspace.originalReadOnly')}</h3>
          <p>{t('employee.documents.originalReadOnlyHint', { type: typeTitle })}</p>
          <p>
            {t('validate.uploadedDocument')}: {flow.item?.original_filename}
          </p>
        </>
      ) : (
        <>
          <h3>
            {hasStoredOriginal
              ? t('employee.workspace.replaceHintTitle')
              : t('employee.documents.uploadTitle', { type: typeTitle })}
          </h3>
          <p>
            {hasStoredOriginal
              ? t('employee.documents.replaceHint', { type: typeTitle })
              : t('employee.documents.uploadHint', { type: typeTitle })}
          </p>
          {flow.pendingFile && (
            <p>
              {t('validate.uploadedDocument')}: {flow.pendingFile.name}
            </p>
          )}
        </>
      )}

      <div className="document-language">
        <label htmlFor={`doc-language-${documentType}`}>
          <span>{t('validate.documentLanguage')}</span>
          <select
            id={`doc-language-${documentType}`}
            value={flow.documentLanguage}
            disabled={flow.isBusy}
            onChange={(event) =>
              flow.setDocumentLanguage(event.target.value as DocumentLanguage)
            }
          >
            <option value="he">{t('validate.langHe')}</option>
            <option value="en">{t('validate.langEn')}</option>
            <option value="ar">{t('validate.langAr')}</option>
            <option value="auto">{t('validate.langAuto')}</option>
          </select>
        </label>
      </div>

      <DragDropZone
        accept=".pdf,.png,.jpg,.jpeg"
        selectedFileName={flow.pendingFile?.name}
        errorMessage={flow.fileError ?? undefined}
        onFileSelected={(file) => {
          void flow.selectFile(file);
        }}
        onRemove={flow.pendingFile ? flow.deleteSelectedFile : undefined}
      />

      {flow.busyPhase === 'extracting' && (
        <div className="employee-extract-loading" aria-busy="true" aria-live="polite">
          <h3>{t('employee.documents.extracting')}</h3>
          <div
            className="employee-progress"
            role="progressbar"
            aria-label={t('employee.documents.extracting')}
          >
            <div className="employee-progress__bar" />
          </div>
        </div>
      )}

      <div className="employee-payslip-wizard__actions">
        <button
          type="button"
          className="btn btn--primary btn--large"
          disabled={!uploadEnabled}
          onClick={() => {
            void onUpload();
          }}
        >
          {t('employee.documents.extractDigitalForm')}
        </button>
        {flow.pendingFile && (
          <button
            type="button"
            className="btn btn--danger"
            disabled={flow.isBusy}
            onClick={flow.deleteSelectedFile}
          >
            {t('employee.workspace.deleteSelectedOnly')}
          </button>
        )}
      </div>
    </section>
  );
}

function DigitalTab({
  flow,
  documentType,
}: {
  flow: Flow;
  documentType: PersistentDocumentType;
}) {
  const { t } = useTranslation();
  const fixedType =
    documentType === 'national_id' || documentType === 'id_appendix'
      ? documentType
      : null;

  return (
    <section aria-label={t('employee.documents.tabDigital')}>
      {fixedType ? (
        <EmployeeFixedDocumentForm
          documentType={fixedType}
          values={flow.fixedValues}
          busy={flow.isBusy}
          reviewNotice={t('employee.documents.fixedFormNotice')}
          onChangeField={flow.updateFieldDraft}
        />
      ) : (
        <EmployeeDigitalForm
          fields={flow.fields}
          drafts={flow.fieldDrafts}
          editable
          busy={flow.isBusy}
          reviewNotice={t('employee.documents.digitalFormNotice')}
          onChangeField={flow.updateFieldDraft}
          onClearField={flow.clearFieldDraft}
          onRemoveField={flow.removeField}
          onAddField={flow.addField}
        />
      )}
      {flow.hasDigitalForm && (
        <div className="employee-payslip-wizard__actions employee-digital-validate">
          <button
            type="button"
            className="btn btn--primary"
            disabled={flow.isBusy || !flow.hasDirtyFields}
            onClick={() => {
              void flow.saveDigitalForm();
            }}
          >
            {flow.busyPhase === 'saving'
              ? t('employee.documents.savingDigitalForm')
              : t('employee.documents.saveDigitalForm')}
          </button>
        </div>
      )}
    </section>
  );
}

function OriginalTab({
  flow,
  documentType,
}: {
  flow: Flow;
  documentType: PersistentDocumentType;
}) {
  const { t, i18n } = useTranslation();
  const { confirm } = useConfirmDialog();

  if (!flow.hasDocument) {
    return <p>{t('employee.upload.originalUnavailable')}</p>;
  }

  const uploadedAt = flow.item?.uploaded_at
    ? new Intl.DateTimeFormat(i18n.language, {
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(new Date(flow.item.uploaded_at))
    : t('common.emDash');

  return (
    <section
      className="employee-original-meta"
      aria-label={t('employee.upload.tabOriginal')}
    >
      <h3>{t('employee.upload.tabOriginal')}</h3>
      <dl className="employee-original-meta__list">
        <div>
          <dt>{t('employee.workspace.originalFilename')}</dt>
          <dd>{flow.item?.original_filename || t('common.emDash')}</dd>
        </div>
        <div>
          <dt>{t('employee.workspace.originalUploadedAt')}</dt>
          <dd>{uploadedAt}</dd>
        </div>
        <div>
          <dt>{t('employee.workspace.originalDocumentType')}</dt>
          <dd>
            {t(`employee.documents.types.${documentType}`, {
              defaultValue: documentType,
            })}
          </dd>
        </div>
        <div>
          <dt>{t('employee.workspace.originalStatus')}</dt>
          <dd>
            {flow.item?.processing_status
              ? t(`employee.lifecycle.${flow.item.processing_status}`, {
                  defaultValue: flow.item.processing_status,
                })
              : t('common.emDash')}
          </dd>
        </div>
      </dl>
      {flow.item?.document_id && (
        <div className="employee-payslip-wizard__actions">
          <button
            type="button"
            className="btn btn--danger"
            disabled={flow.isBusy}
            onClick={() => {
              void (async () => {
                const ok = await confirm({
                  title: t('employee.workspace.deleteOriginalTitle'),
                  message: t('employee.workspace.deleteOriginalMessage'),
                  confirmLabel: t('employee.workspace.deleteOriginal'),
                  cancelLabel: t('common.cancel'),
                  variant: 'danger',
                });
                if (!ok) return;
                await flow.deleteOwnedDocument();
              })();
            }}
          >
            {t('employee.workspace.deleteOriginal')}
          </button>
        </div>
      )}
    </section>
  );
}
