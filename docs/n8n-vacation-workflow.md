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

## Recommended flow (batch leave ingest)

1. **IMAP Email Trigger** with Action = Nothing (or equivalent unread-safe poll).
2. **Filter** by `process_after` watermark.
3. Normalize / deterministic pre-check.
4. Optional: `GET /vacation/mailbox-config` for notification prefs / status bootstrap (not for IMAP target).
5. Event `EMAIL_OBSERVED` → `POST /email/events` (optional analytics).
6. Classify + extract: `VACATION | SICK_LEAVE | OTHER | UNCERTAIN`.
7. **Filter** to `VACATION` or `SICK_LEAVE` only (drop OTHER/UNCERTAIN — do not create domain records).
8. **Aggregate** the filtered items for this poll cycle.
9. **ONE** HTTP call: `POST /email/inbound-leave/batch` with `{ "items": [ ... ] }`.
10. Inspect `notification.should_send`:
    - `false` → end (typical when the batch is all duplicates/ignored, prefs off, or no recipient).
    - `true` → send **ONE** email using `notification.to_email`, `notification.subject`, `notification.body_text`.
11. Parallel cron: `POST /mailbox/health` with monitored email + `ok|error`.

### Compatibility

`POST /email/inbound-vacation` remains available for single-vacation integrations.
Prefer the batch endpoint for mixed vacation + sick leave workflows.

### What n8n must NOT do

- Employee matching, duplicate/overlap decisions, attention-code taxonomy
- Choosing `organization_id` (API key resolves tenant)
- Building business notification content or notification preference logic
- Sending more than one summary email per batch response

## Retry

Same `provider_message_id` within a domain → `DUPLICATE` (counted, not listed as a new result in batch).  
Stable `event_id` across retries so counters are not inflated.
