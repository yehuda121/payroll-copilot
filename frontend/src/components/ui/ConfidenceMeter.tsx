import { useTranslation } from 'react-i18next';
import './ui.css';

type ConfidenceMeterProps = {
  value: number | null | undefined;
  label?: string;
};

export function ConfidenceMeter({ value, label }: ConfidenceMeterProps) {
  const { t } = useTranslation();
  if (value === null || value === undefined || Number.isNaN(value)) {
    return null;
  }

  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <div className="confidence-meter" aria-label={`${label ?? t('report.confidenceLabel')}: ${pct}%`}>
      <div className="confidence-meter__row">
        <span>{label ?? t('report.confidenceLabel')}</span>
        <strong>{pct}%</strong>
      </div>
      <div className="confidence-meter__track" aria-hidden="true">
        <div className="confidence-meter__fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
