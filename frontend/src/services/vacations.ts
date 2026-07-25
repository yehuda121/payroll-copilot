import { apiRequest } from './api';

export type VacationReviewStatus =
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'cancelled'
  | 'requires_attention';

export type VacationAiExtractionOriginal = {
  employeeEmail: string | null;
  employeeName: string | null;
  startDate: string | null;
  endDate: string | null;
  confidence: number | null;
  explanation: string | null;
};

export type VacationRecord = {
  id: string;
  organizationId: string;
  employeeId: string | null;
  extractedEmployeeEmail: string | null;
  extractedEmployeeName: string | null;
  senderEmail: string | null;
  startDate: string | null;
  endDate: string | null;
  provider: string | null;
  providerMessageId: string | null;
  originalSubject: string | null;
  originalBodyText: string | null;
  receivedAt: string | null;
  aiConfidence: number | null;
  aiExplanation: string | null;
  aiExtractionOriginal: VacationAiExtractionOriginal | null;
  overlapWith: string[];
  intent: string;
  relatedVacationId: string | null;
  source: string;
  reviewStatus: VacationReviewStatus | string;
  attentionCodes: string[];
  attentionDetail: string | null;
  seenAt: string | null;
  createdAt: string | null;
  updatedAt: string | null;
};

export type EmailAutomationStatus =
  | 'not_configured'
  | 'active'
  | 'disconnected'
  | 'error';

export type SupportContact = {
  name: string | null;
  email: string | null;
  phone: string | null;
};

export type VacationSettings = {
  notificationEmailVerified: string | null;
  notificationEmailPending: string | null;
  notifyOnNewVacation: boolean;
  notifyOnErrorOrAttention: boolean;
  activeMonitoredEmail: string | null;
  mailboxConnectionStatus: string;
  mailboxLastCheckAt: string | null;
  mailboxLastProcessedAt: string | null;
  mailboxLastProcessedMessageId: string | null;
  mailboxLastErrorCode: string | null;
  mailboxLastErrorMessage: string | null;
  emailAutomationStatus: EmailAutomationStatus | string;
  supportContact: SupportContact;
};

type ApiVacation = Record<string, unknown>;

/** Serialize JSON bodies for apiRequest — matches employeesService convention. */
export function jsonBody(payload: unknown): string {
  return JSON.stringify(payload);
}

function mapAiOriginal(raw: unknown): VacationAiExtractionOriginal | null {
  if (!raw || typeof raw !== 'object') return null;
  const row = raw as Record<string, unknown>;
  return {
    employeeEmail: (row.employee_email as string) ?? null,
    employeeName: (row.employee_name as string) ?? null,
    startDate: (row.start_date as string) ?? null,
    endDate: (row.end_date as string) ?? null,
    confidence: row.confidence == null ? null : Number(row.confidence),
    explanation: (row.explanation as string) ?? null,
  };
}

function mapVacation(row: ApiVacation): VacationRecord {
  return {
    id: String(row.id),
    organizationId: String(row.organization_id),
    employeeId: row.employee_id ? String(row.employee_id) : null,
    extractedEmployeeEmail: (row.extracted_employee_email as string) ?? null,
    extractedEmployeeName: (row.extracted_employee_name as string) ?? null,
    senderEmail: (row.sender_email as string) ?? null,
    startDate: (row.start_date as string) ?? null,
    endDate: (row.end_date as string) ?? null,
    provider: (row.provider as string) ?? null,
    providerMessageId: (row.provider_message_id as string) ?? null,
    originalSubject: (row.original_subject as string) ?? null,
    originalBodyText: (row.original_body_text as string) ?? null,
    receivedAt: (row.received_at as string) ?? null,
    aiConfidence: row.ai_confidence == null ? null : Number(row.ai_confidence),
    aiExplanation: (row.ai_explanation as string) ?? null,
    aiExtractionOriginal: mapAiOriginal(row.ai_extraction_original),
    overlapWith: Array.isArray(row.overlap_with) ? row.overlap_with.map(String) : [],
    intent: String(row.intent || 'new'),
    relatedVacationId: row.related_vacation_id ? String(row.related_vacation_id) : null,
    source: String(row.source || 'manual'),
    reviewStatus: String(row.review_status || 'pending_approval'),
    attentionCodes: Array.isArray(row.attention_codes)
      ? row.attention_codes.map(String)
      : [],
    attentionDetail: (row.attention_detail as string) ?? null,
    seenAt: (row.seen_at as string) ?? null,
    createdAt: (row.created_at as string) ?? null,
    updatedAt: (row.updated_at as string) ?? null,
  };
}

function mapSettings(row: Record<string, unknown>): VacationSettings {
  const support = (row.support_contact as Record<string, unknown> | undefined) || {};
  return {
    notificationEmailVerified: (row.notification_email_verified as string) ?? null,
    notificationEmailPending: (row.notification_email_pending as string) ?? null,
    notifyOnNewVacation: Boolean(row.notify_on_new_vacation ?? true),
    notifyOnErrorOrAttention: Boolean(row.notify_on_error_or_attention ?? true),
    activeMonitoredEmail: (row.active_monitored_email as string) ?? null,
    mailboxConnectionStatus: String(row.mailbox_connection_status || 'disconnected'),
    mailboxLastCheckAt: (row.mailbox_last_check_at as string) ?? null,
    mailboxLastProcessedAt: (row.mailbox_last_processed_at as string) ?? null,
    mailboxLastProcessedMessageId: (row.mailbox_last_processed_message_id as string) ?? null,
    mailboxLastErrorCode: (row.mailbox_last_error_code as string) ?? null,
    mailboxLastErrorMessage: (row.mailbox_last_error_message as string) ?? null,
    emailAutomationStatus: String(row.email_automation_status || 'not_configured'),
    supportContact: {
      name: (support.name as string) ?? null,
      email: (support.email as string) ?? null,
      phone: (support.phone as string) ?? null,
    },
  };
}

/** Exported for unit tests — maps API settings payload for Vacations cards. */
export function mapVacationSettingsForUi(row: Record<string, unknown>): VacationSettings {
  return mapSettings(row);
}

export const vacationsService = {
  async getSettings(): Promise<VacationSettings> {
    const raw = await apiRequest<Record<string, unknown>>('/accountant/vacations/settings', {
      portalAuth: true,
    });
    return mapSettings(raw);
  },

  async patchPreferences(body: {
    notifyOnNewVacation?: boolean;
    notifyOnErrorOrAttention?: boolean;
    /** When provided (including empty string), updates notification destination without OTP. */
    notificationEmail?: string | null;
  }): Promise<VacationSettings> {
    const payload: Record<string, unknown> = {};
    if (body.notifyOnNewVacation !== undefined) {
      payload.notify_on_new_vacation = body.notifyOnNewVacation;
    }
    if (body.notifyOnErrorOrAttention !== undefined) {
      payload.notify_on_error_or_attention = body.notifyOnErrorOrAttention;
    }
    if (body.notificationEmail !== undefined) {
      payload.notification_email = body.notificationEmail;
    }
    const raw = await apiRequest<Record<string, unknown>>(
      '/accountant/vacations/settings/preferences',
      {
        method: 'PATCH',
        portalAuth: true,
        body: jsonBody(payload),
      },
    );
    return mapSettings(raw);
  },

  async startVerification(email: string) {
    return apiRequest<{ email: string; expires_in_seconds: number }>(
      '/accountant/vacations/settings/notification-email/start-verification',
      {
        method: 'POST',
        portalAuth: true,
        body: jsonBody({ email }),
      },
    );
  },

  async confirmVerification(email: string, code: string): Promise<VacationSettings> {
    const raw = await apiRequest<Record<string, unknown>>(
      '/accountant/vacations/settings/notification-email/confirm-verification',
      {
        method: 'POST',
        portalAuth: true,
        body: jsonBody({ email, code }),
      },
    );
    return mapSettings(raw);
  },

  async list(params: {
    bucket?: string;
    rangeStart?: string;
    rangeEnd?: string;
    query?: string;
  }): Promise<VacationRecord[]> {
    const qs = new URLSearchParams();
    if (params.bucket) qs.set('bucket', params.bucket);
    if (params.rangeStart) qs.set('range_start', params.rangeStart);
    if (params.rangeEnd) qs.set('range_end', params.rangeEnd);
    if (params.query) qs.set('query', params.query);
    const raw = await apiRequest<{ items: ApiVacation[] }>(
      `/accountant/vacations?${qs.toString()}`,
      { portalAuth: true },
    );
    return (raw.items || []).map(mapVacation);
  },

  async unseenCount(): Promise<number> {
    const raw = await apiRequest<{ count: number }>('/accountant/vacations/unseen-count', {
      portalAuth: true,
    });
    return Number(raw.count || 0);
  },

  async markSeen(body: { vacationIds?: string[]; seenBefore?: string }) {
    return apiRequest<{ updated: number }>('/accountant/vacations/mark-seen', {
      method: 'POST',
      portalAuth: true,
      body: jsonBody({
        vacation_ids: body.vacationIds,
        seen_before: body.seenBefore,
      }),
    });
  },

  async createManual(body: {
    employeeEmail?: string;
    employeeName?: string;
    employeeId?: string;
    startDate: string;
    endDate: string;
    subject?: string;
    notes?: string;
  }): Promise<VacationRecord> {
    const raw = await apiRequest<ApiVacation>('/accountant/vacations', {
      method: 'POST',
      portalAuth: true,
      body: jsonBody({
        employee_email: body.employeeEmail,
        employee_name: body.employeeName,
        employee_id: body.employeeId,
        start_date: body.startDate,
        end_date: body.endDate,
        subject: body.subject,
        notes: body.notes,
      }),
    });
    return mapVacation(raw);
  },

  async update(
    id: string,
    body: {
      employeeEmail?: string | null;
      employeeName?: string | null;
      startDate?: string | null;
      endDate?: string | null;
      employeeId?: string | null;
      attentionDetail?: string | null;
    },
  ): Promise<VacationRecord> {
    const payload: Record<string, unknown> = {};
    if (body.employeeEmail !== undefined) payload.extracted_employee_email = body.employeeEmail;
    if (body.employeeName !== undefined) payload.extracted_employee_name = body.employeeName;
    if (body.startDate !== undefined) payload.start_date = body.startDate;
    if (body.endDate !== undefined) payload.end_date = body.endDate;
    if (body.employeeId !== undefined) payload.employee_id = body.employeeId;
    if (body.attentionDetail !== undefined) payload.attention_detail = body.attentionDetail;
    const raw = await apiRequest<ApiVacation>(`/accountant/vacations/${id}`, {
      method: 'PATCH',
      portalAuth: true,
      body: jsonBody(payload),
    });
    return mapVacation(raw);
  },

  async approve(id: string, confirmWarnings = false): Promise<VacationRecord> {
    const raw = await apiRequest<ApiVacation>(`/accountant/vacations/${id}/approve`, {
      method: 'POST',
      portalAuth: true,
      body: jsonBody({ confirm_warnings: confirmWarnings }),
    });
    return mapVacation(raw);
  },

  async reject(id: string, reason?: string): Promise<VacationRecord> {
    const raw = await apiRequest<ApiVacation>(`/accountant/vacations/${id}/reject`, {
      method: 'POST',
      portalAuth: true,
      body: jsonBody({ reason }),
    });
    return mapVacation(raw);
  },

  async bulkApprove(vacationIds: string[], confirmWarnings = false) {
    return apiRequest<{
      status: string;
      items: Array<{ id: string; classification: string; codes: string[] }>;
      approved: Array<{ id: string }>;
      skipped_blocked: Array<{ id: string; codes: string[] }>;
      failed: Array<{ id: string; error: string }>;
    }>('/accountant/vacations/bulk-approve', {
      method: 'POST',
      portalAuth: true,
      body: jsonBody({ vacation_ids: vacationIds, confirm_warnings: confirmWarnings }),
    });
  },

  async bulkDelete(vacationIds: string[]) {
    return apiRequest<{
      status: string;
      deleted: Array<{ id: string }>;
      cancelled: Array<{ id: string }>;
      failed: Array<{ id: string; error: string }>;
    }>('/accountant/vacations/bulk-delete', {
      method: 'POST',
      portalAuth: true,
      body: jsonBody({ vacation_ids: vacationIds }),
    });
  },

  async deleteOrCancel(id: string) {
    return apiRequest(`/accountant/vacations/${id}`, {
      method: 'DELETE',
      portalAuth: true,
    });
  },
};
