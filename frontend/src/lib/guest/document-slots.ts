export type GuestDocumentSlotId =
  | 'payslip'
  | 'attendance'
  | 'contract'
  | 'national_id'
  | 'bank_details'
  | 'tax_form';

export type GuestDocumentSlot = {
  id: GuestDocumentSlotId;
  labelKey: string;
  whyKey: string;
  backendType: 'payslip' | 'attendance' | 'contract' | 'national_id' | 'bank_details' | 'tax_form';
  accept: string;
  optional?: boolean;
  /** When false, hidden from the current guest landing/upload UX (architecture retained). */
  guestEnabled?: boolean;
};

/**
 * Full guest document catalog (extensible).
 * Attendance / bank / tax remain defined for classification but are not guest-enabled now.
 */
export const GUEST_DOCUMENT_SLOTS: GuestDocumentSlot[] = [
  {
    id: 'payslip',
    labelKey: 'slots.payslip',
    whyKey: 'slots.payslipWhy',
    backendType: 'payslip',
    accept: '.pdf,.png,.jpg,.jpeg',
    guestEnabled: true,
  },
  {
    id: 'attendance',
    labelKey: 'slots.attendance',
    whyKey: 'slots.attendanceWhy',
    backendType: 'attendance',
    accept: '.pdf,.xlsx,.csv',
    optional: true,
    guestEnabled: false,
  },
  {
    id: 'contract',
    labelKey: 'slots.contract',
    whyKey: 'slots.contractWhy',
    backendType: 'contract',
    accept: '.pdf',
    optional: true,
    guestEnabled: true,
  },
  {
    id: 'national_id',
    labelKey: 'slots.national_id',
    whyKey: 'slots.nationalIdWhy',
    backendType: 'national_id',
    accept: '.pdf,.png,.jpg,.jpeg',
    optional: true,
    guestEnabled: true,
  },
  {
    id: 'bank_details',
    labelKey: 'slots.bank_details',
    whyKey: 'slots.bankDetailsWhy',
    backendType: 'bank_details',
    accept: '.pdf,.png,.jpg,.jpeg',
    optional: true,
    guestEnabled: false,
  },
  {
    id: 'tax_form',
    labelKey: 'slots.tax_form',
    whyKey: 'slots.taxFormWhy',
    backendType: 'tax_form',
    accept: '.pdf,.png,.jpg,.jpeg',
    optional: true,
    guestEnabled: false,
  },
];

/** Currently exposed guest document types (payslip, national ID, employment contract). */
export const GUEST_ACTIVE_DOCUMENT_SLOTS: GuestDocumentSlot[] = GUEST_DOCUMENT_SLOTS.filter(
  (slot) => slot.guestEnabled !== false,
);

export function isGuestAttendanceHidden(): boolean {
  return !GUEST_DOCUMENT_SLOTS.some((slot) => slot.id === 'attendance' && slot.guestEnabled !== false);
}
