import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pencil, Trash2 } from 'lucide-react';
import { ModalDialog, useConfirmDialog } from '../../components/ui/Dialog';
import type { FieldDraft } from '../../hooks/useEmployeePayslipFlow';
import { buildDigitalFormSections } from '../../lib/employee/digital-form-model';
import type { EmployeeFieldValidationMeta } from '../../lib/employee/field-validation-status';
import {
  normalizeFieldInput,
  usesMultilineEditor,
  type EmployeeFieldType,
} from '../../lib/employee/field-types';
import type { ExtractedPayslipField } from '../../types/api';
import { useAppLocale } from '../../hooks/useAppLocale';
import { FieldAiPopover } from '../guest/landing/FieldAiPopover';
import '../guest/landing/landing-chat.css';

type EmployeeDigitalFormProps = {
  fields: ExtractedPayslipField[] | undefined;
  drafts: Record<string, FieldDraft>;
  editable: boolean;
  busy?: boolean;
  reviewNotice?: string | null;
  validationMap?: Record<string, EmployeeFieldValidationMeta>;
  onChangeField: (key: string, value: string) => void;
  onClearField: (key: string) => void;
  onRemoveField?: (key: string) => void;
  onAddField?: () => void;
};

function statusVisual(
  status: EmployeeFieldValidationMeta['status'] | undefined,
  t: (key: string, opts?: { defaultValue?: string }) => string,
) {
  switch (status) {
    case 'passed':
      return {
        icon: '✓',
        css: 'is-passed',
        fieldCss: 'digital-form__field--found',
        label: t('employee.validation.status.passed'),
      };
    case 'failed':
      return {
        icon: '!',
        css: 'is-failed',
        fieldCss: 'digital-form__field--failed',
        label: t('employee.validation.status.failed'),
      };
    case 'uncertain':
      return {
        icon: '⚠',
        css: 'is-uncertain',
        fieldCss: 'digital-form__field--uncertain',
        label: t('employee.validation.status.uncertain'),
      };
    case 'unchecked':
      return {
        icon: '–',
        css: 'is-unchecked',
        fieldCss: 'digital-form__field--missing',
        label: t('employee.validation.status.unchecked'),
      };
    default:
      return null;
  }
}

export function EmployeeDigitalForm({
  fields,
  drafts,
  editable,
  busy = false,
  reviewNotice,
  validationMap,
  onChangeField,
  onClearField: _onClearField,
  onRemoveField,
  onAddField,
}: EmployeeDigitalFormProps) {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const { confirm } = useConfirmDialog();
  const sections = buildDigitalFormSections(fields, drafts, t, locale);
  const allFields = sections.flatMap((section) => section.fields);

  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [draftValue, setDraftValue] = useState('');
  const [editError, setEditError] = useState<string | null>(null);

  const editingField = editingKey
    ? allFields.find((field) => field.key === editingKey) ?? null
    : null;
  const editingType: EmployeeFieldType = editingField?.type ?? 'unknown';
  const multiline = usesMultilineEditor(editingType) || draftValue.length > 72 || draftValue.includes('\n');

  const openEditor = (key: string, currentValue: string) => {
    if (!editable || busy) return;
    setEditingKey(key);
    setDraftValue(currentValue);
    setEditError(null);
  };

  const closeEditor = () => {
    setEditingKey(null);
    setDraftValue('');
    setEditError(null);
  };

  const saveEditor = () => {
    if (!editingKey || !editingField) return;
    const normalized = normalizeFieldInput(draftValue, editingField.type);
    if (!normalized.ok) {
      setEditError(t(normalized.messageKey));
      return;
    }
    onChangeField(editingKey, normalized.value);
    closeEditor();
  };

  const requestDeleteField = async (key: string) => {
    if (!onRemoveField || busy) return;
    const ok = await confirm({
      title: t('employee.digitalForm.deleteFieldTitle'),
      message: t('employee.digitalForm.deleteFieldMessage'),
      confirmLabel: t('employee.digitalForm.deleteFieldConfirm'),
      cancelLabel: t('common.cancel'),
      variant: 'danger',
    });
    if (!ok) return;
    onRemoveField(key);
  };

  if (allFields.length === 0) {
    return (
      <div
        className="digital-form employee-digital-form"
        role="form"
        aria-label={t('employee.upload.digitalFormTitle')}
      >
        <div className="digital-form__empty" role="alert">
          <p>{t('employee.upload.noExtractedFields')}</p>
        </div>
        {editable && onAddField && (
          <button
            type="button"
            className="btn btn--secondary digital-form__add"
            onClick={onAddField}
            disabled={busy}
          >
            {t('landingChat.form.addField')}
          </button>
        )}
      </div>
    );
  }

  return (
    <div
      className="digital-form employee-digital-form"
      role="form"
      aria-label={t('employee.upload.digitalFormTitle')}
    >
      <header className="digital-form__header">
        <h3 className="digital-form__title">{t('employee.upload.digitalFormTitle')}</h3>
        {reviewNotice && <p className="digital-form__hint">{reviewNotice}</p>}
      </header>

      {sections.map((section) => (
        <section
          key={section.id}
          className="digital-form__section employee-digital-form__section"
          data-section-id={section.id}
        >
          {section.titleKey && (
            <h4 className="digital-form__section-title">{t(section.titleKey)}</h4>
          )}
          <div className="digital-form__grid employee-digital-form__grid">
            {section.fields.map((field) => {
              const draft = drafts[field.key];
              const meta = draft?.dirty ? undefined : validationMap?.[field.key];
              const visual = statusVisual(meta?.status, t);
              const explanation =
                meta?.explanation ||
                (meta?.confidencePercent != null
                  ? t('employee.validation.confidenceExplain', {
                      percent: meta.confidencePercent,
                    })
                  : null);
              const preview = field.preview || t('common.emDash');

              return (
                <div
                  key={field.key}
                  className={`digital-form__field employee-digital-form__field ${
                    field.columnSpan === 2 ? 'employee-digital-form__field--span-2' : ''
                  } ${visual?.fieldCss ?? ''} ${draft?.dirty ? 'digital-form__field--edited' : ''}`.trim()}
                  data-field-type={field.type}
                >
                  <div className="employee-digital-form__card-header">
                    <span className="digital-form__label">
                      {field.label}
                      {draft?.dirty && (
                        <span className="digital-form__edited">{t('validate.fieldEdited')}</span>
                      )}
                    </span>
                    {visual && (
                      <span
                        className={`employee-field-status ${visual.css}`}
                        title={explanation || visual.label}
                      >
                        <span aria-hidden="true">{visual.icon}</span>
                        <span>{visual.label}</span>
                        {explanation && (
                          <FieldAiPopover label={field.label} explanation={explanation} />
                        )}
                      </span>
                    )}
                  </div>

                  <div className="employee-digital-form__card-body">
                    {editable ? (
                      <button
                        type="button"
                        className="digital-form__value-btn"
                        onClick={() => openEditor(field.key, field.value)}
                        disabled={busy}
                        aria-invalid={meta?.status === 'failed'}
                        aria-label={`${field.label}: ${preview}`}
                      >
                        <span className="digital-form__value-text">{preview}</span>
                      </button>
                    ) : (
                      <p className="digital-form__readonly digital-form__value-text">{preview}</p>
                    )}
                  </div>

                  {editable && (
                    <div className="employee-digital-form__card-footer">
                      <button
                        type="button"
                        className="employee-digital-form__icon-btn"
                        onClick={() => openEditor(field.key, field.value)}
                        disabled={busy}
                        title={t('employee.digitalForm.editField')}
                        aria-label={t('employee.digitalForm.editField')}
                      >
                        <Pencil size={16} strokeWidth={2} aria-hidden="true" />
                      </button>
                      {onRemoveField && (
                        <button
                          type="button"
                          className="employee-digital-form__icon-btn employee-digital-form__icon-btn--danger"
                          onClick={() => {
                            void requestDeleteField(field.key);
                          }}
                          disabled={busy}
                          title={t('employee.digitalForm.deleteField')}
                          aria-label={t('employee.digitalForm.deleteField')}
                        >
                          <Trash2 size={16} strokeWidth={2} aria-hidden="true" />
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      ))}

      {editable && onAddField && (
        <button
          type="button"
          className="btn btn--secondary digital-form__add"
          onClick={onAddField}
          disabled={busy}
        >
          {t('landingChat.form.addField')}
        </button>
      )}

      {editingField && (
        <ModalDialog
          title={t('employee.validation.editFieldTitle')}
          onClose={closeEditor}
          wide={multiline}
          footer={
            <>
              <button type="button" className="btn btn--secondary" onClick={closeEditor}>
                {t('common.cancel')}
              </button>
              <button type="button" className="btn btn--primary" onClick={saveEditor}>
                {t('employee.validation.editFieldSave')}
              </button>
            </>
          }
        >
          <label className="employee-field-edit">
            <span className="employee-field-edit__name">{editingField.label}</span>
            {multiline ? (
              <textarea
                className="digital-form__input employee-field-edit__textarea"
                value={draftValue}
                rows={Math.min(16, Math.max(6, draftValue.split('\n').length + 2))}
                onChange={(event) => {
                  setDraftValue(event.target.value);
                  setEditError(null);
                }}
                autoFocus
              />
            ) : (
              <input
                className="digital-form__input"
                value={draftValue}
                onChange={(event) => {
                  setDraftValue(event.target.value);
                  setEditError(null);
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    saveEditor();
                  }
                }}
                autoFocus
                inputMode={
                  editingType === 'number' ||
                  editingType === 'currency' ||
                  editingType === 'percentage'
                    ? 'decimal'
                    : undefined
                }
              />
            )}
          </label>
          {editError && (
            <p className="employee-field-edit__error" role="alert">
              {editError}
            </p>
          )}
        </ModalDialog>
      )}
    </div>
  );
}
