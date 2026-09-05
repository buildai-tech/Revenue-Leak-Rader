import React from 'react';
import { X, Sparkles, CheckCircle2, AlertTriangle, Layers, Database, FileText, ArrowRight } from 'lucide-react';
import { TierBadge } from './TierBadge';
import { ConfidenceBadge } from './ConfidenceBadge';
import { StatusBadge } from './StatusBadge';
import { formatINR, formatDate } from '../../lib/formatters';
import { LeakageEventDetail } from '../../lib/api';

interface EvidenceDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  event: LeakageEventDetail | null;
  onGenerateRecommendation?: (leakageEventId: string) => void;
  isGenerating?: boolean;
}

export const EvidenceDrawer: React.FC<EvidenceDrawerProps> = ({
  isOpen,
  onClose,
  event,
  onGenerateRecommendation,
  isGenerating = false,
}) => {
  if (!isOpen || !event) return null;

  const financial = event.financial || (event.financial_calculations && event.financial_calculations[0]);

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/70 backdrop-blur-sm transition-opacity animate-fade-in"
        onClick={onClose}
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-xl bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col z-10">
          
          {/* Header */}
          <div className="p-6 border-b border-slate-800 bg-slate-950/60 flex items-start justify-between gap-4">
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <StatusBadge status={event.status} />
                <span className="text-xs font-mono text-slate-400">ID: {event.id.slice(0, 8)}</span>
              </div>
              <h2 className="text-lg font-bold text-white tracking-tight">{event.title}</h2>
              <p className="text-xs text-slate-400">
                Lead: <span className="text-slate-200 font-medium">{event.lead_name || 'N/A'}</span>
              </p>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Content Body */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            
            {/* Financial Impact Card */}
            {financial && (
              <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-5 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                    <Layers className="w-4 h-4 text-blue-400" />
                    Financial Calculation
                  </span>
                  <TierBadge tier={financial.tier || event.tier} />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <span className="text-xs text-slate-400 block mb-1">Calculated Impact</span>
                    <span className="text-2xl font-bold font-mono text-white">
                      {formatINR(financial.amount_inr)}
                    </span>
                  </div>
                  <div>
                    <span className="text-xs text-slate-400 block mb-1">Confidence Rating</span>
                    <ConfidenceBadge score={financial.confidence} />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 pt-2 text-xs border-t border-slate-800/60">
                  <div>
                    <span className="text-slate-500 block">Formula ID</span>
                    <span className="text-slate-300 font-mono">{financial.formula_id || 'v1.0'}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Formula Version</span>
                    <span className="text-slate-300 font-mono">{financial.formula_version || '1.0'}</span>
                  </div>
                  <div className="col-span-2">
                    <span className="text-slate-500 block">Data Source</span>
                    <span className="text-slate-300 flex items-center gap-1 mt-0.5">
                      <Database className="w-3 h-3 text-slate-400" />
                      {financial.data_source || 'CRM Lead Database'}
                    </span>
                  </div>
                </div>

                {/* Explicit Disclosed Assumptions */}
                {financial.assumptions && (
                  <div className="bg-slate-900/90 rounded-lg p-3 border border-slate-800/80 mt-2 space-y-1.5">
                    <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
                      Disclosed Assumptions
                    </span>
                    <pre className="text-xs font-mono text-amber-300/90 whitespace-pre-wrap overflow-x-auto">
                      {JSON.stringify(financial.assumptions, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}

            {/* Evidence Checklist */}
            <div className="space-y-3">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                <FileText className="w-4 h-4 text-emerald-400" />
                Auditable Evidence Trail
              </h3>

              {event.evidence && event.evidence.length > 0 ? (
                <div className="space-y-2">
                  {event.evidence.map((item, idx) => (
                    <div
                      key={idx}
                      className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3 text-xs space-y-1"
                    >
                      <div className="flex items-center gap-2 text-emerald-400 font-medium">
                        <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                        <span className="capitalize">{item.evidence_type.replace(/_/g, ' ')}</span>
                      </div>
                      <div className="text-slate-300 pl-5">
                        {item.evidence_payload?.detail || JSON.stringify(item.evidence_payload)}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-slate-500 italic p-3 bg-slate-950/40 rounded-lg border border-slate-800">
                  No discrete evidence items logged for this event.
                </div>
              )}
            </div>

            {/* Metadata Footer */}
            <div className="text-[11px] text-slate-500 space-y-1 pt-2 border-t border-slate-800/60">
              <div>Event Category: <span className="text-slate-400 font-mono">{event.category}</span></div>
              <div>Detected At: <span className="text-slate-400">{formatDate(event.created_at)}</span></div>
            </div>
          </div>

          {/* Footer Action */}
          <div className="p-4 border-t border-slate-800 bg-slate-950/80 flex items-center justify-between gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors"
            >
              Close
            </button>
            {onGenerateRecommendation && (
              <button
                disabled={isGenerating}
                onClick={() => onGenerateRecommendation(event.id)}
                className="px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-lg transition-colors flex items-center gap-1.5 shadow-lg shadow-blue-600/20"
              >
                <Sparkles className="w-3.5 h-3.5" />
                {isGenerating ? 'Generating Playbook...' : 'Generate Recommendation'}
                <ArrowRight className="w-3.5 h-3.5 ml-1" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
