import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { ActionIconButton } from '../../components/ui/ActionIconButton';
import { DataTable, type DataTableColumn } from '../../components/ui/DataTable';
import { LoadingOverlay, ModalDialog, useConfirmDialog } from '../../components/ui/Dialog';
import { TrashIcon } from '../../components/ui/icons';
import { useToast } from '../../components/ui/Toast';
import {
  getLeaveListCache,
  leaveListCacheKey,
  readLeaveUiSession,
  setLeaveListCache,
  writeLeaveUiSession,
} from '../../lib/accountant/leave-management-cache';
import {
  formatLeaveConfidence,
  formatLeaveDateTime,
  isBasicLeaveNotificationEmail,
  isLeaveEditDirty,
  isLeaveSettingsDirty,
  LEAVE_DEFAULT_BUCKET,
  LEAVE_HARD_ATTENTION_CODES,
  leaveAttentionLabel,
  leaveEditBaseline,
  leaveEmployeeLabel,
  leaveRowSeverityClass,
  leaveSettingsBaseline,
  leaveStatusBadgeClass,
  mapLeaveActionError,
  normalizeLeaveNotificationEmail,
  type LeaveEditForm,
  type LeaveSettingsForm,
} from '../../lib/accountant/leave-management-ui';
import { ApiClientError } from '../../services/api';
import {
  vacationsService,
  type VacationRecord,
  type VacationSettings,
} from '../../services/vacations';
import {
  LeaveLoadError,
  LeaveManualEntryFields,
  LeaveToolbar,
  LeaveUnsavedChangesDialog,
} from './leave-ui/LeavePresentation';
import './leave-ui/LeaveManagement.css';

type Bucket =
  | typeof LEAVE_DEFAULT_BUCKET
  | 'current'
  | 'upcoming'
  | 'past'
  | 'pending_approval'
  | 'requires_attention'
  | 'approved';

type LoadOptions = {
  /** Explicit refresh — keep rows visible, show subtle refreshing state. */
  force?: boolean;
};

type LeaveRow = VacationRecord & Record<string, unknown>;

export function VacationsPage() {
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

  const [settings, setSettings] = useState<VacationSettings | null>(
    () => initialCache?.settings ?? null,
  );
  const [items, setItems] = useState<VacationRecord[]>(() => initialCache?.items ?? []);
  const [bucket, setBucket] = useState<Bucket>((session.bucket as Bucket) || LEAVE_DEFAULT_BUCKET);
  const [rangeStart, setRangeStart] = useState(session.rangeStart);
  const [rangeEnd, setRangeEnd] = useState(session.rangeEnd);
  const [loading, setLoading] = useState(() => !initialCache);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [detail, setDetail] = useState<VacationRecord | null>(null);
  const [editBaseline, setEditBaseline] = useState<LeaveEditForm | null>(null);
  const [unsavedOpen, setUnsavedOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsForm, setSettingsForm] = useState<LeaveSettingsForm>({
    notificationEmail: '',
    notifyOnNewVacation: true,
    notifyOnErrorOrAttention: true,
  });
  const [settingsBaseline, setSettingsBaseline] = useState<LeaveSettingsForm | null>(null);
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
      mapLeaveActionError(err, t('accountant.vacations.toastActionFailed'), {
        blockedApproval: options?.blockedApproval
          ? t('accountant.vacations.toastApproveBlocked')
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

      const settingsResult = await vacationsService.getSettings().then(
        (value) => ({ ok: true as const, value }),
        (err: unknown) => ({ ok: false as const, err }),
      );
      const listResult = await vacationsService
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
          await vacationsService.markSeen({
            vacationIds: listResult.value.map((row) => row.id),
            seenBefore: pageLoadedAt,
          });
        } catch (err) {
          console.error('Leave mark-seen failed', err);
          showToast({
            tone: 'error',
            message: t('accountant.vacations.toastMarkSeenFailed'),
          });
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
    settingsBaseline && isLeaveSettingsDirty(settingsForm, settingsBaseline),
  );

  const openSettings = () => {
    if (!settings) return;
    const baseline = leaveSettingsBaseline(settings);
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
      setSettingsEmailError(t('accountant.vacations.invalidNotificationEmail'));
      return;
    }
    setSettingsEmailError(null);
    setSettingsSaving(true);
    try {
      const next = await vacationsService.patchPreferences({
        notificationEmail: normalizeLeaveNotificationEmail(settingsForm.notificationEmail) || null,
        notifyOnNewVacation: settingsForm.notifyOnNewVacation,
        notifyOnErrorOrAttention: settingsForm.notifyOnErrorOrAttention,
      });
      setSettings(next);
      const baseline = leaveSettingsBaseline(next);
      setSettingsForm(baseline);
      setSettingsBaseline(baseline);
      const cacheKey = leaveListCacheKey(bucket, rangeStart, rangeEnd);
      const cached = getLeaveListCache(cacheKey);
      setLeaveListCache(cacheKey, {
        items: cached?.items ?? items,
        settings: next,
      });
      showToast({ tone: 'success', message: t('accountant.vacations.toastSettingsSaved') });
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
      const updated = await vacationsService.update(detail.id, {
        employeeEmail: editForm.employeeEmail.trim() || null,
        employeeName: editForm.employeeName.trim() || null,
        startDate: editForm.startDate || null,
        endDate: editForm.endDate || null,
      });
      const baseline = leaveEditBaseline(updated);
      setDetail(updated);
      setEditForm(baseline);
      setEditBaseline(baseline);
      showToast({ tone: 'success', message: t('accountant.vacations.toastSaved') });
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

  const approveOne = async (row: VacationRecord, confirmWarnings = false) => {
    try {
      await vacationsService.approve(row.id, confirmWarnings);
      showToast({ tone: 'success', message: t('accountant.vacations.toastApproved') });
      await load({ force: true });
      if (detail?.id === row.id) closeDetail();
    } catch (err) {
      if (err instanceof ApiClientError && err.status === 409) {
        const ok = await confirm({
          title: t('accountant.vacations.bulkConfirmTitle'),
          message: t('accountant.vacations.approveWarningConfirm'),
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

  const deleteOne = async (row: VacationRecord) => {
    const ok = await confirm({
      title: t('accountant.vacations.deleteOneTitle'),
      message: t('accountant.vacations.deleteOneMessage'),
      confirmLabel: t('common.delete'),
      cancelLabel: t('common.cancel'),
      variant: 'danger',
    });
    if (!ok) return;
    try {
      await vacationsService.deleteOrCancel(row.id);
      showToast({ tone: 'success', message: t('accountant.vacations.toastDeleted') });
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
      const result = await vacationsService.bulkApprove(ids, confirmWarnings);
      if (result.status === 'confirmation_required') {
        const warningItems = result.items.filter((item) => item.classification === 'WARNING');
        const ok = await confirm({
          title: t('accountant.vacations.bulkConfirmTitle'),
          message: t('accountant.vacations.bulkConfirmMessage', {
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
      showToast({ tone: 'success', message: t('accountant.vacations.toastBulkApproved') });
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
      title: t('accountant.vacations.deleteConfirmTitle'),
      message: t('accountant.vacations.deleteConfirmMessage', { count: ids.length }),
      confirmLabel: t('common.delete'),
      cancelLabel: t('common.cancel'),
      variant: 'danger',
    });
    if (!ok) return;
    try {
      await vacationsService.bulkDelete(ids);
      showToast({ tone: 'success', message: t('accountant.vacations.toastBulkDeleted') });
      await load({ force: true });
    } catch (err) {
      console.error('Leave bulk delete failed', err);
      showToast({ tone: 'error', message: friendlyError(err) });
    }
  };

  const createManual = async () => {
    try {
      await vacationsService.createManual({
        employeeEmail: manualForm.employeeEmail || undefined,
        employeeName: manualForm.employeeName || undefined,
        startDate: manualForm.startDate,
        endDate: manualForm.endDate,
        notes: manualForm.notes || undefined,
      });
      setManualOpen(false);
      showToast({ tone: 'success', message: t('accountant.vacations.toastSaved') });
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
          aria-label={t('accountant.vacations.selectAll')}
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
          aria-label={t('accountant.vacations.selectRow')}
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
      header: t('accountant.vacations.colEmployee'),
      sortValue: (row) => leaveEmployeeLabel(row),
      render: (row) => (
        <span className={leaveRowSeverityClass(row.attentionCodes)}>
          {leaveEmployeeLabel(row)}
          {row.attentionCodes.length > 0 ? (
            <span className="leave-codes">
              {row.attentionCodes.slice(0, 2).map((code) => (
                <span
                  key={code}
                  className={`status-badge ${
                    LEAVE_HARD_ATTENTION_CODES.has(code)
                      ? 'status-badge--critical'
                      : 'status-badge--warnings'
                  }`}
                >
                  {leaveAttentionLabel(code, t, 'accountant.vacations')}
                </span>
              ))}
            </span>
          ) : null}
        </span>
      ),
    },
    {
      key: 'type',
      header: t('accountant.vacations.colType'),
      sortValue: () => 'vacation',
      render: () => t('accountant.vacations.typeVacation'),
    },
    {
      key: 'startDate',
      header: t('accountant.vacations.colStart'),
      sortValue: (row) => row.startDate,
      render: (row) => row.startDate || '—',
    },
    {
      key: 'endDate',
      header: t('accountant.vacations.colEnd'),
      sortValue: (row) => row.endDate,
      render: (row) => row.endDate || '—',
    },
    {
      key: 'reviewStatus',
      header: t('accountant.vacations.colStatus'),
      sortValue: (row) => row.reviewStatus,
      render: (row) => (
        <span className={`status-badge ${leaveStatusBadgeClass(row.reviewStatus, row.attentionCodes)}`}>
          {t(`accountant.vacations.status.${row.reviewStatus}`, {
            defaultValue: row.reviewStatus,
          })}
        </span>
      ),
    },
    {
      key: 'receivedAt',
      header: t('accountant.vacations.colReceived'),
      sortValue: (row) => row.receivedAt || row.createdAt,
      render: (row) => (row.receivedAt || row.createdAt || '—').slice(0, 10),
    },
    {
      key: 'actions',
      header: t('accountant.vacations.colActions'),
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
            {t('accountant.vacations.approve')}
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
      title={t('accountant.vacations.title')}
      description={t('accountant.vacations.description')}
    >
      {loading && items.length === 0 ? <LoadingOverlay label={t('common.loading')} /> : null}

      <LeaveLoadError message={loadError} className="vacations-error" />

      <LeaveToolbar
        filterClassPrefix="vacations"
        labels={{
          addManual: t('accountant.vacations.addManual'),
          settingsOpen: t('accountant.vacations.settingsOpen'),
          refresh: t('accountant.vacations.refresh'),
          filterStatus: t('accountant.vacations.filterStatus'),
          rangeStart: t('accountant.vacations.rangeStart'),
          rangeEnd: t('accountant.vacations.rangeEnd'),
          approveSelected: t('accountant.vacations.approveSelected'),
          deleteSelected: t('accountant.vacations.deleteSelected'),
        }}
        buckets={buckets.map((key) => ({
          value: key,
          label: t(`accountant.vacations.buckets.${key}`),
        }))}
        bucket={bucket}
        rangeStart={rangeStart}
        rangeEnd={rangeEnd}
        selectedCount={selected.size}
        refreshing={refreshing}
        settingsDisabled={!settings}
        onAddManual={() => setManualOpen(true)}
        onOpenSettings={openSettings}
        onRefresh={() => void load({ force: true })}
        onBucketChange={(value) => setBucket(value as Bucket)}
        onRangeStartChange={setRangeStart}
        onRangeEndChange={setRangeEnd}
        onApproveSelected={() => void bulkApprove()}
        onDeleteSelected={() => void bulkDelete()}
      />

      <DataTable
        columns={columns}
        data={tableRows}
        sortable
        getRowKey={(row) => row.id}
        emptyMessage={t('accountant.vacations.empty')}
        ariaLabel={t('accountant.vacations.title')}
        onRowClick={(row) => setDetail(row)}
      />

      {detail ? (
        <ModalDialog
          title={leaveEmployeeLabel(detail)}
          wide
          className="leave-request-dialog"
          closeLabel={t('common.close')}
          onClose={unsavedOpen ? () => undefined : requestCloseDetail}
          footer={
            <div className="leave-detail-footer">
              <ActionIconButton
                tone="danger"
                label={t('accountant.vacations.deleteTooltip')}
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
                {t('accountant.vacations.saveChanges')}
              </button>
              {detail.reviewStatus === 'pending_approval' ||
              detail.reviewStatus === 'requires_attention' ? (
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => void approveOne(detail)}
                >
                  {t('accountant.vacations.approve')}
                </button>
              ) : null}
            </div>
          }
        >
          <div className="leave-detail-modal">
            <p>
              <span
                className={`status-badge ${leaveStatusBadgeClass(detail.reviewStatus, detail.attentionCodes)}`}
              >
                {t(`accountant.vacations.status.${detail.reviewStatus}`, {
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
                        LEAVE_HARD_ATTENTION_CODES.has(code)
                          ? 'status-badge--critical'
                          : 'status-badge--warnings'
                      }`}
                    >
                      {leaveAttentionLabel(code, t, 'accountant.vacations')}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}

            {detail.overlapWith.length > 0 ? (
              <p>
                {t('accountant.vacations.overlapWith')}: {detail.overlapWith.join(', ')}
              </p>
            ) : null}

            <div className="form-grid">
              <label>
                {t('accountant.vacations.fieldName')}
                <input
                  value={editForm.employeeName}
                  onChange={(e) => setEditForm((f) => ({ ...f, employeeName: e.target.value }))}
                />
              </label>
              <label>
                {t('accountant.vacations.fieldEmail')}
                <input
                  type="email"
                  value={editForm.employeeEmail}
                  onChange={(e) => setEditForm((f) => ({ ...f, employeeEmail: e.target.value }))}
                />
              </label>
              <label>
                {t('accountant.vacations.fieldStartDate')}
                <input
                  type="date"
                  value={editForm.startDate}
                  onChange={(e) => setEditForm((f) => ({ ...f, startDate: e.target.value }))}
                />
              </label>
              <label>
                {t('accountant.vacations.fieldEndDate')}
                <input
                  type="date"
                  value={editForm.endDate}
                  onChange={(e) => setEditForm((f) => ({ ...f, endDate: e.target.value }))}
                />
              </label>
            </div>

            {detail.aiExtractionOriginal ? (
              <>
                <h3 className="leave-detail-section-title">{t('accountant.vacations.aiOriginal')}</h3>
                <dl className="vacations-drawer__meta">
                  <div>
                    <dt>{t('accountant.vacations.fieldEmail')}</dt>
                    <dd>{detail.aiExtractionOriginal.employeeEmail || '—'}</dd>
                  </div>
                  <div>
                    <dt>{t('accountant.vacations.fieldName')}</dt>
                    <dd>{detail.aiExtractionOriginal.employeeName || '—'}</dd>
                  </div>
                  <div>
                    <dt>{t('accountant.vacations.extractedDates')}</dt>
                    <dd>
                      {detail.aiExtractionOriginal.startDate || '—'} →{' '}
                      {detail.aiExtractionOriginal.endDate || '—'}
                    </dd>
                  </div>
                </dl>
              </>
            ) : null}

            <h3 className="leave-detail-section-title">{t('accountant.vacations.originalEmail')}</h3>
            <dl className="leave-original-email">
              <div className="leave-original-email__field">
                <dt>{t('accountant.vacations.receivedDate')}</dt>
                <dd>{formatLeaveDateTime(detail.receivedAt, dateLocale)}</dd>
              </div>
              <div className="leave-original-email__field">
                <dt>{t('accountant.vacations.sender')}</dt>
                <dd>{detail.senderEmail || '—'}</dd>
              </div>
              <div className="leave-original-email__field">
                <dt>{t('accountant.vacations.subject')}</dt>
                <dd>{detail.originalSubject || '—'}</dd>
              </div>
              <div className="leave-original-email__field">
                <dt>{t('accountant.vacations.originalBody')}</dt>
                <dd>
                  <pre className="leave-original-email__block">{detail.originalBodyText || '—'}</pre>
                </dd>
              </div>
              <div className="leave-original-email__field">
                <dt>{t('accountant.vacations.extractionExplanation')}</dt>
                <dd>
                  <pre className="leave-original-email__block leave-original-email__block--ai">
                    {originalExplanation || '—'}
                  </pre>
                </dd>
              </div>
              <div className="leave-original-email__field">
                <dt>{t('accountant.vacations.confidenceLevel')}</dt>
                <dd>{formatLeaveConfidence(originalConfidence)}</dd>
              </div>
            </dl>
          </div>
        </ModalDialog>
      ) : null}

      <LeaveUnsavedChangesDialog
        open={unsavedOpen}
        title={t('accountant.vacations.unsavedTitle')}
        message={t('accountant.vacations.unsavedMessage')}
        stayLabel={t('accountant.vacations.unsavedStay')}
        discardLabel={t('accountant.vacations.unsavedDiscard')}
        saveAndLeaveLabel={t('accountant.vacations.unsavedSaveAndLeave')}
        closeLabel={t('common.close')}
        saving={saving}
        onStay={() => setUnsavedOpen(false)}
        onDiscard={discardAndLeave}
        onSaveAndLeave={() => void saveAndLeave()}
      />

      {settingsOpen && settings ? (
        <ModalDialog
          title={t('accountant.vacations.settings')}
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
                {t('accountant.vacations.notificationsSection')}
              </h3>
              <label className="leave-settings-field">
                <span className="leave-settings-field__label">
                  {t('accountant.vacations.notificationEmailField')}
                </span>
                <input
                  type="email"
                  className="vacations-filter-control leave-settings-input"
                  value={settingsForm.notificationEmail}
                  onChange={(e) => {
                    setSettingsForm((f) => ({ ...f, notificationEmail: e.target.value }));
                    setSettingsEmailError(null);
                  }}
                  autoComplete="email"
                />
                <span className="leave-settings-field__help">
                  {t('accountant.vacations.notificationEmailHelp')}
                </span>
                {settingsForm.notificationEmail.trim() ? (
                  <span className="leave-settings-field__hint">
                    {t('accountant.vacations.notificationEmailUnverifiedHint')}
                  </span>
                ) : null}
                {settingsEmailError ? (
                  <span className="leave-settings-field__error" role="alert">
                    {settingsEmailError}
                  </span>
                ) : null}
              </label>

              <div className="leave-settings-prefs">
                <label className="vacations-check">
                  <input
                    type="checkbox"
                    checked={settingsForm.notifyOnNewVacation}
                    onChange={(e) =>
                      setSettingsForm((f) => ({ ...f, notifyOnNewVacation: e.target.checked }))
                    }
                  />
                  {t('accountant.vacations.notifyNew')}
                </label>
                <label className="vacations-check">
                  <input
                    type="checkbox"
                    checked={settingsForm.notifyOnErrorOrAttention}
                    onChange={(e) =>
                      setSettingsForm((f) => ({
                        ...f,
                        notifyOnErrorOrAttention: e.target.checked,
                      }))
                    }
                  />
                  {t('accountant.vacations.notifyAttention')}
                </label>
              </div>
            </section>
          </div>
        </ModalDialog>
      ) : null}

      {manualOpen ? (
        <ModalDialog
          title={t('accountant.vacations.addManual')}
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
          <LeaveManualEntryFields
            labels={{
              fieldEmail: t('accountant.vacations.fieldEmail'),
              fieldName: t('accountant.vacations.fieldName'),
              fieldStartDate: t('accountant.vacations.fieldStartDate'),
              fieldEndDate: t('accountant.vacations.fieldEndDate'),
            }}
            values={manualForm}
            onChange={(patch) => setManualForm((f) => ({ ...f, ...patch }))}
          />
        </ModalDialog>
      ) : null}
    </PortalPage>
  );
}
