import { Link, Navigate, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { getRoleHomePath } from '../../auth/authProvider';
import { useAuth } from '../../auth/AuthContext';
import { DEV_IDENTITIES } from '../../auth/devAuth';
import { useConfirmDialog } from '../../components/ui/Dialog';
import type { UserRole } from '../../types/auth';
import '../../layouts/PublicLayout.css';

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { confirm } = useConfirmDialog();
  const { devAuthEnabled, loginWithDevRole, isAuthenticated, session } = useAuth();

  if (isAuthenticated && session) {
    return <Navigate to={getRoleHomePath(session.user.role)} replace />;
  }

  if (devAuthEnabled) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <span className="dev-badge">{t('auth.devBadge')}</span>
          <h1>{t('auth.signInTitle')}</h1>
          <p className="auth-card__subtitle">{t('auth.devSubtitle')}</p>
          <div className="dev-role-list">
            {(Object.keys(DEV_IDENTITIES) as UserRole[]).map((role) => {
              const identity = DEV_IDENTITIES[role];
              return (
                <button
                  key={role}
                  type="button"
                  className="dev-role-card"
                  onClick={() => {
                    void (async () => {
                      try {
                        await loginWithDevRole(role);
                        navigate(getRoleHomePath(role));
                      } catch (err) {
                        await confirm({
                          title: t('auth.loginFailedTitle'),
                          message: err instanceof Error ? err.message : t('auth.loginFailed'),
                          confirmLabel: t('common.close'),
                          cancelLabel: t('common.close'),
                          variant: 'danger',
                        });
                      }
                    })();
                  }}
                >
                  <strong>{t(`auth.roles.${role}`)}</strong>
                  <span>
                    {identity.fullName} — {identity.email}
                  </span>
                </button>
              );
            })}
          </div>
          <p className="auth-card__footer">
            <Link to="/">{t('auth.backToLanding')}</Link>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>{t('auth.signInTitle')}</h1>
        <p className="auth-card__subtitle">{t('auth.cognitoPending')}</p>
        <PlaceholderLoginForm />
        <p className="auth-card__footer">
          {t('auth.noAccount')} <Link to="/signup">{t('common.signup')}</Link>
        </p>
      </div>
    </div>
  );
}

function PlaceholderLoginForm() {
  const { t } = useTranslation();
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
      }}
    >
      <div className="form-field">
        <label htmlFor="email">{t('auth.email')}</label>
        <input id="email" type="email" placeholder={t('auth.emailPlaceholder')} disabled />
      </div>
      <div className="form-field">
        <label htmlFor="password">{t('auth.password')}</label>
        <input id="password" type="password" placeholder="••••••••" disabled />
      </div>
      <button type="submit" className="btn btn--primary" style={{ width: '100%' }} disabled>
        {t('auth.signInCognitoPending')}
      </button>
    </form>
  );
}
