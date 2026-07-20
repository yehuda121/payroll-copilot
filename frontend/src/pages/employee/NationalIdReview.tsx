import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { getDisplayError } from '../../lib/getDisplayError';
import { employeePortalService } from '../../services/employeePortal';
import { useAppLocale } from '../../hooks/useAppLocale';

export function NationalIdReviewPage() {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setData(await employeePortalService.getNationalIdReview());
      } catch (err) {
        setError(getDisplayError(err, t('common.error')));
      }
    })();
  }, [t]);

  return (
    <PortalPage
      title={t('employee.documents.nationalIdReviewTitle')}
      description={t('employee.documents.nationalIdReviewDescription')}
    >
      <p>
        <Link to="/employee/documents">{t('employee.documents.backToCenter')}</Link>
      </p>
      {error && <p role="alert">{error}</p>}
      {data && (
        <div className="employee-nid-review">
          <ul>
            <li>
              {t('employee.documents.filename')}:{' '}
              {String(data.original_filename || t('common.emDash'))}
            </li>
            <li>
              {t('employee.documents.uploadedAt')}:{' '}
              {data.uploaded_at
                ? new Date(String(data.uploaded_at)).toLocaleString(locale)
                : t('common.emDash')}
            </li>
            <li>
              {t('employee.documents.extractionStatus')}:{' '}
              {t(`employee.lifecycle.${String(data.extraction_status)}`, {
                defaultValue: String(data.extraction_status),
              })}
            </li>
            <li>
              {t('employee.compare.fields.national_id')}:{' '}
              {String(data.national_id_masked || t('common.emDash'))}
            </li>
          </ul>
          <p className="employee-month-detail__note" role="note">
            {t('employee.documents.nationalIdFoundation')}
          </p>
        </div>
      )}
    </PortalPage>
  );
}
