/** Interval overlap used by vacation date-range filters (inclusive days). */
export function vacationIntervalsOverlap(
  vacationStart: string | null | undefined,
  vacationEnd: string | null | undefined,
  filterStart: string | null | undefined,
  filterEnd: string | null | undefined,
): boolean {
  if (!vacationStart || !vacationEnd || !filterStart || !filterEnd) return false;
  return vacationStart <= filterEnd && vacationEnd >= filterStart;
}
