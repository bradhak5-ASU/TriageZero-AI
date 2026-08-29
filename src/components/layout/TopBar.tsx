import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bell,
  FolderSearch,
  LogOut,
  Menu,
  Moon,
  Search,
  ShieldAlert,
  Sun,
} from 'lucide-react';
import { config } from '../../app/config';
import { useAuth } from '../../context/AuthContext';
import { useInvestigations } from '../../context/InvestigationsContext';
import { useSettings } from '../../context/SettingsContext';
import { formatRelativeTime } from '../../utils/format';
import type { EnvironmentName } from '../../types';
import { InvestigationStatusBadge } from '../ui/StatusBadge';

const environments: EnvironmentName[] = ['local', 'staging', 'production'];

export function TopBar({ onOpenMobileNav }: { onOpenMobileNav: () => void }) {
  const navigate = useNavigate();
  const { items } = useInvestigations();
  const { environment, setEnvironment, settings, toggleTheme } = useSettings();
  const { status: authStatus, email, signOut } = useAuth();
  const [query, setQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!searchRef.current?.contains(e.target as Node)) setSearchOpen(false);
      if (!notifRef.current?.contains(e.target as Node)) setNotifOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSearchOpen(false);
        setNotifOpen(false);
      }
    };
    window.addEventListener('mousedown', onClick);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mousedown', onClick);
      window.removeEventListener('keydown', onKey);
    };
  }, []);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return items
      .filter(
        (i) =>
          i.id.toLowerCase().includes(q) ||
          i.testName.toLowerCase().includes(q) ||
          i.repository.toLowerCase().includes(q) ||
          (i.classification ?? '').includes(q.replaceAll(' ', '_')),
      )
      .slice(0, 7);
  }, [items, query]);

  const alerts = useMemo(
    () =>
      items.filter(
        (i) =>
          (settings.notifications.blockRelease && i.releaseRisk === 'block_release') ||
          (settings.notifications.needsReview && i.status === 'needs_review'),
      ),
    [items, settings.notifications],
  );

  const health = config.useMockApi ? 'warn' : 'ok';

  const openResult = (id: string) => {
    setSearchOpen(false);
    setQuery('');
    navigate(`/investigations/${id}`);
  };

  return (
    <header className="topbar">
      <button
        type="button"
        className="icon-btn mobile-nav-toggle"
        aria-label="Open navigation"
        onClick={onOpenMobileNav}
      >
        <Menu size={18} aria-hidden />
      </button>

      <div className="topbar__search" ref={searchRef}>
        <Search size={15} aria-hidden />
        <input
          type="search"
          className="input"
          placeholder="Search investigations, tests, repos…"
          aria-label="Global search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSearchOpen(true);
          }}
          onFocus={() => setSearchOpen(true)}
        />
        {searchOpen && query.trim() && (
          <div className="search-pop" role="listbox" aria-label="Search results">
            {results.length === 0 ? (
              <div style={{ padding: '12px 14px', fontSize: 12.5, color: 'var(--text-faint)' }}>
                No matches for “{query}”
              </div>
            ) : (
              results.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  className="search-pop__item"
                  onClick={() => openResult(r.id)}
                >
                  <FolderSearch size={14} aria-hidden style={{ color: 'var(--text-faint)', flexShrink: 0 }} />
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span className="cell-main" style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.testName}
                    </span>
                    <span className="cell-sub mono">
                      {r.id} · {r.repository}
                    </span>
                  </span>
                  <InvestigationStatusBadge status={r.status} />
                </button>
              ))
            )}
          </div>
        )}
      </div>

      <div className="topbar__spacer" />

      <label className="visually-hidden" htmlFor="env-select">
        Environment
      </label>
      <select
        id="env-select"
        className="select"
        value={environment}
        onChange={(e) => setEnvironment(e.target.value as EnvironmentName)}
        title="Active environment"
      >
        {environments.map((env) => (
          <option key={env} value={env}>
            {env}
          </option>
        ))}
      </select>

      <span className="health-pill desktop-only" title={config.useMockApi ? 'Demo mode — mock data' : 'Connected to API'}>
        <span className={`pulse pulse--${health}`} aria-hidden />
        {config.useMockApi ? 'Demo mode' : 'Connected'}
      </span>

      <div style={{ position: 'relative' }} ref={notifRef}>
        <button
          type="button"
          className="icon-btn"
          aria-label={`Notifications — ${alerts.length} active`}
          onClick={() => setNotifOpen((o) => !o)}
        >
          <Bell size={17} aria-hidden />
          {alerts.length > 0 && <span className="dot" aria-hidden />}
        </button>
        {notifOpen && (
          <div className="menu-pop">
            <h4>Notifications</h4>
            {alerts.length === 0 ? (
              <div style={{ padding: '8px', fontSize: 12.5, color: 'var(--text-faint)' }}>
                Nothing needs your attention.
              </div>
            ) : (
              alerts.slice(0, 6).map((a) => (
                <button
                  key={a.id}
                  type="button"
                  className="menu-pop__item"
                  onClick={() => {
                    setNotifOpen(false);
                    navigate(`/investigations/${a.id}`);
                  }}
                >
                  <ShieldAlert
                    size={15}
                    aria-hidden
                    style={{
                      color: a.releaseRisk === 'block_release' ? 'var(--crit)' : 'var(--warn)',
                      marginTop: 1,
                      flexShrink: 0,
                    }}
                  />
                  <span>
                    <strong style={{ color: 'var(--text)', display: 'block', fontSize: 12.5 }}>
                      {a.releaseRisk === 'block_release' ? 'Release blocked' : 'Needs review'} · {a.id}
                    </strong>
                    {a.testName} · {formatRelativeTime(a.createdAt)}
                  </span>
                </button>
              ))
            )}
          </div>
        )}
      </div>

      <button
        type="button"
        className="icon-btn"
        onClick={toggleTheme}
        aria-label={settings.theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
        title={settings.theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      >
        {settings.theme === 'dark' ? <Sun size={17} aria-hidden /> : <Moon size={17} aria-hidden />}
      </button>

      {authStatus === 'signed-in' ? (
        <>
          <span
            className="avatar"
            title={email ? `Signed in as ${email}` : 'Signed in'}
            aria-label={email ? `Signed in as ${email}` : 'Signed in'}
          >
            {(email ?? 'U').slice(0, 2).toUpperCase()}
          </span>
          <button
            type="button"
            className="icon-btn"
            onClick={() => void signOut()}
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut size={17} aria-hidden />
          </button>
        </>
      ) : (
        <span className="avatar" title="Not signed in" aria-label="Not signed in">
          --
        </span>
      )}
    </header>
  );
}
