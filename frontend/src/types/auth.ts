/** Application roles aligned with backend RBAC (future Cognito groups). */
export type UserRole = 'employee' | 'payroll_accountant' | 'developer_admin';

export type AuthUser = {
  id: string;
  email: string;
  fullName: string;
  role: UserRole;
  organizationId: string;
};

export type AuthSession = {
  user: AuthUser;
  /** Dev mode marker — replaced by Cognito tokens in production. */
  provider: 'dev' | 'cognito';
  issuedAt: string;
};

export type LoginCredentials = {
  email: string;
  password: string;
};
