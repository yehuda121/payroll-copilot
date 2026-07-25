import { describe, expect, it } from 'vitest';
import { mapVacationSettingsForUi } from '../../services/vacations';

describe('mapVacationSettingsForUi V1', () => {
  it('maps not_configured automation status for settings cards', () => {
    const mapped = mapVacationSettingsForUi({
      notification_email_verified: null,
      notify_on_new_vacation: true,
      notify_on_error_or_attention: true,
      active_monitored_email: null,
      mailbox_connection_status: 'disconnected',
      email_automation_status: 'not_configured',
      support_contact: { name: 'Support', email: 'support@example.com', phone: null },
    });
    expect(mapped.emailAutomationStatus).toBe('not_configured');
    expect(mapped.supportContact.email).toBe('support@example.com');
    expect(mapped.activeMonitoredEmail).toBeNull();
  });

  it('maps active read-only monitored mailbox', () => {
    const mapped = mapVacationSettingsForUi({
      active_monitored_email: 'hr@example.com',
      email_automation_status: 'active',
      mailbox_connection_status: 'ok',
      support_contact: {},
    });
    expect(mapped.emailAutomationStatus).toBe('active');
    expect(mapped.activeMonitoredEmail).toBe('hr@example.com');
  });
});
