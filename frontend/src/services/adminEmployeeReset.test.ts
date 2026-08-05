import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./api', () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from './api';
import {
  RESET_EMPLOYEE_DATA_PHRASE,
  adminEmployeeResetService,
} from './adminEmployeeReset';

describe('adminEmployeeResetService', () => {
  beforeEach(() => {
    vi.mocked(apiRequest).mockReset();
  });

  it('posts confirmation phrase and destruction flag', async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce({
      organization_id: 'org-1',
      confirmation_phrase_required: RESET_EMPLOYEE_DATA_PHRASE,
      idempotent: false,
      counts: { employees: 0 },
    });

    await adminEmployeeResetService.resetEmployeeData({
      confirmationPhrase: RESET_EMPLOYEE_DATA_PHRASE,
      confirmDestruction: true,
    });

    expect(apiRequest).toHaveBeenCalledWith('/admin/reset-employee-data', {
      method: 'POST',
      portalAuth: true,
      body: JSON.stringify({
        confirmation_phrase: RESET_EMPLOYEE_DATA_PHRASE,
        confirm_destruction: true,
      }),
    });
  });
});
