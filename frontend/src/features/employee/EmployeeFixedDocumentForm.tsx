import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BirthDateField } from './BirthDateField';
import { fixedFieldKeysFor } from '../../lib/employee/document-fixed-forms';
import { parseBirthDate } from '../../lib/employee/birth-date';
import { FIELD_MAX_LENGTH, validatePersonName } from '../../lib/employee/field-text';
import { validateNationalId } from '../../lib/employee/israeli-id';
import '../../components/document/document-preview-card.css';
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
      <div
        className="digital-form employee-digital-form document-fixed-edit-form"
        data-busy={busy || undefined}
        role="form"
        aria-label={t('employee.documents.tabDigital')}
      >
        {reviewNotice ? (
          <p className="digital-form__hint document-fixed-edit-form__notice">{reviewNotice}</p>
        ) : null}
        <p className="digital-form__hint document-fixed-edit-form__notice">
          {t('employee.documents.contract.termsHint')}
        </p>
        <div className="digital-form__grid document-fixed-edit-form__grid">
          {keys.map((key) => {
            const label = t(`employee.documents.contract.fields.${key}`);
            const value = values[key] ?? '';
            const fieldId = `contract-${key}`;
            if (CONTRACT_DATE_KEYS.has(key)) {
              return (
                <BirthDateField
                  key={key}
                  id={fieldId}
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
                <label
                  key={key}
                  className="digital-form__field employee-digital-form__field"
                  htmlFor={fieldId}
                >
                  <span className="digital-form__label">{label}</span>
                  <select
                    id={fieldId}
                    className="digital-form__input"
                    value={value}
                    disabled={busy}
                    onChange={(event) => onChangeField(key, event.target.value)}
                  >
                    <option value="">{t('common.emDash')}</option>
                    <option value="monthly">{t('employee.documents.contract.salaryBasis.monthly')}</option>
                    <option value="hourly">{t('employee.documents.contract.salaryBasis.hourly')}</option>
                    <option value="daily">{t('employee.documents.contract.salaryBasis.daily')}</option>
                  </select>
                </label>
              );
            }
            return (
              <label
                key={key}
                className="digital-form__field employee-digital-form__field"
                htmlFor={fieldId}
              >
                <span className="digital-form__label">{label}</span>
                <input
                  id={fieldId}
                  className={`digital-form__input${fieldErrors[key] ? ' is-invalid' : ''}`}
                  value={value}
                  disabled={busy}
                  onChange={(event) => onChangeField(key, event.target.value)}
                  inputMode="decimal"
                />
                {fieldErrors[key] ? (
                  <span className="digital-form__error" role="alert">
                    {fieldErrors[key]}
                  </span>
                ) : null}
              </label>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div
      className="digital-form employee-digital-form document-fixed-edit-form"
      data-busy={busy || undefined}
      role="form"
      aria-label={t('employee.documents.tabDigital')}
    >
      {reviewNotice ? (
        <p className="digital-form__hint document-fixed-edit-form__notice">{reviewNotice}</p>
      ) : null}
      <div className="digital-form__grid document-fixed-edit-form__grid">
        {keys.map((key) => {
          if (key === 'birth_date') {
            return (
              <BirthDateField
                key={key}
                id="id-birth-date"
                label={t('employee.documents.fixedFields.birth_date')}
                value={values.birth_date ?? ''}
                disabled={busy}
                error={fieldErrors.birth_date}
                onChange={(next) => onChangeField('birth_date', next)}
              />
            );
          }
          if (key === 'national_id') {
            const idInvalid = Boolean((touchedId ? liveIdError : null) || fieldErrors.national_id);
            return (
              <label
                key={key}
                className="digital-form__field employee-digital-form__field"
                htmlFor="id-national-id"
              >
                <span className="digital-form__label">
                  {t('employee.documents.fixedFields.national_id')}
                </span>
                <input
                  id="id-national-id"
                  className={`digital-form__input${idInvalid ? ' is-invalid' : ''}`}
                  value={values.national_id ?? ''}
                  disabled={busy}
                  maxLength={FIELD_MAX_LENGTH.nationalId}
                  autoComplete="off"
                  inputMode="numeric"
                  onBlur={() => setTouchedId(true)}
                  onChange={(event) => onChangeField('national_id', event.target.value)}
                />
                {idInvalid ? (
                  <span className="digital-form__error" role="alert">
                    {fieldErrors.national_id || liveIdError}
                  </span>
                ) : null}
              </label>
            );
          }
          const nameInvalid = Boolean((touchedName ? liveNameError : null) || fieldErrors.full_name);
          return (
            <label
              key={key}
              className="digital-form__field employee-digital-form__field"
              htmlFor="id-full-name"
            >
              <span className="digital-form__label">
                {t('employee.documents.fixedFields.full_name')}
              </span>
              <input
                id="id-full-name"
                className={`digital-form__input${nameInvalid ? ' is-invalid' : ''}`}
                value={values.full_name ?? ''}
                disabled={busy}
                maxLength={FIELD_MAX_LENGTH.personName}
                autoComplete="name"
                onBlur={() => setTouchedName(true)}
                onChange={(event) => onChangeField('full_name', event.target.value)}
              />
              {nameInvalid ? (
                <span className="digital-form__error" role="alert">
                  {fieldErrors.full_name || liveNameError}
                </span>
              ) : null}
            </label>
          );
        })}
      </div>
      {/* Keep parseBirthDate referenced for tree-shaking-safe reuse in parents */}
      <span hidden>{parseBirthDate(values.birth_date ?? '') ? '' : ''}</span>
    </div>
  );
}
