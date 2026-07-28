import { useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { FormInfoPanel, FormShell } from '../../components/ui/form/FormPrimitives';
import {
  BriefcaseIcon,
  CoinsIcon,
  IdCardIcon,
  InfoIcon,
  SparklesIcon,
} from '../../components/ui/icons';
import { BirthDateField } from './BirthDateField';
import { parseBirthDate } from '../../lib/employee/birth-date';
import {
  documentFieldSectionsForType,
  orderedFormFieldKeys,
  resolveDocumentFieldLabel,
  type DocumentFieldSection,
} from '../../lib/employee/document-field-registry';
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

function sectionIcon(section: DocumentFieldSection): ReactNode {
  if (section === 'identity') return <IdCardIcon size={16} />;
  if (section === 'employment') return <BriefcaseIcon size={16} />;
  if (section === 'compensation') return <CoinsIcon size={16} />;
  return <InfoIcon size={16} />;
}

export function EmployeeFixedDocumentForm({
  documentType,
  values,
  busy = false,
  reviewNotice,
  fieldErrors = {},
  onChangeField,
}: EmployeeFixedDocumentFormProps) {
  const { t } = useTranslation();
  const keys = orderedFormFieldKeys(documentType);
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

  const fieldLabel = (key: string) => {
    const label = resolveDocumentFieldLabel(documentType, key, t);
    if (!label) {
      throw new Error(`Missing document field registry entry: ${documentType}.${key}`);
    }
    return label;
  };

  const sections = documentFieldSectionsForType(documentType, keys);
  const aside = (
    <FormInfoPanel
      tone="tip"
      eyebrow={t('forms.info.tipEyebrow')}
      title={
        documentType === 'contract'
          ? t('forms.info.contractTitle')
          : t('forms.info.identityCardTitle')
      }
      icon={<SparklesIcon size={14} aria-hidden="true" />}
    >
      <p>
        {documentType === 'contract'
          ? t('forms.info.contractBody')
          : t('forms.info.identityCardBody')}
      </p>
    </FormInfoPanel>
  );

  const renderContractField = (key: string, label: string) => {
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
            className="digital-form__input pc-form-control--select"
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
  };

  return (
    <FormShell aside={aside}>
      <div
        className="digital-form employee-digital-form document-fixed-edit-form"
        data-busy={busy || undefined}
        role="form"
        aria-label={t('employee.documents.tabDigital')}
      >
        {reviewNotice ? (
          <p className="digital-form__hint document-fixed-edit-form__notice">{reviewNotice}</p>
        ) : null}
        {documentType === 'contract' ? (
          <p className="digital-form__hint document-fixed-edit-form__notice">
            {t('employee.documents.contract.termsHint')}
          </p>
        ) : null}

        {sections.map((section) => (
          <section
            key={section.id}
            className="digital-form__section document-fixed-edit-form__section"
            data-section-id={section.id}
          >
            <h4 className="digital-form__section-title">
              <span className="pc-form-section__icon" aria-hidden="true">
                {sectionIcon(section.id)}
              </span>
              {t(section.titleKey)}
            </h4>
            <p className="document-fixed-edit-form__section-desc">
              {t(`forms.sections.${section.id}.description`)}
            </p>
            <div className="digital-form__grid document-fixed-edit-form__grid">
              {documentType === 'contract'
                ? section.fields.map((def) =>
                    renderContractField(def.canonical_key, t(def.label_i18n_key)),
                  )
                : section.fields.map((def) => {
                    const key = def.canonical_key;
                    if (key === 'birth_date') {
                      return (
                        <BirthDateField
                          key={key}
                          id="id-birth-date"
                          label={fieldLabel('birth_date')}
                          value={values.birth_date ?? ''}
                          disabled={busy}
                          error={fieldErrors.birth_date}
                          onChange={(next) => onChangeField('birth_date', next)}
                        />
                      );
                    }
                    if (key === 'national_id') {
                      const idInvalid = Boolean(
                        (touchedId ? liveIdError : null) || fieldErrors.national_id,
                      );
                      return (
                        <label
                          key={key}
                          className="digital-form__field employee-digital-form__field"
                          htmlFor="id-national-id"
                        >
                          <span className="digital-form__label">{fieldLabel('national_id')}</span>
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
                    const nameInvalid = Boolean(
                      (touchedName ? liveNameError : null) || fieldErrors.full_name,
                    );
                    return (
                      <label
                        key={key}
                        className="digital-form__field employee-digital-form__field"
                        htmlFor="id-full-name"
                      >
                        <span className="digital-form__label">{fieldLabel('full_name')}</span>
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
          </section>
        ))}
        <span hidden>{parseBirthDate(values.birth_date ?? '') ? '' : ''}</span>
      </div>
    </FormShell>
  );
}
