import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { Card } from '../../components/ui/Card';

export function AccountantDashboardPage() {
  const { t } = useTranslation();

  const links = [
    {
      titleKey: 'accountant.dashboard.employeesTitle',
      descriptionKey: 'accountant.dashboard.employeesDescription',
      to: '/accountant/employees',
    },
    {
      titleKey: 'accountant.dashboard.bulkTitle',
      descriptionKey: 'accountant.dashboard.bulkDescription',
      to: '/accountant/bulk-upload',
    },
    {
      titleKey: 'accountant.dashboard.batchTitle',
      descriptionKey: 'accountant.dashboard.batchDescription',
      to: '/accountant/batch-monitor',
    },
    {
      titleKey: 'accountant.dashboard.rulesTitle',
      descriptionKey: 'accountant.dashboard.rulesDescription',
      to: '/accountant/rules',
    },
    {
      titleKey: 'accountant.dashboard.reviewTitle',
      descriptionKey: 'accountant.dashboard.reviewDescription',
      to: '/accountant/approvals',
    },
    {
      titleKey: 'accountant.dashboard.auditTitle',
      descriptionKey: 'accountant.dashboard.auditDescription',
      to: '/accountant/audit-logs',
    },
  ] as const;

  return (
    <PortalPage
      title={t('accountant.dashboard.title')}
      description={t('accountant.dashboard.description')}
    >
      <div className="employee-profile__grid">
        {links.map((item) => (
          <Card key={item.to} title={t(item.titleKey)}>
            <p>{t(item.descriptionKey)}</p>
            <Link to={item.to} className="btn btn--secondary">
              {t('common.open')}
            </Link>
          </Card>
        ))}
      </div>
    </PortalPage>
  );
}
