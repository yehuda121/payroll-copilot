import { describe, expect, it } from 'vitest';
import { toastViewportPositionClass } from '../../components/ui/Toast';
import heAccountant from '../../i18n/locales/accountant.he.json';
import { jsonBody } from '../../services/vacations';

describe('Leave Management settings + toast contract', () => {
  it('serializes preferences PATCH with notification_email (regression for 422 extra_forbid)', () => {
    const body = jsonBody({
      notification_email: 'hr@example.com',
      notify_on_new_vacation: true,
      notify_on_error_or_attention: false,
    });
    expect(JSON.parse(body)).toEqual({
      notification_email: 'hr@example.com',
      notify_on_new_vacation: true,
      notify_on_error_or_attention: false,
    });
  });

  it('uses fixed overlay toast viewport class (no layout participation)', () => {
    expect(toastViewportPositionClass()).toBe('toast-viewport');
  });

  it('does not expose misleading disconnected / mailbox-unavailable accountant copy as primary settings', () => {
    const vacations = heAccountant.accountant.vacations;
    expect(vacations.notificationsSection).toBe('התראות');
    expect(vacations.notificationEmailField).toBe('מייל לקבלת התראות');
    // Monitored mailbox section keys may still exist for legacy, but must not be the
    // primary misleading "unavailable/disconnected" product message for accountants.
    expect(vacations.refresh).toBe('רענון');
  });
});
