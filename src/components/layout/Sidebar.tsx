import { NavLink } from 'react-router-dom';
import {
  Activity,
  FolderSearch,
  LayoutDashboard,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Upload,
} from 'lucide-react';
import { Logo } from '../ui/Logo';

const navItems = [
  { to: '/', label: 'Command Center', icon: LayoutDashboard, end: true },
  { to: '/investigations', label: 'Investigations', icon: FolderSearch, end: false },
  { to: '/ingest', label: 'Ingest Failure', icon: Upload, end: false },
  { to: '/system', label: 'System Health', icon: Activity, end: false },
  { to: '/settings', label: 'Settings', icon: Settings, end: false },
];

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

export function Sidebar({ collapsed, onToggleCollapsed, mobileOpen, onCloseMobile }: SidebarProps) {
  return (
    <>
      {mobileOpen && (
        <button
          type="button"
          className="mobile-scrim"
          aria-label="Close navigation"
          onClick={onCloseMobile}
        />
      )}
      <nav
        className={`sidebar ${collapsed ? 'sidebar--collapsed' : ''} ${mobileOpen ? 'sidebar--open' : ''}`}
        aria-label="Primary navigation"
      >
        <div className="sidebar__brand">
          <Logo withText={!collapsed || mobileOpen} tagline="Failure Intelligence" />
        </div>
        <div className="sidebar__nav">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
              onClick={onCloseMobile}
              title={collapsed ? label : undefined}
            >
              <Icon size={17} aria-hidden />
              <span className="nav-label">{label}</span>
            </NavLink>
          ))}
        </div>
        <div className="sidebar__footer">
          <button
            type="button"
            className="nav-item desktop-only"
            onClick={onToggleCollapsed}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            style={{ background: 'none', border: '1px solid transparent', cursor: 'pointer', width: '100%', font: 'inherit' }}
          >
            {collapsed ? (
              <PanelLeftOpen size={17} aria-hidden />
            ) : (
              <PanelLeftClose size={17} aria-hidden />
            )}
            <span className="nav-label">Collapse</span>
          </button>
        </div>
      </nav>
    </>
  );
}
