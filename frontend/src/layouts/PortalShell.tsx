import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../auth/AuthContext';
import { LanguageSelector } from '../components/ui/LanguageSelector';
import { ThemeToggle } from '../components/ui/ThemeToggle';
import { useOptionalBatchNavigationGuard } from '../features/accountant/BatchNavigationGuard';
import { useOptionalUnsavedChanges } from '../features/accountant/UnsavedChangesGuard';
import { useAppLocale } from '../hooks/useAppLocale';
import { vacationsService } from '../services/vacations';
import { sickLeavesService } from '../services/sickLeaves';
import type { PortalConfig } from '../types/navigation';
import './PortalShell.css';

type PortalShellProps = {
  config: PortalConfig;
};

export function PortalShell({ config }: PortalShellProps) {
  const { t } = useTranslation();
  const { locale, dir } = useAppLocale();
  const { session, logout } = useAuth();
  const user = session?.user;
  const navigate = useNavigate();
  const { isBatchActive } = useOptionalBatchNavigationGuard();
  const unsaved = useOptionalUnsavedChanges();
  const [vacationsUnseen, setVacationsUnseen] = useState(0);
  const [sickLeavesUnseen, setSickLeavesUnseen] = useState(0);
  const needsVacationBadge = config.navItems.some((item) => item.badgeKey === 'vacationsUnseen');
  const needsSickLeaveBadge = config.navItems.some((item) => item.badgeKey === 'sickLeavesUnseen');

  useEffect(() => {
    if (!needsVacationBadge || !session) return;
    let cancelled = false;
    const refresh = () => {
      void vacationsService
        .unseenCount()
        .then((count) => {
          if (!cancelled) setVacationsUnseen(count);
        })
        .catch(() => {
          if (!cancelled) setVacationsUnseen(0);
        });
    };
    refresh();
    const timer = window.setInterval(refresh, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [needsVacationBadge, session]);

  useEffect(() => {
    if (!needsSickLeaveBadge || !session) return;
    let cancelled = false;
    const refresh = () => {
      void sickLeavesService
        .unseenCount()
        .then((count) => {
          if (!cancelled) setSickLeavesUnseen(count);
        })
        .catch(() => {
          if (!cancelled) setSickLeavesUnseen(0);
        });
    };
    refresh();
    const timer = window.setInterval(refresh, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [needsSickLeaveBadge, session]);

  const portalName = config.portalNameKey
    ? t(config.portalNameKey)
    : (config.portalName ?? '');
  const portalSubtitle = config.portalSubtitleKey
    ? t(config.portalSubtitleKey)
    : (config.portalSubtitle ?? '');

  const handleNavClick = async (
    event: React.MouseEvent<HTMLAnchorElement>,
    path: string,
  ) => {
    if (unsaved?.isDirty) {
      event.preventDefault();
      const ok = await unsaved.confirmIfDirty();
      if (!ok) return;
      unsaved.setDirty(false);
      navigate(path);
      return;
    }
  };

  return (
    <div className="portal-shell ui-chrome-rtl" dir="rtl">
      <aside className="portal-shell__sidebar">
        <div className="portal-shell__brand">
          <span className="portal-shell__brand-mark" aria-hidden="true">
            PC
          </span>
          <div>
            <strong>{portalName}</strong>
            <span>{portalSubtitle}</span>
          </div>
        </div>
        {isBatchActive && (
          <div className="portal-shell__batch-banner" role="status">
            {t('portal.shell.batchActiveBanner')}
          </div>
        )}
        {config.showUserEmail && user?.email ? (
          <p className="portal-shell__nav-email" title={user.email}>
            {user.email}
          </p>
        ) : null}
        <nav className="portal-shell__nav" aria-label={portalName}>
          {(config.navGroups ?? [{ labelKey: '', items: config.navItems }]).map((group, groupIndex) => {
            const groupLabel = group.labelKey ? t(group.labelKey) : null;
            return (
              <div key={group.labelKey || `nav-group-${groupIndex}`} className="portal-shell__nav-group">
                {groupLabel ? (
                  <p className="portal-shell__nav-group-label" id={`portal-nav-group-${groupIndex}`}>
                    {groupLabel}
                  </p>
                ) : null}
                <div
                  className="portal-shell__nav-group-items"
                  role={groupLabel ? 'group' : undefined}
                  aria-labelledby={groupLabel ? `portal-nav-group-${groupIndex}` : undefined}
                >
                  {group.items.map((item) => {
                    const label = item.labelKey ? t(item.labelKey) : (item.label ?? item.path);
                    const badge =
                      item.badgeKey === 'vacationsUnseen' && vacationsUnseen > 0
                        ? vacationsUnseen
                        : item.badgeKey === 'sickLeavesUnseen' && sickLeavesUnseen > 0
                          ? sickLeavesUnseen
                          : null;
                    return (
                      <NavLink
                        key={item.path}
                        to={item.path}
                        end={item.path === config.basePath}
                        className={({ isActive }) =>
                          `portal-shell__nav-link${isActive ? ' portal-shell__nav-link--active' : ''}`
                        }
                        onClick={(event) => void handleNavClick(event, item.path)}
                      >
                        {badge != null ? `${label} (${badge})` : label}
                      </NavLink>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </nav>
        <div className="portal-shell__sidebar-footer">
          <Link to="/" className="portal-shell__footer-link">
            {t('common.publicSite')}
          </Link>
        </div>
      </aside>
      <div className="portal-shell__content">
        <header className="portal-shell__topbar">
          <div className="portal-shell__user">
            <span
              className="portal-shell__user-name"
              lang={locale}
              title={
                locale === 'en'
                  ? user?.fullName || undefined
                  : user?.localizedFullName || user?.fullName || undefined
              }
            >
              {locale === 'en'
                ? user?.fullName
                : (user?.localizedFullName || user?.fullName)}
            </span>
            <span className="portal-shell__user-role">
              {user?.role ? t(`common.roles.${user.role}`) : ''}
            </span>
          </div>
          <div className="portal-shell__topbar-actions">
            <LanguageSelector />
            <ThemeToggle />
            <button type="button" className="btn btn--ghost" onClick={logout}>
              {t('common.logout')}
            </button>
          </div>
        </header>
        <main className="portal-shell__main" dir={dir}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
