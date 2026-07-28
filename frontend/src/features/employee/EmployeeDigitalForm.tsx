import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Info, Trash2 } from 'lucide-react';
import { ModalDialog, useConfirmDialog } from '../../components/ui/Dialog';
import { Skeleton, SkeletonText } from '../../components/ui/Skeleton';
import type { FieldDraft } from '../../hooks/useEmployeePayslipFlow';
import {
  buildDigitalFormSections,
  digitalFormNeedsShowMore,
  INITIAL_DIGITAL_FORM_VISIBLE_COUNT,
  orderDigitalFormFieldsForDisplay,
  type DigitalFormFieldModel,
  type DigitalFormSectionModel,
} from '../../lib/employee/digital-form-model';
import type { EmployeeFieldValidationMeta } from '../../lib/employee/field-validation-status';
import {
  normalizeFieldInput,
  usesMultilineEditor,
  type EmployeeFieldType,
} from '../../lib/employee/field-types';
import type { ExtractedPayslipField } from '../../types/api';
import { useAppLocale } from '../../hooks/useAppLocale';
import { FieldAiPopover } from '../guest/landing/FieldAiPopover';
import { FieldEvidenceDetails } from './FieldEvidenceDetails';
import '../guest/landing/landing-chat.css';

type EmployeeDigitalFormProps = {
  fields: ExtractedPayslipField[] | undefined;
  drafts: Record<string, FieldDraft>;
  editable: boolean;
  busy?: boolean;
  /** True while extraction/review data is still being fetched. */
  loading?: boolean;
  reviewNotice?: string | null;
  validationMap?: Record<string, EmployeeFieldValidationMeta>;
  /** Employee hides Other by default; accountant sees all extracted fields. */
  audience?: 'employee' | 'accountant';
  includeOther?: boolean;
  /**
   * Accountant batch: first N fields (priority-ordered); rest behind Show more.
   * Does not change persisted data.
   */
  collapseSecondaryFields?: boolean;
  onChangeField: (key: string, value: string) => void;
  onClearField: (key: string) => void;
  onRemoveField?: (key: string) => void;
  /** Opens Add Field modal in this form; parent receives name + value. */
  onAddField?: (payload: { name: string; value: string }) => void;
  /** Confirm a proposed field value (e.g. payroll period) without a dialog. */
  onApproveField?: (key: string) => void;
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

function sectionsFromOrderedFields(
  ordered: DigitalFormFieldModel[],
  groupBy: 'requirement' | 'registrySection',
): DigitalFormSectionModel[] {
  if (groupBy === 'registrySection') {
    const sectionIds = Array.from(new Set(ordered.map((field) => field.sectionId)));
    return sectionIds
      .map((id) => ({
        id,
        titleKey: `employee.digitalForm.sections.${id}`,
        fields: ordered.filter((field) => field.sectionId === id),
      }))
      .filter((section) => section.fields.length > 0);
  }
  const groups: Array<{ id: 'required' | 'expected' | 'other'; titleKey: string }> = [
    { id: 'required', titleKey: 'employee.digitalForm.sectionRequired' },
    { id: 'expected', titleKey: 'employee.digitalForm.sectionExpected' },
    { id: 'other', titleKey: 'employee.digitalForm.sectionOther' },
  ];
  return groups
    .map((group) => ({
      id: group.id,
      titleKey: group.titleKey,
      fields: ordered.filter((field) => field.requirementCategory === group.id),
    }))
    .filter((section) => section.fields.length > 0);
}

export function EmployeeDigitalForm({
  fields,
  drafts,
  editable,
  busy = false,
  loading = false,
  reviewNotice,
  validationMap,
  audience = 'employee',
  includeOther,
  collapseSecondaryFields = audience === 'accountant',
  onChangeField,
  onClearField: _onClearField,
  onRemoveField,
  onAddField,
  onApproveField,
}: EmployeeDigitalFormProps) {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const { confirm } = useConfirmDialog();
  const [showSecondary, setShowSecondary] = useState(false);
  const groupBy = audience === 'accountant' ? 'registrySection' : 'requirement';

  const fullSections = buildDigitalFormSections(fields, drafts, t, locale, {
    audience,
    includeOther,
    groupBy,
  });
  const allOrdered = orderDigitalFormFieldsForDisplay(
    fullSections.flatMap((section) => section.fields),
  );
  const showOnlyPrimary = collapseSecondaryFields && !showSecondary;
  const visibleOrdered = showOnlyPrimary
    ? allOrdered.slice(0, INITIAL_DIGITAL_FORM_VISIBLE_COUNT)
    : allOrdered;
  const sections = collapseSecondaryFields
    ? sectionsFromOrderedFields(visibleOrdered, groupBy)
    : fullSections;
  const hasMore = collapseSecondaryFields && digitalFormNeedsShowMore(allOrdered.length);
  const allFields = allOrdered;

  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [evidenceKey, setEvidenceKey] = useState<string | null>(null);
  const [draftValue, setDraftValue] = useState('');
  const [editError, setEditError] = useState<string | null>(null);
  const [addFieldOpen, setAddFieldOpen] = useState(false);
  const [addFieldName, setAddFieldName] = useState('');
  const [addFieldValue, setAddFieldValue] = useState('');
  const [addFieldError, setAddFieldError] = useState<string | null>(null);

  const editingField = editingKey
    ? allFields.find((field) => field.key === editingKey) ?? null
    : null;
  const evidenceField = evidenceKey
    ? fields?.find((field) => field.key === evidenceKey) ?? null
    : null;
  const editingType: EmployeeFieldType = editingField?.type ?? 'unknown';
  const multiline = usesMultilineEditor(editingType) || draftValue.length > 72 || draftValue.includes('\n');

  const openEditor = (key: string, currentValue: string) => {
    if (!editable || busy || loading) return;
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
    if (!onRemoveField || busy || loading) return;
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

  const openAddField = () => {
    if (!editable || busy || loading || !onAddField) return;
    setAddFieldName('');
    setAddFieldValue('');
    setAddFieldError(null);
    setAddFieldOpen(true);
  };

  const closeAddField = () => {
    setAddFieldOpen(false);
    setAddFieldName('');
    setAddFieldValue('');
    setAddFieldError(null);
  };

  const saveAddField = () => {
    if (!onAddField) return;
    const name = addFieldName.trim();
    if (!name) {
      setAddFieldError(t('employee.digitalForm.addFieldNameRequired'));
      return;
    }
    onAddField({ name, value: addFieldValue });
    closeAddField();
  };

  if (loading) {
    return (
      <div
        className="digital-form employee-digital-form"
        role="status"
        aria-busy="true"
        aria-live="polite"
        aria-label={t('employee.upload.digitalFormTitle')}
      >
        <Skeleton height={16} width="30%" />
        <SkeletonText lines={5} />
        <Skeleton height={16} width="40%" />
        <SkeletonText lines={4} />
      </div>
    );
  }

  if (allFields.length === 0) {
    return (
      <div
        className="digital-form employee-digital-form"
        role="form"
        aria-label={t('employee.upload.digitalFormTitle')}
      >
        <div className="digital-form__empty" role="status">
          <p>{t('employee.upload.noExtractedFields')}</p>
        </div>
        {editable && onAddField && (
          <button
            type="button"
            className="btn btn--secondary digital-form__add"
            onClick={openAddField}
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
      className={`digital-form employee-digital-form${
        audience === 'accountant' ? ' employee-digital-form--document' : ''
      }`}
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
            <h4
              className={`digital-form__section-title${
                audience === 'accountant' ? ' digital-form__section-title--document' : ''
              }`}
            >
              {t(section.titleKey)}
            </h4>
          )}
          <div className="digital-form__grid employee-digital-form__grid">
            {section.fields.map((field) => {
              const draft = drafts[field.key];
              const mapped = validationMap?.[field.key];
              // Keep WARNING+Approve while pending, and PASSED after userApproved, even if draft dirty.
              const meta =
                draft?.dirty && !mapped?.userApproved && !mapped?.requiresApproval
                  ? undefined
                  : mapped;
              const visual = statusVisual(meta?.status, t);
              const missingRequired =
                !meta?.requiresApproval &&
                !meta?.userApproved &&
                (field.missingRequired || meta?.neutralKind === 'missing_required');
              const staticTip =
                missingRequired
                  ? t('employee.digitalForm.missingRequiredExplain', { field: field.label })
                  : meta?.status === 'failed'
                    ? t('employee.digitalForm.failedFieldExplain', { field: field.label })
                    : meta?.status === 'uncertain' && !meta.requiresApproval
                      ? t('employee.digitalForm.uncertainFieldExplain', { field: field.label })
                      : null;
              const explanation =
                meta?.explanation ||
                staticTip ||
                (meta?.confidencePercent != null
                  ? t('employee.validation.confidenceExplain', {
                      percent: meta.confidencePercent,
                    })
                  : null);
              const preview = missingRequired && !field.value.trim()
                ? t('employee.digitalForm.notFoundOnPayslip')
                : field.preview || t('common.emDash');

              return (
                <div
                  key={field.key}
                  className={`digital-form__field employee-digital-form__field ${
                    field.columnSpan === 2 ? 'employee-digital-form__field--span-2' : ''
                  } ${visual?.fieldCss ?? ''} ${missingRequired ? 'digital-form__field--missing-required' : ''} ${draft?.dirty && !meta?.userApproved ? 'digital-form__field--edited' : ''}`.trim()}
                  data-field-type={field.type}
                  data-requirement={field.requirementCategory}
                >
                  <div className="employee-digital-form__card-header">
                    <span className="digital-form__label">
                      {field.label}
                      {field.requirementCategory === 'required' && (
                        <span className="digital-form__required-tag">
                          {t('employee.digitalForm.requiredTag')}
                        </span>
                      )}
                      {draft?.dirty && !meta?.userApproved && (
                        <span className="digital-form__edited">{t('validate.fieldEdited')}</span>
                      )}
                    </span>
                    <div className="employee-digital-form__card-header-actions">
                      {meta?.requiresApproval ? (
                        <span className="status-badge status-badge--warnings employee-digital-form__approval-badge">
                          {t('employee.digitalForm.requiresApproval')}
                        </span>
                      ) : null}
                      {meta?.requiresApproval && editable && onApproveField ? (
                        <button
                          type="button"
                          className="btn btn--ghost employee-digital-form__approve-btn"
                          onClick={() => onApproveField(field.key)}
                          disabled={busy}
                        >
                          {t('employee.digitalForm.approveField')}
                        </button>
                      ) : null}
                      {explanation ? (
                        <FieldAiPopover label={field.label} explanation={explanation} />
                      ) : null}
                      {fields?.find((item) => item.key === field.key)?.evidence_details && (
                        <button
                          type="button"
                          className="employee-digital-form__icon-btn"
                          onClick={() => setEvidenceKey(field.key)}
                          title={t('explainability.viewEvidence')}
                          aria-label={`${t('explainability.viewEvidence')}: ${field.label}`}
                        >
                          <Info size={16} strokeWidth={2} aria-hidden="true" />
                        </button>
                      )}
                      {editable && onRemoveField && (
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
                  </div>

                  <div className="employee-digital-form__card-body">
                    <div className="employee-digital-form__value-row">
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
                    {missingRequired && (
                      <p className="digital-form__missing-hint" role="status">
                        {t('employee.digitalForm.missingRequiredHint')}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ))}

      {hasMore && (
        <div className="employee-digital-form__more">
          <button
            type="button"
            className="btn btn--ghost employee-digital-form__more-btn"
            aria-expanded={showSecondary}
            onClick={() => setShowSecondary((value) => !value)}
          >
            {showSecondary
              ? t('employee.digitalForm.showLess')
              : t('employee.digitalForm.showMore')}
          </button>
        </div>
      )}

      {editable && onAddField && (
        <button
          type="button"
          className="btn btn--secondary digital-form__add"
          onClick={openAddField}
          disabled={busy}
        >
          {t('landingChat.form.addField')}
        </button>
      )}

      {addFieldOpen && (
        <ModalDialog
          title={t('employee.digitalForm.addFieldTitle')}
          onClose={closeAddField}
          footer={
            <>
              <button type="button" className="btn btn--secondary" onClick={closeAddField}>
                {t('common.cancel')}
              </button>
              <button type="button" className="btn btn--primary" onClick={saveAddField}>
                {t('employee.digitalForm.addFieldConfirm')}
              </button>
            </>
          }
        >
          <div className="employee-field-edit employee-field-edit--stack">
            <label className="employee-field-edit">
              <span className="employee-field-edit__name">
                {t('employee.digitalForm.addFieldName')}
              </span>
              <input
                className="digital-form__input"
                value={addFieldName}
                onChange={(event) => {
                  setAddFieldName(event.target.value);
                  setAddFieldError(null);
                }}
                autoFocus
              />
            </label>
            <label className="employee-field-edit">
              <span className="employee-field-edit__name">
                {t('employee.digitalForm.addFieldValue')}
              </span>
              <input
                className="digital-form__input"
                value={addFieldValue}
                onChange={(event) => setAddFieldValue(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    saveAddField();
                  }
                }}
              />
            </label>
            {addFieldError && (
              <p className="chat-panel__error" role="alert">
                {addFieldError}
              </p>
            )}
          </div>
        </ModalDialog>
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

      {evidenceField?.evidence_details && (
        <ModalDialog
          title={t('explainability.title')}
          onClose={() => setEvidenceKey(null)}
          footer={
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => setEvidenceKey(null)}
            >
              {t('common.close', { defaultValue: 'Close' })}
            </button>
          }
        >
          <FieldEvidenceDetails evidence={evidenceField.evidence_details} />
        </ModalDialog>
      )}
    </div>
  );
}
