import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { Card } from '../../components/ui/Card';
import { DataTable } from '../../components/ui/DataTable';
import { EmptyState, LoadingOverlay, ModalDialog, useConfirmDialog } from '../../components/ui/Dialog';
import {
  FormControl,
  FormField,
  FormInfoPanel,
  FormSection,
  FormShell,
  FormTextarea,
} from '../../components/ui/form/FormPrimitives';
import { PencilIcon, SparklesIcon } from '../../components/ui/icons';
import { getAccountantErrorMessage } from '../../i18n/accountantLabels';
import { useAppLocale } from '../../hooks/useAppLocale';
import { formatDateTime } from '../../lib/formatLocale';
import {
  complianceService,
  type LegalRuleDifference,
  type LegalUpdateCheckResult,
  type RuleFileContent,
} from '../../services/compliance';
import { FREE_TEXT_MAX_LENGTH, clampFreeTextInput } from '../../lib/validation';
import type { LegalRuleSummary } from '../../types';

export function PayrollRulesPage() {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const { confirm } = useConfirmDialog();
  const [rules, setRules] = useState<LegalRuleSummary[]>([]);
  const [selected, setSelected] = useState<RuleFileContent | null>(null);
  const [draft, setDraft] = useState('');
  const [reason, setReason] = useState('');
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [checkingLegal, setCheckingLegal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [legalCheck, setLegalCheck] = useState<LegalUpdateCheckResult | null>(null);
  const [selectedChangeIds, setSelectedChangeIds] = useState<Set<string>>(new Set());

  const loadList = async () => {
    setLoading(true);
    try {
      const list = await complianceService.listLegalRules();
      setRules(list);
      setError(null);
    } catch {
      setError(getAccountantErrorMessage('loadFailed', t));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openRule = async (filename: string) => {
    setEditing(false);
    try {
      const content = await complianceService.getLegalRule(filename);
      setSelected(content);
      setDraft(content.content);
      setReason('');
    } catch {
      setError(getAccountantErrorMessage('loadFailed', t));
    }
  };

  const beginEdit = async () => {
    const ok = await confirm({
      title: t('accountant.rules.editWarningTitle'),
      message: t('accountant.rules.editWarningMessage'),
      confirmLabel: t('accountant.rules.editWarningConfirm'),
      cancelLabel: t('common.cancel'),
      variant: 'danger',
    });
    if (ok) setEditing(true);
  };

  const save = async () => {
    if (!selected) return;
    if (reason.trim().length < 3) {
      setError(t('accountant.rules.reasonRequired'));
      return;
    }
    const ok = await confirm({
      title: t('accountant.rules.publishTitle'),
      message: t('accountant.rules.publishMessage', {
        filename: selected.filename,
        reason: reason.trim(),
      }),
      confirmLabel: t('accountant.rules.publishConfirm'),
      cancelLabel: t('common.cancel'),
      variant: 'warning',
    });
    if (!ok) return;
    setSaving(true);
    try {
      const updated = await complianceService.updateLegalRule(
        selected.filename,
        draft,
        reason.trim(),
      );
      setSelected(updated);
      setDraft(updated.content);
      setEditing(false);
      setReason('');
      await loadList();
      setError(null);
    } catch {
      setError(getAccountantErrorMessage('saveFailed', t));
    } finally {
      setSaving(false);
    }
  };

  const rollback = async (versionId: string) => {
    if (!selected) return;
    const ok = await confirm({
      title: t('accountant.rules.rollbackTitle'),
      message: t('accountant.rules.rollbackMessage', {
        filename: selected.filename,
        versionId,
      }),
      confirmLabel: t('accountant.rules.rollbackConfirm'),
      cancelLabel: t('common.cancel'),
      variant: 'danger',
    });
    if (!ok) return;
    const rollbackReason =
      reason.trim() || t('accountant.rules.rollbackReason', { versionId });
    setSaving(true);
    try {
      const updated = await complianceService.rollbackLegalRule(
        selected.filename,
        versionId,
        rollbackReason,
      );
      setSelected(updated);
      setDraft(updated.content);
      setEditing(false);
      await loadList();
    } catch {
      setError(getAccountantErrorMessage('saveFailed', t));
    } finally {
      setSaving(false);
    }
  };

  const closeLegalDialog = () => {
    setLegalCheck(null);
    setSelectedChangeIds(new Set());
  };

  const checkLegalUpdates = async () => {
    setCheckingLegal(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const result = await complianceService.checkLegalUpdates();
      if (result.status === 'up_to_date') {
        setSuccessMessage(t('accountant.rules.legalUpToDate'));
        setLegalCheck(null);
        return;
      }
      setLegalCheck(result);
      setSelectedChangeIds(
        new Set(result.effective_changes.filter((c) => c.selectable).map((c) => c.change_id)),
      );
    } catch {
      setError(t('accountant.rules.legalDiffFailed'));
    } finally {
      setCheckingLegal(false);
    }
  };

  const toggleChange = (changeId: string) => {
    setSelectedChangeIds((prev) => {
      const next = new Set(prev);
      if (next.has(changeId)) next.delete(changeId);
      else next.add(changeId);
      return next;
    });
  };

  const confirmLegalUpdates = async () => {
    if (!legalCheck) return;
    const selectedIds = [...selectedChangeIds];
    if (selectedIds.length === 0) {
      setSuccessMessage(t('accountant.rules.legalDiffNoneSelected'));
      closeLegalDialog();
      return;
    }
    setSaving(true);
    try {
      const applied = await complianceService.applyLegalUpdates({
        selected_change_ids: selectedIds,
        effective_changes: legalCheck.effective_changes,
        future_changes: legalCheck.future_changes,
      });
      const count = applied.created_versions?.length ?? 0;
      if (count === 0) {
        setSuccessMessage(t('accountant.rules.legalDiffNoneSelected'));
      } else {
        setSuccessMessage(t('accountant.rules.legalDiffApplied', { count }));
        await loadList();
      }
      closeLegalDialog();
    } catch {
      setError(t('accountant.rules.legalDiffFailed'));
    } finally {
      setSaving(false);
    }
  };

  const renderDifference = (change: LegalRuleDifference, selectable: boolean) => (
    <li key={change.change_id} className="stack-sm" style={{ listStyle: 'none' }}>
      <label className="stack-xs" style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
        {selectable ? (
          <input
            type="checkbox"
            checked={selectedChangeIds.has(change.change_id)}
            onChange={() => toggleChange(change.change_id)}
          />
        ) : null}
        <span className="stack-xs">
          <strong>
            {change.rule_name} ({change.rule_id}.{change.parameter_key})
          </strong>
          <span>
            {t('accountant.rules.legalDiffCurrent')}: {String(change.current_value ?? '—')}
          </span>
          <span>
            {t('accountant.rules.legalDiffProposed')}: {String(change.proposed_value ?? '—')}
          </span>
          <span>
            {t('accountant.rules.legalDiffSource')}: {change.legal_source}
          </span>
          <span>
            {t('accountant.rules.legalDiffEffective')}: {change.effective_date ?? '—'}
          </span>
          <span>{change.explanation}</span>
        </span>
      </label>
    </li>
  );

  return (
    <PortalPage
      title={t('accountant.rules.title')}
      description={t('accountant.rules.description')}
    >
      {error && <p className="chat-panel__error">{error}</p>}
      {successMessage && <p className="chat-panel__success">{successMessage}</p>}

      <div className="stack-sm" style={{ marginBottom: '1rem' }}>
        <button
          type="button"
          className="btn btn--primary"
          disabled={checkingLegal || saving}
          onClick={() => void checkLegalUpdates()}
        >
          {checkingLegal
            ? t('accountant.rules.checkingLegalUpdates')
            : t('accountant.rules.checkLegalUpdates')}
        </button>
      </div>

      <div className="panel-relative" aria-busy={loading}>
        {loading && rules.length === 0 && (
          <LoadingOverlay label={t('accountant.rules.loading')} />
        )}
        <DataTable<LegalRuleSummary & Record<string, unknown>>
          columns={[
            { key: 'filename', header: t('accountant.rules.colFile') },
            {
              key: 'rules_count',
              header: t('accountant.rules.colRules'),
              render: (row) => String(row.rules_count ?? row.rule_count ?? t('common.emDash')),
            },
            {
              key: 'version',
              header: t('accountant.rules.colVersion'),
              render: (row) => row.version || t('common.emDash'),
            },
            {
              key: 'actions',
              header: t('common.actions'),
              render: (row) => (
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => void openRule(row.filename)}
                >
                  {t('common.open')}
                </button>
              ),
            },
          ]}
          data={rules as Array<LegalRuleSummary & Record<string, unknown>>}
          emptyMessage={t('accountant.rules.empty')}
        />
      </div>

      {selected && (
        <Card title={selected.filename}>
          <FormShell
            aside={
              editing ? (
                <FormInfoPanel
                  tone="warning"
                  eyebrow={t('forms.info.tipEyebrow')}
                  title={t('forms.info.payrollRulesTitle')}
                  icon={<SparklesIcon size={14} aria-hidden="true" />}
                >
                  {t('forms.info.payrollRulesBody')}
                </FormInfoPanel>
              ) : null
            }
          >
            <FormSection>
              <div className="stack-sm">
                {!editing ? (
                  <button type="button" className="btn btn--secondary" onClick={() => void beginEdit()}>
                    <PencilIcon size={16} aria-hidden="true" />
                    {t('accountant.rules.edit')}
                  </button>
                ) : (
                  <>
                    <FormField label={t('accountant.rules.reasonPlaceholder')} htmlFor="rule-reason">
                      <FormControl
                        id="rule-reason"
                        value={reason}
                        aria-label={t('accountant.rules.reasonAria')}
                        onChange={(event) =>
                          setReason(clampFreeTextInput(event.target.value, FREE_TEXT_MAX_LENGTH))
                        }
                      />
                    </FormField>
                    <button
                      type="button"
                      className="btn btn--primary"
                      disabled={saving}
                      onClick={() => void save()}
                    >
                      {t('accountant.rules.saveVersion')}
                    </button>
                  </>
                )}
                <FormTextarea
                  value={draft}
                  readOnly={!editing}
                  aria-label={t('accountant.rules.contentAria')}
                  onChange={(event) => setDraft(event.target.value)}
                  rows={18}
                />
              </div>
            </FormSection>

            <FormSection title={t('accountant.rules.versionHistory')}>
              {selected.versions.length === 0 ? (
                <EmptyState
                  title={t('accountant.rules.noVersionsTitle')}
                  description={t('accountant.rules.noVersionsDescription')}
                />
              ) : (
                <ul className="stack-sm">
                  {selected.versions.map((version) => (
                    <li key={version.version_id} className="stack-xs">
                      <div>
                        <strong>{version.version_id}</strong>
                        <span> · {formatDateTime(version.created_at, locale)}</span>
                        {version.previous_version_id ? (
                          <span>
                            {' '}
                            · {t('accountant.rules.prevVersion', { id: version.previous_version_id })}
                          </span>
                        ) : null}
                      </div>
                      <div>{version.reason}</div>
                      <button
                        type="button"
                        className="btn btn--ghost"
                        disabled={saving}
                        onClick={() => void rollback(version.version_id)}
                      >
                        {t('accountant.rules.rollback')}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </FormSection>
          </FormShell>
        </Card>
      )}

      {legalCheck && (
        <ModalDialog
          title={t('accountant.rules.legalDiffTitle')}
          onClose={closeLegalDialog}
          wide
          footer={
            <>
              <button type="button" className="btn btn--ghost" onClick={closeLegalDialog}>
                {t('accountant.rules.legalDiffCancel')}
              </button>
              <button
                type="button"
                className="btn btn--primary"
                disabled={saving}
                onClick={() => void confirmLegalUpdates()}
              >
                {t('accountant.rules.legalDiffConfirm')}
              </button>
            </>
          }
        >
          <p>{t('accountant.rules.legalDiffIntro')}</p>
          <ul className="stack-md">
            {legalCheck.effective_changes.map((change) => renderDifference(change, true))}
          </ul>
          {legalCheck.future_changes.length > 0 ? (
            <>
              <h3>{t('accountant.rules.legalDiffFutureHeading')}</h3>
              <ul className="stack-md">
                {legalCheck.future_changes.map((change) => (
                  <li key={change.change_id} className="stack-xs" style={{ listStyle: 'none' }}>
                    <p>
                      {t('accountant.rules.legalDiffFutureNote', {
                        date: change.effective_date ?? '—',
                      })}
                    </p>
                    {renderDifference(change, false)}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </ModalDialog>
      )}
    </PortalPage>
  );
}
