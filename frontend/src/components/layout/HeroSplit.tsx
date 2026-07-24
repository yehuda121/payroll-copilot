import type { ReactNode } from 'react';

type HeroSplitProps = {
  copy: ReactNode;
  media: ReactNode;
  className?: string;
};

/**
 * Two-column marketing hero with fixed physical layout (Hebrew reference):
 * Chat/media on the left, supporting copy on the right — locale-independent.
 * On narrow screens: Chat first, then copy/popular content.
 */
export function HeroSplit({ copy, media, className = '' }: HeroSplitProps) {
  return (
    <section className={`hero-split ${className}`.trim()} dir="ltr">
      <div className="hero-split__media">{media}</div>
      <div className="hero-split__copy" dir="auto">
        {copy}
      </div>
    </section>
  );
}
