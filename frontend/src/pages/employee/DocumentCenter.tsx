import { createPortal } from 'react-dom';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import { DocumentTypeCard } from '../../components/document/DocumentTypeCard';
import type { PersistentDocumentType } from '../../hooks/useEmployeeDocumentWorkspace';
import { useWorkspacePageCopy } from '../../hooks/useWorkspacePageCopy';
import '../../features/employee/employee-payslip.css';
import '../../features/guest/landing/landing-chat.css';
import '../../components/document/document-preview-card.css';

const DOCUMENT_TYPES: PersistentDocumentType[] = [
  'national_id',
  'id_appendix',
  'contract',
];

/**
 * Employee Document Center — three fixed document preview cards.
 */
export function DocumentCenterPage() {
  const { t } = useTranslation();
  const copy = useWorkspacePageCopy();
  const isAccountant = copy.isAccountant;
  const [statusHost, setStatusHost] = useState<HTMLElement | null>(null);

  useEffect(() => {
    if (!isAccountant) {
      setStatusHost(null);
      return;
    }
    setStatusHost(document.getElementById('accountant-doc-page-status-host'));
  }, [isAccountant]);

  return (
    <PortalPage
      title={copy.documentsTitle}
      description={isAccountant ? '' : copy.documentsDescription}
      hideHeader={isAccountant}
    >
      {isAccountant && statusHost
        ? createPortal(
            <p className="accountant-doc-page__status" role="status">
              {t('employee.documents.persistentIntro')}
            </p>,
            statusHost,
          )
        : null}

      <div
        className={`document-center-grid${isAccountant ? ' accountant-doc-workspace' : ''}`}
        role="list"
        aria-label={t('employee.documents.persistentTitle')}
      >
        {DOCUMENT_TYPES.map((documentType) => (
          <div key={documentType} role="listitem">
            <DocumentTypeCard documentType={documentType} />
          </div>
        ))}
      </div>
    </PortalPage>
  );
}
