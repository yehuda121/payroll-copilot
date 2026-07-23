import { Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { APP_NAME } from '../config/brand';
import { AppNavbar } from '../components/layout/AppNavbar';
import './PublicLayout.css';

export function PublicLayout() {
  const { t } = useTranslation();

  return (
    <div className="public-layout">
      <AppNavbar showAuthLinks />
      <main className="public-layout__main">
        <Outlet />
      </main>
      <footer className="public-layout__footer">
        <p>{t('common.footer', { appName: APP_NAME })}</p>
      </footer>
    </div>
  );
}
