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

  return (
    <PortalPage
      title={copy.documentsTitle}
      description={isAccountant ? '' : copy.documentsDescription}
    >
      <div
        className={`document-center-grid ui-chrome-rtl${isAccountant ? ' accountant-doc-workspace' : ''}`}
        dir="rtl"
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
