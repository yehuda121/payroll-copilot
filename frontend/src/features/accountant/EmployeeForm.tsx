import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
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
  profileIncomplete: boolean;
};

type EmployeeFormProps = {
  mode: 'create' | 'edit';
  initial?: Partial<EmployeeFormValues>;
  submitting?: boolean;
  error?: string | null;
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
  profileIncomplete: false,
};

export function toWritePayload(
  values: EmployeeFormValues,
  mode: 'create' | 'edit',
): EmployeeWritePayload & { employee_number?: string } {
  const amount = values.baseSalaryOrRate.trim()
    ? Number(values.baseSalaryOrRate)
    : null;
  const payload: EmployeeWritePayload & { employee_number?: string } = {
    first_name: values.firstName.trim(),
    last_name: values.lastName.trim(),
    employment_type: values.employmentType,
    salary_type: values.salaryType,
    email: values.email.trim() || undefined,
    national_id: values.nationalId.trim() || undefined,
    contract_start_date: values.contractStartDate || undefined,
    profile_incomplete: values.profileIncomplete,
    hourly_rate: values.salaryType === 'hourly' ? amount : null,
    monthly_salary: values.salaryType === 'monthly' ? amount : null,
  };
  if (mode === 'create') {
    payload.employee_number = values.employeeNumber.trim();
  }
  return payload;
}

export function EmployeeForm({
  mode,
  initial,
  submitting,
  error,
  onSubmit,
  onDirtyChange,
  footer,
}: EmployeeFormProps) {
  const { t } = useTranslation();
  const baselineRef = useRef<EmployeeFormValues>({ ...DEFAULTS, ...initial });
  const [values, setValues] = useState<EmployeeFormValues>({ ...DEFAULTS, ...initial });

  useEffect(() => {
    const next = { ...DEFAULTS, ...initial };
    baselineRef.current = next;
    setValues(next);
    onDirtyChange?.(false);
  }, [initial, onDirtyChange]);

  useEffect(() => {
    const dirty = JSON.stringify(values) !== JSON.stringify(baselineRef.current);
    onDirtyChange?.(dirty);
  }, [values, onDirtyChange]);

  const update = <K extends keyof EmployeeFormValues>(key: K, value: EmployeeFormValues[K]) => {
    setValues((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
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
          onChange={(e) => update('employeeNumber', e.target.value)}
        />
      </div>
      <div className="form-field">
        <label htmlFor="firstName">{t('accountant.employees.fieldFirstName')}</label>
        <input
          id="firstName"
          required
          value={values.firstName}
          onChange={(e) => update('firstName', e.target.value)}
        />
      </div>
      <div className="form-field">
        <label htmlFor="lastName">{t('accountant.employees.fieldLastName')}</label>
        <input
          id="lastName"
          required
          value={values.lastName}
          onChange={(e) => update('lastName', e.target.value)}
        />
      </div>
      <div className="form-field">
        <label htmlFor="email">{t('accountant.employees.fieldEmail')}</label>
        <input
          id="email"
          type="email"
          value={values.email}
          onChange={(e) => update('email', e.target.value)}
        />
      </div>
      <div className="form-field">
        <label htmlFor="nationalId">{t('accountant.employees.fieldNationalId')}</label>
        <input
          id="nationalId"
          value={values.nationalId}
          onChange={(e) => update('nationalId', e.target.value)}
          autoComplete="off"
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
      <div className="form-field form-field--checkbox">
        <label htmlFor="profileIncomplete">
          <input
            id="profileIncomplete"
            type="checkbox"
            checked={values.profileIncomplete}
            onChange={(e) => update('profileIncomplete', e.target.checked)}
          />
          {t('accountant.employees.fieldProfileIncomplete')}
        </label>
      </div>
      {error && <p className="chat-panel__error" style={{ gridColumn: '1 / -1' }}>{error}</p>}
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
