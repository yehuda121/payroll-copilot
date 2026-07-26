import type { CSSProperties, ReactNode } from 'react';

type TruncatedTextProps = {
  children: ReactNode;
  /** Full value for native tooltip / accessibility when truncated visually. */
  title?: string;
  className?: string;
  /** Use line-clamp instead of single-line ellipsis. */
  lines?: 1 | 2 | 3;
  as?: 'span' | 'div' | 'p';
  style?: CSSProperties;
};

/**
 * Presentation-only truncation. Does not mutate stored data.
 * Prefer CSS width constraints from parents (flex/grid min-width: 0).
 */
export function TruncatedText({
  children,
  title,
  className = '',
  lines = 1,
  as: Tag = 'span',
  style,
}: TruncatedTextProps) {
  const truncateClass =
    lines === 1 ? 'u-text-truncate' : lines === 2 ? 'u-text-clamp-2' : 'u-text-clamp-3';
  const textTitle =
    title ?? (typeof children === 'string' || typeof children === 'number' ? String(children) : undefined);

  return (
    <Tag className={`${truncateClass} ${className}`.trim()} title={textTitle} style={style}>
      {children}
    </Tag>
  );
}
