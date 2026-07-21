import type { ReactNode } from 'react';
import { PageHeader } from './ui/PageHeader';
import { PlaceholderPanel } from './ui/PlaceholderPanel';

type PortalPageProps = {
  title: string;
  description: string;
  /** Optional transient status shown directly under the page title. */
  status?: ReactNode;
  /** When true, omit the page header (title is rendered elsewhere). */
  hideHeader?: boolean;
  integrationNote?: string;
  children?: ReactNode;
};

export function PortalPage({
  title,
  description,
  status,
  hideHeader = false,
  integrationNote,
  children,
}: PortalPageProps) {
  return (
    <div>
      {!hideHeader ? (
        <PageHeader title={title} description={description} status={status} />
      ) : null}
      {children ?? <PlaceholderPanel integrationNote={integrationNote} />}
    </div>
  );
}
