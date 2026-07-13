import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { Card } from '../../components/ui/Card';
import { useConfirmDialog } from '../../components/ui/Dialog';
import { EmployeeForm, toWritePayload } from '../../features/accountant/EmployeeForm';
import { getAccountantErrorMessage } from '../../i18n/accountantLabels';
import { employeesService } from '../../services/employees';

export function AddEmployeePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { confirm } = useConfirmDialog();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <PortalPage
      title={t('accountant.employees.add')}
      description={t('accountant.employees.addDescription')}
    >
      <Card>
        <EmployeeForm
          mode="create"
          submitting={submitting}
          error={error}
          onSubmit={async (values) => {
            const ok = await confirm({
              title: t('accountant.employees.createTitle'),
              message: t('accountant.employees.createMessage', {
                number: values.employeeNumber,
                name: `${values.firstName} ${values.lastName}`.trim(),
              }),
              confirmLabel: t('accountant.employees.createConfirm'),
              cancelLabel: t('common.cancel'),
              variant: 'default',
            });
            if (!ok) return;
            setSubmitting(true);
            setError(null);
            try {
              const payload = toWritePayload(values, 'create');
              if (!payload.employee_number) {
                setError(t('accountant.employees.employeeNumberRequired'));
                return;
              }
              const created = await employeesService.create({
                ...payload,
                employee_number: payload.employee_number,
              });
              navigate(`/accountant/employees/${created.employeeNumber}`);
            } catch {
              setError(getAccountantErrorMessage('saveFailed', t));
            } finally {
              setSubmitting(false);
            }
          }}
          footer={
            <Link to="/accountant/employees" className="btn btn--secondary">
              {t('common.cancel')}
            </Link>
          }
        />
      </Card>
    </PortalPage>
  );
}
