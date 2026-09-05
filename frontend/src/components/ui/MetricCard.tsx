import React from 'react';
import { TierBadge } from './TierBadge';
import { ConfidenceBadge } from './ConfidenceBadge';

interface MetricCardProps {
  title: string;
  value: string;
  subtitle?: string;
  tier?: string;
  confidence?: number;
  icon?: React.ReactNode;
  trend?: {
    value: string;
    positive?: boolean;
  };
  onClick?: () => void;
  accentBorder?: 'blue' | 'amber' | 'emerald' | 'purple' | 'slate';
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  subtitle,
  tier,
  confidence,
  icon,
  trend,
  onClick,
  accentBorder = 'slate',
}) => {
  const borderStyles = {
    blue: 'hover:border-blue-500/50',
    amber: 'hover:border-amber-500/50',
    emerald: 'hover:border-emerald-500/50',
    purple: 'hover:border-purple-500/50',
    slate: 'hover:border-slate-600',
  };

  return (
    <div
      onClick={onClick}
      className={`relative group bg-[#0f172a]/90 border border-slate-800/80 rounded-xl p-5 transition-all duration-200 ${
        onClick ? 'cursor-pointer hover:bg-slate-850 hover:shadow-lg hover:shadow-black/40 ' + borderStyles[accentBorder] : ''
      }`}
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          {title}
        </span>
        {icon && <div className="text-slate-400 group-hover:text-slate-200 transition-colors">{icon}</div>}
      </div>

      <div className="space-y-2">
        <div className="text-2xl lg:text-3xl font-bold font-mono tracking-tight text-white flex items-baseline gap-2">
          {value}
          {trend && (
            <span className={`text-xs font-sans font-medium ${trend.positive ? 'text-emerald-400' : 'text-slate-400'}`}>
              {trend.value}
            </span>
          )}
        </div>

        {(tier || confidence !== undefined || subtitle) && (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            {tier && <TierBadge tier={tier} size="sm" />}
            {confidence !== undefined && <ConfidenceBadge score={confidence} size="sm" />}
            {subtitle && <span className="text-xs text-slate-400">{subtitle}</span>}
          </div>
        )}
      </div>
    </div>
  );
};
