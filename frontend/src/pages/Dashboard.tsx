import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  TrendingDown,
  Sparkles,
  CheckCircle2,
  DollarSign,
  Clock,
  Layers,
  ArrowRight,
  Info,
  ShieldAlert,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';

import {
  fetchApi,
  DashboardSummary,
  LeakageBreakdownItem,
  HighPriorityIssue,
  RecoveryPipeline,
  RecentRecovery,
  ResponseLeakageAnalysis,
  LeakageEventDetail,
} from '../lib/api';
import { formatINR, formatDate, TIER_CONFIG } from '../lib/formatters';
import { MetricCard } from '../components/ui/MetricCard';
import { StatusBadge } from '../components/ui/StatusBadge';
import { TierBadge } from '../components/ui/TierBadge';
import { ConfidenceBadge } from '../components/ui/ConfidenceBadge';
import { EvidenceDrawer } from '../components/ui/EvidenceDrawer';

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Selected event for Evidence Drawer
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

  // Queries
  const { data: summary, isLoading: loadingSummary } = useQuery<DashboardSummary>({
    queryKey: ['dashboard-summary'],
    queryFn: () => fetchApi('/dashboard/summary'),
  });

  const { data: breakdown = [], isLoading: loadingBreakdown } = useQuery<LeakageBreakdownItem[]>({
    queryKey: ['dashboard-breakdown'],
    queryFn: () => fetchApi('/dashboard/leakage-breakdown'),
  });

  const { data: highPriority = [], isLoading: loadingHighPriority } = useQuery<HighPriorityIssue[]>({
    queryKey: ['dashboard-high-priority'],
    queryFn: () => fetchApi('/dashboard/high-priority?limit=10'),
  });

  const { data: pipeline, isLoading: loadingPipeline } = useQuery<RecoveryPipeline>({
    queryKey: ['dashboard-pipeline'],
    queryFn: () => fetchApi('/dashboard/recovery-pipeline'),
  });

  const { data: responseLeakage, isLoading: loadingResponseLeakage } = useQuery<ResponseLeakageAnalysis>({
    queryKey: ['dashboard-response-leakage'],
    queryFn: () => fetchApi('/dashboard/response-leakage'),
  });

  const { data: recentRecoveries = [] } = useQuery<RecentRecovery[]>({
    queryKey: ['dashboard-recent-recoveries'],
    queryFn: () => fetchApi('/dashboard/recent-recoveries'),
  });

  // Query for individual event when selected for drawer
  const { data: selectedEvent } = useQuery<LeakageEventDetail>({
    queryKey: ['leakage-detail', selectedEventId],
    queryFn: () => fetchApi(`/leakage/${selectedEventId}`),
    enabled: !!selectedEventId,
  });

  // Mutation to generate recommendation
  const generateRecMutation = useMutation({
    mutationFn: (leakageEventId: string) =>
      fetchApi('/recommendations/generate', {
        method: 'POST',
        body: JSON.stringify({ leakage_event_id: leakageEventId }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard-pipeline'] });
      queryClient.invalidateQueries({ queryKey: ['recommendations'] });
      navigate('/recommendations');
    },
  });

  const CHART_COLORS = ['#f43f5e', '#f59e0b', '#8b5cf6', '#3b82f6', '#06b6d4', '#10b981'];

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-12">
      
      {/* Page Title & Context */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-6">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center gap-2.5">
            Command Center
            <span className="text-xs font-mono font-medium px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
              Live Intel
            </span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Real-time deterministic revenue leakage detection, auditable financial calculations & recovery tracking.
          </p>
        </div>

        <button
          onClick={() => navigate('/data-import')}
          className="self-start sm:self-auto px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-500 rounded-lg transition-colors flex items-center gap-2 shadow-lg shadow-blue-600/20"
        >
          <Sparkles className="w-3.5 h-3.5" />
          Import CRM Batch
        </button>
      </div>

      {/* â”€â”€ 1. Top Four Financial Summary Metric Cards â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
        <MetricCard
          title="Revenue at Risk"
          value={formatINR(summary?.revenue_at_risk, true)}
          tier={summary?.revenue_at_risk_tier || 'estimated_financial_impact'}
          confidence={summary?.revenue_at_risk_confidence}
          icon={<AlertTriangle className="w-5 h-5 text-rose-400" />}
          accentBorder="blue"
        />

        <MetricCard
          title="Potentially Recoverable"
          value={formatINR(summary?.potentially_recoverable, true)}
          tier="estimated_financial_impact"
          subtitle="Active leakage opportunities"
          icon={<TrendingDown className="w-5 h-5 text-amber-400" />}
          accentBorder="amber"
        />

        <MetricCard
          title="High-Priority Issues"
          value={summary ? summary.high_priority_count.toString() : '0'}
          subtitle="Open leakage events"
          icon={<ShieldAlert className="w-5 h-5 text-purple-400" />}
          accentBorder="purple"
        />

        <MetricCard
          title="Confirmed Recovered"
          value={formatINR(summary?.confirmed_recovered, true)}
          tier={summary?.confirmed_recovered_tier || 'confirmed_recovered_revenue'}
          subtitle="Verified booking outcomes"
          icon={<CheckCircle2 className="w-5 h-5 text-emerald-400" />}
          accentBorder="emerald"
        />
      </div>

      {/* â”€â”€ 2. Leakage Breakdown & Recovery Funnel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Leakage by Category Chart */}
        <div className="lg:col-span-2 bg-[#0f172a]/90 border border-slate-800 rounded-xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                Leakage Events by Category
              </h3>
              <p className="text-xs text-slate-400">Total detected occurrences and financial impact distribution</p>
            </div>
            <button
              onClick={() => navigate('/leakage')}
              className="text-xs text-blue-400 hover:text-blue-300 font-medium flex items-center gap-1"
            >
              View All <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="h-64 w-full pt-2">
            {loadingBreakdown ? (
              <div className="h-full flex items-center justify-center text-xs text-slate-500">Loading chart...</div>
            ) : breakdown.length === 0 ? (
              <div className="h-full flex items-center justify-center text-xs text-slate-500">No leakage data available</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={breakdown} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                  <XAxis
                    dataKey="category"
                    tick={{ fill: '#94a3b8', fontSize: 11 }}
                    tickFormatter={(val) => val.replace(/_/g, ' ').slice(0, 14)}
                    interval={0}
                    angle={-15}
                    textAnchor="end"
                  />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#090d16',
                      borderColor: '#334155',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                    formatter={(val: any, name: string) => [
                      name === 'event_count' ? `${val} events` : formatINR(val),
                      name === 'event_count' ? 'Occurrences' : 'Estimated Impact',
                    ]}
                  />
                  <Bar dataKey="event_count" radius={[4, 4, 0, 0]}>
                    {breakdown.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Recovery Pipeline Funnel */}
        <div className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-6 flex flex-col justify-between space-y-4">
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Recovery Pipeline
            </h3>
            <p className="text-xs text-slate-400">Resolution funnel progression</p>
          </div>

          <div className="space-y-3 py-2">
            {[
              { label: 'Detected', count: pipeline?.detected || 0, color: 'bg-rose-500' },
              { label: 'Reviewed', count: pipeline?.reviewed || 0, color: 'bg-blue-500' },
              { label: 'Recommended', count: pipeline?.recommended || 0, color: 'bg-amber-500' },
              { label: 'Intervention Started', count: pipeline?.intervention_started || 0, color: 'bg-cyan-500' },
              { label: 'Recovered', count: pipeline?.recovered || 0, color: 'bg-emerald-500' },
            ].map((step, idx) => {
              const maxVal = Math.max(pipeline?.detected || 1, 1);
              const pct = Math.max(8, Math.round((step.count / maxVal) * 100));

              return (
                <div key={idx} className="space-y-1">
                  <div className="flex justify-between text-xs font-medium">
                    <span className="text-slate-300">{step.label}</span>
                    <span className="font-mono text-slate-200">{step.count}</span>
                  </div>
                  <div className="w-full bg-slate-900 rounded-full h-2 overflow-hidden border border-slate-800">
                    <div className={`h-full ${step.color} rounded-full transition-all duration-500`} style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>

          <button
            onClick={() => navigate('/interventions')}
            className="w-full py-2 text-xs font-semibold text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors flex items-center justify-center gap-1.5"
          >
            Open Intervention Kanban <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* â”€â”€ 3. High-Priority Issues Table â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      <div className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              High-Priority Issues
            </h3>
            <p className="text-xs text-slate-400">
              Click any row to inspect complete auditable evidence and calculate recommendation
            </p>
          </div>
          <span className="text-xs text-slate-400 font-mono">
            Showing top {highPriority.length} actionable items
          </span>
        </div>

        <div className="overflow-x-auto rounded-lg border border-slate-800">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-slate-950/80 border-b border-slate-800 text-slate-400 uppercase font-semibold">
              <tr>
                <th className="py-3 px-4">Lead / Issue</th>
                <th className="py-3 px-4">Leakage Category</th>
                <th className="py-3 px-4">Financial Impact</th>
                <th className="py-3 px-4">Confidence</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Audit</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-200">
              {highPriority.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-500 italic">
                    No high-priority leakage events found.
                  </td>
                </tr>
              ) : (
                highPriority.map((issue) => (
                  <tr
                    key={issue.id}
                    onClick={() => setSelectedEventId(issue.id)}
                    className="hover:bg-slate-800/60 cursor-pointer transition-colors group"
                  >
                    <td className="py-3.5 px-4 font-medium text-white">
                      <div className="font-semibold text-slate-100 group-hover:text-blue-400 transition-colors">
                        {issue.lead_name}
                      </div>
                      <div className="text-[11px] text-slate-400 font-normal truncate max-w-xs">
                        {issue.title}
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800 text-slate-300 border border-slate-700">
                        {issue.category}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 font-mono font-semibold text-slate-100">
                      {formatINR(issue.financial_impact)}
                      {issue.tier && (
                        <div className="mt-0.5">
                          <TierBadge tier={issue.tier} size="sm" />
                        </div>
                      )}
                    </td>
                    <td className="py-3.5 px-4">
                      <ConfidenceBadge score={issue.confidence} size="sm" />
                    </td>
                    <td className="py-3.5 px-4">
                      <StatusBadge status={issue.status} />
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <span className="text-xs font-semibold text-blue-400 group-hover:text-blue-300 inline-flex items-center gap-1">
                        Inspect Evidence <ArrowRight className="w-3.5 h-3.5" />
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* â”€â”€ 4. Response Leakage Section â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      {responseLeakage && (
        <div className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-6 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <div className="flex items-center gap-2">
                <Clock className="w-4 h-4 text-blue-400" />
                <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                  Response Delay Impact Analysis
                </h3>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                First outbound response delay vs. lead conversion rates
              </p>
            </div>

            {/* MANDATORY DISCLAIMER BADGE */}
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs font-medium">
              <Info className="w-3.5 h-3.5 shrink-0" />
              <span>Correlation, not causation</span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 pt-2">
            {responseLeakage.buckets.map((b) => (
              <div key={b.bucket_key} className="bg-slate-950/80 border border-slate-800 rounded-lg p-3.5 space-y-1">
                <span className="text-xs font-semibold text-slate-300 block">{b.bucket_label}</span>
                <div className="text-xl font-bold font-mono text-white">
                  {b.sample_too_small ? (
                    <span className="text-xs font-sans text-slate-500 italic">Sample &lt; 20</span>
                  ) : (
                    `${b.conversion_rate}% conv.`
                  )}
                </div>
                <div className="text-[11px] text-slate-400 font-mono">
                  {b.lead_count} leads Â· {b.converted_count} converted
                </div>
              </div>
            ))}

            {responseLeakage.never_contacted && (
              <div className="bg-rose-950/20 border border-rose-900/40 rounded-lg p-3.5 space-y-1">
                <span className="text-xs font-semibold text-rose-400 block">Never Contacted</span>
                <div className="text-xl font-bold font-mono text-white">
                  {responseLeakage.never_contacted.sample_too_small ? (
                    <span className="text-xs font-sans text-slate-500 italic">Sample &lt; 20</span>
                  ) : (
                    `${responseLeakage.never_contacted.conversion_rate}% conv.`
                  )}
                </div>
                <div className="text-[11px] text-slate-400 font-mono">
                  {responseLeakage.never_contacted.lead_count} leads
                </div>
              </div>
            )}
          </div>

          <p className="text-[11px] text-slate-500 italic border-t border-slate-800/80 pt-2">
            * Disclaimer: {responseLeakage.disclaimer}
          </p>
        </div>
      )}

      {/* â”€â”€ 5. Evidence Drawer Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
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


