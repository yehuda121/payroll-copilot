import { useTranslation } from 'react-i18next';
import type { ExtractionField } from '../../lib/guest/extraction-review';
import type { FieldDraft } from '../../hooks/useGuestValidationFlow';
import './ui.css';

type ExtractionReviewTableProps = {
  fields: ExtractionField[];
  drafts: Record<string, FieldDraft>;
  editable?: boolean;
  reviewNotice?: string | null;
  onChangeField?: (key: string, value: string) => void;
  onClearField?: (key: string) => void;
};

export function ExtractionReviewTable({
  fields,
  drafts,
  editable = false,
  reviewNotice,
  onChangeField,
  onClearField,
}: ExtractionReviewTableProps) {
  const { t } = useTranslation();

  return (
    <section className="extraction-review" aria-label={t('validate.reviewTitle')}>
      {reviewNotice && (
        <div className="extraction-review__banner" role="status">
          {reviewNotice}
        </div>
      )}
      <p className="extraction-review__lead">{t('validate.reviewLead')}</p>
      <div className="extraction-review__grid">
        {fields.map((field) => {
          const draft = drafts[field.key];
          const inputValue = draft?.value ?? '';
          const showMissing = !editable && (field.status === 'MISSING' || !field.displayValue);
          return (
            <div
              key={field.key}
              className={`extraction-field extraction-field--${field.status.toLowerCase()}${
                draft?.dirty ? ' extraction-field--edited' : ''
              }`}
            >
              <label className="extraction-field__label" htmlFor={`extract-${field.key}`}>
                {field.label}
                {draft?.dirty && (
                  <span className="extraction-field__edited-tag">{t('validate.fieldEdited')}</span>
                )}
              </label>
              {editable ? (
                <div className="extraction-field__editor">
                  <input
                    id={`extract-${field.key}`}
                    className="extraction-field__input"
                    value={inputValue}
                    placeholder={t('validate.fieldMissing')}
                    onChange={(event) => onChangeField?.(field.key, event.target.value)}
                    aria-label={field.label}
                  />
                  <button
                    type="button"
                    className="btn btn--ghost extraction-field__clear"
                    onClick={() => onClearField?.(field.key)}
                  >
                    {t('validate.fieldClear')}
                  </button>
                </div>
              ) : (
                <span className="extraction-field__value">
                  {showMissing ? t('validate.fieldMissing') : field.displayValue}
                </span>
              )}
              {field.confidenceLabel && (
                <span className="extraction-field__confidence">
                  {t('validate.confidenceLabel')}: {field.confidenceLabel}
                </span>
              )}
              {field.sourceText && (
                <span className="extraction-field__source">
                  {t('validate.sourceTextLabel')}: {field.sourceText}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
