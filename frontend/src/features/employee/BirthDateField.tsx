import { useTranslation } from 'react-i18next';
import {
  birthDateToDateInputValue,
  normalizeBirthDateInput,
  parseBirthDate,
} from '../../lib/employee/birth-date';
import { FIELD_MAX_LENGTH } from '../../lib/employee/field-text';

type BirthDateFieldProps = {
  id: string;
  label: string;
  value: string;
  disabled?: boolean;
  error?: string | null;
  className?: string;
  onChange: (normalizedValue: string) => void;
};

/**
 * Dual birth-date entry: typed text + native calendar picker.
 * Values normalize to YYYY-MM-DD via the shared parser.
 */
export function BirthDateField({
  id,
  label,
  value,
  disabled = false,
  error = null,
  className = '',
  onChange,
}: BirthDateFieldProps) {
  const { t } = useTranslation();
  const pickerId = `${id}-picker`;
  const pickerValue = birthDateToDateInputValue(value);
  const showRawHint = Boolean(value.trim()) && !parseBirthDate(value).ok;

  return (
    <div className={`digital-form__field employee-digital-form__field ${className}`.trim()}>
      <span className="digital-form__label" id={`${id}-label`}>
        {label}
      </span>
      <div className="birth-date-field__controls">
        <input
          id={id}
          className={`digital-form__input birth-date-field__text${error ? ' is-invalid' : ''}`}
          type="text"
          inputMode="numeric"
          autoComplete="bday"
          maxLength={FIELD_MAX_LENGTH.birthDate}
          value={value}
          disabled={disabled}
          aria-labelledby={`${id}-label`}
          placeholder={t('employee.documents.validation.datePlaceholder')}
          onChange={(event) => onChange(event.target.value)}
          onBlur={() => {
            if (!value.trim()) return;
            const parsed = parseBirthDate(value);
            if (parsed.ok) onChange(parsed.iso);
          }}
        />
        <input
          id={pickerId}
          className="birth-date-field__picker"
          type="date"
          value={pickerValue}
          disabled={disabled}
          aria-label={t('employee.documents.validation.datePickerAria', { label })}
          onChange={(event) => {
            const next = event.target.value;
            onChange(next ? normalizeBirthDateInput(next) : '');
          }}
        />
      </div>
      {showRawHint ? (
        <span className="digital-form__hint" role="status">
          {t('employee.documents.validation.dateUnrecognized')}
        </span>
      ) : null}
      {error ? (
        <span className="digital-form__error" role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
}
