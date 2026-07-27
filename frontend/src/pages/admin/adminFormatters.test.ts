import { describe, expect, it } from 'vitest';
import { formatRagMetric } from './adminFormatters';

describe('formatRagMetric', () => {
  it('shows Unavailable when metric status is not ok', () => {
    expect(formatRagMetric({ value: 0, status: 'unavailable' }).label).toBe('Unavailable');
    expect(formatRagMetric({ value: null, status: 'ok' }).unavailable).toBe(true);
  });

  it('formats ok metrics as percentages', () => {
    expect(formatRagMetric({ value: 0.812, status: 'ok' }).label).toBe('81.2%');
    expect(formatRagMetric({ value: 0.812, status: 'ok' }).unavailable).toBe(false);
  });
});
