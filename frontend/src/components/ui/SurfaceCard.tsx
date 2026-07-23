import type { ReactNode } from 'react';

type SurfaceCardProps = {
  children: ReactNode;
  className?: string;
  as?: 'div' | 'section' | 'article';
  padded?: boolean;
};

/** Theme-aware elevated surface — foundation for chat shells, panels, welcome cards. */
export function SurfaceCard({
  children,
  className = '',
  as: Tag = 'div',
  padded = true,
}: SurfaceCardProps) {
  return (
    <Tag
      className={`surface-card ${padded ? 'surface-card--padded' : ''} ${className}`.trim()}
    >
      {children}
    </Tag>
  );
}
