import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import {
  EmptyState,
  LoadingOverlay,
  ModalDialog,
} from '../../components/ui/Dialog';
import {
  getAccountantErrorMessage,
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
import { ApiClientError } from '../../services/api';
import { documentsService } from '../../services/documents';
import { employeesService } from '../../services/employees';
import type { DocumentResponse } from '../../types';
import {
  MONTH_KEYS,
  documentsForPeriod,
  groupDocumentTypes,
  monthTone,
  type ProfileDocItem,
  type ProfilePayload,
} from './EmployeeProfile.model';

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
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [selectedMonth, setSelectedMonth] = useState<number | null>(null);
  const [uploadingType, setUploadingType] = useState<string | null>(null);
  const [listDialog, setListDialog] = useState<{
    title: string;
    docs: ProfileDocItem[];
  } | null>(null);
  const [docDetail, setDocDetail] = useState<DocumentResponse | null>(null);
  const [docDetailLoading, setDocDetailLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const pendingUploadRef = useRef<{
    typeKey: string;
    periodYear?: number;
    periodMonth?: number;
  } | null>(null);

  const reload = async () => {
    if (!employeeNumber) return;
    const data = await employeesService.getProfile(employeeNumber);
    setProfile(data as ProfilePayload);
  };

  useEffect(() => {
    if (!employeeNumber) return;
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = (await employeesService.getProfile(employeeNumber)) as ProfilePayload;
        if (cancelled) return;
        setProfile(data);
        const years = Array.from(new Set(data.monthly_history.map((row) => row.year))).sort(
          (a, b) => b - a,
        );
        setSelectedYear(years[0] ?? new Date().getFullYear());
        setSelectedMonth(null);
      } catch (err) {
        if (cancelled) return;
        const message =
          err instanceof ApiClientError
            ? err.message
            : getAccountantErrorMessage('loadFailed', t);
        setError(message);
        setProfile((prev) =>
          prev && prev.employee.employee_number === employeeNumber ? prev : null,
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [employeeNumber, t]);

  const docCards = useMemo(
    () => (profile ? groupDocumentTypes(profile.document_collections) : []),
    [profile],
  );

  const years = useMemo(() => {
    if (!profile) return [];
    const fromHistory = profile.monthly_history.map((row) => row.year);
    const fromDocs = docCards.flatMap((card) =>
      card.documents.map((doc) => doc.period_year).filter((y): y is number => y != null),
    );
    return Array.from(new Set([...fromHistory, ...fromDocs, new Date().getFullYear()])).sort(
      (a, b) => b - a,
    );
  }, [profile, docCards]);

  const historyByMonth = useMemo(() => {
    const map = new Map<string, MonthRow>();
    if (!profile) return map;
    for (const row of profile.monthly_history) {
      map.set(`${row.year}-${row.month}`, row);
    }
    return map;
  }, [profile]);

  const activeYear = selectedYear ?? years[0] ?? new Date().getFullYear();
  const selectedMonthRow =
    selectedMonth != null ? historyByMonth.get(`${activeYear}-${selectedMonth}`) : undefined;

  const summary = useMemo(() => {
    if (!profile) return null;
    const totalTypes = docCards.length;
    const presentTypes = docCards.filter((card) => card.documents.length > 0).length;
    const latestPeriod = profile.monthly_history[0];
    const openIssues = profile.monthly_history.filter(
      (row) =>
        row.missing_documents.length > 0 ||
        row.validation_status === 'failed' ||
        row.validation_status === 'critical',
    ).length;
    const failedMonths = profile.monthly_history.filter(
      (row) => row.validation_status === 'failed' || row.validation_status === 'critical',
    ).length;
    return {
      totalTypes,
      presentTypes,
      latestPeriod,
      openIssues,
      failedMonths,
      validationLabel: failedMonths
        ? t('accountant.employeeProfile.summaryValidationIssues', { count: failedMonths })
        : t('accountant.employeeProfile.summaryValidationClear'),
    };
  }, [profile, docCards, t]);

  const startUpload = (typeKey: string, periodYear?: number, periodMonth?: number) => {
    pendingUploadRef.current = { typeKey, periodYear, periodMonth };
    fileInputRef.current?.click();
  };

  const onFileSelected = async (file: File | null) => {
    const pending = pendingUploadRef.current;
    pendingUploadRef.current = null;
    if (!file || !pending || !profile?.employee.id) return;
    setUploadingType(pending.typeKey);
    setActionError(null);
    try {
      await documentsService.upload(file, pending.typeKey, 'auto', {
        employeeId: profile.employee.id,
        periodYear: pending.periodYear,
        periodMonth: pending.periodMonth,
      });
      await reload();
    } catch (err) {
      console.error('Document upload failed', err);
      const message =
        err instanceof ApiClientError
          ? err.message
          : getAccountantErrorMessage('uploadFailed', t);
      setActionError(message);
    } finally {
      setUploadingType(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const openDocumentList = (title: string, docs: ProfileDocItem[]) => {
    setListDialog({ title, docs });
  };

  const openDocumentDetail = async (documentId: string) => {
    setDocDetailLoading(true);
    setActionError(null);
    try {
      const detail = await documentsService.getDocument(documentId);
      setDocDetail(detail);
    } catch (err) {
      console.error('Load document failed', err);
      const message =
        err instanceof ApiClientError
          ? err.message
          : getAccountantErrorMessage('loadFailed', t);
      setActionError(message);
    } finally {
      setDocDetailLoading(false);
    }
  };

  const periodDocs =
    selectedMonth != null ? documentsForPeriod(docCards, activeYear, selectedMonth) : [];

  return (
    <PortalPage
      title={
        profile
          ? profile.employee.full_name
          : t('accountant.employees.editTitle', { number: employeeNumber ?? '' })
      }
      description={t('accountant.employeeProfile.description')}
    >
      <input
        ref={fileInputRef}
        type="file"
        className="visually-hidden"
        accept=".pdf,.png,.jpg,.jpeg,.webp"
        aria-hidden="true"
        tabIndex={-1}
        onChange={(event) => void onFileSelected(event.target.files?.[0] ?? null)}
      />

      <div className="panel-relative employee-profile" aria-busy={loading}>
        {loading && !profile && (
          <LoadingOverlay label={t('accountant.employeeProfile.loading')} />
        )}
        {error && (
          <p className="chat-panel__error" role="alert">
            {error}
          </p>
        )}
        {actionError && (
          <p className="chat-panel__error" role="alert">
            {actionError}
          </p>
        )}
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
        {profile && summary && (
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

            <section className="employee-summary" aria-label={t('accountant.employeeProfile.summaryTitle')}>
              <div className="employee-summary__item">
                <span className="employee-summary__label">
                  {t('accountant.employeeProfile.summaryStatus')}
                </span>
                <strong>{getEmployeeStatusLabel(profile.employee.status, t)}</strong>
              </div>
              <div className="employee-summary__item">
                <span className="employee-summary__label">
                  {t('accountant.employeeProfile.summaryCompleteness')}
                </span>
                <strong>
                  {profile.employee.profile_incomplete
                    ? t('accountant.employees.incomplete')
                    : t('accountant.employeeProfile.summaryProfileComplete')}
                </strong>
              </div>
              <div className="employee-summary__item">
                <span className="employee-summary__label">
                  {t('accountant.employeeProfile.summaryLatestPayroll')}
                </span>
                <strong>
                  {summary.latestPeriod
                    ? formatMonthYear(summary.latestPeriod.year, summary.latestPeriod.month, locale)
                    : t('common.emDash')}
                </strong>
              </div>
              <div className="employee-summary__item">
                <span className="employee-summary__label">
                  {t('accountant.employeeProfile.summaryDocuments')}
                </span>
                <strong>
                  {t('accountant.employeeProfile.summaryDocumentCount', {
                    present: summary.presentTypes,
                    total: summary.totalTypes,
                  })}
                </strong>
              </div>
              <div className="employee-summary__item">
                <span className="employee-summary__label">
                  {t('accountant.employeeProfile.summaryValidation')}
                </span>
                <strong>{summary.validationLabel}</strong>
              </div>
              <div className="employee-summary__item">
                <span className="employee-summary__label">
                  {t('accountant.employeeProfile.summaryOpenIssues')}
                </span>
                <strong>
                  {summary.openIssues > 0
                    ? t('accountant.employeeProfile.summaryOpenIssuesCount', {
                        count: summary.openIssues,
                      })
                    : t('accountant.employeeProfile.summaryNoOpenIssues')}
                </strong>
              </div>
            </section>

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
              <div className="doc-mgmt-grid">
                {docCards.map((card) => {
                  const latestLabel = card.latest
                    ? card.latest.period_year && card.latest.period_month
                      ? formatMonthYear(card.latest.period_year, card.latest.period_month, locale)
                      : t('accountant.employeeProfile.latestDocumentAttached')
                    : t('accountant.employeeProfile.noDocumentsYet');
                  return (
                    <article key={card.typeKey} className="doc-mgmt-card">
                      <header className="doc-mgmt-card__header">
                        <h4>{getDocumentTypeLabel(card.typeKey, t)}</h4>
                        <AvailabilityBadge value={card.availability} />
                      </header>
                      <dl className="doc-mgmt-card__meta">
                        <div>
                          <dt>{t('accountant.employeeProfile.documentCount')}</dt>
                          <dd>{card.documents.length}</dd>
                        </div>
                        <div>
                          <dt>{t('accountant.employeeProfile.latestDocument')}</dt>
                          <dd>{latestLabel}</dd>
                        </div>
                      </dl>
                      <div className="doc-mgmt-card__actions">
                        <button
                          type="button"
                          className="btn btn--secondary"
                          disabled={card.documents.length === 0}
                          onClick={() =>
                            openDocumentList(
                              getDocumentTypeLabel(card.typeKey, t),
                              card.documents,
                            )
                          }
                        >
                          {t('accountant.employeeProfile.openDocuments')}
                        </button>
                        <button
                          type="button"
                          className="btn btn--primary"
                          disabled={uploadingType === card.typeKey}
                          onClick={() => startUpload(card.typeKey)}
                        >
                          {uploadingType === card.typeKey
                            ? t('common.saving')
                            : t('accountant.employeeProfile.uploadDocument')}
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            </ProfileSection>

            <ProfileSection title={t('accountant.employeeProfile.payrollHistory')} defaultOpen>
              <div className="payroll-year-nav" role="tablist" aria-label={t('accountant.employeeProfile.selectYear')}>
                {years.map((year) => (
                  <button
                    key={year}
                    type="button"
                    role="tab"
                    aria-selected={year === activeYear}
                    className={`payroll-year-nav__btn${year === activeYear ? ' payroll-year-nav__btn--active' : ''}`}
                    onClick={() => {
                      setSelectedYear(year);
                      setSelectedMonth(null);
                    }}
                  >
                    {year}
                  </button>
                ))}
              </div>

              <div
                className="payroll-month-grid"
                role="list"
                aria-label={t('accountant.employeeProfile.selectMonth')}
              >
                {MONTH_KEYS.map((key, index) => {
                  const month = index + 1;
                  const row = historyByMonth.get(`${activeYear}-${month}`);
                  const tone = monthTone(row);
                  const isSelected = selectedMonth === month;
                  return (
                    <button
                      key={key}
                      type="button"
                      role="listitem"
                      className={`payroll-month-cell payroll-month-cell--${tone}${isSelected ? ' payroll-month-cell--selected' : ''}`}
                      aria-pressed={isSelected}
                      onClick={() => setSelectedMonth(month)}
                    >
                      <span className="payroll-month-cell__label">
                        {t(`accountant.employeeProfile.months.${key}`)}
                      </span>
                      <span className="payroll-month-cell__tone" aria-hidden="true" />
                      <span className="visually-hidden">
                        {t(`accountant.employeeProfile.monthStatus.${tone}`)}
                      </span>
                    </button>
                  );
                })}
              </div>

              <div className="payroll-month-legend" aria-hidden="true">
                <span>
                  <i className="payroll-legend payroll-legend--complete" />
                  {t('accountant.employeeProfile.monthStatus.complete')}
                </span>
                <span>
                  <i className="payroll-legend payroll-legend--missing" />
                  {t('accountant.employeeProfile.monthStatus.missing')}
                </span>
                <span>
                  <i className="payroll-legend payroll-legend--failed" />
                  {t('accountant.employeeProfile.monthStatus.failed')}
                </span>
                <span>
                  <i className="payroll-legend payroll-legend--empty" />
                  {t('accountant.employeeProfile.monthStatus.empty')}
                </span>
              </div>

              {selectedMonth != null && (
                <div className="payroll-month-panel">
                  <header className="payroll-month-panel__header">
                    <div>
                      <h4>{formatMonthYear(activeYear, selectedMonth, locale)}</h4>
                      {selectedMonthRow ? (
                        <span
                          className={`status-badge status-badge--${selectedMonthRow.validation_status}`}
                        >
                          {getValidationStatusLabel(selectedMonthRow.validation_status, t)}
                        </span>
                      ) : (
                        <span className="status-badge status-badge--doc-missing">
                          {t('accountant.employeeProfile.monthStatus.empty')}
                        </span>
                      )}
                    </div>
                    <button
                      type="button"
                      className="btn btn--ghost"
                      onClick={() => setSelectedMonth(null)}
                    >
                      {t('common.clear')}
                    </button>
                  </header>

                  {selectedMonthRow?.missing_documents.length ? (
                    <p>
                      {t('accountant.employeeProfile.missing', {
                        list: selectedMonthRow.missing_documents
                          .map((code) => getDocumentTypeLabel(code, t))
                          .join(', '),
                      })}
                    </p>
                  ) : null}
                  {selectedMonthRow?.warnings.length ? (
                    <p>
                      {t('accountant.employeeProfile.warnings', {
                        list: selectedMonthRow.warnings.join('; '),
                      })}
                    </p>
                  ) : null}

                  <div className="doc-mgmt-grid doc-mgmt-grid--compact">
                    {periodDocs.map(({ card, docs, available }) => (
                      <article key={card.typeKey} className="doc-mgmt-card">
                        <header className="doc-mgmt-card__header">
                          <h4>{getDocumentTypeLabel(card.typeKey, t)}</h4>
                          <AvailabilityBadge value={available ? 'available' : 'missing'} />
                        </header>
                        <p className="doc-mgmt-card__hint">
                          {available
                            ? t('accountant.employeeProfile.documentCountLabel', {
                                count: docs.length || card.documents.length,
                              })
                            : t('accountant.employeeProfile.noDocumentsYet')}
                        </p>
                        <div className="doc-mgmt-card__actions">
                          <button
                            type="button"
                            className="btn btn--secondary"
                            disabled={!available}
                            onClick={() =>
                              openDocumentList(
                                getDocumentTypeLabel(card.typeKey, t),
                                card.supportsPeriod ? docs : card.documents,
                              )
                            }
                          >
                            {t('common.open')}
                          </button>
                          <button
                            type="button"
                            className="btn btn--primary"
                            disabled={uploadingType === card.typeKey}
                            onClick={() =>
                              startUpload(
                                card.typeKey,
                                card.supportsPeriod ? activeYear : undefined,
                                card.supportsPeriod ? selectedMonth : undefined,
                              )
                            }
                          >
                            {uploadingType === card.typeKey
                              ? t('common.saving')
                              : t('accountant.employeeProfile.uploadDocument')}
                          </button>
                        </div>
                      </article>
                    ))}
                  </div>
                </div>
              )}
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

      {listDialog && (
        <ModalDialog
          title={listDialog.title}
          onClose={() => setListDialog(null)}
          wide
          footer={
            <button type="button" className="btn btn--secondary" onClick={() => setListDialog(null)}>
              {t('common.cancel')}
            </button>
          }
        >
          {listDialog.docs.length === 0 ? (
            <EmptyState title={t('accountant.employeeProfile.noDocumentsYet')} />
          ) : (
            <ul className="doc-list">
              {listDialog.docs.map((doc) => (
                <li key={doc.document_id} className="doc-list__item">
                  <div>
                    <strong>
                      {doc.period_year && doc.period_month
                        ? formatMonthYear(doc.period_year, doc.period_month, locale)
                        : getDocumentTypeLabel(doc.type_key, t)}
                    </strong>
                    {doc.gross_salary != null && (
                      <span>
                        {t('accountant.employeeProfile.grossNet', {
                          gross: formatCurrencyILS(Number(doc.gross_salary), locale),
                          net:
                            doc.net_salary != null
                              ? formatCurrencyILS(Number(doc.net_salary), locale)
                              : t('common.emDash'),
                        })}
                      </span>
                    )}
                  </div>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    disabled={docDetailLoading}
                    onClick={() => doc.document_id && void openDocumentDetail(doc.document_id)}
                  >
                    {t('common.viewDetails')}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </ModalDialog>
      )}

      {docDetail && (
        <ModalDialog
          title={t('accountant.employeeProfile.documentDetails')}
          onClose={() => setDocDetail(null)}
          footer={
            <button type="button" className="btn btn--secondary" onClick={() => setDocDetail(null)}>
              {t('common.cancel')}
            </button>
          }
        >
          <dl className="doc-detail-grid">
            <div>
              <dt>{t('accountant.employeeProfile.documentId')}</dt>
              <dd>{docDetail.document_id}</dd>
            </div>
            <div>
              <dt>{t('accountant.employeeProfile.documentType')}</dt>
              <dd>{getDocumentTypeLabel(docDetail.document_type, t)}</dd>
            </div>
            <div>
              <dt>{t('common.status')}</dt>
              <dd>{docDetail.status}</dd>
            </div>
            <div>
              <dt>{t('accountant.employeeProfile.originalFilename')}</dt>
              <dd>{docDetail.original_filename}</dd>
            </div>
          </dl>
        </ModalDialog>
      )}
    </PortalPage>
  );
}
