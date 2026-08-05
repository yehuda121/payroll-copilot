import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useConfirmDialog } from '../../components/ui/Dialog';
import {
  RESET_EMPLOYEE_DATA_PHRASE,
  adminEmployeeResetService,
  type ResetEmployeeDataCounts,
} from '../../services/adminEmployeeReset';
import './admin-ai.css';

const COUNT_KEYS: (keyof ResetEmployeeDataCounts)[] = [
  'employees',
  'employee_user_bindings',
  'documents',
  'extractions',
  'validation_runs',
  'validation_findings',
  'vacations',
  'sick_leaves',
  'leave_idempotency',
  's3_objects',
  's3_orphan_prefix_objects',
  'redis_manual_review_items',
  'redis_batch_progress_jobs',
  'redis_guest_session_keys',
];

type Props = {
  onSuccess?: () => void;
};

export function AdminEmployeeResetPanel({ onSuccess }: Props) {
  const { t } = useTranslation();
  const { confirm } = useConfirmDialog();
  const [phrase, setPhrase] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [counts, setCounts] = useState<ResetEmployeeDataCounts | null>(null);
  const [organizationId, setOrganizationId] = useState<string | null>(null);

  const phraseMatches = phrase.trim() === RESET_EMPLOYEE_DATA_PHRASE;

  async function handleReset() {
    setError(null);
    if (!phraseMatches) {
      setError(t('admin.employeeReset.errorPhrase'));
      return;
    }

    const accepted = await confirm({
      title: t('admin.employeeReset.confirmTitle'),
      message: t('admin.employeeReset.confirmMessage'),
      confirmLabel: t('admin.employeeReset.confirmButton'),
      cancelLabel: t('common.cancel'),
      variant: 'danger',
    });
    if (!accepted) return;

    setBusy(true);
    try {
      const result = await adminEmployeeResetService.resetEmployeeData({
        confirmationPhrase: phrase.trim(),
        confirmDestruction: true,
      });
      setCounts(result.counts);
      setOrganizationId(result.organization_id);
      setPhrase('');
      onSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('admin.employeeReset.errorGeneric'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="admin-dashboard-section admin-employee-reset" aria-labelledby="admin-employee-reset-title">
      <header className="admin-dashboard-section__header">
        <h2 id="admin-employee-reset-title">{t('admin.employeeReset.title')}</h2>
        <p>{t('admin.employeeReset.description')}</p>
      </header>
      <div className="admin-dashboard-section__body">
        <div className="admin-ai-card admin-employee-reset__card">
          <p className="admin-employee-reset__warning" role="alert">
            {t('admin.employeeReset.warning')}
          </p>
          <p className="admin-ai-muted">{t('admin.employeeReset.preserves')}</p>
          <label className="admin-employee-reset__field">
            <span>{t('admin.employeeReset.phraseLabel', { phrase: RESET_EMPLOYEE_DATA_PHRASE })}</span>
            <input
              className="pc-form-control"
              type="text"
              autoComplete="off"
              spellCheck={false}
              value={phrase}
              disabled={busy}
              onChange={(event) => setPhrase(event.target.value)}
              placeholder={RESET_EMPLOYEE_DATA_PHRASE}
            />
          </label>
          <div className="admin-employee-reset__actions">
            <button
              type="button"
              className="btn btn--danger"
              disabled={busy || !phraseMatches}
              onClick={() => void handleReset()}
            >
              {busy ? t('admin.employeeReset.running') : t('admin.employeeReset.button')}
            </button>
          </div>
          {error ? (
            <p className="admin-employee-reset__error" role="alert">
              {error}
            </p>
          ) : null}
          {counts ? (
            <div className="admin-employee-reset__results">
              <h3>{t('admin.employeeReset.resultsTitle')}</h3>
              {organizationId ? (
                <p className="admin-ai-muted">
                  {t('admin.employeeReset.organizationId', { id: organizationId })}
                </p>
              ) : null}
              <ul>
                {COUNT_KEYS.map((key) => (
                  <li key={key}>
                    <span>{t(`admin.employeeReset.counts.${key}`)}</span>
                    <strong>{Number(counts[key] ?? 0).toLocaleString()}</strong>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
