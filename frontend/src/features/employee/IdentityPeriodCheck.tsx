import { useTranslation } from 'react-i18next';
import type { ComparisonField, IdentityCheck, PeriodCheck } from '../../services/employeePortal';

type IdentityPeriodCheckProps = {
  identity: IdentityCheck;
  period: PeriodCheck;
};

function statusClass(status: string, severity?: string): string {
  if (status === 'mismatch' && severity === 'critical') return 'is-critical';
  if (status === 'mismatch') return 'is-warning';
  if (status === 'uncertain') return 'is-uncertain';
  if (status === 'missing') return 'is-missing';
  if (status === 'match') return 'is-match';
  return 'is-extracted';
}

function FieldRow({ field }: { field: ComparisonField }) {
  const { t } = useTranslation();
  return (
    <li className={`identity-period-check__field ${statusClass(field.status, field.severity)}`}>
      <div className="identity-period-check__field-head">
        <strong>{t(`employee.compare.fields.${field.key}`, { defaultValue: field.key })}</strong>
        <span>{t(`employee.compare.status.${field.status}`, { defaultValue: field.status })}</span>
      </div>
      <p>
        {t('employee.compare.extracted')}: {field.extracted_display ?? '—'}
      </p>
      <p>
        {t('employee.compare.expected')}: {field.expected_display ?? '—'}
      </p>
    </li>
  );
}

export function IdentityPeriodCheck({ identity, period }: IdentityPeriodCheckProps) {
  const { t } = useTranslation();
  const nid = identity.fields.find((f) => f.key === 'national_id');
  const nameOnlyWarning =
    !identity.blocks_confirmation &&
    identity.fields.some((f) => f.key === 'employee_name' && f.status === 'mismatch');

  return (
    <div className="identity-period-check" role="region" aria-label={t('employee.compare.title')}>
      <h3>{t('employee.compare.title')}</h3>
      <p className="identity-period-check__intro">{t('employee.compare.intro')}</p>

      {nid?.status === 'mismatch' && (
        <div className="identity-period-check__banner is-critical" role="alert">
          {t('employee.compare.nationalIdMismatch')}
        </div>
      )}
      {period.blocks_confirmation && (
        <div className="identity-period-check__banner is-critical" role="alert">
          {t('employee.compare.periodMismatch', {
            selected: `${period.selected_month}/${period.selected_year}`,
            extracted:
              period.extracted_month && period.extracted_year
                ? `${period.extracted_month}/${period.extracted_year}`
                : '—',
          })}
        </div>
      )}
      {nameOnlyWarning && (
        <div className="identity-period-check__banner is-warning" role="status">
          {t('employee.compare.nameMismatchWarning')}
        </div>
      )}

      <ul className="identity-period-check__list">
        {identity.fields.map((field) => (
          <FieldRow key={field.key} field={field} />
        ))}
        <li className={`identity-period-check__field ${statusClass(period.status)}`}>
          <div className="identity-period-check__field-head">
            <strong>{t('employee.compare.fields.pay_period')}</strong>
            <span>{t(`employee.compare.status.${period.status}`, { defaultValue: period.status })}</span>
          </div>
          <p>
            {t('employee.compare.selected')}: {period.selected_month}/{period.selected_year}
          </p>
          <p>
            {t('employee.compare.extracted')}:{' '}
            {period.extracted_month && period.extracted_year
              ? `${period.extracted_month}/${period.extracted_year}`
              : '—'}
          </p>
        </li>
      </ul>
    </div>
  );
}
