import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { ApiClientError } from '../../services/api';
import {
  employeePortalService,
  type EmployeeDocumentCenter,
  type EmployeeDocumentCenterItem,
} from '../../services/employeePortal';
import { useAppLocale } from '../../hooks/useAppLocale';
import './MyPayslips.css';

function DocRow({
  item,
  onUpload,
  busy,
}: {
  item: EmployeeDocumentCenterItem;
  onUpload: (type: EmployeeDocumentCenterItem['document_type'], file: File) => void;
  busy: boolean;
}) {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const typeLabel = t(`employee.documents.types.${item.document_type}`, {
    defaultValue: item.document_type,
  });

  return (
    <article className="employee-doc-card">
      <header className="employee-doc-card__head">
        <h3>{typeLabel}</h3>
        <span>
          {item.exists
            ? t('employee.documents.statePresent')
            : t('employee.documents.stateMissing')}
        </span>
      </header>
      {item.exists ? (
        <ul className="employee-doc-card__meta">
          <li>
            {t('employee.documents.filename')}: {item.original_filename}
          </li>
          <li>
            {t('employee.documents.uploadedAt')}:{' '}
            {item.uploaded_at
              ? new Date(item.uploaded_at).toLocaleString(locale)
              : t('common.emDash')}
          </li>
          <li>
            {t('employee.documents.processingStatus')}:{' '}
            {t(`employee.lifecycle.${item.processing_status}`, {
              defaultValue: item.processing_status,
            })}
          </li>
          <li>
            {t('employee.documents.extractionStatus')}:{' '}
            {t(`employee.lifecycle.${item.extraction_status}`, {
              defaultValue: item.extraction_status,
            })}
          </li>
          <li>
            {t('employee.documents.confirmationStatus')}:{' '}
            {t(`employee.lifecycle.${item.confirmation_status}`, {
              defaultValue: item.confirmation_status,
            })}
          </li>
          {item.version_count > 1 && (
            <li>
              {t('employee.documents.versionCount', { count: item.version_count })}
            </li>
          )}
        </ul>
      ) : (
        <p>{t('employee.documents.missingState')}</p>
      )}
      {item.extraction_connection === 'extraction_not_connected' && item.exists && (
        <p className="employee-month-detail__note">
          {t('employee.documents.extractionNotConnected')}
        </p>
      )}
      {item.document_type === 'national_id' && (
        <p className="employee-month-detail__note">
          {t('employee.documents.nationalIdFoundation')}
        </p>
      )}
      <div className="employee-doc-card__actions">
        {(item.actions.can_upload || item.actions.can_replace) && (
          <label className="btn btn--secondary">
            {item.exists
              ? t('employee.documents.replace')
              : t('employee.documents.upload')}
            <input
              type="file"
              accept=".pdf,.png,.jpg,.jpeg"
              hidden
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) onUpload(item.document_type, file);
                event.target.value = '';
              }}
            />
          </label>
        )}
        {item.document_type === 'national_id' && item.exists && (
          <Link className="btn btn--ghost" to="/employee/documents/national-id">
            {t('employee.documents.reviewNationalId')}
          </Link>
        )}
      </div>
    </article>
  );
}

export function DocumentCenterPage() {
  const { t } = useTranslation();
  const [data, setData] = useState<EmployeeDocumentCenter | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await employeePortalService.listDocuments());
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.error'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onUpload = async (documentType: string, file: File) => {
    setBusy(true);
    setMessage(null);
    try {
      await employeePortalService.uploadOwnedDocument(file, {
        documentType: documentType as 'national_id' | 'id_appendix' | 'contract',
      });
      setMessage(t('employee.documents.uploadSuccess'));
      await load();
    } catch (err) {
      setMessage(
        err instanceof ApiClientError || err instanceof Error
          ? err.message
          : t('common.error'),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <PortalPage
      title={t('employee.documents.pageTitle')}
      description={t('employee.documents.pageDescription')}
    >
      {loading && <p>{t('common.loading')}</p>}
      {error && (
        <div role="alert">
          <p>{error}</p>
          <button type="button" className="btn btn--secondary" onClick={() => void load()}>
            {t('common.retry')}
          </button>
        </div>
      )}
      {message && <p role="status">{message}</p>}
      {data && (
        <div className="employee-doc-center">
          <section>
            <h2>{t('employee.documents.persistentTitle')}</h2>
            <p>{t('employee.documents.persistentIntro')}</p>
            <div className="employee-doc-center__grid">
              {data.persistent_documents.map((item) => (
                <DocRow key={item.document_type} item={item} onUpload={onUpload} busy={busy} />
              ))}
            </div>
          </section>
          <section>
            <h2>{t('employee.documents.monthlyTitle')}</h2>
            <p>{t('employee.documents.monthlyIntro')}</p>
            <p>
              {t('employee.documents.monthlyCount', {
                count: data.monthly_documents.count,
              })}
            </p>
            <Link className="btn btn--primary" to="/employee/payslips">
              {t('employee.documents.openPayslips')}
            </Link>
          </section>
        </div>
      )}
    </PortalPage>
  );
}
