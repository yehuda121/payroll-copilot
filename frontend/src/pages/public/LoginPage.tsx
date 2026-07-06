import { Link, Navigate, useNavigate } from 'react-router-dom';
import { getRoleHomePath } from '../../auth/authProvider';
import { useAuth } from '../../auth/AuthContext';
import { DEV_IDENTITIES } from '../../auth/devAuth';
import type { UserRole } from '../../types/auth';
import '../../layouts/PublicLayout.css';

const ROLE_LABELS: Record<UserRole, string> = {
  employee: 'Employee',
  payroll_accountant: 'Payroll Accountant',
  developer_admin: 'Developer / Admin',
};

export function LoginPage() {
  const navigate = useNavigate();
  const { devAuthEnabled, loginWithDevRole, isAuthenticated, session } = useAuth();

  if (isAuthenticated && session) {
    return <Navigate to={getRoleHomePath(session.user.role)} replace />;
  }

  if (devAuthEnabled) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <span className="dev-badge">Dev Auth Mode</span>
          <h1>Sign in</h1>
          <p className="auth-card__subtitle">
            Select a development role to explore role-based portals. No password required.
            Production will use AWS Cognito / RBAC.
          </p>
          <div className="dev-role-list">
            {(Object.keys(DEV_IDENTITIES) as UserRole[]).map((role) => {
              const identity = DEV_IDENTITIES[role];
              return (
                <button
                  key={role}
                  type="button"
                  className="dev-role-card"
                  onClick={() => {
                    loginWithDevRole(role);
                    navigate(getRoleHomePath(role));
                  }}
                >
                  <strong>{ROLE_LABELS[role]}</strong>
                  <span>
                    {identity.fullName} — {identity.email}
                  </span>
                </button>
              );
            })}
          </div>
          <p className="auth-card__footer">
            <Link to="/">Back to landing page</Link>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Sign in</h1>
        <p className="auth-card__subtitle">
          Production authentication via AWS Cognito is not yet connected. Enable{' '}
          <code>VITE_DEV_AUTH_ENABLED=true</code> for local development.
        </p>
        <PlaceholderLoginForm />
        <p className="auth-card__footer">
          No account? <Link to="/signup">Sign up</Link>
        </p>
      </div>
    </div>
  );
}

function PlaceholderLoginForm() {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
      }}
    >
      <div className="form-field">
        <label htmlFor="email">Email</label>
        <input id="email" type="email" placeholder="you@company.com" disabled />
      </div>
      <div className="form-field">
        <label htmlFor="password">Password</label>
        <input id="password" type="password" placeholder="••••••••" disabled />
      </div>
      <button type="submit" className="btn btn--primary" style={{ width: '100%' }} disabled>
        Sign in (Cognito pending)
      </button>
    </form>
  );
}
