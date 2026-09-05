import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { AppLayout } from './components/layout/AppLayout';
import { Dashboard } from './pages/Dashboard';
import { Leads } from './pages/Leads';
import { LeadDetail } from './pages/LeadDetail';
import { Leakage } from './pages/Leakage';
import { Recommendations } from './pages/Recommendations';
import { Interventions } from './pages/Interventions';
import { DataImport } from './pages/DataImport';
import { DataImportDetail } from './pages/DataImportDetail';
import { Reports } from './pages/Reports';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 30000,
    },
  },
});

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<AppLayout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="leads" element={<Leads />} />
            <Route path="leads/:id" element={<LeadDetail />} />
            <Route path="leakage" element={<Leakage />} />
            <Route path="recommendations" element={<Recommendations />} />
            <Route path="interventions" element={<Interventions />} />
            <Route path="data-import" element={<DataImport />} />
            <Route path="data-import/:id" element={<DataImportDetail />} />
            <Route path="reports" element={<Reports />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
};

export default App;
