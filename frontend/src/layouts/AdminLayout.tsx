import { PortalShell } from './PortalShell';
import { ADMIN_PORTAL } from './portalConfig';

export function AdminLayout() {
  return <PortalShell config={ADMIN_PORTAL} />;
}
