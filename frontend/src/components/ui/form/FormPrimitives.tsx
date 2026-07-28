import type {
  FormEventHandler,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react';
import { InfoIcon } from '../icons';

export type FormShellProps = {
  children: ReactNode;
  aside?: ReactNode;
  className?: string;
  /** Use native form element when wrapping submit handlers. */
  asForm?: boolean;
  onSubmit?: FormEventHandler<HTMLFormElement>;
};

/**
 * Premium form layout shell — optional sticky aside for tips / status.
 */
export function FormShell({
  children,
  aside,
  className = '',
  asForm = false,
  onSubmit,
}: FormShellProps) {
  const classes = [
    'pc-form',
    aside ? 'pc-form--with-aside' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  if (asForm) {
    return (
      <form className={classes} onSubmit={onSubmit} noValidate={false}>
        <div className="pc-form__main">{children}</div>
        {aside ? <aside className="pc-form__aside">{aside}</aside> : null}
      </form>
    );
  }

  return (
    <div className={classes}>
      <div className="pc-form__main">{children}</div>
      {aside ? <aside className="pc-form__aside">{aside}</aside> : null}
    </div>
  );
}

export type FormSectionProps = {
  title: string;
  description?: string;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
  columns?: 1 | 2;
};

export function FormSection({
  title,
  description,
  icon,
  children,
  className = '',
  columns = 2,
}: FormSectionProps) {
  return (
    <section className={`pc-form-section ${className}`.trim()}>
      <header className="pc-form-section__header">
        {icon ? (
          <span className="pc-form-section__icon" aria-hidden="true">
            {icon}
          </span>
        ) : null}
        <div className="pc-form-section__titles">
          <h3 className="pc-form-section__title">{title}</h3>
          {description ? (
            <p className="pc-form-section__description">{description}</p>
          ) : null}
        </div>
      </header>
      <div className={`pc-form-grid${columns === 1 ? ' pc-form-grid--one' : ''}`}>{children}</div>
    </section>
  );
}

export type FormFieldProps = {
  label: string;
  htmlFor: string;
  children: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  required?: boolean;
  span?: 1 | 2;
  className?: string;
};

export function FormField({
  label,
  htmlFor,
  children,
  hint,
  error,
  required = false,
  span = 1,
  className = '',
}: FormFieldProps) {
  return (
    <div
      className={[
        'pc-form-field',
        span === 2 ? 'pc-form-field--span-2' : '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <label className="pc-form-field__label" htmlFor={htmlFor}>
        {label}
        {required ? (
          <span className="pc-form-field__required" aria-hidden="true">
            *
          </span>
        ) : null}
      </label>
      {children}
      {hint ? <span className="pc-form-field__hint">{hint}</span> : null}
      {error ? (
        <span className="pc-form-field__error" role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
}

export type FormControlProps = InputHTMLAttributes<HTMLInputElement> & {
  invalid?: boolean;
};

/** Shared text/number/email/date control chrome for the Form Design System. */
export function FormControl({ invalid = false, className = '', ...props }: FormControlProps) {
  return (
    <input
      className={['pc-form-control', invalid ? 'is-invalid' : '', className].filter(Boolean).join(' ')}
      {...props}
    />
  );
}

export type FormSelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  invalid?: boolean;
};

export function FormSelect({ invalid = false, className = '', children, ...props }: FormSelectProps) {
  return (
    <select
      className={['pc-form-control', 'pc-form-control--select', invalid ? 'is-invalid' : '', className]
        .filter(Boolean)
        .join(' ')}
      {...props}
    >
      {children}
    </select>
  );
}

export type FormTextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  invalid?: boolean;
};

export function FormTextarea({
  invalid = false,
  className = '',
  ...props
}: FormTextareaProps) {
  return (
    <textarea
      className={[
        'pc-form-control',
        'pc-form-control--textarea',
        invalid ? 'is-invalid' : '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      {...props}
    />
  );
}

export type FormInfoPanelProps = {
  title: string;
  children: ReactNode;
  eyebrow?: string;
  tone?: 'info' | 'tip' | 'success' | 'warning';
  icon?: ReactNode;
};

export function FormInfoPanel({
  title,
  children,
  eyebrow,
  tone = 'info',
  icon,
}: FormInfoPanelProps) {
  return (
    <div className={`pc-form-info pc-form-info--${tone}`}>
      <p className="pc-form-info__eyebrow">
        {icon ?? <InfoIcon size={14} aria-hidden="true" />}
        {eyebrow}
      </p>
      <p className="pc-form-info__title">{title}</p>
      <div className="pc-form-info__body">{children}</div>
    </div>
  );
}
