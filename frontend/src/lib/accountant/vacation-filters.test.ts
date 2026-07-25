import { describe, expect, it } from 'vitest';
import { vacationIntervalsOverlap } from './vacation-filters';

describe('vacationIntervalsOverlap', () => {
  it('matches when ranges partially overlap', () => {
    expect(vacationIntervalsOverlap('2026-08-01', '2026-08-10', '2026-08-05', '2026-08-20')).toBe(
      true,
    );
  });

  it('matches when vacation is fully inside the filter', () => {
    expect(vacationIntervalsOverlap('2026-08-05', '2026-08-07', '2026-08-01', '2026-08-31')).toBe(
      true,
    );
  });

  it('rejects adjacent non-overlapping ranges', () => {
    expect(vacationIntervalsOverlap('2026-08-01', '2026-08-10', '2026-08-11', '2026-08-20')).toBe(
      false,
    );
  });

  it('rejects incomplete inputs', () => {
    expect(vacationIntervalsOverlap('2026-08-01', null, '2026-08-01', '2026-08-31')).toBe(false);
  });
});
