import { Outlet } from 'react-router-dom';
import { Trans } from 'react-i18next';
import { APP_NAME } from '../config/brand';
import { AppNavbar } from '../components/layout/AppNavbar';
import './PublicLayout.css';

export function PublicLayout() {
  return (
    <div className="public-layout">
      <AppNavbar showAuthLinks />
      <main className="public-layout__main">
        <Outlet />
      </main>
      <footer className="public-layout__footer">
        <p dir="auto">
          <Trans
            i18nKey="common.footer"
            values={{ appName: APP_NAME }}
            components={[<bdi key="brand" />]}
          />
        </p>
      </footer>
    </div>
  );
}
