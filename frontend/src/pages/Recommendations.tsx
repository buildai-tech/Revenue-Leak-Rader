import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Sparkles, ArrowRight, UserPlus, CheckCircle2, Copy } from 'lucide-react';
import { fetchApi, Recommendation } from '../lib/api';
import { formatDate } from '../lib/formatters';

export const Recommendations: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const { data: recommendations = [], isLoading } = useQuery<Recommendation[]>({
    queryKey: ['recommendations'],
    queryFn: () => fetchApi('/recommendations'),
  });

  const createInterventionMutation = useMutation({
    mutationFn: (recId: string) =>
      fetchApi('/interventions', {
        method: 'POST',
        body: JSON.stringify({
          recommendation_id: recId,
          assigned_rep_name: 'Priya Sharma',
          notes: 'Auto-assigned from playbook recommendation.',
        }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['interventions'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-pipeline'] });
      navigate('/interventions');
    },
  });

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-6">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center gap-2.5">
            <Sparkles className="w-6 h-6 text-amber-400" />
            Playbook Recommendations
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Deterministic playbooks with personalized outreach templates for rapid recovery.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="p-12 text-center text-sm text-slate-400">
          <div className="inline-block w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mb-2" />
          <p>Loading generated recommendations...</p>
        </div>
      ) : recommendations.length === 0 ? (
        <div className="bg-[#0f172a]/60 border border-slate-800 rounded-xl p-12 text-center space-y-3">
          <Sparkles className="w-8 h-8 text-slate-600 mx-auto" />
          <h3 className="text-sm font-semibold text-slate-300">No Recommendations Generated Yet</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            Inspect a leakage event from the Command Center or Leakage Ledger and click "Generate Recommendation".
          </p>
          <button
            onClick={() => navigate('/leakage')}
            className="px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-500 rounded-lg transition-colors inline-flex items-center gap-1.5"
          >
            Explore Leakage Events <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {recommendations.map((rec) => (
            <div
              key={rec.id}
              className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-5 space-y-4 hover:border-slate-700 transition-colors flex flex-col justify-between"
            >
              <div className="space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="space-y-0.5">
                    <span className="text-[11px] font-mono font-semibold uppercase text-amber-400">
                      Playbook: {rec.playbook_key}
                    </span>
                    <h3 className="text-sm font-bold text-white">
                      Lead: {rec.lead_name || 'Prospect'}
                    </h3>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                    Source: {rec.generated_by}
                  </span>
                </div>

                <div className="bg-slate-950/80 border border-slate-800 rounded-lg p-3.5 text-xs text-slate-300 leading-relaxed font-sans">
                  {rec.generated_copy}
                </div>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-slate-800/60 text-xs">
                <span className="text-[11px] text-slate-500">{formatDate(rec.created_at)}</span>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleCopy(rec.id, rec.generated_copy)}
                    className="px-3 py-1.5 bg-slate-900 border border-slate-800 rounded hover:bg-slate-800 text-slate-300 transition-colors flex items-center gap-1"
                  >
                    {copiedId === rec.id ? (
                      <>
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-emerald-400">Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5" />
                        <span>Copy</span>
                      </>
                    )}
                  </button>

                  <button
                    disabled={createInterventionMutation.isPending}
                    onClick={() => createInterventionMutation.mutate(rec.id)}
                    className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 font-semibold text-white rounded transition-colors flex items-center gap-1 shadow-sm shadow-blue-600/20"
                  >
                    <UserPlus className="w-3.5 h-3.5" />
                    <span>Assign Intervention</span>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
