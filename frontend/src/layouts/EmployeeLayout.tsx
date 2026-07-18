import { useAuth } from '../auth/AuthContext';
import { EmployeeSessionProvider } from '../auth/EmployeeSessionContext';
import { PortalShell } from './PortalShell';
import { EMPLOYEE_PORTAL } from './portalConfig';

export function EmployeeLayout() {
  const { session } = useAuth();
  // Remount (and wipe in-memory cache) when the authenticated employee identity changes.
  const sessionKey = session?.user.id ?? 'employee';

  return (
    <EmployeeSessionProvider key={sessionKey}>
      <PortalShell config={EMPLOYEE_PORTAL} />
    </EmployeeSessionProvider>
  );
}
