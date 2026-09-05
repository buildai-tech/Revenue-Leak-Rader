import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { FileBarChart2 } from 'lucide-react';
import { fetchApi } from '../lib/api';
import { formatINR } from '../lib/formatters';

interface ReportOverview {
  total_leads: number;
  total_leakage_events: number;
  leakage_rate: number;
  total_estimated_impact: number;
  total_confirmed_recovered: number;
  total_interventions: number;
  by_category: Array<{ category: string; count: number }>;
  by_project: Array<{ project: string; count: number }>;
}

export const Reports: React.FC = () => {
  const { data: report, isLoading } = useQuery<ReportOverview>({
    queryKey: ['report-overview'],
    queryFn: () => fetchApi('/reports/overview'),
  });

  if (isLoading) {
    return (
      <div className="p-12 text-center text-sm text-slate-400">
        <div className="inline-block w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mb-2" />
        <p>Aggregating live intelligence reports...</p>
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-6">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center gap-2.5">
            <FileBarChart2 className="w-6 h-6 text-purple-400" />
            Audit & Intelligence Report
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Deterministic business performance summary and auditable leakage metrics.
          </p>
        </div>
      </div>

      {/* Aggregate Overview Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-5 space-y-2">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total Leads Audited</span>
          <div className="text-3xl font-bold font-mono text-white">{report?.total_leads || 0}</div>
          <span className="text-xs text-slate-500">Unmerged CRM population</span>
        </div>

        <div className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-5 space-y-2">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total Leakage Events</span>
          <div className="text-3xl font-bold font-mono text-rose-400">{report?.total_leakage_events || 0}</div>
          <span className="text-xs text-slate-500">{report?.leakage_rate || 0}% overall leakage rate</span>
        </div>

        <div className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-5 space-y-2">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Estimated Financial Impact</span>
          <div className="text-3xl font-bold font-mono text-amber-400">{formatINR(report?.total_estimated_impact, true)}</div>
          <span className="text-xs text-slate-500">Disclosed formulas tier</span>
        </div>

        <div className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-5 space-y-2">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Confirmed Recoveries</span>
          <div className="text-3xl font-bold font-mono text-emerald-400">{formatINR(report?.total_confirmed_recovered, true)}</div>
          <span className="text-xs text-slate-500">Validated outcome bookings</span>
        </div>
      </div>

      {/* Distribution Tables */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Leakage by Category */}
        <div className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-6 space-y-4">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">Leakage by Rule Category</h3>
          <div className="divide-y divide-slate-800/80">
            {report?.by_category?.map((item) => (
              <div key={item.category} className="py-3 flex items-center justify-between text-xs">
                <span className="font-mono text-slate-300">{item.category}</span>
                <span className="font-mono font-bold text-rose-400">{item.count} events</span>
              </div>
            ))}
          </div>
        </div>

        {/* Leakage by Project */}
        <div className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-6 space-y-4">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">Leakage by Property Project</h3>
          <div className="divide-y divide-slate-800/80">
            {report?.by_project?.map((item) => (
              <div key={item.project} className="py-3 flex items-center justify-between text-xs">
                <span className="text-slate-200 font-medium">{item.project}</span>
                <span className="font-mono font-bold text-amber-400">{item.count} events</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
