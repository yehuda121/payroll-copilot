import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { ActionIconButton } from '../../components/ui/ActionIconButton';
import { DataTable, type DataTableColumn } from '../../components/ui/DataTable';
import { LoadingOverlay, ModalDialog, useConfirmDialog } from '../../components/ui/Dialog';
import { RefreshIcon, SettingsIcon, TrashIcon } from '../../components/ui/icons';
import { useToast } from '../../components/ui/Toast';
import {
  getLeaveListCache,
  leaveListCacheKey,
  readLeaveUiSession,
  setLeaveListCache,
  writeLeaveUiSession,
} from '../../lib/accountant/sick-leave-management-cache';
import {
  formatLeaveConfidence,
  formatLeaveDateTime,
  isBasicLeaveNotificationEmail,
  isLeaveEditDirty,
  isSickLeaveSettingsDirty,
  LEAVE_DEFAULT_BUCKET,
  leaveEditBaseline,
  sickLeaveSettingsBaseline,
  mapLeaveActionError,
  normalizeLeaveNotificationEmail,
  type LeaveEditForm,
  type SickLeaveSettingsForm,
} from '../../lib/accountant/leave-management-ui';
import { ApiClientError } from '../../services/api';
import {
  sickLeavesService,
  type SickLeaveRecord,
  type SickLeaveSettings,
} from '../../services/sickLeaves';
import './SickLeaves.css';

type Bucket =
  | typeof LEAVE_DEFAULT_BUCKET
  | 'current'
  | 'upcoming'
  | 'past'
  | 'pending_approval'
  | 'requires_attention'
  | 'approved';

const HARD_CODES = new Set([
  'MISSING_EMPLOYEE_EMAIL',
  'EMPLOYEE_NOT_FOUND',
  'EMPLOYEE_AMBIGUOUS',
  'MISSING_START_DATE',
  'MISSING_END_DATE',
  'INVALID_DATE',
  'END_BEFORE_START',
  'AMBIGUOUS_UPDATE',
  'AMBIGUOUS_CANCEL',
]);

const WARNING_CODES = new Set([
  'OVERLAP',
  'LOW_CONFIDENCE',
  'UPDATE_PROPOSED',
  'CANCEL_PROPOSED',
  'DUPLICATE_CONTENT',
]);

type LoadOptions = {
  /** Explicit refresh — keep rows visible, show subtle refreshing state. */
  force?: boolean;
};

function statusBadgeClass(status: string, codes: string[]): string {
  if (status === 'approved') return 'status-badge--passed';
  if (codes.some((c) => HARD_CODES.has(c)) || status === 'requires_attention') {
    return 'status-badge--critical';
  }
  if (codes.some((c) => WARNING_CODES.has(c))) return 'status-badge--warnings';
  if (status === 'pending_approval') return 'status-badge--warnings';
  return 'status-badge--neutral';
}

function rowSeverityClass(row: SickLeaveRecord): string {
  if (row.attentionCodes.some((c) => HARD_CODES.has(c))) return 'leave-row--error';
  if (row.attentionCodes.some((c) => WARNING_CODES.has(c))) return 'leave-row--warning';
  return '';
}

function attentionLabel(code: string, t: (k: string) => string): string {
  const key = `accountant.sickLeaves.attention.${code}`;
  const translated = t(key);
  return translated === key ? code : translated;
}

function employeeLabel(row: SickLeaveRecord): string {
  return row.extractedEmployeeName || row.extractedEmployeeEmail || '—';
}

type LeaveRow = SickLeaveRecord & Record<string, unknown>;

export function SickLeavesPage() {
  const { t, i18n } = useTranslation();
  const { confirm } = useConfirmDialog();
  const { showToast } = useToast();
  const session = readLeaveUiSession();
  const initialCacheKey = leaveListCacheKey(
    session.bucket,
    session.rangeStart,
    session.rangeEnd,
  );
  const initialCache = getLeaveListCache(initialCacheKey);

  const [settings, setSettings] = useState<SickLeaveSettings | null>(
    () => initialCache?.settings ?? null,
  );
  const [items, setItems] = useState<SickLeaveRecord[]>(() => initialCache?.items ?? []);
  const [bucket, setBucket] = useState<Bucket>((session.bucket as Bucket) || LEAVE_DEFAULT_BUCKET);
  const [rangeStart, setRangeStart] = useState(session.rangeStart);
  const [rangeEnd, setRangeEnd] = useState(session.rangeEnd);
  const [loading, setLoading] = useState(() => !initialCache);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [detail, setDetail] = useState<SickLeaveRecord | null>(null);
  const [editBaseline, setEditBaseline] = useState<LeaveEditForm | null>(null);
  const [unsavedOpen, setUnsavedOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsForm, setSettingsForm] = useState<SickLeaveSettingsForm>({
    notificationEmail: '',
    notifyOnNewSickLeave: true,
    notifyOnSickLeaveErrorOrAttention: true,
  });
  const [settingsBaseline, setSettingsBaseline] = useState<SickLeaveSettingsForm | null>(null);
  const [settingsEmailError, setSettingsEmailError] = useState<string | null>(null);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [manualForm, setManualForm] = useState({
    employeeEmail: '',
    employeeName: '',
    startDate: '',
    endDate: '',
    notes: '',
  });
  const [editForm, setEditForm] = useState<LeaveEditForm>({
    employeeEmail: '',
    employeeName: '',
    startDate: '',
    endDate: '',
  });
  const [saving, setSaving] = useState(false);
  const [pageLoadedAt] = useState(() => new Date().toISOString());
  const selectAllRef = useRef<HTMLInputElement | null>(null);
  const requestSequence = useRef(0);

  const dateLocale = i18n.language?.startsWith('he')
    ? 'he-IL'
    : i18n.language?.startsWith('ar')
      ? 'ar'
      : undefined;

  useEffect(() => {
    writeLeaveUiSession({ bucket, rangeStart, rangeEnd });
  }, [bucket, rangeStart, rangeEnd]);

  const friendlyError = useCallback(
    (err: unknown, options?: { blockedApproval?: boolean }) =>
      mapLeaveActionError(err, t('accountant.sickLeaves.toastActionFailed'), {
        blockedApproval: options?.blockedApproval
          ? t('accountant.sickLeaves.toastApproveBlocked')
          : undefined,
      }),
    [t],
  );

  const load = useCallback(
    async (options: LoadOptions = {}) => {
      const cacheKey = leaveListCacheKey(bucket, rangeStart, rangeEnd);
      const cached = getLeaveListCache(cacheKey);
      if (cached) {
        setItems(cached.items);
        if (cached.settings) setSettings(cached.settings);
      }

      const requestId = ++requestSequence.current;
      setLoadError(null);
      if (!cached) {
        setLoading(true);
      } else {
        setRefreshing(true);
      }

      const settingsResult = await sickLeavesService.getSettings().then(
        (value) => ({ ok: true as const, value }),
        (err: unknown) => ({ ok: false as const, err }),
      );
      const listResult = await sickLeavesService
        .list({
          bucket,
          rangeStart: rangeStart || undefined,
          rangeEnd: rangeEnd || undefined,
        })
        .then(
          (value) => ({ ok: true as const, value }),
          (err: unknown) => ({ ok: false as const, err }),
        );

      if (requestId !== requestSequence.current) return;

      const errors: string[] = [];
      let nextSettings = cached?.settings ?? null;
      let nextItems = cached?.items ?? [];

      if (settingsResult.ok) {
        nextSettings = settingsResult.value;
        setSettings(settingsResult.value);
      } else {
        console.error('Leave settings load failed', settingsResult.err);
        if (!cached?.settings) {
          setSettings(null);
          errors.push(friendlyError(settingsResult.err));
        } else if (options.force) {
          showToast({ tone: 'error', message: friendlyError(settingsResult.err) });
        }
      }

      if (listResult.ok) {
        nextItems = listResult.value;
        setItems(listResult.value);
        setSelected(new Set());
        try {
          await sickLeavesService.markSeen({
            sickLeaveIds: listResult.value.map((row) => row.id),
            seenBefore: pageLoadedAt,
          });
        } catch (err) {
          console.error('Leave mark-seen failed', err);
        }
      } else {
        console.error('Leave list load failed', listResult.err);
        if (!cached?.items?.length) {
          setItems([]);
          errors.push(friendlyError(listResult.err));
        } else {
          showToast({ tone: 'error', message: friendlyError(listResult.err) });
        }
      }

      if (settingsResult.ok || listResult.ok) {
        setLeaveListCache(cacheKey, {
          items: listResult.ok ? listResult.value : nextItems,
          settings: settingsResult.ok ? settingsResult.value : nextSettings,
        });
      }

      setLoadError(errors[0] ?? null);
      setLoading(false);
      setRefreshing(false);
    },
    [bucket, rangeStart, rangeEnd, pageLoadedAt, friendlyError, showToast],
  );

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!detail) {
      setEditBaseline(null);
      setUnsavedOpen(false);
      return;
    }
    const baseline = leaveEditBaseline(detail);
    setEditForm(baseline);
    setEditBaseline(baseline);
  }, [detail]);

  const dirty = Boolean(editBaseline && isLeaveEditDirty(editForm, editBaseline));
  const settingsDirty = Boolean(
    settingsBaseline && isSickLeaveSettingsDirty(settingsForm, settingsBaseline),
  );

  const openSettings = () => {
    if (!settings) return;
    const baseline = sickLeaveSettingsBaseline(settings);
    setSettingsForm(baseline);
    setSettingsBaseline(baseline);
    setSettingsEmailError(null);
    setSettingsOpen(true);
  };

  const closeSettings = () => {
    setSettingsOpen(false);
    setSettingsEmailError(null);
  };

  const saveSettings = async () => {
    if (!settingsBaseline || !settingsDirty) return;
    if (!isBasicLeaveNotificationEmail(settingsForm.notificationEmail)) {
      setSettingsEmailError(t('accountant.sickLeaves.invalidNotificationEmail'));
      return;
    }
    setSettingsEmailError(null);
    setSettingsSaving(true);
    try {
      const next = await sickLeavesService.patchPreferences({
        notificationEmail: normalizeLeaveNotificationEmail(settingsForm.notificationEmail) || null,
        notifyOnNewSickLeave: settingsForm.notifyOnNewSickLeave,
        notifyOnSickLeaveErrorOrAttention: settingsForm.notifyOnSickLeaveErrorOrAttention,
      });
      setSettings(next);
      const baseline = sickLeaveSettingsBaseline(next);
      setSettingsForm(baseline);
      setSettingsBaseline(baseline);
      const cacheKey = leaveListCacheKey(bucket, rangeStart, rangeEnd);
      const cached = getLeaveListCache(cacheKey);
      setLeaveListCache(cacheKey, {
        items: cached?.items ?? items,
        settings: next,
      });
      showToast({ tone: 'success', message: t('accountant.sickLeaves.toastSettingsSaved') });
      closeSettings();
    } catch (err) {
      console.error('Leave settings save failed', err);
      showToast({ tone: 'error', message: friendlyError(err) });
    } finally {
      setSettingsSaving(false);
    }
  };

  const buckets: Bucket[] = [
    LEAVE_DEFAULT_BUCKET,
    'current',
    'upcoming',
    'past',
    'pending_approval',
    'requires_attention',
    'approved',
  ];

  const selectableIds = useMemo(
    () =>
      items
        .filter(
          (row) =>
            row.reviewStatus === 'pending_approval' || row.reviewStatus === 'requires_attention',
        )
        .map((row) => row.id),
    [items],
  );

  const allSelectableSelected =
    selectableIds.length > 0 && selected.size === selectableIds.length;

  useEffect(() => {
    const el = selectAllRef.current;
    if (!el) return;
    el.indeterminate = selected.size > 0 && selected.size < selectableIds.length;
  }, [selected, selectableIds]);

  const toggleAll = (event: MouseEvent) => {
    event.stopPropagation();
    if (allSelectableSelected) {
      setSelected(new Set());
      return;
    }
    setSelected(new Set(selectableIds));
  };

  const toggleOne = (id: string, event: MouseEvent) => {
    event.stopPropagation();
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const closeDetail = () => {
    setUnsavedOpen(false);
    setDetail(null);
  };

  const requestCloseDetail = () => {
    if (unsavedOpen) return;
    if (dirty) {
      setUnsavedOpen(true);
      return;
    }
    closeDetail();
  };

  const saveDetail = async (): Promise<boolean> => {
    if (!detail) return false;
    setSaving(true);
    try {
      const updated = await sickLeavesService.update(detail.id, {
        employeeEmail: editForm.employeeEmail.trim() || null,
        employeeName: editForm.employeeName.trim() || null,
        startDate: editForm.startDate || null,
        endDate: editForm.endDate || null,
      });
      const baseline = leaveEditBaseline(updated);
      setDetail(updated);
      setEditForm(baseline);
      setEditBaseline(baseline);
      showToast({ tone: 'success', message: t('accountant.sickLeaves.toastSaved') });
      await load({ force: true });
      return true;
    } catch (err) {
      console.error('Leave save failed', err);
      showToast({ tone: 'error', message: friendlyError(err) });
      return false;
    } finally {
      setSaving(false);
    }
  };

  const saveAndLeave = async () => {
    const ok = await saveDetail();
    if (ok) closeDetail();
    else setUnsavedOpen(false);
  };

  const discardAndLeave = () => {
    closeDetail();
  };

  const approveOne = async (row: SickLeaveRecord, confirmWarnings = false) => {
    try {
      await sickLeavesService.approve(row.id, confirmWarnings);
      showToast({ tone: 'success', message: t('accountant.sickLeaves.toastApproved') });
      await load({ force: true });
      if (detail?.id === row.id) closeDetail();
    } catch (err) {
      if (err instanceof ApiClientError && err.status === 409) {
        const ok = await confirm({
          title: t('accountant.sickLeaves.bulkConfirmTitle'),
          message: t('accountant.sickLeaves.approveWarningConfirm'),
          confirmLabel: t('common.confirm'),
          cancelLabel: t('common.cancel'),
          variant: 'warning',
        });
        if (ok) await approveOne(row, true);
        return;
      }
      console.error('Leave approve failed', err);
      showToast({
        tone: 'error',
        message: friendlyError(err, { blockedApproval: true }),
      });
    }
  };

  const deleteOne = async (row: SickLeaveRecord) => {
    const ok = await confirm({
      title: t('accountant.sickLeaves.deleteOneTitle'),
      message: t('accountant.sickLeaves.deleteOneMessage'),
      confirmLabel: t('common.delete'),
      cancelLabel: t('common.cancel'),
      variant: 'danger',
    });
    if (!ok) return;
    try {
      await sickLeavesService.deleteOrCancel(row.id);
      showToast({ tone: 'success', message: t('accountant.sickLeaves.toastDeleted') });
      closeDetail();
      await load({ force: true });
    } catch (err) {
      console.error('Leave delete failed', err);
      showToast({ tone: 'error', message: friendlyError(err) });
    }
  };

  const bulkApprove = async (confirmWarnings = false) => {
    const ids = [...selected];
    if (!ids.length) return;
    try {
      const result = await sickLeavesService.bulkApprove(ids, confirmWarnings);
      if (result.status === 'confirmation_required') {
        const warningItems = result.items.filter((item) => item.classification === 'WARNING');
        const ok = await confirm({
          title: t('accountant.sickLeaves.bulkConfirmTitle'),
          message: t('accountant.sickLeaves.bulkConfirmMessage', {
            count: warningItems.length,
            details: warningItems.map((item) => `${item.id}: ${item.codes.join(', ')}`).join('\n'),
          }),
          confirmLabel: t('common.confirm'),
          cancelLabel: t('common.cancel'),
          variant: 'warning',
        });
        if (ok) await bulkApprove(true);
        return;
      }
      showToast({ tone: 'success', message: t('accountant.sickLeaves.toastBulkApproved') });
      await load({ force: true });
    } catch (err) {
      console.error('Leave bulk approve failed', err);
      showToast({
        tone: 'error',
        message: friendlyError(err, { blockedApproval: true }),
      });
    }
  };

  const bulkDelete = async () => {
    const ids = [...selected];
    if (!ids.length) return;
    const ok = await confirm({
      title: t('accountant.sickLeaves.deleteConfirmTitle'),
      message: t('accountant.sickLeaves.deleteConfirmMessage', { count: ids.length }),
      confirmLabel: t('common.delete'),
      cancelLabel: t('common.cancel'),
      variant: 'danger',
    });
    if (!ok) return;
    try {
      await sickLeavesService.bulkDelete(ids);
      showToast({ tone: 'success', message: t('accountant.sickLeaves.toastBulkDeleted') });
      await load({ force: true });
    } catch (err) {
      console.error('Leave bulk delete failed', err);
      showToast({ tone: 'error', message: friendlyError(err) });
    }
  };

  const createManual = async () => {
    try {
      await sickLeavesService.createManual({
        employeeEmail: manualForm.employeeEmail || undefined,
        employeeName: manualForm.employeeName || undefined,
        startDate: manualForm.startDate,
        endDate: manualForm.endDate,
        notes: manualForm.notes || undefined,
      });
      setManualOpen(false);
      showToast({ tone: 'success', message: t('accountant.sickLeaves.toastSaved') });
      await load({ force: true });
    } catch (err) {
      console.error('Leave manual create failed', err);
      showToast({ tone: 'error', message: friendlyError(err) });
    }
  };

  const columns: DataTableColumn<LeaveRow>[] = [
    {
      key: 'select',
      header: (
        <input
          ref={selectAllRef}
          type="checkbox"
          className="leave-select-all"
          aria-label={t('accountant.sickLeaves.selectAll')}
          checked={allSelectableSelected}
          disabled={selectableIds.length === 0}
          onClick={toggleAll}
          onChange={() => undefined}
        />
      ),
      sortable: false,
      render: (row) => (
        <input
          type="checkbox"
          className="leave-select-row"
          aria-label={t('accountant.sickLeaves.selectRow')}
          checked={selected.has(row.id)}
          disabled={
            row.reviewStatus !== 'pending_approval' && row.reviewStatus !== 'requires_attention'
          }
          onClick={(event) => toggleOne(row.id, event)}
          onChange={() => undefined}
        />
      ),
    },
    {
      key: 'employee',
      header: t('accountant.sickLeaves.colEmployee'),
      sortValue: (row) => employeeLabel(row),
      render: (row) => (
        <span className={rowSeverityClass(row)}>
          {employeeLabel(row)}
          {row.attentionCodes.length > 0 ? (
            <span className="leave-codes">
              {row.attentionCodes.slice(0, 2).map((code) => (
                <span
                  key={code}
                  className={`status-badge ${
                    HARD_CODES.has(code) ? 'status-badge--critical' : 'status-badge--warnings'
                  }`}
                >
                  {attentionLabel(code, t)}
                </span>
              ))}
            </span>
          ) : null}
        </span>
      ),
    },
    {
      key: 'type',
      header: t('accountant.sickLeaves.colType'),
      sortValue: () => 'sickLeave',
      render: () => t('accountant.sickLeaves.typeSickLeave'),
    },
    {
      key: 'startDate',
      header: t('accountant.sickLeaves.colStart'),
      sortValue: (row) => row.startDate,
      render: (row) => row.startDate || '—',
    },
    {
      key: 'endDate',
      header: t('accountant.sickLeaves.colEnd'),
      sortValue: (row) => row.endDate,
      render: (row) => row.endDate || '—',
    },
    {
      key: 'reviewStatus',
      header: t('accountant.sickLeaves.colStatus'),
      sortValue: (row) => row.reviewStatus,
      render: (row) => (
        <span className={`status-badge ${statusBadgeClass(row.reviewStatus, row.attentionCodes)}`}>
          {t(`accountant.sickLeaves.status.${row.reviewStatus}`, {
            defaultValue: row.reviewStatus,
          })}
        </span>
      ),
    },
    {
      key: 'receivedAt',
      header: t('accountant.sickLeaves.colReceived'),
      sortValue: (row) => row.receivedAt || row.createdAt,
      render: (row) => (row.receivedAt || row.createdAt || '—').slice(0, 10),
    },
    {
      key: 'actions',
      header: t('accountant.sickLeaves.colActions'),
      sortable: false,
      render: (row) =>
        row.reviewStatus === 'pending_approval' || row.reviewStatus === 'requires_attention' ? (
          <button
            type="button"
            className="btn btn--secondary btn--sm"
            onClick={(event) => {
              event.stopPropagation();
              void approveOne(row);
            }}
          >
            {t('accountant.sickLeaves.approve')}
          </button>
        ) : null,
    },
  ];

  const tableRows = items as LeaveRow[];

  const originalConfidence =
    detail?.aiExtractionOriginal?.confidence ?? detail?.aiConfidence ?? null;
  const originalExplanation =
    detail?.aiExtractionOriginal?.explanation || detail?.aiExplanation || '';

  return (
    <PortalPage
      title={t('accountant.sickLeaves.title')}
      description={t('accountant.sickLeaves.description')}
    >
      {loading && items.length === 0 ? <LoadingOverlay label={t('common.loading')} /> : null}

      {loadError ? (
        <p className="sickLeaves-error" role="alert">
          {loadError}
        </p>
      ) : null}

      <div className="leave-toolbar">
        <div className="leave-toolbar__actions">
          <button type="button" className="btn btn--primary" onClick={() => setManualOpen(true)}>
            {t('accountant.sickLeaves.addManual')}
          </button>
          <ActionIconButton
            label={t('accountant.sickLeaves.settingsOpen')}
            icon={<SettingsIcon size={18} />}
            disabled={!settings}
            onClick={openSettings}
          />
          <ActionIconButton
            label={t('accountant.sickLeaves.refresh')}
            icon={<RefreshIcon size={18} className={refreshing ? 'leave-icon--spin' : undefined} />}
            disabled={refreshing}
            onClick={() => void load({ force: true })}
          />
        </div>
        <div className="leave-toolbar__filters">
          <label className="sickLeaves-filter-field sickLeaves-filter-field--status">
            <select
              className="sickLeaves-filter-control"
              value={bucket}
              aria-label={t('accountant.sickLeaves.filterStatus')}
              onChange={(e) => setBucket(e.target.value as Bucket)}
            >
              {buckets.map((key) => (
                <option key={key} value={key}>
                  {t(`accountant.sickLeaves.buckets.${key}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="sickLeaves-filter-field">
            {t('accountant.sickLeaves.rangeStart')}
            <input
              className="sickLeaves-filter-control"
              type="date"
              value={rangeStart}
              onChange={(e) => setRangeStart(e.target.value)}
            />
          </label>
          <label className="sickLeaves-filter-field">
            {t('accountant.sickLeaves.rangeEnd')}
            <input
              className="sickLeaves-filter-control"
              type="date"
              value={rangeEnd}
              onChange={(e) => setRangeEnd(e.target.value)}
            />
          </label>
          {selected.size > 0 ? (
            <div className="leave-bulk-actions">
              <button type="button" className="btn btn--primary" onClick={() => void bulkApprove()}>
                {t('accountant.sickLeaves.approveSelected')}
              </button>
              <button type="button" className="btn btn--danger" onClick={() => void bulkDelete()}>
                {t('accountant.sickLeaves.deleteSelected')}
              </button>
            </div>
          ) : null}
        </div>
      </div>

      <DataTable
        columns={columns}
        data={tableRows}
        sortable
        getRowKey={(row) => row.id}
        emptyMessage={t('accountant.sickLeaves.empty')}
        ariaLabel={t('accountant.sickLeaves.title')}
        onRowClick={(row) => setDetail(row)}
      />

      {detail ? (
        <ModalDialog
          title={employeeLabel(detail)}
          wide
          className="leave-request-dialog"
          closeLabel={t('common.close')}
          onClose={unsavedOpen ? () => undefined : requestCloseDetail}
          footer={
            <div className="leave-detail-footer">
              <ActionIconButton
                tone="danger"
                label={t('accountant.sickLeaves.deleteTooltip')}
                icon={<TrashIcon size={17} />}
                onClick={() => void deleteOne(detail)}
              />
              <span className="leave-detail-footer__spacer" />
              <button
                type="button"
                className="btn btn--secondary"
                onClick={requestCloseDetail}
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                className="btn btn--secondary"
                disabled={!dirty || saving}
                onClick={() => void saveDetail()}
              >
                {t('accountant.sickLeaves.saveChanges')}
              </button>
              {detail.reviewStatus === 'pending_approval' ||
              detail.reviewStatus === 'requires_attention' ? (
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => void approveOne(detail)}
                >
                  {t('accountant.sickLeaves.approve')}
                </button>
              ) : null}
            </div>
          }
        >
          <div className="leave-detail-modal">
            <p>
              <span
                className={`status-badge ${statusBadgeClass(detail.reviewStatus, detail.attentionCodes)}`}
              >
                {t(`accountant.sickLeaves.status.${detail.reviewStatus}`, {
                  defaultValue: detail.reviewStatus,
                })}
              </span>
            </p>

            {detail.attentionCodes.length > 0 ? (
              <ul className="leave-attention-list">
                {detail.attentionCodes.map((code) => (
                  <li key={code}>
                    <span
                      className={`status-badge ${
                        HARD_CODES.has(code) ? 'status-badge--critical' : 'status-badge--warnings'
                      }`}
                    >
                      {attentionLabel(code, t)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}

            {detail.overlapWith.length > 0 ? (
              <p>
                {t('accountant.sickLeaves.overlapWith')}: {detail.overlapWith.join(', ')}
              </p>
            ) : null}

            <div className="form-grid">
              <label>
                {t('accountant.sickLeaves.fieldName')}
                <input
                  value={editForm.employeeName}
                  onChange={(e) => setEditForm((f) => ({ ...f, employeeName: e.target.value }))}
                />
              </label>
              <label>
                {t('accountant.sickLeaves.fieldEmail')}
                <input
                  type="email"
                  value={editForm.employeeEmail}
                  onChange={(e) => setEditForm((f) => ({ ...f, employeeEmail: e.target.value }))}
                />
              </label>
              <label>
                {t('accountant.sickLeaves.fieldStartDate')}
                <input
                  type="date"
                  value={editForm.startDate}
                  onChange={(e) => setEditForm((f) => ({ ...f, startDate: e.target.value }))}
                />
              </label>
              <label>
                {t('accountant.sickLeaves.fieldEndDate')}
                <input
                  type="date"
                  value={editForm.endDate}
                  onChange={(e) => setEditForm((f) => ({ ...f, endDate: e.target.value }))}
                />
              </label>
            </div>

            {detail.aiExtractionOriginal ? (
              <>
                <h3 className="leave-detail-section-title">{t('accountant.sickLeaves.aiOriginal')}</h3>
                <dl className="sickLeaves-drawer__meta">
                  <div>
                    <dt>{t('accountant.sickLeaves.fieldEmail')}</dt>
                    <dd>{detail.aiExtractionOriginal.employeeEmail || '—'}</dd>
                  </div>
                  <div>
                    <dt>{t('accountant.sickLeaves.fieldName')}</dt>
                    <dd>{detail.aiExtractionOriginal.employeeName || '—'}</dd>
                  </div>
                  <div>
                    <dt>{t('accountant.sickLeaves.extractedDates')}</dt>
                    <dd>
                      {detail.aiExtractionOriginal.startDate || '—'} →{' '}
                      {detail.aiExtractionOriginal.endDate || '—'}
                    </dd>
                  </div>
                </dl>
              </>
            ) : null}

            <h3 className="leave-detail-section-title">{t('accountant.sickLeaves.originalEmail')}</h3>
            <dl className="leave-original-email">
              <div className="leave-original-email__field">
                <dt>{t('accountant.sickLeaves.receivedDate')}</dt>
                <dd>{formatLeaveDateTime(detail.receivedAt, dateLocale)}</dd>
              </div>
              <div className="leave-original-email__field">
                <dt>{t('accountant.sickLeaves.sender')}</dt>
                <dd>{detail.senderEmail || '—'}</dd>
              </div>
              <div className="leave-original-email__field">
                <dt>{t('accountant.sickLeaves.subject')}</dt>
                <dd>{detail.originalSubject || '—'}</dd>
              </div>
              <div className="leave-original-email__field">
                <dt>{t('accountant.sickLeaves.originalBody')}</dt>
                <dd>
                  <pre className="leave-original-email__block">{detail.originalBodyText || '—'}</pre>
                </dd>
              </div>
              <div className="leave-original-email__field">
                <dt>{t('accountant.sickLeaves.extractionExplanation')}</dt>
                <dd>
                  <pre className="leave-original-email__block leave-original-email__block--ai">
                    {originalExplanation || '—'}
                  </pre>
                </dd>
              </div>
              <div className="leave-original-email__field">
                <dt>{t('accountant.sickLeaves.confidenceLevel')}</dt>
                <dd>{formatLeaveConfidence(originalConfidence)}</dd>
              </div>
            </dl>
          </div>
        </ModalDialog>
      ) : null}

      {unsavedOpen ? (
        <ModalDialog
          title={t('accountant.sickLeaves.unsavedTitle')}
          variant="warning"
          closeLabel={t('common.close')}
          onClose={() => setUnsavedOpen(false)}
          footer={
            <div className="unsaved-actions">
              <button
                type="button"
                className="btn btn--secondary"
                onClick={() => setUnsavedOpen(false)}
              >
                {t('accountant.sickLeaves.unsavedStay')}
              </button>
              <button type="button" className="btn btn--secondary" onClick={discardAndLeave}>
                {t('accountant.sickLeaves.unsavedDiscard')}
              </button>
              <button
                type="button"
                className="btn btn--primary"
                disabled={saving}
                onClick={() => void saveAndLeave()}
              >
                {t('accountant.sickLeaves.unsavedSaveAndLeave')}
              </button>
            </div>
          }
        >
          <p className="modal-dialog__message">{t('accountant.sickLeaves.unsavedMessage')}</p>
        </ModalDialog>
      ) : null}

      {settingsOpen && settings ? (
        <ModalDialog
          title={t('accountant.sickLeaves.settings')}
          closeLabel={t('common.close')}
          onClose={closeSettings}
          footer={
            <>
              <button type="button" className="btn btn--secondary" onClick={closeSettings}>
                {t('common.cancel')}
              </button>
              <button
                type="button"
                className="btn btn--primary"
                disabled={!settingsDirty || settingsSaving}
                onClick={() => void saveSettings()}
              >
                {t('common.save')}
              </button>
            </>
          }
        >
          <div className="leave-settings-modal">
            <section className="leave-settings-section" aria-labelledby="leave-settings-notify">
              <h3 id="leave-settings-notify" className="leave-settings-section__title">
                {t('accountant.sickLeaves.notificationsSection')}
              </h3>
              <label className="leave-settings-field">
                <span className="leave-settings-field__label">
                  {t('accountant.sickLeaves.notificationEmailField')}
                </span>
                <input
                  type="email"
                  className="sickLeaves-filter-control leave-settings-input"
                  value={settingsForm.notificationEmail}
                  onChange={(e) => {
                    setSettingsForm((f) => ({ ...f, notificationEmail: e.target.value }));
                    setSettingsEmailError(null);
                  }}
                  autoComplete="email"
                />
                <span className="leave-settings-field__help">
                  {t('accountant.sickLeaves.notificationEmailHelp')}
                </span>
                {settingsForm.notificationEmail.trim() ? (
                  <span className="leave-settings-field__hint">
                    {t('accountant.sickLeaves.notificationEmailUnverifiedHint')}
                  </span>
                ) : null}
                {settingsEmailError ? (
                  <span className="leave-settings-field__error" role="alert">
                    {settingsEmailError}
                  </span>
                ) : null}
              </label>

              <div className="leave-settings-prefs">
                <label className="sickLeaves-check">
                  <input
                    type="checkbox"
                    checked={settingsForm.notifyOnNewSickLeave}
                    onChange={(e) =>
                      setSettingsForm((f) => ({ ...f, notifyOnNewSickLeave: e.target.checked }))
                    }
                  />
                  {t('accountant.sickLeaves.notifyNew')}
                </label>
                <label className="sickLeaves-check">
                  <input
                    type="checkbox"
                    checked={settingsForm.notifyOnSickLeaveErrorOrAttention}
                    onChange={(e) =>
                      setSettingsForm((f) => ({
                        ...f,
                        notifyOnSickLeaveErrorOrAttention: e.target.checked,
                      }))
                    }
                  />
                  {t('accountant.sickLeaves.notifyAttention')}
                </label>
              </div>
            </section>
          </div>
        </ModalDialog>
      ) : null}

      {manualOpen ? (
        <ModalDialog
          title={t('accountant.sickLeaves.addManual')}
          onClose={() => setManualOpen(false)}
          footer={
            <>
              <button
                type="button"
                className="btn btn--secondary"
                onClick={() => setManualOpen(false)}
              >
                {t('common.cancel')}
              </button>
              <button type="button" className="btn btn--primary" onClick={() => void createManual()}>
                {t('common.create')}
              </button>
            </>
          }
        >
          <div className="form-grid">
            <label>
              {t('accountant.sickLeaves.fieldEmail')}
              <input
                value={manualForm.employeeEmail}
                onChange={(e) => setManualForm((f) => ({ ...f, employeeEmail: e.target.value }))}
              />
            </label>
            <label>
              {t('accountant.sickLeaves.fieldName')}
              <input
                value={manualForm.employeeName}
                onChange={(e) => setManualForm((f) => ({ ...f, employeeName: e.target.value }))}
              />
            </label>
            <label>
              {t('accountant.sickLeaves.fieldStartDate')}
              <input
                type="date"
                value={manualForm.startDate}
                onChange={(e) => setManualForm((f) => ({ ...f, startDate: e.target.value }))}
              />
            </label>
            <label>
              {t('accountant.sickLeaves.fieldEndDate')}
              <input
                type="date"
                value={manualForm.endDate}
                onChange={(e) => setManualForm((f) => ({ ...f, endDate: e.target.value }))}
              />
            </label>
          </div>
        </ModalDialog>
      ) : null}
    </PortalPage>
  );
}
