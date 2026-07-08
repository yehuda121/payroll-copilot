import './ui.css';

export type StatusTone = 'passed' | 'unable' | 'issue' | 'neutral';

type StatusBadgeProps = {
  tone: StatusTone;
  label: string;
};

export function StatusBadge({ tone, label }: StatusBadgeProps) {
  return <span className={`status-badge status-badge--${tone}`}>{label}</span>;
}
