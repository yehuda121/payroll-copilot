import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { getRoleHomePath, loadCognitoSession } from '../../auth/authProvider';
import { useAuth } from '../../auth/AuthContext';
import { DEV_IDENTITIES } from '../../auth/devAuth';
import { useConfirmDialog } from '../../components/ui/Dialog';
import type { UserRole } from '../../types/auth';
import '../../layouts/PublicLayout.css';

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { confirm } = useConfirmDialog();
  const {
    devAuthEnabled,
    loginWithDevRole,
    loginWithCredentials,
    isAuthenticated,
    session,
  } = useAuth();

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
        <p className="auth-card__subtitle">
          {t('auth.cognitoSignInHint', {
            defaultValue: 'Sign in with your organization account (Amazon Cognito).',
          })}
        </p>
        <CognitoLoginForm
          onLogin={async (email, password) => {
            await loginWithCredentials({ email, password });
            const next = loadCognitoSession();
            if (!next) {
              throw new Error(t('auth.loginFailed'));
            }
            navigate(getRoleHomePath(next.user.role));
          }}
          onError={async (message) => {
            await confirm({
              title: t('auth.loginFailedTitle'),
              message,
              confirmLabel: t('common.close'),
              cancelLabel: t('common.close'),
              variant: 'danger',
            });
          }}
        />
        <p className="auth-card__footer">
          {t('auth.noAccount')} <Link to="/signup">{t('common.signup')}</Link>
        </p>
      </div>
    </div>
  );
}

function CognitoLoginForm({
  onLogin,
  onError,
}: {
  onLogin: (email: string, password: string) => Promise<void>;
  onError: (message: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await onLogin(email.trim(), password);
    } catch (err) {
      await onError(err instanceof Error ? err.message : t('auth.loginFailed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(event) => void handleSubmit(event)}>
      <div className="form-field">
        <label htmlFor="email">{t('auth.email')}</label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          placeholder={t('auth.emailPlaceholder')}
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          disabled={busy}
        />
      </div>
      <div className="form-field">
        <label htmlFor="password">{t('auth.password')}</label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          placeholder="••••••••"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          disabled={busy}
        />
      </div>
      <button type="submit" className="btn btn--primary" style={{ width: '100%' }} disabled={busy}>
        {busy ? t('common.loading') : t('common.login')}
      </button>
    </form>
  );
}
