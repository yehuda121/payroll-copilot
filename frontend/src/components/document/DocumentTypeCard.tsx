import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ModalDialog, useConfirmDialog } from '../ui/Dialog';
import { FormInfoPanel, FormSection, FormShell } from '../ui/form/FormPrimitives';
import { TrashIcon, WarningTriangleIcon } from '../ui/icons';
import { DocumentPreviewCard } from './DocumentPreviewCard';
import { AppendixChildrenForm } from '../../features/employee/AppendixChildrenForm';
import { EmployeeDigitalForm } from '../../features/employee/EmployeeDigitalForm';
import { EmployeeFixedDocumentForm } from '../../features/employee/EmployeeFixedDocumentForm';
import {
  useEmployeeDocumentWorkspace,
  type PersistentDocumentType,
} from '../../hooks/useEmployeeDocumentWorkspace';
import {
  formatAppendixChildPreview,
  isAppendixDocumentType,
} from '../../lib/employee/document-fixed-forms';
import {
  documentFieldSectionsForType,
  getDocumentFieldDefinition,
  resolveDocumentFieldLabel,
  resolveDocumentFieldSectionTitle,
} from '../../lib/employee/document-field-registry';
import {
  validateAppendixChildren,
  type AppendixChildRowError,
} from '../../lib/employee/appendix-children-validation';
import { parseBirthDate } from '../../lib/employee/birth-date';
import { validatePersonName } from '../../lib/employee/field-text';
import { validateNationalId } from '../../lib/employee/israeli-id';
import { resolveDocumentCardStatus } from '../../lib/employee/document-card-status';
import { validateUploadFile } from '../../lib/guest/upload-guardrails';
import type { DocumentPreviewField } from './DocumentPreviewCard';

function formatFixedPreviewValue(
  documentType: PersistentDocumentType,
  key: string,
  raw: string,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (documentType === 'contract' && key === 'salary_basis' && raw.trim()) {
    const basisKey = `employee.documents.contract.salaryBasis.${raw.trim()}`;
    const translated = t(basisKey);
    if (translated !== basisKey) return translated;
  }
  return raw;
}

const TYPE_LABEL: Record<PersistentDocumentType, string> = {
  national_id: 'employee.documents.tabs.idCard',
  id_appendix: 'employee.documents.tabs.idAppendix',
  contract: 'employee.documents.tabs.contract',
};

type DeleteScope = 'original' | 'digital' | 'both';

/**
 * One document-type card with edit/upload/delete wired to the existing workspace hook.
 */
export function DocumentTypeCard({ documentType }: { documentType: PersistentDocumentType }) {
  const { t } = useTranslation();
  const { confirm } = useConfirmDialog();
  const flow = useEmployeeDocumentWorkspace(documentType);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const editBodyRef = useRef<HTMLDivElement | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteScope, setDeleteScope] = useState<DeleteScope>('both');
  const [idFieldErrors, setIdFieldErrors] = useState<
    Partial<Record<'national_id' | 'birth_date' | 'full_name', string>>
  >({});
  const [appendixRowErrors, setAppendixRowErrors] = useState<AppendixChildRowError[]>([]);

  const title = t(TYPE_LABEL[documentType]);
  const settled = !flow.loading;
  const hasOriginal = flow.hasDocument;
  const hasDigital = flow.hasDigitalForm;
  const empty = settled && !hasOriginal && !hasDigital;
  const allowManualEditWhenEmpty =
    documentType === 'national_id' ||
    documentType === 'contract' ||
    isAppendixDocumentType(documentType);
  const status = resolveDocumentCardStatus({
    loading: flow.loading,
    settled,
    hasOriginal,
    hasDigital,
    confirmationStatus: flow.item?.confirmation_status,
  });

  const previewFields = useMemo((): DocumentPreviewField[] => {
    if (isAppendixDocumentType(documentType)) {
      const sectionTitle = resolveDocumentFieldSectionTitle('family', t);
      if (flow.appendixChildren.length === 0) {
        const childrenLabel =
          resolveDocumentFieldLabel(documentType, 'children', t) ??
          t('employee.documents.fields.children');
        return [
          {
            key: 'children-empty',
            label: childrenLabel,
            value: t('employee.documents.appendix.emptyChildren'),
            sectionId: 'family',
            sectionTitle,
          },
        ];
      }
      return flow.appendixChildren.map((child, index) => ({
        key: `child-${index}`,
        label: t('employee.documents.appendix.childLabel', { index: index + 1 }),
        value: formatAppendixChildPreview(child, t('common.emDash')),
        sectionId: 'family',
        sectionTitle,
      }));
    }

    if (documentType === 'national_id' || documentType === 'contract') {
      const sections = documentFieldSectionsForType(documentType);
      const out: DocumentPreviewField[] = [];
      for (const section of sections) {
        const sectionTitle = t(section.titleKey);
        for (const def of section.fields) {
          const label = t(def.label_i18n_key);
          const raw = flow.fixedValues[def.canonical_key] ?? '';
          out.push({
            key: def.canonical_key,
            label,
            value: formatFixedPreviewValue(documentType, def.canonical_key, raw, t),
            sectionId: section.id,
            sectionTitle,
          });
        }
      }
      return out;
    }

    return flow.fields.map((field) => {
      const def = getDocumentFieldDefinition(documentType, field.key);
      return {
        key: field.key,
        label: def ? t(def.label_i18n_key) : field.key,
        value: String(field.value ?? ''),
      };
    });
  }, [documentType, flow.appendixChildren, flow.fields, flow.fixedValues, t]);

  useEffect(() => {
    if (!editOpen) return;
    const timer = window.setTimeout(() => {
      const root = editBodyRef.current;
      const first = root?.querySelector<HTMLElement>(
        'input:not([disabled]), textarea:not([disabled]), select:not([disabled])',
      );
      first?.focus();
    }, 40);
    return () => window.clearTimeout(timer);
  }, [editOpen]);

  useEffect(() => {
    if (!editOpen) {
      setIdFieldErrors({});
      setAppendixRowErrors([]);
    }
  }, [editOpen]);

  const requestCloseEdit = async () => {
    if (flow.hasDirtyFields) {
      const keep = await confirm({
        title: t('employee.documents.unsavedTitle'),
        message: t('employee.documents.unsavedMessage'),
        confirmLabel: t('employee.documents.unsavedKeep'),
        cancelLabel: t('employee.documents.unsavedDiscard'),
        variant: 'warning',
      });
      if (keep) return;
    }
    setEditOpen(false);
  };

  const runUploadWithFile = async (file: File) => {
    const validated = await validateUploadFile(
      documentType === 'id_appendix' ? 'national_id' : documentType,
      file,
      [],
      t,
    );
    if (!validated.ok) {
      await flow.selectFile(file);
      return;
    }
    await flow.selectFile(file);
    if (hasOriginal) {
      const ok = await confirm({
        title: t('employee.documents.replaceDigitalFormTitle'),
        message: t('employee.documents.replaceConfirmMessage', { type: title }),
        confirmLabel: t('employee.documents.extractDigitalForm'),
        cancelLabel: t('common.cancel'),
        variant: 'danger',
      });
      if (!ok) {
        flow.deleteSelectedFile();
        return;
      }
    }
    await flow.extractDocument(file);
  };

  const onFiles = (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    void runUploadWithFile(file);
  };

  const validateAndSave = async () => {
    if (documentType === 'national_id') {
      const errors: Partial<Record<'national_id' | 'birth_date' | 'full_name', string>> = {};
      const nextValues = { ...flow.fixedValues };
      const fullNameRaw = nextValues.full_name ?? '';
      if (fullNameRaw.trim()) {
        const nameResult = validatePersonName(fullNameRaw);
        if (!nameResult.ok) {
          if (nameResult.code === 'digits') {
            errors.full_name = t('employee.documents.validation.nameNoDigits');
          } else if (nameResult.code === 'max_length') {
            errors.full_name = t('employee.documents.validation.nameMaxLength');
          } else {
            errors.full_name = t('employee.documents.validation.nameInvalid');
          }
        } else {
          nextValues.full_name = nameResult.value;
        }
      } else {
        nextValues.full_name = '';
      }

      const nationalId = nextValues.national_id ?? '';
      if (nationalId.trim()) {
        const idResult = validateNationalId(nationalId);
        if (!idResult.ok) {
          if (idResult.code === 'digits_only') {
            errors.national_id = t('employee.documents.validation.nationalIdDigits');
          } else if (idResult.code === 'length') {
            errors.national_id = t('employee.documents.validation.nationalIdLength');
          } else if (idResult.code === 'checksum') {
            errors.national_id = t('employee.documents.validation.nationalIdChecksum');
          }
        } else {
          nextValues.national_id = idResult.digits;
        }
      }

      const birth = nextValues.birth_date ?? '';
      if (birth.trim()) {
        const parsed = parseBirthDate(birth);
        if (!parsed.ok) {
          errors.birth_date = t('employee.documents.validation.dateInvalid');
        } else {
          nextValues.birth_date = parsed.iso;
        }
      } else {
        nextValues.birth_date = '';
      }

      setIdFieldErrors(errors);
      if (Object.keys(errors).length > 0) return;
      const ok = await flow.saveDigitalForm({ fixedValuesOverride: nextValues });
      if (ok) setEditOpen(false);
      return;
    }

    if (isAppendixDocumentType(documentType)) {
      const result = validateAppendixChildren(flow.appendixChildren);
      if (!result.ok) {
        setAppendixRowErrors(result.errors);
        return;
      }
      setAppendixRowErrors([]);
      const ok = await flow.saveDigitalForm({ appendixChildrenOverride: result.children });
      if (ok) setEditOpen(false);
      return;
    }

    const ok = await flow.saveDigitalForm();
    if (ok) setEditOpen(false);
  };

  const buildDeleteConfirmMessage = (scope: DeleteScope) => {
    const originalLine = `• ${t('employee.documents.deleteOriginal')}`;
    const digitalLine = `• ${t('employee.documents.deleteDigital')}`;
    if (scope === 'both') {
      return [
        t('employee.documents.deleteConfirmIntroPlural'),
        '',
        originalLine,
        digitalLine,
        '',
        t('employee.documents.deleteConfirmIrreversible'),
      ].join('\n');
    }
    const item = scope === 'original' ? originalLine : digitalLine;
    return [
      t('employee.documents.deleteConfirmIntroSingular'),
      '',
      item,
      '',
      t('employee.documents.deleteConfirmIrreversible'),
    ].join('\n');
  };

  const requestDelete = async () => {
    const ok = await confirm({
      title: t('employee.documents.deleteConfirmTitle'),
      message: buildDeleteConfirmMessage(deleteScope),
      confirmLabel: t('employee.documents.deleteConfirm'),
      cancelLabel: t('common.cancel'),
      variant: 'danger',
    });
    if (!ok) return;
    await flow.deleteOwnedDocument(deleteScope);
    setDeleteOpen(false);
  };

  return (
    <>
      <DocumentPreviewCard
        title={title}
        status={status}
        fields={previewFields}
        empty={empty}
        busy={flow.isBusy}
        filename={flow.item?.original_filename}
        allowManualEditWhenEmpty={allowManualEditWhenEmpty}
        hasOriginal={hasOriginal}
        hasDigital={hasDigital}
        onEdit={() => setEditOpen(true)}
        onUpload={() => fileInputRef.current?.click()}
        onDelete={() => {
          setDeleteScope(hasOriginal && hasDigital ? 'both' : hasOriginal ? 'original' : 'digital');
          setDeleteOpen(true);
        }}
        onFilesDropped={(list) => onFiles(list)}
        footer={
          flow.error ? (
            <p className="chat-panel__error document-preview-card__error" role="alert">
              {flow.error}
            </p>
          ) : null
        }
      />

      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg"
        hidden
        onChange={(event) => {
          onFiles(event.target.files);
          event.target.value = '';
        }}
      />

      {editOpen ? (
        <ModalDialog
          title={t('employee.documents.editTitle', { type: title })}
          size="lg"
          className={`document-edit-modal${
            documentType === 'national_id' ||
            documentType === 'id_appendix' ||
            documentType === 'contract'
              ? ' document-edit-modal--fixed'
              : ''
          }`}
          closeLabel={t('common.close')}
          onClose={() => {
            void requestCloseEdit();
          }}
          footer={
            <>
              <button
                type="button"
                className="btn btn--secondary"
                disabled={flow.isBusy}
                onClick={() => {
                  void requestCloseEdit();
                }}
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                className="btn btn--primary"
                disabled={flow.isBusy || !flow.hasDirtyFields}
                onClick={() => {
                  void validateAndSave();
                }}
              >
                {flow.busyPhase === 'saving'
                  ? t('employee.documents.savingDigitalForm')
                  : t('employee.documents.saveDigitalForm')}
              </button>
            </>
          }
        >
          <div ref={editBodyRef}>
            {isAppendixDocumentType(documentType) ? (
              <AppendixChildrenForm
                childrenList={flow.appendixChildren}
                busy={flow.isBusy}
                reviewNotice={t('employee.documents.fixedFormNotice')}
                rowErrors={appendixRowErrors}
                onChangeChild={(index, patch) => {
                  setAppendixRowErrors((prev) => prev.filter((row) => row.index !== index));
                  flow.updateChild(index, patch);
                }}
                onAddChild={flow.addChild}
                onRemoveChild={(index) => {
                  setAppendixRowErrors([]);
                  flow.removeChild(index);
                }}
              />
            ) : documentType === 'national_id' || documentType === 'contract' ? (
              <EmployeeFixedDocumentForm
                documentType={documentType}
                values={flow.fixedValues}
                busy={flow.isBusy}
                reviewNotice={t('employee.documents.fixedFormNotice')}
                fieldErrors={idFieldErrors}
                onChangeField={(key, value) => {
                  setIdFieldErrors((prev) => {
                    const next = { ...prev };
                    delete next[key as keyof typeof next];
                    return next;
                  });
                  flow.updateFieldDraft(key, value);
                }}
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
          </div>
        </ModalDialog>
      ) : null}

      {deleteOpen ? (
        <ModalDialog
          title={t('employee.documents.deleteTitle', { type: title })}
          variant="danger"
          size="md"
          onClose={() => setDeleteOpen(false)}
          footer={
            <>
              <button
                type="button"
                className="btn btn--secondary"
                onClick={() => setDeleteOpen(false)}
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                className="btn btn--danger"
                disabled={flow.isBusy}
                onClick={() => {
                  void requestDelete();
                }}
              >
                {t('employee.documents.deleteConfirm')}
              </button>
            </>
          }
        >
          <FormShell
            aside={
              <FormInfoPanel
                tone="warning"
                eyebrow={t('forms.info.tipEyebrow')}
                title={t('forms.info.documentDeleteTitle')}
                icon={<WarningTriangleIcon size={14} aria-hidden="true" />}
              >
                <p>{t('forms.info.documentDeleteBody')}</p>
              </FormInfoPanel>
            }
          >
            <FormSection
              title={t('employee.documents.deleteLegend')}
              description={t('employee.documents.deleteIntro')}
              icon={<TrashIcon size={18} />}
              columns={1}
            >
              <fieldset className="document-delete-choices pc-form-field--span-2">
                <legend className="visually-hidden">{t('employee.documents.deleteLegend')}</legend>
                <label
                  title={
                    !hasOriginal ? t('employee.documents.deleteOriginalDisabledHint') : undefined
                  }
                >
                  <input
                    type="radio"
                    name={`delete-scope-${documentType}`}
                    checked={deleteScope === 'original'}
                    disabled={!hasOriginal}
                    onChange={() => setDeleteScope('original')}
                  />
                  <span>
                    <strong>{t('employee.documents.deleteOriginal')}</strong>
                    <br />
                    {t('employee.documents.deleteOriginalHint')}
                  </span>
                </label>
                <label
                  title={!hasDigital ? t('employee.documents.deleteDigitalDisabledHint') : undefined}
                >
                  <input
                    type="radio"
                    name={`delete-scope-${documentType}`}
                    checked={deleteScope === 'digital'}
                    disabled={!hasDigital}
                    onChange={() => setDeleteScope('digital')}
                  />
                  <span>
                    <strong>{t('employee.documents.deleteDigital')}</strong>
                    <br />
                    {t('employee.documents.deleteDigitalHint')}
                  </span>
                </label>
                <label
                  title={
                    !(hasOriginal && hasDigital)
                      ? t('employee.documents.deleteBothDisabledHint')
                      : undefined
                  }
                >
                  <input
                    type="radio"
                    name={`delete-scope-${documentType}`}
                    checked={deleteScope === 'both'}
                    disabled={!(hasOriginal && hasDigital)}
                    onChange={() => setDeleteScope('both')}
                  />
                  <span>
                    <strong>{t('employee.documents.deleteBoth')}</strong>
                    <br />
                    {t('employee.documents.deleteBothHint')}
                  </span>
                </label>
              </fieldset>
            </FormSection>
          </FormShell>
        </ModalDialog>
      ) : null}
    </>
  );
}
