import type { ReactNode } from 'react';
import './ui.css';

type PlaceholderPanelProps = {
  children?: ReactNode;
  integrationNote?: string;
};

export function PlaceholderPanel({ children, integrationNote }: PlaceholderPanelProps) {
  return (
    <div className="placeholder-panel">
      {children ?? (
        <p className="placeholder-panel__text">
          This section is a UI foundation placeholder. Backend integration pending.
        </p>
      )}
      {integrationNote && (
        <p className="placeholder-panel__integration">{integrationNote}</p>
      )}
    </div>
  );
}
