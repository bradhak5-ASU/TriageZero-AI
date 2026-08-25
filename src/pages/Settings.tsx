import { useState } from 'react';
import { Info, RotateCcw, ShieldCheck } from 'lucide-react';
import { config } from '../app/config';
import { ConfirmModal } from '../components/ui/ConfirmModal';
import { useSettings } from '../context/SettingsContext';
import { useToast } from '../context/ToastContext';
import type { EnvironmentName, ThemeName } from '../types';

export function Settings() {
  const { settings, updateSettings, resetSettings } = useSettings();
  const { pushToast } = useToast();
  const [resetOpen, setResetOpen] = useState(false);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Settings</h1>
          <p className="sub">Preferences persist locally in this browser.</p>
        </div>
        <div className="header-actions">
          <button type="button" className="btn" onClick={() => setResetOpen(true)}>
            <RotateCcw size={14} aria-hidden />
            Reset to defaults
          </button>
        </div>
      </div>

      <div className="section-grid" style={{ gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)' }} data-collapse="stack">
        <div className="section-grid" style={{ alignContent: 'start' }}>
          <div className="card">
            <div className="card__header">
              <h2>Connection</h2>
            </div>
            <div className="card__body" style={{ display: 'grid', gap: 12 }}>
              <dl className="kv">
                <dt>API base URL</dt>
                <dd className="mono">{config.apiBaseUrl}</dd>
                <dt>Mock API</dt>
                <dd>
                  {config.useMockApi ? (
                    <span className="badge badge--ai">Enabled — demo mode</span>
                  ) : (
                    <span className="badge badge--ok">Disabled — live API</span>
                  )}
                </dd>
                <dt>Artifact retention</dt>
                <dd>{config.artifactRetentionDays} days (configured server-side)</dd>
              </dl>
              <p className="faint" style={{ fontSize: 12, display: 'flex', gap: 7, alignItems: 'flex-start' }}>
                <Info size={13} aria-hidden style={{ flexShrink: 0, marginTop: 2 }} />
                Connection values come from build-time environment variables (VITE_API_BASE_URL,
                VITE_USE_MOCK_API) and cannot be changed at runtime.
              </p>
              <p className="faint" style={{ fontSize: 12, display: 'flex', gap: 7, alignItems: 'flex-start' }}>
                <ShieldCheck size={13} aria-hidden style={{ flexShrink: 0, marginTop: 2 }} />
                This frontend never stores credentials or API keys. Backend authentication is handled
                by the deployment platform.
              </p>
            </div>
          </div>

          <div className="card">
            <div className="card__header">
              <h2>Behavior</h2>
            </div>
            <div className="card__body" style={{ display: 'grid', gap: 14 }}>
              <div className="field">
                <label htmlFor="s-env">Default environment</label>
                <select
                  id="s-env"
                  className="select"
                  value={settings.defaultEnvironment}
                  onChange={(e) =>
                    updateSettings({ defaultEnvironment: e.target.value as EnvironmentName })
                  }
                >
                  <option value="local">local</option>
                  <option value="staging">staging</option>
                  <option value="production">production</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="s-refresh">Auto-refresh interval</label>
                <select
                  id="s-refresh"
                  className="select"
                  value={settings.refreshIntervalSec}
                  onChange={(e) => updateSettings({ refreshIntervalSec: Number(e.target.value) })}
                >
                  <option value={0}>Off</option>
                  <option value={15}>Every 15 seconds</option>
                  <option value={30}>Every 30 seconds</option>
                  <option value={60}>Every minute</option>
                  <option value={300}>Every 5 minutes</option>
                </select>
              </div>
              <label style={{ display: 'flex', gap: 9, alignItems: 'flex-start', fontSize: 13, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={settings.confirmDangerousActions}
                  onChange={(e) => updateSettings({ confirmDangerousActions: e.target.checked })}
                  style={{ marginTop: 2 }}
                />
                <span>
                  <strong>Confirm dangerous actions</strong>
                  <span className="muted" style={{ display: 'block', fontSize: 12 }}>
                    Ask before retrying analyses or other actions that change investigation state.
                  </span>
                </span>
              </label>
            </div>
          </div>
        </div>

        <div className="section-grid" style={{ alignContent: 'start' }}>
          <div className="card">
            <div className="card__header">
              <h2>Notifications</h2>
            </div>
            <div className="card__body" style={{ display: 'grid', gap: 12 }}>
              {(
                [
                  ['blockRelease', 'Block-release failures', 'Alert when an investigation is assessed as release-blocking.'],
                  ['needsReview', 'Needs review', 'Alert when confidence is too low for automated action.'],
                  ['completed', 'Completed investigations', 'Notify for every completed investigation.'],
                ] as const
              ).map(([key, label, help]) => (
                <label key={key} style={{ display: 'flex', gap: 9, alignItems: 'flex-start', fontSize: 13, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={settings.notifications[key]}
                    onChange={(e) =>
                      updateSettings({
                        notifications: { ...settings.notifications, [key]: e.target.checked },
                      })
                    }
                    style={{ marginTop: 2 }}
                  />
                  <span>
                    <strong>{label}</strong>
                    <span className="muted" style={{ display: 'block', fontSize: 12 }}>{help}</span>
                  </span>
                </label>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card__header">
              <h2>Appearance</h2>
            </div>
            <div className="card__body">
              <div className="field">
                <label htmlFor="s-theme">Theme</label>
                <select
                  id="s-theme"
                  className="select"
                  value={settings.theme}
                  onChange={(e) => updateSettings({ theme: e.target.value as ThemeName })}
                >
                  <option value="dark">Dark (default)</option>
                  <option value="light">Light</option>
                </select>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card__header">
              <h2>About</h2>
            </div>
            <div className="card__body">
              <dl className="kv">
                <dt>Product</dt>
                <dd>
                  {config.appName} — {config.tagline}
                </dd>
                <dt>Version</dt>
                <dd className="mono">
                  {config.version} · {config.build}
                </dd>
                <dt>Pipeline</dt>
                <dd className="muted">
                  Playwright evidence → ingestion → Gemini + Google ADK analysis → recommendation
                </dd>
              </dl>
            </div>
          </div>
        </div>
      </div>

      <ConfirmModal
        open={resetOpen}
        title="Reset all settings?"
        message="Theme, refresh interval, and notification preferences will return to their defaults."
        confirmLabel="Reset settings"
        danger
        onConfirm={() => {
          resetSettings();
          setResetOpen(false);
          pushToast('Settings reset to defaults', 'ok');
        }}
        onCancel={() => setResetOpen(false)}
      />
    </>
  );
}
