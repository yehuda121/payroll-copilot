import { Link } from 'react-router-dom';
import { PortalPage } from '../../components/PortalPage';
import { DataTable } from '../../components/ui/DataTable';
import type { EmployeeRecord } from '../../types';

/**
 * DEVELOPMENT PLACEHOLDER DATA — not real employee records.
 * Replace with employeesService.list() when API is connected.
 */
const PLACEHOLDER_EMPLOYEES: EmployeeRecord[] = [
  {
    employeeNumber: 'EMP-1001',
    fullName: 'Sarah Cohen',
    email: 'sarah.cohen@company.local',
    department: 'Legal',
    employmentType: 'full_time',
    salaryType: 'monthly',
    baseSalaryOrRate: 18500,
    status: 'active',
  },
  {
    employeeNumber: 'EMP-1002',
    fullName: 'Michael Rosen',
    email: 'michael.rosen@company.local',
    department: 'Engineering',
    employmentType: 'full_time',
    salaryType: 'monthly',
    baseSalaryOrRate: 22000,
    status: 'active',
  },
  {
    employeeNumber: 'EMP-1003',
    fullName: 'Noa Barak',
    email: 'noa.barak@company.local',
    department: 'Accounting',
    employmentType: 'part_time',
    salaryType: 'hourly',
    baseSalaryOrRate: 65,
    status: 'on_leave',
  },
];

function StatusBadge({ status }: { status: EmployeeRecord['status'] }) {
  const label = status.replace(/_/g, ' ');
  return <span className={`status-badge status-badge--${status}`}>{label}</span>;
}

export function EmployeeManagementPage() {
  return (
    <PortalPage
      title="Employee Management"
      description="Browse and manage employee master data. Excel import uses header-name field detection on the backend."
      integrationNote="@integration-point EMPLOYEES_LIST"
    >
      <div style={{ marginBottom: '1rem' }}>
        <Link to="/accountant/employees/add" className="btn btn--primary">
          Add Employee
        </Link>
      </div>
      <DataTable<EmployeeRecord>
        columns={[
          { key: 'employeeNumber', header: 'Employee #' },
          { key: 'fullName', header: 'Full Name' },
          { key: 'email', header: 'Email' },
          { key: 'department', header: 'Department' },
          {
            key: 'employmentType',
            header: 'Employment Type',
            render: (row) => row.employmentType.replace(/_/g, ' '),
          },
          { key: 'salaryType', header: 'Salary Type' },
          {
            key: 'baseSalaryOrRate',
            header: 'Base / Rate',
            render: (row) =>
              row.salaryType === 'monthly'
                ? `₪${row.baseSalaryOrRate.toLocaleString()}`
                : `₪${row.baseSalaryOrRate}/hr`,
          },
          {
            key: 'status',
            header: 'Status',
            render: (row) => <StatusBadge status={row.status} />,
          },
          {
            key: 'actions',
            header: '',
            render: (row) => (
              <Link to={`/accountant/employees/${row.employeeNumber}/edit`} className="btn btn--ghost">
                Edit
              </Link>
            ),
          },
        ]}
        data={PLACEHOLDER_EMPLOYEES}
      />
    </PortalPage>
  );
}
