import { useCallback, useEffect, useState } from 'react';
import { Link, useBlocker, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { Card } from '../../components/ui/Card';
import { EmptyState, LoadingOverlay, useConfirmDialog } from '../../components/ui/Dialog';
import {
  EmployeeForm,
  toWritePayload,
  type EmployeeFormValues,
} from '../../features/accountant/EmployeeForm';
import { useUnsavedChanges } from '../../features/accountant/UnsavedChangesGuard';
import { getAccountantErrorMessage } from '../../i18n/accountantLabels';
import { ApiClientError } from '../../services/api';
import { employeesService } from '../../services/employees';

export function EditEmployeePage() {
  const { t } = useTranslation();
  const { employeeNumber } = useParams<{ employeeNumber: string }>();
  const navigate = useNavigate();
  const { confirm } = useConfirmDialog();
  const { setDirty, isDirty, confirmIfDirty } = useUnsavedChanges();
  const [initial, setInitial] = useState<Partial<EmployeeFormValues> | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    return () => setDirty(false);
  }, [setDirty]);

  const blocker = useBlocker(isDirty);

  useEffect(() => {
    if (blocker.state !== 'blocked') return;
    void (async () => {
      const ok = await confirmIfDirty();
      if (ok) {
        setDirty(false);
        blocker.proceed();
      } else {
        blocker.reset();
      }
    })();
  }, [blocker, confirmIfDirty, setDirty]);

  const onDirtyChange = useCallback(
    (dirty: boolean) => {
      setDirty(dirty);
    },
    [setDirty],
  );

  useEffect(() => {
    if (!employeeNumber) return;
    void (async () => {
      setLoading(true);
      try {
        const row = await employeesService.getByNumber(employeeNumber);
        if (!row) {
          setInitial(null);
          return;
        }
        setInitial({
          employeeNumber: row.employeeNumber,
          firstName: row.firstName ?? row.fullName.split(' ')[0] ?? '',
          lastName: row.lastName ?? row.fullName.split(' ').slice(1).join(' ') ?? '',
          email: row.email,
          nationalId: '',
          employmentType: row.employmentType,
          salaryType: row.salaryType,
          baseSalaryOrRate: String(row.baseSalaryOrRate || ''),
          contractStartDate: row.contractStartDate?.slice(0, 10) ?? '',
          profileIncomplete: Boolean(row.profileIncomplete),
        });
      } catch (err) {
        const message =
          err instanceof ApiClientError
            ? err.message
            : getAccountantErrorMessage('loadFailed', t);
        setError(message);
      } finally {
        setLoading(false);
      }
    })();
  }, [employeeNumber, t]);

  return (
    <PortalPage
      title={t('accountant.employees.editTitle', { number: employeeNumber ?? '' })}
      description={t('accountant.employees.editDescription')}
    >
      <div className="panel-relative">
        {loading && !initial && (
          <LoadingOverlay label={t('accountant.employees.loadingOne')} />
        )}
        {!loading && !initial ? (
          <EmptyState
            title={t('accountant.employees.notFoundTitle')}
            description={t('accountant.employees.notFoundDescription')}
            action={
              <Link to="/accountant/employees" className="btn btn--secondary">
                {t('accountant.employees.backToList')}
              </Link>
            }
          />
        ) : (
          initial && (
            <Card>
              <EmployeeForm
                mode="edit"
                initial={initial}
                submitting={submitting}
                error={error}
                onDirtyChange={onDirtyChange}
                onSubmit={async (values) => {
                  if (!employeeNumber) return;
                  const ok = await confirm({
                    title: t('accountant.employees.saveTitle'),
                    message: t('accountant.employees.saveMessage'),
                    confirmLabel: t('accountant.employees.saveConfirm'),
                    cancelLabel: t('common.cancel'),
                    variant: 'warning',
                  });
                  if (!ok) return;
                  setSubmitting(true);
                  setError(null);
                  try {
                    const payload = toWritePayload(values, 'edit');
                    if (!payload.national_id) {
                      delete payload.national_id;
                    }
                    await employeesService.update(employeeNumber, payload);
                    setDirty(false);
                    navigate(`/accountant/employees/${employeeNumber}`);
                  } catch (err) {
                    const message =
                      err instanceof ApiClientError
                        ? err.message
                        : getAccountantErrorMessage('saveFailed', t);
                    setError(message);
                  } finally {
                    setSubmitting(false);
                  }
                }}
                footer={
                  <Link
                    to={`/accountant/employees/${employeeNumber}`}
                    className="btn btn--secondary"
                    onClick={(event) => {
                      if (!isDirty) return;
                      event.preventDefault();
                      void (async () => {
                        const ok = await confirmIfDirty();
                        if (!ok) return;
                        setDirty(false);
                        navigate(`/accountant/employees/${employeeNumber}`);
                      })();
                    }}
                  >
                    {t('common.cancel')}
                  </Link>
                }
              />
            </Card>
          )
        )}
      </div>
    </PortalPage>
  );
}
