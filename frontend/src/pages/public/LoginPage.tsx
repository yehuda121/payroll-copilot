import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { getRoleHomePath, loadCognitoSession } from '../../auth/authProvider';
import { useAuth } from '../../auth/AuthContext';
import { DEV_IDENTITIES } from '../../auth/devAuth';
import { useConfirmDialog } from '../../components/ui/Dialog';
import {
  FormControl,
  FormField,
  FormSection,
  FormShell,
} from '../../components/ui/form/FormPrimitives';
import { UserIcon } from '../../components/ui/icons';
import {
  EMAIL_MAX_LENGTH,
  FREE_TEXT_MAX_LENGTH,
  validateEmailFormat,
} from '../../lib/validation';
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
    const emailResult = validateEmailFormat(email);
    if (!emailResult.ok) {
      await onError(t('common.validation.invalidEmail'));
      return;
    }
    setBusy(true);
    try {
      await onLogin(emailResult.value, password);
    } catch (err) {
      await onError(err instanceof Error ? err.message : t('auth.loginFailed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <FormShell asForm onSubmit={(event) => void handleSubmit(event)}>
      <FormSection
        title={t('forms.sections.signIn.title')}
        description={t('forms.sections.signIn.description')}
        icon={<UserIcon size={18} />}
        columns={1}
      >
        <FormField label={t('auth.email')} htmlFor="email" required span={2}>
          <FormControl
            id="email"
            type="email"
            autoComplete="username"
            placeholder={t('auth.emailPlaceholder')}
            value={email}
            maxLength={EMAIL_MAX_LENGTH}
            onChange={(event) => setEmail(event.target.value)}
            required
            disabled={busy}
          />
        </FormField>
        <FormField label={t('auth.password')} htmlFor="password" required span={2}>
          <FormControl
            id="password"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            maxLength={FREE_TEXT_MAX_LENGTH.password}
            onChange={(event) => setPassword(event.target.value)}
            required
            disabled={busy}
          />
        </FormField>
      </FormSection>
      <div className="form-actions">
        <button type="submit" className="btn btn--primary" style={{ width: '100%' }} disabled={busy}>
          {busy ? t('common.loading') : t('common.login')}
        </button>
      </div>
    </FormShell>
  );
}
