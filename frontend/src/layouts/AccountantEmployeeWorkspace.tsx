import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Link,
  NavLink,
  Outlet,
  useLocation,
  useParams,
  useSearchParams,
} from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Settings } from 'lucide-react';
import { EmployeeSessionProvider } from '../auth/EmployeeSessionContext';
import { IconBackButton } from '../components/ui/IconBackButton';
import {
  EmployeeWorkspaceProvider,
  type EmployeeWorkspaceScope,
} from '../features/employee/EmployeeWorkspaceContext';
import { useAppLocale } from '../hooks/useAppLocale';
import { createAccountantEmployeeWorkspaceApi } from '../services/accountantEmployeeWorkspace';
import { employeesService } from '../services/employees';
import type { EmployeeMe } from '../services/employeePortal';
import type { EmployeeRecord } from '../types/employee';
import './AccountantEmployeeWorkspace.css';

export function AccountantEmployeeWorkspaceLayout() {
  const { t } = useTranslation();
  const { dir } = useAppLocale();
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
  const basePath = `/accountant/employees/${encodeURIComponent(employeeNumber)}/workspace`;
  const isDocumentsSection =
    location.pathname === `${basePath}/documents` ||
    location.pathname.endsWith('/workspace/documents');
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

  useEffect(() => {
    let active = true;
    setError(null);
    void Promise.all([api.me(), employeesService.getByNumber(employeeNumber)])
      .then(([me, record]) => {
        if (!active) return;
        setProfile(me);
        setMaster(record);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : t('common.error'));
        }
      });
    return () => {
      active = false;
    };
  }, [api, employeeNumber, location.pathname, t]);

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

  return (
    <EmployeeSessionProvider
      key={`${employeeNumber}:${batchReview?.documentId || 'published'}`}
    >
      <EmployeeWorkspaceProvider value={scope}>
        <section className="accountant-employee-workspace">
          <header className="accountant-employee-workspace__header" dir="rtl">
            <IconBackButton to={backPath} ariaLabel={backAria} title={backAria} />
            <div className="accountant-employee-workspace__identity">
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
            </div>
            {!batchReview && (
              <div className="accountant-employee-workspace__profile-actions">
                <Link
                  to={`${basePath}/settings`}
                  className="icon-back-button"
                  aria-label={t('accountant.workspace.openSettings')}
                  title={t('accountant.workspace.openSettings')}
                >
                  <Settings size={16} aria-hidden="true" />
                </Link>
              </div>
            )}
          </header>

          {error && (
            <p className="chat-panel__error" role="alert">
              {error}
            </p>
          )}

          {!batchReview && isDocumentsSection ? (
            <div className="accountant-employee-workspace__page-heading" dir="rtl">
              <h2 className="accountant-employee-workspace__page-title">
                {t('accountant.workspace.documentsTitle', {
                  name: displayName || t('common.emDash'),
                })}
              </h2>
              <div id="accountant-doc-page-status-host" />
            </div>
          ) : null}

          {!batchReview && (
            <div
              className={`accountant-employee-workspace__section-nav${
                isDocumentsSection ? ' is-documents' : ''
              }`}
            >
              <nav
                className="employee-review-tabs accountant-employee-workspace__tabs accountant-employee-workspace__tabs--primary"
                aria-label={t('accountant.workspace.tabsLabel')}
                dir="rtl"
              >
                <NavLink
                  to={`${basePath}/documents${reviewQuery}`}
                  className={({ isActive }) =>
                    `employee-review-tabs__tab ${isActive ? 'is-active' : ''}`
                  }
                >
                  {t('accountant.workspace.navDocuments')}
                </NavLink>
                <NavLink
                  to={`${basePath}/payslips${reviewQuery}`}
                  className={({ isActive }) =>
                    `employee-review-tabs__tab ${isActive ? 'is-active' : ''}`
                  }
                >
                  {t('accountant.workspace.navPayslips')}
                </NavLink>
                <NavLink
                  to={`${basePath}/chat${reviewQuery}`}
                  className={({ isActive }) =>
                    `employee-review-tabs__tab ${isActive ? 'is-active' : ''}`
                  }
                >
                  {t('accountant.workspace.navChat')}
                </NavLink>
              </nav>

              <div dir={dir}>
                <Outlet />
              </div>
            </div>
          )}

          {batchReview ? (
            <div dir={dir}>
              <Outlet />
            </div>
          ) : null}
        </section>
      </EmployeeWorkspaceProvider>
    </EmployeeSessionProvider>
  );
}
