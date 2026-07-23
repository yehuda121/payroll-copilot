import type { ReactNode } from 'react';

type PageContainerProps = {
  children: ReactNode;
  className?: string;
  /** Wider content (dashboards); default suits marketing/landing. */
  width?: 'default' | 'narrow' | 'wide';
};

/**
 * Shared horizontal page gutter + max-width.
 * Reuse across public and portal surfaces.
 */
export function PageContainer({
  children,
  className = '',
  width = 'default',
}: PageContainerProps) {
  return (
    <div className={`page-container page-container--${width} ${className}`.trim()}>
      {children}
    </div>
  );
}
