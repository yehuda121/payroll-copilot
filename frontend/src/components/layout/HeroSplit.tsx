import type { ReactNode } from 'react';

type HeroSplitProps = {
  copy: ReactNode;
  media: ReactNode;
  className?: string;
};

/**
 * Two-column marketing hero.
 * Copy at inline-start, chat/media at inline-end — mirrors automatically in RTL.
 * On narrow screens chat appears first via CSS order.
 */
export function HeroSplit({ copy, media, className = '' }: HeroSplitProps) {
  return (
    <section className={`hero-split ${className}`.trim()}>
      <div className="hero-split__copy">{copy}</div>
      <div className="hero-split__media">{media}</div>
    </section>
  );
}
