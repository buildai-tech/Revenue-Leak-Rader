import React from 'react';

interface StatusBadgeProps {
  status: string | null | undefined;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  if (!status) return null;

  const normalized = status.toLowerCase().replace(/_/g, ' ');

  const getStyle = () => {
    switch (normalized) {
      case 'open':
      case 'new':
      case 'pending':
        return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
      case 'contacted':
      case 'in progress':
      case 'interested':
      case 'qualified':
        return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
      case 'converted':
      case 'resolved':
      case 'closed':
      case 'completed':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
      case 'dead':
      case 'lost':
      case 'failed':
      case 'dismissed':
        return 'bg-slate-500/10 text-slate-400 border-slate-500/20';
      default:
        return 'bg-slate-500/10 text-slate-300 border-slate-500/20';
    }
  };

  return (
    <span className={`inline-flex items-center text-xs font-medium px-2.5 py-0.5 rounded-full border ${getStyle()} capitalize`}>
      {normalized}
    </span>
  );
};
