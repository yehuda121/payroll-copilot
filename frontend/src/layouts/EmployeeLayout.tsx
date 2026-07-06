import { PortalShell } from './PortalShell';
import { EMPLOYEE_PORTAL } from './portalConfig';

export function EmployeeLayout() {
  return <PortalShell config={EMPLOYEE_PORTAL} />;
}
