/** Leave Management UI helpers — presentation only; no business rules. */

/** Default list filter: maps UI "הכל" / "All" to existing backend `active` bucket. */
export const LEAVE_DEFAULT_BUCKET = 'active' as const;

export type LeaveEditForm = {
  employeeEmail: string;
  employeeName: string;
  startDate: string;
  endDate: string;
};

export function leaveEditBaseline(row: {
  extractedEmployeeEmail: string | null;
  extractedEmployeeName: string | null;
  startDate: string | null;
  endDate: string | null;
}): LeaveEditForm {
  return {
    employeeEmail: row.extractedEmployeeEmail || '',
    employeeName: row.extractedEmployeeName || '',
    startDate: row.startDate || '',
    endDate: row.endDate || '',
  };
}

export function isLeaveEditDirty(current: LeaveEditForm, baseline: LeaveEditForm): boolean {
  return (
    current.employeeEmail.trim() !== baseline.employeeEmail.trim() ||
    current.employeeName.trim() !== baseline.employeeName.trim() ||
    current.startDate !== baseline.startDate ||
    current.endDate !== baseline.endDate
  );
}

/** Display ISO timestamps in a compact local Israeli-friendly form. */
export function formatLeaveDateTime(iso: string | null | undefined, locale = 'he-IL'): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(locale, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

/** 0.95 → "95%" for display only. */
export function formatLeaveConfidence(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  const pct = value <= 1 ? Math.round(value * 100) : Math.round(value);
  return `${pct}%`;
}

export type LeaveToastTone = 'success' | 'error';

export function mapLeaveActionError(
  err: unknown,
  fallback: string,
  options?: { blockedApproval?: string },
): string {
  const message =
    err && typeof err === 'object' && 'message' in err
      ? String((err as { message?: unknown }).message || '')
      : '';
  const status =
    err && typeof err === 'object' && 'status' in err
      ? Number((err as { status?: unknown }).status)
      : 0;
  const code =
    err && typeof err === 'object' && 'code' in err
      ? String((err as { code?: unknown }).code || '')
      : '';

  const lower = message.toLowerCase();
  if (
    status === 422 ||
    code === 'blocked' ||
    lower.includes('blocked') ||
    lower.includes('unprocessable')
  ) {
    return options?.blockedApproval || fallback;
  }
  if (message && !/^api request failed/i.test(message) && !/unprocessable entity/i.test(message)) {
    // Prefer backend message when already human-readable.
    if (!/\b\d{3}\b/.test(message)) return message;
  }
  return fallback;
}

/** Trim + lower — matches backend normalize_email presentation. */
export function normalizeLeaveNotificationEmail(value: string): string {
  return value.trim().toLowerCase();
}

/**
 * Basic local@domain check (same rule as EmployeeForm).
 * Empty string is allowed (clears override → fall back to monitored mailbox).
 */
export function isBasicLeaveNotificationEmail(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return true;
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed);
}

export type LeaveSettingsForm = {
  notificationEmail: string;
  notifyOnNewVacation: boolean;
  notifyOnErrorOrAttention: boolean;
};

export function leaveSettingsBaseline(settings: {
  notificationEmailVerified: string | null;
  notificationEmailPending: string | null;
  notifyOnNewVacation: boolean;
  notifyOnErrorOrAttention: boolean;
}): LeaveSettingsForm {
  return {
    notificationEmail:
      settings.notificationEmailVerified || settings.notificationEmailPending || '',
    notifyOnNewVacation: settings.notifyOnNewVacation,
    notifyOnErrorOrAttention: settings.notifyOnErrorOrAttention,
  };
}

export function isLeaveSettingsDirty(
  current: LeaveSettingsForm,
  baseline: LeaveSettingsForm,
): boolean {
  return (
    normalizeLeaveNotificationEmail(current.notificationEmail) !==
      normalizeLeaveNotificationEmail(baseline.notificationEmail) ||
    current.notifyOnNewVacation !== baseline.notifyOnNewVacation ||
    current.notifyOnErrorOrAttention !== baseline.notifyOnErrorOrAttention
  );
}

