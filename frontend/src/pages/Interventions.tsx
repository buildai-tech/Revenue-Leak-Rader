import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  KanbanSquare,
  User,
  Clock,
  ArrowRight,
  CheckCircle2,
  DollarSign,
  X,
  Sparkles,
} from 'lucide-react';
import { fetchApi, Intervention } from '../lib/api';
import { formatINR, formatDate } from '../lib/formatters';

const STAGES = [
  { key: 'pending', label: 'Pending Assignment', color: 'border-blue-500/40 text-blue-400' },
  { key: 'contacted', label: 'Contacted', color: 'border-amber-500/40 text-amber-400' },
  { key: 'in_progress', label: 'In Progress / Negotiation', color: 'border-purple-500/40 text-purple-400' },
  { key: 'closed', label: 'Closed / Outcome Recorded', color: 'border-emerald-500/40 text-emerald-400' },
];

export const Interventions: React.FC = () => {
  const queryClient = useQueryClient();
  const [selectedIntervention, setSelectedIntervention] = useState<Intervention | null>(null);
  const [outcomeType, setOutcomeType] = useState('converted');
  const [bookingAmount, setBookingAmount] = useState('5000000');

  const { data: interventions = [], isLoading } = useQuery<Intervention[]>({
    queryKey: ['interventions'],
    queryFn: () => fetchApi('/interventions'),
  });

  const updateStatusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      fetchApi(`/interventions/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['interventions'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-pipeline'] });
    },
  });

  const recordOutcomeMutation = useMutation({
    mutationFn: ({
      interventionId,
      type,
      amount,
    }: {
      interventionId: string;
      type: string;
      amount?: number;
    }) =>
      fetchApi('/recovery/record', {
        method: 'POST',
        body: JSON.stringify({
          intervention_id: interventionId,
          outcome_type: type,
          booking_amount_inr: type === 'converted' ? amount : null,
          evidence: {
            source: 'intervention_kanban',
            notes: 'Outcome recorded via Intervention Kanban workflow',
          },
        }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['interventions'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-recent-recoveries'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-pipeline'] });
      setSelectedIntervention(null);
    },
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-6">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center gap-2.5">
            <KanbanSquare className="w-6 h-6 text-blue-400" />
            Interventions Kanban
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Track sales rep outreach workflow and record validated conversion outcomes to confirm revenue.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="p-12 text-center text-sm text-slate-400">
          <div className="inline-block w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mb-2" />
          <p>Loading Kanban board...</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
          {STAGES.map((stage) => {
            const itemsInStage = interventions.filter((i) => i.status.toLowerCase() === stage.key);

            return (
              <div
                key={stage.key}
                className="bg-[#0c1222] border border-slate-800/80 rounded-xl p-4 flex flex-col space-y-4 min-h-[500px]"
              >
                {/* Stage Header */}
                <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                  <span className={`text-xs font-bold uppercase tracking-wider ${stage.color}`}>
                    {stage.label}
                  </span>
                  <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-slate-900 text-slate-400 border border-slate-800">
                    {itemsInStage.length}
                  </span>
                </div>

                {/* Stage Cards */}
                <div className="space-y-3 flex-1 overflow-y-auto">
                  {itemsInStage.length === 0 ? (
                    <div className="h-32 flex items-center justify-center text-xs text-slate-600 italic border border-dashed border-slate-800 rounded-lg">
                      Empty stage
                    </div>
                  ) : (
                    itemsInStage.map((item) => (
                      <div
                        key={item.id}
                        className="bg-slate-900/90 border border-slate-800 hover:border-slate-700 rounded-lg p-3.5 space-y-3 shadow-md transition-all"
                      >
                        <div>
                          <h4 className="text-xs font-bold text-white tracking-tight">
                            {item.lead_name || 'Prospect'}
                          </h4>
                          <span className="text-[10px] font-mono text-slate-400 block mt-0.5">
                            Playbook: {item.playbook_key || 'Direct Followup'}
                          </span>
                        </div>

                        <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-slate-800/60">
                          <span className="flex items-center gap-1 text-slate-300">
                            <User className="w-3 h-3 text-slate-500" />
                            {item.assigned_rep_name || 'Unassigned'}
                          </span>
                          <span>{formatDate(item.created_at)}</span>
                        </div>

                        {/* Stage Progression Actions */}
                        <div className="pt-2 border-t border-slate-800/60 flex items-center justify-between gap-2">
                          {stage.key === 'pending' && (
                            <button
                              onClick={() => updateStatusMutation.mutate({ id: item.id, status: 'contacted' })}
                              className="w-full py-1 text-[11px] font-semibold text-blue-400 hover:text-white bg-blue-600/10 hover:bg-blue-600 rounded border border-blue-500/20 transition-all"
                            >
                              Mark Contacted →
                            </button>
                          )}
                          {stage.key === 'contacted' && (
                            <button
                              onClick={() => updateStatusMutation.mutate({ id: item.id, status: 'in_progress' })}
                              className="w-full py-1 text-[11px] font-semibold text-purple-400 hover:text-white bg-purple-600/10 hover:bg-purple-600 rounded border border-purple-500/20 transition-all"
                            >
                              Move to In Progress →
                            </button>
                          )}
                          {stage.key === 'in_progress' && (
                            <button
                              onClick={() => setSelectedIntervention(item)}
                              className="w-full py-1 text-[11px] font-semibold text-emerald-400 hover:text-white bg-emerald-600/10 hover:bg-emerald-600 rounded border border-emerald-500/20 transition-all flex items-center justify-center gap-1"
                            >
                              <CheckCircle2 className="w-3 h-3" /> Record Outcome
                            </button>
                          )}
                          {stage.key === 'closed' && (
                            <span className="text-[10px] text-emerald-400 font-mono italic">
                              Outcome Logged ✓
                            </span>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Record Outcome Modal ────────────────────────────────────────── */}
      {selectedIntervention && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-5 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                Record Confirmed Outcome
              </h3>
              <button
                onClick={() => setSelectedIntervention(null)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div>
                <span className="text-slate-400 block mb-1">Target Lead</span>
                <span className="font-semibold text-white text-sm">{selectedIntervention.lead_name}</span>
              </div>

              <div>
                <label className="text-slate-400 block mb-1 font-semibold">Outcome Type</label>
                <select
                  value={outcomeType}
                  onChange={(e) => setOutcomeType(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-blue-500"
                >
                  <option value="converted">Converted (Booking Confirmed)</option>
                  <option value="re_engaged">Re-engaged (Active Discussion)</option>
                  <option value="not_interested">Not Interested / Drop</option>
                  <option value="lost">Lost to Competitor</option>
                </select>
              </div>

              {outcomeType === 'converted' && (
                <div>
                  <label className="text-slate-400 block mb-1 font-semibold">
                    Booking Amount (₹ INR)
                  </label>
                  <input
                    type="number"
                    value={bookingAmount}
                    onChange={(e) => setBookingAmount(e.target.value)}
                    placeholder="e.g. 5000000"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 font-mono focus:outline-none focus:border-blue-500"
                  />
                  <p className="text-[11px] text-emerald-400/90 mt-1">
                    * This will immediately write a CONFIRMED_RECOVERED_REVENUE tier record into the financial engine.
                  </p>
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-3 pt-2 border-t border-slate-800">
              <button
                onClick={() => setSelectedIntervention(null)}
                className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white bg-slate-800 rounded-lg"
              >
                Cancel
              </button>
              <button
                disabled={recordOutcomeMutation.isPending}
                onClick={() =>
                  recordOutcomeMutation.mutate({
                    interventionId: selectedIntervention.id,
                    type: outcomeType,
                    amount: outcomeType === 'converted' ? parseFloat(bookingAmount) : undefined,
                  })
                }
                className="px-4 py-2 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-500 rounded-lg shadow-lg shadow-emerald-600/20 flex items-center gap-1.5"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                {recordOutcomeMutation.isPending ? 'Confirming...' : 'Confirm Outcome'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
