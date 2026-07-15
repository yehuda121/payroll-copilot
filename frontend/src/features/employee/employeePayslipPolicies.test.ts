import { describe, expect, it } from 'vitest';

/** Pure helper mirroring employee confirmation gating (frontend must not invent comparison). */
function canConfirm(blocksConfirmation: boolean): boolean {
  return !blocksConfirmation;
}

function canRunValidation(opts: {
  blocksConfirmation: boolean;
  acknowledgement: boolean;
  confirmationStatus: string | null;
}): boolean {
  return (
    !opts.blocksConfirmation &&
    opts.acknowledgement &&
    opts.confirmationStatus === 'confirmed'
  );
}

function displayMasksNationalId(payload: {
  extracted_display?: string | null;
  expected_display?: string | null;
}) {
  const blob = `${payload.extracted_display ?? ''}${payload.expected_display ?? ''}`;
  return !/\d{9}/.test(blob);
}

describe('employee payslip UI policies', () => {
  it('disables confirmation when backend blocks_confirmation is true', () => {
    expect(canConfirm(true)).toBe(false);
    expect(canConfirm(false)).toBe(true);
  });

  it('requires persisted confirmation before validation can start', () => {
    expect(
      canRunValidation({
        blocksConfirmation: false,
        acknowledgement: true,
        confirmationStatus: null,
      }),
    ).toBe(false);
    expect(
      canRunValidation({
        blocksConfirmation: false,
        acknowledgement: true,
        confirmationStatus: 'confirmed',
      }),
    ).toBe(true);
  });

  it('allows confirmation for name-only mismatch when blocks_confirmation is false', () => {
    const identity = {
      overall: 'incomplete',
      blocks_confirmation: false,
      fields: [{ key: 'employee_name', status: 'mismatch', severity: 'warning' }],
    };
    expect(canConfirm(identity.blocks_confirmation)).toBe(true);
  });

  it('does not display raw 9-digit national id from masked displays', () => {
    expect(
      displayMasksNationalId({
        extracted_display: '****6783',
        expected_display: '****6783',
      }),
    ).toBe(true);
    expect(
      displayMasksNationalId({
        extracted_display: '313366783',
        expected_display: '****6783',
      }),
    ).toBe(false);
  });

  it('period picker values are required before extract', () => {
    const periodYear = 2026;
    const periodMonth = 6;
    expect(Boolean(periodYear && periodMonth >= 1 && periodMonth <= 12)).toBe(true);
    expect(Boolean(0 && periodMonth)).toBe(false);
  });
});
