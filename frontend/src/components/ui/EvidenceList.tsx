import { useTranslation } from 'react-i18next';
import type { ChecklistEvidence } from '../../lib/guest/validation-report-adapter';
import './ui.css';

type EvidenceListProps = {
  evidence: ChecklistEvidence;
};

export function EvidenceList({ evidence }: EvidenceListProps) {
  const { t } = useTranslation();

  return (
    <div className="evidence-list">
      {evidence.verified.length > 0 && (
        <div>
          <p className="evidence-list__heading">{t('report.evidenceTitle')}</p>
          <ul>
            {evidence.verified.map((item) => (
              <li key={`ok-${item}`} className="evidence-list__ok">
                ✓ {item}
              </li>
            ))}
          </ul>
        </div>
      )}
      {evidence.missing.length > 0 && (
        <div>
          <p className="evidence-list__heading">
            {evidence.unableBecause ? t('report.evidenceUnableBecause') : t('report.evidenceMissing')}
          </p>
          {evidence.unableBecause && <p className="evidence-list__reason">{evidence.unableBecause}</p>}
          <ul>
            {evidence.missing.map((item) => (
              <li key={`miss-${item}`} className="evidence-list__miss">
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
