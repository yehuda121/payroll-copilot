import { PortalPage } from '../../components/PortalPage';

export function DepartmentRulesPage() {
  return (
    <PortalPage
      title="Department Rules"
      description="Configure department-specific rule profiles (lawyers, interns, accounting, etc.) via plugin profiles."
      integrationNote="@integration-point DEPARTMENT_RULES — backend/config/rules/departments"
    />
  );
}
