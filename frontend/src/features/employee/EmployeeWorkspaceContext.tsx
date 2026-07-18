import { createContext, useContext, type ReactNode } from 'react';
import { employeePortalService } from '../../services/employeePortal';

export type EmployeeWorkspaceApi = typeof employeePortalService;

export type EmployeeWorkspaceScope = {
  api: EmployeeWorkspaceApi;
  basePath: string;
  employeeNumber?: string;
  employeeName?: string;
  backPath?: string;
  mode: 'employee' | 'accountant';
  batchReview?: {
    jobId: string;
    itemId: string;
    documentId?: string;
  };
};

const DEFAULT_SCOPE: EmployeeWorkspaceScope = {
  api: employeePortalService,
  basePath: '/employee',
  backPath: '/employee',
  mode: 'employee',
};

const EmployeeWorkspaceContext = createContext<EmployeeWorkspaceScope>(DEFAULT_SCOPE);

export function EmployeeWorkspaceProvider({
  value,
  children,
}: {
  value: EmployeeWorkspaceScope;
  children: ReactNode;
}) {
  return (
    <EmployeeWorkspaceContext.Provider value={value}>
      {children}
    </EmployeeWorkspaceContext.Provider>
  );
}

/**
 * Shared Employee workspace boundary.
 * Employee Portal uses the default `/me` API; Accountant workspace injects a
 * selected-employee API whose backend resolves the employee within the
 * authenticated accountant's organization.
 */
export function useEmployeeWorkspace(): EmployeeWorkspaceScope {
  return useContext(EmployeeWorkspaceContext);
}
