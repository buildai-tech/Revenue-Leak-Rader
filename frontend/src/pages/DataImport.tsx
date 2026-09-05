import React, { useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, FileSpreadsheet, ArrowRight, CheckCircle2, Clock } from 'lucide-react';
import { fetchApi, ImportPreview } from '../lib/api';
import { formatDate } from '../lib/formatters';
import { StatusBadge } from '../components/ui/StatusBadge';

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

  const { data: imports = [], isLoading } = useQuery<ImportPreview[]>({
    queryKey: ['imports-list'],
    queryFn: () => fetchApi('/imports'),
  });

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
      const response = await fetch('/api/imports/upload', {
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

      {/* Historical Imports Table */}
      <div className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-6 space-y-4">
        <h3 className="text-sm font-bold text-white uppercase tracking-wider">
          Batch Ingestion History
        </h3>

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
                      <span className="text-xs font-semibold text-blue-400 hover:underline inline-flex items-center gap-1">
                        Inspect Stepper <ArrowRight className="w-3.5 h-3.5" />
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
