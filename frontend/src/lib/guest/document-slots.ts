export type GuestDocumentSlotId = 'payslip' | 'attendance' | 'contract' | 'national_id';

export type GuestDocumentSlot = {
  id: GuestDocumentSlotId;
  label: string;
  backendType: 'payslip' | 'attendance' | 'contract' | 'national_id';
  accept: string;
  optional?: boolean;
  why: string;
};

export const GUEST_DOCUMENT_SLOTS: GuestDocumentSlot[] = [
  {
    id: 'payslip',
    label: 'Payslip',
    backendType: 'payslip',
    accept: '.pdf,.png,.jpg,.jpeg',
    why: 'Required to validate salary, deductions, overtime, and payslip line items.',
  },
  {
    id: 'attendance',
    label: 'Attendance Report',
    backendType: 'attendance',
    accept: '.pdf,.xlsx,.csv',
    optional: true,
    why: 'Helps verify working hours, overtime, and leave when attendance checks are connected.',
  },
  {
    id: 'contract',
    label: 'Employment Agreement',
    backendType: 'contract',
    accept: '.pdf',
    optional: true,
    why: 'Allows validation against contractual obligations when contract analysis is connected.',
  },
  {
    id: 'national_id',
    label: 'Israeli ID',
    backendType: 'national_id',
    accept: '.pdf,.png,.jpg,.jpeg',
    optional: true,
    why: 'Supports identity-dependent tax and benefit checks when those validations are connected.',
  },
];
