import { Route, Routes } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { CommandCenter } from '../pages/CommandCenter';
import { IngestFailure } from '../pages/IngestFailure';
import { InvestigationDetail } from '../pages/InvestigationDetail';
import { Investigations } from '../pages/Investigations';
import { NotFound } from '../pages/NotFound';
import { Settings } from '../pages/Settings';
import { SystemHealth } from '../pages/SystemHealth';

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<CommandCenter />} />
        <Route path="investigations" element={<Investigations />} />
        <Route path="investigations/:investigationId" element={<InvestigationDetail />} />
        <Route path="ingest" element={<IngestFailure />} />
        <Route path="system" element={<SystemHealth />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
