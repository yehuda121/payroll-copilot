import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { batchService } from '../../services/batch';
import type { BatchEmployeeStatus, BatchJobStatus } from '../../types/api';

type BatchGuardContextValue = {
  isBatchActive: boolean;
  setBatchActive: (active: boolean) => void;
  batchLabel: string;
  setBatchLabel: (label: string) => void;
  activeJobId: string | null;
  activeJob: BatchJobStatus | null;
  trackBatch: (jobId: string) => void;
  refreshBatch: () => Promise<void>;
  selectedTab: 'upload' | 'extracted';
  setSelectedTab: (tab: 'upload' | 'extracted') => void;
  statusFilter: BatchEmployeeStatus | 'all';
  setStatusFilter: (status: BatchEmployeeStatus | 'all') => void;
  savedScrollY: number;
  setSavedScrollY: (value: number) => void;
  batchError: string | null;
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
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<BatchJobStatus | null>(null);
  const [selectedTab, setSelectedTab] = useState<'upload' | 'extracted'>('upload');
  const [statusFilter, setStatusFilter] = useState<BatchEmployeeStatus | 'all'>('all');
  const [savedScrollY, setSavedScrollY] = useState(0);
  const [batchError, setBatchError] = useState<string | null>(null);

  const refreshBatch = useCallback(async () => {
    if (!activeJobId) return;
    try {
      const next = await batchService.getJobStatus(activeJobId);
      setActiveJob(next);
      setBatchError(null);
      const active = next.status === 'queued' || next.status === 'running';
      setBatchActive(active);
    } catch (error) {
      setBatchError(error instanceof Error ? error.message : 'Unable to load batch progress.');
    }
  }, [activeJobId]);

  const trackBatch = useCallback((jobId: string) => {
    setActiveJobId(jobId);
    setActiveJob(null);
    setBatchActive(true);
    setSelectedTab('extracted');
    setStatusFilter('all');
  }, []);

  const activeJobStatus = activeJob?.status;

  useEffect(() => {
    if (!activeJobId) return;
    if (activeJobStatus && !['queued', 'running'].includes(activeJobStatus)) return;
    void refreshBatch();
    const timer = window.setInterval(() => void refreshBatch(), 1500);
    return () => window.clearInterval(timer);
  }, [activeJobId, activeJobStatus, refreshBatch]);

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
      activeJobId,
      activeJob,
      trackBatch,
      refreshBatch,
      selectedTab,
      setSelectedTab,
      statusFilter,
      setStatusFilter,
      savedScrollY,
      setSavedScrollY,
      batchError,
    }),
    [
      activeJob,
      activeJobId,
      batchError,
      batchLabel,
      isBatchActive,
      refreshBatch,
      savedScrollY,
      selectedTab,
      statusFilter,
      trackBatch,
    ],
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
    activeJobId: null,
    activeJob: null,
    trackBatch: () => undefined,
    refreshBatch: async () => undefined,
    selectedTab: 'upload',
    setSelectedTab: () => undefined,
    statusFilter: 'all',
    setStatusFilter: () => undefined,
    savedScrollY: 0,
    setSavedScrollY: () => undefined,
    batchError: null,
  };
}
