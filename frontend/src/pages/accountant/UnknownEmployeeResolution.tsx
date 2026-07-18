import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../../auth/AuthContext';
import { PortalPage } from '../../components/PortalPage';
import { EmptyState } from '../../components/ui/Dialog';
import { useBatchNavigationGuard } from '../../features/accountant/BatchNavigationGuard';
import { batchService } from '../../services/batch';
import { employeesService } from '../../services/employees';
import type { EmployeeRecord } from '../../types/employee';
import './UnknownEmployeeResolution.css';

type ResolutionAction = 'create' | 'search' | 'edit_id' | 'ignore';

type CreateValues = {
  employeeNumber: string;
  firstName: string;
  lastName: string;
  nationalId: string;
  email: string;
  company: string;
  department: string;
};

export function UnknownEmployeeResolutionPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { session } = useAuth();
  const { jobId = '', itemId = '' } = useParams<{ jobId: string; itemId: string }>();
  const batch = useBatchNavigationGuard();
  const [action, setAction] = useState<ResolutionAction>('search');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<EmployeeRecord[]>([]);
  const [nationalId, setNationalId] = useState('');
  const [createValues, setCreateValues] = useState<CreateValues>({
    employeeNumber: '',
    firstName: '',
    lastName: '',
    nationalId: '',
    email: '',
    company: session?.user.organizationId || '',
    department: '',
  });

  const item = useMemo(
    () => batch.activeJob?.items?.find((row) => row.id === itemId) ?? null,
    [batch.activeJob?.items, itemId],
  );

  const finish = async () => {
    await batch.refreshBatch();
    navigate('/accountant/bulk-upload');
  };

  const resolve = async (
    payload:
      | { action: 'ignore' }
      | { action: 'edit_national_id'; national_id: string }
      | { action: 'attach_employee'; employee_number: string },
  ) => {
    setBusy(true);
    setError(null);
    try {
      await batchService.resolveItem(jobId, itemId, payload);
      await finish();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('common.error'));
    } finally {
      setBusy(false);
    }
  };

  const search = async () => {
    setBusy(true);
    setError(null);
    try {
      setResults(
        await employeesService.list({
          q: query.trim() || undefined,
          includeDisabled: false,
        }),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('common.error'));
    } finally {
      setBusy(false);
    }
  };

  const createEmployee = async () => {
    const values = Object.values(createValues);
    if (values.some((value) => !value.trim())) {
      setError(t('accountant.unknown.required'));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await employeesService.create({
        employee_number: createValues.employeeNumber.trim(),
        first_name: createValues.firstName.trim(),
        last_name: createValues.lastName.trim(),
        national_id: createValues.nationalId.trim(),
        email: createValues.email.trim(),
        employment_type: 'full_time',
        salary_type: 'monthly',
        profile_incomplete: false,
        metadata: {
          company: createValues.company.trim(),
          department: createValues.department.trim(),
          source: 'batch_unknown_employee_resolution',
        },
      });
      await batchService.resolveItem(jobId, itemId, {
        action: 'attach_employee',
        employee_number: created.employeeNumber,
      });
      await finish();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('common.error'));
    } finally {
      setBusy(false);
    }
  };

  if (!item && batch.activeJob && batch.activeJob.id === jobId) {
    return (
      <PortalPage
        title={t('accountant.unknown.title')}
        description={t('accountant.unknown.description')}
      >
        <EmptyState
          title={t('accountant.unknown.notFound')}
          action={
            <button className="btn btn--secondary" onClick={() => navigate('/accountant/bulk-upload')}>
              {t('accountant.workspace.back')}
            </button>
          }
        />
      </PortalPage>
    );
  }

  return (
    <PortalPage
      title={t('accountant.unknown.title')}
      description={t('accountant.unknown.description')}
    >
      <div className="unknown-resolution">
        <button
          type="button"
          className="btn btn--ghost"
          onClick={() => navigate('/accountant/bulk-upload')}
        >
          ← {t('accountant.workspace.back')}
        </button>

        <div className="unknown-resolution__summary">
          <strong>
            {item
              ? t('accountant.bulk.progress.slip', { value: item.slip_index + 1 })
              : t('common.loading')}
          </strong>
          <span>{item?.national_id_masked || t('common.emDash')}</span>
        </div>

        <div className="unknown-resolution__actions" role="tablist">
          {(
            [
              ['create', 'accountant.unknown.create'],
              ['search', 'accountant.unknown.search'],
              ['edit_id', 'accountant.unknown.editId'],
              ['ignore', 'accountant.unknown.ignore'],
            ] as Array<[ResolutionAction, string]>
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={action === id}
              className={`btn ${action === id ? 'btn--primary' : 'btn--secondary'}`}
              onClick={() => setAction(id)}
            >
              {t(label)}
            </button>
          ))}
        </div>

        {error && <p className="chat-panel__error">{error}</p>}

        {action === 'search' && (
          <section className="unknown-resolution__panel">
            <label>
              <span>{t('accountant.unknown.searchLabel')}</span>
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={t('accountant.unknown.searchPlaceholder')}
              />
            </label>
            <button type="button" className="btn btn--primary" disabled={busy} onClick={() => void search()}>
              {t('common.search')}
            </button>
            <div className="unknown-resolution__results">
              {results.map((employee) => (
                <button
                  key={employee.employeeNumber}
                  type="button"
                  className="unknown-resolution__employee"
                  disabled={busy}
                  onClick={() =>
                    void resolve({
                      action: 'attach_employee',
                      employee_number: employee.employeeNumber,
                    })
                  }
                >
                  <strong>{employee.fullName}</strong>
                  <span>#{employee.employeeNumber}</span>
                  <span>{employee.nationalIdMasked || t('common.emDash')}</span>
                </button>
              ))}
            </div>
          </section>
        )}

        {action === 'edit_id' && (
          <section className="unknown-resolution__panel">
            <label>
              <span>{t('accountant.unknown.nationalId')}</span>
              <input value={nationalId} onChange={(event) => setNationalId(event.target.value)} />
            </label>
            <button
              type="button"
              className="btn btn--primary"
              disabled={busy || !nationalId.trim()}
              onClick={() =>
                void resolve({
                  action: 'edit_national_id',
                  national_id: nationalId.trim(),
                })
              }
            >
              {t('accountant.unknown.retryMatch')}
            </button>
          </section>
        )}

        {action === 'ignore' && (
          <section className="unknown-resolution__panel">
            <p>{t('accountant.unknown.ignoreDescription')}</p>
            <button
              type="button"
              className="btn btn--danger"
              disabled={busy}
              onClick={() => void resolve({ action: 'ignore' })}
            >
              {t('accountant.unknown.ignore')}
            </button>
          </section>
        )}

        {action === 'create' && (
          <section className="unknown-resolution__panel unknown-resolution__form">
            {(
              [
                ['employeeNumber', 'accountant.unknown.employeeNumber'],
                ['firstName', 'accountant.unknown.firstName'],
                ['lastName', 'accountant.unknown.lastName'],
                ['nationalId', 'accountant.unknown.nationalId'],
                ['email', 'accountant.unknown.email'],
                ['company', 'accountant.unknown.company'],
                ['department', 'accountant.unknown.department'],
              ] as Array<[keyof CreateValues, string]>
            ).map(([key, label]) => (
              <label key={key}>
                <span>{t(label)}</span>
                <input
                  type={key === 'email' ? 'email' : 'text'}
                  value={createValues[key]}
                  readOnly={key === 'company'}
                  required
                  onChange={(event) =>
                    setCreateValues((previous) => ({
                      ...previous,
                      [key]: event.target.value,
                    }))
                  }
                />
              </label>
            ))}
            <button
              type="button"
              className="btn btn--primary"
              disabled={busy}
              onClick={() => void createEmployee()}
            >
              {t('accountant.unknown.createAndAttach')}
            </button>
          </section>
        )}
      </div>
    </PortalPage>
  );
}
