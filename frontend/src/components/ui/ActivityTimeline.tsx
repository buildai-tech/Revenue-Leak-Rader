import React from 'react';
import { formatDate, formatTimeAgo } from '../../lib/formatters';
import {
  PhoneCall,
  PhoneOutgoing,
  Mail,
  MessageSquare,
  Building,
  UserCheck,
  CheckCircle2,
  AlertCircle,
  Clock,
} from 'lucide-react';

interface EventItem {
  id?: string;
  event_type: string;
  occurred_at: string;
  event_payload?: any;
  source?: string;
}

interface ActivityTimelineProps {
  events: EventItem[];
}

export const ActivityTimeline: React.FC<ActivityTimelineProps> = ({ events }) => {
  if (!events || events.length === 0) {
    return (
      <div className="p-6 text-center text-sm text-slate-500 bg-slate-900/40 rounded-xl border border-slate-800/80">
        No recorded activity events for this lead.
      </div>
    );
  }

  const getEventIcon = (type: string) => {
    switch (type.toLowerCase()) {
      case 'inbound_call':
        return <PhoneCall className="w-3.5 h-3.5 text-blue-400" />;
      case 'outbound_call':
        return <PhoneOutgoing className="w-3.5 h-3.5 text-emerald-400" />;
      case 'inbound_message':
      case 'outbound_message':
        return <MessageSquare className="w-3.5 h-3.5 text-purple-400" />;
      case 'inbound_email':
      case 'outbound_email':
        return <Mail className="w-3.5 h-3.5 text-amber-400" />;
      case 'site_visit':
      case 'walk_in':
        return <Building className="w-3.5 h-3.5 text-cyan-400" />;
      case 'status_change':
        return <CheckCircle2 className="w-3.5 h-3.5 text-rose-400" />;
      case 'created':
        return <UserCheck className="w-3.5 h-3.5 text-slate-400" />;
      default:
        return <Clock className="w-3.5 h-3.5 text-slate-400" />;
    }
  };

  return (
    <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-800">
      {events.map((event, idx) => (
        <div key={event.id || idx} className="relative group">
          {/* Node Dot */}
          <div className="absolute -left-6 top-1 w-5 h-5 rounded-full bg-slate-900 border border-slate-700 flex items-center justify-center shadow">
            {getEventIcon(event.event_type)}
          </div>

          <div className="bg-slate-900/80 border border-slate-800/80 rounded-lg p-3.5 space-y-1 hover:border-slate-700 transition-colors">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-slate-200 capitalize">
                {event.event_type.replace(/_/g, ' ')}
              </span>
              <span className="text-[11px] font-mono text-slate-400" title={formatDate(event.occurred_at)}>
                {formatTimeAgo(event.occurred_at)}
              </span>
            </div>

            {event.event_payload && (
              <div className="text-xs text-slate-300">
                {event.event_payload.note ||
                  event.event_payload.old_status && `Status changed: ${event.event_payload.old_status} → ${event.event_payload.new_status}` ||
                  JSON.stringify(event.event_payload)}
              </div>
            )}

            {event.source && (
              <div className="text-[10px] text-slate-500">
                Source: <span className="font-mono text-slate-400">{event.source}</span>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};
