import React from 'react';
import { TIER_CONFIG } from '../../lib/formatters';
import { ShieldCheck, Sparkles, Calculator, CheckCircle2 } from 'lucide-react';

interface TierBadgeProps {
  tier: string | null | undefined;
  showDesc?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export const TierBadge: React.FC<TierBadgeProps> = ({ tier, showDesc = false, size = 'md' }) => {
  if (!tier) return null;
  const config = TIER_CONFIG[tier.toLowerCase()] || {
    label: tier.replace(/_/g, ' '),
    desc: 'Unclassified tier',
    color: 'text-slate-400',
    bg: 'bg-slate-500/10',
    border: 'border-slate-500/20',
  };

  const getIcon = () => {
    switch (tier.toLowerCase()) {
      case 'observed_fact':
        return <ShieldCheck className="w-3.5 h-3.5 shrink-0" />;
      case 'model_prediction':
        return <Sparkles className="w-3.5 h-3.5 shrink-0" />;
      case 'estimated_financial_impact':
        return <Calculator className="w-3.5 h-3.5 shrink-0" />;
      case 'confirmed_recovered_revenue':
        return <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />;
      default:
        return null;
    }
  };

  const sizeClasses = {
    sm: 'text-[11px] px-2 py-0.5 gap-1',
    md: 'text-xs px-2.5 py-1 gap-1.5',
    lg: 'text-sm px-3 py-1.5 gap-2',
  };

  return (
    <div className="inline-flex flex-col items-start">
      <span
        title={config.desc}
        className={`inline-flex items-center font-medium rounded-full border ${config.bg} ${config.color} ${config.border} ${sizeClasses[size]} tracking-wide shadow-sm`}
      >
        {getIcon()}
        <span>{config.label}</span>
      </span>
      {showDesc && (
        <span className="text-[11px] text-slate-400 mt-1 max-w-xs">{config.desc}</span>
      )}
    </div>
  );
};
