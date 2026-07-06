import { Link } from 'react-router-dom';
import { PortalPage } from '../../components/PortalPage';
import { Card } from '../../components/ui/Card';

export function AddEmployeePage() {
  return (
    <PortalPage
      title="Add Employee"
      description="Create a new employee record in the master data."
      integrationNote="@integration-point EMPLOYEES_CREATE"
    >
      <Card>
        <form
          onSubmit={(e) => {
            e.preventDefault();
          }}
        >
          <div className="form-field">
            <label htmlFor="fullName">Full name</label>
            <input id="fullName" type="text" />
          </div>
          <div className="form-field">
            <label htmlFor="email">Email</label>
            <input id="email" type="email" />
          </div>
          <div className="form-field">
            <label htmlFor="department">Department</label>
            <select id="department">
              <option value="">Select department</option>
              <option value="legal">Legal</option>
              <option value="engineering">Engineering</option>
              <option value="accounting">Accounting</option>
            </select>
          </div>
          <div className="form-field">
            <label htmlFor="employmentType">Employment type</label>
            <select id="employmentType">
              <option value="full_time">Full time</option>
              <option value="part_time">Part time</option>
              <option value="contractor">Contractor</option>
              <option value="intern">Intern</option>
            </select>
          </div>
          <div className="form-field">
            <label htmlFor="salaryType">Salary type</label>
            <select id="salaryType">
              <option value="monthly">Monthly</option>
              <option value="hourly">Hourly</option>
            </select>
          </div>
          <div className="form-field">
            <label htmlFor="baseSalary">Base salary / hourly rate</label>
            <input id="baseSalary" type="number" min="0" step="0.01" />
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button type="submit" className="btn btn--primary" disabled>
              Save employee (API pending)
            </button>
            <Link to="/accountant/employees" className="btn btn--secondary">
              Cancel
            </Link>
          </div>
        </form>
      </Card>
    </PortalPage>
  );
}
