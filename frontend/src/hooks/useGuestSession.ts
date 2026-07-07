import { useCallback, useState } from 'react';
import { authService } from '../services/auth';
import { getGuestToken } from '../lib/guest/guest-session';

export function useGuestSession() {
  const [isReady, setIsReady] = useState(Boolean(getGuestToken()));
  const [error, setError] = useState<string | null>(null);

  const ensureSession = useCallback(async () => {
    if (getGuestToken()) {
      setIsReady(true);
      return;
    }
    setError(null);
    try {
      await authService.createGuestSession();
      setIsReady(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to start guest session.');
      setIsReady(false);
      throw err;
    }
  }, []);

  return { isReady, error, ensureSession };
}
