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
import {
  getAccountantErrorMessage,
  getEmployeeStatusLabel,
} from '../../i18n/accountantLabels';
import { ApiClientError } from '../../services/api';
import { employeesService } from '../../services/employees';
import type { EmployeeRecord } from '../../types/employee';
import { useEmployeeWorkspace } from '../../features/employee/EmployeeWorkspaceContext';
import { invalidateEmployeesListCache } from './EmployeeManagement';

/**
 * Accountant Employee Settings — single place for master-data edit and disable.
 */
export function EmployeeSettingsPage() {
  const { t } = useTranslation();
  const { employeeNumber: paramNumber } = useParams<{ employeeNumber: string }>();
  const { employeeNumber: workspaceNumber, basePath } = useEmployeeWorkspace();
  const employeeNumber = paramNumber || workspaceNumber;
  const navigate = useNavigate();
  const { confirm } = useConfirmDialog();
  const { setDirty, isDirty, confirmIfDirty } = useUnsavedChanges();
  const [record, setRecord] = useState<EmployeeRecord | null>(null);
  const [initial, setInitial] = useState<Partial<EmployeeFormValues> | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [disabling, setDisabling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

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

  const applyRecord = useCallback((row: EmployeeRecord) => {
    setRecord(row);
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
    });
  }, []);

  useEffect(() => {
    if (!employeeNumber) return;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const row = await employeesService.getByNumber(employeeNumber);
        if (!row) {
          setRecord(null);
          setInitial(null);
          return;
        }
        applyRecord(row);
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
  }, [applyRecord, employeeNumber, t]);

  const workspaceDocumentsPath = `${basePath}/documents`;

  const disableEmployee = async () => {
    if (!employeeNumber || !record || record.status === 'disabled') return;
    const ok = await confirm({
      title: t('accountant.employees.disableTitle'),
      message: t('accountant.employees.disableMessage'),
      confirmLabel: t('accountant.employees.disableConfirm'),
      cancelLabel: t('common.cancel'),
      variant: 'danger',
    });
    if (!ok) return;
    setDisabling(true);
    setActionError(null);
    try {
      const updated = await employeesService.disable(employeeNumber);
      invalidateEmployeesListCache();
      applyRecord(updated);
      setDirty(false);
    } catch (err) {
      const message =
        err instanceof ApiClientError
          ? err.message
          : getAccountantErrorMessage('disableFailed', t);
      setActionError(message);
    } finally {
      setDisabling(false);
    }
  };

  return (
    <PortalPage
      title={t('accountant.employees.settingsTitle', { number: employeeNumber ?? '' })}
      description={t('accountant.employees.settingsDescription')}
    >
      <div className="panel-relative employee-settings">
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
          initial &&
          record && (
            <div className="employee-settings__stack">
              <Card title={t('accountant.employees.settingsPersonalHeading')}>
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
                      const updated = await employeesService.update(employeeNumber, payload);
                      invalidateEmployeesListCache();
                      applyRecord(updated);
                      setDirty(false);
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
                      to={workspaceDocumentsPath}
                      className="btn btn--secondary"
                      onClick={(event) => {
                        if (!isDirty) return;
                        event.preventDefault();
                        void (async () => {
                          const ok = await confirmIfDirty();
                          if (!ok) return;
                          setDirty(false);
                          navigate(workspaceDocumentsPath);
                        })();
                      }}
                    >
                      {t('common.cancel')}
                    </Link>
                  }
                />
              </Card>

              <Card title={t('accountant.employees.settingsAccessHeading')}>
                {actionError && (
                  <p className="chat-panel__error" role="alert">
                    {actionError}
                  </p>
                )}
                <p className="employee-settings__status">
                  {t('accountant.employees.colStatus')}:{' '}
                  <strong>{getEmployeeStatusLabel(record.status, t)}</strong>
                </p>
                {record.status === 'disabled' ? (
                  <p className="employee-settings__hint">
                    {t('accountant.employees.settingsAlreadyDisabled')}
                  </p>
                ) : (
                  <button
                    type="button"
                    className="btn btn--danger"
                    disabled={disabling}
                    onClick={() => {
                      void disableEmployee();
                    }}
                  >
                    {disabling ? t('common.saving') : t('common.disable')}
                  </button>
                )}
              </Card>
            </div>
          )
        )}
      </div>
    </PortalPage>
  );
}
