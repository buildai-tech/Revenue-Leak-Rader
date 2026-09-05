import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  AlertOctagon,
  Sparkles,
  KanbanSquare,
  UploadCloud,
  FileBarChart2,
  Radar,
} from 'lucide-react';

const NAV_ITEMS = [
  { name: 'Command Center', path: '/dashboard', icon: LayoutDashboard },
  { name: 'Leads & Score', path: '/leads', icon: Users },
  { name: 'Leakage Events', path: '/leakage', icon: AlertOctagon },
  { name: 'Recommendations', path: '/recommendations', icon: Sparkles },
  { name: 'Interventions', path: '/interventions', icon: KanbanSquare },
  { name: 'Data Ingestion', path: '/data-import', icon: UploadCloud },
  { name: 'Audit & Reports', path: '/reports', icon: FileBarChart2 },
];

export const Sidebar: React.FC = () => {
  return (
    <aside className="w-64 bg-[#0c1222] border-r border-slate-800/80 flex flex-col shrink-0">
      {/* Brand Header */}
      <div className="p-5 border-b border-slate-800/80 flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-blue-600/20 border border-blue-500/40 flex items-center justify-center text-blue-400 shadow-md shadow-blue-500/10">
          <Radar className="w-5 h-5 animate-spin-slow" />
        </div>
        <div>
          <div className="font-bold text-sm text-white tracking-tight flex items-center gap-1.5">
            Revenue Leak Radar
          </div>
          <div className="text-[11px] text-slate-400 font-mono">Real-Estate Intel</div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-blue-600/15 text-blue-400 border border-blue-500/30 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                }`
              }
            >
              <Icon className="w-4 h-4 shrink-0" />
              <span>{item.name}</span>
            </NavLink>
          );
        })}
      </nav>

            {/* Demo Data Persistent Indicator */}
      <div className="p-4 border-t border-slate-800/80 bg-slate-950/40">
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase font-bold tracking-wider text-emerald-400">
              System Active
            </span>
            <span className="inline-flex items-center text-[10px] font-mono px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
              Local Mode (SQLite + Batch)
            </span>
          </div>
          <div className="text-xs text-slate-300 font-medium truncate">GreenVista Realty Demo</div>
          <div className="text-[10px] text-slate-500 font-mono">Org: Bengaluru HQ</div>
        </div>
      </div>
    </aside>
  );
};
