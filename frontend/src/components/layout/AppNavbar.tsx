import { useEffect, useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { APP_NAME, APP_NAME_SHORT } from '../../config/brand';
import { LanguageSelector } from '../ui/LanguageSelector';
import { ThemeToggle } from '../ui/ThemeToggle';
import { CloseIcon, MenuIcon } from '../ui/icons';
import { PageContainer } from './PageContainer';

type AppNavbarProps = {
  /** Show login/signup (public). Portal shells can hide these. */
  showAuthLinks?: boolean;
};

/**
 * Application navbar with a fixed Hebrew (RTL) chrome layout.
 * Logo stays on the right and actions on the left in every language;
 * only page content follows document RTL/LTR.
 */
export function AppNavbar({ showAuthLinks = true }: AppNavbarProps) {
  const { t } = useTranslation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuId = useId();

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenuOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menuOpen]);

  useEffect(() => {
    document.body.classList.toggle('nav-menu-open', menuOpen);
    return () => document.body.classList.remove('nav-menu-open');
  }, [menuOpen]);

  return (
    <header className="app-navbar ui-chrome-rtl" dir="rtl">
      <PageContainer className="app-navbar__inner" width="wide">
        <Link to="/" className="app-navbar__brand" onClick={() => setMenuOpen(false)}>
          <span className="app-navbar__mark" aria-hidden="true">
            {APP_NAME_SHORT}
          </span>
          <span className="app-navbar__name">{APP_NAME}</span>
        </Link>

        <div className="app-navbar__actions">
          <div className="app-navbar__chrome-controls">
            <LanguageSelector />
            <ThemeToggle />
          </div>
          <nav className="app-navbar__desktop" aria-label={t('common.primaryNav')}>
            {showAuthLinks ? (
              <>
                <Link to="/login" className="btn btn--ghost">
                  {t('common.login')}
                </Link>
                <Link to="/signup" className="btn btn--primary">
                  {t('common.signup')}
                </Link>
              </>
            ) : null}
          </nav>
          {showAuthLinks ? (
            <button
              type="button"
              className="btn btn--ghost btn--icon app-navbar__menu-btn"
              aria-expanded={menuOpen}
              aria-controls={menuId}
              aria-label={menuOpen ? t('common.closeMenu') : t('common.openMenu')}
              onClick={() => setMenuOpen((open) => !open)}
            >
              {menuOpen ? <CloseIcon aria-hidden="true" /> : <MenuIcon aria-hidden="true" />}
            </button>
          ) : null}
        </div>
      </PageContainer>

      {showAuthLinks ? (
        <div
          id={menuId}
          className={`app-navbar__drawer ${menuOpen ? 'is-open' : ''}`}
          hidden={!menuOpen}
        >
          <PageContainer className="app-navbar__drawer-inner" width="wide">
            <div className="app-navbar__drawer-auth">
              <Link
                to="/login"
                className="btn btn--secondary"
                onClick={() => setMenuOpen(false)}
              >
                {t('common.login')}
              </Link>
              <Link
                to="/signup"
                className="btn btn--primary"
                onClick={() => setMenuOpen(false)}
              >
                {t('common.signup')}
              </Link>
            </div>
          </PageContainer>
        </div>
      ) : null}
    </header>
  );
}
