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
};

type DocumentPreviewCardProps = {
  title: string;
  status: DocumentCardStatus;
  fields: DocumentPreviewField[];
  empty: boolean;
  busy?: boolean;
  filename?: string | null;
  /** When true, Edit stays available even with no original/digital document. */
  allowManualEditWhenEmpty?: boolean;
  /** True when an uploaded original file exists. */
  hasOriginal?: boolean;
  onEdit: () => void;
  onUpload: () => void;
  onDelete: () => void;
  onFilesDropped: (files: FileList) => void;
  footer?: ReactNode;
};

/**
 * Fixed-height document preview card for Employee Document Center.
 * Only the preview surface opens Edit — chrome actions stay separate.
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
  onEdit,
  onUpload,
  onDelete,
  onFilesDropped,
  footer,
}: DocumentPreviewCardProps) {
  const { t } = useTranslation();
  const canEdit =
    !busy && status !== 'loading' && (!empty || allowManualEditWhenEmpty);
  // Always visible. Disabled when no uploaded original exists (per product rule).
  const canDelete = !busy && status !== 'loading' && hasOriginal;
  const deleteLabel = canDelete
    ? t('common.delete')
    : t('employee.documents.deleteDisabledNoOriginal');

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
      <header className="document-preview-card__header" dir="rtl">
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
              <p className="document-preview-card__filename">{filename}</p>
            ) : null}
            <div className="digital-form__grid document-preview-card__grid">
              {fields.map((field) => (
                <div key={field.key} className="digital-form__field document-preview-card__field">
                  <span className="digital-form__label">{field.label}</span>
                  <p className="digital-form__readonly">{field.value || t('common.emDash')}</p>
                </div>
              ))}
            </div>
          </button>
        )}
      </div>

      <footer className="document-preview-card__actions" dir="rtl">
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
