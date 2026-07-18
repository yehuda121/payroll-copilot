import { useCallback } from 'react';
import { useEmployeeSession } from '../auth/EmployeeSessionContext';
import {
  buildEmployeeContext,
  type BuiltEmployeeContext,
} from '../lib/employee/employee-context-builder';

/**
 * Read-only Employee Context Builder.
 * Inspects the in-memory Employee Session Context only — never calls the backend.
 * Not wired to Employee AI Chat (Step 2 infrastructure).
 */
export function useEmployeeContextBuilder() {
  const session = useEmployeeSession();

  const build = useCallback((): BuiltEmployeeContext => {
    return buildEmployeeContext(session.inspect());
  }, [session]);

  return { build };
}
