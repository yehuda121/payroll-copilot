import { Link } from 'react-router-dom';
import '../../layouts/PublicLayout.css';

/**
 * Sign-up entry point — production will redirect to Cognito hosted UI.
 * @integration-point AUTH_SIGNUP
 */
export function SignupPage() {
  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Create account</h1>
        <p className="auth-card__subtitle">
          Employee self-registration and organization onboarding will be handled through AWS
          Cognito. This form is a UI placeholder.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
          }}
        >
          <div className="form-field">
            <label htmlFor="signup-name">Full name</label>
            <input id="signup-name" type="text" disabled />
          </div>
          <div className="form-field">
            <label htmlFor="signup-email">Work email</label>
            <input id="signup-email" type="email" disabled />
          </div>
          <div className="form-field">
            <label htmlFor="signup-password">Password</label>
            <input id="signup-password" type="password" disabled />
          </div>
          <button type="submit" className="btn btn--primary" style={{ width: '100%' }} disabled>
            Create account (Cognito pending)
          </button>
        </form>
        <p className="auth-card__footer">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
