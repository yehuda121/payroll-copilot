/** Application roles aligned with backend RBAC (future Cognito groups). */
export type UserRole = 'employee' | 'payroll_accountant' | 'developer_admin';

export type AuthUser = {
  id: string;
  email: string;
  fullName: string;
  /** Optional localized display name from `/employees/me` (e.g. Hebrew). */
  localizedFullName?: string;
  role: UserRole;
  organizationId: string;
};

export type AuthSession = {
  user: AuthUser;
  /** Cognito (production) or local dev role selector. */
  provider: 'dev' | 'cognito';
  issuedAt: string;
  /** Bearer token for portal API calls (Cognito access token or local HS256). */
  accessToken?: string;
};

export type LoginCredentials = {
  email: string;
  password: string;
};
