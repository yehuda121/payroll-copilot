import { PortalPage } from '../../components/PortalPage';

export function UsersAndRolesPage() {
  return (
    <PortalPage
      title="Users & Roles"
      description="Manage user accounts, role assignments, and organization membership. Production: AWS Cognito groups."
      integrationNote="@integration-point ADMIN_USERS_ROLES"
    />
  );
}
