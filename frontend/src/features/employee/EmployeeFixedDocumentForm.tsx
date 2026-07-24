import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BirthDateField } from './BirthDateField';
import { fixedFieldKeysFor } from '../../lib/employee/document-fixed-forms';
import { parseBirthDate } from '../../lib/employee/birth-date';
import { FIELD_MAX_LENGTH, validatePersonName } from '../../lib/employee/field-text';
import { validateNationalId } from '../../lib/employee/israeli-id';
import '../employee/employee-payslip.css';
import '../guest/landing/landing-chat.css';

type EmployeeFixedDocumentFormProps = {
  documentType: 'national_id';
  values: Record<string, string>;
  busy?: boolean;
  reviewNotice?: string | null;
  fieldErrors?: Partial<Record<'full_name' | 'national_id' | 'birth_date', string>>;
  onChangeField: (key: string, value: string) => void;
};

export function EmployeeFixedDocumentForm({
  documentType,
  values,
  busy = false,
  reviewNotice,
  fieldErrors = {},
  onChangeField,
}: EmployeeFixedDocumentFormProps) {
  const { t } = useTranslation();
  const keys = fixedFieldKeysFor(documentType) ?? [];
  const [touchedId, setTouchedId] = useState(false);
  const [touchedName, setTouchedName] = useState(false);

  const liveIdError = useMemo(() => {
    const raw = values.national_id ?? '';
    if (!raw.trim()) return null;
    const result = validateNationalId(raw);
    if (result.ok) return null;
    if (result.code === 'digits_only') return t('employee.documents.validation.nationalIdDigits');
    if (result.code === 'length') return t('employee.documents.validation.nationalIdLength');
    if (result.code === 'checksum') return t('employee.documents.validation.nationalIdChecksum');
    return null;
  }, [t, values.national_id]);

  const liveNameError = useMemo(() => {
    const raw = values.full_name ?? '';
    if (!raw.trim()) return null;
    const result = validatePersonName(raw);
    if (result.ok) return null;
    if (result.code === 'digits') return t('employee.documents.validation.nameNoDigits');
    if (result.code === 'max_length') return t('employee.documents.validation.nameMaxLength');
    if (result.code === 'invalid_chars') return t('employee.documents.validation.nameInvalid');
    return null;
  }, [t, values.full_name]);

  const liveBirthError = useMemo(() => {
    const raw = values.birth_date ?? '';
    if (!raw.trim()) return null;
    const parsed = parseBirthDate(raw);
    if (parsed.ok) return null;
    return t('employee.documents.validation.dateInvalid');
  }, [t, values.birth_date]);

  return (
    <div
      className="digital-form employee-digital-form"
      role="form"
      aria-label={t('employee.documents.tabDigital')}
    >
      <header className="digital-form__header">
        <h3 className="digital-form__title">{t('employee.documents.tabDigital')}</h3>
        {reviewNotice && <p className="digital-form__hint">{reviewNotice}</p>}
      </header>

      <section className="digital-form__section employee-digital-form__section">
        <div className="digital-form__grid employee-digital-form__grid">
          {keys.map((key) => {
            const inputId = `fixed-doc-field-${documentType}-${key}`;
            if (key === 'birth_date') {
              return (
                <BirthDateField
                  key={key}
                  id={inputId}
                  label={t(`employee.documents.fixedFields.${key}`)}
                  value={values[key] ?? ''}
                  disabled={busy}
                  className="employee-digital-form__field--span-2"
                  error={fieldErrors.birth_date ?? liveBirthError}
                  onChange={(next) => onChangeField(key, next)}
                />
              );
            }

            const error =
              key === 'national_id'
                ? (fieldErrors.national_id ?? (touchedId ? liveIdError : null))
                : key === 'full_name'
                  ? (fieldErrors.full_name ?? (touchedName ? liveNameError : null))
                  : null;

            const maxLength =
              key === 'national_id'
                ? FIELD_MAX_LENGTH.nationalId
                : key === 'full_name'
                  ? FIELD_MAX_LENGTH.personName
                  : undefined;

            return (
              <label
                key={key}
                className="digital-form__field employee-digital-form__field employee-digital-form__field--span-2"
                htmlFor={inputId}
              >
                <span className="digital-form__label">
                  {t(`employee.documents.fixedFields.${key}`)}
                </span>
                <input
                  id={inputId}
                  className={`digital-form__input${error ? ' is-invalid' : ''}`}
                  type="text"
                  inputMode={key === 'national_id' ? 'numeric' : undefined}
                  maxLength={maxLength}
                  value={values[key] ?? ''}
                  disabled={busy}
                  onChange={(event) => onChangeField(key, event.target.value)}
                  onBlur={() => {
                    if (key === 'national_id') setTouchedId(true);
                    if (key === 'full_name') setTouchedName(true);
                  }}
                  autoComplete="off"
                />
                {error ? (
                  <span className="digital-form__error" role="alert">
                    {error}
                  </span>
                ) : null}
              </label>
            );
          })}
        </div>
      </section>
    </div>
  );
}
