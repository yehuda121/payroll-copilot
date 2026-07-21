import { useTranslation } from 'react-i18next';
import type { DynamicDocumentEntry } from '../../../types/api';
import {
  getDynamicEntryDisplayKey,
  groupEntriesBySection,
  isMeaningfulReviewEntry,
  serializeEntryValue,
} from '../../../lib/guest/extraction-review';
import './landing-chat.css';

type ChatDocumentReviewCardProps = {
  fileName: string;
  documentTypeLabel?: string;
  entries: DynamicDocumentEntry[];
  confirmed: boolean;
  busy?: boolean;
  onChangeEntry: (id: string, patch: Partial<Pick<DynamicDocumentEntry, 'key' | 'value'>>) => void;
  onDeleteEntry: (id: string) => void;
  onAddEntry: () => void;
  onConfirm: () => void;
};

function isReviewVisibleEntry(entry: DynamicDocumentEntry): boolean {
  // Keep in-progress user-added rows editable; document rows need label + value.
  if (entry.source === 'user') return true;
  return isMeaningfulReviewEntry(entry);
}

function EntryRow({
  entry,
  confirmed,
  busy,
  onChangeEntry,
  onDeleteEntry,
}: {
  entry: DynamicDocumentEntry;
  confirmed: boolean;
  busy: boolean;
  onChangeEntry: ChatDocumentReviewCardProps['onChangeEntry'];
  onDeleteEntry: ChatDocumentReviewCardProps['onDeleteEntry'];
}) {
  const { t } = useTranslation();
  const valueText = serializeEntryValue(entry.value);
  const keyDisplay = getDynamicEntryDisplayKey(entry.key, t);
  const keyInputValue = entry.key.trim() ? keyDisplay : '';

  return (
    <div className="digital-form__kv-row">
      {confirmed ? (
        <>
          <div className="digital-form__kv-key">
            <span className="digital-form__kv-label">{t('landingChat.form.keyLabel')}</span>
            <p className="digital-form__readonly">{keyDisplay}</p>
          </div>
          <div className="digital-form__kv-value">
            <span className="digital-form__kv-label">{t('landingChat.form.valueLabel')}</span>
            <p className="digital-form__readonly">{valueText || t('common.emDash')}</p>
          </div>
        </>
      ) : (
        <>
          <label className="digital-form__kv-key">
            <span className="digital-form__kv-label">{t('landingChat.form.keyLabel')}</span>
            <input
              className="digital-form__input"
              value={keyInputValue}
              onChange={(event) => onChangeEntry(entry.id, { key: event.target.value })}
              placeholder={t('payroll.fields.unknown')}
              disabled={busy}
            />
          </label>
          <label className="digital-form__kv-value">
            <span className="digital-form__kv-label">{t('landingChat.form.valueLabel')}</span>
            <input
              className="digital-form__input"
              value={valueText}
              onChange={(event) => onChangeEntry(entry.id, { value: event.target.value })}
              placeholder={t('landingChat.form.valuePlaceholder')}
              disabled={busy}
            />
          </label>
          <button
            type="button"
            className="btn btn--ghost digital-form__clear"
            onClick={() => onDeleteEntry(entry.id)}
            disabled={busy}
            aria-label={t('landingChat.form.deleteField')}
          >
            {t('landingChat.form.deleteField')}
          </button>
        </>
      )}
    </div>
  );
}

export function ChatDocumentReviewCard({
  fileName,
  documentTypeLabel,
  entries,
  confirmed,
  busy = false,
  onChangeEntry,
  onDeleteEntry,
  onAddEntry,
  onConfirm,
}: ChatDocumentReviewCardProps) {
  const { t } = useTranslation();
  const visibleEntries = entries.filter(isReviewVisibleEntry);
  const usable = visibleEntries.some(
    (entry) => entry.value !== null && String(entry.value).trim() !== '',
  );
  const canConfirm = !confirmed && usable && !busy;
  const groups = groupEntriesBySection(visibleEntries);
  const hasNamedSections = groups.some((group) => Boolean(group.section));

  return (
    <div className="digital-form" role="form" aria-label={t('landingChat.documentCardTitle')}>
      <header className="digital-form__header">
        <p className="digital-form__eyebrow">{t('landingChat.form.eyebrow')}</p>
        <h3 className="digital-form__title">{t('landingChat.documentCardTitle')}</h3>
        <dl className="digital-form__meta">
          <div>
            <dt>{t('landingChat.form.documentType')}</dt>
            <dd>{documentTypeLabel || t('slots.payslip')}</dd>
          </div>
          <div>
            <dt>{t('landingChat.uploadedFile')}</dt>
            <dd>{fileName}</dd>
          </div>
        </dl>
        <p className="digital-form__hint">{t('landingChat.confirmBeforeValidate')}</p>
      </header>

      {entries.length === 0 ? (
        <div className="digital-form__empty" role="alert">
          <p>{t('landingChat.extractionEmpty')}</p>
        </div>
      ) : (
        <>
          {groups.map((group) => (
            <section
              key={group.section || '__unsectioned__'}
              className="digital-form__section"
            >
              <h4 className="digital-form__section-title">
                {group.section ||
                  (hasNamedSections
                    ? t('landingChat.form.sections.other')
                    : t('landingChat.form.sections.basics'))}
              </h4>
              <div className="digital-form__kv-list">
                {group.entries.map((entry) => (
                  <EntryRow
                    key={entry.id}
                    entry={entry}
                    confirmed={confirmed}
                    busy={busy}
                    onChangeEntry={onChangeEntry}
                    onDeleteEntry={onDeleteEntry}
                  />
                ))}
              </div>
            </section>
          ))}
          {!confirmed && (
            <button
              type="button"
              className="btn btn--secondary digital-form__add"
              onClick={onAddEntry}
              disabled={busy}
            >
              {t('landingChat.form.addField')}
            </button>
          )}
        </>
      )}

      <footer className="digital-form__footer">
        {confirmed ? (
          <p className="digital-form__confirmed" role="status">
            {t('landingChat.documentConfirmed')}
          </p>
        ) : (
          <button
            type="button"
            className="btn btn--primary"
            disabled={!canConfirm}
            onClick={onConfirm}
          >
            {t('landingChat.confirmDocument')}
          </button>
        )}
      </footer>
    </div>
  );
}
