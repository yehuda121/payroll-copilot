import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useConfirmDialog } from '../../components/ui/Dialog';
import { useTranslation } from 'react-i18next';

type UnsavedChangesContextValue = {
  isDirty: boolean;
  setDirty: (dirty: boolean) => void;
  confirmIfDirty: () => Promise<boolean>;
};

const UnsavedChangesContext = createContext<UnsavedChangesContextValue | null>(null);

export function UnsavedChangesProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { confirm } = useConfirmDialog();
  const [isDirty, setDirtyState] = useState(false);

  const setDirty = useCallback((dirty: boolean) => {
    setDirtyState(dirty);
  }, []);

  const confirmIfDirty = useCallback(async () => {
    if (!isDirty) return true;
    return confirm({
      title: t('accountant.unsaved.title'),
      message: t('accountant.unsaved.message'),
      confirmLabel: t('accountant.unsaved.leave'),
      cancelLabel: t('accountant.unsaved.stay'),
      variant: 'warning',
    });
  }, [confirm, isDirty, t]);

  useEffect(() => {
    if (!isDirty) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [isDirty]);

  const value = useMemo(
    () => ({ isDirty, setDirty, confirmIfDirty }),
    [confirmIfDirty, isDirty, setDirty],
  );

  return (
    <UnsavedChangesContext.Provider value={value}>{children}</UnsavedChangesContext.Provider>
  );
}

export function useUnsavedChanges(): UnsavedChangesContextValue {
  const ctx = useContext(UnsavedChangesContext);
  if (!ctx) {
    throw new Error('useUnsavedChanges must be used within UnsavedChangesProvider');
  }
  return ctx;
}

export function useOptionalUnsavedChanges(): UnsavedChangesContextValue | null {
  return useContext(UnsavedChangesContext);
}
