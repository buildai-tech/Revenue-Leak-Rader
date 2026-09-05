import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  CheckCircle2,
  Table,
  Sliders,
  Play,
  Layers,
  ArrowRight,
  AlertCircle,
  AlertTriangle,
  RotateCw,
} from 'lucide-react';
import { fetchApi, ImportPreview } from '../lib/api';
import { StatusBadge } from '../components/ui/StatusBadge';

/**
 * Sanitize a backend error message for display: strip control characters
 * that could mangle the layout and cap its length. The backend only stores
 * short, human-readable messages (never stack traces or credentials), and
 * React escapes text output by default.
 */
function sanitizeErrorMessage(raw?: string | null): string {
  const msg = (raw || '')
    .replace(/[\u0000-\u001F\u007F]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!msg) {
    return 'The import could not be processed. Please try again or re-upload the file.';
  }
  return msg.length > 300 ? `${msg.slice(0, 300)}…` : msg;
}

const TARGET_FIELDS = [
  { key: 'name', label: 'Lead Full Name', required: true },
  { key: 'phone_raw', label: 'Contact Phone Number', required: true },
  { key: 'email', label: 'Email Address', required: false },
  { key: 'status', label: 'Lead Status', required: false },
  { key: 'budget', label: 'Budget / Deal Value', required: false },
  { key: 'source', label: 'Lead Channel / Source', required: false },
  { key: 'project_name', label: 'Project / Property Name', required: false },
  { key: 'sales_rep_name', label: 'Assigned Sales Agent', required: false },
  { key: 'created_at', label: 'Enquiry Date', required: false },
  { key: 'last_followup_at', label: 'Last Follow-up Date', required: false },
];

interface SuggestionsResponse {
  suggestions?: Array<{ source_column: string; target_field: string; confidence?: number; suggested_by?: string }>;
  target_fields?: string[];
  source?: "llm" | "heuristic";
  provider_error?: string | null;
  /** True while the backend runs the optional AI refinement in the background —
   *  the heuristic pre-fill is already usable, and a refetch will upgrade it. */
  refinement_pending?: boolean;
}

export const DataImportDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [mappings, setMappings] = useState<Record<string, string>>({});
  const [step, setStep] = useState<1 | 2 | 3 | 4>(2); // 1: Upload (done), 2: Preview & Map, 3: Process, 4: Results
  const [processingStats, setProcessingStats] = useState<any>(null);
  // Once the user hand-adjusts a dropdown, never clobber their choice again —
  // even when the async AI refinement lands and the suggestions are re-fetched.
  const userEditedRef = useRef(false);

  const { data: importData, isLoading } = useQuery<ImportPreview>({
    queryKey: ['import-detail', id],
    queryFn: () => fetchApi(`/imports/${id}`),
    enabled: !!id,
  });

  const { data: suggestionsData, isError: suggestionsError } = useQuery<SuggestionsResponse>({
    queryKey: ['import-suggestions', id],
    queryFn: () => fetchApi(`/imports/${id}/suggestions`),
    enabled: !!id,
    retry: false,
    // The backend returns deterministic heuristics immediately and refines them
    // with the AI in the background. Poll lightly while refinement is pending so
    // the better mapping lands as soon as it is ready — never blocking first paint.
    refetchInterval: (query) =>
      (query.state.data as SuggestionsResponse | undefined)?.refinement_pending ? 2000 : false,
  });

  // Pre-fill mappings from suggestions, but never overwrite a manual selection.
  useEffect(() => {
    if (!userEditedRef.current && suggestionsData?.suggestions) {
      const initial: Record<string, string> = {};
      suggestionsData.suggestions.forEach((s) => {
        initial[s.source_column] = s.target_field;
      });
      setMappings(initial);
    }
  }, [suggestionsData]);

  const processMutation = useMutation({
    mutationFn: () => {
      const mappingList = Object.entries(mappings).map(([source_column, target_field]) => ({
        source_column,
        target_field,
      }));
      return fetchApi(`/imports/${id}/map`, {
        method: 'POST',
        body: JSON.stringify({ mappings: mappingList }),
      });
    },
    onSuccess: (data) => {
      setProcessingStats(data);
      setStep(4);
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
      queryClient.invalidateQueries({ queryKey: ['leads-list'] });
      queryClient.invalidateQueries({ queryKey: ['leakage-list'] });
    },
  });

  if (isLoading || !importData) {
    return (
      <div className="p-12 text-center text-sm text-slate-400">
        <div className="inline-block w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mb-2" />
        <p>Loading import batch preview...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-12">
      {/* Header */}
      <div className="space-y-3">
        <button
          onClick={() => navigate('/data-import')}
          className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Ingestion History
        </button>

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-5">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">{importData.filename}</h1>
            <p className="text-xs text-slate-400 font-mono">ID: {importData.id}</p>
          </div>
          <StatusBadge status={importData.status} />
        </div>

        {importData.status === 'failed' && (
          <div className="flex items-start gap-2 bg-rose-500/10 border border-rose-500/30 rounded-lg p-3">
            <AlertCircle className="w-4 h-4 text-rose-400 mt-0.5 shrink-0" />
            <div>
              <p className="text-xs font-semibold text-rose-300">Import failed</p>
              <p className="text-xs text-slate-300 break-words">
                {sanitizeErrorMessage(importData.error_message)}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Stepper Progress Indicator */}
      <div className="grid grid-cols-4 gap-2 bg-[#0c1222] p-2 rounded-xl border border-slate-800">
        {[
          { num: 1, label: 'Upload', done: true },
          { num: 2, label: 'Column Mapping', done: step >= 2 },
          { num: 3, label: 'Run Pipeline', done: step >= 3 },
          { num: 4, label: 'Audit Results', done: step >= 4 },
        ].map((s) => (
          <div
            key={s.num}
            className={`flex items-center gap-2 p-2 rounded-lg text-xs font-semibold ${
              s.done ? 'bg-blue-600/15 text-blue-400 border border-blue-500/20' : 'text-slate-500'
            }`}
          >
            <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] ${
              s.done ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-400'
            }`}>
              {s.done && s.num < step ? '✓' : s.num}
            </span>
            <span>{s.label}</span>
          </div>
        ))}
      </div>

      {/* Step 2: Column Mapping & Preview */}
      {step === 2 && (
        <div className="space-y-6">
          <div className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                  <Sliders className="w-4 h-4 text-blue-400" />
                  Map Source Columns to Target Fields
                </h3>
                <p className="text-xs text-slate-400">
                  Confirm the target field for each recognized column in your uploaded batch.
                </p>
              </div>
            </div>

            {/* Show a clear message if suggestions could not be loaded at all
                (e.g. original upload no longer available on the server). */}
            {suggestionsError && (
              <div className="flex items-start gap-2 bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 mb-4">
                <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-xs font-semibold text-amber-300">Column suggestions could not be loaded</p>
                  <p className="text-xs text-slate-400 break-words">
                    The source file for this import may no longer be available on the server.
                    Please delete this batch and re-upload the CSV to continue.
                  </p>
                </div>
              </div>
            )}

            {/* Show AI/heuristic provider status */}
            {suggestionsData?.provider_error && (
              <div className="flex items-start gap-2 bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 mb-4">
                <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-xs font-semibold text-amber-300">Heuristic fallback active</p>
                  <p className="text-xs text-slate-400 break-words">
                    {sanitizeErrorMessage(suggestionsData.provider_error)}
                  </p>
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {importData?.columns?.map((col) => (
                <div
                  key={col}
                  className="bg-slate-950/80 border border-slate-800/80 rounded-lg p-3.5 flex items-center justify-between gap-4"
                >
                  <div className="truncate">
                    <span className="text-xs font-mono font-semibold text-slate-200 block truncate">
                      {col}
                    </span>
                    <span className="text-[10px] text-slate-500">CSV Column</span>
                  </div>

                  <select
                    value={mappings[col] || ''}
                    onChange={(e) => {
                      userEditedRef.current = true;
                      setMappings({ ...mappings, [col]: e.target.value });
                    }}
                    className="bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500 max-w-[200px]"
                  >
                    <option value="">— Ignore Column —</option>
                    {TARGET_FIELDS.map((t) => (
                      <option key={t.key} value={t.key}>
                        {t.label} {t.required ? '(Required)' : ''}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>

            <div className="pt-4 border-t border-slate-800 flex items-center justify-end">
              <button
                disabled={processMutation.isPending}
                onClick={() => processMutation.mutate()}
                className="px-5 py-2.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-lg transition-colors shadow-lg shadow-blue-600/20 flex items-center gap-2"
              >
                <Play className="w-3.5 h-3.5" />
                {processMutation.isPending ? 'Executing Pipeline...' : 'Confirm Mapping & Run Detection'}
              </button>
            </div>
          </div>

          {/* Raw Preview Table */}
          <div className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-6 space-y-4">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <Table className="w-4 h-4 text-emerald-400" />
              Raw Batch Sample Preview (First 10 Rows)
            </h3>

            <div className="overflow-x-auto rounded-lg border border-slate-800">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-slate-950/80 border-b border-slate-800 text-slate-400 uppercase font-semibold">
                  <tr>
                    {importData.columns.map((c) => (
                      <th key={c} className="py-2.5 px-3 whitespace-nowrap">{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-slate-200 font-mono text-[11px]">
                  {importData.preview_rows.map((row, idx) => (
                    <tr key={idx} className="hover:bg-slate-800/40">
                      {importData.columns.map((c) => (
                        <td key={c} className="py-2.5 px-3 whitespace-nowrap">{String(row[c] || '')}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Step 4: Results View */}
      {step === 4 && processingStats && (
        <div className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-8 space-y-6 text-center max-w-2xl mx-auto shadow-2xl">
          <div className="w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 mx-auto">
            <CheckCircle2 className="w-8 h-8" />
          </div>

          <div className="space-y-1">
            <h2 className="text-xl font-bold text-white">Pipeline Execution Complete!</h2>
            <p className="text-xs text-slate-400">
              Raw records normalized, identity resolved, and deterministic leakage rules evaluated.
            </p>
          </div>

          {processingStats?.import_stats?.error && (
            <div className="flex items-start gap-2 bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 text-left">
              <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
              <div>
                <p className="text-xs font-semibold text-amber-300">Pipeline finished with warnings</p>
                <p className="text-xs text-slate-300 break-words">
                  {sanitizeErrorMessage(String(processingStats.import_stats.error))}
                </p>
              </div>
            </div>
          )}

          <div className="grid grid-cols-3 gap-4 text-left">
            <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
              <span className="text-[11px] text-slate-500 uppercase font-semibold block">Leads Created</span>
              <span className="text-xl font-bold font-mono text-white">
                {processingStats.import_stats?.leads_created || 0}
              </span>
            </div>
            <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
              <span className="text-[11px] text-slate-500 uppercase font-semibold block">Duplicates Merged</span>
              <span className="text-xl font-bold font-mono text-emerald-400">
                {processingStats.merge_stats?.total_merges || 0}
              </span>
            </div>
            <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
              <span className="text-[11px] text-slate-500 uppercase font-semibold block">Leakage Detected</span>
              <span className="text-xl font-bold font-mono text-rose-400">
                {processingStats.leakage_stats?.total_events || 0}
              </span>
            </div>
          </div>

          <div className="pt-4 flex items-center justify-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="px-6 py-2.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-500 rounded-lg transition-colors shadow-lg shadow-blue-600/20 flex items-center gap-2"
            >
              Open Command Center <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
