import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { FIELD_MAX_LENGTH, normalizeHumanText, validatePersonName } from '../../lib/employee/field-text';
import { validateNationalId } from '../../lib/employee/israeli-id';
import {
  EMAIL_MAX_LENGTH,
  FREE_TEXT_MAX_LENGTH,
  clampFreeTextInput,
  sanitizeEmailInput,
  validateEmailFormat,
} from '../../lib/validation';
import type { EmployeeWritePayload, EmploymentType, SalaryType } from '../../types/employee';

export type EmployeeFormValues = {
  employeeNumber: string;
  firstName: string;
  lastName: string;
  email: string;
  nationalId: string;
  employmentType: EmploymentType;
  salaryType: SalaryType;
  baseSalaryOrRate: string;
  contractStartDate: string;
};

type EmployeeFormProps = {
  mode: 'create' | 'edit';
  initial?: Partial<EmployeeFormValues>;
  /** Current on-file national ID mask (edit mode display only). */
  nationalIdMasked?: string | null;
  submitting?: boolean;
  error?: string | null;
  success?: string | null;
  onSubmit: (values: EmployeeFormValues, payload: EmployeeWritePayload) => void | Promise<void>;
  onDirtyChange?: (dirty: boolean) => void;
  footer: ReactNode;
};

const DEFAULTS: EmployeeFormValues = {
  employeeNumber: '',
  firstName: '',
  lastName: '',
  email: '',
  nationalId: '',
  employmentType: 'full_time',
  salaryType: 'monthly',
  baseSalaryOrRate: '',
  contractStartDate: new Date().toISOString().slice(0, 10),
};

function personNameErrorKey(code: string): string {
  if (code === 'digits') return 'common.validation.nameNoDigits';
  if (code === 'max_length') return 'common.validation.nameMaxLength';
  return 'common.validation.nameInvalid';
}

export function toWritePayload(
  values: EmployeeFormValues,
  mode: 'create' | 'edit',
): EmployeeWritePayload & { employee_number?: string } {
  const amount = values.baseSalaryOrRate.trim()
    ? Number(values.baseSalaryOrRate)
    : null;
  const email = sanitizeEmailInput(values.email);
  const firstName = normalizeHumanText(values.firstName);
  const lastName = normalizeHumanText(values.lastName);
  const nationalIdRaw = values.nationalId.trim();
  const payload: EmployeeWritePayload & { employee_number?: string } = {
    first_name: firstName,
    last_name: lastName,
    employment_type: values.employmentType,
    salary_type: values.salaryType,
    email: email || undefined,
    national_id: nationalIdRaw || undefined,
    contract_start_date: values.contractStartDate || undefined,
    hourly_rate: values.salaryType === 'hourly' ? amount : null,
    monthly_salary: values.salaryType === 'monthly' ? amount : null,
  };
  if (mode === 'create') {
    payload.employee_number = clampFreeTextInput(
      values.employeeNumber.trim(),
      FREE_TEXT_MAX_LENGTH.identifier,
    );
  }
  return payload;
}

export function EmployeeForm({
  mode,
  initial,
  nationalIdMasked,
  submitting,
  error,
  success,
  onSubmit,
  onDirtyChange,
  footer,
}: EmployeeFormProps) {
  const { t } = useTranslation();
  const baselineRef = useRef<EmployeeFormValues>({ ...DEFAULTS, ...initial });
  const [values, setValues] = useState<EmployeeFormValues>({ ...DEFAULTS, ...initial });
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    const next = { ...DEFAULTS, ...initial };
    baselineRef.current = next;
    setValues(next);
    setLocalError(null);
    onDirtyChange?.(false);
  }, [initial, onDirtyChange]);

  useEffect(() => {
    const dirty = JSON.stringify(values) !== JSON.stringify(baselineRef.current);
    onDirtyChange?.(dirty);
  }, [values, onDirtyChange]);

  const update = <K extends keyof EmployeeFormValues>(key: K, value: EmployeeFormValues[K]) => {
    setValues((prev) => ({ ...prev, [key]: value }));
    setLocalError(null);
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const first = validatePersonName(values.firstName);
    if (!first.ok) {
      setLocalError(t(personNameErrorKey(first.code)));
      return;
    }
    const last = validatePersonName(values.lastName);
    if (!last.ok) {
      setLocalError(t(personNameErrorKey(last.code)));
      return;
    }
    const emailResult = validateEmailFormat(values.email, { allowEmpty: true });
    if (!emailResult.ok) {
      setLocalError(t('common.validation.invalidEmail'));
      return;
    }
    const nationalIdRaw = values.nationalId.trim();
    if (nationalIdRaw) {
      const nid = validateNationalId(nationalIdRaw);
      if (!nid.ok) {
        const key =
          nid.code === 'digits_only'
            ? 'common.validation.nationalIdDigits'
            : nid.code === 'length'
              ? 'common.validation.nationalIdLength'
              : 'common.validation.nationalIdChecksum';
        setLocalError(t(key));
        return;
      }
    }
    setLocalError(null);
    void onSubmit(values, toWritePayload(values, mode));
  };

  return (
    <form className="form-grid" onSubmit={handleSubmit}>
      <div className="form-field">
        <label htmlFor="employeeNumber">{t('accountant.employees.fieldEmployeeNumber')}</label>
        <input
          id="employeeNumber"
          required={mode === 'create'}
          readOnly={mode === 'edit'}
          value={values.employeeNumber}
          maxLength={FREE_TEXT_MAX_LENGTH.identifier}
          autoComplete="off"
          onChange={(e) =>
            update(
              'employeeNumber',
              clampFreeTextInput(e.target.value, FREE_TEXT_MAX_LENGTH.identifier),
            )
          }
        />
      </div>
      <div className="form-field">
        <label htmlFor="firstName">{t('accountant.employees.fieldFirstName')}</label>
        <input
          id="firstName"
          required
          value={values.firstName}
          maxLength={FIELD_MAX_LENGTH.personName}
          autoComplete="given-name"
          onChange={(e) => update('firstName', e.target.value)}
        />
      </div>
      <div className="form-field">
        <label htmlFor="lastName">{t('accountant.employees.fieldLastName')}</label>
        <input
          id="lastName"
          required
          value={values.lastName}
          maxLength={FIELD_MAX_LENGTH.personName}
          autoComplete="family-name"
          onChange={(e) => update('lastName', e.target.value)}
        />
      </div>
      <div className="form-field">
        <label htmlFor="email">{t('accountant.employees.fieldEmail')}</label>
        <input
          id="email"
          type="email"
          value={values.email}
          maxLength={EMAIL_MAX_LENGTH}
          onChange={(e) => update('email', e.target.value)}
          autoComplete="off"
        />
        {mode === 'edit' && (
          <span className="form-hint">{t('accountant.employees.fieldEmailEditHint')}</span>
        )}
      </div>
      <div className="form-field">
        <label htmlFor="nationalId">{t('accountant.employees.fieldNationalId')}</label>
        {mode === 'edit' && (
          <p className="form-hint" data-testid="national-id-current">
            {t('accountant.employees.fieldNationalIdCurrent', {
              value: nationalIdMasked || t('common.emDash'),
            })}
          </p>
        )}
        <input
          id="nationalId"
          value={values.nationalId}
          onChange={(e) =>
            update('nationalId', e.target.value.replace(/\D/g, '').slice(0, FIELD_MAX_LENGTH.nationalId))
          }
          inputMode="numeric"
          maxLength={FIELD_MAX_LENGTH.nationalId}
          autoComplete="off"
          placeholder={
            mode === 'edit' ? t('accountant.employees.fieldNationalIdPlaceholder') : undefined
          }
        />
        <span className="form-hint">{t('accountant.employees.fieldNationalIdHint')}</span>
      </div>
      <div className="form-field">
        <label htmlFor="employmentType">{t('accountant.employees.fieldEmploymentType')}</label>
        <select
          id="employmentType"
          value={values.employmentType}
          onChange={(e) => update('employmentType', e.target.value as EmploymentType)}
        >
          <option value="full_time">{t('accountant.employees.employmentTypes.fullTime')}</option>
          <option value="part_time">{t('accountant.employees.employmentTypes.partTime')}</option>
          <option value="contractor">{t('accountant.employees.employmentTypes.contractor')}</option>
          <option value="intern">{t('accountant.employees.employmentTypes.intern')}</option>
          <option value="pre_intern">{t('accountant.employees.employmentTypes.preIntern')}</option>
        </select>
      </div>
      <div className="form-field">
        <label htmlFor="salaryType">{t('accountant.employees.fieldSalaryType')}</label>
        <select
          id="salaryType"
          value={values.salaryType}
          onChange={(e) => update('salaryType', e.target.value as SalaryType)}
        >
          <option value="monthly">{t('accountant.employees.salaryTypes.monthly')}</option>
          <option value="hourly">{t('accountant.employees.salaryTypes.hourly')}</option>
        </select>
      </div>
      <div className="form-field">
        <label htmlFor="baseSalary">
          {values.salaryType === 'monthly'
            ? t('accountant.employees.fieldMonthlySalary')
            : t('accountant.employees.fieldHourlyRate')}
        </label>
        <input
          id="baseSalary"
          type="number"
          min="0"
          step="0.01"
          inputMode="decimal"
          value={values.baseSalaryOrRate}
          onChange={(e) => update('baseSalaryOrRate', e.target.value)}
        />
      </div>
      <div className="form-field">
        <label htmlFor="contractStart">{t('accountant.employees.fieldContractStart')}</label>
        <input
          id="contractStart"
          type="date"
          value={values.contractStartDate}
          onChange={(e) => update('contractStartDate', e.target.value)}
        />
      </div>
      {(localError || error) && (
        <p className="chat-panel__error" style={{ gridColumn: '1 / -1' }} role="alert">
          {localError || error}
        </p>
      )}
      {success && !localError && !error && (
        <p className="form-hint" style={{ gridColumn: '1 / -1' }} role="status">
          {success}
        </p>
      )}
      <div className="form-actions" style={{ gridColumn: '1 / -1' }}>
        {footer}
        <button type="submit" className="btn btn--primary" disabled={submitting}>
          {submitting
            ? t('common.saving')
            : mode === 'create'
              ? t('accountant.employees.createSubmit')
              : t('accountant.employees.saveSubmit')}
        </button>
      </div>
    </form>
  );
}
