import type { ReactNode } from 'react';

type HeroSplitProps = {
  copy: ReactNode;
  media: ReactNode;
  className?: string;
};

/**
 * Two-column marketing hero: copy | primary interaction.
 * Stacks on tablet/mobile (copy first, media second).
 */
export function HeroSplit({ copy, media, className = '' }: HeroSplitProps) {
  return (
    <section className={`hero-split ${className}`.trim()}>
      <div className="hero-split__copy">{copy}</div>
      <div className="hero-split__media">{media}</div>
    </section>
  );
}
