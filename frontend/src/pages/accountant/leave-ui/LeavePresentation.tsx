/** Shared leave-page presentation primitives — labels/actions supplied by domain. */

import { ActionIconButton } from '../../../components/ui/ActionIconButton';
import { ModalDialog } from '../../../components/ui/Dialog';
import { FormField, FormInfoPanel, FormSection, FormShell } from '../../../components/ui/form/FormPrimitives';
import { CalendarIcon, RefreshIcon, SettingsIcon, SparklesIcon, UserIcon } from '../../../components/ui/icons';
import { FIELD_MAX_LENGTH } from '../../../lib/employee/field-text';
import { EMAIL_MAX_LENGTH } from '../../../lib/validation/email';
import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation();
  return (
    <FormShell
      aside={
        <FormInfoPanel
          tone="tip"
          eyebrow={t('forms.info.tipEyebrow')}
          title={t('forms.info.leaveManualTitle')}
          icon={<SparklesIcon size={14} aria-hidden="true" />}
        >
          <p>{t('forms.info.leaveManualBody')}</p>
        </FormInfoPanel>
      }
    >
      <FormSection
        title={t('forms.sections.employeeContact.title')}
        description={t('forms.sections.employeeContact.description')}
        icon={<UserIcon size={18} />}
      >
        <FormField label={labels.fieldEmail} htmlFor="leave-manual-email" span={2}>
          <input
            id="leave-manual-email"
            className="pc-form-control"
            type="email"
            inputMode="email"
            autoComplete="off"
            maxLength={EMAIL_MAX_LENGTH}
            value={values.employeeEmail}
            onChange={(e) => onChange({ employeeEmail: e.target.value })}
          />
        </FormField>
        <FormField label={labels.fieldName} htmlFor="leave-manual-name" span={2}>
          <input
            id="leave-manual-name"
            className="pc-form-control"
            type="text"
            autoComplete="name"
            maxLength={FIELD_MAX_LENGTH.personName}
            value={values.employeeName}
            onChange={(e) => onChange({ employeeName: e.target.value })}
          />
        </FormField>
      </FormSection>
      <FormSection
        title={t('forms.sections.leaveDates.title')}
        description={t('forms.sections.leaveDates.description')}
        icon={<CalendarIcon size={18} />}
      >
        <FormField label={labels.fieldStartDate} htmlFor="leave-manual-start">
          <input
            id="leave-manual-start"
            className="pc-form-control"
            type="date"
            value={values.startDate}
            onChange={(e) => onChange({ startDate: e.target.value })}
          />
        </FormField>
        <FormField label={labels.fieldEndDate} htmlFor="leave-manual-end">
          <input
            id="leave-manual-end"
            className="pc-form-control"
            type="date"
            value={values.endDate}
            onChange={(e) => onChange({ endDate: e.target.value })}
          />
        </FormField>
      </FormSection>
      {error ? (
        <p className="pc-form-field__error" role="alert">
          {error}
        </p>
      ) : null}
    </FormShell>
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
      size="lg"
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

export type LeaveDetailEditFieldsProps = {
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
  onChange: (patch: Partial<LeaveDetailEditFieldsProps['values']>) => void;
  error?: string | null;
};

/** Shared leave detail edit fields — Form Design System. */
export function LeaveDetailEditFields({
  labels,
  values,
  onChange,
  error = null,
}: LeaveDetailEditFieldsProps) {
  const { t } = useTranslation();
  return (
    <FormShell
      aside={
        <FormInfoPanel
          tone="tip"
          eyebrow={t('forms.info.tipEyebrow')}
          title={t('forms.info.leaveDetailTitle')}
          icon={<SparklesIcon size={14} aria-hidden="true" />}
        >
          <p>{t('forms.info.leaveDetailBody')}</p>
        </FormInfoPanel>
      }
    >
      <FormSection
        title={t('forms.sections.employeeContact.title')}
        description={t('forms.sections.employeeContact.description')}
        icon={<UserIcon size={18} />}
      >
        <FormField label={labels.fieldName} htmlFor="leave-detail-name">
          <input
            id="leave-detail-name"
            className="pc-form-control"
            value={values.employeeName}
            maxLength={FIELD_MAX_LENGTH.personName}
            autoComplete="name"
            onChange={(e) => onChange({ employeeName: e.target.value })}
          />
        </FormField>
        <FormField label={labels.fieldEmail} htmlFor="leave-detail-email">
          <input
            id="leave-detail-email"
            className="pc-form-control"
            type="email"
            maxLength={EMAIL_MAX_LENGTH}
            value={values.employeeEmail}
            autoComplete="off"
            onChange={(e) => onChange({ employeeEmail: e.target.value })}
          />
        </FormField>
      </FormSection>
      <FormSection
        title={t('forms.sections.leaveDates.title')}
        description={t('forms.sections.leaveDates.description')}
        icon={<CalendarIcon size={18} />}
      >
        <FormField label={labels.fieldStartDate} htmlFor="leave-detail-start">
          <input
            id="leave-detail-start"
            className="pc-form-control"
            type="date"
            value={values.startDate}
            onChange={(e) => onChange({ startDate: e.target.value })}
          />
        </FormField>
        <FormField label={labels.fieldEndDate} htmlFor="leave-detail-end">
          <input
            id="leave-detail-end"
            className="pc-form-control"
            type="date"
            value={values.endDate}
            onChange={(e) => onChange({ endDate: e.target.value })}
          />
        </FormField>
      </FormSection>
      {error ? (
        <p className="pc-form-field__error" role="alert">
          {error}
        </p>
      ) : null}
    </FormShell>
  );
}

export type LeaveSettingsFieldsProps = {
  labels: {
    notificationsSection: string;
    notificationEmailField: string;
    notificationEmailHelp: string;
    notificationEmailUnverifiedHint: string;
    notifyNew: string;
    notifyAttention: string;
  };
  values: {
    notificationEmail: string;
    notifyOnNew: boolean;
    notifyOnAttention: boolean;
  };
  emailError?: string | null;
  onChangeEmail: (value: string) => void;
  onChangeNotifyNew: (value: boolean) => void;
  onChangeNotifyAttention: (value: boolean) => void;
};

/** Shared leave notification settings — Form Design System. */
export function LeaveSettingsFields({
  labels,
  values,
  emailError = null,
  onChangeEmail,
  onChangeNotifyNew,
  onChangeNotifyAttention,
}: LeaveSettingsFieldsProps) {
  const { t } = useTranslation();
  return (
    <FormShell
      aside={
        <FormInfoPanel
          tone="info"
          eyebrow={t('forms.info.tipEyebrow')}
          title={t('forms.info.leaveSettingsTitle')}
        >
          <p>{t('forms.info.leaveSettingsBody')}</p>
        </FormInfoPanel>
      }
    >
      <FormSection
        title={labels.notificationsSection}
        description={labels.notificationEmailHelp}
        icon={<SettingsIcon size={18} />}
        columns={1}
      >
        <FormField
          label={labels.notificationEmailField}
          htmlFor="leave-settings-email"
          hint={
            values.notificationEmail.trim() ? labels.notificationEmailUnverifiedHint : undefined
          }
          error={emailError}
          span={2}
        >
          <input
            id="leave-settings-email"
            className="pc-form-control"
            type="email"
            value={values.notificationEmail}
            maxLength={EMAIL_MAX_LENGTH}
            onChange={(e) => onChangeEmail(e.target.value)}
            autoComplete="email"
          />
        </FormField>
        <label className="form-field form-field--checkbox pc-form-field--span-2" htmlFor="leave-notify-new">
          <input
            id="leave-notify-new"
            type="checkbox"
            checked={values.notifyOnNew}
            onChange={(e) => onChangeNotifyNew(e.target.checked)}
          />
          <span>{labels.notifyNew}</span>
        </label>
        <label
          className="form-field form-field--checkbox pc-form-field--span-2"
          htmlFor="leave-notify-attention"
        >
          <input
            id="leave-notify-attention"
            type="checkbox"
            checked={values.notifyOnAttention}
            onChange={(e) => onChangeNotifyAttention(e.target.checked)}
          />
          <span>{labels.notifyAttention}</span>
        </label>
      </FormSection>
    </FormShell>
  );
}
