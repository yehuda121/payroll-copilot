import type { CSSProperties } from 'react';
import './Skeleton.css';

type SkeletonProps = {
  className?: string;
  width?: string | number;
  height?: string | number;
  /** Accessible label while content is loading. */
  label?: string;
  rounded?: boolean;
};

/** Lightweight placeholder block for progressive loading UIs. */
export function Skeleton({
  className = '',
  width,
  height,
  label,
  rounded = false,
}: SkeletonProps) {
  const style: CSSProperties = {};
  if (width != null) style.width = typeof width === 'number' ? `${width}px` : width;
  if (height != null) style.height = typeof height === 'number' ? `${height}px` : height;
  return (
    <span
      className={`ui-skeleton ${rounded ? 'ui-skeleton--rounded' : ''} ${className}`.trim()}
      style={style}
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? 'status' : undefined}
    />
  );
}

type SkeletonTextProps = {
  lines?: number;
  className?: string;
};

export function SkeletonText({ lines = 3, className = '' }: SkeletonTextProps) {
  return (
    <div className={`ui-skeleton-stack ${className}`.trim()} aria-hidden="true">
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton
          key={index}
          height={12}
          width={index === lines - 1 ? '62%' : '100%'}
          className="ui-skeleton--line"
        />
      ))}
    </div>
  );
}
