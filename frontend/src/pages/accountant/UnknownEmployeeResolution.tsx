import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../../auth/AuthContext';
import { PortalPage } from '../../components/PortalPage';
import { EmptyState } from '../../components/ui/Dialog';
import { TruncatedText } from '../../components/ui/TruncatedText';
import { useBatchNavigationGuard } from '../../features/accountant/BatchNavigationGuard';
import { FIELD_MAX_LENGTH, validatePersonName } from '../../lib/employee/field-text';
import { validateNationalId } from '../../lib/employee/israeli-id';
import {
  EMAIL_MAX_LENGTH,
  FREE_TEXT_MAX_LENGTH,
  clampFreeTextInput,
  validateEmailFormat,
} from '../../lib/validation';
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
    const first = validatePersonName(createValues.firstName);
    if (!first.ok) {
      setError(
        t(
          first.code === 'digits'
            ? 'common.validation.nameNoDigits'
            : first.code === 'max_length'
              ? 'common.validation.nameMaxLength'
              : 'common.validation.nameInvalid',
        ),
      );
      return;
    }
    const last = validatePersonName(createValues.lastName);
    if (!last.ok) {
      setError(
        t(
          last.code === 'digits'
            ? 'common.validation.nameNoDigits'
            : last.code === 'max_length'
              ? 'common.validation.nameMaxLength'
              : 'common.validation.nameInvalid',
        ),
      );
      return;
    }
    const emailResult = validateEmailFormat(createValues.email);
    if (!emailResult.ok) {
      setError(t('common.validation.invalidEmail'));
      return;
    }
    const nid = validateNationalId(createValues.nationalId);
    if (!nid.ok) {
      setError(
        t(
          nid.code === 'digits_only'
            ? 'common.validation.nationalIdDigits'
            : nid.code === 'length'
              ? 'common.validation.nationalIdLength'
              : 'common.validation.nationalIdChecksum',
        ),
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await employeesService.create({
        employee_number: clampFreeTextInput(
          createValues.employeeNumber.trim(),
          FREE_TEXT_MAX_LENGTH.identifier,
        ),
        first_name: first.value,
        last_name: last.value,
        national_id: nid.digits,
        email: emailResult.value,
        employment_type: 'full_time',
        salary_type: 'monthly',
        metadata: {
          company: clampFreeTextInput(createValues.company.trim(), FREE_TEXT_MAX_LENGTH.shortNote),
          department: clampFreeTextInput(
            createValues.department.trim(),
            FREE_TEXT_MAX_LENGTH.shortNote,
          ),
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
                maxLength={FREE_TEXT_MAX_LENGTH.searchQuery}
                value={query}
                onChange={(event) =>
                  setQuery(clampFreeTextInput(event.target.value, FREE_TEXT_MAX_LENGTH.searchQuery))
                }
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
                  <strong>
                    <TruncatedText>{employee.fullName}</TruncatedText>
                  </strong>
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
              <input
                value={nationalId}
                inputMode="numeric"
                maxLength={FIELD_MAX_LENGTH.nationalId}
                autoComplete="off"
                onChange={(event) =>
                  setNationalId(
                    event.target.value.replace(/\D/g, '').slice(0, FIELD_MAX_LENGTH.nationalId),
                  )
                }
              />
            </label>
            <button
              type="button"
              className="btn btn--primary"
              disabled={busy || !nationalId.trim()}
              onClick={() => {
                const nid = validateNationalId(nationalId);
                if (!nid.ok) {
                  setError(
                    t(
                      nid.code === 'digits_only'
                        ? 'common.validation.nationalIdDigits'
                        : nid.code === 'length'
                          ? 'common.validation.nationalIdLength'
                          : 'common.validation.nationalIdChecksum',
                    ),
                  );
                  return;
                }
                void resolve({
                  action: 'edit_national_id',
                  national_id: nid.digits,
                });
              }}
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
                  inputMode={key === 'nationalId' ? 'numeric' : undefined}
                  maxLength={
                    key === 'nationalId'
                      ? FIELD_MAX_LENGTH.nationalId
                      : key === 'firstName' || key === 'lastName'
                        ? FIELD_MAX_LENGTH.personName
                        : key === 'email'
                          ? EMAIL_MAX_LENGTH
                          : key === 'employeeNumber'
                            ? FREE_TEXT_MAX_LENGTH.identifier
                            : FREE_TEXT_MAX_LENGTH.shortNote
                  }
                  autoComplete="off"
                  onChange={(event) => {
                    let next = event.target.value;
                    if (key === 'nationalId') {
                      next = next.replace(/\D/g, '').slice(0, FIELD_MAX_LENGTH.nationalId);
                    } else if (key === 'email') {
                      next = next.slice(0, EMAIL_MAX_LENGTH);
                    } else if (key === 'firstName' || key === 'lastName') {
                      next = next.slice(0, FIELD_MAX_LENGTH.personName);
                    } else if (key === 'employeeNumber') {
                      next = clampFreeTextInput(next, FREE_TEXT_MAX_LENGTH.identifier);
                    } else {
                      next = clampFreeTextInput(next, FREE_TEXT_MAX_LENGTH.shortNote);
                    }
                    setCreateValues((previous) => ({
                      ...previous,
                      [key]: key === 'email' ? next : next,
                    }));
                  }}
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
