/** Shared leave-page presentation primitives — labels/actions supplied by domain. */

import { ActionIconButton } from '../../../components/ui/ActionIconButton';
import { ModalDialog } from '../../../components/ui/Dialog';
import { RefreshIcon, SettingsIcon } from '../../../components/ui/icons';
import { FIELD_MAX_LENGTH } from '../../../lib/employee/field-text';
import { EMAIL_MAX_LENGTH } from '../../../lib/validation/email';

export type LeaveToolbarBucketOption = {
  value: string;
  label: string;
};

export type LeaveToolbarProps = {
  /** CSS class prefix historically used by each page (`vacations` | `sickLeaves`). */
  filterClassPrefix: 'vacations' | 'sickLeaves';
  labels: {
    addManual: string;
    settingsOpen: string;
    refresh: string;
    filterStatus: string;
    rangeStart: string;
    rangeEnd: string;
    approveSelected: string;
    deleteSelected: string;
  };
  buckets: LeaveToolbarBucketOption[];
  bucket: string;
  rangeStart: string;
  rangeEnd: string;
  selectedCount: number;
  refreshing: boolean;
  settingsDisabled: boolean;
  onAddManual: () => void;
  onOpenSettings: () => void;
  onRefresh: () => void;
  onBucketChange: (value: string) => void;
  onRangeStartChange: (value: string) => void;
  onRangeEndChange: (value: string) => void;
  onApproveSelected: () => void;
  onDeleteSelected: () => void;
};

export function LeaveToolbar(props: LeaveToolbarProps) {
  const {
    filterClassPrefix,
    labels,
    buckets,
    bucket,
    rangeStart,
    rangeEnd,
    selectedCount,
    refreshing,
    settingsDisabled,
    onAddManual,
    onOpenSettings,
    onRefresh,
    onBucketChange,
    onRangeStartChange,
    onRangeEndChange,
    onApproveSelected,
    onDeleteSelected,
  } = props;
  const field = `${filterClassPrefix}-filter-field`;
  const control = `${filterClassPrefix}-filter-control`;
  return (
    <div className="leave-toolbar">
      <div className="leave-toolbar__actions">
        <button type="button" className="btn btn--primary" onClick={onAddManual}>
          {labels.addManual}
        </button>
        <ActionIconButton
          label={labels.settingsOpen}
          icon={<SettingsIcon size={18} />}
          disabled={settingsDisabled}
          onClick={onOpenSettings}
        />
        <ActionIconButton
          label={labels.refresh}
          icon={<RefreshIcon size={18} className={refreshing ? 'leave-icon--spin' : undefined} />}
          disabled={refreshing}
          onClick={onRefresh}
        />
      </div>
      <div className="leave-toolbar__filters">
        <label className={`${field} ${field}--status`}>
          <select
            className={control}
            value={bucket}
            aria-label={labels.filterStatus}
            onChange={(e) => onBucketChange(e.target.value)}
          >
            {buckets.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className={field}>
          {labels.rangeStart}
          <input
            className={control}
            type="date"
            value={rangeStart}
            onChange={(e) => onRangeStartChange(e.target.value)}
          />
        </label>
        <label className={field}>
          {labels.rangeEnd}
          <input
            className={control}
            type="date"
            value={rangeEnd}
            onChange={(e) => onRangeEndChange(e.target.value)}
          />
        </label>
        {selectedCount > 0 ? (
          <div className="leave-bulk-actions">
            <button type="button" className="btn btn--primary" onClick={onApproveSelected}>
              {labels.approveSelected}
            </button>
            <button type="button" className="btn btn--danger" onClick={onDeleteSelected}>
              {labels.deleteSelected}
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export type LeaveManualEntryFieldsProps = {
  labels: {
    fieldEmail: string;
    fieldName: string;
    fieldStartDate: string;
    fieldEndDate: string;
  };
  values: {
    employeeEmail: string;
    employeeName: string;
    startDate: string;
    endDate: string;
  };
  onChange: (patch: Partial<LeaveManualEntryFieldsProps['values']>) => void;
  error?: string | null;
};

export function LeaveManualEntryFields({ labels, values, onChange, error }: LeaveManualEntryFieldsProps) {
  return (
    <div className="leave-manual-form">
      <label className="leave-manual-form__field">
        {labels.fieldEmail}
        <input
          type="email"
          inputMode="email"
          autoComplete="off"
          maxLength={EMAIL_MAX_LENGTH}
          value={values.employeeEmail}
          onChange={(e) => onChange({ employeeEmail: e.target.value })}
        />
      </label>
      <label className="leave-manual-form__field">
        {labels.fieldName}
        <input
          type="text"
          autoComplete="name"
          maxLength={FIELD_MAX_LENGTH.personName}
          value={values.employeeName}
          onChange={(e) => onChange({ employeeName: e.target.value })}
        />
      </label>
      <div className="leave-manual-form__row">
        <label className="leave-manual-form__field">
          {labels.fieldStartDate}
          <input
            type="date"
            value={values.startDate}
            onChange={(e) => onChange({ startDate: e.target.value })}
          />
        </label>
        <label className="leave-manual-form__field">
          {labels.fieldEndDate}
          <input
            type="date"
            value={values.endDate}
            onChange={(e) => onChange({ endDate: e.target.value })}
          />
        </label>
      </div>
      {error ? (
        <p className="leave-manual-form__error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export type LeaveManualEntryDialogProps = {
  title: string;
  closeLabel: string;
  cancelLabel: string;
  createLabel: string;
  labels: LeaveManualEntryFieldsProps['labels'];
  values: LeaveManualEntryFieldsProps['values'];
  onChange: LeaveManualEntryFieldsProps['onChange'];
  onClose: () => void;
  onCreate: () => void;
  error?: string | null;
};

/** Shared visual shell for manual leave create — all copy supplied by the domain page. */
export function LeaveManualEntryDialog({
  title,
  closeLabel,
  cancelLabel,
  createLabel,
  labels,
  values,
  onChange,
  onClose,
  onCreate,
  error = null,
}: LeaveManualEntryDialogProps) {
  return (
    <ModalDialog
      title={title}
      closeLabel={closeLabel}
      className="leave-manual-dialog"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn--secondary" onClick={onClose}>
            {cancelLabel}
          </button>
          <button type="button" className="btn btn--primary" onClick={onCreate}>
            {createLabel}
          </button>
        </>
      }
    >
      <LeaveManualEntryFields labels={labels} values={values} onChange={onChange} error={error} />
    </ModalDialog>
  );
}

export type LeaveUnsavedChangesDialogProps = {
  open: boolean;
  title: string;
  message: string;
  stayLabel: string;
  discardLabel: string;
  saveAndLeaveLabel: string;
  closeLabel: string;
  saving?: boolean;
  onStay: () => void;
  onDiscard: () => void;
  onSaveAndLeave: () => void;
};

export function LeaveUnsavedChangesDialog({
  open,
  title,
  message,
  stayLabel,
  discardLabel,
  saveAndLeaveLabel,
  closeLabel,
  saving = false,
  onStay,
  onDiscard,
  onSaveAndLeave,
}: LeaveUnsavedChangesDialogProps) {
  if (!open) return null;
  return (
    <ModalDialog
      title={title}
      variant="warning"
      closeLabel={closeLabel}
      onClose={onStay}
      footer={
        <div className="unsaved-actions">
          <button type="button" className="btn btn--secondary" onClick={onStay}>
            {stayLabel}
          </button>
          <button type="button" className="btn btn--secondary" onClick={onDiscard}>
            {discardLabel}
          </button>
          <button
            type="button"
            className="btn btn--primary"
            disabled={saving}
            onClick={onSaveAndLeave}
          >
            {saveAndLeaveLabel}
          </button>
        </div>
      }
    >
      <p className="modal-dialog__message">{message}</p>
    </ModalDialog>
  );
}

export type LeaveLoadErrorProps = {
  message: string | null;
  className: string;
};

export function LeaveLoadError({ message, className }: LeaveLoadErrorProps) {
  if (!message) return null;
  return (
    <p className={className} role="alert">
      {message}
    </p>
  );
}
