import { useId, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { GuestChecklistItem } from '../../lib/guest/validation-report-adapter';
import { ConfidenceMeter } from './ConfidenceMeter';
import { EvidenceList } from './EvidenceList';
import { StatusBadge, type StatusTone } from './StatusBadge';
import './ui.css';

type ChecklistItemCardProps = {
  item: GuestChecklistItem;
  details?: ReactNode;
};

function toneLabel(tone: StatusTone, t: (key: string) => string): string {
  switch (tone) {
    case 'passed':
      return t('report.statusPassed');
    case 'unable':
      return t('report.statusUnable');
    case 'issue':
      return t('report.statusIssue');
    default:
      return t('report.statusNA');
  }
}

export function ChecklistItemCard({ item, details }: ChecklistItemCardProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const panelId = useId();

  return (
    <article className={`checklist-item checklist-item--${item.tone}`}>
      <header className="checklist-item__header">
        <div className="checklist-item__title-row">
          <StatusBadge tone={item.tone} label={toneLabel(item.tone, t)} />
          <h4>{item.title}</h4>
        </div>
        <p className="checklist-item__summary">{item.explanation}</p>
        {item.confidence !== null ? (
          <ConfidenceMeter value={item.confidence} label={t('report.ruleConfidence')} />
        ) : null}
      </header>

      <EvidenceList evidence={item.evidence} />

      <button
        type="button"
        className="btn btn--ghost"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={() => setExpanded((prev) => !prev)}
      >
        {expanded ? t('common.collapse') : t('common.expand')}
      </button>

      {expanded && (
        <div id={panelId} className="checklist-item__details">
          {item.recommendation && (
            <p>
              <strong>{t('common.recommendation')}:</strong> {item.recommendation}
            </p>
          )}
          {item.legalReference && (
            <p>
              <strong>{t('common.legalReference')}:</strong> {item.legalReference}
            </p>
          )}
          {details}
        </div>
      )}
    </article>
  );
}
