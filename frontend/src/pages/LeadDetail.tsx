import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft,
  Phone,
  Mail,
  Building,
  User,
  DollarSign,
  Calendar,
  AlertTriangle,
  Layers,
  History,
} from 'lucide-react';
import { fetchApi, LeadDetail as LeadDetailType } from '../lib/api';
import { formatINR, formatDate } from '../lib/formatters';
import { StatusBadge } from '../components/ui/StatusBadge';
import { RecoveryScore } from '../components/ui/RecoveryScore';
import { ActivityTimeline } from '../components/ui/ActivityTimeline';

export const LeadDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: lead, isLoading } = useQuery<LeadDetailType>({
    queryKey: ['lead-detail', id],
    queryFn: () => fetchApi(`/leads/${id}`),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className="p-12 text-center text-sm text-slate-400">
        <div className="inline-block w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mb-2" />
        <p>Loading lead intelligence profile...</p>
      </div>
    );
  }

  if (!lead) {
    return (
      <div className="p-12 text-center text-slate-400">
        <p>Lead profile not found.</p>
        <button
          onClick={() => navigate('/leads')}
          className="mt-4 text-xs text-blue-400 hover:underline"
        >
          Return to Leads
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-12">
      {/* Back Button & Header */}
      <div className="space-y-3">
        <button
          onClick={() => navigate('/leads')}
          className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Leads Directory
        </button>

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-5">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-white tracking-tight">{lead.name}</h1>
              <StatusBadge status={lead.status} />
            </div>
            <p className="text-xs text-slate-400 font-mono">ID: {lead.id}</p>
          </div>

          <RecoveryScore score={lead.recovery_score} riskLevel={lead.risk_level} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Column: Profile Info & Contributing Scoring Factors */}
        <div className="space-y-6">
          
          {/* Key Attributes */}
          <div className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-5 space-y-4">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
              Profile Metadata
            </h3>

            <div className="space-y-3 text-xs">
              <div className="flex items-center justify-between py-1.5 border-b border-slate-800/60">
                <span className="text-slate-400 flex items-center gap-1.5">
                  <DollarSign className="w-3.5 h-3.5 text-slate-500" /> Budget
                </span>
                <span className="font-mono font-semibold text-white">{formatINR(lead.budget)}</span>
              </div>

              <div className="flex items-center justify-between py-1.5 border-b border-slate-800/60">
                <span className="text-slate-400 flex items-center gap-1.5">
                  <Phone className="w-3.5 h-3.5 text-slate-500" /> Phone
                </span>
                <span className="font-mono text-slate-200">{lead.phone_normalized || lead.phone_raw || '—'}</span>
              </div>

              <div className="flex items-center justify-between py-1.5 border-b border-slate-800/60">
                <span className="text-slate-400 flex items-center gap-1.5">
                  <Mail className="w-3.5 h-3.5 text-slate-500" /> Email
                </span>
                <span className="text-slate-200 truncate max-w-[160px]">{lead.email || '—'}</span>
              </div>

              <div className="flex items-center justify-between py-1.5 border-b border-slate-800/60">
                <span className="text-slate-400 flex items-center gap-1.5">
                  <Building className="w-3.5 h-3.5 text-slate-500" /> Project
                </span>
                <span className="text-slate-200 font-medium">{lead.project_name || '—'}</span>
              </div>

              <div className="flex items-center justify-between py-1.5 border-b border-slate-800/60">
                <span className="text-slate-400 flex items-center gap-1.5">
                  <User className="w-3.5 h-3.5 text-slate-500" /> Sales Rep
                </span>
                <span className="text-slate-200 font-medium">{lead.sales_rep_name || 'Unassigned'}</span>
              </div>

              <div className="flex items-center justify-between py-1.5">
                <span className="text-slate-400 flex items-center gap-1.5">
                  <Calendar className="w-3.5 h-3.5 text-slate-500" /> Created
                </span>
                <span className="text-slate-300">{formatDate(lead.created_at)}</span>
              </div>
            </div>
          </div>

          {/* Contributing Scoring Factors */}
          <div className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-5 space-y-4">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
              Recovery Score Breakdown
            </h3>

            {lead.contributing_factors.length === 0 ? (
              <div className="text-xs text-slate-500 italic">No negative leakage flags detected.</div>
            ) : (
              <div className="space-y-2.5">
                {lead.contributing_factors.map((factor, idx) => (
                  <div key={idx} className="bg-slate-950/80 border border-slate-800 rounded-lg p-3 text-xs space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-slate-200 capitalize">
                        {factor.rule.replace(/_/g, ' ')}
                      </span>
                      <span className="font-mono text-rose-400 font-bold">+{factor.points} pts</span>
                    </div>
                    {factor.evidence && factor.evidence.map((ev, eIdx) => (
                      <div key={eIdx} className="text-[11px] text-slate-400 pl-2 border-l border-slate-700">
                        {ev.detail || JSON.stringify(ev)}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Activity Timeline */}
        <div className="lg:col-span-2 bg-[#0f172a]/90 border border-slate-800 rounded-xl p-6 space-y-6">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
            <div>
              <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <History className="w-4 h-4 text-blue-400" />
                Chronological Activity Timeline
              </h3>
              <p className="text-xs text-slate-400">All inbound messages, calls, site visits, and status changes</p>
            </div>
            <span className="text-xs font-mono text-slate-400">{lead.events.length} logged events</span>
          </div>

          <ActivityTimeline events={lead.events} />
        </div>
      </div>
    </div>
  );
};
