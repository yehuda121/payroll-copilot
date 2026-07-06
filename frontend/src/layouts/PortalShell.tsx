import { Link, NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import type { PortalConfig } from '../types/navigation';
import './PortalShell.css';

type PortalShellProps = {
  config: PortalConfig;
};

export function PortalShell({ config }: PortalShellProps) {
  const { session, logout } = useAuth();
  const user = session?.user;

  return (
    <div className="portal-shell">
      <aside className="portal-shell__sidebar">
        <div className="portal-shell__brand">
          <span className="portal-shell__brand-mark" aria-hidden="true">
            PC
          </span>
          <div>
            <strong>{config.portalName}</strong>
            <span>{config.portalSubtitle}</span>
          </div>
        </div>
        <nav className="portal-shell__nav" aria-label={`${config.portalName} navigation`}>
          {config.navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === config.basePath}
              className={({ isActive }) =>
                `portal-shell__nav-link${isActive ? ' portal-shell__nav-link--active' : ''}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="portal-shell__sidebar-footer">
          <Link to="/" className="portal-shell__footer-link">
            Public site
          </Link>
        </div>
      </aside>
      <div className="portal-shell__content">
        <header className="portal-shell__topbar">
          <div className="portal-shell__user">
            <span className="portal-shell__user-name">{user?.fullName}</span>
            <span className="portal-shell__user-role">{user?.role.replace(/_/g, ' ')}</span>
          </div>
          <button type="button" className="btn btn--ghost" onClick={logout}>
            Log out
          </button>
        </header>
        <main className="portal-shell__main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
