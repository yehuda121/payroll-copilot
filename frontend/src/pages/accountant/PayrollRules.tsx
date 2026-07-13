import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { Card } from '../../components/ui/Card';
import { DataTable } from '../../components/ui/DataTable';
import { EmptyState, LoadingOverlay, useConfirmDialog } from '../../components/ui/Dialog';
import { getAccountantErrorMessage } from '../../i18n/accountantLabels';
import { useAppLocale } from '../../hooks/useAppLocale';
import { formatDateTime } from '../../lib/formatLocale';
import { complianceService, type RuleFileContent } from '../../services/compliance';
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
  const [error, setError] = useState<string | null>(null);

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

  return (
    <PortalPage
      title={t('accountant.rules.title')}
      description={t('accountant.rules.description')}
    >
      {error && <p className="chat-panel__error">{error}</p>}
      <div className="panel-relative">
        {loading && <LoadingOverlay label={t('accountant.rules.loading')} />}
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
          <div className="accountant-toolbar">
            {!editing ? (
              <button type="button" className="btn btn--primary" onClick={() => void beginEdit()}>
                {t('accountant.rules.edit')}
              </button>
            ) : (
              <>
                <input
                  type="text"
                  placeholder={t('accountant.rules.reasonPlaceholder')}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  aria-label={t('accountant.rules.reasonAria')}
                  className="rule-reason-input"
                />
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={saving}
                  onClick={() => void save()}
                >
                  {saving ? t('common.saving') : t('accountant.rules.saveVersion')}
                </button>
                <button
                  type="button"
                  className="btn btn--secondary"
                  onClick={() => {
                    setEditing(false);
                    setDraft(selected.content);
                  }}
                >
                  {t('common.cancel')}
                </button>
              </>
            )}
          </div>
          <textarea
            className="rule-editor"
            value={draft}
            readOnly={!editing}
            onChange={(e) => setDraft(e.target.value)}
            rows={18}
            spellCheck={false}
            aria-label={t('accountant.rules.contentAria')}
            dir="ltr"
          />
          <h4>{t('accountant.rules.versionHistory')}</h4>
          {selected.versions.length === 0 ? (
            <EmptyState
              title={t('accountant.rules.noVersionsTitle')}
              description={t('accountant.rules.noVersionsDescription')}
            />
          ) : (
            <ul className="audit-list">
              {selected.versions.map((version) => (
                <li key={version.version_id}>
                  <div>
                    <strong>{version.version_id}</strong>
                    <div className="month-card__meta">
                      <span>{formatDateTime(version.created_at, locale)}</span>
                      <span>{version.reason}</span>
                      {version.previous_version_id && (
                        <span>
                          {t('accountant.rules.prevVersion', {
                            id: version.previous_version_id,
                          })}
                        </span>
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => void rollback(version.version_id)}
                  >
                    {t('accountant.rules.rollback')}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
    </PortalPage>
  );
}
