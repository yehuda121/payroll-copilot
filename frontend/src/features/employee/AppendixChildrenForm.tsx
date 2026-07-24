import { useTranslation } from 'react-i18next';
import { BirthDateField } from './BirthDateField';
import type { AppendixChild } from '../../lib/employee/document-fixed-forms';
import type { AppendixChildRowError } from '../../lib/employee/appendix-children-validation';
import { FIELD_MAX_LENGTH } from '../../lib/employee/field-text';
import '../../components/document/document-preview-card.css';
import '../employee/employee-payslip.css';
import '../guest/landing/landing-chat.css';

type AppendixChildrenFormProps = {
  childrenList: AppendixChild[];
  busy?: boolean;
  reviewNotice?: string | null;
  rowErrors?: AppendixChildRowError[];
  onChangeChild: (index: number, patch: Partial<AppendixChild>) => void;
  onAddChild: () => void;
  onRemoveChild: (index: number) => void;
};

function rowErrorMessage(
  t: (key: string) => string,
  code: AppendixChildRowError['code'] | undefined,
): string | null {
  if (!code) return null;
  if (code === 'incomplete') return t('employee.documents.validation.childIncomplete');
  if (code === 'invalid_birth_date') return t('employee.documents.validation.dateInvalid');
  if (code === 'name_digits') return t('employee.documents.validation.nameNoDigits');
  if (code === 'name_max_length') return t('employee.documents.validation.nameMaxLength');
  if (code === 'invalid_name') return t('employee.documents.validation.nameInvalid');
  return null;
}

/**
 * Manual / extracted Identity Appendix editor — children list only.
 */
export function AppendixChildrenForm({
  childrenList,
  busy = false,
  reviewNotice,
  rowErrors = [],
  onChangeChild,
  onAddChild,
  onRemoveChild,
}: AppendixChildrenFormProps) {
  const { t } = useTranslation();
  const errorByIndex = new Map(rowErrors.map((row) => [row.index, row]));

  return (
    <div
      className="digital-form employee-digital-form appendix-children-form"
      role="form"
      aria-label={t('employee.documents.tabDigital')}
    >
      <header className="digital-form__header">
        <h3 className="digital-form__title">{t('employee.documents.tabDigital')}</h3>
        {reviewNotice ? <p className="digital-form__hint">{reviewNotice}</p> : null}
      </header>

      <section className="digital-form__section employee-digital-form__section">
        {childrenList.length === 0 ? (
          <p className="digital-form__hint appendix-children-form__empty">
            {t('employee.documents.appendix.emptyChildren')}
          </p>
        ) : (
          <ul className="appendix-children-form__list">
            {childrenList.map((child, index) => {
              const nameId = `appendix-child-name-${index}`;
              const birthId = `appendix-child-birth-${index}`;
              const rowError = errorByIndex.get(index);
              const message = rowErrorMessage(t, rowError?.code);
              const nameInvalid =
                rowError?.code === 'incomplete' ||
                rowError?.code === 'invalid_name' ||
                rowError?.code === 'name_digits' ||
                rowError?.code === 'name_max_length';
              const birthInvalid =
                rowError?.code === 'incomplete' || rowError?.code === 'invalid_birth_date';
              return (
                <li key={`child-${index}`} className="appendix-children-form__item">
                  <div className="appendix-children-form__item-header">
                    <span className="digital-form__label">
                      {t('employee.documents.appendix.childLabel', { index: index + 1 })}
                    </span>
                    <button
                      type="button"
                      className="btn btn--ghost"
                      disabled={busy}
                      onClick={() => onRemoveChild(index)}
                    >
                      {t('employee.documents.appendix.removeChild')}
                    </button>
                  </div>
                  <div className="digital-form__grid employee-digital-form__grid">
                    <label className="digital-form__field employee-digital-form__field" htmlFor={nameId}>
                      <span className="digital-form__label">
                        {t('employee.documents.fixedFields.child_name')}
                      </span>
                      <input
                        id={nameId}
                        className={`digital-form__input${nameInvalid ? ' is-invalid' : ''}`}
                        type="text"
                        maxLength={FIELD_MAX_LENGTH.personName}
                        value={child.name}
                        disabled={busy}
                        onChange={(event) => onChangeChild(index, { name: event.target.value })}
                        autoComplete="off"
                      />
                    </label>
                    <BirthDateField
                      id={birthId}
                      label={t('employee.documents.fixedFields.child_birth_date')}
                      value={child.birth_date}
                      disabled={busy}
                      error={
                        birthInvalid && rowError?.code === 'invalid_birth_date'
                          ? t('employee.documents.validation.dateInvalid')
                          : null
                      }
                      onChange={(next) => onChangeChild(index, { birth_date: next })}
                    />
                  </div>
                  {message ? (
                    <p className="digital-form__error" role="alert">
                      {message}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}

        <div className="appendix-children-form__actions">
          <button
            type="button"
            className="btn btn--secondary"
            disabled={busy}
            onClick={onAddChild}
          >
            {t('employee.documents.appendix.addChild')}
          </button>
        </div>
      </section>
    </div>
  );
}
