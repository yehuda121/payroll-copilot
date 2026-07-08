export type GuestDocumentSlotId = 'payslip' | 'attendance' | 'contract' | 'national_id';

export type GuestDocumentSlot = {
  id: GuestDocumentSlotId;
  labelKey: string;
  whyKey: string;
  backendType: 'payslip' | 'attendance' | 'contract' | 'national_id';
  accept: string;
  optional?: boolean;
};

export const GUEST_DOCUMENT_SLOTS: GuestDocumentSlot[] = [
  {
    id: 'payslip',
    labelKey: 'slots.payslip',
    whyKey: 'slots.payslipWhy',
    backendType: 'payslip',
    accept: '.pdf,.png,.jpg,.jpeg',
  },
  {
    id: 'attendance',
    labelKey: 'slots.attendance',
    whyKey: 'slots.attendanceWhy',
    backendType: 'attendance',
    accept: '.pdf,.xlsx,.csv',
    optional: true,
  },
  {
    id: 'contract',
    labelKey: 'slots.contract',
    whyKey: 'slots.contractWhy',
    backendType: 'contract',
    accept: '.pdf',
    optional: true,
  },
  {
    id: 'national_id',
    labelKey: 'slots.national_id',
    whyKey: 'slots.nationalIdWhy',
    backendType: 'national_id',
    accept: '.pdf,.png,.jpg,.jpeg',
    optional: true,
  },
];
