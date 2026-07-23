import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import './ui.css';

export type DialogVariant = 'default' | 'danger' | 'warning';

export type ConfirmDialogOptions = {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: DialogVariant;
};

type DialogContextValue = {
  confirm: (options: ConfirmDialogOptions) => Promise<boolean>;
};

const DialogContext = createContext<DialogContextValue | null>(null);

type PendingConfirm = ConfirmDialogOptions & {
  resolve: (value: boolean) => void;
};

export function DialogProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<PendingConfirm | null>(null);

  const confirm = useCallback((options: ConfirmDialogOptions) => {
    return new Promise<boolean>((resolve) => {
      setPending({ ...options, resolve });
    });
  }, []);

  const close = useCallback(
    (result: boolean) => {
      if (!pending) return;
      pending.resolve(result);
      setPending(null);
    },
    [pending],
  );

  const value = useMemo(() => ({ confirm }), [confirm]);

  return (
    <DialogContext.Provider value={value}>
      {children}
      {pending && (
        <ModalDialog
          title={pending.title}
          variant={pending.variant ?? 'warning'}
          onClose={() => close(false)}
          footer={
            <>
              <button type="button" className="btn btn--secondary" onClick={() => close(false)}>
                {pending.cancelLabel ?? 'Cancel'}
              </button>
              <button
                type="button"
                className={`btn ${pending.variant === 'danger' ? 'btn--danger' : 'btn--primary'}`}
                onClick={() => close(true)}
                autoFocus
              >
                {pending.confirmLabel ?? 'Confirm'}
              </button>
            </>
          }
        >
          <p className="modal-dialog__message">{pending.message}</p>
        </ModalDialog>
      )}
    </DialogContext.Provider>
  );
}

export function useConfirmDialog(): DialogContextValue {
  const ctx = useContext(DialogContext);
  if (!ctx) {
    throw new Error('useConfirmDialog must be used within DialogProvider');
  }
  return ctx;
}

type ModalDialogProps = {
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  variant?: DialogVariant;
  onClose: () => void;
  wide?: boolean;
  className?: string;
};

export function ModalDialog({
  title,
  children,
  footer,
  variant = 'default',
  onClose,
  wide = false,
  className = '',
}: ModalDialogProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // Focus the dialog shell once on mount. Do not re-run when `onClose` identity
  // changes — that would steal focus from inputs on every keystroke.
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current();
      }
      if (event.key === 'Tab' && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      previous?.focus();
    };
  }, []);

  return createPortal(
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <div
        ref={dialogRef}
        className={`modal-dialog modal-dialog--${variant}${wide ? ' modal-dialog--wide' : ''} ${className}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="modal-dialog__header">
          <h2 id={titleId}>{title}</h2>
          <button type="button" className="btn btn--ghost modal-dialog__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>
        <div className="modal-dialog__body">{children}</div>
        {footer && <footer className="modal-dialog__footer">{footer}</footer>}
      </div>
    </div>,
    document.body,
  );
}

type ProgressDialogProps = {
  title: string;
  message: string;
  progressPercent?: number | null;
  indeterminate?: boolean;
};

export function ProgressDialog({
  title,
  message,
  progressPercent = null,
  indeterminate = true,
}: ProgressDialogProps) {
  const titleId = useId();
  const value = progressPercent == null ? undefined : Math.max(0, Math.min(100, progressPercent));

  return createPortal(
    <div className="modal-backdrop modal-backdrop--progress" role="presentation">
      <div
        className="modal-dialog modal-dialog--progress"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-busy="true"
      >
        <header className="modal-dialog__header">
          <h2 id={titleId}>{title}</h2>
        </header>
        <div className="modal-dialog__body">
          <p className="modal-dialog__message">{message}</p>
          <div
            className={`progress-track${indeterminate || value == null ? ' progress-track--indeterminate' : ''}`}
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={value}
          >
            <div
              className="progress-track__fill"
              style={value == null ? undefined : { width: `${value}%` }}
            />
          </div>
          {value != null && <p className="progress-track__label">{Math.round(value)}%</p>}
        </div>
      </div>
    </div>,
    document.body,
  );
}

type LoadingOverlayProps = {
  label?: string;
};

export function LoadingOverlay({ label = 'Loading…' }: LoadingOverlayProps) {
  return (
    <div className="loading-overlay" role="status" aria-live="polite">
      <div className="loading-overlay__spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

type EmptyStateProps = {
  title: string;
  description?: string;
  action?: ReactNode;
};

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}
