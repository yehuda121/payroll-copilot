import { useTranslation } from 'react-i18next';
import {
  birthDateToDateInputValue,
  normalizeBirthDateInput,
  parseBirthDate,
} from '../../lib/employee/birth-date';

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
 * Native date input with normalize-on-change for common pasted formats.
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
  const inputValue = birthDateToDateInputValue(value);
  const showRawHint = Boolean(value.trim()) && !parseBirthDate(value).ok;

  return (
    <label
      className={`digital-form__field employee-digital-form__field ${className}`.trim()}
      htmlFor={id}
    >
      <span className="digital-form__label">{label}</span>
      <input
        id={id}
        className={`digital-form__input${error ? ' is-invalid' : ''}`}
        type="date"
        value={inputValue}
        disabled={disabled}
        onChange={(event) => {
          const next = event.target.value;
          onChange(next ? normalizeBirthDateInput(next) : '');
        }}
        onBlur={() => {
          if (!value.trim()) return;
          const parsed = parseBirthDate(value);
          if (parsed.ok && parsed.iso !== value) onChange(parsed.iso);
        }}
        autoComplete="bday"
      />
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
    </label>
  );
}
