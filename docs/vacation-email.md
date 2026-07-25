# Vacation Email Management (V1)

Payroll Copilot owns **VacationRequest** as the DynamoDB source of truth for employee vacations.

## V1 product model

**ONE ORGANIZATION → ONE manually provisioned n8n workflow.**

The system administrator:

1. Creates an organization-bound integration API key (`POST /api/v1/admin/vacation-integrations/organizations/{org_id}/integration-credentials`).
2. Duplicates/configures that org’s n8n workflow.
3. Configures the org’s IMAP credential **inside n8n** (not in Payroll Copilot).
4. Activates the workflow with a historical-email watermark (`process_after = activation time`).

Payroll Copilot does **not** dynamically provision n8n workflows or IMAP credentials.  
Accountants do **not** change the monitored mailbox.

Future automated provisioning is out of scope for V1.

## Responsibility split

| Layer | Owns |
| --- | --- |
| n8n | IMAP credentials, receive (no Read/Unread mutation), watermark, normalize, guardrail, AI classify/extract, branch routing, notification sending per backend instructions, events + mailbox health |
| Payroll Copilot | VacationRequest SoT, org-bound auth, employee matching, validation, overlaps, idempotency, proposals, manual CRUD, approval/bulk, unseen, audit, leave reconciler, analytics, notification destination email + prefs, derived automation status (for integrations/diagnostics — not accountant connection UX) |

## Integration status (derived)

Single field: `email_automation_status` (used by integrations / diagnostics; not shown as an accountant “connected/disconnected” badge)

| Value | Meaning |
| --- | --- |
| `not_configured` | No non-revoked org integration credential |
| `active` | Credential exists + health `ok` + `active_monitored_email` set |
| `error` | Credential exists + latest health `error` |
| `disconnected` | Credential exists but not active and not error |

`active_monitored_email` may be reported by n8n health for diagnostics; it is not presented as a Payroll Copilot–owned IMAP connection control in the accountant UI.

## Notification email

Accountant-configurable notification destination (preferences PATCH). Independent of the n8n-monitored mailbox. OTP endpoints remain for backward compatibility; the V1 accountant UI saves the address directly with a correctness helper (no independent ownership verification).

## Key APIs

### Accountant

- Settings / notification prefs (incl. notification email) / vacation CRUD / approve / bulk / unseen
- Notification OTP routes remain available but are unused by the V1 accountant UI
- Monitored-email OTP → **410 Gone** (retired)
- Accountant create integration key → **403** (admin only)

### Admin (`require_developer_admin`)

- `POST/GET …/admin/vacation-integrations/organizations/{org_id}/integration-credentials`
- `POST …/integration-credentials/{id}/revoke`

### Integrations (org-bound `X-Api-Key`)

- `GET /integrations/vacation/mailbox-config` — notification prefs + status (not IMAP mailbox assignment)
- `POST /integrations/email/inbound-vacation` — single vacation item (compat)
- `POST /integrations/email/inbound-leave/batch` — mixed VACATION + SICK_LEAVE batch; one aggregated notification instruction
- `POST /integrations/email/events`
- `POST /integrations/mailbox/health`

Legacy global `N8N_API_KEY` is **not** accepted as org authorization.

## Historical email protection

Primary: **n8n activation watermark** (`process_after`).  
Secondary: backend `provider` + `provider_message_id` idempotency (per domain).

## Vacation and Sick Leave are separate domains

Payroll Copilot keeps **VacationRequest** and **SickLeaveRequest** as independent first-class entities
(separate DynamoDB `entity_type` / key prefixes `VAC#` vs `SICK#`). Do not merge them into a generic
LeaveRequest. Overlap and business-duplicate detection are **intra-domain only** initially
(Vacation ↔ Sick Leave for the same dates are not treated as duplicates or overlaps).

Accountant UI: `/accountant/vacations` and `/accountant/sick-leaves` are separate tabs with parallel UX.
Notification destination email is shared; vacation and sick-leave notify toggles are independent.

Batch response contract (conceptual):

```json
{
  "received_count": 5,
  "duplicate_count": 2,
  "results": [
    {
      "classification": "VACATION",
      "request_id": "...",
      "outcome": "SUCCESS",
      "review_status": "pending_approval",
      "employee_name": "...",
      "start_date": "...",
      "end_date": "...",
      "attention_codes": [],
      "summary": "..."
    }
  ],
  "notification": {
    "should_send": true,
    "to_email": "payroll@example.com",
    "subject": "Payroll Copilot — New leave requests",
    "body_text": "..."
  }
}
```

Duplicates are counted but omitted from `results`. If every item is a duplicate (or nothing
notify-worthy remains after prefs/recipient checks), `notification.should_send` is `false`.
Payroll Copilot remains SoT for matching, validation, duplicates, overlaps, and notification content;
n8n remains the email/orchestration layer and only executes the returned send instruction.
