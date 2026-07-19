import { ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';
import './ui.css';

type IconBackButtonProps = {
  ariaLabel: string;
  title?: string;
  to?: string;
  onClick?: () => void;
};

/**
 * Circular RTL-aware back control for workspace chrome.
 * Arrow flips in RTL so it always points toward the reading start edge.
 */
export function IconBackButton({ ariaLabel, title, to, onClick }: IconBackButtonProps) {
  const label = title ?? ariaLabel;
  const icon = <ArrowLeft className="icon-back-button__icon" aria-hidden="true" size={18} strokeWidth={2.25} />;

  if (to) {
    return (
      <Link to={to} className="icon-back-button" aria-label={ariaLabel} title={label}>
        {icon}
      </Link>
    );
  }

  return (
    <button
      type="button"
      className="icon-back-button"
      aria-label={ariaLabel}
      title={label}
      onClick={onClick}
    >
      {icon}
    </button>
  );
}
