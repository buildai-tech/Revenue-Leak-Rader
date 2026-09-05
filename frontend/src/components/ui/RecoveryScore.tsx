import React from 'react';

interface RecoveryScoreProps {
  score: number;
  riskLevel?: string;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
}

export const RecoveryScore: React.FC<RecoveryScoreProps> = ({
  score,
  riskLevel,
  size = 'md',
  showLabel = true,
}) => {
  const normalized = Math.max(0, Math.min(100, Math.round(score)));

  const getColor = () => {
    if (normalized >= 75) return 'text-rose-400 stroke-rose-500';
    if (normalized >= 50) return 'text-amber-400 stroke-amber-500';
    if (normalized >= 25) return 'text-blue-400 stroke-blue-500';
    return 'text-slate-400 stroke-slate-500';
  };

  const getRiskBadge = () => {
    const level = riskLevel || (normalized >= 75 ? 'critical' : normalized >= 50 ? 'high' : normalized >= 25 ? 'medium' : 'low');
    const styles = {
      critical: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
      high: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
      medium: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
      low: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
    };
    return (
      <span className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded border ${styles[level as keyof typeof styles]}`}>
        {level} Priority
      </span>
    );
  };

  if (size === 'sm') {
    return (
      <div className="inline-flex items-center gap-2">
        <span className={`font-mono font-bold text-sm ${getColor().split(' ')[0]}`}>{normalized}</span>
        {riskLevel && getRiskBadge()}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <div className="relative flex items-center justify-center w-14 h-14 rounded-full bg-slate-950 border border-slate-800 shadow-inner">
        <span className={`font-mono font-bold text-lg ${getColor().split(' ')[0]}`}>
          {normalized}
        </span>
      </div>
      {showLabel && (
        <div className="space-y-1">
          <div className="text-xs font-semibold text-slate-300">Lead Recovery Score</div>
          {getRiskBadge()}
        </div>
      )}
    </div>
  );
};
