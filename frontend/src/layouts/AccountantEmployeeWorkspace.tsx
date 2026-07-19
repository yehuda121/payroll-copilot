import { useEffect, useMemo, useRef, useState } from 'react';
import {
  NavLink,
  Outlet,
  useLocation,
  useParams,
  useSearchParams,
} from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Pencil, Check, X } from 'lucide-react';
import { EmployeeSessionProvider } from '../auth/EmployeeSessionContext';
import { IconBackButton } from '../components/ui/IconBackButton';
import {
  EmployeeWorkspaceProvider,
  type EmployeeWorkspaceScope,
} from '../features/employee/EmployeeWorkspaceContext';
import { ApiClientError } from '../services/api';
import { createAccountantEmployeeWorkspaceApi } from '../services/accountantEmployeeWorkspace';
import { employeesService } from '../services/employees';
import type { EmployeeMe } from '../services/employeePortal';
import type { EmployeeRecord } from '../types/employee';
import './AccountantEmployeeWorkspace.css';

export function AccountantEmployeeWorkspaceLayout() {
  const { t } = useTranslation();
  const { employeeNumber = '' } = useParams<{ employeeNumber: string }>();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const batchJobId = searchParams.get('batchJobId');
  const batchItemId = searchParams.get('batchItemId');
  const batchDocumentId = searchParams.get('batchDocumentId');
  const batchReview = useMemo(
    () =>
      batchJobId && batchItemId
        ? {
            jobId: batchJobId,
            itemId: batchItemId,
            documentId: batchDocumentId || undefined,
          }
        : undefined,
    [batchDocumentId, batchItemId, batchJobId],
  );
  const reviewQuery = batchReview
    ? `?batchJobId=${encodeURIComponent(batchReview.jobId)}&batchItemId=${encodeURIComponent(batchReview.itemId)}${batchReview.documentId ? `&batchDocumentId=${encodeURIComponent(batchReview.documentId)}` : ''}`
    : '';
  const api = useMemo(
    () =>
      createAccountantEmployeeWorkspaceApi(
        employeeNumber,
        batchReview?.documentId,
      ),
    [batchReview?.documentId, employeeNumber],
  );
  const [profile, setProfile] = useState<EmployeeMe | null>(null);
  const [master, setMaster] = useState<EmployeeRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const basePath = `/accountant/employees/${encodeURIComponent(employeeNumber)}/workspace`;
  const requestedBackPath =
    typeof location.state === 'object' &&
    location.state &&
    'backTo' in location.state &&
    typeof location.state.backTo === 'string'
      ? location.state.backTo
      : batchReview
        ? '/accountant/bulk-upload'
        : '/accountant/employees';
  const backPath = useRef(requestedBackPath).current;

  const displayName =
    master?.fullName ||
    [master?.firstName, master?.lastName].filter(Boolean).join(' ').trim() ||
    profile?.full_name;

  const loadProfiles = async () => {
    setError(null);
    try {
      const [me, record] = await Promise.all([
        api.me(),
        employeesService.getByNumber(employeeNumber),
      ]);
      setProfile(me);
      setMaster(record);
      if (record) {
        setFirstName(record.firstName ?? record.fullName.split(' ')[0] ?? '');
        setLastName(
          record.lastName ?? record.fullName.split(' ').slice(1).join(' ') ?? '',
        );
      }
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : t('common.error'));
    }
  };

  useEffect(() => {
    let active = true;
    setError(null);
    void Promise.all([api.me(), employeesService.getByNumber(employeeNumber)])
      .then(([me, record]) => {
        if (!active) return;
        setProfile(me);
        setMaster(record);
        if (record) {
          setFirstName(record.firstName ?? record.fullName.split(' ')[0] ?? '');
          setLastName(
            record.lastName ?? record.fullName.split(' ').slice(1).join(' ') ?? '',
          );
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : t('common.error'));
        }
      });
    return () => {
      active = false;
    };
  }, [api, employeeNumber, t]);

  const scope = useMemo<EmployeeWorkspaceScope>(
    () => ({
      api,
      basePath,
      employeeNumber,
      employeeName: displayName,
      backPath,
      mode: 'accountant',
      batchReview,
    }),
    [api, backPath, basePath, batchReview, displayName, employeeNumber],
  );

  const backAria = batchReview
    ? t('accountant.workspace.backToBatchAria')
    : t('accountant.workspace.backToEmployeesAria');

  const saveProfile = async () => {
    if (!master) return;
    const nextFirst = firstName.trim();
    const nextLast = lastName.trim();
    if (!nextFirst || !nextLast) {
      setError(t('accountant.workspace.profileNameRequired'));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await employeesService.update(employeeNumber, {
        first_name: nextFirst,
        last_name: nextLast,
        employment_type: master.employmentType,
        salary_type: master.salaryType,
        contract_start_date: master.contractStartDate,
        contract_end_date: master.contractEndDate,
        profile_incomplete: master.profileIncomplete,
        status: master.status,
        hourly_rate: master.salaryType === 'hourly' ? master.baseSalaryOrRate : null,
        monthly_salary: master.salaryType === 'monthly' ? master.baseSalaryOrRate : null,
        // Email is intentionally omitted — permanently immutable for existing employees.
      });
      setMaster(updated);
      setFirstName(updated.firstName ?? nextFirst);
      setLastName(updated.lastName ?? nextLast);
      setProfile((prev) =>
        prev
          ? {
              ...prev,
              full_name: updated.fullName,
            }
          : prev,
      );
      setEditing(false);
      void loadProfiles();
    } catch (reason: unknown) {
      const message =
        reason instanceof ApiClientError
          ? reason.message
          : reason instanceof Error
            ? reason.message
            : t('common.error');
      setError(message);
    } finally {
      setSaving(false);
    }
  };

  const cancelEdit = () => {
    if (master) {
      setFirstName(master.firstName ?? master.fullName.split(' ')[0] ?? '');
      setLastName(
        master.lastName ?? master.fullName.split(' ').slice(1).join(' ') ?? '',
      );
    }
    setEditing(false);
    setError(null);
  };

  return (
    <EmployeeSessionProvider
      key={`${employeeNumber}:${batchReview?.documentId || 'published'}`}
    >
      <EmployeeWorkspaceProvider value={scope}>
        <section className="accountant-employee-workspace">
          <header className="accountant-employee-workspace__header">
            <IconBackButton to={backPath} ariaLabel={backAria} title={backAria} />
            <div className="accountant-employee-workspace__identity">
              {editing ? (
                <div className="accountant-employee-workspace__edit-grid">
                  <label>
                    <span>{t('accountant.employees.fieldFirstName')}</span>
                    <input
                      value={firstName}
                      onChange={(event) => setFirstName(event.target.value)}
                      autoComplete="given-name"
                      disabled={saving}
                    />
                  </label>
                  <label>
                    <span>{t('accountant.employees.fieldLastName')}</span>
                    <input
                      value={lastName}
                      onChange={(event) => setLastName(event.target.value)}
                      autoComplete="family-name"
                      disabled={saving}
                    />
                  </label>
                  <label className="accountant-employee-workspace__email">
                    <span>{t('accountant.employees.fieldEmail')}</span>
                    <input
                      type="email"
                      value={master?.email ?? ''}
                      readOnly
                      disabled
                      aria-readonly="true"
                      title={t('accountant.workspace.emailReadonly')}
                    />
                  </label>
                </div>
              ) : (
                <div>
                  <h1>{displayName || t('common.loading')}</h1>
                  <p>
                    {profile
                      ? t('accountant.workspace.employeeNumber', {
                          number: profile.employee_number,
                        })
                      : t('accountant.workspace.loading')}
                    {master?.email ? ` · ${master.email}` : ''}
                  </p>
                </div>
              )}
            </div>
            {!batchReview && (
              <div className="accountant-employee-workspace__profile-actions">
                {editing ? (
                  <>
                    <button
                      type="button"
                      className="icon-back-button"
                    aria-label={t('accountant.workspace.saveProfile')}
                    title={t('accountant.workspace.saveProfile')}
                    disabled={saving}
                    onClick={() => void saveProfile()}
                  >
                    <Check size={18} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    className="icon-back-button"
                    aria-label={t('common.cancel')}
                    title={t('common.cancel')}
                    disabled={saving}
                    onClick={cancelEdit}
                  >
                    <X size={18} aria-hidden="true" />
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="icon-back-button"
                  aria-label={t('accountant.workspace.editProfile')}
                  title={t('accountant.workspace.editProfile')}
                  disabled={!master}
                  onClick={() => setEditing(true)}
                >
                  <Pencil size={16} aria-hidden="true" />
                </button>
              )}
              </div>
            )}
          </header>

          {error && (
            <p className="chat-panel__error" role="alert">
              {error}
            </p>
          )}

          {!batchReview && (
            <nav
              className="employee-review-tabs accountant-employee-workspace__tabs"
              aria-label={t('accountant.workspace.tabsLabel')}
            >
              <NavLink
                to={`${basePath}/documents${reviewQuery}`}
                className={({ isActive }) =>
                  `employee-review-tabs__tab ${isActive ? 'is-active' : ''}`
                }
              >
                {t('employee.navigation.documents')}
              </NavLink>
              <NavLink
                to={`${basePath}/payslips${reviewQuery}`}
                className={({ isActive }) =>
                  `employee-review-tabs__tab ${isActive ? 'is-active' : ''}`
                }
              >
                {t('employee.navigation.payslips')}
              </NavLink>
              <NavLink
                to={`${basePath}/chat${reviewQuery}`}
                className={({ isActive }) =>
                  `employee-review-tabs__tab ${isActive ? 'is-active' : ''}`
                }
              >
                {t('employee.navigation.chat')}
              </NavLink>
            </nav>
          )}

          <Outlet />
        </section>
      </EmployeeWorkspaceProvider>
    </EmployeeSessionProvider>
  );
}
