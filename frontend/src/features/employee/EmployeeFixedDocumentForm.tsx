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
  documentType: 'national_id' | 'contract';
  values: Record<string, string>;
  busy?: boolean;
  reviewNotice?: string | null;
  fieldErrors?: Partial<Record<string, string>>;
  onChangeField: (key: string, value: string) => void;
};

const CONTRACT_DATE_KEYS = new Set([
  'employment_commencement_date',
  'effective_from',
  'effective_to',
]);

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
    if (documentType !== 'national_id') return null;
    const raw = values.national_id ?? '';
    if (!raw.trim()) return null;
    const result = validateNationalId(raw);
    if (result.ok) return null;
    if (result.code === 'digits_only') return t('employee.documents.validation.nationalIdDigits');
    if (result.code === 'length') return t('employee.documents.validation.nationalIdLength');
    if (result.code === 'checksum') return t('employee.documents.validation.nationalIdChecksum');
    return t('employee.documents.validation.nationalIdInvalid');
  }, [documentType, t, values.national_id]);

  const liveNameError = useMemo(() => {
    if (documentType !== 'national_id') return null;
    const raw = values.full_name ?? '';
    if (!raw.trim()) return null;
    const result = validatePersonName(raw);
    if (result.ok) return null;
    return t('employee.documents.validation.nameInvalid');
  }, [documentType, t, values.full_name]);

  if (documentType === 'contract') {
    return (
      <div className="employee-digital-form" data-busy={busy || undefined}>
        {reviewNotice ? <p className="landing-muted">{reviewNotice}</p> : null}
        <p className="landing-muted">
          {t('employee.documents.contract.termsHint', {
            defaultValue:
              'Confirm original employment commencement and contractual pay terms. Do not use system registration dates.',
          })}
        </p>
        {keys.map((key) => {
          const label = t(`employee.documents.contract.fields.${key}`, {
            defaultValue: key.replaceAll('_', ' '),
          });
          const value = values[key] ?? '';
          if (CONTRACT_DATE_KEYS.has(key)) {
            return (
              <BirthDateField
                key={key}
                id={`contract-${key}`}
                label={label}
                value={value}
                disabled={busy}
                error={fieldErrors[key]}
                onChange={(next) => onChangeField(key, next)}
              />
            );
          }
          if (key === 'salary_basis') {
            return (
              <label key={key} className="landing-field">
                <span>{label}</span>
                <select
                  value={value}
                  disabled={busy}
                  onChange={(event) => onChangeField(key, event.target.value)}
                >
                  <option value="">{t('common.emDash', { defaultValue: '—' })}</option>
                  <option value="monthly">
                    {t('employee.documents.contract.salaryBasis.monthly', { defaultValue: 'Monthly' })}
                  </option>
                  <option value="hourly">
                    {t('employee.documents.contract.salaryBasis.hourly', { defaultValue: 'Hourly' })}
                  </option>
                  <option value="daily">
                    {t('employee.documents.contract.salaryBasis.daily', { defaultValue: 'Daily' })}
                  </option>
                </select>
              </label>
            );
          }
          return (
            <label key={key} className="landing-field">
              <span>{label}</span>
              <input
                value={value}
                disabled={busy}
                onChange={(event) => onChangeField(key, event.target.value)}
                inputMode="decimal"
              />
              {fieldErrors[key] ? <span className="field-error">{fieldErrors[key]}</span> : null}
            </label>
          );
        })}
      </div>
    );
  }

  return (
    <div className="employee-digital-form" data-busy={busy || undefined}>
      {reviewNotice ? <p className="landing-muted">{reviewNotice}</p> : null}
      {keys.map((key) => {
        if (key === 'birth_date') {
          return (
            <BirthDateField
              key={key}
              id="id-birth-date"
              label={t('employee.documents.fields.birth_date', { defaultValue: 'Birth date' })}
              value={values.birth_date ?? ''}
              disabled={busy}
              error={fieldErrors.birth_date}
              onChange={(next) => onChangeField('birth_date', next)}
            />
          );
        }
        if (key === 'national_id') {
          return (
            <label key={key} className="landing-field">
              <span>{t('employee.documents.fields.national_id', { defaultValue: 'National ID' })}</span>
              <input
                value={values.national_id ?? ''}
                disabled={busy}
                maxLength={FIELD_MAX_LENGTH}
                onBlur={() => setTouchedId(true)}
                onChange={(event) => onChangeField('national_id', event.target.value)}
              />
              {(touchedId ? liveIdError : null) || fieldErrors.national_id ? (
                <span className="field-error">{fieldErrors.national_id || liveIdError}</span>
              ) : null}
            </label>
          );
        }
        return (
          <label key={key} className="landing-field">
            <span>{t('employee.documents.fields.full_name', { defaultValue: 'Full name' })}</span>
            <input
              value={values.full_name ?? ''}
              disabled={busy}
              maxLength={FIELD_MAX_LENGTH}
              onBlur={() => setTouchedName(true)}
              onChange={(event) => onChangeField('full_name', event.target.value)}
            />
            {(touchedName ? liveNameError : null) || fieldErrors.full_name ? (
              <span className="field-error">{fieldErrors.full_name || liveNameError}</span>
            ) : null}
          </label>
        );
      })}
      {/* Keep parseBirthDate referenced for tree-shaking-safe reuse in parents */}
      <span hidden>{parseBirthDate(values.birth_date ?? '') ? '' : ''}</span>
    </div>
  );
}
