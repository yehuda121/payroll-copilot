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
  /** Dev mode marker — replaced by Cognito tokens in production. */
  provider: 'dev' | 'cognito';
  issuedAt: string;
  /** API JWT for employee-bound routes (issued by /auth/dev/employee-session). */
  accessToken?: string;
};

export type LoginCredentials = {
  email: string;
  password: string;
};
