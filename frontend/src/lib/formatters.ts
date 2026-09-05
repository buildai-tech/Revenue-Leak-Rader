/**
 * Formatting utilities for Indian Rupee figures, dates, and tiers.
 */

export function formatINR(amount: number | null | undefined, compact: boolean = false): string {
  if (amount === null || amount === undefined || isNaN(amount)) return '₹0';

  if (compact) {
    if (Math.abs(amount) >= 10000000) {
      return `₹${(amount / 10000000).toFixed(2)} Cr`;
    }
    if (Math.abs(amount) >= 100000) {
      return `₹${(amount / 100000).toFixed(2)} L`;
    }
    if (Math.abs(amount) >= 1000) {
      return `₹${(amount / 1000).toFixed(1)} K`;
    }
  }

  // Indian number grouping standard
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return '—';
  try {
    const d = new Date(dateString);
    return new Intl.DateTimeFormat('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(d);
  } catch {
    return dateString;
  }
}

export function formatTimeAgo(dateString: string | null | undefined): string {
  if (!dateString) return '—';
  try {
    const d = new Date(dateString);
    const now = new Date();
    const diffSec = Math.floor((now.getTime() - d.getTime()) / 1000);

    if (diffSec < 60) return 'just now';
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    if (diffSec < 2592000) return `${Math.floor(diffSec / 86400)}d ago`;
    return formatDate(dateString);
  } catch {
    return dateString;
  }
}

export const TIER_CONFIG: Record<string, { label: string; desc: string; color: string; bg: string; border: string }> = {
  observed_fact: {
    label: 'Observed Fact',
    desc: 'Direct empirical data with zero speculative assumptions applied',
    color: 'text-sky-400',
    bg: 'bg-sky-500/10',
    border: 'border-sky-500/20',
  },
  model_prediction: {
    label: 'Model Prediction',
    desc: 'Heuristic or statistical assessment scored with measurable confidence',
    color: 'text-purple-400',
    bg: 'bg-purple-500/10',
    border: 'border-purple-500/20',
  },
  estimated_financial_impact: {
    label: 'Estimated Financial Impact',
    desc: 'Rigorous calculation based on explicit, disclosed financial assumptions',
    color: 'text-amber-400',
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/20',
  },
  confirmed_recovered_revenue: {
    label: 'Confirmed Recovered',
    desc: 'Verified booking/conversion value recorded through validated intervention outcome',
    color: 'text-emerald-400',
    bg: 'bg-emerald-500/10',
    border: 'border-emerald-500/20',
  },
};
