import { BatchNavigationGuardProvider } from '../features/accountant/BatchNavigationGuard';
import { PortalShell } from './PortalShell';
import { ACCOUNTANT_PORTAL } from './portalConfig';

export function AccountantLayout() {
  return (
    <BatchNavigationGuardProvider>
      <PortalShell config={ACCOUNTANT_PORTAL} />
    </BatchNavigationGuardProvider>
  );
}
