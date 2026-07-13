import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';

export function ValidationFindingsPage() {
  const { t } = useTranslation();
  return (
    <PortalPage
      title={t('accountant.validations.findingsTitle')}
      description={t('accountant.validations.findingsDescription')}
    />
  );
}
