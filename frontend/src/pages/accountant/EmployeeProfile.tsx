import { useEffect, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { EmptyState, LoadingOverlay } from '../../components/ui/Dialog';
import {
  getAccountantErrorMessage,
  getDocumentCollectionLabel,
  getDocumentStatusLabel,
  getDocumentTypeLabel,
  getEmployeeStatusLabel,
  getEmploymentTypeLabel,
  getSalaryTypeLabel,
  getValidationModuleDescription,
  getValidationModuleName,
  getValidationStatusLabel,
} from '../../i18n/accountantLabels';
import { useAppLocale } from '../../hooks/useAppLocale';
import { formatCurrencyILS, formatDateTime, formatMonthYear } from '../../lib/formatLocale';
import { employeesService } from '../../services/employees';
import type { AuditLogItem, ExpectedDocumentAvailability } from '../../types/employee';

type ProfileDocItem = {
  type_key: string;
  label: string;
  availability: ExpectedDocumentAvailability;
  supports_period: boolean;
};

type ProfileCollection = {
  key: string;
  label: string;
  items: ProfileDocItem[];
};

type MonthRow = {
  year: number;
  month: number;
  label: string;
  payslip: ExpectedDocumentAvailability;
  attendance: ExpectedDocumentAvailability;
  validation_status: string;
  missing_documents: string[];
  warnings: string[];
};

type ProfilePayload = {
  employee: {
    employee_number: string;
    full_name: string;
    first_name: string;
    last_name: string;
    email?: string | null;
    department?: string | null;
    employment_type: string;
    salary_type: string;
    status: string;
    profile_incomplete?: boolean;
    national_id_masked?: string | null;
    contract_start_date?: string;
    base_salary_or_rate?: number | null;
  };
  document_collections: ProfileCollection[];
  monthly_history: MonthRow[];
  validation_history: unknown[];
  findings: unknown[];
  timeline: AuditLogItem[];
  audit_log: AuditLogItem[];
  validation_modules: Array<{ key: string; label: string; description: string; enabled: boolean }>;
};

function AvailabilityBadge({ value }: { value: string }) {
  const { t } = useTranslation();
  return (
    <span className={`status-badge status-badge--doc-${value}`}>
      {getDocumentStatusLabel(value, t)}
    </span>
  );
}

function ProfileSection({
  title,
  defaultOpen = false,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="profile-section">
      <button
        type="button"
        className="profile-section__header"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
      >
        <strong>{title}</strong>
        <span aria-hidden="true">{open ? '▾' : '▸'}</span>
        <span className="visually-hidden">
          {open ? t('common.collapse') : t('common.expand')}
        </span>
      </button>
      {open && <div className="profile-section__body">{children}</div>}
    </section>
  );
}

export function EmployeeProfilePage() {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const { employeeNumber } = useParams<{ employeeNumber: string }>();
  const [profile, setProfile] = useState<ProfilePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [yearFilter, setYearFilter] = useState<number | 'all'>('all');

  useEffect(() => {
    if (!employeeNumber) return;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await employeesService.getProfile(employeeNumber);
        setProfile(data as ProfilePayload);
      } catch {
        setError(getAccountantErrorMessage('loadFailed', t));
        setProfile(null);
      } finally {
        setLoading(false);
      }
    })();
  }, [employeeNumber, t]);

  const years = profile
    ? Array.from(new Set(profile.monthly_history.map((row) => row.year))).sort((a, b) => b - a)
    : [];
  const months =
    profile?.monthly_history.filter((row) => yearFilter === 'all' || row.year === yearFilter) ?? [];

  return (
    <PortalPage
      title={profile ? profile.employee.full_name : t('accountant.employees.editTitle', { number: employeeNumber ?? '' })}
      description={t('accountant.employeeProfile.description')}
    >
      <div className="panel-relative employee-profile">
        {loading && <LoadingOverlay label={t('accountant.employeeProfile.loading')} />}
        {error && <p className="chat-panel__error">{error}</p>}
        {!loading && !profile && !error && (
          <EmptyState
            title={t('accountant.employees.notFoundTitle')}
            action={
              <Link to="/accountant/employees" className="btn btn--secondary">
                {t('accountant.employees.backToEmployees')}
              </Link>
            }
          />
        )}
        {profile && (
          <>
            <div className="accountant-toolbar">
              <div className="month-card__meta">
                <span>#{profile.employee.employee_number}</span>
                <span className={`status-badge status-badge--${profile.employee.status}`}>
                  {getEmployeeStatusLabel(profile.employee.status, t)}
                </span>
                {profile.employee.profile_incomplete && (
                  <span className="status-badge status-badge--incomplete">
                    {t('accountant.employees.incomplete')}
                  </span>
                )}
              </div>
              <Link
                to={`/accountant/employees/${profile.employee.employee_number}/edit`}
                className="btn btn--primary"
              >
                {t('accountant.employeeProfile.editEmployee')}
              </Link>
            </div>

            <ProfileSection title={t('accountant.employeeProfile.personalInformation')} defaultOpen>
              <div className="employee-profile__grid">
                <div>
                  <strong>{t('accountant.employeeProfile.name')}</strong>
                  <p>{profile.employee.full_name}</p>
                </div>
                <div>
                  <strong>{t('accountant.employeeProfile.email')}</strong>
                  <p>{profile.employee.email || t('common.emDash')}</p>
                </div>
                <div>
                  <strong>{t('accountant.employeeProfile.department')}</strong>
                  <p>{profile.employee.department || t('common.emDash')}</p>
                </div>
                <div>
                  <strong>{t('accountant.employeeProfile.nationalId')}</strong>
                  <p>{profile.employee.national_id_masked || t('common.emDash')}</p>
                </div>
                <div>
                  <strong>{t('accountant.employeeProfile.employment')}</strong>
                  <p>{getEmploymentTypeLabel(profile.employee.employment_type, t)}</p>
                </div>
                <div>
                  <strong>{t('accountant.employeeProfile.compensation')}</strong>
                  <p>
                    {getSalaryTypeLabel(profile.employee.salary_type, t)}{' '}
                    {profile.employee.base_salary_or_rate != null
                      ? formatCurrencyILS(Number(profile.employee.base_salary_or_rate), locale)
                      : t('common.emDash')}
                  </p>
                </div>
              </div>
            </ProfileSection>

            <ProfileSection title={t('accountant.employeeProfile.documents')} defaultOpen>
              <p className="guest-section__intro">{t('accountant.employeeProfile.documentsIntro')}</p>
              {profile.document_collections.map((collection) => (
                <div key={collection.key} className="doc-collection">
                  <h4>{getDocumentCollectionLabel(collection.key, t)}</h4>
                  <div className="doc-type-grid">
                    {collection.items.map((item) => (
                      <div key={item.type_key} className="doc-type-row">
                        <span>{getDocumentTypeLabel(item.type_key, t)}</span>
                        <AvailabilityBadge value={item.availability} />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </ProfileSection>

            <ProfileSection title={t('accountant.employeeProfile.monthlyHistory')} defaultOpen>
              <div className="accountant-toolbar">
                <select
                  aria-label={t('accountant.employeeProfile.filterYearAria')}
                  value={yearFilter === 'all' ? 'all' : String(yearFilter)}
                  onChange={(e) =>
                    setYearFilter(e.target.value === 'all' ? 'all' : Number(e.target.value))
                  }
                >
                  <option value="all">{t('accountant.employeeProfile.allYears')}</option>
                  {years.map((year) => (
                    <option key={year} value={year}>
                      {year}
                    </option>
                  ))}
                </select>
              </div>
              <div className="month-timeline">
                {months.map((row) => (
                  <article key={`${row.year}-${row.month}`} className="month-card">
                    <strong>{formatMonthYear(row.year, row.month, locale)}</strong>
                    <div className="month-card__meta">
                      <span>
                        {t('accountant.employeeProfile.payslip')}{' '}
                        <AvailabilityBadge value={row.payslip} />
                      </span>
                      <span>
                        {t('accountant.employeeProfile.attendance')}{' '}
                        <AvailabilityBadge value={row.attendance} />
                      </span>
                      <span className={`status-badge status-badge--${row.validation_status}`}>
                        {getValidationStatusLabel(row.validation_status, t)}
                      </span>
                    </div>
                    {row.missing_documents.length > 0 && (
                      <p>
                        {t('accountant.employeeProfile.missing', {
                          list: row.missing_documents
                            .map((code) => getDocumentTypeLabel(code, t))
                            .join(', '),
                        })}
                      </p>
                    )}
                    {row.warnings.length > 0 && (
                      <p>
                        {t('accountant.employeeProfile.warnings', {
                          list: row.warnings.join('; '),
                        })}
                      </p>
                    )}
                  </article>
                ))}
              </div>
            </ProfileSection>

            <ProfileSection title={t('accountant.employeeProfile.validationModules')}>
              <div className="doc-type-grid">
                {profile.validation_modules.map((module) => (
                  <div key={module.key} className="doc-type-row">
                    <div>
                      <strong>{getValidationModuleName(module.key, t)}</strong>
                      <p>{getValidationModuleDescription(module.key, t)}</p>
                    </div>
                    <span
                      className={`status-badge status-badge--${module.enabled ? 'active' : 'disabled'}`}
                    >
                      {module.enabled
                        ? t('accountant.validations.moduleEnabled')
                        : t('accountant.validations.moduleDisabled')}
                    </span>
                  </div>
                ))}
              </div>
            </ProfileSection>

            <ProfileSection title={t('accountant.employeeProfile.validationHistory')}>
              <EmptyState
                title={t('accountant.employeeProfile.validationHistoryEmptyTitle')}
                description={t('accountant.employeeProfile.validationHistoryEmptyDescription')}
              />
            </ProfileSection>

            <ProfileSection title={t('accountant.employeeProfile.findings')}>
              <EmptyState
                title={t('accountant.employeeProfile.findingsEmptyTitle')}
                description={t('accountant.employeeProfile.findingsEmptyDescription')}
              />
            </ProfileSection>

            <ProfileSection title={t('accountant.employeeProfile.timeline')}>
              {profile.timeline.length === 0 ? (
                <EmptyState title={t('accountant.employeeProfile.timelineEmpty')} />
              ) : (
                <ul className="audit-list">
                  {profile.timeline.map((item) => (
                    <li key={item.id}>
                      <strong>{item.action}</strong>
                      <span>{formatDateTime(item.created_at, locale)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </ProfileSection>

            <ProfileSection title={t('accountant.employeeProfile.auditLog')}>
              {profile.audit_log.length === 0 ? (
                <EmptyState title={t('accountant.employeeProfile.auditEmpty')} />
              ) : (
                <ul className="audit-list">
                  {profile.audit_log.map((item) => (
                    <li key={item.id}>
                      <strong>{item.action}</strong>
                      <span>{formatDateTime(item.created_at, locale)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </ProfileSection>
          </>
        )}
      </div>
    </PortalPage>
  );
}
