import React, { useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, FileSpreadsheet, ArrowRight, CheckCircle2, Clock, Trash2, AlertTriangle, RefreshCw, X } from 'lucide-react';
import { fetchApi, ImportPreview, deleteImport, clearDemoImports } from '../lib/api';
import { formatDate } from '../lib/formatters';
import { StatusBadge } from '../components/ui/StatusBadge';

const API_BASE = (import.meta.env.VITE_API_URL as string) || '/api';

const ALLOWED_EXTENSIONS = ['csv', 'xls', 'xlsx'];

const ALLOWED_MIME_TYPES = new Set([
  'text/csv',
  'application/csv',
  'text/comma-separated-values',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  // Common browser/OS fallback when the MIME type cannot be determined
  'application/octet-stream',
]);

const INVALID_FILE_MESSAGE = 'Unsupported file type. Please select a CSV, XLS, or XLSX file.';

function getFileExtension(file: File): string {
  return file.name.split('.').pop()?.toLowerCase() ?? '';
}

function validateSpreadsheetFile(file: File): string | null {
  const ext = getFileExtension(file);
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return INVALID_FILE_MESSAGE;
  }
  const mime = (file.type || '').toLowerCase();
  if (mime && !ALLOWED_MIME_TYPES.has(mime)) {
    return INVALID_FILE_MESSAGE;
  }
  return null;
}

function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;

  const kb = bytes / 1024;
  if (kb < 1024) {
    const rounded = Math.round(kb * 10) / 10;
    return `${Number.isInteger(rounded) ? rounded : rounded.toFixed(1)} KB`;
  }

  const mb = kb / 1024;
  const rounded = Math.round(mb * 100) / 100;
  return `${Number.isInteger(rounded) ? rounded : rounded.toFixed(2)} MB`;
}

export const DataImport: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragDepthRef = useRef(0);

  // Deletion & reset states
  const [batchToDelete, setBatchToDelete] = useState<ImportPreview | null>(null);
  const [isResetModalOpen, setIsResetModalOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [actionNotification, setActionNotification] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);

  const { data: imports = [], isLoading } = useQuery<ImportPreview[]>({
    queryKey: ['imports-list'],
    queryFn: () => fetchApi('/imports'),
  });

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ['imports-list'] });
    queryClient.invalidateQueries({ queryKey: ['imports'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    queryClient.invalidateQueries({ queryKey: ['leads'] });
    queryClient.invalidateQueries({ queryKey: ['leakage'] });
    queryClient.invalidateQueries({ queryKey: ['recommendations'] });
    queryClient.invalidateQueries({ queryKey: ['interventions'] });
    queryClient.invalidateQueries({ queryKey: ['reports'] });
  };

  const handleDeleteBatch = async () => {
    if (!batchToDelete) return;
    setIsDeleting(true);
    setActionNotification(null);
    try {
      const res = await deleteImport(batchToDelete.id);
      setActionNotification({
        type: 'success',
        message: `Batch "${batchToDelete.filename}" deleted permanently (${res.deleted_leads || 0} leads and derived records removed).`,
      });
      setBatchToDelete(null);
      invalidateAll();
    } catch (err: any) {
      setActionNotification({
        type: 'error',
        message: err?.message || 'Failed to delete imported batch.',
      });
    } finally {
      setIsDeleting(false);
    }
  };

  const handleClearAllImports = async () => {
    setIsDeleting(true);
    setActionNotification(null);
    try {
      const res = await clearDemoImports();
      setActionNotification({
        type: 'success',
        message: `All imported demo data cleared permanently (${res.deleted_batches || 0} batches, ${res.deleted_leads || 0} leads removed).`,
      });
      setIsResetModalOpen(false);
      invalidateAll();
    } catch (err: any) {
      setActionNotification({
        type: 'error',
        message: err?.message || 'Failed to clear imported demo data.',
      });
    } finally {
      setIsDeleting(false);
    }
  };

  const handleFileSelected = (selected: File | null): void => {
    // No file selected (e.g. the picker was cancelled) → keep current state untouched
    if (!selected) return;

    const error = validateSpreadsheetFile(selected);
    if (error) {
      setUploadError(error);
      return;
    }

    setFile(selected);
    setUploadError(null);
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>): void => {
    handleFileSelected(e.target.files?.[0] ?? null);
    // Reset the input so selecting the same file again still triggers onChange
    e.target.value = '';
  };

  const handleDragEnter = (e: React.DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    e.stopPropagation();
    dragDepthRef.current += 1;
    setIsDragging(true);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    e.stopPropagation();
    if (dragDepthRef.current === 0) dragDepthRef.current = 1;
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    e.stopPropagation();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    e.stopPropagation();
    dragDepthRef.current = 0;
    setIsDragging(false);
    handleFileSelected(e.dataTransfer.files?.[0] ?? null);
  };

  const handleFileUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    setIsUploading(true);
    setUploadError(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${API_BASE}/imports/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        let message = 'File upload failed';
        try {
          const errorJson = await response.json();
          message = errorJson.detail || errorJson.error || message;
        } catch {
          // Ignore — fall back to the generic message above
        }
        throw new Error(message);
      }

      const data: ImportPreview = await response.json();
      queryClient.invalidateQueries({ queryKey: ['imports-list'] });
      navigate(`/data-import/${data.id}`);
    } catch (err: any) {
      setUploadError(err.message || 'Upload error');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-6">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center gap-2.5">
            <UploadCloud className="w-6 h-6 text-blue-400" />
            CRM Data Ingestion
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Ingest raw CSV / XLSX lead records with automated column normalization and deduplication.
          </p>
        </div>
      </div>

      {/* Upload Zone */}
      <div className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-8 max-w-2xl mx-auto shadow-xl">
        <form onSubmit={handleFileUpload} className="space-y-6 text-center">
          <div
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                fileInputRef.current?.click();
              }
            }}
            onDragEnter={handleDragEnter}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-xl p-8 transition-colors bg-slate-950/50 flex flex-col items-center justify-center gap-3 cursor-pointer ${
              isDragging
                ? 'border-blue-400 bg-blue-500/10'
                : file
                  ? 'border-emerald-500/60 hover:border-emerald-400'
                  : 'border-slate-700 hover:border-blue-500'
            }`}
          >
            <div className={`w-12 h-12 rounded-full border flex items-center justify-center transition-colors ${
              file
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                : 'bg-blue-500/10 border-blue-500/30 text-blue-400'
            }`}>
              <FileSpreadsheet className="w-6 h-6" />
            </div>

            <div>
              <span className="cursor-pointer text-sm font-semibold text-blue-400 hover:text-blue-300">
                Click to select CSV or XLSX file
              </span>
              <input
                ref={fileInputRef}
                id="file-upload"
                type="file"
                accept=".csv,.xls,.xlsx,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={handleFileInputChange}
                onClick={(e) => e.stopPropagation()}
                className="hidden"
              />
              <p className="text-xs text-slate-500 mt-1">Supports UTF-8 CSV, XLS, and XLSX formats</p>
            </div>

            {file && (
              <div className="flex flex-col items-center gap-1.5 mt-1">
                <p className="text-xs text-slate-500">Selected file:</p>
                <p className="text-sm font-semibold text-white break-all">{file.name}</p>
                <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-3 py-1.5 rounded-full border border-emerald-500/20">
                  {getFileExtension(file).toUpperCase()} • {formatFileSize(file.size)}
                </span>
              </div>
            )}
          </div>

          {uploadError && (
            <div className="text-xs text-rose-400 bg-rose-500/10 p-3 rounded-lg border border-rose-500/20">
              {uploadError}
            </div>
          )}

          <button
            type="submit"
            disabled={!file || isUploading}
            className="w-full py-2.5 px-4 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-lg transition-colors shadow-lg shadow-blue-600/20 flex items-center justify-center gap-2"
          >
            <UploadCloud className="w-4 h-4" />
            {isUploading ? 'Uploading & Parsing...' : 'Proceed to Preview & Column Mapping'}
          </button>
        </form>
      </div>

      {/* Action Notification Toast/Banner */}
      {actionNotification && (
        <div
          className={`p-4 rounded-xl border flex items-center justify-between text-xs font-medium animate-in fade-in ${
            actionNotification.type === 'success'
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
              : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
          }`}
        >
          <div className="flex items-center gap-2">
            {actionNotification.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            )}
            <span>{actionNotification.message}</span>
          </div>
          <button
            type="button"
            onClick={() => setActionNotification(null)}
            className="p-1 hover:opacity-75 transition-opacity"
            title="Dismiss"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Historical Imports Table */}
      <div className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Batch Ingestion History
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Historical CSV and XLSX files processed into the revenue engine.
            </p>
          </div>
          {imports.length > 0 && (
            <button
              type="button"
              onClick={() => setIsResetModalOpen(true)}
              className="px-4 py-2 text-sm font-semibold text-rose-300 hover:text-white bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 hover:border-rose-500/50 rounded-lg transition-colors inline-flex items-center gap-2"
            >
              <Trash2 className="w-4 h-4" />
              Clear All Demo Data
            </button>
          )}
        </div>

        <div className="overflow-x-auto rounded-lg border border-slate-800">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-slate-950/80 border-b border-slate-800 text-slate-400 uppercase font-semibold">
              <tr>
                <th className="py-3 px-4">Filename</th>
                <th className="py-3 px-4">Type</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Row Count</th>
                <th className="py-3 px-4">Imported At</th>
                <th className="py-3 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-200">
              {imports.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-500 italic">
                    No files ingested yet.
                  </td>
                </tr>
              ) : (
                imports.map((item) => (
                  <tr
                    key={item.id}
                    onClick={() => navigate(`/data-import/${item.id}`)}
                    className="hover:bg-slate-800/60 cursor-pointer transition-colors"
                  >
                    <td className="py-3.5 px-4 font-semibold text-white">{item.filename}</td>
                    <td className="py-3.5 px-4 font-mono text-slate-400 uppercase">{item.file_type}</td>
                    <td className="py-3.5 px-4"><StatusBadge status={item.status} /></td>
                    <td className="py-3.5 px-4 font-mono">{item.row_count || '—'}</td>
                    <td className="py-3.5 px-4 text-slate-400">{formatDate(item.created_at)}</td>
                    <td className="py-3.5 px-4 text-right">
                      <div className="inline-flex items-center gap-2">
                        <span className="text-xs font-semibold text-blue-400 hover:underline inline-flex items-center gap-1">
                          Inspect Stepper <ArrowRight className="w-3.5 h-3.5" />
                        </span>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setBatchToDelete(item);
                          }}
                          title="Delete this batch"
                          className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-md transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Delete Batch Confirmation Dialog */}
      {batchToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-[#0f172a] border border-slate-800 rounded-xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-400 flex items-center justify-center shrink-0">
                <Trash2 className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-base font-bold text-white">Delete this imported batch?</h4>
                <p className="text-xs text-slate-400 mt-1">
                  This will permanently remove <span className="font-semibold text-slate-200">"{batchToDelete.filename}"</span> and its related demo records, leads, and derived leakage events.
                </p>
              </div>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800 text-xs text-slate-400 space-y-1 font-mono">
              <div>Batch: <span className="text-slate-200">{batchToDelete.filename}</span></div>
              <div>Type: <span className="text-slate-200 uppercase">{batchToDelete.file_type}</span></div>
              <div>Rows: <span className="text-slate-200">{batchToDelete.row_count ?? 'N/A'}</span></div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                disabled={isDeleting}
                onClick={() => setBatchToDelete(null)}
                className="px-4 py-2 text-xs font-semibold text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isDeleting}
                onClick={handleDeleteBatch}
                className="px-4 py-2 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-500 disabled:opacity-50 rounded-lg transition-colors shadow-lg shadow-rose-600/20 flex items-center gap-1.5"
              >
                {isDeleting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    Deleting...
                  </>
                ) : (
                  <>
                    <Trash2 className="w-3.5 h-3.5" />
                    Delete Batch
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Clear Demo Data Confirmation Dialog */}
      {isResetModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-[#0f172a] border border-slate-800 rounded-xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-base font-bold text-white">Clear All Demo Data?</h4>
                <p className="text-xs text-slate-400 mt-1">
                  This will permanently delete all imported demo batches and their derived data.
                </p>
                <p className="text-xs text-slate-400 mt-1">
                  Your organization, project, and baseline structure will remain.
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                disabled={isDeleting}
                onClick={() => setIsResetModalOpen(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isDeleting}
                onClick={handleClearAllImports}
                className="px-4 py-2 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-500 disabled:opacity-50 rounded-lg transition-colors shadow-lg shadow-rose-600/20 flex items-center gap-1.5"
              >
                {isDeleting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    Clearing...
                  </>
                ) : (
                  'Clear All Data'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
