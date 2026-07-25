# n8n Vacation Email Workflow (V1)

This repository does **not** version-control n8n workflow JSON. Build one workflow **per organization**.

## V1 model

ONE ORGANIZATION → ONE manually provisioned n8n workflow → ONE org-bound `X-Api-Key` → IMAP credential configured in n8n.

Payroll Copilot does not tell n8n which IMAP mailbox to connect to.

## Prerequisites

1. Developer admin creates org integration key:  
   `POST /api/v1/admin/vacation-integrations/organizations/{organization_id}/integration-credentials`  
   Store plaintext once as header `X-Api-Key` in n8n.
2. Configure IMAP credentials for that org’s mailbox **inside n8n**.
3. Accountant may verify notification email + prefs in Payroll Copilot Vacations UI.
4. Base URL: `{API}/api/v1/integrations/...`

## Historical email watermark (required)

On workflow activation, set n8n static data:

`process_after = <activation timestamp>`

Before classification, ignore any message older than `process_after`.

Do **not** mark messages read/unread/archive/delete.

Backend idempotency (`provider` + `provider_message_id`) is the second safety layer.

## Recommended flow

1. **IMAP Email Trigger** with Action = Nothing (or equivalent unread-safe poll).
2. **Filter** by `process_after` watermark.
3. Normalize / deterministic pre-check.
4. Optional: `GET /vacation/mailbox-config` for notification prefs / status bootstrap (not for IMAP target).
5. Event `EMAIL_OBSERVED` → `POST /email/events`.
6. Classify: `VACATION | SICK_LEAVE | OTHER | UNCERTAIN`.
7. Branches:
   - OTHER → `CLASSIFIED_OTHER` → stop  
   - SICK_LEAVE → `CLASSIFIED_SICK_LEAVE` → stop (no VacationRequest)  
   - UNCERTAIN → event + optional notify → stop  
   - VACATION → continue
8. Guardrail + structured extraction.
9. `POST /email/inbound-vacation` → inspect `notification.*` → send email if instructed.
10. Report persist/attention/notification events.
11. Parallel cron: `POST /mailbox/health` with monitored email + `ok|error`.

## Retry

Same `provider_message_id` → `DUPLICATE`.  
Stable `event_id` across retries so counters are not inflated.
