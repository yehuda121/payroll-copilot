import { describe, expect, it } from 'vitest';
import { jsonBody } from '../../services/vacations';

describe('vacationsService jsonBody', () => {
  it('serializes mark-seen payload as JSON string (not [object Object])', () => {
    const body = jsonBody({
      vacation_ids: ['11111111-1111-4111-8111-111111111111'],
      seen_before: '2026-07-25T00:00:00.000Z',
    });
    expect(typeof body).toBe('string');
    expect(body).not.toBe('[object Object]');
    expect(JSON.parse(body)).toEqual({
      vacation_ids: ['11111111-1111-4111-8111-111111111111'],
      seen_before: '2026-07-25T00:00:00.000Z',
    });
  });

  it('serializes approve and preferences payloads', () => {
    expect(JSON.parse(jsonBody({ confirm_warnings: true }))).toEqual({
      confirm_warnings: true,
    });
    expect(
      JSON.parse(
        jsonBody({
          notify_on_new_vacation: false,
          notify_on_error_or_attention: true,
        }),
      ),
    ).toEqual({
      notify_on_new_vacation: false,
      notify_on_error_or_attention: true,
    });
  });
});
