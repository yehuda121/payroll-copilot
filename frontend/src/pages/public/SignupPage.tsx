import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  FormControl,
  FormField,
  FormInfoPanel,
  FormSection,
  FormShell,
} from '../../components/ui/form/FormPrimitives';
import { SparklesIcon, UserIcon } from '../../components/ui/icons';
import '../../layouts/PublicLayout.css';

/**
 * Sign-up entry point — production will redirect to Cognito hosted UI.
 * @integration-point AUTH_SIGNUP
 */
export function SignupPage() {
  const { t } = useTranslation();
  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>{t('auth.signUpTitle', { defaultValue: 'Create account' })}</h1>
        <p className="auth-card__subtitle">
          {t('auth.signUpSubtitle', {
            defaultValue:
              'Employee self-registration and organization onboarding will be handled through AWS Cognito. This form is a UI placeholder.',
          })}
        </p>
        <FormShell
          asForm
          onSubmit={(e) => {
            e.preventDefault();
          }}
          aside={
            <FormInfoPanel
              tone="tip"
              eyebrow={t('forms.info.tipEyebrow')}
              title={t('forms.info.signUpTitle')}
              icon={<SparklesIcon size={14} aria-hidden="true" />}
            >
              <p>{t('forms.info.signUpBody')}</p>
            </FormInfoPanel>
          }
        >
          <FormSection
            title={t('forms.sections.signUp.title')}
            description={t('forms.sections.signUp.description')}
            icon={<UserIcon size={18} />}
            columns={1}
          >
            <FormField
              label={t('auth.fullName', { defaultValue: 'Full name' })}
              htmlFor="signup-name"
              span={2}
            >
              <FormControl id="signup-name" type="text" disabled />
            </FormField>
            <FormField
              label={t('auth.email', { defaultValue: 'Work email' })}
              htmlFor="signup-email"
              span={2}
            >
              <FormControl id="signup-email" type="email" disabled />
            </FormField>
            <FormField
              label={t('auth.password', { defaultValue: 'Password' })}
              htmlFor="signup-password"
              span={2}
            >
              <FormControl id="signup-password" type="password" disabled />
            </FormField>
          </FormSection>
          <div className="form-actions">
            <button type="submit" className="btn btn--primary" style={{ width: '100%' }} disabled>
              {t('auth.signUpPending', { defaultValue: 'Create account (Cognito pending)' })}
            </button>
          </div>
        </FormShell>
        <p className="auth-card__footer">
          {t('auth.haveAccount', { defaultValue: 'Already have an account?' })}{' '}
          <Link to="/login">{t('common.login')}</Link>
        </p>
      </div>
    </div>
  );
}
