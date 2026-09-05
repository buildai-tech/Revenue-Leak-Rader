import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { AlertOctagon, Filter, ArrowRight, Sparkles } from 'lucide-react';
import { fetchApi, LeakageListResponse, LeakageEventDetail } from '../lib/api';
import { formatINR, formatDate } from '../lib/formatters';
import { StatusBadge } from '../components/ui/StatusBadge';
import { TierBadge } from '../components/ui/TierBadge';
import { ConfidenceBadge } from '../components/ui/ConfidenceBadge';
import { DataTable } from '../components/ui/DataTable';
import { EvidenceDrawer } from '../components/ui/EvidenceDrawer';

export const Leakage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [categoryFilter, setCategoryFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

  const { data, isLoading } = useQuery<LeakageListResponse>({
    queryKey: ['leakage-list', categoryFilter, statusFilter],
    queryFn: () => {
      const params = new URLSearchParams();
      if (categoryFilter) params.append('category', categoryFilter);
      if (statusFilter) params.append('status', statusFilter);
      return fetchApi(`/leakage?${params.toString()}`);
    },
  });

  const { data: selectedEvent } = useQuery<LeakageEventDetail>({
    queryKey: ['leakage-detail', selectedEventId],
    queryFn: () => fetchApi(`/leakage/${selectedEventId}`),
    enabled: !!selectedEventId,
  });

  const generateRecMutation = useMutation({
    mutationFn: (leakageEventId: string) =>
      fetchApi('/recommendations/generate', {
        method: 'POST',
        body: JSON.stringify({ leakage_event_id: leakageEventId }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recommendations'] });
      navigate('/recommendations');
    },
  });

  const columns = [
    {
      header: 'Leakage Event / Lead',
      accessor: (row: LeakageEventDetail) => (
        <div className="space-y-0.5">
          <div className="font-semibold text-white group-hover:text-blue-400 transition-colors">
            {row.title}
          </div>
          <div className="text-[11px] text-slate-400">
            Lead: <span className="text-slate-300 font-medium">{row.lead_name || 'N/A'}</span>
          </div>
        </div>
      ),
    },
    {
      header: 'Category',
      accessor: (row: LeakageEventDetail) => (
        <span className="font-mono text-xs text-slate-300 bg-slate-800 px-2 py-0.5 rounded border border-slate-700">
          {row.category}
        </span>
      ),
    },
    {
      header: 'Financial Impact',
      accessor: (row: LeakageEventDetail) => (
        <div className="space-y-1">
          <div className="font-mono font-semibold text-slate-100">
            {formatINR(row.financial?.amount_inr)}
          </div>
          <TierBadge tier={row.financial?.tier || row.tier} size="sm" />
        </div>
      ),
    },
    {
      header: 'Confidence',
      accessor: (row: LeakageEventDetail) => (
        <ConfidenceBadge score={row.financial?.confidence} size="sm" />
      ),
    },
    {
      header: 'Status',
      accessor: (row: LeakageEventDetail) => <StatusBadge status={row.status} />,
    },
    {
      header: 'Detected At',
      accessor: (row: LeakageEventDetail) => (
        <span className="text-slate-400 text-[11px]">{formatDate(row.created_at)}</span>
      ),
    },
    {
      header: 'Action',
      className: 'text-right',
      accessor: (row: LeakageEventDetail) => (
        <span className="text-xs font-semibold text-blue-400 group-hover:text-blue-300 inline-flex items-center gap-1">
          Evidence <ArrowRight className="w-3.5 h-3.5" />
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-6">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center gap-2.5">
            <AlertOctagon className="w-6 h-6 text-rose-400" />
            Leakage Events Ledger
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Complete list of detected revenue leaks with auditable evidence trails and calculation provenance.
          </p>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-wrap items-center gap-3 bg-[#0f172a]/90 border border-slate-800 p-4 rounded-xl">
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
        >
          <option value="">All Categories</option>
          <option value="dead_but_recently_engaged">Dead but Recently Engaged</option>
          <option value="unresolved_questions">Unresolved Questions</option>
          <option value="repeated_re_engagement">Repeated Re-engagement</option>
          <option value="assigned_to_inactive_rep">Assigned to Inactive Rep</option>
          <option value="no_followup">No Follow-up</option>
          <option value="high_value_poor_followup">High Value & Poor Follow-up</option>
          <option value="response_delay">Response Delay</option>
          <option value="never_contacted">Never Contacted</option>
        </select>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
        >
          <option value="">All Statuses</option>
          <option value="open">Open</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="in_progress">In Progress</option>
          <option value="resolved">Resolved</option>
          <option value="dismissed">Dismissed</option>
        </select>
      </div>

      {/* Table */}
      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        onRowClick={(row) => setSelectedEventId(row.id)}
        emptyMessage="No leakage events match current filters."
      />

      {/* Evidence Drawer */}
      <EvidenceDrawer
        isOpen={!!selectedEventId}
        onClose={() => setSelectedEventId(null)}
        event={selectedEvent || null}
        onGenerateRecommendation={(id) => generateRecMutation.mutate(id)}
        isGenerating={generateRecMutation.isPending}
      />
    </div>
  );
};
