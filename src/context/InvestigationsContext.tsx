import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { api } from '../services';
import { useSettings } from './SettingsContext';
import type { FailurePackage, Investigation } from '../types';

interface InvestigationsContextValue {
  items: Investigation[];
  loading: boolean;
  error: string | null;
  lastUpdated: number | null;
  refresh: () => Promise<void>;
  getById: (id: string) => Investigation | undefined;
  fetchById: (id: string) => Promise<Investigation>;
  create: (pkg: FailurePackage) => Promise<string>;
  retry: (id: string) => Promise<Investigation>;
}

const InvestigationsContext = createContext<InvestigationsContextValue | null>(null);

export function InvestigationsProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Investigation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const { settings } = useSettings();
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listInvestigations();
      if (!mounted.current) return;
      setItems(data);
      setError(null);
      setLastUpdated(Date.now());
    } catch (e) {
      if (!mounted.current) return;
      setError(e instanceof Error ? e.message : 'Failed to load investigations');
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // periodic background refresh, driven by the settings interval
  useEffect(() => {
    if (settings.refreshIntervalSec <= 0) return;
    const id = window.setInterval(() => {
      void refresh();
    }, settings.refreshIntervalSec * 1000);
    return () => window.clearInterval(id);
  }, [settings.refreshIntervalSec, refresh]);

  const getById = useCallback(
    (id: string) => items.find((i) => i.id === id),
    [items],
  );

  const fetchById = useCallback(async (id: string) => {
    const inv = await api.getInvestigation(id);
    setItems((prev) => {
      const idx = prev.findIndex((p) => p.id === id);
      if (idx === -1) return [inv, ...prev];
      const next = [...prev];
      next[idx] = inv;
      return next;
    });
    return inv;
  }, []);

  const create = useCallback(
    async (pkg: FailurePackage) => {
      const res = await api.createInvestigation(pkg);
      await refresh();
      return res.id;
    },
    [refresh],
  );

  const retry = useCallback(
    async (id: string) => {
      const inv = await api.retryInvestigation(id);
      await refresh();
      return inv;
    },
    [refresh],
  );

  return (
    <InvestigationsContext.Provider
      value={{
        items,
        loading,
        error,
        lastUpdated,
        refresh,
        getById,
        fetchById,
        create,
        retry,
      }}
    >
      {children}
    </InvestigationsContext.Provider>
  );
}

export function useInvestigations(): InvestigationsContextValue {
  const ctx = useContext(InvestigationsContext);
  if (!ctx) {
    throw new Error('useInvestigations must be used inside InvestigationsProvider');
  }
  return ctx;
}
