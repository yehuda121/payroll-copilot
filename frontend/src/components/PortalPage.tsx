import type { ReactNode } from 'react';
import { PageHeader } from './ui/PageHeader';
import { PlaceholderPanel } from './ui/PlaceholderPanel';

type PortalPageProps = {
  title: string;
  description: string;
  integrationNote?: string;
  children?: ReactNode;
};

export function PortalPage({ title, description, integrationNote, children }: PortalPageProps) {
  return (
    <div>
      <PageHeader title={title} description={description} />
      {children ?? <PlaceholderPanel integrationNote={integrationNote} />}
    </div>
  );
}
