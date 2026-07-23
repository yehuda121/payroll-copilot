import type { ButtonHTMLAttributes, ReactNode } from 'react';

type ActionIconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  icon: ReactNode;
  tone?: 'default' | 'danger' | 'primary';
};

/**
 * Icon-only action control with required accessible name (aria-label + title).
 * Place inside RTL chrome when used in application chrome.
 */
export function ActionIconButton({
  label,
  icon,
  tone = 'default',
  className = '',
  type = 'button',
  ...rest
}: ActionIconButtonProps) {
  return (
    <button
      type={type}
      className={`action-icon-btn action-icon-btn--${tone} ${className}`.trim()}
      aria-label={label}
      title={label}
      {...rest}
    >
      <span className="action-icon-btn__icon" aria-hidden="true">
        {icon}
      </span>
    </button>
  );
}
