import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ActionIconButton } from '../ui/ActionIconButton';
import { PencilIcon, TrashIcon, UploadIcon } from '../ui/icons';
import { DocumentStatusBadge } from './DocumentStatusBadge';
import type { DocumentCardStatus } from '../../lib/employee/document-card-status';
import './document-preview-card.css';

export type DocumentPreviewField = {
  key: string;
  label: string;
  value: string;
  /** When set, fields are grouped under this section (payslip-style). */
  sectionId?: string;
  sectionTitle?: string | null;
};

type DocumentPreviewSection = {
  id: string;
  title: string | null;
  fields: DocumentPreviewField[];
};

function groupPreviewFields(fields: DocumentPreviewField[]): DocumentPreviewSection[] {
  const sections: DocumentPreviewSection[] = [];
  const indexById = new Map<string, number>();
  for (const field of fields) {
    const id = field.sectionId ?? '_default';
    let index = indexById.get(id);
    if (index === undefined) {
      index = sections.length;
      indexById.set(id, index);
      sections.push({
        id,
        title: field.sectionTitle ?? null,
        fields: [],
      });
    }
    sections[index].fields.push(field);
  }
  return sections;
}

type DocumentPreviewCardProps = {
  title: string;
  status: DocumentCardStatus;
  fields: DocumentPreviewField[];
  empty: boolean;
  busy?: boolean;
  filename?: string | null;
  /** When true, Edit stays available even with no original/digital document. */
  allowManualEditWhenEmpty?: boolean;
  hasOriginal?: boolean;
  hasDigital?: boolean;
  onEdit: () => void;
  onUpload: () => void;
  onDelete: () => void;
  onFilesDropped: (files: FileList) => void;
  footer?: ReactNode;
};

/**
 * Fixed-height document preview card for Employee Document Center.
 * Structural chrome stays RTL; preview values ellipsize visually only.
 */
export function DocumentPreviewCard({
  title,
  status,
  fields,
  empty,
  busy = false,
  filename,
  allowManualEditWhenEmpty = false,
  hasOriginal = false,
  hasDigital = false,
  onEdit,
  onUpload,
  onDelete,
  onFilesDropped,
  footer,
}: DocumentPreviewCardProps) {
  const { t } = useTranslation();
  const canEdit =
    !busy && status !== 'loading' && (!empty || allowManualEditWhenEmpty);
  // Delete enabled when original and/or digital form exists.
  const canDelete = !busy && status !== 'loading' && (hasOriginal || hasDigital);
  const deleteLabel = canDelete
    ? t('common.delete')
    : t('employee.documents.deleteDisabledNothing');
  const sections = groupPreviewFields(fields);
  const showSectionTitles = sections.some((section) => Boolean(section.title));

  return (
    <article
      className={`document-preview-card${busy ? ' is-busy' : ''}${status === 'loading' ? ' is-loading' : ''}`}
      aria-busy={busy || status === 'loading'}
      onDragOver={(event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'copy';
      }}
      onDrop={(event) => {
        event.preventDefault();
        if (busy || status === 'loading') return;
        if (event.dataTransfer.files?.length) {
          onFilesDropped(event.dataTransfer.files);
        }
      }}
    >
      <header className="document-preview-card__header ui-chrome-rtl" dir="rtl">
        <h3 className="document-preview-card__title">{title}</h3>
        <DocumentStatusBadge status={status} />
      </header>

      <div className="document-preview-card__body">
        {status === 'loading' ? (
          <div className="document-preview-card__skeleton" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
        ) : empty ? (
          <div className="document-preview-card__empty">
            <span className="document-preview-card__empty-icon" aria-hidden="true">
              ▭
            </span>
            <p>{t('employee.documents.cardEmpty')}</p>
            <ActionIconButton
              label={t('employee.documents.upload')}
              icon={<UploadIcon size={18} />}
              disabled={busy}
              onClick={onUpload}
            />
          </div>
        ) : (
          <button
            type="button"
            className="document-preview-card__form digital-form"
            aria-label={t('employee.documents.openEditPreview', { type: title })}
            disabled={!canEdit}
            onClick={onEdit}
          >
            {filename ? (
              <p className="document-preview-card__filename" title={filename}>
                {filename}
              </p>
            ) : null}
            {sections.map((section) => (
              <section
                key={section.id}
                className="digital-form__section document-preview-card__section"
                data-section-id={section.id}
              >
                {showSectionTitles && section.title ? (
                  <h4 className="digital-form__section-title">{section.title}</h4>
                ) : null}
                <div className="digital-form__grid document-preview-card__grid">
                  {section.fields.map((field) => (
                    <div
                      key={field.key}
                      className="digital-form__field document-preview-card__field"
                    >
                      <span className="digital-form__label">{field.label}</span>
                      <p
                        className="digital-form__readonly document-preview-card__value"
                        title={field.value || undefined}
                      >
                        {field.value || t('common.emDash')}
                      </p>
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </button>
        )}
      </div>

      <footer className="document-preview-card__actions ui-chrome-rtl" dir="rtl">
        <ActionIconButton
          label={t('common.edit')}
          tone="primary"
          icon={<PencilIcon size={17} />}
          disabled={!canEdit}
          onClick={onEdit}
        />
        <ActionIconButton
          label={t('employee.documents.upload')}
          icon={<UploadIcon size={17} />}
          disabled={busy || status === 'loading'}
          onClick={onUpload}
        />
        <ActionIconButton
          label={deleteLabel}
          tone="danger"
          icon={<TrashIcon size={17} />}
          disabled={!canDelete}
          onClick={onDelete}
        />
      </footer>
      {footer}
    </article>
  );
}
