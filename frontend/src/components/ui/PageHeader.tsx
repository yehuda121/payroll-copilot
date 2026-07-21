import type { ReactNode } from 'react';
import './ui.css';

type PageHeaderProps = {
  title: string;
  description?: string;
  /** Transient status shown directly under the title (e.g. Loading). */
  status?: ReactNode;
  actions?: ReactNode;
};

export function PageHeader({ title, description, status, actions }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div>
        <h1 className="page-header__title">{title}</h1>
        {description ? <p className="page-header__description">{description}</p> : null}
        {status ?? null}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </header>
  );
}
