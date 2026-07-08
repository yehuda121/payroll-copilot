import { Link, Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { LanguageSelector } from '../components/ui/LanguageSelector';
import './PublicLayout.css';

export function PublicLayout() {
  const { t } = useTranslation();

  return (
    <div className="public-layout">
      <header className="public-layout__header">
        <div className="public-layout__header-inner">
          <Link to="/" className="public-layout__logo">
            <span className="public-layout__logo-mark">PC</span>
            <span>{t('common.appName')}</span>
          </Link>
          <nav className="public-layout__nav">
            <LanguageSelector />
            <Link to="/login" className="btn btn--ghost">
              {t('common.login')}
            </Link>
            <Link to="/signup" className="btn btn--primary">
              {t('common.signup')}
            </Link>
          </nav>
        </div>
      </header>
      <main className="public-layout__main">
        <Outlet />
      </main>
      <footer className="public-layout__footer">
        <p>{t('common.footer')}</p>
      </footer>
    </div>
  );
}
