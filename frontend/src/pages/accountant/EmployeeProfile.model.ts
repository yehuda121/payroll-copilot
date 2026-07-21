import type { AuditLogItem, ExpectedDocumentAvailability } from '../../types/employee';

export type ProfileDocItem = {
  type_key: string;
  label: string;
  availability: ExpectedDocumentAvailability;
  supports_period: boolean;
  document_id?: string;
  period_year?: number | null;
  period_month?: number | null;
  fixture_classification?: string | null;
  gross_salary?: number | null;
  net_salary?: number | null;
};

export type ProfileCollection = {
  key: string;
  label: string;
  items: ProfileDocItem[];
};

export type MonthRow = {
  year: number;
  month: number;
  label: string;
  payslip: ExpectedDocumentAvailability;
  attendance: ExpectedDocumentAvailability;
  validation_status: string;
  missing_documents: string[];
  warnings: string[];
};

export type ProfilePayload = {
  employee: {
    id: string;
    employee_number: string;
    full_name: string;
    first_name: string;
    last_name: string;
    email?: string | null;
    department?: string | null;
    employment_type: string;
    salary_type: string;
    status: string;
    national_id_masked?: string | null;
    contract_start_date?: string;
    base_salary_or_rate?: number | null;
  };
  document_collections: ProfileCollection[];
  monthly_history: MonthRow[];
  validation_history: unknown[];
  findings: unknown[];
  timeline: AuditLogItem[];
  audit_log: AuditLogItem[];
  validation_modules: Array<{
    key: string;
    label: string;
    description: string;
    enabled: boolean;
  }>;
};

export type DocTypeCardModel = {
  typeKey: string;
  supportsPeriod: boolean;
  availability: ExpectedDocumentAvailability;
  documents: ProfileDocItem[];
  latest: ProfileDocItem | null;
};

export type MonthTone = 'complete' | 'missing' | 'failed' | 'empty';

export const MONTH_KEYS = [
  'jan',
  'feb',
  'mar',
  'apr',
  'may',
  'jun',
  'jul',
  'aug',
  'sep',
  'oct',
  'nov',
  'dec',
] as const;

export function groupDocumentTypes(collections: ProfileCollection[]): DocTypeCardModel[] {
  const byType = new Map<string, DocTypeCardModel>();
  for (const collection of collections) {
    for (const item of collection.items) {
      let card = byType.get(item.type_key);
      if (!card) {
        card = {
          typeKey: item.type_key,
          supportsPeriod: item.supports_period,
          availability: item.availability,
          documents: [],
          latest: null,
        };
        byType.set(item.type_key, card);
      }
      if (item.document_id) {
        card.documents.push(item);
      }
    }
  }

  return Array.from(byType.values()).map((card) => {
    const docs = [...card.documents].sort((a, b) => {
      const ay = a.period_year ?? 0;
      const by = b.period_year ?? 0;
      if (ay !== by) return by - ay;
      return (b.period_month ?? 0) - (a.period_month ?? 0);
    });
    return {
      ...card,
      documents: docs,
      latest: docs[0] ?? null,
      availability: docs.length > 0 ? 'available' : 'missing',
    };
  });
}

export function monthTone(row: MonthRow | undefined): MonthTone {
  if (!row) return 'empty';
  if (row.validation_status === 'failed' || row.validation_status === 'critical') {
    return 'failed';
  }
  if (row.missing_documents.length > 0) return 'missing';
  return 'complete';
}

export function documentsForPeriod(
  cards: DocTypeCardModel[],
  year: number,
  month: number,
): Array<{ card: DocTypeCardModel; docs: ProfileDocItem[]; available: boolean }> {
  return cards.map((card) => {
    if (!card.supportsPeriod) {
      return {
        card,
        docs: card.documents,
        available: card.documents.length > 0,
      };
    }
    const docs = card.documents.filter(
      (doc) => doc.period_year === year && doc.period_month === month,
    );
    return { card, docs, available: docs.length > 0 };
  });
}
