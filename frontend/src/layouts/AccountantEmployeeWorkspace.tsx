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
import { EmployeeSessionProvider } from '../auth/EmployeeSessionContext';
import {
  EmployeeWorkspaceProvider,
  type EmployeeWorkspaceScope,
} from '../features/employee/EmployeeWorkspaceContext';
import { createAccountantEmployeeWorkspaceApi } from '../services/accountantEmployeeWorkspace';
import type { EmployeeMe } from '../services/employeePortal';
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
  const [error, setError] = useState<string | null>(null);
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

  useEffect(() => {
    let active = true;
    setError(null);
    void api
      .me()
      .then((result) => {
        if (active) setProfile(result);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : t('common.error'));
        }
      });
    return () => {
      active = false;
    };
  }, [api, t]);

  const scope = useMemo<EmployeeWorkspaceScope>(
    () => ({
      api,
      basePath,
      employeeNumber,
      employeeName: profile?.full_name,
      backPath,
      mode: 'accountant',
      batchReview,
    }),
    [api, backPath, basePath, batchReview, employeeNumber, profile?.full_name],
  );

  return (
    <EmployeeSessionProvider
      key={`${employeeNumber}:${batchReview?.documentId || 'published'}`}
    >
      <EmployeeWorkspaceProvider value={scope}>
        <section className="accountant-employee-workspace">
          <header className="accountant-employee-workspace__header">
            <Link to={backPath} className="btn btn--ghost">
              ←{' '}
              {batchReview
                ? t('accountant.bulk.review.backToBatch')
                : t('accountant.workspace.back')}
            </Link>
            <div>
              <h1>{profile?.full_name || t('common.loading')}</h1>
              <p>
                {profile
                  ? t('accountant.workspace.employeeNumber', {
                      number: profile.employee_number,
                    })
                  : t('accountant.workspace.loading')}
              </p>
            </div>
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
