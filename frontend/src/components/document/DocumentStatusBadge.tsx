import { useTranslation } from 'react-i18next';
import type { DocumentCardStatus } from '../../lib/employee/document-card-status';

const STATUS_LABEL: Record<DocumentCardStatus, string> = {
  loading: 'employee.documents.badges.loading',
  missing: 'employee.documents.badges.missing',
  needs_review: 'employee.documents.badges.needsReview',
  verified: 'employee.documents.badges.verified',
};

export function DocumentStatusBadge({ status }: { status: DocumentCardStatus }) {
  const { t } = useTranslation();
  return (
    <span className={`document-status-badge document-status-badge--${status}`}>
      {t(STATUS_LABEL[status])}
    </span>
  );
}
