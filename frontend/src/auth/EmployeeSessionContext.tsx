import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  type ReactNode,
} from 'react';
import type {
  EmployeeDocumentCenter,
  EmployeeDocumentForm,
  EmployeeMe,
  PayrollMonthDetail,
  PayrollMonthsResponse,
} from '../services/employeePortal';
import type { GuestValidationReport } from '../types/validation-report';

function payrollMonthKey(year: number, month: number): string {
  return `${year}-${month}`;
}

/**
 * In-memory session cache for the authenticated employee.
 * Stores only data already fetched by screens. Never fetches on its own.
 * Cleared on logout / provider unmount. Not persisted to storage.
 */
export type EmployeeSessionStore = {
  /** `/employees/me` profile when already loaded. */
  profile: EmployeeMe | null;
  /** Year → payroll months list response. */
  payrollMonthsByYear: Map<number, PayrollMonthsResponse>;
  /** `${year}-${month}` → month workspace detail. */
  payrollMonthDetails: Map<string, PayrollMonthDetail>;
  /** Document center listing when already loaded. */
  documentCenter: EmployeeDocumentCenter | null;
  /** Document id → digital form payload. */
  documentFormsById: Map<string, EmployeeDocumentForm>;
  /** Document type → digital form (for form-only ID shells). */
  documentFormsByType: Map<string, EmployeeDocumentForm>;
  /** Validation run id → adapted report when already loaded. */
  validationReportsByRunId: Map<string, GuestValidationReport>;
};

export type EmployeeSessionContextValue = {
  /** Snapshot accessors — never trigger network I/O. */
  getProfile: () => EmployeeMe | null;
  setProfile: (profile: EmployeeMe) => void;
  invalidateProfile: () => void;

  getPayrollMonths: (year: number) => PayrollMonthsResponse | undefined;
  setPayrollMonths: (response: PayrollMonthsResponse) => void;
  invalidatePayrollMonths: (year?: number) => void;

  getPayrollMonthDetail: (year: number, month: number) => PayrollMonthDetail | undefined;
  setPayrollMonthDetail: (detail: PayrollMonthDetail) => void;
  invalidatePayrollMonth: (year: number, month: number) => void;

  getDocumentCenter: () => EmployeeDocumentCenter | null;
  setDocumentCenter: (center: EmployeeDocumentCenter) => void;
  invalidateDocumentCenter: () => void;

  getDocumentForm: (documentId: string) => EmployeeDocumentForm | undefined;
  setDocumentForm: (form: EmployeeDocumentForm) => void;
  invalidateDocumentForm: (documentId: string) => void;

  getDocumentFormByType: (documentType: string) => EmployeeDocumentForm | undefined;
  setDocumentFormByType: (documentType: string, form: EmployeeDocumentForm) => void;
  invalidateDocumentFormByType: (documentType: string) => void;

  getValidationReport: (runId: string) => GuestValidationReport | undefined;
  setValidationReport: (runId: string, report: GuestValidationReport) => void;
  invalidateValidationReport: (runId: string) => void;

  /**
   * Read-only copy of whatever is already in the session cache.
   * Never fetches. Safe for Context Builder / future AI prep layers.
   */
  inspect: () => EmployeeSessionInspectSnapshot;

  /** Drop every cached object for this employee session. */
  clear: () => void;
};

/** Plain snapshot of cached session data (no Maps; safe to inspect freely). */
export type EmployeeSessionInspectSnapshot = {
  profile: EmployeeMe | null;
  payrollMonthsByYear: PayrollMonthsResponse[];
  payrollMonthDetails: PayrollMonthDetail[];
  documentCenter: EmployeeDocumentCenter | null;
  documentForms: EmployeeDocumentForm[];
  validationReports: Array<{ runId: string; report: GuestValidationReport }>;
};

const EmployeeSessionContext = createContext<EmployeeSessionContextValue | null>(null);

function createEmptyStore(): EmployeeSessionStore {
  return {
    profile: null,
    payrollMonthsByYear: new Map(),
    payrollMonthDetails: new Map(),
    documentCenter: null,
    documentFormsById: new Map(),
    documentFormsByType: new Map(),
    validationReportsByRunId: new Map(),
  };
}

export function EmployeeSessionProvider({ children }: { children: ReactNode }) {
  const storeRef = useRef<EmployeeSessionStore>(createEmptyStore());

  const clear = useCallback(() => {
    storeRef.current = createEmptyStore();
  }, []);

  const getProfile = useCallback(() => storeRef.current.profile, []);
  const setProfile = useCallback((profile: EmployeeMe) => {
    storeRef.current.profile = profile;
  }, []);
  const invalidateProfile = useCallback(() => {
    storeRef.current.profile = null;
  }, []);

  const getPayrollMonths = useCallback(
    (year: number) => storeRef.current.payrollMonthsByYear.get(year),
    [],
  );
  const setPayrollMonths = useCallback((response: PayrollMonthsResponse) => {
    storeRef.current.payrollMonthsByYear.set(response.year, response);
  }, []);
  const invalidatePayrollMonths = useCallback((year?: number) => {
    if (year == null) {
      storeRef.current.payrollMonthsByYear.clear();
      return;
    }
    storeRef.current.payrollMonthsByYear.delete(year);
  }, []);

  const getPayrollMonthDetail = useCallback(
    (year: number, month: number) =>
      storeRef.current.payrollMonthDetails.get(payrollMonthKey(year, month)),
    [],
  );
  const setPayrollMonthDetail = useCallback((detail: PayrollMonthDetail) => {
    storeRef.current.payrollMonthDetails.set(
      payrollMonthKey(detail.year, detail.month),
      detail,
    );
  }, []);
  const invalidatePayrollMonth = useCallback((year: number, month: number) => {
    storeRef.current.payrollMonthDetails.delete(payrollMonthKey(year, month));
    storeRef.current.payrollMonthsByYear.delete(year);
  }, []);

  const getDocumentCenter = useCallback(() => storeRef.current.documentCenter, []);
  const setDocumentCenter = useCallback((center: EmployeeDocumentCenter) => {
    storeRef.current.documentCenter = center;
  }, []);
  const invalidateDocumentCenter = useCallback(() => {
    storeRef.current.documentCenter = null;
  }, []);

  const getDocumentForm = useCallback(
    (documentId: string) => storeRef.current.documentFormsById.get(documentId),
    [],
  );
  const setDocumentForm = useCallback((form: EmployeeDocumentForm) => {
    storeRef.current.documentFormsById.set(form.document_id, form);
    storeRef.current.documentFormsByType.set(form.document_type, form);
  }, []);
  const invalidateDocumentForm = useCallback((documentId: string) => {
    const existing = storeRef.current.documentFormsById.get(documentId);
    storeRef.current.documentFormsById.delete(documentId);
    if (existing) {
      storeRef.current.documentFormsByType.delete(existing.document_type);
    }
  }, []);

  const getDocumentFormByType = useCallback(
    (documentType: string) => storeRef.current.documentFormsByType.get(documentType),
    [],
  );
  const setDocumentFormByType = useCallback(
    (documentType: string, form: EmployeeDocumentForm) => {
      storeRef.current.documentFormsByType.set(documentType, form);
      storeRef.current.documentFormsById.set(form.document_id, form);
    },
    [],
  );
  const invalidateDocumentFormByType = useCallback((documentType: string) => {
    const existing = storeRef.current.documentFormsByType.get(documentType);
    storeRef.current.documentFormsByType.delete(documentType);
    if (existing) {
      storeRef.current.documentFormsById.delete(existing.document_id);
    }
  }, []);

  const getValidationReport = useCallback(
    (runId: string) => storeRef.current.validationReportsByRunId.get(runId),
    [],
  );
  const setValidationReport = useCallback((runId: string, report: GuestValidationReport) => {
    storeRef.current.validationReportsByRunId.set(runId, report);
  }, []);
  const invalidateValidationReport = useCallback((runId: string) => {
    storeRef.current.validationReportsByRunId.delete(runId);
  }, []);

  const inspect = useCallback((): EmployeeSessionInspectSnapshot => {
    const store = storeRef.current;
    const formsById = new Map<string, EmployeeDocumentForm>();
    for (const form of store.documentFormsById.values()) {
      formsById.set(form.document_id, form);
    }
    for (const form of store.documentFormsByType.values()) {
      formsById.set(form.document_id, form);
    }
    return {
      profile: store.profile,
      payrollMonthsByYear: Array.from(store.payrollMonthsByYear.values()),
      payrollMonthDetails: Array.from(store.payrollMonthDetails.values()),
      documentCenter: store.documentCenter,
      documentForms: Array.from(formsById.values()),
      validationReports: Array.from(store.validationReportsByRunId.entries()).map(
        ([runId, report]) => ({ runId, report }),
      ),
    };
  }, []);

  const value = useMemo<EmployeeSessionContextValue>(
    () => ({
      getProfile,
      setProfile,
      invalidateProfile,
      getPayrollMonths,
      setPayrollMonths,
      invalidatePayrollMonths,
      getPayrollMonthDetail,
      setPayrollMonthDetail,
      invalidatePayrollMonth,
      getDocumentCenter,
      setDocumentCenter,
      invalidateDocumentCenter,
      getDocumentForm,
      setDocumentForm,
      invalidateDocumentForm,
      getDocumentFormByType,
      setDocumentFormByType,
      invalidateDocumentFormByType,
      getValidationReport,
      setValidationReport,
      invalidateValidationReport,
      inspect,
      clear,
    }),
    [
      getProfile,
      setProfile,
      invalidateProfile,
      getPayrollMonths,
      setPayrollMonths,
      invalidatePayrollMonths,
      getPayrollMonthDetail,
      setPayrollMonthDetail,
      invalidatePayrollMonth,
      getDocumentCenter,
      setDocumentCenter,
      invalidateDocumentCenter,
      getDocumentForm,
      setDocumentForm,
      invalidateDocumentForm,
      getDocumentFormByType,
      setDocumentFormByType,
      invalidateDocumentFormByType,
      getValidationReport,
      setValidationReport,
      invalidateValidationReport,
      inspect,
      clear,
    ],
  );

  return (
    <EmployeeSessionContext.Provider value={value}>{children}</EmployeeSessionContext.Provider>
  );
}

export function useEmployeeSession(): EmployeeSessionContextValue {
  const ctx = useContext(EmployeeSessionContext);
  if (!ctx) {
    throw new Error('useEmployeeSession must be used within EmployeeSessionProvider');
  }
  return ctx;
}
