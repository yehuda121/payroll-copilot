import { Navigate, useParams } from 'react-router-dom';

/** Legacy edit URL — redirects to Employee Settings (single edit surface). */
export function EditEmployeePage() {
  const { employeeNumber = '' } = useParams<{ employeeNumber: string }>();
  return (
    <Navigate
      to={`/accountant/employees/${encodeURIComponent(employeeNumber)}/workspace/settings`}
      replace
    />
  );
}
