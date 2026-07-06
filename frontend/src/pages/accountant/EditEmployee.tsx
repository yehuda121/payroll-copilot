import { Link, useParams } from 'react-router-dom';
import { PortalPage } from '../../components/PortalPage';
import { Card } from '../../components/ui/Card';

export function EditEmployeePage() {
  const { employeeNumber } = useParams<{ employeeNumber: string }>();

  return (
    <PortalPage
      title={`Edit Employee ${employeeNumber ?? ''}`}
      description="Update employee master data fields."
      integrationNote="@integration-point EMPLOYEES_UPDATE"
    >
      <Card>
        <form
          onSubmit={(e) => {
            e.preventDefault();
          }}
        >
          <div className="form-field">
            <label htmlFor="employeeNumber">Employee number</label>
            <input id="employeeNumber" type="text" defaultValue={employeeNumber} readOnly />
          </div>
          <div className="form-field">
            <label htmlFor="fullName">Full name</label>
            <input id="fullName" type="text" />
          </div>
          <div className="form-field">
            <label htmlFor="status">Status</label>
            <select id="status" defaultValue="active">
              <option value="active">Active</option>
              <option value="on_leave">On leave</option>
              <option value="terminated">Terminated</option>
            </select>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button type="submit" className="btn btn--primary" disabled>
              Update employee (API pending)
            </button>
            <Link to="/accountant/employees" className="btn btn--secondary">
              Back to list
            </Link>
          </div>
        </form>
      </Card>
    </PortalPage>
  );
}
