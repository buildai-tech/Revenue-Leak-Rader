import React from 'react';

interface ConfidenceBadgeProps {
  score: number | null | undefined;
  size?: 'sm' | 'md';
}

export const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({ score, size = 'md' }) => {
  if (score === null || score === undefined) return null;

  const validScore = Math.max(0, Math.min(100, Math.round(score)));

  let colorClasses = 'bg-rose-500/10 text-rose-400 border-rose-500/20';
  if (validScore >= 80) {
    colorClasses = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
  } else if (validScore >= 50) {
    colorClasses = 'bg-amber-500/10 text-amber-400 border-amber-500/20';
  }

  const sizeClass = size === 'sm' ? 'text-[11px] px-2 py-0.5' : 'text-xs px-2.5 py-1';

  return (
    <span
      title={`Confidence Score: ${validScore}% (derived from sample size and data completeness)`}
      className={`inline-flex items-center font-mono font-medium rounded border ${colorClasses} ${sizeClass}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current mr-1.5 animate-pulse" />
      {validScore}% conf.
    </span>
  );
};
