import React from 'react';

interface Column<T> {
  header: string;
  accessor?: keyof T | ((row: T) => React.ReactNode);
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  onRowClick?: (row: T) => void;
  isLoading?: boolean;
  emptyMessage?: string;
}

export function DataTable<T extends { id?: string | number }>({
  columns,
  data,
  onRowClick,
  isLoading = false,
  emptyMessage = 'No records found.',
}: DataTableProps<T>) {
  if (isLoading) {
    return (
      <div className="w-full bg-slate-900/60 border border-slate-800 rounded-xl p-12 text-center text-sm text-slate-400">
        <div className="inline-block w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mb-2" />
        <p>Loading real-time records...</p>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="w-full bg-slate-900/40 border border-slate-800 rounded-xl p-12 text-center text-sm text-slate-500">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="w-full overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60 shadow-lg">
      <table className="w-full text-left text-xs border-collapse">
        <thead className="bg-slate-950/80 border-b border-slate-800 text-slate-400 uppercase tracking-wider font-semibold">
          <tr>
            {columns.map((col, idx) => (
              <th key={idx} className={`py-3.5 px-4 ${col.className || ''}`}>
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/60 text-slate-200">
          {data.map((row, rowIdx) => (
            <tr
              key={row.id || rowIdx}
              onClick={() => onRowClick && onRowClick(row)}
              className={`transition-colors ${
                onRowClick ? 'cursor-pointer hover:bg-slate-800/60' : 'hover:bg-slate-800/30'
              }`}
            >
              {columns.map((col, colIdx) => (
                <td key={colIdx} className={`py-3.5 px-4 ${col.className || ''}`}>
                  {typeof col.accessor === 'function'
                    ? col.accessor(row)
                    : col.accessor
                    ? (row[col.accessor] as unknown as React.ReactNode)
                    : null}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
