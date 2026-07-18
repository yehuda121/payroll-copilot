import { useTranslation } from 'react-i18next';
import type { PersistentDocumentType } from '../../hooks/useEmployeeDocumentWorkspace';
import { fixedFieldKeysFor } from '../../lib/employee/document-fixed-forms';
import '../employee/employee-payslip.css';
import '../guest/landing/landing-chat.css';

type EmployeeFixedDocumentFormProps = {
  documentType: Exclude<PersistentDocumentType, 'contract'>;
  values: Record<string, string>;
  busy?: boolean;
  reviewNotice?: string | null;
  onChangeField: (key: string, value: string) => void;
};

export function EmployeeFixedDocumentForm({
  documentType,
  values,
  busy = false,
  reviewNotice,
  onChangeField,
}: EmployeeFixedDocumentFormProps) {
  const { t } = useTranslation();
  const keys = fixedFieldKeysFor(documentType) ?? [];

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
                  className="digital-form__input"
                  type="text"
                  value={values[key] ?? ''}
                  disabled={busy}
                  onChange={(event) => onChangeField(key, event.target.value)}
                  autoComplete="off"
                />
              </label>
            );
          })}
        </div>
      </section>
    </div>
  );
}
