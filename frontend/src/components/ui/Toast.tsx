import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import './ui.css';

export type ToastTone = 'success' | 'error' | 'warning' | 'info';

export type ShowToastOptions = {
  message: string;
  tone?: ToastTone;
  /** Auto-dismiss duration in ms. Default 4000. Use 0 to require manual dismiss. */
  durationMs?: number;
};

type ToastItem = {
  id: string;
  message: string;
  tone: ToastTone;
  durationMs: number;
};

type ToastContextValue = {
  showToast: (options: ShowToastOptions | string) => void;
  dismissToast: (id: string) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const DEFAULT_DURATION_MS = 4000;

function normalizeOptions(options: ShowToastOptions | string): Required<ShowToastOptions> {
  if (typeof options === 'string') {
    return { message: options, tone: 'info', durationMs: DEFAULT_DURATION_MS };
  }
  return {
    message: options.message,
    tone: options.tone ?? 'info',
    durationMs: options.durationMs ?? DEFAULT_DURATION_MS,
  };
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const seq = useRef(0);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback((options: ShowToastOptions | string) => {
    const normalized = normalizeOptions(options);
    if (!normalized.message.trim()) return;
    const id = `toast-${++seq.current}`;
    setToasts((prev) => [
      ...prev,
      {
        id,
        message: normalized.message,
        tone: normalized.tone,
        durationMs: normalized.durationMs,
      },
    ]);
  }, []);

  const value = useMemo(() => ({ showToast, dismissToast }), [showToast, dismissToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismissToast} />
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used within ToastProvider');
  }
  return ctx;
}

function ToastViewport({
  toasts,
  onDismiss,
}: {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}) {
  if (typeof document === 'undefined') return null;

  return createPortal(
    <div className="toast-viewport" aria-live="polite" aria-relevant="additions text">
      {toasts.map((toast) => (
        <ToastCard key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>,
    document.body,
  );
}

function ToastCard({
  toast,
  onDismiss,
}: {
  toast: ToastItem;
  onDismiss: (id: string) => void;
}) {
  useEffect(() => {
    if (toast.durationMs <= 0) return;
    const timer = window.setTimeout(() => onDismiss(toast.id), toast.durationMs);
    return () => window.clearTimeout(timer);
  }, [toast.durationMs, toast.id, onDismiss]);

  const role = toast.tone === 'error' ? 'alert' : 'status';

  return (
    <div className={`toast toast--${toast.tone}`} role={role}>
      <p className="toast__message">{toast.message}</p>
      <button
        type="button"
        className="toast__dismiss"
        aria-label="Dismiss"
        onClick={() => onDismiss(toast.id)}
      >
        ×
      </button>
    </div>
  );
}

/** Pure helper for tests — fixed overlay must not participate in document flow. */
export function toastViewportPositionClass(): string {
  return 'toast-viewport';
}
