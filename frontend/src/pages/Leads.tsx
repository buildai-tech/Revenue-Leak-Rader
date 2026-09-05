import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Search, Filter, ArrowRight, UserPlus, Phone, Mail, Building, User } from 'lucide-react';
import { fetchApi, LeadListResponse, LeadListItem } from '../lib/api';
import { formatINR, formatDate } from '../lib/formatters';
import { StatusBadge } from '../components/ui/StatusBadge';
import { DataTable } from '../components/ui/DataTable';

export const Leads: React.FC = () => {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery<LeadListResponse>({
    queryKey: ['leads-list', page, search, statusFilter],
    queryFn: () => {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: '25',
      });
      if (search) params.append('search', search);
      if (statusFilter) params.append('status', statusFilter);
      return fetchApi(`/leads?${params.toString()}`);
    },
  });

  const columns = [
    {
      header: 'Lead Name',
      accessor: (row: LeadListItem) => (
        <div className="font-semibold text-white hover:text-blue-400 transition-colors">
          {row.name}
          {row.source && <span className="block text-[11px] font-normal text-slate-400">{row.source}</span>}
        </div>
      ),
    },
    {
      header: 'Contact Info',
      accessor: (row: LeadListItem) => (
        <div className="space-y-0.5 font-mono text-[11px] text-slate-300">
          {row.phone_normalized && (
            <div className="flex items-center gap-1.5">
              <Phone className="w-3 h-3 text-slate-500" />
              <span>{row.phone_normalized}</span>
            </div>
          )}
          {row.email && (
            <div className="flex items-center gap-1.5 text-slate-400">
              <Mail className="w-3 h-3 text-slate-500" />
              <span className="truncate max-w-[150px]">{row.email}</span>
            </div>
          )}
        </div>
      ),
    },
    {
      header: 'Project / Rep',
      accessor: (row: LeadListItem) => (
        <div className="text-xs space-y-0.5">
          <div className="text-slate-200 font-medium">{row.project_name || '—'}</div>
          <div className="text-slate-400 text-[11px]">{row.sales_rep_name || 'Unassigned'}</div>
        </div>
      ),
    },
    {
      header: 'Budget',
      accessor: (row: LeadListItem) => (
        <span className="font-mono font-semibold text-slate-200">
          {formatINR(row.budget)}
        </span>
      ),
    },
    {
      header: 'Status',
      accessor: (row: LeadListItem) => <StatusBadge status={row.status} />,
    },
    {
      header: 'Enquiry Date',
      accessor: (row: LeadListItem) => (
        <span className="text-slate-400 text-[11px]">{formatDate(row.created_at)}</span>
      ),
    },
  ];

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-6">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight">Leads Intelligence Directory</h1>
          <p className="text-xs text-slate-400 mt-1">
            Browse, search and inspect active and historical CRM records with scoring and timelines.
          </p>
        </div>
      </div>

      {/* Filter Controls */}
      <div className="flex flex-wrap items-center gap-3 bg-[#0f172a]/90 border border-slate-800 p-4 rounded-xl">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search leads by name, phone (+91), or email..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="w-full pl-9 pr-4 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
        </div>

        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-blue-500 capitalize"
        >
          <option value="">All Statuses</option>
          <option value="new">New</option>
          <option value="contacted">Contacted</option>
          <option value="interested">Interested</option>
          <option value="qualified">Qualified</option>
          <option value="dead">Dead</option>
          <option value="converted">Converted</option>
        </select>
      </div>

      {/* Leads Table */}
      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        onRowClick={(row) => navigate(`/leads/${row.id}`)}
        emptyMessage="No leads match your search criteria."
      />

      {/* Pagination */}
      {data && data.total > 25 && (
        <div className="flex items-center justify-between text-xs text-slate-400 pt-2">
          <span>Showing {data.items.length} of {data.total} leads</span>
          <div className="flex gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="px-3 py-1.5 bg-slate-900 border border-slate-800 rounded hover:bg-slate-800 disabled:opacity-40"
            >
              Previous
            </button>
            <button
              disabled={page * 25 >= data.total}
              onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1.5 bg-slate-900 border border-slate-800 rounded hover:bg-slate-800 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
