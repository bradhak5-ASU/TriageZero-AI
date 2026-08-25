import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';
import { useLocalStorage } from '../hooks/useLocalStorage';
import type { AppSettings, EnvironmentName, ThemeName } from '../types';

export const SETTINGS_KEY = 'triagezero.settings.v1';

export const defaultSettings: AppSettings = {
  theme: 'dark',
  defaultEnvironment: 'local',
  refreshIntervalSec: 30,
  notifications: {
    blockRelease: true,
    needsReview: true,
    completed: false,
  },
  confirmDangerousActions: true,
};

interface SettingsContextValue {
  settings: AppSettings;
  updateSettings: (patch: Partial<AppSettings>) => void;
  resetSettings: () => void;
  environment: EnvironmentName;
  setEnvironment: (env: EnvironmentName) => void;
  toggleTheme: () => void;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useLocalStorage<AppSettings>(
    SETTINGS_KEY,
    defaultSettings,
  );
  const [environment, setEnvironment] = useState<EnvironmentName>(
    settings.defaultEnvironment,
  );

  useEffect(() => {
    document.documentElement.dataset.theme = settings.theme;
  }, [settings.theme]);

  const updateSettings = useCallback(
    (patch: Partial<AppSettings>) => setSettings((prev) => ({ ...prev, ...patch })),
    [setSettings],
  );

  const resetSettings = useCallback(
    () => setSettings(defaultSettings),
    [setSettings],
  );

  const toggleTheme = useCallback(() => {
    setSettings((prev) => ({
      ...prev,
      theme: (prev.theme === 'dark' ? 'light' : 'dark') as ThemeName,
    }));
  }, [setSettings]);

  return (
    <SettingsContext.Provider
      value={{
        settings,
        updateSettings,
        resetSettings,
        environment,
        setEnvironment,
        toggleTheme,
      }}
    >
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error('useSettings must be used inside SettingsProvider');
  return ctx;
}
