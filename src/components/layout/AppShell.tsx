import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useLocalStorage } from '../../hooks/useLocalStorage';
import { Breadcrumbs } from './Breadcrumbs';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

export function AppShell() {
  const [collapsed, setCollapsed] = useLocalStorage('triagezero.sidebar.v1', false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { pathname } = useLocation();

  useEffect(() => {
    setMobileOpen(false);
    window.scrollTo(0, 0);
  }, [pathname]);

  return (
    <div className="shell">
      <Sidebar
        collapsed={collapsed}
        onToggleCollapsed={() => setCollapsed((c) => !c)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />
      <div className={`main ${collapsed ? 'main--wide' : ''}`}>
        <TopBar onOpenMobileNav={() => setMobileOpen(true)} />
        <main className="content" id="main-content">
          <Breadcrumbs />
          <Outlet />
        </main>
      </div>
    </div>
  );
}
