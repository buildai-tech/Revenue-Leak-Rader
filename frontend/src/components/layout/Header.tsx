import React from 'react';
import { Database, ShieldCheck, HelpCircle, Activity } from 'lucide-react';

export const Header: React.FC = () => {
  return (
    <header className="h-14 border-b border-slate-800/80 bg-[#0c1222]/80 backdrop-blur-md px-6 flex items-center justify-between z-10 shrink-0">
      <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 text-xs text-slate-400">
          <span className="w-2 h-2 rounded-full bg-emerald-400" />
          <span className="text-slate-300 font-medium">Batch Processing</span>
          <span className="text-slate-600">|</span>
          <span className="font-mono text-slate-400">SQLite Engine (v1)</span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-mono">
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>Deterministic Audit V1</span>
        </div>

        <div className="text-xs text-slate-400 flex items-center gap-1.5 border-l border-slate-800 pl-4">
          <Activity className="w-3.5 h-3.5 text-slate-400" />
          <span>Actor: <span className="font-mono text-slate-300">system</span></span>
        </div>
      </div>
    </header>
  );
};

