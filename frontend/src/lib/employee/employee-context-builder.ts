import type { EmployeeSessionInspectSnapshot } from '../../auth/EmployeeSessionContext';
import type {
  EmployeeDocumentCenter,
  EmployeeDocumentForm,
  EmployeeMe,
  PayrollMonthDetail,
  PayrollMonthsResponse,
} from '../../services/employeePortal';
import type { GuestValidationReport } from '../../types/validation-report';

/**
 * Extensible catalog of known employee document types.
 * Add entries here when new persistent document kinds join the portal —
 * the builder will report Available/Missing without screen-specific code.
 */
export const EMPLOYEE_CONTEXT_DOCUMENT_TYPES: ReadonlyArray<{
  documentType: string;
  label: string;
}> = [
  { documentType: 'national_id', label: 'ID Card' },
  { documentType: 'id_appendix', label: 'ID Appendix' },
  { documentType: 'contract', label: 'Employment Contract' },
];

export type EmployeeContextResourceStatus = 'available' | 'missing';

export type EmployeeContextResourceKind =
  | 'employee_profile'
  | 'payroll_months_list'
  | 'payroll_month_detail'
  | 'employee_documents'
  | 'document_form'
  | 'validation_report'
  | (string & {});

export type EmployeeContextResource = {
  /** Stable machine key, e.g. `payroll_month_detail:2026-05`. */
  key: string;
  kind: EmployeeContextResourceKind;
  /** Human-readable inventory label. */
  label: string;
  status: EmployeeContextResourceStatus;
  /** Present only when status is `available`. */
  data?: unknown;
  meta?: Record<string, unknown>;
};

export type EmployeeContextAvailabilityRow = {
  label: string;
  status: 'Available' | 'Missing';
};

/**
 * Prepared employee context for future AI use.
 * Built only from the in-memory session cache — never fetches.
 */
export type BuiltEmployeeContext = {
  builtAt: string;
  resources: EmployeeContextResource[];
  profile: EmployeeMe | null;
  payrollMonthsLists: PayrollMonthsResponse[];
  payrollMonthDetails: PayrollMonthDetail[];
  documentCenter: EmployeeDocumentCenter | null;
  documentForms: EmployeeDocumentForm[];
  validationReports: Array<{ runId: string; report: GuestValidationReport }>;
  getResource: (key: string) => EmployeeContextResource | undefined;
  isAvailable: (key: string) => boolean;
  listByKind: (kind: EmployeeContextResourceKind) => EmployeeContextResource[];
  /** Flat inventory suitable for prompts / debugging (Available vs Missing). */
  availabilitySummary: () => EmployeeContextAvailabilityRow[];
};

function padMonth(month: number): string {
  return String(month).padStart(2, '0');
}

function payrollMonthLabel(year: number, month: number): string {
  return `Payroll Month ${year}-${padMonth(month)}`;
}

function payrollMonthDetailKey(year: number, month: number): string {
  return `payroll_month_detail:${year}-${padMonth(month)}`;
}

function pushResource(
  resources: EmployeeContextResource[],
  byKey: Map<string, EmployeeContextResource>,
  resource: EmployeeContextResource,
): void {
  const existing = byKey.get(resource.key);
  if (existing && existing.status === 'available' && resource.status === 'missing') {
    return;
  }
  byKey.set(resource.key, resource);
  const idx = resources.findIndex((row) => row.key === resource.key);
  if (idx >= 0) {
    resources[idx] = resource;
  } else {
    resources.push(resource);
  }
}

/**
 * Build employee context solely by inspecting a session cache snapshot.
 * Missing data is reported as unavailable — never loaded here.
 */
export function buildEmployeeContext(
  snapshot: EmployeeSessionInspectSnapshot,
  options?: { now?: () => Date },
): BuiltEmployeeContext {
  const now = options?.now ?? (() => new Date());
  const resources: EmployeeContextResource[] = [];
  const byKey = new Map<string, EmployeeContextResource>();

  pushResource(resources, byKey, {
    key: 'employee_profile',
    kind: 'employee_profile',
    label: 'Employee Profile',
    status: snapshot.profile ? 'available' : 'missing',
    data: snapshot.profile ?? undefined,
  });

  pushResource(resources, byKey, {
    key: 'employee_documents',
    kind: 'employee_documents',
    label: 'Employee Documents',
    status: snapshot.documentCenter ? 'available' : 'missing',
    data: snapshot.documentCenter ?? undefined,
  });

  const formsByType = new Map<string, EmployeeDocumentForm>();
  for (const form of snapshot.documentForms) {
    formsByType.set(form.document_type, form);
    pushResource(resources, byKey, {
      key: `document_form:${form.document_type}`,
      kind: 'document_form',
      label: documentTypeLabel(form.document_type),
      status: 'available',
      data: form,
      meta: { documentType: form.document_type, documentId: form.document_id },
    });
  }

  const centerByType = new Map(
    (snapshot.documentCenter?.persistent_documents ?? []).map((item) => [
      item.document_type,
      item,
    ]),
  );

  for (const entry of EMPLOYEE_CONTEXT_DOCUMENT_TYPES) {
    const key = `document_form:${entry.documentType}`;
    if (byKey.has(key) && byKey.get(key)?.status === 'available') {
      continue;
    }
    const centerItem = centerByType.get(entry.documentType);
    const form = formsByType.get(entry.documentType);
    if (form) {
      pushResource(resources, byKey, {
        key,
        kind: 'document_form',
        label: entry.label,
        status: 'available',
        data: form,
        meta: { documentType: entry.documentType, documentId: form.document_id },
      });
      continue;
    }
    // Document center proves the binary exists, but the digital form may still be missing.
    // Form-oriented inventory stays Missing unless a form payload was cached.
    // Surface document presence separately when the center knows about it.
    if (centerItem?.exists) {
      pushResource(resources, byKey, {
        key: `employee_document:${entry.documentType}`,
        kind: 'employee_documents',
        label: `${entry.label} (file)`,
        status: 'available',
        data: centerItem,
        meta: { documentType: entry.documentType, documentId: centerItem.document_id },
      });
    }
    pushResource(resources, byKey, {
      key,
      kind: 'document_form',
      label: entry.label,
      status: 'missing',
      meta: { documentType: entry.documentType },
    });
  }

  for (const list of snapshot.payrollMonthsByYear) {
    pushResource(resources, byKey, {
      key: `payroll_months_list:${list.year}`,
      kind: 'payroll_months_list',
      label: `Payroll Months ${list.year}`,
      status: 'available',
      data: list,
      meta: { year: list.year },
    });
  }

  const loadedDetailKeys = new Set(
    snapshot.payrollMonthDetails.map((detail) =>
      payrollMonthDetailKey(detail.year, detail.month),
    ),
  );

  for (const detail of snapshot.payrollMonthDetails) {
    const key = payrollMonthDetailKey(detail.year, detail.month);
    pushResource(resources, byKey, {
      key,
      kind: 'payroll_month_detail',
      label: payrollMonthLabel(detail.year, detail.month),
      status: 'available',
      data: detail,
      meta: { year: detail.year, month: detail.month },
    });

    const runId = detail.latest_validation.validation_run_id;
    if (detail.latest_validation.exists && runId) {
      pushResource(resources, byKey, {
        key: `validation_report:${runId}`,
        kind: 'validation_report',
        label: `Validation ${detail.year}-${padMonth(detail.month)}`,
        status: 'available',
        data: detail.latest_validation,
        meta: {
          runId,
          year: detail.year,
          month: detail.month,
          source: 'payroll_month_detail',
        },
      });
    }
  }

  // When a year list is cached, report months whose details were not loaded yet.
  for (const list of snapshot.payrollMonthsByYear) {
    for (const monthRow of list.months) {
      const key = payrollMonthDetailKey(list.year, monthRow.month);
      if (loadedDetailKeys.has(key)) continue;
      pushResource(resources, byKey, {
        key,
        kind: 'payroll_month_detail',
        label: payrollMonthLabel(list.year, monthRow.month),
        status: 'missing',
        meta: { year: list.year, month: monthRow.month },
      });
    }
  }

  for (const { runId, report } of snapshot.validationReports) {
    pushResource(resources, byKey, {
      key: `validation_report:${runId}`,
      kind: 'validation_report',
      label: `Validation ${runId}`,
      status: 'available',
      data: report,
      meta: { runId, source: 'session_cache' },
    });
  }

  const getResource = (key: string) => byKey.get(key);

  return {
    builtAt: now().toISOString(),
    resources: [...resources],
    profile: snapshot.profile,
    payrollMonthsLists: [...snapshot.payrollMonthsByYear],
    payrollMonthDetails: [...snapshot.payrollMonthDetails],
    documentCenter: snapshot.documentCenter,
    documentForms: [...snapshot.documentForms],
    validationReports: [...snapshot.validationReports],
    getResource,
    isAvailable: (key: string) => getResource(key)?.status === 'available',
    listByKind: (kind: EmployeeContextResourceKind) =>
      resources.filter((row) => row.kind === kind),
    availabilitySummary: () =>
      resources.map((row) => ({
        label: row.label,
        status: row.status === 'available' ? 'Available' : 'Missing',
      })),
  };
}

function documentTypeLabel(documentType: string): string {
  const known = EMPLOYEE_CONTEXT_DOCUMENT_TYPES.find(
    (entry) => entry.documentType === documentType,
  );
  return known?.label ?? `Document Form (${documentType})`;
}
