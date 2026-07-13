import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

type BatchGuardContextValue = {
  isBatchActive: boolean;
  setBatchActive: (active: boolean) => void;
  batchLabel: string;
  setBatchLabel: (label: string) => void;
};

const BatchGuardContext = createContext<BatchGuardContextValue | null>(null);

/**
 * Tracks active bulk processing for UX guards.
 * Backend processing never depends on the browser remaining open.
 * Tab/window close uses beforeunload; in-app leave confirmations are handled
 * by pages that call useConfirmDialog while isBatchActive.
 */
export function BatchNavigationGuardProvider({ children }: { children: ReactNode }) {
  const [isBatchActive, setBatchActive] = useState(false);
  const [batchLabel, setBatchLabel] = useState('Batch processing is running');

  useEffect(() => {
    if (!isBatchActive) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [isBatchActive]);

  const value = useMemo(
    () => ({
      isBatchActive,
      setBatchActive,
      batchLabel,
      setBatchLabel,
    }),
    [batchLabel, isBatchActive],
  );

  return <BatchGuardContext.Provider value={value}>{children}</BatchGuardContext.Provider>;
}

export function useBatchNavigationGuard(): BatchGuardContextValue {
  const ctx = useContext(BatchGuardContext);
  if (!ctx) {
    throw new Error('useBatchNavigationGuard must be used within BatchNavigationGuardProvider');
  }
  return ctx;
}

export function useOptionalBatchNavigationGuard(): BatchGuardContextValue {
  const ctx = useContext(BatchGuardContext);
  const noopBool = useCallback((_active: boolean) => undefined, []);
  const noopLabel = useCallback((_label: string) => undefined, []);
  if (ctx) return ctx;
  return {
    isBatchActive: false,
    setBatchActive: noopBool,
    batchLabel: '',
    setBatchLabel: noopLabel,
  };
}
